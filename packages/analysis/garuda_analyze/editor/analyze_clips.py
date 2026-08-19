from __future__ import annotations

import json
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

from ..pipeline import run_pipeline
from ..performance import yield_stage
from ..progress_timing import ClipBatchTimer

Emit = Optional[Callable[[dict], None]]

REPORT_SCHEMA_VERSION = 3
REQUIRED_REPORT_FIELDS = ("pacing",)


def is_clip_report_fresh(report: Optional[dict]) -> bool:
    if not report:
        return False
    try:
        version = int(report.get("version") or 0)
    except (TypeError, ValueError):
        return False
    if version < REPORT_SCHEMA_VERSION:
        return False
    for key in REQUIRED_REPORT_FIELDS:
        if not report.get(key):
            return False
    visual = report.get("visual") or {}
    if visual.get("verticalCropSafe") is None:
        return False
    return True


def count_stale_clips(project_path: Path, clips: list[dict]) -> int:
    stale = 0
    for clip in clips:
        cid = clip.get("id")
        if not cid:
            stale += 1
            continue
        path = Path(clip.get("path") or "")
        cached = load_clip_report(project_path, str(cid))
        if not cached or cached.get("sourcePath") != str(path) or not is_clip_report_fresh(cached):
            stale += 1
    return stale


def _emit(
    emit: Emit,
    percent: float,
    message: str,
    *,
    stage: str = "analyze",
    phase: str | None = None,
    phase_percent: float | None = None,
    clip_index: int | None = None,
    clip_total: int | None = None,
    clip_name: str | None = None,
    timer: ClipBatchTimer | None = None,
) -> None:
    if emit:
        evt: dict[str, Any] = {
            "type": "progress",
            "stage": stage,
            "percent": int(max(0, min(100, percent))),
            "message": message,
        }
        if phase is not None:
            evt["phase"] = phase
        if phase_percent is not None:
            evt["phasePercent"] = int(max(0, min(100, phase_percent)))
        if clip_index is not None:
            evt["clipIndex"] = clip_index
        if clip_total is not None:
            evt["clipTotal"] = clip_total
        if clip_name is not None:
            evt["clipName"] = clip_name
        if timer is not None:
            timer.enrich(evt, clip_index=clip_index, clip_total=clip_total, percent=percent)
        emit(evt)


def analysis_cache_dir(project_path: Path) -> Path:
    return project_path.parent / "clip_analysis"


def clip_report_path(project_path: Path, clip_id: str) -> Path:
    return analysis_cache_dir(project_path) / clip_id / "report.json"


def load_clip_report(project_path: Path, clip_id: str) -> Optional[dict]:
    p = clip_report_path(project_path, clip_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _editor_sample_every(duration: float, width: int = 0, fps: float = 30.0) -> int:
    """Stride so we still read the file but don't OOM on 4K every-frame decode."""
    target_hz = 6.0
    if duration > 180:
        target_hz = 3.0
    elif duration > 90:
        target_hz = 4.0
    if width >= 3000:
        target_hz = min(target_hz, 2.5)
    elif width >= 1920:
        target_hz = min(target_hz, 4.0)
    fps = fps if fps > 1 else 30.0
    return max(1, int(round(fps / target_hz)))


def analyze_project_clips(
    *,
    project: dict,
    project_path: Path,
    ffmpeg: str,
    ffprobe: str,
    whisper_model: str = "tiny",
    skip_asr: bool = True,
    force: bool = False,
    emit: Emit = None,
) -> dict[str, dict]:
    """
    Run Garuda analysis on every day-pool clip (cached under clip_analysis/<id>/).
    Per-clip failures are skipped so one bad file does not kill the whole propose.
    """
    clips = list(project.get("clips") or [])
    if not clips:
        return {}

    reports: dict[str, dict] = {}
    n = len(clips)
    batch_timer = ClipBatchTimer()
    stale_n = count_stale_clips(project_path, clips)
    stale_note = f" ({stale_n} clip(s) need re-analysis)" if stale_n else ""
    _emit(
        emit,
        1,
        f"Deep propose: reading {n} clip(s){stale_note}…",
        stage="propose",
        phase="probe",
        phase_percent=10,
        timer=batch_timer,
    )

    for i, clip in enumerate(clips):
        cid = clip.get("id") or f"clip-{i}"
        path = Path(clip.get("path") or "")
        clip_name = str(clip.get("name") or path.name)
        base = 5 + (i / max(n, 1)) * 80
        _emit(
            emit,
            base,
            f"[{i + 1}/{n}] Reading {clip_name}",
            stage="analyze",
            phase="probe",
            phase_percent=5,
            clip_index=i + 1,
            clip_total=n,
            clip_name=clip_name,
            timer=batch_timer,
        )

        if not path.exists():
            _emit(
                emit,
                base + 1,
                f"[{i + 1}/{n}] Missing file, skipping {clip_name}",
                stage="analyze",
                clip_index=i + 1,
                clip_total=n,
                clip_name=clip_name,
            )
            continue

        cached = None if force else load_clip_report(project_path, cid)
        if cached and cached.get("sourcePath") == str(path) and is_clip_report_fresh(cached):
            reports[cid] = cached
            batch_timer.note_clip_done(0.15)
            _emit(
                emit,
                base + 80 / max(n, 1),
                f"[{i + 1}/{n}] Cached analysis · {clip_name}",
                stage="analyze",
                phase="cache",
                phase_percent=100,
                clip_index=i + 1,
                clip_total=n,
                clip_name=clip_name,
                timer=batch_timer,
            )
            continue

        out_dir = analysis_cache_dir(project_path) / cid
        out_dir.mkdir(parents=True, exist_ok=True)

        dur = float(clip.get("durationSec") or 0) or 60.0
        name = (clip.get("name") or "").lower()
        width_guess = 3840 if any(k in name for k in ("4096", "2160", "uhd", "4k")) else 1920
        sample_every = _editor_sample_every(dur, width_guess, 30.0)

        clip_t0 = time.time()

        def clip_emit(evt: dict) -> None:
            if not emit:
                return
            stage_pct = float(evt.get("percent") or 0)
            overall = base + (stage_pct / 100.0) * (75.0 / max(n, 1))
            msg = evt.get("message") or evt.get("stage") or "Analyzing…"
            inner_stage = str(evt.get("stage") or "analyze")
            phase_map = {
                "ingest": "probe",
                "audio_extract": "extract",
                "visual": "decode",
                "asr": "transcribe",
                "audio_features": "features",
                "scoring": "score",
                "export": "write",
            }
            out_evt: dict[str, Any] = {
                "type": "progress",
                "stage": "analyze",
                "percent": int(min(88, overall)),
                "message": f"[{i + 1}/{n}] {msg}",
                "phase": evt.get("phase") or phase_map.get(inner_stage) or "decode",
                "phasePercent": int(evt.get("phasePercent") or stage_pct),
                "clipIndex": i + 1,
                "clipTotal": n,
                "clipName": clip_name,
            }
            if evt.get("elapsedSec") is not None:
                out_evt["elapsedSec"] = evt["elapsedSec"]
            if evt.get("etaSec") is not None:
                out_evt["etaSec"] = evt["etaSec"]
            batch_timer.enrich(
                out_evt,
                clip_index=i + 1,
                clip_total=n,
                percent=float(out_evt["percent"]),
            )
            emit(out_evt)

        try:
            report_path = run_pipeline(
                video_path=path,
                out_dir=out_dir,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                whisper_model=whisper_model,
                skip_asr=skip_asr,
                emit=clip_emit,
                sample_every=sample_every,
            )
            yield_stage()
            report = json.loads(Path(report_path).read_text(encoding="utf-8"))
            report["editorClipId"] = cid
            Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
            reports[cid] = report
            batch_timer.note_clip_done(time.time() - clip_t0)
            yield_stage()
        except Exception as exc:  # noqa: BLE001
            _emit(
                emit,
                base + 5,
                f"[{i + 1}/{n}] Failed on {clip_name}: {exc} — continuing",
                stage="analyze",
                clip_index=i + 1,
                clip_total=n,
                clip_name=clip_name,
                timer=batch_timer,
            )
            fail_path = out_dir / "analyze_error.txt"
            fail_path.write_text(f"{exc}\n\n{traceback.format_exc()[-1500:]}", encoding="utf-8")
            continue

    _emit(
        emit,
        88,
        f"Analyzed {len(reports)}/{n} clips — building proposal…",
        stage="assemble",
        phase="assemble",
        phase_percent=40,
        clip_total=n,
        timer=batch_timer,
    )
    return reports
