from __future__ import annotations

from typing import Any

import numpy as np


def _fmt(t: float) -> str:
    m = int(t // 60)
    s = int(t % 60)
    return f"{m}:{s:02d}"


def _first_speech(transcript: list[dict]) -> float | None:
    if not transcript:
        return None
    return min(float(seg["start"]) for seg in transcript)


def _cuts_per_min(cuts: list[float], start: float, end: float) -> float:
    if end <= start:
        return 0.0
    n = sum(1 for c in cuts if start <= c < end)
    minutes = max((end - start) / 60.0, 1e-6)
    return round(n / minutes, 2)


def build_pacing_metrics(
    *,
    duration: float,
    timeline: list[dict],
    cuts: list[float],
    transcript: list[dict],
    on_cam: float,
) -> dict[str, Any]:
    """Hook + pacing metrics for reports and editor proposals."""
    duration = max(float(duration or 0), 0.1)
    speech_at = _first_speech(transcript)

    first_value_at: float | None = None
    for p in timeline:
        t = float(p.get("t") or 0)
        if t > min(90.0, duration):
            break
        interest = float(p.get("interestingness") or 0)
        motion = float(p.get("motion") or 0)
        audio_e = float(p.get("audioEnergy") or 0)
        if interest >= 48 and (motion >= 38 or audio_e >= 45):
            first_value_at = t
            break

    first_30 = [p for p in timeline if float(p.get("t") or 0) <= 30.0]
    if first_30:
        low = sum(1 for p in first_30 if float(p.get("interestingness") or 0) < 35.0)
        early_retention_risk = round(100.0 * low / len(first_30), 1)
    else:
        early_retention_risk = 0.0

    first_15_cuts = [c for c in cuts if c <= 15.0]
    pattern_interrupts = len(first_15_cuts)

    first_sec = [p for p in timeline if float(p.get("t") or 0) <= 1.0]
    first_frame_punch = (
        round(float(np.mean([float(p.get("interestingness") or 0) for p in first_sec])), 1)
        if first_sec
        else 0.0
    )

    t1 = duration / 3.0
    t2 = 2.0 * duration / 3.0

    def _mean_interest(start: float, end: float) -> float:
        pts = [float(p.get("interestingness") or 0) for p in timeline if start <= float(p.get("t") or 0) < end]
        return float(np.mean(pts)) if pts else 0.0

    open_e = _mean_interest(0, t1)
    mid_e = _mean_interest(t1, t2)
    close_e = _mean_interest(t2, duration)
    if close_e > open_e + 8:
        energy_arc = "rising"
    elif open_e > close_e + 8:
        energy_arc = "falling"
    else:
        energy_arc = "flat"

    cut_rate_by_segment = [
        {"label": "Open third", "start": 0.0, "end": round(t1, 2), "cutsPerMin": _cuts_per_min(cuts, 0, t1)},
        {"label": "Middle third", "start": round(t1, 2), "end": round(t2, 2), "cutsPerMin": _cuts_per_min(cuts, t1, t2)},
        {"label": "Close third", "start": round(t2, 2), "end": round(duration, 2), "cutsPerMin": _cuts_per_min(cuts, t2, duration)},
    ]

    if speech_at is None:
        hook_pattern = "no_speech"
    elif speech_at > 5.0:
        hook_pattern = "slow_intro"
    elif first_value_at is not None and first_value_at > 6.0:
        hook_pattern = "slow_intro"
    elif pattern_interrupts >= 2 and (speech_at or 99) <= 3.0:
        hook_pattern = "strong_open"
    elif pattern_interrupts == 0 and (speech_at or 0) > 3.0:
        hook_pattern = "static_open"
    else:
        hook_pattern = "standard"

    notes: list[str] = []
    if first_value_at is not None and first_value_at > 4.0:
        notes.append(f"First strong moment at {_fmt(first_value_at)} — consider opening here.")
    if early_retention_risk >= 55:
        notes.append(f"{early_retention_risk:.0f}% of the first 30s is low-energy.")
    if energy_arc == "falling":
        notes.append("Energy fades toward the end — tighten the close or add a peak.")
    if pattern_interrupts == 0:
        notes.append("No cuts in the first 15s — add a visual punch for Shorts.")

    return {
        "timeToFirstValueSec": round(first_value_at, 2) if first_value_at is not None else None,
        "speechOnsetSec": round(speech_at, 2) if speech_at is not None else None,
        "earlyRetentionRisk": early_retention_risk,
        "patternInterrupts15s": pattern_interrupts,
        "firstFramePunch": first_frame_punch,
        "energyArc": energy_arc,
        "energyByThird": {
            "open": round(open_e, 1),
            "middle": round(mid_e, 1),
            "close": round(close_e, 1),
        },
        "cutRateBySegment": cut_rate_by_segment,
        "hookPattern": hook_pattern,
        "onCamPresence": round(on_cam, 3),
        "notes": notes[:6],
    }
