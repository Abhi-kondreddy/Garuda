from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import config, parameters
from .coaching import build_companion
from .asr import language_label, refine_transcript_languages
from .framing import build_framing
from .fusion import build_drop_risk
from .metrics import REGISTRY, Metric
from .pacing_metrics import build_pacing_metrics
from .provenance import build_provenance
from .retention import build_retention_curve
from .seeding import seed_everything
from .text_analysis import build_chapters, build_keywords
from .util import clamp as _clamp


def _legacy_metrics(scores: dict, visual: dict, audio: dict) -> "dict[str, dict]":
    """Wrap the established scores/metrics as first-class metric contracts."""
    defs = [
        ("hook", "Hook strength", scores["hook"], "points", (0, 100), "heuristic_v1"),
        ("interestingness", "Interestingness", scores["interestingness"], "points", (0, 100), "heuristic_v1"),
        ("colorEvenness", "Color evenness", scores["colorEvenness"], "points", (0, 100), "hsv_stability"),
        ("visualQuality", "Visual quality", scores["visualQuality"], "points", (0, 100), "consistency_fusion"),
        ("audioQuality", "Audio quality", scores["audioQuality"], "points", (0, 100), "loudness_clarity_fusion"),
        ("overall", "Overall", scores["overall"], "points", (0, 100), "weighted_fusion"),
        ("onCamPresence", "On-cam presence", visual["onCamPresence"] * 100.0, "%", (0, 100), "face_detection"),
        ("sceneCutRate", "Scene cuts", visual["sceneCutRate"], "cuts/min", (0, 120), "scene_detect"),
        ("deadAirRatio", "Dead air", audio["deadAirRatio"] * 100.0, "%", (0, 100), "rms_silence"),
    ]
    out: dict[str, dict] = {}
    for mid, label, value, unit, rng, method in defs:
        out[mid] = Metric(
            id=mid, label=label, value=round(float(value), 2), unit=unit,
            range=rng, method=method, version=config.SCORING_VERSION, group="core",
        ).to_dict()
    lufs = audio.get("lufs")
    out["lufs"] = Metric(
        id="lufs", label="Integrated loudness", value=lufs, unit="LUFS", range=(-60, 0),
        method="ebu_r128", confidence=1.0 if lufs is not None else 0.0, group="audio",
        recommendation=(None if lufs is None else f"Target {config.LUFS_TARGETS['youtube']} LUFS"),
    ).to_dict()
    return out


def _safe_std(arr: list[float] | np.ndarray) -> float:
    if len(arr) < 2:
        return 0.0
    return float(np.std(arr))


def _energy_series(audio_data: dict, T: np.ndarray) -> np.ndarray:
    """Vectorized nearest-neighbour audio energy (0..100) for every bin time.

    Replaces the old per-bin ``argmin`` over all RMS frames (O(bins x frames)
    with a per-call ``max``) — this precomputes the max once and uses
    ``searchsorted``, which is O(bins log frames)."""
    et = np.asarray(audio_data.get("energy_times") or [], dtype=float)
    en = np.asarray(audio_data.get("energy") or [], dtype=float)
    if et.size == 0 or en.size == 0 or T.size == 0:
        return np.zeros_like(T)
    # Never let garbage audio (NaN/Inf) poison the timeline.
    et = np.nan_to_num(et, nan=0.0, posinf=0.0, neginf=0.0)
    en = np.nan_to_num(en, nan=0.0, posinf=0.0, neginf=0.0)
    mx = float(en.max())
    if not np.isfinite(mx) or mx <= 0:
        mx = 1.0
    pos = np.clip(np.searchsorted(et, T), 0, et.size - 1)
    left = np.clip(pos - 1, 0, et.size - 1)
    choose_left = np.abs(et[left] - T) <= np.abs(et[pos] - T)
    idx = np.where(choose_left, left, pos)
    return 100.0 * (en[idx] / mx)


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def _speech_mask(transcript: list[dict], T: np.ndarray) -> np.ndarray:
    """Boolean mask: is each bin time covered by (padded) speech? O(segs+bins)."""
    if T.size == 0 or not transcript:
        return np.zeros(T.shape, dtype=bool)
    pad = config.SPEECH_PAD_SEC
    ivs: list[tuple[float, float]] = []
    for s in transcript:
        try:
            lo = float(s["start"]) - pad
            hi = float(s["end"]) + pad
        except (KeyError, TypeError, ValueError):
            continue
        if hi >= lo:
            ivs.append((lo, hi))
    if not ivs:
        return np.zeros(T.shape, dtype=bool)
    merged = _merge_intervals(ivs)
    los = np.array([m[0] for m in merged])
    his = np.array([m[1] for m in merged])
    idx = np.searchsorted(los, T, side="right") - 1
    mask = np.zeros(T.shape, dtype=bool)
    valid = idx >= 0
    mask[valid] = T[valid] <= his[idx[valid]]
    return mask


def _cut_mask(cuts: list[float], T: np.ndarray) -> np.ndarray:
    """Boolean mask: is each bin time within CUT_PROXIMITY_SEC of a scene cut?"""
    if T.size == 0 or not cuts:
        return np.zeros(T.shape, dtype=bool)
    cs = np.sort(np.asarray([float(c) for c in cuts], dtype=float))
    pos = np.searchsorted(cs, T)
    left = np.clip(pos - 1, 0, cs.size - 1)
    right = np.clip(pos, 0, cs.size - 1)
    mind = np.minimum(np.abs(T - cs[left]), np.abs(cs[right] - T))
    return mind < config.CUT_PROXIMITY_SEC


def _build_timeline(
    bins: list[dict], audio_data: dict, transcript: list[dict], cuts: list[float]
) -> list[dict]:
    if not bins:
        return []
    T = np.array([float(b["t"]) for b in bins], dtype=float)
    mot = np.array([float(b["motion"]) for b in bins], dtype=float)
    bri = np.array([float(b["brightness"]) for b in bins], dtype=float)
    mot_n = 100.0 * np.minimum(1.0, mot / config.MOTION_FULL_SCALE)
    audio_e = _energy_series(audio_data, T)
    speech = _speech_mask(transcript, T).astype(float) * config.SPEECH_PRESENT_SCORE
    cut_boost = _cut_mask(cuts, T).astype(float) * config.CUT_BOOST_SCORE
    w = config.INTEREST_WEIGHTS
    interest = np.clip(
        w["motion"] * mot_n + w["audio"] * audio_e + w["speech"] * speech + w["cut"] * cut_boost,
        0.0,
        100.0,
    )
    mot_c = np.clip(mot_n, 0.0, 100.0)
    audio_c = np.clip(audio_e, 0.0, 100.0)
    bri_c = np.clip((bri / 255.0) * 100.0, 0.0, 100.0)
    # Final guard: any residual non-finite value becomes 0 so the timeline is
    # always numeric (schema-valid) regardless of upstream garbage.
    interest = np.nan_to_num(interest, nan=0.0, posinf=100.0, neginf=0.0)
    mot_c = np.nan_to_num(mot_c, nan=0.0, posinf=100.0, neginf=0.0)
    audio_c = np.nan_to_num(audio_c, nan=0.0, posinf=100.0, neginf=0.0)
    bri_c = np.nan_to_num(bri_c, nan=0.0, posinf=100.0, neginf=0.0)
    return [
        {
            "t": float(T[i]),
            "interestingness": float(interest[i]),
            "motion": float(mot_c[i]),
            "audioEnergy": float(audio_c[i]),
            "brightness": float(bri_c[i]),
        }
        for i in range(len(bins))
    ]


def build_report(
    *,
    video_path: Path,
    meta: dict,
    frame_data: dict,
    audio_data: dict,
    transcript: list[dict],
) -> dict:
    seed = seed_everything()
    duration = float(meta["duration"] or frame_data.get("duration") or 0.0)
    fps = float(meta["fps"] or frame_data.get("fps") or 30.0)

    brightness = frame_data.get("brightness") or []
    contrast = frame_data.get("contrast") or []
    motion = frame_data.get("motion") or []
    hue = frame_data.get("hue_means") or []
    sat = frame_data.get("sat_means") or []
    cuts = frame_data.get("scene_cuts") or []
    bins = frame_data.get("timeline_bins") or []

    bri_std = _safe_std(brightness)
    con_std = _safe_std(contrast)
    brightness_consistency = _clamp(100.0 - bri_std * config.BRIGHTNESS_STD_PENALTY)
    contrast_consistency = _clamp(100.0 - con_std * config.CONTRAST_STD_PENALTY)
    hue_std = _safe_std(hue)
    sat_std = _safe_std(sat)
    color_evenness = _clamp(
        100.0 - hue_std * config.HUE_STD_PENALTY - sat_std * config.SAT_STD_PENALTY
    )
    exposure_flicker = _clamp(bri_std * config.EXPOSURE_FLICKER_GAIN)

    minutes = max(duration / 60.0, 1e-6)
    scene_cut_rate = len(cuts) / minutes

    motion_arr = np.array(motion, dtype=float) if motion else np.array([0.0])
    motion_thr = float(np.percentile(motion_arr, config.STATIC_MOTION_PERCENTILE))
    static_ratio = float(np.mean(motion_arr <= max(motion_thr, config.STATIC_MOTION_FLOOR)))

    on_cam = float(frame_data.get("on_cam_presence") or 0.0)
    face_avg_area = float(frame_data.get("face_avg_area_ratio") or 0.0)
    face_center_offset = float(frame_data.get("face_center_offset") or 0.5)
    face_center_x = float(frame_data.get("face_center_x") or 0.5)
    vertical_crop_safe = float(frame_data.get("vertical_crop_safe") or 50.0)

    # Color evenness is weighted separately in `overall`, so exclude it here to
    # avoid double-counting.
    vqw = config.VISUAL_QUALITY_WEIGHTS
    visual_quality = _clamp(
        vqw["brightness"] * brightness_consistency
        + vqw["contrast"] * contrast_consistency
        + vqw["static"] * (100.0 * (1.0 - min(1.0, static_ratio)))
    )

    timeline = _build_timeline(bins, audio_data, transcript, cuts)

    if not timeline and duration > 0:
        timeline = [
            {
                "t": 0.0,
                "interestingness": 20.0,
                "motion": 0.0,
                "audioEnergy": 0.0,
                "brightness": 50.0,
            }
        ]

    avg_interest = float(np.mean([p["interestingness"] for p in timeline])) if timeline else 0.0

    hook_window = [p for p in timeline if p["t"] <= 15.0]
    early = [p for p in hook_window if p["t"] <= 3.0] or hook_window
    hook_motion = float(np.mean([p["motion"] for p in early])) if early else 0.0
    hook_audio = float(np.mean([p["audioEnergy"] for p in early])) if early else 0.0
    early_cuts = len([c for c in cuts if c <= 15.0])
    speech_onset = 0.0
    if transcript:
        first = min(seg["start"] for seg in transcript)
        speech_onset = 100.0 if first <= 3.0 else (70.0 if first <= 8.0 else 30.0)
    hkw = config.HOOK_WEIGHTS
    hook = _clamp(
        hkw["motion"] * hook_motion
        + hkw["audio"] * hook_audio
        + hkw["speech_onset"] * speech_onset
        + hkw["early_cuts"] * min(100.0, early_cuts * 20.0)
        + hkw["on_cam"] * (100.0 * on_cam)
    )

    risk_zones = []
    if timeline:
        low_thr = config.RISK_LOW_THRESHOLD
        min_stretch = config.RISK_MIN_STRETCH_SEC
        high_stretch = config.RISK_HIGH_STRETCH_SEC
        start = None
        for p in timeline:
            if p["interestingness"] < low_thr:
                if start is None:
                    start = p["t"]
            else:
                if start is not None and p["t"] - start >= min_stretch:
                    risk_zones.append(
                        {
                            "start": start,
                            "end": p["t"],
                            "reason": "Low interestingness stretch",
                            "severity": "high" if p["t"] - start >= high_stretch else "medium",
                        }
                    )
                start = None
        if start is not None and duration - start >= min_stretch:
            risk_zones.append(
                {
                    "start": start,
                    "end": duration,
                    "reason": "Low interestingness stretch",
                    "severity": "high" if duration - start >= high_stretch else "medium",
                }
            )

    ranked = sorted(timeline, key=lambda p: p["interestingness"], reverse=True)
    highlights = []
    used: list[float] = []
    for p in ranked:
        if any(abs(p["t"] - u) < config.HIGHLIGHT_MIN_GAP_SEC for u in used):
            continue
        used.append(p["t"])
        label = "Peak moment"
        if p["t"] <= 15:
            label = "Hook peak"
        elif p["audioEnergy"] > 70:
            label = "Audio punch"
        highlights.append({"t": p["t"], "score": p["interestingness"], "label": label})
        if len(highlights) >= config.HIGHLIGHT_MAX:
            break

    transcript = refine_transcript_languages(transcript)

    te = en = hi = other = 0.0
    by_lang: dict[str, float] = {}
    for seg in transcript:
        dur = max(0.01, float(seg["end"]) - float(seg["start"]))
        code = seg.get("language") or "other"
        by_lang[code] = by_lang.get(code, 0.0) + dur
        if code == "te":
            te += dur
        elif code == "en":
            en += dur
        elif code == "hi":
            hi += dur
        else:
            other += dur
    spoken = sum(by_lang.values())
    if spoken <= 0:
        te_p = en_p = hi_p = other_p = 0.0
        language_breakdown: list[dict] = []
    else:
        te_p = 100.0 * te / spoken
        en_p = 100.0 * en / spoken
        hi_p = 100.0 * hi / spoken
        other_p = 100.0 * other / spoken
        language_breakdown = [
            {
                "code": code,
                "label": language_label(code),
                "percent": round(100.0 * dur / spoken, 1),
            }
            for code, dur in sorted(by_lang.items(), key=lambda kv: kv[1], reverse=True)
            if dur > 0
        ]

    words = 0
    speech_dur = 0.0
    for seg in transcript:
        words += len((seg.get("text") or "").split())
        speech_dur += max(0.0, float(seg["end"]) - float(seg["start"]))
    wpm = int(round(words / (speech_dur / 60.0))) if speech_dur > 1 else None

    wpm_variance: float | None = None
    if transcript and len(transcript) >= 2:
        seg_wpms: list[float] = []
        for seg in transcript:
            seg_words = len((seg.get("text") or "").split())
            seg_dur = max(0.01, float(seg["end"]) - float(seg["start"]))
            if seg_words >= 3:
                seg_wpms.append(seg_words / (seg_dur / 60.0))
        if len(seg_wpms) >= 2:
            wpm_variance = round(float(np.std(seg_wpms)), 1)

    snr_proxy = float(audio_data.get("snr_proxy") or 0.0)

    pacing = build_pacing_metrics(
        duration=duration,
        timeline=timeline,
        cuts=cuts,
        transcript=transcript,
        on_cam=on_cam,
    )

    clarity = float(audio_data.get("clarity") or 0.0)
    loudness = float(audio_data.get("loudness_consistency") or 0.0)
    dead = float(audio_data.get("dead_air_ratio") or 0.0)
    clip = float(audio_data.get("clipping_ratio") or 0.0)
    aqw = config.AUDIO_QUALITY_WEIGHTS
    audio_quality = _clamp(
        aqw["clarity"] * clarity
        + aqw["loudness"] * loudness
        + aqw["dead"] * (100.0 * (1.0 - min(1.0, dead)))
        + aqw["clip"] * (100.0 * (1.0 - min(1.0, clip * config.CLIP_PENALTY_SCALE)))
    )

    ow = config.OVERALL_WEIGHTS
    overall = _clamp(
        ow["hook"] * hook
        + ow["interest"] * avg_interest
        + ow["color"] * color_evenness
        + ow["visual"] * visual_quality
        + ow["audio"] * audio_quality
    )

    notes = [
        "Lightweight metrics scanned every frame; face presence used dense sampling (~3 fps).",
        "Scores are deterministic local heuristics — not platform retention predictions.",
        "Coach modules: Hook Doctor, titles/thumbnails, pacing, publish checklist, talking points, cut list, Shorts clips.",
    ]
    if not transcript:
        notes.append("No ASR transcript available. Enable faster-whisper for speech analysis.")
    mixed = [b for b in language_breakdown if b["percent"] > 5]
    if len(mixed) >= 2:
        mix_lbl = " / ".join(f"{b['label']} {b['percent']:.0f}%" for b in mixed[:3])
        notes.append(f"Multilingual speech detected — {mix_lbl}.")

    companion = build_companion(
        duration=duration,
        hook_score=hook,
        avg_interest=avg_interest,
        overall=overall,
        timeline=timeline,
        cuts=cuts,
        transcript=transcript,
        on_cam=on_cam,
        highlights=highlights,
        source_name=video_path.name,
        te_pct=te_p,
        en_pct=en_p,
        hi_pct=hi_p,
        scene_cut_rate=scene_cut_rate,
        dead_air=dead,
        wpm=wpm,
        silence_gaps=audio_data.get("silence_gaps") or [],
        static_ratio=static_ratio,
        loudness=loudness,
        clarity=clarity,
        clipping=clip,
        risk_zones=risk_zones,
        audio_quality=audio_quality,
        color_evenness=color_evenness,
        visual_quality=visual_quality,
        music_speech_ratio=float(audio_data.get("music_speech_ratio") or 0.5),
    )

    # Prefer filtered risk zones for the report timeline when available.
    # Use key-presence (not truthiness): an empty list means every zone was a
    # false positive and correctly removed — don't revert to the unfiltered set.
    report_risks = (
        companion["riskZonesFiltered"] if "riskZonesFiltered" in companion else risk_zones
    )

    chapters = build_chapters(transcript, cuts, duration)
    keywords = build_keywords(transcript)
    face_boxes = frame_data.get("face_boxes") or []
    retention_curve = build_retention_curve(timeline)
    framing = build_framing(face_boxes, duration)

    report = {
        "version": 3,
        "scoringVersion": config.SCORING_VERSION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sourcePath": str(video_path),
        "sourceName": video_path.name,
        "durationSec": duration,
        "fps": fps,
        "width": int(meta.get("width") or 0),
        "height": int(meta.get("height") or 0),
        "scores": {
            "hook": round(hook, 1),
            "interestingness": round(avg_interest, 1),
            "colorEvenness": round(color_evenness, 1),
            "visualQuality": round(visual_quality, 1),
            "audioQuality": round(audio_quality, 1),
            "overall": round(overall, 1),
        },
        "visual": {
            "colorEvenness": round(color_evenness, 1),
            "brightnessConsistency": round(brightness_consistency, 1),
            "contrastConsistency": round(contrast_consistency, 1),
            "exposureFlicker": round(exposure_flicker, 1),
            "sceneCutRate": round(scene_cut_rate, 2),
            "staticStretchRatio": round(static_ratio, 3),
            "onCamPresence": round(on_cam, 3),
            "faceAvgAreaRatio": round(face_avg_area, 4),
            "faceCenterOffset": round(face_center_offset, 4),
            "faceCenterX": round(face_center_x, 4),
            "verticalCropSafe": round(vertical_crop_safe, 1),
        },
        "audio": {
            "loudnessConsistency": round(loudness, 1),
            "clarity": round(clarity, 1),
            "deadAirRatio": round(dead, 3),
            "clippingRatio": round(clip, 4),
            "musicSpeechRatio": round(float(audio_data.get("music_speech_ratio") or 0.5), 3),
            "teluguPercent": round(te_p, 1),
            "englishPercent": round(en_p, 1),
            "hindiPercent": round(hi_p, 1),
            "otherPercent": round(other_p, 1),
            "languageBreakdown": language_breakdown,
            "estimatedWpm": wpm,
            "wpmVariance": wpm_variance,
            "snrProxy": round(snr_proxy, 1),
            "silenceGaps": audio_data.get("silence_gaps") or [],
            "lufs": audio_data.get("lufs"),
            "lufsTarget": config.LUFS_TARGETS.get("youtube"),
            "lufsGap": (
                round(config.LUFS_TARGETS.get("youtube", -14.0) - float(audio_data["lufs"]), 1)
                if audio_data.get("lufs") is not None
                else None
            ),
            "delivery": audio_data.get("delivery") or {},
        },
        "pacing": pacing,
        "timeline": timeline,
        "waveform": audio_data.get("waveform") or [],
        "transcript": transcript,
        "riskZones": report_risks,
        "highlights": highlights,
        "palette": frame_data.get("palette") or [],
        "chapters": chapters,
        "keywords": keywords,
        "faceBoxes": face_boxes,
        "retentionCurve": retention_curve,
        "framing": framing,
        "notes": notes,
        "companion": companion,
    }

    # Metric-contract layer: wrap core scores + run registered parameter plugins.
    context = {
        "meta": meta,
        "frame_data": frame_data,
        "audio_data": audio_data,
        "transcript": transcript,
        "timeline": timeline,
        "cuts": cuts,
        "duration": duration,
        "fps": fps,
        "report": report,
    }
    plugin_metrics, plugin_diags = REGISTRY.run(context)
    metrics = _legacy_metrics(report["scores"], report["visual"], report["audio"])
    metrics.update(plugin_metrics)
    report["metrics"] = metrics
    try:
        from .models import MODELS

        _mv = MODELS.versions()
    except Exception:
        _mv = {}
    report["provenance"] = build_provenance(seed=seed, model_versions=_mv)
    report["diagnostics"] = {
        "plugins": plugin_diags,
        "pluginModulesLoaded": list(parameters.loaded),
        "pluginModulesMissing": dict(parameters.missing),
        "faceBackend": frame_data.get("face_backend"),
    }

    # Multimodal per-timestamp drop-risk (visual + audio + speech fusion).
    filler_ev = [
        e.get("t")
        for e in (metrics.get("fillerRate", {}).get("evidence") or [])
        if isinstance(e, dict) and "t" in e
    ]
    report["dropRiskTimeline"] = build_drop_risk(
        timeline, audio_data.get("silence_gaps") or [], filler_ev
    )

    # Explainability: top actionable drivers across all metric groups.
    _order = {"high": 0, "medium": 1}
    drivers = []
    for mid, mc in metrics.items():
        if mc.get("severity") in ("high", "medium") and mc.get("recommendation"):
            ev = mc.get("evidence") or []
            drivers.append(
                {
                    "metricId": mid,
                    "label": mc.get("label"),
                    "value": mc.get("value"),
                    "severity": mc.get("severity"),
                    "recommendation": mc.get("recommendation"),
                    "t": ev[0]["t"] if ev and isinstance(ev[0], dict) and "t" in ev[0] else 0.0,
                }
            )
    drivers.sort(key=lambda d: _order.get(d["severity"], 9))
    report["topDrivers"] = drivers[:10]
    return report
