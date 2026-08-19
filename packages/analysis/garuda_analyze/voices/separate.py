from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional
import math
import threading
import time

import numpy as np
import soundfile as sf

Emit = Optional[Callable[[dict], None]]


def _emit(
    emit: Emit,
    percent: float,
    message: str,
    *,
    phase: str | None = None,
    phase_percent: float | None = None,
) -> None:
    if not emit:
        return
    payload: dict = {
        "type": "progress",
        "stage": "separate",
        "percent": int(max(0, min(99, percent))),
        "message": message,
    }
    if phase is not None:
        payload["phase"] = phase
    if phase_percent is not None:
        payload["phasePercent"] = float(max(0.0, min(100.0, phase_percent)))
    emit(payload)

def _mask_from_segments(n_samples: int, sr: int, segments: list[dict], fade: int = 256) -> np.ndarray:
    mask = np.zeros(n_samples, dtype=np.float32)
    for seg in segments:
        a = max(0, int(float(seg["start"]) * sr))
        b = min(n_samples, int(float(seg["end"]) * sr))
        if b <= a:
            continue
        mask[a:b] = 1.0
        f = min(fade, (b - a) // 4)
        if f > 1:
            ramp = np.linspace(0, 1, f, dtype=np.float32)
            mask[a : a + f] = np.maximum(mask[a : a + f], ramp)
            mask[b - f : b] = np.maximum(mask[b - f : b], ramp[::-1])
    return mask


def _frame_activity(mask: np.ndarray, hop: int, n_frames: int) -> np.ndarray:
    """Downsample sample mask to STFT frames."""
    n = len(mask)
    out = np.zeros(n_frames, dtype=np.float32)
    for i in range(n_frames):
        a = i * hop
        b = min(n, a + hop)
        if b > a:
            out[i] = float(np.mean(mask[a:b]))
    return out


def separate_stft_masked(
    y: np.ndarray,
    sr: int,
    clusters: list[dict],
    out_dir: Path,
    *,
    emit: Emit = None,
) -> tuple[list[dict], Path, str]:
    """
    STFT soft-Wiener separation guided by diarization activity.
    Better overlap handling than pure time-domain mute masks.
    """
    import librosa

    _emit(emit, 18, "Building STFT speaker masks…")
    n = len(y)
    S = len(clusters)
    n_fft = 1024
    hop = 256
    stft = librosa.stft(y.astype(np.float32), n_fft=n_fft, hop_length=hop)
    mag = np.abs(stft)
    phase = np.angle(stft)
    n_frames = mag.shape[1]

    acts = []
    for c in clusters:
        sample_mask = _mask_from_segments(n, sr, c["segments"], fade=max(256, hop * 2))
        acts.append(_frame_activity(sample_mask, hop, n_frames))
    act = np.stack(acts, axis=0)  # S x frames
    # Soften activity
    act = np.clip(act, 0.0, 1.0)
    # Prior: speakers present in a frame share magnitude via Wiener-like weights
    eps = 1e-6
    prior = act + 0.04  # small floor so silent speakers don't vanish abruptly
    # Boost exclusive regions
    active_count = np.maximum((act > 0.35).sum(axis=0), 1.0)
    for s in range(S):
        exclusive = (act[s] > 0.5) & (active_count <= 1.1)
        prior[s, exclusive] *= 2.2
    prior_sum = np.maximum(prior.sum(axis=0, keepdims=True), eps)
    weights = prior / prior_sum  # S x frames

    _emit(emit, 48, "Reconstructing speaker stems…")
    stems_meta: list[dict] = []
    stem_sum = np.zeros(n, dtype=np.float32)
    for i, c in enumerate(clusters):
        _emit(emit, 50 + (40 * i) / max(S, 1), f"Writing speaker stem {i + 1}…")
        # Broadcast weights across frequency
        w = weights[i][None, :]
        stem_mag = mag * w
        stem_stft = stem_mag * np.exp(1j * phase)
        stem = librosa.istft(stem_stft, hop_length=hop, length=n).astype(np.float32)
        # Gate residual hiss outside activity with soft sample mask
        sample_mask = _mask_from_segments(n, sr, c["segments"], fade=hop * 3)
        stem = stem * np.clip(sample_mask * 0.85 + 0.15, 0.0, 1.0)
        path = out_dir / f"speaker_{i + 1}.wav"
        sf.write(str(path), np.clip(stem, -1.0, 1.0), sr)
        stem_sum += stem
        dur = sum(max(0.0, float(s["end"]) - float(s["start"])) for s in c["segments"])
        stems_meta.append(
            {
                "id": f"spk_{i + 1}",
                "label": f"Speaker {i + 1}",
                "stemPath": str(path),
                "segments": c["segments"],
                "durationSec": round(dur, 2),
            }
        )

    residual = np.clip(y - stem_sum, -1.0, 1.0).astype(np.float32)
    residual_path = out_dir / "residual.wav"
    sf.write(str(residual_path), residual, sr)
    _emit(emit, 95, "STFT stems ready")
    warning = (
        f"STFT soft-Wiener isolation for {S} speaker(s). "
        "For stronger overlap separation on 2 voices, install torch + speechbrain "
        "and enable Download voice models, then Re-detect."
    )
    return stems_meta, residual_path, warning


def separate_masked(
    y: np.ndarray,
    sr: int,
    clusters: list[dict],
    out_dir: Path,
    *,
    emit: Emit = None,
) -> tuple[list[dict], Path, str]:
    """Backward-compatible entry — prefer STFT masking."""
    try:
        return separate_stft_masked(y, sr, clusters, out_dir, emit=emit)
    except Exception:
        # Fall back to simple time masks if STFT path fails
        return _separate_time_masked(y, sr, clusters, out_dir, emit=emit)


def _separate_time_masked(
    y: np.ndarray,
    sr: int,
    clusters: list[dict],
    out_dir: Path,
    *,
    emit: Emit = None,
) -> tuple[list[dict], Path, str]:
    import librosa

    _emit(emit, 20, "Building speaker activity masks…")
    n = len(y)
    masks = [_mask_from_segments(n, sr, c["segments"]) for c in clusters]
    stack = np.stack(masks, axis=0)
    active = stack.sum(axis=0)
    hop = 512
    frame_rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms_s = np.repeat(frame_rms, hop)[:n]
    if len(rms_s) < n:
        rms_s = np.pad(rms_s, (0, n - len(rms_s)))

    _emit(emit, 45, "Extracting overlapping stems…")
    weights = stack.copy()
    overlap = active > 1.0
    if np.any(overlap):
        denom = np.maximum(active, 1e-6)
        for s in range(stack.shape[0]):
            weights[s, overlap] = stack[s, overlap] / denom[overlap]
            # Prefer louder local energy slightly
            weights[s, overlap] *= 0.7 + 0.3 * (rms_s[overlap] / (float(np.max(rms_s)) + 1e-6))
        renorm = np.maximum(weights[:, overlap].sum(axis=0), 1e-6)
        for s in range(stack.shape[0]):
            weights[s, overlap] /= renorm

    stems_meta = []
    stem_sum = np.zeros(n, dtype=np.float32)
    for i, c in enumerate(clusters):
        _emit(emit, 50 + (40 * i) / max(len(clusters), 1), f"Writing speaker stem {i + 1}…")
        stem = (y * weights[i]).astype(np.float32)
        path = out_dir / f"speaker_{i + 1}.wav"
        sf.write(str(path), stem, sr)
        stem_sum += stem
        dur = sum(max(0.0, float(s["end"]) - float(s["start"])) for s in c["segments"])
        stems_meta.append(
            {
                "id": f"spk_{i + 1}",
                "label": f"Speaker {i + 1}",
                "stemPath": str(path),
                "segments": c["segments"],
                "durationSec": round(dur, 2),
            }
        )

    residual = np.clip(y - stem_sum, -1.0, 1.0).astype(np.float32)
    residual_path = out_dir / "residual.wav"
    sf.write(str(residual_path), residual, sr)
    _emit(emit, 95, "Stems ready")
    warning = (
        "Time-mask isolation (fallback). "
        "Install optional neural separators for higher isolation quality."
    )
    return stems_meta, residual_path, warning


def assign_stems_by_embedding(
    stems: list[np.ndarray],
    clusters: list[dict],
    y: np.ndarray,
    sr: int,
) -> list[np.ndarray]:
    """Match separator stems to diarization labels via MFCC cosine similarity."""
    import librosa

    def emb(audio: np.ndarray) -> np.ndarray:
        if len(audio) < sr // 4:
            audio = np.pad(audio, (0, max(0, sr // 4 - len(audio))))
        mfcc = librosa.feature.mfcc(y=audio.astype(np.float32), sr=sr, n_mfcc=20)
        v = mfcc.mean(axis=1)
        nrm = np.linalg.norm(v) + 1e-9
        return v / nrm

    enroll: list[np.ndarray] = []
    for c in clusters:
        parts: list[np.ndarray] = []
        for seg in c.get("segments") or []:
            a = max(0, int(float(seg["start"]) * sr))
            b = min(len(y), int(float(seg["end"]) * sr))
            if b > a:
                parts.append(y[a:b])
        if not parts:
            enroll.append(emb(np.zeros(sr // 2, dtype=np.float32)))
        else:
            enroll.append(emb(np.concatenate(parts)[: sr * 8]))

    stem_embs = [emb(s) for s in stems]
    used_stems: set[int] = set()
    ordered: list[np.ndarray | None] = [None] * len(clusters)
    pairs: list[tuple[float, int, int]] = []
    for ci, e in enumerate(enroll):
        for si, se in enumerate(stem_embs):
            pairs.append((float(np.dot(e, se)), ci, si))
    pairs.sort(reverse=True)
    for _score, ci, si in pairs:
        if ordered[ci] is not None or si in used_stems:
            continue
        ordered[ci] = stems[si]
        used_stems.add(si)
        if len(used_stems) >= len(stems):
            break
    leftover = [stems[i] for i in range(len(stems)) if i not in used_stems]
    out: list[np.ndarray] = []
    for i in range(len(clusters)):
        if ordered[i] is not None:
            out.append(ordered[i])  # type: ignore[arg-type]
        elif leftover:
            out.append(leftover.pop(0))
        else:
            out.append(np.zeros_like(y))
    return out


def _resample_to_len(s: np.ndarray, target_len: int, sr: int) -> np.ndarray:
    import librosa

    if len(s) == target_len:
        return s.astype(np.float32)
    # Heuristic: SepFormer often outputs 8k
    guess_sr = 8000 if abs(len(s) * (sr / 8000) - target_len) < abs(len(s) - target_len) else sr
    s = librosa.resample(s.astype(np.float32), orig_sr=guess_sr, target_sr=sr)
    if len(s) < target_len:
        s = np.pad(s, (0, target_len - len(s)))
    return s[:target_len].astype(np.float32)


def _fmt_elapsed(sec: float) -> str:
    s = max(0, int(sec))
    return f"{s // 60}:{s % 60:02d}"


def _run_sepformer_file(
    model,
    path: Path,
    emit: Emit = None,
    *,
    base_pct: float = 40,
    span: float = 12,
    label: str = "Neural separation",
) -> list[np.ndarray] | None:
    """Run SepFormer with heartbeat progress (inference can take minutes on CPU)."""
    import torch

    stop = threading.Event()
    t0 = time.monotonic()

    def heartbeat() -> None:
        while not stop.wait(1.2):
            elapsed = time.monotonic() - t0
            # Asymptotic creep inside this pass — never claims 100% until done
            phase_p = min(94.0, 4.0 + 90.0 * (1.0 - math.exp(-elapsed / 50.0)))
            overall = base_pct + span * (phase_p / 100.0)
            _emit(
                emit,
                overall,
                f"{label} — {_fmt_elapsed(elapsed)} elapsed (neural can take several minutes)…",
                phase="sepformer",
                phase_percent=phase_p,
            )

    _emit(
        emit,
        base_pct,
        f"{label} — starting…",
        phase="sepformer",
        phase_percent=1.0,
    )
    hb = threading.Thread(target=heartbeat, daemon=True)
    hb.start()
    try:
        est = model.separate_file(path=str(path))
        if not isinstance(est, torch.Tensor):
            return None
        arr = est.squeeze().cpu().numpy()
        if arr.ndim == 1:
            return None
        return [arr[i].astype(np.float32) for i in range(min(2, arr.shape[0]))]
    finally:
        stop.set()
        hb.join(timeout=2.0)
        _emit(
            emit,
            base_pct + span,
            f"{label} — done",
            phase="sepformer",
            phase_percent=100.0,
        )


def try_speechbrain_separate(
    y: np.ndarray,
    sr: int,
    n_spk: int,
    out_dir: Path,
    *,
    allow_download: bool,
    emit: Emit = None,
) -> list[np.ndarray] | None:
    """
    Neural 2-speaker SepFormer. For 3–4 speakers, cascade:
    separate → pick loudest residual pair iteratively.
    """
    if not allow_download or n_spk < 2:
        return None
    try:
        _emit(emit, 28, "Loading SpeechBrain SepFormer…", phase="load", phase_percent=5)
        from speechbrain.inference.separation import SepformerSeparation
        import torch  # noqa: F401

        model = SepformerSeparation.from_hparams(
            source="speechbrain/sepformer-wsj02mix",
            savedir=str(out_dir / ".sepformer"),
        )
        _emit(emit, 36, "SepFormer ready", phase="load", phase_percent=100)
        tmp = out_dir / "_mix_tmp.wav"
        sf.write(str(tmp), y, sr)

        if n_spk == 2:
            sources = _run_sepformer_file(
                model,
                tmp,
                emit,
                base_pct=40,
                span=18,
                label="Neural 2-speaker separation",
            )
            if not sources:
                return None
            return [_resample_to_len(s, len(y), sr) for s in sources]

        # Cascade for 3–4 speakers (best-effort on constrained machines)
        if n_spk > 4:
            return None
        passes = n_spk - 1
        _emit(
            emit,
            38,
            f"Cascade neural separation for {n_spk} speakers ({passes} passes)…",
            phase="cascade",
            phase_percent=0,
        )
        remaining = y.astype(np.float32).copy()
        collected: list[np.ndarray] = []
        # Reserve ~40–72% overall for cascade passes
        band_start = 40.0
        band_span = 32.0
        pass_span = band_span / max(1, passes)
        for step in range(passes):
            step_path = out_dir / f"_mix_cascade_{step}.wav"
            sf.write(str(step_path), remaining, sr)
            base = band_start + step * pass_span
            label = f"Cascade pass {step + 1}/{passes}"
            pair = _run_sepformer_file(
                model,
                step_path,
                emit,
                base_pct=base,
                span=pass_span * 0.92,
                label=label,
            )
            if not pair or len(pair) < 2:
                return None
            a = _resample_to_len(pair[0], len(y), sr)
            b = _resample_to_len(pair[1], len(y), sr)
            # Keep stronger stem; residual continues
            if float(np.mean(a * a)) >= float(np.mean(b * b)):
                collected.append(a)
                remaining = b
            else:
                collected.append(b)
                remaining = a
            _emit(
                emit,
                band_start + (step + 1) * pass_span,
                f"{label} complete — {len(collected)} stem(s) so far",
                phase="cascade",
                phase_percent=100.0 * (step + 1) / passes,
            )
        collected.append(remaining.astype(np.float32))
        return collected[:n_spk]
    except Exception:
        return None


def neural_availability() -> dict:
    """Small diagnostic for UI / logs."""
    out = {"torch": False, "speechbrain": False, "pyannote": False}
    try:
        import importlib.util

        out["torch"] = importlib.util.find_spec("torch") is not None
        out["speechbrain"] = importlib.util.find_spec("speechbrain") is not None
        out["pyannote"] = importlib.util.find_spec("pyannote") is not None
    except Exception:
        pass
    return out
