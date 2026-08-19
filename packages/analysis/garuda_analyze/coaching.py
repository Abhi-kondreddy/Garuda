from __future__ import annotations

from typing import Any

from .deep_analysis import build_deep_analysis
from .util import fmt_timecode as _fmt


def _first_speech(transcript: list[dict]) -> float | None:
    if not transcript:
        return None
    return min(float(seg["start"]) for seg in transcript)


def _hook_face_onset(timeline: list[dict], on_cam: float) -> float | None:
    """Approximate first strong on-cam moment using early motion+brightness proxy.
    We don't store per-frame faces in timeline; use on_cam rate + early energy."""
    if on_cam <= 0.05:
        return None
    early = [p for p in timeline if p["t"] <= 15.0]
    if not early:
        return 0.0 if on_cam > 0.2 else None
    # Prefer first moment with elevated motion in first 15s as face-proxy when overall on-cam is decent
    for p in early:
        if p.get("motion", 0) >= 35 or p.get("interestingness", 0) >= 45:
            return float(p["t"])
    return float(early[0]["t"])


def build_hook_doctor(
    *,
    hook_score: float,
    timeline: list[dict],
    cuts: list[float],
    transcript: list[dict],
    on_cam: float,
) -> dict:
    findings: list[dict] = []
    speech_at = _first_speech(transcript)
    early_cuts = sorted(c for c in cuts if c <= 15.0)
    face_at = _hook_face_onset(timeline, on_cam)
    early = [p for p in timeline if p["t"] <= 3.0]
    audio_punch = float(sum(p.get("audioEnergy", 0) for p in early) / max(len(early), 1))

    if speech_at is None:
        findings.append(
            {
                "id": "no_speech",
                "severity": "high",
                "title": "No speech detected in the open",
                "detail": "Viewers decide in the first seconds. Lead with a spoken promise or question.",
                "fix": "Start talking within the first 2 seconds — state the payoff immediately.",
                "metric": None,
            }
        )
    elif speech_at > 3.0:
        findings.append(
            {
                "id": "late_speech",
                "severity": "high" if speech_at > 5 else "medium",
                "title": "Speech starts too late",
                "detail": f"First speech at {_fmt(speech_at)}. Strong hooks usually speak by 0:02.",
                "fix": f"Move your opening line earlier — trim or talk over the first {_fmt(speech_at)}.",
                "metric": round(speech_at, 2),
            }
        )
    else:
        findings.append(
            {
                "id": "speech_ok",
                "severity": "low",
                "title": "Speech onset is solid",
                "detail": f"First speech at {_fmt(speech_at)} — within the hook window.",
                "fix": "Keep leading with the promise; tighten wording if it rambles.",
                "metric": round(speech_at, 2),
            }
        )

    if not early_cuts:
        findings.append(
            {
                "id": "no_early_cut",
                "severity": "medium",
                "title": "No scene change in the first 15s",
                "detail": "Static opens lose scrollers. A cut, zoom, or B-roll punch helps.",
                "fix": "Add at least one visual change before 0:05 (cut, zoom, or graphic).",
                "metric": 0,
            }
        )
    elif early_cuts[0] > 5.0:
        findings.append(
            {
                "id": "late_first_cut",
                "severity": "medium",
                "title": "First cut arrives late",
                "detail": f"First detected cut at {_fmt(early_cuts[0])}.",
                "fix": "Bring the first visual change forward — ideally under 0:05.",
                "metric": round(early_cuts[0], 2),
            }
        )
    else:
        findings.append(
            {
                "id": "cuts_ok",
                "severity": "low",
                "title": "Early visual change present",
                "detail": f"First cut around {_fmt(early_cuts[0])} ({len(early_cuts)} in first 15s).",
                "fix": "Keep early cuts purposeful — don’t chop without a reason.",
                "metric": round(early_cuts[0], 2),
            }
        )

    if on_cam < 0.15:
        findings.append(
            {
                "id": "no_face",
                "severity": "medium",
                "title": "Low on-camera presence overall",
                "detail": "Faces boost trust and click-through, especially in the hook.",
                "fix": "Show your face (or a strong subject) in the first 3 seconds when possible.",
                "metric": round(on_cam * 100, 1),
            }
        )
    elif face_at is not None and face_at > 8.0:
        findings.append(
            {
                "id": "late_face",
                "severity": "medium",
                "title": "Subject energy arrives late",
                "detail": f"Strong early motion/interest around {_fmt(face_at)}.",
                "fix": "Open on face or high-energy frame sooner.",
                "metric": round(face_at, 2),
            }
        )

    if audio_punch < 25:
        findings.append(
            {
                "id": "weak_audio_punch",
                "severity": "medium",
                "title": "Weak audio energy in first 3s",
                "detail": "Quiet or flat opens feel unfinished next to competing videos.",
                "fix": "Raise opening volume slightly and start on a strong word or sound design hit.",
                "metric": round(audio_punch, 1),
            }
        )

    # Prioritize actionable high/medium first
    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 9))

    verdict = (
        "Hook is battle-ready"
        if hook_score >= 70
        else "Hook can convert better"
        if hook_score >= 45
        else "Hook needs a rewrite"
    )

    return {
        "score": round(hook_score, 1),
        "verdict": verdict,
        "speechOnsetSec": speech_at,
        "firstCutSec": early_cuts[0] if early_cuts else None,
        "findings": findings[:8],
    }


def build_title_thumbnail(
    *,
    transcript: list[dict],
    highlights: list[dict],
    timeline: list[dict],
    source_name: str,
    te_pct: float,
    en_pct: float,
    hi_pct: float = 0.0,
) -> dict:
    # Seed phrases from early + peak transcript
    early_text = " ".join(
        seg.get("text", "").strip() for seg in transcript if float(seg.get("start", 0)) <= 20.0
    ).strip()
    peak_text = ""
    if highlights and transcript:
        ht = float(highlights[0]["t"])
        near = [
            seg.get("text", "").strip()
            for seg in transcript
            if abs(float(seg["start"]) - ht) < 8 or abs(float(seg["end"]) - ht) < 8
        ]
        peak_text = " ".join(t for t in near if t)

    seed = early_text or peak_text or source_name.replace("_", " ").rsplit(".", 1)[0]
    words = [w for w in seed.replace("\n", " ").split() if len(w) > 2][:12]
    core = " ".join(words[:8]) if words else source_name.rsplit(".", 1)[0]

    bilingual = (te_pct > 8 and en_pct > 8) or (hi_pct > 8 and en_pct > 8)
    mix_name = (
        "Telugu + English"
        if te_pct > 8 and en_pct > 8
        else "Hindi + English"
        if hi_pct > 8 and en_pct > 8
        else "bilingual"
    )
    titles = [
        {
            "angle": "Curiosity gap",
            "title": f"I tried this — and it changed everything ({core[:48]}…)" if len(core) > 48 else f"I tried this — {core}",
            "why": "Promises a result without spoiling it.",
        },
        {
            "angle": "Direct promise",
            "title": f"How to {core[:60]}" if core else "How to level up your next video",
            "why": "Search-friendly and clear payoff.",
        },
        {
            "angle": "Contrarian",
            "title": f"Stop doing this: {core[:55]}" if core else "Stop editing like this",
            "why": "Pattern interrupt — high CTR for advice niches.",
        },
        {
            "angle": "List / number",
            "title": f"3 mistakes in the first 15 seconds ({core[:40]})" if core else "3 mistakes killing your hook",
            "why": "Scannable; works well with thumbnail numbers.",
        },
        {
            "angle": "Bilingual punch" if bilingual else "Story open",
            "title": (
                f"{core[:40]} | {mix_name} breakdown"
                if bilingual
                else f"The moment everything flipped — {core[:40]}"
            ),
            "why": "Matches your language mix" if bilingual else "Narrative hook for retention.",
        },
    ]

    # Thumbnail candidates: highlights + highest interestingness with decent brightness
    thumbs: list[dict] = []
    for h in highlights[:4]:
        thumbs.append(
            {
                "t": round(float(h["t"]), 2),
                "score": round(float(h["score"]), 1),
                "label": h.get("label") or "Peak frame",
                "tip": "Face + emotion + readable text safe zone on the right third.",
            }
        )
    ranked = sorted(timeline, key=lambda p: p.get("interestingness", 0), reverse=True)
    for p in ranked:
        if any(abs(p["t"] - t["t"]) < 2.5 for t in thumbs):
            continue
        if p.get("brightness", 50) < 18:
            continue
        thumbs.append(
            {
                "t": round(float(p["t"]), 2),
                "score": round(float(p["interestingness"]), 1),
                "label": "High-energy frame",
                "tip": "Bright, high-contrast frame — add bold text and avoid busy backgrounds.",
            }
        )
        if len(thumbs) >= 5:
            break

    return {"titles": titles[:5], "thumbnails": thumbs[:5], "seedPhrase": core[:120]}


def build_pacing_coach(
    *,
    duration: float,
    scene_cut_rate: float,
    dead_air: float,
    wpm: int | None,
    silence_gaps: list[dict],
    te_pct: float,
    en_pct: float,
    static_ratio: float,
    hi_pct: float = 0.0,
) -> dict:
    fmt = "shorts" if duration > 0 and duration <= 90 else "long_form"
    # Targets
    if fmt == "shorts":
        cut_lo, cut_hi = 12.0, 40.0
        wpm_lo, wpm_hi = 140, 200
        dead_max = 0.12
    else:
        cut_lo, cut_hi = 4.0, 18.0
        wpm_lo, wpm_hi = 120, 170
        dead_max = 0.18

    tips: list[dict] = []
    if scene_cut_rate < cut_lo:
        tips.append(
            {
                "id": "slow_cuts",
                "severity": "medium",
                "title": "Pacing feels slow",
                "detail": f"{scene_cut_rate:.1f} cuts/min vs target {cut_lo:.0f}–{cut_hi:.0f} for {fmt.replace('_', '-')}.",
                "fix": "Add B-roll, jump cuts on breaths, or zoom punches on key lines.",
            }
        )
    elif scene_cut_rate > cut_hi:
        tips.append(
            {
                "id": "fast_cuts",
                "severity": "medium",
                "title": "Pacing may feel frantic",
                "detail": f"{scene_cut_rate:.1f} cuts/min is above the {fmt.replace('_', '-')} comfort band.",
                "fix": "Hold on faces during emotional beats; cut less during explanations.",
            }
        )
    else:
        tips.append(
            {
                "id": "cuts_ok",
                "severity": "low",
                "title": "Cut rate is in a healthy band",
                "detail": f"{scene_cut_rate:.1f} cuts/min fits {fmt.replace('_', '-')} norms.",
                "fix": "Keep variation — denser in hooks, calmer in payoffs.",
            }
        )

    if dead_air > dead_max:
        tips.append(
            {
                "id": "dead_air",
                "severity": "high",
                "title": "Too much dead air",
                "detail": f"Silence/low-energy ratio ~{dead_air*100:.0f}% (aim under {dead_max*100:.0f}%).",
                "fix": "Tighten pauses over 0.8s; cover gaps with VO, music beds, or B-roll.",
            }
        )

    if wpm is not None:
        if wpm < wpm_lo:
            tips.append(
                {
                    "id": "slow_speech",
                    "severity": "medium",
                    "title": "Speech pace is slow",
                    "detail": f"~{wpm} WPM; {fmt.replace('_', '-')} often lands {wpm_lo}–{wpm_hi}.",
                    "fix": "Tighten scripts; remove filler; slightly raise delivery energy.",
                }
            )
        elif wpm > wpm_hi:
            tips.append(
                {
                    "id": "fast_speech",
                    "severity": "medium",
                    "title": "Speech pace is very fast",
                    "detail": f"~{wpm} WPM may hurt clarity for bilingual audiences.",
                    "fix": "Pause after key claims; slow 5–10% on complex Telugu/English switches.",
                }
            )
        else:
            tips.append(
                {
                    "id": "wpm_ok",
                    "severity": "low",
                    "title": "Speech pace looks healthy",
                    "detail": f"~{wpm} WPM within {wpm_lo}–{wpm_hi}.",
                    "fix": "Hold this pace; emphasize keywords with micro-pauses.",
                }
            )

    if te_pct > 8 and en_pct > 8:
        tips.append(
            {
                "id": "codeswitch",
                "severity": "medium",
                "title": "Telugu–English code-switching",
                "detail": f"Mix ≈ TE {te_pct:.0f}% / EN {en_pct:.0f}%.",
                "fix": "Switch languages on section boundaries, not mid-sentence; repeat key terms once in both.",
            }
        )
    elif hi_pct > 8 and en_pct > 8:
        tips.append(
            {
                "id": "codeswitch_hi",
                "severity": "medium",
                "title": "Hindi–English code-switching",
                "detail": f"Mix ≈ HI {hi_pct:.0f}% / EN {en_pct:.0f}%.",
                "fix": "Switch languages on section boundaries; repeat key terms once in both.",
            }
        )

    if static_ratio > 0.55 and fmt == "shorts":
        tips.append(
            {
                "id": "static_shorts",
                "severity": "high",
                "title": "Too static for Shorts",
                "detail": f"Static stretch ~{static_ratio*100:.0f}%.",
                "fix": "Add movement every 1–2s — zooms, overlays, or pattern interrupts.",
            }
        )

    long_gaps = [g for g in silence_gaps if float(g["end"]) - float(g["start"]) >= 1.5]

    # Attach a representative seek time so coach-feed items don't all jump to 0:00.
    first_gap_t = 0.0
    for g in silence_gaps:
        try:
            if float(g["end"]) - float(g["start"]) >= 0.8:
                first_gap_t = round(float(g["start"]), 2)
                break
        except (KeyError, TypeError, ValueError):
            continue
    for tip in tips:
        tip["t"] = first_gap_t if tip["id"] == "dead_air" else tip.get("t", 0.0)

    score = 100.0
    for t in tips:
        if t["severity"] == "high":
            score -= 18
        elif t["severity"] == "medium":
            score -= 10
    score = max(0.0, min(100.0, score))

    return {
        "format": fmt,
        "score": round(score, 1),
        "targets": {
            "cutsPerMin": [cut_lo, cut_hi],
            "wpm": [wpm_lo, wpm_hi],
            "maxDeadAir": dead_max,
        },
        "measured": {
            "cutsPerMin": round(scene_cut_rate, 2),
            "wpm": wpm,
            "deadAirRatio": round(dead_air, 3),
            "longSilenceGaps": len(long_gaps),
        },
        "tips": tips,
    }


def build_publish_checklist(
    *,
    duration: float,
    hook_score: float,
    speech_onset: float | None,
    loudness: float,
    clarity: float,
    clipping: float,
    dead_air: float,
    transcript: list[dict],
    te_pct: float,
    en_pct: float,
    risk_zones: list[dict],
    end_energy: float,
    hi_pct: float = 0.0,
) -> dict:
    items: list[dict] = []

    def add(id_: str, label: str, ok: bool, detail: str, fix: str) -> None:
        items.append(
            {
                "id": id_,
                "label": label,
                "status": "pass" if ok else "fail",
                "detail": detail,
                "fix": fix,
            }
        )

    add(
        "intro_length",
        "Intro / hook length",
        hook_score >= 50 and (speech_onset is None or speech_onset <= 3.5),
        f"Hook score {hook_score:.0f}" + (f", speech at {_fmt(speech_onset)}" if speech_onset is not None else ""),
        "Rewrite the first 15s so the promise lands by 0:02.",
    )
    add(
        "loudness",
        "Loudness consistency",
        loudness >= 55,
        f"Consistency score {loudness:.0f}/100",
        "Normalize dialogue; avoid whisper-to-shout jumps without intent.",
    )
    add(
        "clarity",
        "Speech clarity",
        clarity >= 50 or not transcript,
        f"Clarity proxy {clarity:.0f}/100",
        "Reduce room noise; mic closer; avoid heavy music under VO.",
    )
    add(
        "clipping",
        "No harsh clipping",
        clipping < 0.02,
        f"Clip ratio {clipping*100:.2f}%",
        "Lower peaks / use a limiter before export.",
    )
    add(
        "dead_air",
        "Dead air under control",
        dead_air <= (0.12 if duration <= 90 else 0.2),
        f"Dead air {dead_air*100:.0f}%",
        "Trim silence gaps over ~0.8s.",
    )
    has_captions_source = len(transcript) > 0
    add(
        "captions",
        "Captions ready (transcript source)",
        has_captions_source,
        "Transcript present" if has_captions_source else "No ASR transcript",
        "Re-run with Whisper enabled, then export SRT for YouTube.",
    )
    lang_bits = []
    if te_pct > 5:
        lang_bits.append(f"TE {te_pct:.0f}%")
    if hi_pct > 5:
        lang_bits.append(f"HI {hi_pct:.0f}%")
    if en_pct > 5:
        lang_bits.append(f"EN {en_pct:.0f}%")
    if lang_bits:
        add(
            "bilingual_captions",
            "Language caption plan",
            True,
            "Detected " + " / ".join(lang_bits),
            "Upload captions for each spoken language or burn key terms on-screen.",
        )
    # End screen / CTA window: last 20s should not be a risk zone dump
    end_risk = any(float(z["end"]) >= duration - 25 for z in risk_zones) if duration > 40 else False
    add(
        "end_screen",
        "End-screen / CTA window",
        duration < 40 or (not end_risk and end_energy >= 30),
        "Last 20–25s has energy for CTA" if duration >= 40 else "Short video — end-screen optional",
        "Keep the final 20s purposeful: recap + CTA + next video tease. Cut trailing lulls.",
    )
    add(
        "retention_risks",
        "No long mid-video lulls",
        len([z for z in risk_zones if z.get("severity") == "high"]) == 0,
        f"{len(risk_zones)} risk zone(s)",
        "Use the cut list to trim or spice low-interest stretches.",
    )

    passed = sum(1 for i in items if i["status"] == "pass")
    return {
        "passed": passed,
        "total": len(items),
        "ready": passed == len(items),
        "items": items,
    }


def build_talking_points(transcript: list[dict], duration: float) -> dict:
    thirds = [duration / 3.0, 2 * duration / 3.0, duration] if duration > 0 else [20.0, 40.0, 60.0]
    empty_structure = [
        {
            "act": "Promise",
            "window": f"0:00–{_fmt(thirds[0])}",
            "beats": [],
            "coach": "State who it’s for + the outcome. Avoid throat-clearing.",
        },
        {
            "act": "Proof",
            "window": f"{_fmt(thirds[0])}–{_fmt(thirds[1])}",
            "beats": [],
            "coach": "Show evidence, steps, or story turns. One idea per beat.",
        },
        {
            "act": "Payoff",
            "window": f"{_fmt(thirds[1])}–{_fmt(duration if duration > 0 else thirds[2])}",
            "beats": [],
            "coach": "Deliver the result, then CTA / next video. Don’t trail off.",
        },
    ]
    if not transcript:
        return {
            "structure": empty_structure,
            "outline": [],
            "summary": "No transcript — enable ASR to fill talking points from your spoken words.",
        }

    buckets = {"promise": [], "proof": [], "payoff": []}
    for seg in transcript:
        t = float(seg["start"])
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if t <= thirds[0]:
            buckets["promise"].append(text)
        elif t <= thirds[1]:
            buckets["proof"].append(text)
        else:
            buckets["payoff"].append(text)

    def pick(lines: list[str], n: int = 3) -> list[str]:
        out = []
        for line in lines:
            if line not in out:
                out.append(line)
            if len(out) >= n:
                break
        return out

    structure = [
        {
            "act": "Promise",
            "window": f"0:00–{_fmt(thirds[0])}",
            "beats": pick(buckets["promise"]),
            "coach": "State who it’s for + the outcome. Avoid throat-clearing.",
        },
        {
            "act": "Proof",
            "window": f"{_fmt(thirds[0])}–{_fmt(thirds[1])}",
            "beats": pick(buckets["proof"]),
            "coach": "Show evidence, steps, or story turns. One idea per beat.",
        },
        {
            "act": "Payoff",
            "window": f"{_fmt(thirds[1])}–{_fmt(duration)}",
            "beats": pick(buckets["payoff"]),
            "coach": "Deliver the result, then CTA / next video. Don’t trail off.",
        },
    ]

    outline = []
    for seg in transcript[:12]:
        outline.append(
            {
                "t": round(float(seg["start"]), 2),
                "text": (seg.get("text") or "").strip(),
                "language": seg.get("language") or "other",
                "role": "promise"
                if float(seg["start"]) <= thirds[0]
                else "proof"
                if float(seg["start"]) <= thirds[1]
                else "payoff",
            }
        )

    return {
        "structure": structure,
        "outline": outline,
        "summary": "Script arc mapped to Promise → Proof → Payoff from your spoken words.",
    }


def build_cut_list(risk_zones: list[dict], silence_gaps: list[dict], duration: float) -> list[dict]:
    cuts: list[dict] = []
    for z in risk_zones:
        start, end = float(z["start"]), float(z["end"])
        cuts.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "action": "trim_or_spice",
                "reason": z.get("reason") or "Low interestingness",
                "severity": z.get("severity") or "medium",
                "suggestion": "Trim, add a pattern interrupt, or overlay a tight VO line.",
            }
        )
    for g in silence_gaps:
        start, end = float(g["start"]), float(g["end"])
        if end - start < 1.2:
            continue
        # skip if already covered by risk zone
        if any(start >= c["start"] - 0.5 and end <= c["end"] + 0.5 for c in cuts):
            continue
        cuts.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "action": "trim_silence",
                "reason": "Long silence gap",
                "severity": "medium" if end - start < 3 else "high",
                "suggestion": "Hard-cut the pause or cover with B-roll + music.",
            }
        )
    cuts.sort(key=lambda c: (0 if c["severity"] == "high" else 1, c["start"]))
    return cuts[:20]


def build_shorts_clips(
    *,
    duration: float,
    highlights: list[dict],
    transcript: list[dict],
    timeline: list[dict],
) -> list[dict]:
    clips: list[dict] = []
    for h in highlights[:5]:
        center = float(h["t"])
        start = max(0.0, center - 8.0)
        end = min(duration, center + 12.0)
        if end - start < 12:
            end = min(duration, start + 25.0)
        # Prefer clip length 15–45s
        if end - start > 45:
            end = start + 45
        quote = ""
        for seg in transcript:
            if float(seg["start"]) >= start - 1 and float(seg["start"]) <= end:
                quote = (seg.get("text") or "").strip()
                break
        clips.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "score": round(float(h["score"]), 1),
                "label": h.get("label") or "Shorts candidate",
                "captionHook": quote[:90] if quote else "Add on-screen hook text in first 1s",
                "tip": "Export vertical 9:16, burn captions, open on the punch line.",
            }
        )
    if not clips and timeline:
        best = max(timeline, key=lambda p: p.get("interestingness", 0))
        start = max(0.0, float(best["t"]) - 5)
        end = min(duration, start + 30)
        clips.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "score": round(float(best["interestingness"]), 1),
                "label": "Best energy window",
                "captionHook": "Hook text here",
                "tip": "Export vertical 9:16 with captions.",
            }
        )
    return clips[:5]


def build_coach_feed(
    *,
    hook_doctor: dict,
    pacing: dict,
    checklist: dict,
    cut_list: list[dict],
    overall: float,
) -> list[dict]:
    feed: list[dict] = []
    for f in hook_doctor.get("findings", []):
        if f.get("severity") == "low":
            continue
        feed.append(
            {
                "source": "hook",
                "impact": "critical" if f["severity"] == "high" else "high",
                "title": f["title"],
                "action": f["fix"],
                "t": float(f.get("t") or 0),
                "expectedLift": f.get("expectedLift") or {},
            }
        )
    for t in pacing.get("tips", []):
        if t.get("severity") == "low":
            continue
        feed.append(
            {
                "source": "pacing",
                "impact": "critical" if t["severity"] == "high" else "high",
                "title": t["title"],
                "action": t["fix"],
                "t": float(t.get("t") or 0),
            }
        )
    for item in checklist.get("items", []):
        if item.get("status") == "fail":
            feed.append(
                {
                    "source": "publish",
                    "impact": "high",
                    "title": item["label"],
                    "action": item["fix"],
                    "t": float(item.get("t") or 0),
                }
            )
    if cut_list:
        top = cut_list[0]
        feed.append(
            {
                "source": "cuts",
                "impact": "high" if top.get("severity") == "high" else "medium",
                "title": f"Edit {_fmt(top['start'])}–{_fmt(top['end'])}",
                "action": top.get("suggestion") or "Trim this stretch.",
                "t": float(top.get("t") or top["start"]),
                "expectedLift": top.get("expectedLift") or {},
            }
        )
    if overall < 55:
        feed.insert(
            0,
            {
                "source": "overall",
                "impact": "critical",
                "title": "This draft isn’t publish-ready yet",
                "action": "Fix critical hook + pacing items first, then re-analyze.",
            },
        )

    rank = {"critical": 0, "high": 1, "medium": 2}
    feed.sort(key=lambda x: rank.get(x["impact"], 9))
    # de-dupe titles
    seen = set()
    out = []
    for item in feed:
        if item["title"] in seen:
            continue
        seen.add(item["title"])
        out.append(item)
    return out[:10]


def build_next_goals(
    *,
    hook_score: float,
    avg_interest: float,
    audio_quality: float,
    dead_air: float,
    checklist: dict,
) -> list[dict]:
    goals = []
    if hook_score < 70:
        goals.append(
            {
                "metric": "Hook",
                "current": round(hook_score, 1),
                "target": 75,
                "plan": "Reshoot/rewrite only the first 15 seconds with speech by 0:02.",
            }
        )
    if avg_interest < 60:
        goals.append(
            {
                "metric": "Interestingness",
                "current": round(avg_interest, 1),
                "target": 65,
                "plan": "Apply the cut list; add a mid-video pattern interrupt.",
            }
        )
    if audio_quality < 70 or dead_air > 0.15:
        goals.append(
            {
                "metric": "Audio polish",
                "current": round(audio_quality, 1),
                "target": 80,
                "plan": "Normalize loudness and trim silence before the next upload.",
            }
        )
    failed = [i for i in checklist.get("items", []) if i.get("status") == "fail"]
    if failed and len(goals) < 3:
        goals.append(
            {
                "metric": "Publish checklist",
                "current": checklist.get("passed", 0),
                "target": checklist.get("total", 0),
                "plan": f"Clear: {failed[0]['label']}.",
            }
        )
    if not goals:
        goals.append(
            {
                "metric": "Consistency",
                "current": 100,
                "target": 100,
                "plan": "Ship on schedule; A/B one title from Garuda’s suggestions.",
            }
        )
    return goals[:4]


def build_companion(
    *,
    duration: float,
    hook_score: float,
    avg_interest: float,
    overall: float,
    timeline: list[dict],
    cuts: list[float],
    transcript: list[dict],
    on_cam: float,
    highlights: list[dict],
    source_name: str,
    te_pct: float,
    en_pct: float,
    scene_cut_rate: float,
    dead_air: float,
    wpm: int | None,
    silence_gaps: list[dict],
    static_ratio: float,
    loudness: float,
    clarity: float,
    clipping: float,
    risk_zones: list[dict],
    audio_quality: float,
    color_evenness: float = 0.0,
    visual_quality: float = 0.0,
    music_speech_ratio: float = 0.5,
    hi_pct: float = 0.0,
) -> dict[str, Any]:
    end_pts = [p for p in timeline if p["t"] >= max(0.0, duration - 20)]
    end_energy = float(sum(p.get("interestingness", 0) for p in end_pts) / max(len(end_pts), 1)) if end_pts else 40.0

    hook_doctor = build_hook_doctor(
        hook_score=hook_score,
        timeline=timeline,
        cuts=cuts,
        transcript=transcript,
        on_cam=on_cam,
    )
    titles = build_title_thumbnail(
        transcript=transcript,
        highlights=highlights,
        timeline=timeline,
        source_name=source_name,
        te_pct=te_pct,
        en_pct=en_pct,
        hi_pct=hi_pct,
    )
    pacing = build_pacing_coach(
        duration=duration,
        scene_cut_rate=scene_cut_rate,
        dead_air=dead_air,
        wpm=wpm,
        silence_gaps=silence_gaps,
        te_pct=te_pct,
        en_pct=en_pct,
        hi_pct=hi_pct,
        static_ratio=static_ratio,
    )
    checklist = build_publish_checklist(
        duration=duration,
        hook_score=hook_score,
        speech_onset=hook_doctor.get("speechOnsetSec"),
        loudness=loudness,
        clarity=clarity,
        clipping=clipping,
        dead_air=dead_air,
        transcript=transcript,
        te_pct=te_pct,
        en_pct=en_pct,
        hi_pct=hi_pct,
        risk_zones=risk_zones,
        end_energy=end_energy,
    )
    talking = build_talking_points(transcript, duration)
    cut_list = build_cut_list(risk_zones, silence_gaps, duration)
    shorts = build_shorts_clips(
        duration=duration, highlights=highlights, transcript=transcript, timeline=timeline
    )
    for s in shorts:
        s["t"] = float(s.get("start", 0))

    deep = build_deep_analysis(
        duration=duration,
        timeline=timeline,
        cuts=cuts,
        transcript=transcript,
        highlights=highlights,
        on_cam=on_cam,
        static_ratio=static_ratio,
        scene_cut_rate=scene_cut_rate,
        risk_zones=risk_zones,
        silence_gaps=silence_gaps,
        audio_data={"music_speech_ratio": music_speech_ratio},
        clarity=clarity,
        dead_air=dead_air,
        hook_score=hook_score,
        avg_interest=avg_interest,
        color_evenness=color_evenness,
        visual_quality=visual_quality,
        audio_quality=audio_quality,
        overall=overall,
        hook_doctor=hook_doctor,
        cut_list=cut_list,
        fmt=pacing.get("format") or "long_form",
    )

    feed = build_coach_feed(
        hook_doctor=deep["hookDoctor"],
        pacing=pacing,
        checklist=checklist,
        cut_list=deep["cutList"],
        overall=overall,
    )
    for item in feed:
        item.setdefault("t", 0.0)
        item.setdefault("expectedLift", {})
    # attach seek times from hook findings when possible
    finding_ts = {f.get("title"): f.get("t") for f in deep["hookDoctor"].get("findings", [])}
    for item in feed:
        if item["title"] in finding_ts and finding_ts[item["title"]] is not None:
            item["t"] = finding_ts[item["title"]]
    for a in deep.get("fixActions", [])[:5]:
        feed.append(
            {
                "source": "lift",
                "impact": "high",
                "title": a["title"],
                "action": a.get("detail") or "",
                "t": a.get("t", 0),
                "expectedLift": a.get("expectedLift") or {},
            }
        )
    goals = build_next_goals(
        hook_score=hook_score,
        avg_interest=avg_interest,
        audio_quality=audio_quality,
        dead_air=dead_air,
        checklist=checklist,
    )
    titles["thumbnails"] = deep.get("thumbnailScores") or titles.get("thumbnails") or []

    return {
        "hookDoctor": deep["hookDoctor"],
        "titlesThumbnails": titles,
        "pacing": pacing,
        "publishChecklist": checklist,
        "talkingPoints": talking,
        "cutList": deep["cutList"],
        "shortsClips": shorts,
        "coachFeed": feed[:12],
        "nextGoals": goals,
        "endingCta": deep["endingCta"],
        "sectionEnergy": deep["sectionEnergy"],
        "patternInterrupts": deep["patternInterrupts"],
        "talkingHeadBalance": deep["talkingHeadBalance"],
        "exposureFlicker": deep["exposureFlicker"],
        "codeSwitch": deep["codeSwitch"],
        "musicUnderVo": deep["musicUnderVo"],
        "pauseTaxonomy": deep["pauseTaxonomy"],
        "scoreDrivers": deep["scoreDrivers"],
        "fixActions": deep["fixActions"],
        "beforeAfter": deep["beforeAfter"],
        "falseRisksRemoved": deep["falseRisksRemoved"],
        "riskZonesFiltered": deep["riskZonesFiltered"],
    }
