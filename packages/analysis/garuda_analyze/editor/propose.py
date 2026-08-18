from __future__ import annotations

import uuid
from typing import Any, Optional


def _clip_duration(clip: dict, report: Optional[dict] = None) -> float:
    if report and report.get("durationSec"):
        try:
            return max(0.5, float(report["durationSec"]))
        except (TypeError, ValueError):
            pass
    d = clip.get("durationSec")
    if d is None:
        return 30.0
    try:
        return max(0.5, float(d))
    except (TypeError, ValueError):
        return 30.0


def _scores(report: Optional[dict]) -> dict:
    if not report:
        return {"hook": 40.0, "interestingness": 40.0, "overall": 40.0, "audio": 40.0}
    s = report.get("scores") or {}
    return {
        "hook": float(s.get("hook") or 40),
        "interestingness": float(s.get("interestingness") or 40),
        "overall": float(s.get("overall") or 40),
        "audio": float(s.get("audioQuality") or 40),
    }


def _silence_gaps(report: Optional[dict]) -> list[dict]:
    if not report:
        return []
    audio = report.get("audio") or {}
    return list(audio.get("silenceGaps") or [])


def _best_in_out(clip: dict, report: Optional[dict], *, max_len: Optional[float] = None) -> tuple[float, float, list[str]]:
    """Pick in/out using silence + energy; prefer contentful middle/open."""
    dur = _clip_duration(clip, report)
    reasons: list[str] = []
    inn = 0.0
    out = dur

    gaps = _silence_gaps(report)
    # Trim leading silence > 0.8s
    for g in gaps:
        gs, ge = float(g.get("start") or 0), float(g.get("end") or 0)
        if gs <= 0.15 and ge - gs >= 0.8:
            inn = max(inn, ge - 0.15)
            reasons.append(f"Trimmed {ge:.1f}s leading silence.")
            break
    # Trim trailing silence
    for g in reversed(gaps):
        gs, ge = float(g.get("start") or 0), float(g.get("end") or 0)
        if ge >= dur - 0.2 and ge - gs >= 0.8:
            out = min(out, gs + 0.1)
            reasons.append("Trimmed trailing silence.")
            break

    # If still very long, prefer window around peak interestingness
    timeline = (report or {}).get("timeline") or []
    if max_len and (out - inn) > max_len and timeline:
        peak = max(timeline, key=lambda p: float(p.get("interestingness") or 0))
        center = float(peak.get("t") or (inn + out) / 2)
        half = max_len / 2
        inn = max(0.0, center - half)
        out = min(dur, inn + max_len)
        if out - inn < max_len:
            inn = max(0.0, out - max_len)
        reasons.append(
            f"Kept {out - inn:.0f}s around peak energy at {center:.1f}s "
            f"(interestingness {float(peak.get('interestingness') or 0):.0f})."
        )
    elif (out - inn) > 90 and timeline:
        # Soft trim for long takes: start at first decent energy after speech/motion
        ranked = sorted(timeline, key=lambda p: float(p.get("interestingness") or 0), reverse=True)
        if ranked:
            t0 = float(ranked[0].get("t") or 0)
            inn = max(inn, max(0.0, t0 - 3.0))
            out = min(dur, inn + min(75.0, dur - inn))
            reasons.append(f"Long take — opened near peak at {t0:.1f}s.")

    if out - inn < 0.5:
        inn, out = 0.0, min(dur, 5.0)
    return round(inn, 2), round(out, 2), reasons


def _sort_day_pool(clips: list[dict], section_hints: list[dict], reports: dict[str, dict]) -> list[dict]:
    by_id = {c["id"]: c for c in clips}
    ordered: list[dict] = []
    seen: set[str] = set()
    for hint in section_hints:
        for cid in hint.get("clipIds") or []:
            if cid in by_id and cid not in seen:
                ordered.append(by_id[cid])
                seen.add(cid)
    rest = [c for c in clips if c["id"] not in seen]

    def rank(c: dict) -> tuple:
        sc = _scores(reports.get(c["id"]))
        # Higher overall/hook first; then mtime as weak prior
        return (-sc["overall"], -sc["hook"], -sc["interestingness"], c.get("mtimeMs") or 0)

    if not section_hints:
        rest.sort(key=rank)
    else:
        rest.sort(key=lambda c: (c.get("mtimeMs") or 0, c.get("name") or ""))
    return ordered + rest


def _timeline_from_analyzed(
    clips: list[dict],
    reports: dict[str, dict],
    *,
    max_total: Optional[float] = None,
) -> tuple[list[dict], list[str]]:
    reasons: list[str] = []
    items: list[dict] = []
    total = 0.0
    for c in clips:
        report = reports.get(c["id"])
        sc = _scores(report)
        inn, out, trim_reasons = _best_in_out(c, report, max_len=None)
        use = out - inn
        if max_total is not None and total + use > max_total and items:
            remaining = max_total - total
            if remaining < 3:
                reasons.append(f"Stopped before {c.get('name')} — hit length target.")
                break
            out = inn + remaining
            use = remaining
            reasons.append(f"Cut {c.get('name')} to fit target length.")
        items.append(
            {
                "id": f"tc-{uuid.uuid4().hex[:8]}",
                "clipId": c["id"],
                "path": c["path"],
                "inSec": round(inn, 2),
                "outSec": round(out, 2),
                "enabled": True,
            }
        )
        total += use
        if report:
            reasons.append(
                f"{c.get('name')}: overall {sc['overall']:.0f}, hook {sc['hook']:.0f}, "
                f"interest {sc['interestingness']:.0f}."
            )
        else:
            reasons.append(
                f"{c.get('name')}: included by order ({use:.0f}s) — no analysis cache yet."
            )
        reasons.extend(trim_reasons[:1])
    if not any("overall" in r or "included by order" in r for r in reasons) and items:
        reasons.insert(0, f"Sequence uses {len(items)} clip(s) ({total:.0f}s).")
    return items, reasons[:12]


def _short_window_from_report(
    clip: dict, report: Optional[dict], short_max: float
) -> tuple[float, float, dict, list[str]]:
    dur = _clip_duration(clip, report)
    reasons: list[str] = []
    sc = _scores(report)

    # Prefer companion shortsClips / highlights
    companion = (report or {}).get("companion") or {}
    shorts = companion.get("shortsClips") or []
    highlights = (report or {}).get("highlights") or []

    if shorts:
        best = max(shorts, key=lambda s: float(s.get("score") or 0))
        inn = float(best.get("start") or 0)
        out = float(best.get("end") or min(dur, inn + short_max))
        out = min(dur, max(inn + 8, out), inn + short_max)
        reasons.append(f"Shorts window from coach ({best.get('label') or 'peak'}).")
        if best.get("captionHook"):
            reasons.append(f"Hook line: {str(best['captionHook'])[:70]}")
    elif highlights:
        h = max(highlights, key=lambda x: float(x.get("score") or 0))
        center = float(h.get("t") or dur / 2)
        half = min(short_max, 35) / 2
        inn = max(0.0, center - half * 0.4)
        out = min(dur, inn + min(short_max, 40))
        reasons.append(f"Opened on highlight “{h.get('label') or 'peak'}” at {center:.1f}s.")
    else:
        inn, out, trim_r = _best_in_out(clip, report, max_len=min(short_max, 45))
        reasons.extend(trim_r)

    window = max(0.5, out - inn)
    if report:
        why = [
            f"Hook score {sc['hook']:.0f}, interestingness {sc['interestingness']:.0f}.",
            f"Window {window:.0f}s from analyzed peak.",
        ]
        if sc["hook"] >= 70:
            why.append("Strong open — likely to hold the first 2s.")
        elif sc["hook"] < 45:
            why.append("Weak hook — consider a punchier open or pinned bin.")
    else:
        why = [
            f"Heuristic window {window:.0f}s (no deep analysis for this clip).",
            "Run Propose timelines for hook / energy scores.",
        ]
    if 12 <= window <= 45:
        why.append("Length in Shorts sweet spot.")
    score = min(
        98.0,
        0.4 * sc["hook"] + 0.4 * sc["interestingness"] + 0.2 * sc["overall"],
    )
    if not report:
        score = max(25.0, score - 20)
    if 12 <= window <= 45:
        score = min(98.0, score + 6)
    success = {"score": round(score, 1), "why": why[:4]}
    return round(inn, 2), round(out, 2), success, reasons


def _overlays_from_briefing(briefing: dict, kind: str) -> list[dict]:
    overlays: list[dict] = []
    title = (briefing.get("title") or "").strip()
    subtitle = (briefing.get("subtitle") or "").strip()
    cta = (briefing.get("cta") or "").strip()
    if title:
        end = 3.5 if kind == "short" else 4.5
        overlays.append({"type": "title", "start": 0, "end": end, "text": title})
    if subtitle and kind == "long":
        overlays.append({"type": "subtitle", "start": 0.4, "end": 5.0, "text": subtitle})
    if cta and kind == "long":
        overlays.append({"type": "cta", "start": -1, "end": -1, "text": cta})
    for cue in briefing.get("texts") or []:
        text = (cue.get("text") or "").strip()
        if not text:
            continue
        when = cue.get("when") or "custom"
        start = float(cue.get("timeSec") or (0 if when == "hook" else 8))
        style = cue.get("style") or "lower_third"
        typ = "title" if style == "title" else ("lower_third" if style == "lower_third" else "subtitle")
        overlays.append({"type": typ, "start": start, "end": start + 3.5, "text": text})
    return overlays


def propose_outputs(
    project: dict,
    *,
    reports: Optional[dict[str, dict]] = None,
) -> dict[str, Any]:
    """
    Propose long + Shorts using per-clip analysis reports when available.
    Falls back to duration heuristics if a clip has no report.
    """
    clips: list[dict] = list(project.get("clips") or [])
    if not clips:
        raise ValueError("Add at least one clip before proposing.")

    reports = reports or {}
    briefing = project.get("briefing") or {}
    fmt = briefing.get("format") or {}
    long_count = max(0, int(fmt.get("longCount") or 0))
    shorts_count = max(0, int(fmt.get("shortsCount") or 0))
    long_target = float(briefing.get("longTargetMin") or 10) * 60.0
    short_max = float(briefing.get("shortMaxSec") or 60)

    section_hints = project.get("sectionHints") or []
    short_bins = project.get("shortBins") or []
    ordered = _sort_day_pool(clips, section_hints, reports)
    by_id = {c["id"]: c for c in clips}

    analyzed_n = sum(1 for c in clips if c["id"] in reports)
    if analyzed_n:
        base_note = (
            f"Deep read: analyzed {analyzed_n}/{len(clips)} clips "
            "(visual + audio; speech when Whisper ran)."
        )
    else:
        base_note = (
            "Quick propose: no deep clip analysis — ordered by duration / file order heuristics. "
            "Run Propose timelines for scores, silence trims, and stronger reasons."
        )

    shorts_only_ids: set[str] = set()
    for bin_ in short_bins:
        if bin_.get("shortsOnly"):
            shorts_only_ids.update(bin_.get("clipIds") or [])

    long_pool = [c for c in ordered if c["id"] not in shorts_only_ids]
    outputs: list[dict] = []

    for li in range(long_count):
        tl, reasons = _timeline_from_analyzed(long_pool, reports, max_total=long_target)
        reasons.insert(0, base_note)
        if section_hints:
            reasons.insert(1, f"Honored {len(section_hints)} section hint(s) as order bias.")
        else:
            reasons.insert(1, "Ordered clips by overall / hook / interestingness scores.")
        if shorts_only_ids:
            reasons.append(f"Excluded {len(shorts_only_ids)} Shorts-only clip(s) from long form.")
        # Put strongest-hook clip first if no section hints
        if not section_hints and len(tl) > 1:
            def hook_of(tc: dict) -> float:
                return _scores(reports.get(tc["clipId"]))["hook"]

            best_i = max(range(len(tl)), key=lambda i: hook_of(tl[i]))
            if best_i > 0 and hook_of(tl[best_i]) >= hook_of(tl[0]) + 8:
                strong = tl.pop(best_i)
                tl.insert(0, strong)
                reasons.append(
                    f"Moved strongest hook ({by_id.get(strong['clipId'], {}).get('name')}) to open."
                )

        outputs.append(
            {
                "id": f"long-{li + 1}",
                "kind": "long",
                "aspect": "16:9",
                "title": (briefing.get("title") or project.get("name") or "Long video")
                + (f" ({li + 1})" if long_count > 1 else ""),
                "topic": None,
                "source": "proposed",
                "clipIds": [x["clipId"] for x in tl],
                "shortsOnly": False,
                "success": None,
                "proposalReasons": reasons[:14],
                "timeline": {
                    "clips": tl,
                    "overlays": _overlays_from_briefing(briefing, "long"),
                },
                "exportPath": None,
            }
        )

    used_for_shorts: set[str] = set()
    short_index = 0

    for bin_ in short_bins:
        if short_index >= shorts_count:
            break
        bin_clips = [by_id[cid] for cid in (bin_.get("clipIds") or []) if cid in by_id]
        if not bin_clips:
            continue
        # For pinned: use best window from first clip or concat short trims
        tl: list[dict] = []
        pin_reasons: list[str] = []
        remaining = short_max
        for c in bin_clips:
            if remaining < 3:
                break
            inn, out, success, r = _short_window_from_report(c, reports.get(c["id"]), remaining)
            use = out - inn
            if use > remaining:
                out = inn + remaining
                use = remaining
            tl.append(
                {
                    "id": f"tc-{uuid.uuid4().hex[:8]}",
                    "clipId": c["id"],
                    "path": c["path"],
                    "inSec": inn,
                    "outSec": out,
                    "enabled": True,
                }
            )
            remaining -= use
            pin_reasons.extend(r[:1])
        topic = bin_.get("topic") or "Pinned Short"
        sc_avg = sum(_scores(reports.get(c["id"]))["overall"] for c in bin_clips) / max(len(bin_clips), 1)
        success = {
            "score": round(min(95.0, 55 + sc_avg * 0.35), 1),
            "why": [
                f"Pinned by you: “{topic}”.",
                f"Built from {len(tl)} analyzed clip(s).",
            ],
        }
        if bin_.get("shortsOnly"):
            success["why"].append("Marked Shorts-only — kept out of long form.")
        outputs.append(
            {
                "id": f"short-{short_index + 1}",
                "kind": "short",
                "aspect": "9:16",
                "title": topic,
                "topic": topic,
                "source": "pinned",
                "clipIds": [c["id"] for c in bin_clips],
                "shortsOnly": bool(bin_.get("shortsOnly")),
                "success": success,
                "proposalReasons": [f"Using your bin “{topic}”.", *pin_reasons[:3]],
                "timeline": {
                    "clips": tl,
                    "overlays": _overlays_from_briefing(
                        {**briefing, "title": topic or briefing.get("title")},
                        "short",
                    ),
                },
                "exportPath": None,
            }
        )
        used_for_shorts.update(c["id"] for c in bin_clips)
        short_index += 1

    # Rank remaining by short fitness from analysis
    def short_fit(c: dict) -> float:
        report = reports.get(c["id"])
        sc = _scores(report)
        dur = _clip_duration(c, report)
        length_bonus = 12.0 if 12 <= dur <= 60 else (5.0 if dur > 60 else 0.0)
        return 0.45 * sc["hook"] + 0.45 * sc["interestingness"] + length_bonus

    candidates = sorted(
        [c for c in ordered if c["id"] not in used_for_shorts],
        key=short_fit,
        reverse=True,
    )

    for c in candidates:
        if short_index >= shorts_count:
            break
        inn, out, success, reasons = _short_window_from_report(c, reports.get(c["id"]), short_max)
        outputs.append(
            {
                "id": f"short-{short_index + 1}",
                "kind": "short",
                "aspect": "9:16",
                "title": c.get("name") or f"Short {short_index + 1}",
                "topic": None,
                "source": "proposed",
                "clipIds": [c["id"]],
                "shortsOnly": False,
                "success": success,
                "proposalReasons": reasons[:4],
                "timeline": {
                    "clips": [
                        {
                            "id": f"tc-{uuid.uuid4().hex[:8]}",
                            "clipId": c["id"],
                            "path": c["path"],
                            "inSec": inn,
                            "outSec": out,
                            "enabled": True,
                        }
                    ],
                    "overlays": _overlays_from_briefing(
                        {
                            **briefing,
                            "title": briefing.get("title") or "",
                        },
                        "short",
                    ),
                },
                "exportPath": None,
            }
        )
        used_for_shorts.add(c["id"])
        short_index += 1

    while short_index < shorts_count and ordered:
        fallback = max(ordered, key=short_fit)
        inn, out, success, reasons = _short_window_from_report(
            fallback, reports.get(fallback["id"]), short_max
        )
        success["score"] = max(20.0, success["score"] - 15)
        success["why"].append("Duplicate source — add more clips for unique Shorts.")
        outputs.append(
            {
                "id": f"short-{short_index + 1}",
                "kind": "short",
                "aspect": "9:16",
                "title": fallback.get("name") or f"Short {short_index + 1}",
                "topic": None,
                "source": "proposed",
                "clipIds": [fallback["id"]],
                "shortsOnly": False,
                "success": success,
                "proposalReasons": [
                    "Pool exhausted — reused best remaining clip.",
                    *reasons[:2],
                ],
                "timeline": {
                    "clips": [
                        {
                            "id": f"tc-{uuid.uuid4().hex[:8]}",
                            "clipId": fallback["id"],
                            "path": fallback["path"],
                            "inSec": inn,
                            "outSec": out,
                            "enabled": True,
                        }
                    ],
                    "overlays": [],
                },
                "exportPath": None,
            }
        )
        short_index += 1

    return {"outputs": outputs, "status": "proposed", "analyzedCount": analyzed_n}
