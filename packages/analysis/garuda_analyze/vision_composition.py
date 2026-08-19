"""Composition / framing parameters derived from detected face boxes."""

from __future__ import annotations

import numpy as np

from .metrics import REGISTRY, Metric, unavailable
from .util import clamp


@REGISTRY.register("vision_composition", group="visual")
def _composition(ctx: dict) -> "list[Metric]":
    fd = ctx.get("frame_data") or {}
    boxes = fd.get("face_boxes") or []
    out: list[Metric] = []

    if boxes:
        cx = np.array([float(b.get("cx", 0.5)) for b in boxes])
        cy = np.array([float(b.get("cy", 0.5)) for b in boxes])
        area = np.array([float(b.get("w", 0.0)) * float(b.get("h", 0.0)) for b in boxes])
        ev = [{"t": float(boxes[0].get("t", 0.0))}]

        size_std = float(np.std(area))
        out.append(
            Metric("subjectSizeStability", "Subject size stability", round(clamp(100.0 - size_std * 400.0), 1),
                   "points", (0, 100), "face_area_std", confidence=0.5, group="visual", evidence=ev)
        )
        mean_cx = float(np.mean(cx))
        lookroom = float(min(mean_cx, 1.0 - mean_cx) * 2.0)
        out.append(
            Metric("lookRoom", "Look room / centering", round(clamp(lookroom * 100.0), 1), "%", (0, 100),
                   "face_center_x", confidence=0.5, group="visual", evidence=ev)
        )
        mean_cy = float(np.mean(cy))
        headroom_dev = abs(mean_cy - 0.4)
        out.append(
            Metric("headroom", "Headroom", round(clamp(100.0 - headroom_dev * 250.0), 1), "points", (0, 100),
                   "face_center_y", confidence=0.5, group="visual", evidence=ev,
                   severity=("medium" if headroom_dev > 0.2 else "low"),
                   recommendation=("Reframe so eyes sit on the upper third" if headroom_dev > 0.2 else None))
        )
    else:
        for mid, label in (
            ("subjectSizeStability", "Subject size stability"),
            ("lookRoom", "Look room / centering"),
            ("headroom", "Headroom"),
        ):
            out.append(unavailable(mid, label, "face_geometry", "visual", "No face data"))

    # Need edge/OCR analysis — present in the catalog but not measured yet.
    out.append(unavailable("horizonLevel", "Horizon level", "edge_hough", "visual", "Not measured"))
    out.append(unavailable("onScreenTextLegibility", "On-screen text legibility", "ocr", "visual", "Not measured"))
    return out
