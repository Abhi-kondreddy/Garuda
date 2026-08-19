"""Retention-risk curve derived from the interestingness timeline.

This is a heuristic proxy (not a platform prediction): a lightly smoothed
interestingness series plus a per-point drop risk, and the timestamp of the
steepest predicted drop for the UI to jump to.
"""

from __future__ import annotations


def _smooth(values: list[float], window: int = 5) -> list[float]:
    if not values:
        return []
    n = len(values)
    half = max(0, window // 2)
    out: list[float] = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        chunk = values[lo:hi]
        out.append(sum(chunk) / len(chunk))
    return out


def build_retention_curve(timeline: list[dict]) -> dict:
    if not timeline:
        return {"points": [], "predictedRetention": None, "worstDropT": None}
    interest = [float(p.get("interestingness", 0.0)) for p in timeline]
    smooth = _smooth(interest)
    points = [
        {
            "t": round(float(timeline[i]["t"]), 2),
            "retention": round(smooth[i], 1),
            "dropRisk": round(max(0.0, 100.0 - smooth[i]), 1),
        }
        for i in range(len(timeline))
    ]
    # Steepest sustained drop (largest decrease between consecutive points).
    worst_t = None
    worst_delta = 0.0
    for i in range(1, len(smooth)):
        delta = smooth[i - 1] - smooth[i]
        if delta > worst_delta:
            worst_delta = delta
            worst_t = round(float(timeline[i]["t"]), 2)
    predicted = round(sum(smooth) / len(smooth), 1)
    return {"points": points, "predictedRetention": predicted, "worstDropT": worst_t}
