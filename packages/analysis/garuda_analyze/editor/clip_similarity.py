from __future__ import annotations

from typing import Any


def _palette_vector(report: dict | None) -> dict[str, float]:
    if not report:
        return {}
    palette = report.get("palette") or []
    return {str(p.get("hex") or ""): float(p.get("weight") or 0) for p in palette if p.get("hex")}


def _highlight_times(report: dict | None) -> list[float]:
    if not report:
        return []
    return [float(h.get("t") or 0) for h in (report.get("highlights") or [])[:4]]


def clip_similarity(report_a: dict | None, report_b: dict | None) -> float:
    """0 = different, 1 = near-duplicate (palette + duration + peak timing)."""
    if not report_a or not report_b:
        return 0.0
    pa = _palette_vector(report_a)
    pb = _palette_vector(report_b)
    keys = set(pa) | set(pb)
    palette_sim = 0.0
    if keys:
        palette_sim = sum(min(pa.get(k, 0), pb.get(k, 0)) for k in keys)

    da = float(report_a.get("durationSec") or 1)
    db = float(report_b.get("durationSec") or 1)
    dur_sim = min(da, db) / max(da, db, 1e-6)

    ha = _highlight_times(report_a)
    hb = _highlight_times(report_b)
    peak_sim = 0.0
    if ha and hb:
        # Compare first peak positions normalized by duration
        ra = ha[0] / max(da, 1)
        rb = hb[0] / max(db, 1)
        peak_sim = max(0.0, 1.0 - abs(ra - rb) * 2.0)

    return round(0.5 * palette_sim + 0.3 * dur_sim + 0.2 * peak_sim, 3)


def find_near_duplicates(
    reports: dict[str, dict],
    *,
    threshold: float = 0.72,
) -> list[dict[str, Any]]:
    ids = list(reports.keys())
    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            sim = clip_similarity(reports[a], reports[b])
            if sim >= threshold:
                pairs.append({"clipA": a, "clipB": b, "similarity": sim})
    return pairs
