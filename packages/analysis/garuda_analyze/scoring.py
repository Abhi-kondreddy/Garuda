from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .coaching import build_companion
from .asr import language_label, refine_transcript_languages
from .pacing_metrics import build_pacing_metrics


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, v)))


def _safe_std(arr: list[float] | np.ndarray) -> float:
    if len(arr) < 2:
        return 0.0
    return float(np.std(arr))


def _interp_energy(audio_data: dict, t: float) -> float:
    times = audio_data.get("energy_times") or []
    energy = audio_data.get("energy") or []
    if not times or not energy:
        return 0.0
    idx = int(np.argmin([abs(x - t) for x in times]))
    e = float(energy[idx])
    mx = max(energy) or 1.0
    return 100.0 * (e / mx)


def build_report(
    *,
    video_path: Path,
    meta: dict,
    frame_data: dict,
    audio_data: dict,
    transcript: list[dict],
) -> dict:
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
    brightness_consistency = _clamp(100.0 - bri_std * 1.2)
    contrast_consistency = _clamp(100.0 - con_std * 1.5)
    hue_std = _safe_std(hue)
    sat_std = _safe_std(sat)
    color_evenness = _clamp(100.0 - hue_std * 1.8 - sat_std * 0.35)
    exposure_flicker = _clamp(bri_std * 1.4)

    minutes = max(duration / 60.0, 1e-6)
    scene_cut_rate = len(cuts) / minutes

    motion_arr = np.array(motion, dtype=float) if motion else np.array([0.0])
    motion_thr = float(np.percentile(motion_arr, 25)) if motion_arr.size else 0.0
    static_ratio = float(np.mean(motion_arr <= max(motion_thr, 1.5))) if motion_arr.size else 1.0

    on_cam = float(frame_data.get("on_cam_presence") or 0.0)
    face_avg_area = float(frame_data.get("face_avg_area_ratio") or 0.0)
    face_center_offset = float(frame_data.get("face_center_offset") or 0.5)
    face_center_x = float(frame_data.get("face_center_x") or 0.5)
    vertical_crop_safe = float(frame_data.get("vertical_crop_safe") or 50.0)

    visual_quality = _clamp(
        0.35 * brightness_consistency
        + 0.25 * contrast_consistency
        + 0.20 * color_evenness
        + 0.20 * (100.0 * (1.0 - min(1.0, static_ratio)))
    )

    timeline = []
    for b in bins:
        t = float(b["t"])
        mot = float(b["motion"])
        mot_n = 100.0 * min(1.0, mot / 25.0)
        audio_e = _interp_energy(audio_data, t)
        speech = 0.0
        for seg in transcript:
            if seg["start"] - 0.25 <= t <= seg["end"] + 0.25:
                speech = 80.0
                break
        cut_boost = 25.0 if any(abs(t - c) < 0.35 for c in cuts) else 0.0
        interestingness = _clamp(0.4 * mot_n + 0.3 * audio_e + 0.2 * speech + 0.1 * cut_boost)
        timeline.append(
            {
                "t": t,
                "interestingness": interestingness,
                "motion": _clamp(mot_n),
                "audioEnergy": _clamp(audio_e),
                "brightness": _clamp((float(b["brightness"]) / 255.0) * 100.0),
            }
        )

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
    hook = _clamp(
        0.3 * hook_motion
        + 0.25 * hook_audio
        + 0.2 * speech_onset
        + 0.15 * min(100.0, early_cuts * 20.0)
        + 0.1 * (100.0 * on_cam)
    )

    risk_zones = []
    if timeline:
        low_thr = 35.0
        start = None
        for p in timeline:
            if p["interestingness"] < low_thr:
                if start is None:
                    start = p["t"]
            else:
                if start is not None and p["t"] - start >= 4.0:
                    risk_zones.append(
                        {
                            "start": start,
                            "end": p["t"],
                            "reason": "Low interestingness stretch",
                            "severity": "high" if p["t"] - start >= 10 else "medium",
                        }
                    )
                start = None
        if start is not None and duration - start >= 4.0:
            risk_zones.append(
                {
                    "start": start,
                    "end": duration,
                    "reason": "Low interestingness stretch",
                    "severity": "high" if duration - start >= 10 else "medium",
                }
            )

    ranked = sorted(timeline, key=lambda p: p["interestingness"], reverse=True)
    highlights = []
    used: list[float] = []
    for p in ranked:
        if any(abs(p["t"] - u) < 3.0 for u in used):
            continue
        used.append(p["t"])
        label = "Peak moment"
        if p["t"] <= 15:
            label = "Hook peak"
        elif p["audioEnergy"] > 70:
            label = "Audio punch"
        highlights.append({"t": p["t"], "score": p["interestingness"], "label": label})
        if len(highlights) >= 6:
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
    audio_quality = _clamp(
        0.35 * clarity
        + 0.35 * loudness
        + 0.2 * (100.0 * (1.0 - min(1.0, dead)))
        + 0.1 * (100.0 * (1.0 - min(1.0, clip * 20.0)))
    )

    overall = _clamp(
        0.22 * hook
        + 0.28 * avg_interest
        + 0.15 * color_evenness
        + 0.15 * visual_quality
        + 0.20 * audio_quality
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

    # Prefer filtered risk zones for the report timeline when available
    report_risks = companion.get("riskZonesFiltered") or risk_zones

    return {
        "version": 3,
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
        },
        "pacing": pacing,
        "timeline": timeline,
        "waveform": audio_data.get("waveform") or [],
        "transcript": transcript,
        "riskZones": report_risks,
        "highlights": highlights,
        "palette": frame_data.get("palette") or [],
        "notes": notes,
        "companion": companion,
    }
