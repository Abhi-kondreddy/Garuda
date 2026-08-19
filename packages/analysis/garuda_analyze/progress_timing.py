from __future__ import annotations

import time
from typing import Any

STAGE_WEIGHTS: dict[str, float] = {
    "ingest": 0.05,
    "audio_extract": 0.08,
    "visual": 0.47,
    "asr": 0.22,
    "audio_features": 0.08,
    "scoring": 0.05,
    "export": 0.05,
}

STAGE_ORDER = [
    "ingest",
    "audio_extract",
    "visual",
    "asr",
    "audio_features",
    "scoring",
    "export",
]


def _normalize_stage(stage: str) -> str:
    if stage in ("frames", "dense_sample"):
        return "visual"
    return stage


def overall_fraction(stage: str, percent: float) -> float:
    normalized = _normalize_stage(stage)
    base = 0.0
    pct = max(0.0, min(100.0, float(percent)))
    for name in STAGE_ORDER:
        weight = STAGE_WEIGHTS.get(name, 0.05)
        if name == normalized:
            return min(0.995, base + weight * (pct / 100.0))
        base += weight
    return min(0.995, base)


class ProgressTimer:
    """Track elapsed + ETA from monotonic overall percent."""

    def __init__(self, t0: float | None = None) -> None:
        self.t0 = t0 if t0 is not None else time.time()

    def elapsed(self) -> float:
        return max(0.0, time.time() - self.t0)

    def enrich(
        self,
        evt: dict[str, Any],
        *,
        percent: float | None = None,
        stage: str | None = None,
    ) -> dict[str, Any]:
        elapsed = self.elapsed()
        evt["elapsedSec"] = round(elapsed, 1)
        pct = percent if percent is not None else float(evt.get("percent") or 0)
        stg = stage if stage is not None else str(evt.get("stage") or "ingest")
        frac = overall_fraction(stg, pct) if stg in STAGE_ORDER or stg in ("frames", "dense_sample") else pct / 100.0
        if frac >= 0.02:
            eta = elapsed * (1.0 / frac - 1.0)
            evt["etaSec"] = round(max(0.0, eta))
        elif evt.get("etaSec") is None:
            evt["etaSec"] = None
        return evt


class ClipBatchTimer:
    """ETA for multi-clip editor jobs from completed clip durations."""

    def __init__(self) -> None:
        self.t0 = time.time()
        self.completed: list[float] = []

    def elapsed(self) -> float:
        return max(0.0, time.time() - self.t0)

    def note_clip_done(self, seconds: float) -> None:
        if seconds > 0:
            self.completed.append(seconds)

    def enrich(
        self,
        evt: dict[str, Any],
        *,
        clip_index: int | None = None,
        clip_total: int | None = None,
        percent: float | None = None,
    ) -> dict[str, Any]:
        elapsed = self.elapsed()
        evt["elapsedSec"] = round(elapsed, 1)
        idx = clip_index if clip_index is not None else evt.get("clipIndex")
        total = clip_total if clip_total is not None else evt.get("clipTotal")
        pct = percent if percent is not None else float(evt.get("percent") or 0)
        if idx and total and int(total) > 0:
            done = max(0, int(idx) - 1)
            remaining = max(0, int(total) - done)
            if self.completed:
                avg = sum(self.completed) / len(self.completed)
                evt["etaSec"] = round(max(0.0, avg * remaining))
            elif pct > 3:
                evt["etaSec"] = round(max(0.0, elapsed * (100.0 / pct - 1.0)))
        elif pct > 3:
            evt["etaSec"] = round(max(0.0, elapsed * (100.0 / pct - 1.0)))
        return evt
