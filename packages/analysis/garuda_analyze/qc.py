"""Technical QC parameters surfaced as metrics (resolution, aspect, black/freeze)."""

from __future__ import annotations

import numpy as np

from .metrics import REGISTRY, Metric


def _aspect(w: int, h: int) -> str:
    if w <= 0 or h <= 0:
        return "unknown"
    r = w / h
    for label, target in (("16:9", 16 / 9), ("9:16", 9 / 16), ("1:1", 1.0), ("4:3", 4 / 3)):
        if abs(r - target) < 0.06:
            return label
    return f"{r:.2f}:1"


@REGISTRY.register("qc", group="technical")
def _qc(ctx: dict) -> "list[Metric]":
    meta = ctx.get("meta") or {}
    fd = ctx.get("frame_data") or {}
    w = int(meta.get("width") or 0)
    h = int(meta.get("height") or 0)
    out: list[Metric] = []

    aspect = _aspect(w, h)
    out.append(
        Metric("aspectRatio", "Aspect ratio", aspect, "", None, "dimensions", confidence=1.0,
               group="technical")
    )
    out.append(
        Metric("resolution", "Resolution", f"{w}x{h}", "px", None, "dimensions", confidence=1.0,
               group="technical",
               recommendation=("Below 1080p — consider higher capture resolution" if h and h < 1080 else None),
               severity=("medium" if h and h < 720 else "low"))
    )
    br = meta.get("bit_rate")
    if isinstance(br, (int, float)) and br > 0:
        out.append(
            Metric("bitrate", "Bitrate", round(br / 1000.0, 1), "kbps", (0, 200000), "container",
                   confidence=0.8, group="technical")
        )

    # Black / freeze hints from already-decoded arrays (no extra decode pass).
    bri = np.asarray(fd.get("brightness") or [], dtype=float)
    if bri.size:
        black_ratio = float(np.mean(bri < 12.0)) * 100.0
        out.append(
            Metric("blackFrameRatio", "Black frames", round(black_ratio, 2), "%", (0, 100), "luma",
                   confidence=0.6, group="technical",
                   severity=("medium" if black_ratio > 5 else "low"))
        )
    motion = np.asarray(fd.get("motion") or [], dtype=float)
    if motion.size:
        freeze_ratio = float(np.mean(motion < 0.4)) * 100.0
        out.append(
            Metric("freezeFrameRatio", "Freeze / static frames", round(freeze_ratio, 2), "%", (0, 100),
                   "interframe_delta", confidence=0.5, group="technical")
        )
    return out
