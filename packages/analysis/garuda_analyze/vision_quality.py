"""Sharpness / focus / stabilization / motion-blur parameters."""

from __future__ import annotations

import numpy as np

from .metrics import REGISTRY, Metric, unavailable
from .util import clamp


@REGISTRY.register("vision_quality", group="visual")
def _quality(ctx: dict) -> "list[Metric]":
    fd = ctx.get("frame_data") or {}
    sharp = np.asarray(fd.get("sharpness") or [], dtype=float)
    motion = np.asarray(fd.get("motion") or [], dtype=float)
    out: list[Metric] = []

    if sharp.size:
        med = float(np.median(sharp))
        sharp_score = clamp(float(np.interp(med, [5.0, 150.0], [0.0, 100.0])))
        out.append(
            Metric("sharpness", "Sharpness / focus", round(sharp_score, 1), "points", (0, 100),
                   "laplacian_var", confidence=0.6, group="visual",
                   severity=("medium" if sharp_score < 40 else "low"),
                   recommendation=("Footage looks soft / out of focus" if sharp_score < 40 else None))
        )
        oof = float(np.mean(sharp < 10.0))
        out.append(
            Metric("outOfFocusRatio", "Out-of-focus frames", round(oof * 100.0, 1), "%", (0, 100),
                   "laplacian_threshold", confidence=0.5, group="visual")
        )
        if motion.size == sharp.size and motion.size:
            hi_mot = motion > np.percentile(motion, 75)
            blur = float(np.mean(sharp[hi_mot] < med * 0.6)) if bool(hi_mot.any()) else 0.0
            out.append(
                Metric("motionBlur", "Motion blur", round(blur * 100.0, 1), "%", (0, 100),
                       "sharpness_vs_motion", confidence=0.4, group="visual")
            )
    else:
        out.append(unavailable("sharpness", "Sharpness / focus", "laplacian_var", "visual", "No sampled frames"))

    if motion.size > 2:
        hf = float(np.mean(np.abs(np.diff(motion))))
        shake = clamp(float(np.interp(hf, [0.0, 8.0], [0.0, 100.0])))
        out.append(
            Metric("cameraShake", "Camera shake", round(shake, 1), "points", (0, 100), "motion_high_freq",
                   confidence=0.5, group="visual", severity=("medium" if shake > 60 else "low"),
                   recommendation=("Stabilize in post or use a gimbal" if shake > 60 else None))
        )
        out.append(
            Metric("motionSaliency", "Motion saliency", round(clamp(float(np.mean(motion)) * 4.0), 1),
                   "points", (0, 100), "mean_motion", confidence=0.4, group="visual")
        )

    # Rolling shutter needs edge/gyro analysis we don't do — present but not measured.
    out.append(unavailable("rollingShutter", "Rolling shutter", "edge_skew", "visual", "Not measured"))
    return out
