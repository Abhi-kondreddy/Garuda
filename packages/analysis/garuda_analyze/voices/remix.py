from __future__ import annotations

from typing import Optional

from pathlib import Path

import numpy as np
import soundfile as sf


def remix_stems(
    stem_paths: list[Path],
    residual_path: str | Path | None,
    out_path: Path,
    *,
    sr: int,
) -> Path:
    mix = None
    for p in stem_paths:
        y, file_sr = sf.read(str(p), always_2d=False)
        y = np.asarray(y, dtype=np.float32)
        if y.ndim > 1:
            y = y.mean(axis=1)
        if file_sr != sr:
            import librosa

            y = librosa.resample(y, orig_sr=file_sr, target_sr=sr)
        if mix is None:
            mix = y
        else:
            n = max(len(mix), len(y))
            if len(mix) < n:
                mix = np.pad(mix, (0, n - len(mix)))
            if len(y) < n:
                y = np.pad(y, (0, n - len(y)))
            mix = mix + y
    if mix is None:
        mix = np.zeros(sr, dtype=np.float32)

    if residual_path and Path(residual_path).exists():
        r, r_sr = sf.read(str(residual_path), always_2d=False)
        r = np.asarray(r, dtype=np.float32)
        if r.ndim > 1:
            r = r.mean(axis=1)
        if r_sr != sr:
            import librosa

            r = librosa.resample(r, orig_sr=r_sr, target_sr=sr)
        n = max(len(mix), len(r))
        if len(mix) < n:
            mix = np.pad(mix, (0, n - len(mix)))
        if len(r) < n:
            r = np.pad(r, (0, n - len(r)))
        mix = mix + r

    peak = float(np.max(np.abs(mix)) + 1e-9)
    if peak > 0.99:
        mix = mix * (0.99 / peak)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), mix.astype(np.float32), sr)
    return out_path
