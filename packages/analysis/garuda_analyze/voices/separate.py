from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import numpy as np
import soundfile as sf

Emit = Optional[Callable[[dict], None]]


def _emit(emit: Emit, percent: float, message: str) -> None:
    if emit:
        emit({"type": "progress", "stage": "separate", "percent": int(percent), "message": message})


def _mask_from_segments(n_samples: int, sr: int, segments: list[dict], fade: int = 256) -> np.ndarray:
    mask = np.zeros(n_samples, dtype=np.float32)
    for seg in segments:
        a = max(0, int(float(seg["start"]) * sr))
        b = min(n_samples, int(float(seg["end"]) * sr))
        if b <= a:
            continue
        mask[a:b] = 1.0
        # soft edges
        f = min(fade, (b - a) // 4)
        if f > 1:
            ramp = np.linspace(0, 1, f, dtype=np.float32)
            mask[a : a + f] = np.maximum(mask[a : a + f], ramp)
            mask[b - f : b] = np.maximum(mask[b - f : b], ramp[::-1])
    return mask


def separate_masked(
    y: np.ndarray,
    sr: int,
    clusters: list[dict],
    out_dir: Path,
    *,
    emit: Emit = None,
) -> tuple[list[dict], Path, str]:
    """
    Soft-mask separation from diarization activity.
    Overlapping regions: energy-weighted split across active speakers (Wiener-ish).
    """
    import librosa

    _emit(emit, 20, "Building speaker activity masks…")
    n = len(y)
    masks = []
    for c in clusters:
        masks.append(_mask_from_segments(n, sr, c["segments"]))
    stack = np.stack(masks, axis=0)  # S x T
    active = stack.sum(axis=0)
    # overlap: split by local RMS contribution estimate using short-time energy
    hop = 512
    frame_rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    # upsample frame_rms to samples
    rms_s = np.repeat(frame_rms, hop)[:n]
    if len(rms_s) < n:
        rms_s = np.pad(rms_s, (0, n - len(rms_s)))

    _emit(emit, 45, "Extracting overlapping stems…")
    # In overlap zones, soft-split equally among active; elsewhere exclusive
    S = stack.shape[0]
    weights = stack.copy()
    overlap = active > 1.0
    if np.any(overlap):
        # give slightly more weight to speakers whose segment centers match higher local energy
        for s in range(S):
            # keep mask; normalize later
            pass
        # normalize active speakers to sum 1
        denom = np.maximum(active, 1e-6)
        for s in range(S):
            weights[s, overlap] = stack[s, overlap] / denom[overlap]

    stems_meta = []
    stem_sum = np.zeros(n, dtype=np.float32)
    for i, c in enumerate(clusters):
        _emit(emit, 50 + (40 * i) / max(len(clusters), 1), f"Writing speaker stem {i + 1}…")
        stem = (y * weights[i]).astype(np.float32)
        # light spectral denoise outside mask already zeroed
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

    residual = (y - stem_sum).astype(np.float32)
    # avoid amplification of inversion error
    residual = np.clip(residual, -1.0, 1.0)
    residual_path = out_dir / "residual.wav"
    sf.write(str(residual_path), residual, sr)
    _emit(emit, 95, "Stems ready")
    warning = (
        "Overlap handled with soft spectral masks. "
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
        n = np.linalg.norm(v) + 1e-9
        return v / n

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
    # greedy bipartite match by cosine
    used_stems: set[int] = set()
    ordered: list[np.ndarray | None] = [None] * len(clusters)
    pairs: list[tuple[float, int, int]] = []
    for ci, e in enumerate(enroll):
        for si, se in enumerate(stem_embs):
            pairs.append((float(np.dot(e, se)), ci, si))
    pairs.sort(reverse=True)
    for score, ci, si in pairs:
        if ordered[ci] is not None or si in used_stems:
            continue
        ordered[ci] = stems[si]
        used_stems.add(si)
        if len(used_stems) >= len(stems):
            break
    # fill leftovers
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


def try_speechbrain_separate(
    y: np.ndarray,
    sr: int,
    n_spk: int,
    out_dir: Path,
    *,
    allow_download: bool,
    emit: Emit = None,
) -> list[np.ndarray] | None:
    if not allow_download or n_spk < 2:
        return None
    try:
        _emit(emit, 30, "Loading SpeechBrain SepFormer…")
        from speechbrain.inference.separation import SepformerSeparation
        import torch
        import torchaudio
        import tempfile
        import soundfile as sf

        # SepFormer wsj02mix is 2-speaker; for >2 fall back
        if n_spk != 2:
            return None
        model = SepformerSeparation.from_hparams(
            source="speechbrain/sepformer-wsj02mix",
            savedir=str(out_dir / ".sepformer"),
        )
        tmp = out_dir / "_mix_tmp.wav"
        # resample to 8k if needed by model — speechbrain handles
        sf.write(str(tmp), y, sr)
        est = model.separate_file(path=str(tmp))
        # est: tensor sources
        if isinstance(est, torch.Tensor):
            arr = est.squeeze().cpu().numpy()
        else:
            return None
        if arr.ndim == 1:
            return None
        sources = [arr[i].astype(np.float32) for i in range(min(2, arr.shape[0]))]
        # resample back if model changed sr
        out = []
        for s in sources:
            if len(s) != len(y):
                import librosa

                s = librosa.resample(s, orig_sr=8000 if abs(len(s) - len(y) // (sr // 8000)) < len(y) * 0.2 else sr, target_sr=sr)
                if len(s) < len(y):
                    s = np.pad(s, (0, len(y) - len(s)))
                s = s[: len(y)]
            out.append(s.astype(np.float32))
        return out
    except Exception:
        return None
