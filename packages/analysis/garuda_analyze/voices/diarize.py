from __future__ import annotations

from typing import Callable, Optional

import numpy as np

Emit = Optional[Callable[[dict], None]]


def _emit(emit: Emit, percent: float, message: str, stage: str = "diarize") -> None:
    if emit:
        emit({"type": "progress", "stage": stage, "percent": int(percent), "message": message})


def _kmeans(X: np.ndarray, k: int, iters: int = 20) -> np.ndarray:
    rng = np.random.default_rng(42)
    n = len(X)
    centroids = X[rng.choice(n, size=k, replace=False)].copy()
    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        d = ((X[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        labels = d.argmin(axis=1)
        for c in range(k):
            pts = X[labels == c]
            if len(pts):
                centroids[c] = pts.mean(axis=0)
    return labels


def diarize_librosa(
    y: np.ndarray,
    sr: int,
    *,
    max_speakers: int = 4,
    emit: Emit = None,
) -> list[dict]:
    """Energy + MFCC clustering diarization (always available, no sklearn)."""
    import librosa

    _emit(emit, 10, "Extracting speaker features…")
    hop = 512
    frame_sec = hop / sr
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    feats = mfcc.T
    n = len(feats)
    if n < 8:
        return [{"cluster": 0, "segments": [{"start": 0.0, "end": float(len(y) / sr)}]}]

    speech = rms > (np.percentile(rms, 40) + 1e-8)
    idx = np.where(speech)[0]
    if len(idx) < 8:
        idx = np.arange(n)

    _emit(emit, 35, "Clustering speakers…")
    X = feats[idx]
    # standardize
    X = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-6)
    k_max = min(max_speakers, max(2, len(idx) // 40))
    best_k = 2
    best_score = -1e9
    labels_best = None
    for k in range(2, k_max + 1):
        lab = _kmeans(X, k)
        cents = []
        for c in range(k):
            pts = X[lab == c]
            if len(pts):
                cents.append(pts.mean(axis=0))
        if len(cents) < 2:
            continue
        cents_a = np.stack(cents)
        d = 0.0
        cnt = 0
        for i in range(len(cents_a)):
            for j in range(i + 1, len(cents_a)):
                d += float(np.linalg.norm(cents_a[i] - cents_a[j]))
                cnt += 1
        score = d / max(cnt, 1)
        # prefer balanced clusters
        sizes = [int((lab == c).sum()) for c in range(k)]
        balance = min(sizes) / (max(sizes) + 1e-6)
        score *= 0.5 + 0.5 * balance
        if score > best_score:
            best_score = score
            best_k = k
            labels_best = lab

    if labels_best is None:
        labels_best = np.zeros(len(idx), dtype=int)
        best_k = 1

    frame_labels = np.full(n, -1, dtype=int)
    frame_labels[idx] = labels_best

    win = 5
    smoothed = frame_labels.copy()
    for i in range(n):
        a = max(0, i - win)
        b = min(n, i + win + 1)
        window = frame_labels[a:b]
        window = window[window >= 0]
        if len(window):
            smoothed[i] = int(np.bincount(window).argmax())

    _emit(emit, 70, "Building speaker segments…")
    speakers: dict[int, list[dict]] = {c: [] for c in range(best_k)}
    cur = int(smoothed[0])
    start_i = 0
    for i in range(1, n + 1):
        lab = int(smoothed[i]) if i < n else -999
        if lab != cur:
            if cur >= 0:
                t0 = start_i * frame_sec
                t1 = i * frame_sec
                if t1 - t0 >= 0.25:
                    speakers[cur].append({"start": round(t0, 3), "end": round(t1, 3)})
            cur = lab
            start_i = i

    out = []
    for c in range(best_k):
        segs = speakers.get(c) or []
        if not segs:
            continue
        out.append({"cluster": c, "segments": segs})
    if not out:
        out = [{"cluster": 0, "segments": [{"start": 0.0, "end": float(len(y) / sr)}]}]
    _emit(emit, 90, f"Found {len(out)} speaker(s)")
    return out


def try_pyannote_diarize(
    wav_path: str,
    *,
    hf_token: str | None,
    allow_download: bool,
    emit: Emit = None,
) -> list[dict] | None:
    if not allow_download:
        return None
    try:
        _emit(emit, 15, "Loading pyannote diarization…")
        from pyannote.audio import Pipeline

        token = hf_token or None
        try:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                token=token,
            )
        except TypeError:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=token,
            )
        _emit(emit, 40, "Running neural diarization…")
        diarization = pipeline(wav_path)
        by_spk: dict[str, list[dict]] = {}
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            by_spk.setdefault(speaker, []).append(
                {"start": round(float(turn.start), 3), "end": round(float(turn.end), 3)}
            )
        out = []
        for i, (_spk, segs) in enumerate(sorted(by_spk.items(), key=lambda x: x[1][0]["start"])):
            if i >= 4:
                break
            out.append({"cluster": i, "segments": segs})
        return out or None
    except Exception:
        return None
