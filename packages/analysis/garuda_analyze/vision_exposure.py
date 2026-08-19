"""Exposure & color parameters (white balance, tint, clipping, grade)."""

from __future__ import annotations

import numpy as np

from .metrics import REGISTRY, Metric, unavailable
from .util import clamp


@REGISTRY.register("vision_exposure", group="visual")
def _exposure(ctx: dict) -> "list[Metric]":
    fd = ctx.get("frame_data") or {}
    rgb = np.asarray(fd.get("rgb_means") or [], dtype=float)
    hi = np.asarray(fd.get("highlight_clip") or [], dtype=float)
    lo = np.asarray(fd.get("shadow_clip") or [], dtype=float)
    out: list[Metric] = []

    if rgb.size and rgb.ndim == 2 and rgb.shape[1] == 3:
        r, g, b = float(rgb[:, 0].mean()), float(rgb[:, 1].mean()), float(rgb[:, 2].mean())
        rb = r / max(b, 1e-6)
        wb_score = clamp(100.0 - abs(rb - 1.0) * 120.0)
        cast = "warm/orange cast" if rb > 1.12 else "cool/blue cast" if rb < 0.89 else None
        out.append(
            Metric("whiteBalance", "White balance neutrality", round(wb_score, 1), "points", (0, 100),
                   "rgb_ratio", confidence=0.6, group="visual",
                   severity=("medium" if wb_score < 55 else "low"),
                   recommendation=(f"Correct {cast}" if cast else None))
        )
        tint = g - (r + b) / 2.0
        out.append(
            Metric("tint", "Green-magenta tint", round(tint, 1), "level", (-128, 128), "rgb_channel",
                   confidence=0.5, group="visual",
                   recommendation=("Pull green" if tint > 8 else "Pull magenta" if tint < -8 else None))
        )
        grade_std = float(np.mean(np.std(rgb, axis=0)))
        out.append(
            Metric("gradeConsistency", "Color grade consistency", round(clamp(100.0 - grade_std * 1.5), 1),
                   "points", (0, 100), "rgb_std", confidence=0.6, group="visual")
        )
    else:
        out.append(unavailable("whiteBalance", "White balance neutrality", "rgb_ratio", "visual", "No sampled frames"))

    if hi.size:
        highlight = float(hi.mean() * 100.0)
        out.append(
            Metric("highlightClipping", "Blown highlights", round(highlight, 2), "%", (0, 100),
                   "luma_threshold", confidence=0.7, group="visual",
                   severity=("high" if highlight > 5 else "medium" if highlight > 1 else "low"),
                   recommendation=("Lower exposure / recover highlights" if highlight > 5 else None))
        )
    if lo.size:
        shadow = float(lo.mean() * 100.0)
        out.append(
            Metric("shadowClipping", "Crushed shadows", round(shadow, 2), "%", (0, 100),
                   "luma_threshold", confidence=0.7, group="visual",
                   severity=("high" if shadow > 12 else "medium" if shadow > 4 else "low"),
                   recommendation=("Lift shadows / add fill" if shadow > 12 else None))
        )
    return out
