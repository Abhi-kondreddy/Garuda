from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Callable

from .asr import run_asr
from .audio_features import analyze_audio
from .frames import analyze_frames
from .scoring import build_report


Emit = Callable[[dict], None]


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
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr.strip() or proc.stdout.strip()}")
    data = json.loads(proc.stdout)
    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not video_stream:
        raise RuntimeError("No video stream found in file")

    duration = float(data.get("format", {}).get("duration") or video_stream.get("duration") or 0)
    fps_raw = video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "30/1"
    if isinstance(fps_raw, str) and "/" in fps_raw:
        num, den = fps_raw.split("/", 1)
        fps = float(num) / max(float(den), 1e-6)
    else:
        fps = float(fps_raw or 30)

    return {
        "duration": duration,
        "fps": fps,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "has_audio": audio_stream is not None,
        "codec": video_stream.get("codec_name"),
    }


def _extract_audio(ffmpeg: str, video_path: Path, wav_path: Path) -> None:
    cmd = [
        ffmpeg,
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
        str(wav_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extract failed: {proc.stderr[-800:]}")


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
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

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
    emit(
        {
            "type": "progress",
            "stage": "ingest",
            "percent": 100,
            "message": f"Loaded {meta['width']}x{meta['height']} @ {meta['fps']:.2f}fps",
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
        _extract_audio(ffmpeg, video_path, wav_path)
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

    frame_data = analyze_frames(
        video_path=video_path,
        duration=meta["duration"],
        fps=meta["fps"],
        on_progress=visual_progress,
        sample_every=sample_every,
    )

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

        transcript = run_asr(wav_path, model_size=whisper_model, on_progress=asr_progress)
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
    audio_data = analyze_audio(wav_path if wav_path.exists() else None, meta["duration"])
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
    report = build_report(
        video_path=video_path,
        meta=meta,
        frame_data=frame_data,
        audio_data=audio_data,
        transcript=transcript,
    )
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
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
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
