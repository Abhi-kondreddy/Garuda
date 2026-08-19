from __future__ import annotations

import json
import math
import subprocess
import time
from pathlib import Path
from typing import Callable

from . import config
from .asr import run_asr
from .audio_features import analyze_audio
from .detectors import detect_scenes
from .frames import analyze_frames
from .preflight import preflight
from .scoring import build_report
from .validation import write_report
from .watchdog import Watchdog

# Hard ceilings so a stalled/locked binary can never hang the whole subprocess.
PROBE_TIMEOUT_SEC = 60
EXTRACT_TIMEOUT_SEC = 1800


Emit = Callable[[dict], None]


def _parse_float(value: object) -> float | None:
    """Parse a possibly-dirty ffprobe value (``"N/A"``, ``None``, ``12.3``)."""
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _parse_fps(*candidates: object) -> float:
    """Resolve fps from ffprobe rate strings, rejecting ``"0/0"`` / invalid.

    ffprobe reports ``avg_frame_rate`` as ``"0/0"`` for some containers; that is
    truthy, so naively preferring it yields ``fps = 0`` and corrupts every
    timeline timestamp. Fall back ``avg_frame_rate -> r_frame_rate -> 30``.
    """
    for c in candidates:
        if isinstance(c, str) and "/" in c:
            num, den = c.split("/", 1)
            n = _parse_float(num)
            d = _parse_float(den)
            if n and d and n > 0 and d > 0:
                return n / d
            continue
        f = _parse_float(c)
        if f and f > 0:
            return f
    return 30.0


def _probe(ffprobe: str, video_path: Path) -> dict:
    cmd = [
        ffprobe,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=PROBE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timed out after {PROBE_TIMEOUT_SEC}s on {video_path.name}")
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr.strip() or proc.stdout.strip()}")
    data = json.loads(proc.stdout)
    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not video_stream:
        raise RuntimeError("No video stream found in file")

    duration = (
        _parse_float(data.get("format", {}).get("duration"))
        or _parse_float(video_stream.get("duration"))
        or 0.0
    )
    fps = _parse_fps(video_stream.get("avg_frame_rate"), video_stream.get("r_frame_rate"))

    rotation = 0
    for sd in video_stream.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(sd.get("rotation") or 0)
    if not rotation:
        try:
            rotation = int(video_stream.get("tags", {}).get("rotate") or 0)
        except (TypeError, ValueError):
            rotation = 0

    return {
        "duration": max(0.0, duration),
        "fps": fps,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "has_audio": audio_stream is not None,
        "codec": video_stream.get("codec_name"),
        "avg_frame_rate": video_stream.get("avg_frame_rate"),
        "r_frame_rate": video_stream.get("r_frame_rate"),
        "pix_fmt": video_stream.get("pix_fmt"),
        "color_transfer": video_stream.get("color_transfer"),
        "bit_rate": _parse_float(
            video_stream.get("bit_rate") or data.get("format", {}).get("bit_rate")
        ),
        "rotation": rotation,
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        "audio_channels": int(audio_stream.get("channels") or 0) if audio_stream else 0,
    }


def _extract_audio(
    ffmpeg: str,
    video_path: Path,
    wav_path: Path,
    duration: float = 0.0,
    on_progress: "Callable[[float, float | None], None] | None" = None,
) -> None:
    cmd = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-progress",
        "pipe:1",
        "-nostats",
        str(wav_path),
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
    )
    start = time.time()
    try:
        # `-progress pipe:1` emits `key=value` lines; out_time_ms tracks position.
        for line in proc.stdout or []:
            if on_progress and duration > 0 and line.startswith("out_time_ms="):
                try:
                    done = max(0.0, float(line.split("=", 1)[1]) / 1_000_000.0)
                    pct = min(99.0, 100.0 * done / duration)
                    elapsed = time.time() - start
                    eta = (elapsed / done) * (duration - done) if done > 0.5 else None
                    on_progress(pct, eta)
                except (ValueError, IndexError):
                    pass
            if time.time() - start > EXTRACT_TIMEOUT_SEC:
                proc.kill()
                raise RuntimeError(f"ffmpeg audio extract timed out after {EXTRACT_TIMEOUT_SEC}s")
        code = proc.wait(timeout=30)
    finally:
        try:
            proc.stdout and proc.stdout.close()
        except Exception:
            pass
    err = ""
    try:
        err = (proc.stderr.read() if proc.stderr else "") or ""
    except Exception:
        pass
    if code != 0:
        raise RuntimeError(f"ffmpeg audio extract failed: {err[-800:]}")


def run_pipeline(
    *,
    video_path: Path,
    out_dir: Path,
    ffmpeg: str,
    ffprobe: str,
    whisper_model: str,
    skip_asr: bool,
    emit: Emit,
    sample_every: int | None = None,
    asr_beam: int = 1,
    word_timestamps: bool = True,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    def _warn(stage: str, message: str) -> None:
        """Report a recoverable stage failure without aborting the whole run."""
        emit(
            {
                "type": "progress",
                "stage": stage,
                "percent": 100,
                "message": message,
                "etaSec": None,
                "phase": "warn",
                "phasePercent": 100,
            }
        )

    emit(
        {
            "type": "progress",
            "stage": "ingest",
            "percent": 5,
            "message": "Probing media…",
            "etaSec": None,
            "phase": "probe",
            "phasePercent": 20,
        }
    )
    meta = _probe(ffprobe, video_path)
    budget = config.ANALYSIS_WALLCLOCK_BASE_SEC + config.ANALYSIS_WALLCLOCK_PER_MIN_SEC * (
        meta["duration"] / 60.0
    )
    watchdog = Watchdog(budget_sec=budget, memory_limit_mb=config.ANALYSIS_MEMORY_LIMIT_MB)
    pf = preflight(meta)
    emit(
        {
            "type": "progress",
            "stage": "ingest",
            "percent": 100,
            "message": f"Loaded {meta['width']}x{meta['height']} @ {meta['fps']:.2f}fps"
            + (f" · {len(pf['warnings'])} QC warning(s)" if pf["warnings"] else ""),
            "etaSec": max(1, meta["duration"] * 0.4),
            "phase": "probe",
            "phasePercent": 100,
        }
    )

    wav_path = out_dir / "audio.wav"
    if meta["has_audio"]:
        emit(
            {
                "type": "progress",
                "stage": "audio_extract",
                "percent": 10,
                "message": "Extracting mono 16kHz audio…",
                "etaSec": None,
                "phase": "extract",
                "phasePercent": 15,
            }
        )
        def extract_progress(pct: float, eta: float | None) -> None:
            emit(
                {
                    "type": "progress",
                    "stage": "audio_extract",
                    "percent": int(min(99, max(10, pct))),
                    "message": f"Extracting mono 16kHz audio… {int(pct)}%",
                    "etaSec": round(eta, 1) if eta else None,
                    "phase": "extract",
                    "phasePercent": int(pct),
                }
            )

        _extract_audio(
            ffmpeg, video_path, wav_path, duration=meta["duration"], on_progress=extract_progress
        )
        emit(
            {
                "type": "progress",
                "stage": "audio_extract",
                "percent": 100,
                "message": "Audio track ready",
                "etaSec": None,
                "phase": "extract",
                "phasePercent": 100,
            }
        )
    else:
        emit(
            {
                "type": "progress",
                "stage": "audio_extract",
                "percent": 100,
                "message": "No audio stream — skipping extract",
                "etaSec": None,
                "phase": "extract",
                "phasePercent": 100,
            }
        )

    def visual_progress(pct: float, message: str) -> None:
        emit(
            {
                "type": "progress",
                "stage": "visual",
                "percent": int(pct),
                "message": message,
                "etaSec": None,
                "phase": "decode",
                "phasePercent": int(pct),
            }
        )

    try:
        frame_data = analyze_frames(
            video_path=video_path,
            duration=meta["duration"],
            fps=meta["fps"],
            on_progress=visual_progress,
            sample_every=sample_every,
        )
    except Exception as exc:  # noqa: BLE001 — degrade to a partial report
        _warn("visual", f"Visual analysis failed ({exc.__class__.__name__}) — partial report")
        frame_data = {}

    # Prefer PySceneDetect's content detector for cuts when available and the
    # clip is short enough that a second decode pass is acceptable.
    if 0 < meta["duration"] <= config.SCENE_DETECT_MAX_SEC:
        try:
            sd_cuts = detect_scenes(video_path)
            if sd_cuts is not None:
                frame_data["scene_cuts"] = sd_cuts
        except Exception:
            pass
    watchdog.check("visual")

    transcript = []
    if meta["has_audio"] and wav_path.exists() and not skip_asr:
        emit(
            {
                "type": "progress",
                "stage": "asr",
                "percent": 5,
                "message": "Running local speech recognition (Telugu/English)…",
                "etaSec": None,
                "phase": "load",
                "phasePercent": 0,
            }
        )

        def asr_progress(
            pct: float,
            message: str,
            *,
            phase: str | None = None,
            phase_percent: float | None = None,
        ) -> None:
            emit(
                {
                    "type": "progress",
                    "stage": "asr",
                    "percent": int(pct),
                    "message": message,
                    "etaSec": None,
                    "phase": phase,
                    "phasePercent": int(phase_percent) if phase_percent is not None else int(pct),
                }
            )

        try:
            transcript = run_asr(
                wav_path,
                model_size=whisper_model,
                on_progress=asr_progress,
                beam_size=asr_beam,
                word_timestamps=word_timestamps,
            )
        except Exception as exc:  # noqa: BLE001 — ASR is best-effort
            _warn("asr", f"ASR failed ({exc.__class__.__name__}) — continuing without transcript")
            transcript = []
        emit(
            {
                "type": "progress",
                "stage": "asr",
                "percent": 100,
                "message": f"ASR complete — {len(transcript)} segments",
                "etaSec": None,
                "phase": "transcribe",
                "phasePercent": 100,
            }
        )
    else:
        emit(
            {
                "type": "progress",
                "stage": "asr",
                "percent": 100,
                "message": "ASR skipped",
                "etaSec": None,
                "phase": "transcribe",
                "phasePercent": 100,
            }
        )

    emit(
        {
            "type": "progress",
            "stage": "audio_features",
            "percent": 20,
            "message": "Measuring loudness, silence, energy…",
            "etaSec": None,
            "phase": "features",
            "phasePercent": 25,
        }
    )
    try:
        audio_data = analyze_audio(wav_path if wav_path.exists() else None, meta["duration"])
    except Exception as exc:  # noqa: BLE001 — degrade to empty audio metrics
        _warn("audio_features", f"Audio analysis failed ({exc.__class__.__name__}) — partial report")
        audio_data = analyze_audio(None, meta["duration"])
    emit(
        {
            "type": "progress",
            "stage": "audio_features",
            "percent": 100,
            "message": "Audio features ready",
            "etaSec": None,
            "phase": "features",
            "phasePercent": 100,
        }
    )

    emit(
        {
            "type": "progress",
            "stage": "scoring",
            "percent": 30,
            "message": "Computing hook, interestingness, color & quality scores…",
            "etaSec": None,
            "phase": "score",
            "phasePercent": 40,
        }
    )
    watchdog.check("audio_features")
    report = build_report(
        video_path=video_path,
        meta=meta,
        frame_data=frame_data,
        audio_data=audio_data,
        transcript=transcript,
    )
    watchdog.check("scoring")
    emit(
        {
            "type": "progress",
            "stage": "scoring",
            "percent": 100,
            "message": "Scores locked",
            "etaSec": None,
            "phase": "score",
            "phasePercent": 100,
        }
    )

    emit(
        {
            "type": "progress",
            "stage": "export",
            "percent": 40,
            "message": "Writing report.json…",
            "etaSec": None,
            "phase": "write",
            "phasePercent": 50,
        }
    )
    # Attach preflight QC + run stats to the report diagnostics.
    watchdog.stop()
    run_stats = {"peakRssMb": watchdog.peak_rss_mb(), "elapsedSec": round(watchdog.elapsed(), 2)}
    if isinstance(report.get("diagnostics"), dict):
        report["diagnostics"]["preflight"] = pf
        report["diagnostics"]["run"] = run_stats
    else:
        report["diagnostics"] = {"preflight": pf, "run": run_stats}

    # Calibrated predictions when a trained model is present (else heuristic stays).
    try:
        from .calibration.apply import apply_calibration

        if apply_calibration(report):
            report["diagnostics"]["calibration"] = report.get("predictions", {}).get(
                "calibrationVersion", "applied"
            )
    except Exception:
        pass

    # Content hash (for cache/dedupe) + percentile benchmarks vs history.
    try:
        from .cache import content_hash

        ch = content_hash(video_path)
        if ch:
            report["contentHash"] = ch
    except Exception:
        pass
    try:
        from .benchmark import build_benchmarks

        report["benchmarks"] = build_benchmarks(report, out_dir.parent)
    except Exception:
        pass

    # Face-aware thumbnail candidates for the peak moments (best-effort).
    try:
        from .thumbnails import export_thumbnails

        peak_ts = [float(h["t"]) for h in (report.get("highlights") or [])]
        report["thumbnailFiles"] = export_thumbnails(
            video_path, peak_ts, report.get("faceBoxes") or [], out_dir / "thumbs"
        )
    except Exception:
        report["thumbnailFiles"] = []

    report_path = out_dir / "report.json"
    valid, errors = write_report(report, report_path)
    if not valid:
        _warn("export", f"Report schema warnings ({len(errors)}) — wrote repaired report")

    # Emit subtitles next to the report so the UI can offer SRT/VTT export.
    if report.get("transcript"):
        try:
            from .captions import write_captions

            write_captions(report["transcript"], out_dir)
        except Exception:
            pass

    elapsed = time.time() - t0
    emit(
        {
            "type": "progress",
            "stage": "export",
            "percent": 100,
            "message": f"Report exported in {elapsed:.1f}s",
            "etaSec": 0,
            "phase": "write",
            "phasePercent": 100,
        }
    )
    return report_path
