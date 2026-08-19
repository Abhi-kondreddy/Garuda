from __future__ import annotations

from typing import Optional


def _merge_ranges(ranges: list[tuple[float, float]], gap: float = 0.35) -> list[tuple[float, float]]:
    if not ranges:
        return []
    ranges = sorted(ranges)
    merged = [ranges[0]]
    for start, end in ranges[1:]:
        prev_s, prev_e = merged[-1]
        if start <= prev_e + gap:
            merged[-1] = (prev_s, max(prev_e, end))
        else:
            merged.append((start, end))
    return merged


def middle_jump_segments(
    inn: float,
    out: float,
    report: Optional[dict],
    *,
    min_gap: float = 1.2,
    min_keep: float = 2.5,
    max_segments: int = 6,
    min_window: float = 18.0,
) -> list[tuple[float, float, list[str]]]:
    """
    Split a clip window by removing middle silence / dull stretches.
    Head/tail trims are handled separately in propose._best_in_out.
    """
    window = out - inn
    if window < min_window or not report:
        return [(inn, out, [])]

    cut_ranges: list[tuple[float, float]] = []
    audio = report.get("audio") or {}
    for g in audio.get("silenceGaps") or []:
        gs, ge = float(g.get("start") or 0), float(g.get("end") or 0)
        gap = ge - gs
        if gap < min_gap:
            continue
        if gs <= inn + 0.6 or ge >= out - 0.6:
            continue
        cut_ranges.append((max(gs, inn), min(ge, out)))

    companion = report.get("companion") or {}
    for c in companion.get("cutList") or []:
        action = c.get("action") or ""
        if action not in ("trim_silence", "trim_or_spice"):
            continue
        gs, ge = float(c.get("start") or 0), float(c.get("end") or 0)
        if ge - gs < min_gap:
            continue
        if gs <= inn + 0.6 or ge >= out - 0.6:
            continue
        cut_ranges.append((max(gs, inn), min(ge, out)))

    if not cut_ranges:
        return [(inn, out, [])]

    merged = _merge_ranges(cut_ranges)
    segments: list[tuple[float, float]] = []
    reasons: list[str] = []
    cursor = inn
    for cs, ce in merged:
        if cs - cursor >= min_keep:
            segments.append((round(cursor, 2), round(cs, 2)))
        reasons.append(f"Jump-cut {ce - cs:.1f}s dead air at {cs:.1f}s.")
        cursor = ce
    if out - cursor >= min_keep:
        segments.append((round(cursor, 2), round(out, 2)))

    if len(segments) <= 1 or len(segments) > max_segments:
        return [(inn, out, [])]

    out_segments: list[tuple[float, float, list[str]]] = []
    for i, (s, e) in enumerate(segments):
        seg_reasons = [reasons[i]] if i < len(reasons) else []
        if i == 0 and seg_reasons:
            seg_reasons = [f"Middle jump cuts — {len(segments)} segments."]
        out_segments.append((s, e, seg_reasons if i == 0 else []))
    return out_segments
