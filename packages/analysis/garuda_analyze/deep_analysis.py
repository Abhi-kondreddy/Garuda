from __future__ import annotations

import re
from typing import Any


def _fmt(t: float) -> str:
    m = int(max(0, t) // 60)
    s = int(max(0, t) % 60)
    return f"{m}:{s:02d}"


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, v)))


_VAGUE_OPENERS = re.compile(
    r"^(hey guys|hi guys|hello everyone|what's up|welcome back|so today|um+|uh+)\b",
    re.I,
)
_PROMISE_CUES = re.compile(
    r"\b(how to|why|secret|mistake|stop|never|always|you need|i'll show|watch|learn|fix|vs\.?|versus)\b",
    re.I,
)
_QUESTION = re.compile(r"\?")
_CTA_CUES = re.compile(
    r"\b(subscribe|like|comment|share|follow|next video|link in|check out|watch till|don't forget)\b",
    re.I,
)


def enrich_hook_content(transcript: list[dict], hook_doctor: dict) -> dict:
    """Hook content quality: promise/question vs vague opener."""
    early = [s for s in transcript if float(s.get("start", 0)) <= 12.0]
    first_text = " ".join((s.get("text") or "").strip() for s in early[:3]).strip()
    content = {
        "openingLine": first_text[:180] if first_text else None,
        "hasPromise": bool(first_text and _PROMISE_CUES.search(first_text)),
        "hasQuestion": bool(first_text and _QUESTION.search(first_text)),
        "isVague": bool(first_text and _VAGUE_OPENERS.search(first_text.strip())),
        "score": 50.0,
        "t": float(early[0]["start"]) if early else 0.0,
        "findings": [],
    }
    score = 55.0
    if not first_text:
        content["findings"].append(
            {
                "id": "no_open_line",
                "severity": "high",
                "title": "No usable opening line",
                "detail": "ASR found no early speech to judge hook content.",
                "fix": "Script a one-sentence promise before you hit record.",
                "t": 0.0,
                "expectedLift": {"hook": 12, "overall": 4},
            }
        )
        score = 25.0
    else:
        if content["isVague"]:
            content["findings"].append(
                {
                    "id": "vague_opener",
                    "severity": "high",
                    "title": "Vague opener detected",
                    "detail": f"Starts like: “{first_text[:80]}…”",
                    "fix": "Replace greetings with a promise, conflict, or question in line 1.",
                    "t": content["t"],
                    "expectedLift": {"hook": 15, "overall": 5},
                }
            )
            score -= 25
        if content["hasPromise"] or content["hasQuestion"]:
            content["findings"].append(
                {
                    "id": "promise_ok",
                    "severity": "low",
                    "title": "Opening has a clear hook cue",
                    "detail": "Detected promise/question language in the first lines.",
                    "fix": "Keep the payoff concrete; cut filler before the claim.",
                    "t": content["t"],
                    "expectedLift": {"hook": 0, "overall": 0},
                }
            )
            score += 20
        else:
            content["findings"].append(
                {
                    "id": "weak_promise",
                    "severity": "medium",
                    "title": "Opening lacks a clear promise",
                    "detail": "No strong how/why/mistake/stop cue in the first lines.",
                    "fix": "Lead with the outcome viewers get if they stay.",
                    "t": content["t"],
                    "expectedLift": {"hook": 10, "overall": 3},
                }
            )
            score -= 10
    content["score"] = _clamp(score)
    # merge into hook doctor findings (non-low)
    for f in content["findings"]:
        if f["severity"] != "low":
            hook_doctor.setdefault("findings", []).append(f)
    hook_doctor["content"] = content
    # stamp seek times on existing findings
    speech = hook_doctor.get("speechOnsetSec")
    for f in hook_doctor.get("findings", []):
        if "t" not in f or f["t"] is None:
            if f.get("id") in ("late_speech", "speech_ok", "no_speech"):
                f["t"] = float(speech or 0.0)
            elif f.get("id") in ("late_first_cut", "cuts_ok", "no_early_cut"):
                f["t"] = float(hook_doctor.get("firstCutSec") or 0.0)
            else:
                f["t"] = float(f.get("metric") or content["t"] or 0.0)
        if "expectedLift" not in f:
            sev = f.get("severity")
            f["expectedLift"] = (
                {"hook": 12, "overall": 4}
                if sev == "high"
                else {"hook": 6, "overall": 2}
                if sev == "medium"
                else {"hook": 0, "overall": 0}
            )
    return hook_doctor


def build_ending_cta(*, duration: float, timeline: list[dict], transcript: list[dict]) -> dict:
    window = 25.0 if duration >= 40 else max(8.0, duration * 0.35)
    start = max(0.0, duration - window)
    end_pts = [p for p in timeline if p["t"] >= start]
    energy = float(sum(p.get("interestingness", 0) for p in end_pts) / max(len(end_pts), 1)) if end_pts else 35.0
    end_text = " ".join(
        (s.get("text") or "").strip() for s in transcript if float(s.get("start", 0)) >= start
    )
    has_cta = bool(end_text and _CTA_CUES.search(end_text))
    score = _clamp(0.55 * energy + (35.0 if has_cta else 5.0) + (10.0 if end_text else 0.0))
    findings = []
    if energy < 35:
        findings.append(
            {
                "id": "weak_end_energy",
                "severity": "high",
                "title": "Ending energy drops",
                "detail": f"Last {_fmt(window)} averages interestingness {energy:.0f}.",
                "fix": "Cut trailing lulls; end on a punch line + CTA.",
                "t": start,
                "tEnd": duration,
                "expectedLift": {"overall": 5, "interestingness": 8},
            }
        )
    if not has_cta and duration >= 30:
        findings.append(
            {
                "id": "missing_cta",
                "severity": "medium",
                "title": "No clear CTA in the ending",
                "detail": "No subscribe/next-video/like language detected near the end.",
                "fix": "Add a 5–8s CTA with a specific next video tease.",
                "t": start,
                "expectedLift": {"overall": 3},
            }
        )
    verdict = "Strong close" if score >= 70 else "Ending needs work" if score >= 45 else "Weak ending"
    return {
        "score": round(score, 1),
        "verdict": verdict,
        "windowStart": round(start, 2),
        "energy": round(energy, 1),
        "hasCta": has_cta,
        "ctaExcerpt": end_text[:140] if end_text else None,
        "findings": findings,
        "t": round(start, 2),
    }


def build_section_energy(timeline: list[dict], duration: float) -> dict:
    if duration <= 0 or not timeline:
        return {"sections": [], "t": 0}
    bounds = [
        ("Intro", 0.0, min(duration, max(15.0, duration * 0.15))),
        ("Middle", min(duration, max(15.0, duration * 0.15)), min(duration, duration * 0.75)),
        ("Payoff", min(duration, duration * 0.75), duration),
    ]
    sections = []
    for name, a, b in bounds:
        pts = [p for p in timeline if a <= p["t"] < b] or [p for p in timeline if abs(p["t"] - a) < 2]
        avg = float(sum(p.get("interestingness", 0) for p in pts) / max(len(pts), 1)) if pts else 0.0
        peak = max((p for p in pts), key=lambda p: p.get("interestingness", 0), default=None)
        valley = min((p for p in pts), key=lambda p: p.get("interestingness", 0), default=None)
        sections.append(
            {
                "name": name,
                "start": round(a, 2),
                "end": round(b, 2),
                "avgInterestingness": round(avg, 1),
                "peakT": round(float(peak["t"]), 2) if peak else round(a, 2),
                "valleyT": round(float(valley["t"]), 2) if valley else round(a, 2),
                "t": round(a, 2),
                "note": (
                    "Strong open"
                    if name == "Intro" and avg >= 55
                    else "Sagging middle"
                    if name == "Middle" and avg < 40
                    else "Payoff lands"
                    if name == "Payoff" and avg >= 50
                    else "Needs a boost"
                    if avg < 40
                    else "Healthy"
                ),
            }
        )
    return {"sections": sections, "t": 0.0}


def build_pattern_interrupts(
    *,
    duration: float,
    cuts: list[float],
    timeline: list[dict],
    fmt: str,
) -> dict:
    target = (1.5, 3.5) if fmt == "shorts" else (8.0, 20.0)
    # Interrupts = scene cuts + energy spikes
    spikes = []
    prev = None
    for p in timeline:
        if prev is not None and p.get("interestingness", 0) - prev.get("interestingness", 0) >= 18:
            spikes.append(float(p["t"]))
        prev = p
    events = sorted(set([round(c, 2) for c in cuts] + [round(s, 2) for s in spikes]))
    gaps = []
    last = 0.0
    for e in events:
        if e - last > 0.4:
            gaps.append(e - last)
        last = e
    if duration - last > 0.4:
        gaps.append(duration - last)
    avg_gap = float(sum(gaps) / max(len(gaps), 1)) if gaps else duration
    ideal = (target[0] + target[1]) / 2
    score = _clamp(100 - abs(avg_gap - ideal) * (12 if fmt == "shorts" else 4))
    long_gaps = [{"start": round(events[i], 2) if i >= 0 else 0.0, "end": round(events[i + 1], 2), "gap": round(events[i + 1] - events[i], 2)} for i in range(len(events) - 1) if events[i + 1] - events[i] > target[1] * 1.4]
    # also gap from 0
    if events and events[0] > target[1] * 1.2:
        long_gaps.insert(0, {"start": 0.0, "end": events[0], "gap": round(events[0], 2)})
    findings = []
    if avg_gap > target[1]:
        t = long_gaps[0]["start"] if long_gaps else 0.0
        findings.append(
            {
                "id": "few_interrupts",
                "severity": "medium",
                "title": "Attention resets are too sparse",
                "detail": f"Avg {avg_gap:.1f}s between interrupts; target ~{target[0]:.0f}–{target[1]:.0f}s for {fmt}.",
                "fix": "Add a cut, zoom, overlay, or B-roll punch in the longest gap.",
                "t": t,
                "expectedLift": {"interestingness": 7, "overall": 3},
            }
        )
    return {
        "format": fmt,
        "score": round(score, 1),
        "avgGapSec": round(avg_gap, 2),
        "targetGapSec": list(target),
        "interruptCount": len(events),
        "longGaps": long_gaps[:8],
        "events": events[:40],
        "findings": findings,
        "t": long_gaps[0]["start"] if long_gaps else (events[0] if events else 0.0),
    }


def score_thumbnails(timeline: list[dict], highlights: list[dict], on_cam: float) -> list[dict]:
    """Rank frames with a designer-ish score: energy + brightness + not too dark + face bias."""
    cands = []
    for h in highlights:
        cands.append({"t": float(h["t"]), "base": float(h.get("score", 50)), "label": h.get("label") or "Peak"})
    ranked = sorted(timeline, key=lambda p: p.get("interestingness", 0), reverse=True)
    for p in ranked[:12]:
        if any(abs(p["t"] - c["t"]) < 2.0 for c in cands):
            continue
        cands.append({"t": float(p["t"]), "base": float(p.get("interestingness", 0)), "label": "Energy frame"})
        if len(cands) >= 10:
            break
    out = []
    for c in cands:
        # nearest timeline point for brightness
        near = min(timeline, key=lambda p: abs(p["t"] - c["t"])) if timeline else None
        bri = float(near.get("brightness", 50)) if near else 50.0
        contrast_proxy = float(near.get("motion", 20)) if near else 20.0
        face_bonus = 12.0 if on_cam > 0.35 else (5.0 if on_cam > 0.15 else 0.0)
        # Prefer mid-bright (not crushed shadows / blown highlights)
        bri_score = 100 - abs(bri - 55) * 1.6
        score = _clamp(0.45 * c["base"] + 0.3 * bri_score + 0.15 * min(100, contrast_proxy * 2) + face_bonus)
        tip = "Strong energy — add bold text on the right third."
        if bri < 28:
            tip = "Too dark for a thumbnail — pick a brighter frame or grade up."
            score = _clamp(score - 15)
        elif bri > 85:
            tip = "Very bright — ensure face/subject still pops with contrast."
            score = _clamp(score - 8)
        if on_cam < 0.15:
            tip += " Face presence is low overall — prefer a frame with a clear subject."
        out.append(
            {
                "t": round(c["t"], 2),
                "score": round(score, 1),
                "label": c["label"],
                "tip": tip,
                "brightness": round(bri, 1),
                "faceBias": round(on_cam, 3),
                "textSafeHint": "Keep title text on the right third; face left/center.",
            }
        )
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:6]


def build_talking_head_balance(*, on_cam: float, static_ratio: float, scene_cut_rate: float, duration: float) -> dict:
    # Proxy: high on_cam + high static = talking-head heavy; low on_cam = b-roll/scenic
    head = on_cam
    broll = _clamp(1.0 - on_cam * 0.7 - static_ratio * 0.3)
    score = _clamp(100 - abs(head - 0.45) * 80 - max(0, static_ratio - 0.5) * 40)
    findings = []
    t = max(0.0, duration * 0.35)
    if head > 0.75 and static_ratio > 0.55:
        findings.append(
            {
                "id": "too_much_acams",
                "severity": "medium",
                "title": "Talking-head heavy",
                "detail": f"On-cam ~{head*100:.0f}% with high static stretch.",
                "fix": "Cut to B-roll on explanations; keep A-cam for emotional beats.",
                "t": t,
                "expectedLift": {"interestingness": 6, "visualQuality": 5},
            }
        )
    elif head < 0.15 and duration > 20:
        findings.append(
            {
                "id": "no_face_bond",
                "severity": "medium",
                "title": "Very little on-camera presence",
                "detail": f"On-cam ~{head*100:.0f}%.",
                "fix": "Add face-to-camera moments for trust, especially in the hook and CTA.",
                "t": 2.0,
                "expectedLift": {"hook": 6, "overall": 2},
            }
        )
    return {
        "score": round(score, 1),
        "talkingHeadRatio": round(head, 3),
        "brollProxy": round(broll, 3),
        "staticRatio": round(static_ratio, 3),
        "cutsPerMin": round(scene_cut_rate, 2),
        "findings": findings,
        "t": t,
    }


def build_exposure_flicker_events(timeline: list[dict]) -> dict:
    events = []
    prev = None
    for p in timeline:
        if prev is not None:
            db = abs(p.get("brightness", 50) - prev.get("brightness", 50))
            if db >= 18:
                events.append(
                    {
                        "t": round(float(p["t"]), 2),
                        "delta": round(db, 1),
                        "severity": "high" if db >= 28 else "medium",
                        "reason": "Brightness jump between beats",
                        "fix": "Match exposure across cuts or add a transition.",
                    }
                )
        prev = p
    score = _clamp(100 - len(events) * 8)
    return {"score": round(score, 1), "events": events[:15], "t": events[0]["t"] if events else 0.0}


def build_codeswitch_quality(transcript: list[dict]) -> dict:
    from .asr import language_label

    issues = []
    prev = None
    tracked = {"te", "en", "hi", "ta", "kn", "ml", "bn", "gu", "pa", "ur", "mr"}
    for seg in transcript:
        lang = seg.get("language") or "other"
        if (
            prev
            and prev.get("language") in tracked
            and lang in tracked
            and lang != prev["language"]
        ):
            gap = float(seg["start"]) - float(prev["end"])
            text = f"{prev.get('text','')} | {seg.get('text','')}"
            if gap < 0.35:
                issues.append(
                    {
                        "t": round(float(seg["start"]), 2),
                        "from": prev["language"],
                        "to": lang,
                        "severity": "medium",
                        "title": "Tight code-switch",
                        "detail": (
                            f"{language_label(prev['language'])} → {language_label(lang)} · "
                            f"{text[:100]}"
                        ),
                        "fix": "Switch languages on section boundaries; repeat key terms once in both.",
                        "expectedLift": {"audioQuality": 4},
                    }
                )
        prev = seg
    score = _clamp(100 - len(issues) * 12)
    return {"score": round(score, 1), "issues": issues[:12], "t": issues[0]["t"] if issues else 0.0}


def build_music_under_vo(*, audio_data: dict, transcript: list[dict], clarity: float) -> dict:
    music = float(audio_data.get("music_speech_ratio") or 0.5)
    windows = []
    if music > 0.55 and transcript:
        for seg in transcript[:20]:
            # mark speech windows when music ratio high + clarity middling
            if clarity < 65:
                windows.append(
                    {
                        "t": round(float(seg["start"]), 2),
                        "end": round(float(seg["end"]), 2),
                        "severity": "medium",
                        "reason": "Speech under likely music bed",
                        "fix": "Duck music −6 to −12dB under VO.",
                    }
                )
    score = _clamp(100 - max(0, music - 0.4) * 80 - (10 if clarity < 55 else 0))
    return {
        "score": round(score, 1),
        "musicSpeechRatio": round(music, 3),
        "clarity": round(clarity, 1),
        "conflictWindows": windows[:10],
        "t": windows[0]["t"] if windows else 0.0,
    }


def build_pause_taxonomy(silence_gaps: list[dict], transcript: list[dict]) -> dict:
    """Classify pauses: think vs cuttable dead air."""
    items = []
    for g in silence_gaps:
        start, end = float(g["start"]), float(g["end"])
        dur = end - start
        if dur < 0.45:
            continue
        # Near speech end = possible think pause; long isolated = cut
        near_speech = any(abs(float(s["end"]) - start) < 0.6 or abs(float(s["start"]) - end) < 0.6 for s in transcript)
        if dur < 0.9 and near_speech:
            kind = "think"
            action = "Keep — natural breath/think pause."
            severity = "low"
        elif dur < 1.4 and near_speech:
            kind = "breath"
            action = "Optional tighten to ~0.4s."
            severity = "low"
        else:
            kind = "dead_air"
            action = "Hard-cut or cover with B-roll."
            severity = "high" if dur >= 2.0 else "medium"
        items.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(dur, 2),
                "kind": kind,
                "severity": severity,
                "action": action,
                "t": round(start, 2),
                "expectedLift": {"overall": 2, "audioQuality": 3} if kind == "dead_air" else {"overall": 0},
            }
        )
    cuttable = [i for i in items if i["kind"] == "dead_air"]
    return {
        "items": items[:25],
        "deadAirCount": len(cuttable),
        "thinkCount": len([i for i in items if i["kind"] == "think"]),
        "t": cuttable[0]["t"] if cuttable else (items[0]["t"] if items else 0.0),
    }


def filter_false_risks(
    risk_zones: list[dict],
    transcript: list[dict],
    timeline: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Downgrade calm storytelling with dense clear speech."""
    kept = []
    filtered = []
    for z in risk_zones:
        start, end = float(z["start"]), float(z["end"])
        speech = [
            s
            for s in transcript
            if float(s["end"]) >= start and float(s["start"]) <= end
        ]
        spoken = sum(max(0.0, float(s["end"]) - float(s["start"])) for s in speech)
        dens = spoken / max(0.01, end - start)
        pts = [p for p in timeline if start <= p["t"] <= end]
        avg_audio = float(sum(p.get("audioEnergy", 0) for p in pts) / max(len(pts), 1)) if pts else 0
        if dens >= 0.55 and avg_audio >= 35 and (end - start) < 12:
            filtered.append({**z, "filterReason": "Dense speech storytelling — not a true lull", "t": start})
            continue
        kept.append({**z, "t": start})
    return kept, filtered


def build_score_drivers(
    *,
    hook: float,
    interestingness: float,
    color: float,
    visual: float,
    audio: float,
    overall: float,
    hook_doctor: dict,
    dead_air: float,
    scene_cut_rate: float,
    on_cam: float,
) -> dict:
    return {
        "overall": round(overall, 1),
        "drivers": [
            {
                "scoreKey": "hook",
                "label": "Hook",
                "value": round(hook, 1),
                "weight": 0.22,
                "why": [
                    f"Speech onset {hook_doctor.get('speechOnsetSec')}",
                    f"First cut {hook_doctor.get('firstCutSec')}",
                    f"On-cam {on_cam*100:.0f}%",
                ],
                "t": float(hook_doctor.get("speechOnsetSec") or hook_doctor.get("content", {}).get("t") or 0.0),
            },
            {
                "scoreKey": "interestingness",
                "label": "Interestingness",
                "value": round(interestingness, 1),
                "weight": 0.28,
                "why": [f"Cuts/min {scene_cut_rate:.1f}", "Motion + audio energy + speech density fusion"],
                "t": 0.0,
            },
            {
                "scoreKey": "colorEvenness",
                "label": "Color",
                "value": round(color, 1),
                "weight": 0.15,
                "why": ["Hue/saturation stability across frames"],
                "t": 0.0,
            },
            {
                "scoreKey": "visualQuality",
                "label": "Visual",
                "value": round(visual, 1),
                "weight": 0.15,
                "why": ["Brightness/contrast consistency", f"On-cam {on_cam*100:.0f}%"],
                "t": 0.0,
            },
            {
                "scoreKey": "audioQuality",
                "label": "Audio",
                "value": round(audio, 1),
                "weight": 0.20,
                "why": [f"Dead air {dead_air*100:.0f}%", "Clarity + loudness consistency"],
                "t": 0.0,
            },
        ],
    }


def estimate_lifts(cut_list: list[dict], hook_doctor: dict, ending: dict, pauses: dict) -> list[dict]:
    actions = []
    for c in cut_list[:8]:
        dur = float(c["end"]) - float(c["start"])
        lift_i = min(12.0, 3.0 + dur * 0.8)
        actions.append(
            {
                "id": f"cut-{c['start']}",
                "title": f"Trim {_fmt(c['start'])}–{_fmt(c['end'])}",
                "detail": c.get("reason") or "Low-interest stretch",
                "t": float(c["start"]),
                "tEnd": float(c["end"]),
                "expectedLift": {
                    "interestingness": round(lift_i, 1),
                    "overall": round(lift_i * 0.35, 1),
                },
            }
        )
    for f in hook_doctor.get("findings", []):
        if f.get("severity") in ("high", "medium") and f.get("expectedLift"):
            actions.append(
                {
                    "id": f"hook-{f.get('id')}",
                    "title": f.get("title"),
                    "detail": f.get("fix"),
                    "t": float(f.get("t") or 0),
                    "expectedLift": f["expectedLift"],
                }
            )
    for f in ending.get("findings", []):
        actions.append(
            {
                "id": f"end-{f.get('id')}",
                "title": f.get("title"),
                "detail": f.get("fix"),
                "t": float(f.get("t") or 0),
                "expectedLift": f.get("expectedLift") or {"overall": 3},
            }
        )
    for p in pauses.get("items", [])[:5]:
        if p.get("kind") == "dead_air":
            actions.append(
                {
                    "id": f"pause-{p['start']}",
                    "title": f"Cut dead air {_fmt(p['start'])}",
                    "detail": p.get("action"),
                    "t": float(p["t"]),
                    "expectedLift": p.get("expectedLift") or {"overall": 2},
                }
            )
    return actions[:12]


def build_before_after(*, overall: float, interestingness: float, hook: float, actions: list[dict]) -> dict:
    # Cap optimistic simulation
    d_overall = sum(float((a.get("expectedLift") or {}).get("overall", 0)) for a in actions[:6])
    d_interest = sum(float((a.get("expectedLift") or {}).get("interestingness", 0)) for a in actions[:6])
    d_hook = sum(float((a.get("expectedLift") or {}).get("hook", 0)) for a in actions[:6])
    d_overall = min(18.0, d_overall * 0.65)
    d_interest = min(22.0, d_interest * 0.65)
    d_hook = min(20.0, d_hook * 0.7)
    return {
        "current": {
            "overall": round(overall, 1),
            "interestingness": round(interestingness, 1),
            "hook": round(hook, 1),
        },
        "simulated": {
            "overall": round(_clamp(overall + d_overall), 1),
            "interestingness": round(_clamp(interestingness + d_interest), 1),
            "hook": round(_clamp(hook + d_hook), 1),
        },
        "delta": {
            "overall": round(d_overall, 1),
            "interestingness": round(d_interest, 1),
            "hook": round(d_hook, 1),
        },
        "assumption": "Heuristic preview if top edit actions are applied — re-analyze after editing for truth.",
        "actionsUsed": len(actions[:6]),
        "t": float(actions[0]["t"]) if actions else 0.0,
    }


def build_deep_analysis(
    *,
    duration: float,
    timeline: list[dict],
    cuts: list[float],
    transcript: list[dict],
    highlights: list[dict],
    on_cam: float,
    static_ratio: float,
    scene_cut_rate: float,
    risk_zones: list[dict],
    silence_gaps: list[dict],
    audio_data: dict,
    clarity: float,
    dead_air: float,
    hook_score: float,
    avg_interest: float,
    color_evenness: float,
    visual_quality: float,
    audio_quality: float,
    overall: float,
    hook_doctor: dict,
    cut_list: list[dict],
    fmt: str,
) -> dict[str, Any]:
    hook_doctor = enrich_hook_content(transcript, hook_doctor)
    ending = build_ending_cta(duration=duration, timeline=timeline, transcript=transcript)
    sections = build_section_energy(timeline, duration)
    interrupts = build_pattern_interrupts(duration=duration, cuts=cuts, timeline=timeline, fmt=fmt)
    thumbs = score_thumbnails(timeline, highlights, on_cam)
    head_balance = build_talking_head_balance(
        on_cam=on_cam, static_ratio=static_ratio, scene_cut_rate=scene_cut_rate, duration=duration
    )
    flicker = build_exposure_flicker_events(timeline)
    codeswitch = build_codeswitch_quality(transcript)
    music = build_music_under_vo(audio_data=audio_data, transcript=transcript, clarity=clarity)
    pauses = build_pause_taxonomy(silence_gaps, transcript)
    kept_risks, filtered_risks = filter_false_risks(risk_zones, transcript, timeline)
    drivers = build_score_drivers(
        hook=hook_score,
        interestingness=avg_interest,
        color=color_evenness,
        visual=visual_quality,
        audio=audio_quality,
        overall=overall,
        hook_doctor=hook_doctor,
        dead_air=dead_air,
        scene_cut_rate=scene_cut_rate,
        on_cam=on_cam,
    )
    # enrich cut list lifts
    for c in cut_list:
        dur = float(c["end"]) - float(c["start"])
        c["t"] = float(c["start"])
        c["expectedLift"] = {
            "interestingness": round(min(12.0, 3.0 + dur * 0.8), 1),
            "overall": round(min(6.0, 1.2 + dur * 0.35), 1),
        }
        c["evidence"] = c.get("reason")
    actions = estimate_lifts(cut_list, hook_doctor, ending, pauses)
    simulation = build_before_after(
        overall=overall, interestingness=avg_interest, hook=hook_score, actions=actions
    )

    return {
        "hookDoctor": hook_doctor,
        "endingCta": ending,
        "sectionEnergy": sections,
        "patternInterrupts": interrupts,
        "thumbnailScores": thumbs,
        "talkingHeadBalance": head_balance,
        "exposureFlicker": flicker,
        "codeSwitch": codeswitch,
        "musicUnderVo": music,
        "pauseTaxonomy": pauses,
        "riskZonesFiltered": kept_risks,
        "falseRisksRemoved": filtered_risks,
        "scoreDrivers": drivers,
        "fixActions": actions,
        "beforeAfter": simulation,
        "cutList": cut_list,
    }
