from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import soundfile as sf

from .project import DEFAULT_FX, stems_dir

Emit = Optional[Callable[[dict], None]]


def _emit(emit: Emit, percent: float, message: str) -> None:
    if emit:
        emit({"type": "progress", "stage": "enhance", "percent": int(percent), "message": message})


def _ffmpeg_afilter(fx: dict[str, Any]) -> str:
    """Build ffmpeg audio filter chain from parametric FX."""
    parts: list[str] = []
    gain = float(fx.get("gainDb") or 0)
    bass = float(fx.get("bassDb") or 0)
    clarity = float(fx.get("clarityDb") or 0)
    presence = float(fx.get("presenceDb") or 0)
    compress = float(fx.get("compress") or 0)
    deess = float(fx.get("deess") or 0)
    gate = float(fx.get("gate") or 0)

    if abs(bass) > 0.05:
        parts.append(f"bass=g={bass:.2f}:f=120")
    if abs(clarity) > 0.05:
        parts.append(f"equalizer=f=2500:t=q:w=1.2:g={clarity:.2f}")
    if abs(presence) > 0.05:
        parts.append(f"equalizer=f=4500:t=q:w=1.0:g={presence:.2f}")
    if compress > 0.05:
        thr = -20 - compress * 8
        ratio = 2 + compress * 6
        parts.append(f"acompressor=threshold={thr:.1f}dB:ratio={ratio:.1f}:attack=10:release=80")
    if deess > 0.05:
        parts.append(f"deesser=i={0.1 + deess * 0.7:.2f}")
    if gate > 0.05:
        parts.append(f"agate=threshold={-50 + gate * 25:.1f}dB:ratio=3:attack=5:release=50")
    if abs(gain) > 0.05:
        parts.append(f"volume={gain:.2f}dB")
    if not parts:
        parts.append("anull")
    return ",".join(parts)


def try_ml_enhance(y: np.ndarray, sr: int) -> np.ndarray | None:
    """Optional DeepFilterNet (or similar) speech enhancement."""
    try:
        from df.enhance import enhance, init_df
        import torch

        model, df_state, _ = init_df()
        # deepfilter expects specific sr often 48k
        import librosa

        target_sr = getattr(df_state, "sr", 48000)
        if sr != target_sr:
            y_r = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
        else:
            y_r = y
        wav = torch.from_numpy(y_r.astype(np.float32)).unsqueeze(0)
        enh = enhance(model, df_state, wav)
        out = enh.squeeze().cpu().numpy().astype(np.float32)
        if target_sr != sr:
            out = librosa.resample(out, orig_sr=target_sr, target_sr=sr)
        if len(out) < len(y):
            out = np.pad(out, (0, len(y) - len(out)))
        return out[: len(y)]
    except Exception:
        return None


def try_pedalboard(y: np.ndarray, sr: int, fx: dict[str, Any]) -> np.ndarray | None:
    try:
        from pedalboard import Pedalboard, Compressor, Gain, LowShelfFilter, PeakFilter, NoiseGate

        board = Pedalboard([])
        gain = float(fx.get("gainDb") or 0)
        bass = float(fx.get("bassDb") or 0)
        clarity = float(fx.get("clarityDb") or 0)
        presence = float(fx.get("presenceDb") or 0)
        compress = float(fx.get("compress") or 0)
        gate = float(fx.get("gate") or 0)
        if gate > 0.05:
            board.append(NoiseGate(threshold_db=-50 + gate * 25, ratio=3))
        if abs(bass) > 0.05:
            board.append(LowShelfFilter(cutoff_frequency_hz=120, gain_db=bass))
        if abs(clarity) > 0.05:
            board.append(PeakFilter(cutoff_frequency_hz=2500, gain_db=clarity, q=1.2))
        if abs(presence) > 0.05:
            board.append(PeakFilter(cutoff_frequency_hz=4500, gain_db=presence, q=1.0))
        if compress > 0.05:
            board.append(
                Compressor(
                    threshold_db=-20 - compress * 8,
                    ratio=2 + compress * 6,
                    attack_ms=10,
                    release_ms=80,
                )
            )
        if abs(gain) > 0.05:
            board.append(Gain(gain_db=gain))
        if len(board) == 0:
            return y.astype(np.float32)
        out = board(y.astype(np.float32), sr)
        return np.asarray(out, dtype=np.float32).reshape(-1)
    except Exception:
        return None


def enhance_audio(
    y: np.ndarray,
    sr: int,
    fx: dict[str, Any],
    *,
    ffmpeg: str,
    tmp_dir: Path,
) -> np.ndarray:
    fx = {**DEFAULT_FX, **(fx or {})}
    audio = y.astype(np.float32)
    if fx.get("mlEnhance"):
        ml = try_ml_enhance(audio, sr)
        if ml is not None:
            audio = ml

    pb = try_pedalboard(audio, sr, fx)
    if pb is not None:
        return np.clip(pb, -1.0, 1.0)

    # ffmpeg fallback
    inp = tmp_dir / "_enh_in.wav"
    outp = tmp_dir / "_enh_out.wav"
    sf.write(str(inp), audio, sr)
    af = _ffmpeg_afilter(fx)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(inp),
        "-af",
        af,
        str(outp),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        # last-resort gain-only
        g = float(fx.get("gainDb") or 0)
        if abs(g) > 0.05:
            audio = audio * (10 ** (g / 20.0))
        return np.clip(audio, -1.0, 1.0)
    if proc.returncode != 0 or not outp.exists():
        return np.clip(audio, -1.0, 1.0)
    out, out_sr = sf.read(str(outp), always_2d=False)
    out = np.asarray(out, dtype=np.float32)
    if out.ndim > 1:
        out = out.mean(axis=1)
    if out_sr != sr:
        import librosa

        out = librosa.resample(out, orig_sr=out_sr, target_sr=sr)
    if len(out) < len(audio):
        out = np.pad(out, (0, len(audio) - len(out)))
    return np.clip(out[: len(audio)], -1.0, 1.0)


def enhance_stem_to_file(
    *,
    report_dir: Path,
    speaker_id: str,
    project: dict[str, Any],
    out_path: Path,
    ffmpeg: str,
    emit: Emit = None,
) -> Path:
    import json

    speakers = json.loads((Path(project["speakersPath"])).read_text(encoding="utf-8"))
    spk = next((s for s in speakers["speakers"] if s["id"] == speaker_id), None)
    if not spk:
        raise RuntimeError(f"Speaker {speaker_id} not found")
    y, sr = sf.read(spk["stemPath"], always_2d=False)
    y = np.asarray(y, dtype=np.float32)
    if y.ndim > 1:
        y = y.mean(axis=1)
    fx = (project.get("fx") or {}).get(speaker_id) or DEFAULT_FX
    _emit(emit, 30, f"Enhancing {spk.get('label') or speaker_id}…")
    tmp = stems_dir(report_dir) / ".cache"
    tmp.mkdir(parents=True, exist_ok=True)
    out = enhance_audio(y, sr, fx, ffmpeg=ffmpeg, tmp_dir=tmp)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), out, sr)
    _emit(emit, 100, "Solo stem ready")
    return out_path


def build_preview_mix(
    *,
    report_dir: Path,
    project: dict[str, Any],
    ffmpeg: str,
    emit: Emit = None,
) -> Path:
    import json

    from .remix import remix_stems

    speakers = json.loads(Path(project["speakersPath"]).read_text(encoding="utf-8"))
    _emit(emit, 10, "Loading stems…")
    tmp = stems_dir(report_dir) / ".cache"
    tmp.mkdir(parents=True, exist_ok=True)
    enhanced_paths: list[Path] = []
    sr = None
    for i, spk in enumerate(speakers["speakers"]):
        _emit(emit, 15 + 60 * (i / max(len(speakers["speakers"]), 1)), f"FX: {spk['label']}")
        y, file_sr = sf.read(spk["stemPath"], always_2d=False)
        y = np.asarray(y, dtype=np.float32)
        if y.ndim > 1:
            y = y.mean(axis=1)
        sr = file_sr
        fx = (project.get("fx") or {}).get(spk["id"]) or DEFAULT_FX
        enh = enhance_audio(y, file_sr, fx, ffmpeg=ffmpeg, tmp_dir=tmp)
        p = tmp / f"enh_{spk['id']}.wav"
        sf.write(str(p), enh, file_sr)
        enhanced_paths.append(p)

    residual = speakers.get("residualPath")
    out = Path(report_dir) / "voices" / "preview_mix.wav"
    _emit(emit, 85, "Remixing preview…")
    remix_stems(enhanced_paths, residual, out, sr=sr or 16000)
    _emit(emit, 100, "Preview mix ready")
    return out
