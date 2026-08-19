from __future__ import annotations

from pathlib import Path

import numpy as np


def analyze_audio(wav_path: Path | None, duration: float) -> dict:
    empty = {
        "waveform": [],
        "energy": [],
        "energy_times": [],
        "rms": 0.0,
        "peak": 0.0,
        "clipping_ratio": 0.0,
        "dead_air_ratio": 1.0 if duration > 0 else 0.0,
        "loudness_consistency": 0.0,
        "clarity": 0.0,
        "music_speech_ratio": 0.5,
        "silence_gaps": [],
        "sample_rate": 16000,
    }
    if wav_path is None or not wav_path.exists():
        return empty

    try:
        import librosa
    except Exception:
        # Minimal WAV read via soundfile/wave fallback
        return _analyze_wave_fallback(wav_path, duration, empty)

    y, sr = librosa.load(str(wav_path), sr=16000, mono=True)
    if y.size == 0:
        return empty

    peak = float(np.max(np.abs(y)))
    rms = float(np.sqrt(np.mean(y ** 2)))
    clipping_ratio = float(np.mean(np.abs(y) > 0.98))

    hop = 512
    frame_rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    times = librosa.frames_to_time(np.arange(len(frame_rms)), sr=sr, hop_length=hop)

    # Waveform downsampled for UI
    target = 400
    if len(y) > target:
        chunks = np.array_split(y, target)
        waveform = [float(np.mean(np.abs(c))) for c in chunks]
    else:
        waveform = [float(abs(v)) for v in y.tolist()]

    silence_thresh = max(0.01, float(np.percentile(frame_rms, 20)) * 0.6)
    silent = frame_rms < silence_thresh
    dead_air_ratio = float(np.mean(silent)) if silent.size else 0.0

    silence_gaps = []
    in_gap = False
    gap_start = 0.0
    for i, is_silent in enumerate(silent):
        t = float(times[i]) if i < len(times) else 0.0
        if is_silent and not in_gap:
            in_gap = True
            gap_start = t
        elif not is_silent and in_gap:
            in_gap = False
            if t - gap_start >= 0.8:
                silence_gaps.append({"start": gap_start, "end": t})
    if in_gap and duration - gap_start >= 0.8:
        silence_gaps.append({"start": gap_start, "end": float(duration)})

    # Loudness consistency: inverse of coefficient of variation on non-silent frames
    active = frame_rms[~silent] if np.any(~silent) else frame_rms
    if active.size and float(np.mean(active)) > 1e-8:
        cov = float(np.std(active) / (np.mean(active) + 1e-8))
        loudness_consistency = float(max(0.0, min(100.0, 100.0 * (1.0 - min(cov, 1.5) / 1.5))))
    else:
        loudness_consistency = 0.0

    # Clarity proxy: high-band energy ratio via spectral centroid stability
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)[0]
    zcr = librosa.feature.zero_crossing_rate(y, hop_length=hop)[0]
    clarity = float(
        max(
            0.0,
            min(
                100.0,
                55.0
                + 25.0 * (1.0 - min(1.0, float(np.std(centroid) / (np.mean(centroid) + 1e-6))))
                + 20.0 * (1.0 - min(1.0, float(np.mean(zcr)) * 4.0)),
            ),
        )
    )

    # Crude music vs speech: high spectral flatness + low ZCR variation leans music
    flatness = librosa.feature.spectral_flatness(y=y, hop_length=hop)[0]
    music_score = float(np.clip(np.mean(flatness) * 2.5, 0.0, 1.0))
    music_speech_ratio = music_score

    noise_floor = float(np.percentile(frame_rms, 15)) if frame_rms.size else 0.0
    signal_level = float(np.percentile(frame_rms, 85)) if frame_rms.size else 0.0
    snr_proxy = float(
        max(0.0, min(100.0, 20.0 * np.log10((signal_level + 1e-8) / (noise_floor + 1e-8))))
    )

    return {
        "waveform": waveform,
        "energy": [float(v) for v in frame_rms.tolist()],
        "energy_times": [float(t) for t in times.tolist()],
        "rms": rms,
        "peak": peak,
        "clipping_ratio": clipping_ratio,
        "dead_air_ratio": dead_air_ratio,
        "loudness_consistency": loudness_consistency,
        "clarity": clarity,
        "music_speech_ratio": music_speech_ratio,
        "silence_gaps": silence_gaps,
        "sample_rate": sr,
        "snr_proxy": snr_proxy,
    }


def _analyze_wave_fallback(wav_path: Path, duration: float, empty: dict) -> dict:
    import wave

    try:
        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            n = wf.getnframes()
            raw = wf.readframes(n)
            width = wf.getsampwidth()
            channels = wf.getnchannels()
    except Exception:
        return empty

    if width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        return empty
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)

    target = 400
    if data.size > target:
        chunks = np.array_split(data, target)
        waveform = [float(np.mean(np.abs(c))) for c in chunks]
    else:
        waveform = [float(abs(v)) for v in data.tolist()]

    rms = float(np.sqrt(np.mean(data ** 2))) if data.size else 0.0
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    return {
        **empty,
        "waveform": waveform,
        "rms": rms,
        "peak": peak,
        "clipping_ratio": float(np.mean(np.abs(data) > 0.98)) if data.size else 0.0,
        "dead_air_ratio": float(np.mean(np.abs(data) < 0.01)) if data.size else 1.0,
        "loudness_consistency": 50.0,
        "clarity": 50.0,
        "sample_rate": sr,
        "duration_hint": duration,
    }
