from __future__ import annotations

import os
import time
from typing import Any

PerformanceMode = str

MODES: dict[str, dict[str, Any]] = {
    "eco": {
        "label": "Eco",
        "nice": 10,
        "frame_sleep_ms": 12,
        "stage_sleep_ms": 180,
        "opencv_threads": 1,
        "ffmpeg_threads": "2",
    },
    "balanced": {
        "label": "Balanced",
        "nice": 0,
        "frame_sleep_ms": 0,
        "stage_sleep_ms": 0,
        "opencv_threads": 0,
        "ffmpeg_threads": "0",
    },
    "high": {
        "label": "High",
        "nice": 0,
        "frame_sleep_ms": 0,
        "stage_sleep_ms": 0,
        "opencv_threads": 0,
        "ffmpeg_threads": "0",
        "boost_nice": -4,
    },
}

# Extra throttling when the desktop guard taps "Force Eco" mid-job.
FORCED_ECO_BOOST: dict[str, Any] = {
    "frame_sleep_ms": 40,
    "stage_sleep_ms": 400,
    "opencv_threads": 1,
    "ffmpeg_threads": "1",
}

_mode: PerformanceMode = "balanced"
_forced_live = False
_override_path: str | None = None
_last_override_mtime = 0.0


def normalize_mode(mode: str | None) -> PerformanceMode:
    if mode in MODES:
        return mode
    return "balanced"


def configure_performance(mode: str | None = None) -> PerformanceMode:
    """Apply process priority + library thread limits. Same analysis depth in every mode."""
    global _mode
    env_mode = os.environ.get("GARUDA_PERFORMANCE_MODE")
    _mode = normalize_mode(mode or env_mode)
    refresh_override(force=True)
    if not _forced_live:
        _apply_mode_config(_mode)
    return _mode


def _apply_mode_config(mode: PerformanceMode) -> None:
    cfg = effective_config(mode, _forced_live)
    try:
        if mode == "high" and not _forced_live:
            boost = int(MODES[mode].get("boost_nice") or 0)
            if boost < 0:
                try:
                    os.nice(boost)
                except OSError:
                    pass
        elif int(cfg.get("nice") or 0) > 0:
            os.nice(int(cfg["nice"]))
    except OSError:
        pass

    try:
        import cv2

        threads = int(cfg.get("opencv_threads") or 0)
        if threads > 0:
            cv2.setNumThreads(threads)
    except Exception:
        pass


def effective_config(mode: PerformanceMode | None = None, forced: bool = False) -> dict[str, Any]:
    base = dict(MODES[mode or _mode])
    if forced:
        for key, val in FORCED_ECO_BOOST.items():
            if key.endswith("_ms"):
                base[key] = max(int(base.get(key) or 0), int(val))
            else:
                base[key] = val
    return base


def refresh_override(*, force: bool = False) -> None:
    """Hot-switch mode while a job is running (written by the desktop guard)."""
    global _last_override_mtime, _mode, _forced_live
    path = _override_path or os.environ.get("GARUDA_PERF_OVERRIDE_PATH")
    if not path:
        return
    try:
        import json
        from pathlib import Path

        p = Path(path)
        if not p.exists():
            if _forced_live:
                _forced_live = False
            return
        mtime = p.stat().st_mtime
        if not force and mtime == _last_override_mtime:
            return
        _last_override_mtime = mtime
        data = json.loads(p.read_text(encoding="utf-8"))
        mode = normalize_mode(data.get("mode"))
        forced = bool(data.get("force")) or mode == "eco"
        changed = mode != _mode or forced != _forced_live
        _mode = mode
        _forced_live = forced and mode == "eco"
        if changed or force:
            _apply_mode_config(_mode)
    except Exception:
        pass


def current_mode() -> PerformanceMode:
    return _mode


def current_config() -> dict[str, Any]:
    return effective_config(_mode, _forced_live)


def yield_frame_tick() -> None:
    """Pause decode loop in eco mode — same frames analyzed, just slower."""
    refresh_override()
    ms = int(current_config().get("frame_sleep_ms") or 0)
    if ms > 0:
        time.sleep(ms / 1000.0)


def yield_stage() -> None:
    refresh_override()
    ms = int(current_config().get("stage_sleep_ms") or 0)
    if ms > 0:
        time.sleep(ms / 1000.0)


def ffmpeg_thread_args() -> list[str]:
    refresh_override()
    threads = str(current_config().get("ffmpeg_threads") or "0")
    if threads and threads != "0":
        return ["-threads", threads]
    return []
