"""Multimodal per-timestamp drop-risk: fuse visual + audio + speech signals."""

from __future__ import annotations


def build_drop_risk(
    timeline: list[dict],
    silence_gaps: "list[dict] | None" = None,
    filler_times: "list[float] | None" = None,
) -> list[dict]:
    if not timeline:
        return []
    gaps = silence_gaps or []
    fillers = sorted(filler_times or [])
    out: list[dict] = []
    for p in timeline:
        t = float(p.get("t", 0.0))
        risk = max(0.0, 100.0 - float(p.get("interestingness", 0.0)))
        reasons: list[str] = []
        if risk > 65:
            reasons.append("low interest")
        if any(float(g.get("start", 0)) <= t <= float(g.get("end", 0)) for g in gaps):
            risk = min(100.0, risk + 15.0)
            reasons.append("dead air")
        if float(p.get("audioEnergy", 0.0)) < 20.0:
            risk = min(100.0, risk + 5.0)
            reasons.append("low audio")
        if any(abs(t - ft) < 0.75 for ft in fillers):
            risk = min(100.0, risk + 8.0)
            reasons.append("filler word")
        out.append({"t": round(t, 2), "risk": round(risk, 1), "reasons": reasons})
    return out
