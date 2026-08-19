"""Small shared helpers used across the scoring / coaching layers."""

from __future__ import annotations


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, v)))


def fmt_timecode(t: float) -> str:
    """Format seconds as ``m:ss`` (or ``h:mm:ss`` past an hour). Negative
    inputs clamp to 0 so a bad timestamp never renders as ``-1:59``."""
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
