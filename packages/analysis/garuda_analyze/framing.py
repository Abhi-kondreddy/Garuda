"""Framing checks + b-roll/talking-head timeline from detected face boxes."""

from __future__ import annotations


def _nearest_box(face_boxes: list[dict], t: float, window: float = 2.0) -> "dict | None":
    best = None
    best_d = window
    for b in face_boxes:
        d = abs(float(b.get("t", 0.0)) - t)
        if d <= best_d:
            best_d = d
            best = b
    return best


def build_broll_timeline(face_boxes: list[dict], duration: float, bin_sec: float = 5.0) -> list[dict]:
    """Coarse per-bin classification: talking-head (face present) vs b-roll."""
    if duration <= 0:
        return []
    n = max(1, int(duration // bin_sec) + 1)
    present = [False] * n
    for b in face_boxes:
        idx = int(float(b.get("t", 0.0)) // bin_sec)
        if 0 <= idx < n:
            present[idx] = True
    segments: list[dict] = []
    for i in range(n):
        kind = "talking_head" if present[i] else "broll"
        start = round(i * bin_sec, 2)
        end = round(min(duration, (i + 1) * bin_sec), 2)
        if segments and segments[-1]["kind"] == kind:
            segments[-1]["end"] = end
        else:
            segments.append({"start": start, "end": end, "kind": kind})
    return segments


def build_framing(face_boxes: list[dict], duration: float) -> dict:
    if not face_boxes:
        return {
            "hasFaceData": False,
            "meanCenter": None,
            "findings": [],
            "brollTimeline": build_broll_timeline([], duration),
        }
    cxs = [float(b.get("cx", 0.5)) for b in face_boxes]
    cys = [float(b.get("cy", 0.5)) for b in face_boxes]
    mean_cx = sum(cxs) / len(cxs)
    mean_cy = sum(cys) / len(cys)

    findings: list[dict] = []
    # Headroom: eyes/face should sit around the upper third (~0.3-0.5 center).
    if mean_cy > 0.62:
        findings.append(
            {
                "id": "low_framing",
                "severity": "medium",
                "title": "Subject sits low in frame",
                "detail": f"Average face center at {mean_cy*100:.0f}% height.",
                "fix": "Raise the camera or reframe so eyes land on the upper third.",
                "t": 0.0,
            }
        )
    elif mean_cy < 0.18:
        findings.append(
            {
                "id": "high_framing",
                "severity": "low",
                "title": "Lots of headroom",
                "detail": f"Average face center at {mean_cy*100:.0f}% height.",
                "fix": "Tighten the frame; reduce empty space above the head.",
                "t": 0.0,
            }
        )
    # Rule of thirds / centering.
    off_center = abs(mean_cx - 0.5)
    near_third = min(abs(mean_cx - 1 / 3), abs(mean_cx - 2 / 3)) < 0.08
    if off_center > 0.28 and not near_third:
        findings.append(
            {
                "id": "off_balance",
                "severity": "low",
                "title": "Subject drifts to one side",
                "detail": f"Average horizontal position {mean_cx*100:.0f}%.",
                "fix": "Center the subject or place them cleanly on a rule-of-thirds line.",
                "t": 0.0,
            }
        )

    return {
        "hasFaceData": True,
        "meanCenter": {"cx": round(mean_cx, 3), "cy": round(mean_cy, 3)},
        "ruleOfThirds": bool(near_third),
        "findings": findings,
        "brollTimeline": build_broll_timeline(face_boxes, duration),
    }
