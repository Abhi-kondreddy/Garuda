from __future__ import annotations

from pathlib import Path

import numpy as np

from . import config


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
        "lufs": None,
        "delivery": {},
        "advanced": {},
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

    # Bound memory on long clips: drop to a lower sample rate past an hour and
    # hard-cap the analyzed span so a multi-hour file can't exhaust RAM.
    load_sr = config.AUDIO_BASE_SR
    load_dur = None
    if duration and duration > config.AUDIO_DOWNSAMPLE_OVER_SEC:
        load_sr = config.AUDIO_DOWNSAMPLE_SR
    if duration and duration > config.AUDIO_MAX_ANALYSIS_SEC:
        load_dur = config.AUDIO_MAX_ANALYSIS_SEC
    try:
        y, sr = librosa.load(str(wav_path), sr=load_sr, mono=True, duration=load_dur)
    except Exception:
        # A decode failure on a valid-looking wav shouldn't abort the whole run.
        return _analyze_wave_fallback(wav_path, duration, empty)
    if y.size == 0:
        return empty

    try:
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
            t = float(times[i])
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

        # Delivery dynamics: loudness variation across active (non-silent) speech.
        energy_dynamics = (
            float(np.std(active) / (np.mean(active) + 1e-8)) if active.size else 0.0
        )
        # Pitch/intonation on a bounded window (yin is the cheap estimator).
        pitch_hz = None
        pitch_var_hz = None
        try:
            seg = y[: int(sr * 60)] if y.size > int(sr * 60) else y
            f0 = librosa.yin(seg, fmin=65, fmax=400, sr=sr)
            f0 = f0[np.isfinite(f0)]
            if f0.size:
                pitch_hz = float(np.median(f0))
                pitch_var_hz = float(np.std(f0))
        except Exception:
            pass
        delivery = {
            "energyDynamics": round(energy_dynamics, 3),
            "pitchHz": round(pitch_hz, 1) if pitch_hz is not None else None,
            "pitchVarHz": round(pitch_var_hz, 1) if pitch_var_hz is not None else None,
            "speechActivity": round(float(1.0 - dead_air_ratio), 3),
        }

        # Integrated loudness (EBU R128) — a real LUFS measure, not the RMS proxy.
        lufs = None
        try:
            import pyloudnorm as pyln

            if y.size >= int(sr * 0.4):  # meter needs >= ~400ms
                meter = pyln.Meter(sr)
                val = float(meter.integrated_loudness(y))
                lufs = round(val, 1) if np.isfinite(val) else None
        except Exception:
            lufs = None

        # Advanced spectral QC (true-peak, SNR, LRA, hum, sibilance, plosives).
        advanced: dict = {}
        try:
            advanced["truePeakDb"] = round(float(20.0 * np.log10(max(peak, 1e-6))), 2)
            fr = frame_rms[frame_rms > 0]
            if fr.size:
                noise = float(np.percentile(fr, 5))
                sig = float(np.percentile(fr, 60))
                advanced["snrDb"] = round(float(20.0 * np.log10(max(sig, 1e-6) / max(noise, 1e-7))), 1)
            win = max(1, int(0.4 * sr / hop))
            if frame_rms.size >= win * 2:
                blocks = np.array(
                    [frame_rms[i : i + win].mean() for i in range(0, frame_rms.size - win, win)]
                )
                bl = 20.0 * np.log10(np.clip(blocks, 1e-6, None))
                advanced["lraDb"] = round(float(np.percentile(bl, 95) - np.percentile(bl, 10)), 1)
            S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
            freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
            total = float(S.sum()) + 1e-9

            def _band(lo: float, hi: float) -> float:
                mask = (freqs >= lo) & (freqs < hi)
                return float(S[mask, :].sum()) / total

            advanced["humRatio"] = round(_band(45, 65) + _band(95, 125), 4)
            advanced["sibilanceRatio"] = round(_band(5000, 9000), 4)
            low = S[freqs < 150, :].sum(axis=0)
            if low.size > 2:
                thr = float(low.mean() + 3.0 * low.std())
                advanced["plosiveCount"] = int(np.sum(np.diff(low) > thr))
        except Exception:
            advanced = {}
    except Exception:
        # Feature extraction hiccup — fall back to the lightweight wave reader.
        return _analyze_wave_fallback(wav_path, duration, empty)

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
        "lufs": lufs,
        "delivery": delivery,
        "advanced": advanced,
        "silence_gaps": silence_gaps,
        "sample_rate": sr,
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
