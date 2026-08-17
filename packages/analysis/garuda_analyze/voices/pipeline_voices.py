from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import soundfile as sf

from . import SPEAKER_COLORS
from .diarize import diarize_librosa, try_pyannote_diarize
from .project import default_project, save_project, speakers_path, stems_dir, voices_dir
from .separate import assign_stems_by_embedding, separate_masked, try_speechbrain_separate

Emit = Optional[Callable[[dict], None]]


def _ensure_wav(report_dir: Path, ffmpeg: str, emit: Emit) -> Path:
    wav = report_dir / "audio.wav"
    if wav.exists():
        return wav
    # try extract from report.json sourcePath
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    src = report.get("sourcePath")
    if not src or not Path(src).exists():
        raise RuntimeError("No audio.wav and source video missing — re-analyze the video.")
    if emit:
        emit({"type": "progress", "stage": "ingest", "percent": 5, "message": "Extracting audio…"})
    import subprocess

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        src,
        "-ac",
        "1",
        "-ar",
        "16000",
        str(wav),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Audio extract failed: {proc.stderr[-600:]}")
    return wav


def run_voice_analyze(
    *,
    report_dir: Path,
    ffmpeg: str,
    hf_token: str | None,
    allow_download: bool,
    emit: Emit,
) -> dict:
    report_dir = Path(report_dir)
    wav_path = _ensure_wav(report_dir, ffmpeg, emit)
    y, sr = sf.read(str(wav_path), always_2d=False)
    y = np.asarray(y, dtype=np.float32)
    if y.ndim > 1:
        y = y.mean(axis=1)

    clusters = try_pyannote_diarize(
        str(wav_path), hf_token=hf_token, allow_download=allow_download, emit=emit
    )
    mode_note = "separated"
    if clusters is None:
        if emit:
            emit(
                {
                    "type": "progress",
                    "stage": "diarize",
                    "percent": 20,
                    "message": "Using local clustering diarization…",
                }
            )
        clusters = diarize_librosa(y, sr, emit=emit)

    # clamp speakers
    clusters = clusters[:4]
    out_stems = stems_dir(report_dir)

    # try neural 2-spk separation then assign; else masked
    neural = try_speechbrain_separate(
        y, sr, len(clusters), out_stems, allow_download=allow_download, emit=emit
    )
    warning = None
    if neural and len(neural) >= 2 and len(clusters) >= 2:
        if emit:
            emit(
                {
                    "type": "progress",
                    "stage": "separate",
                    "percent": 55,
                    "message": "Assigning stems to speakers…",
                }
            )
        assigned = assign_stems_by_embedding(neural, clusters, y, sr)
        if emit:
            emit(
                {
                    "type": "progress",
                    "stage": "separate",
                    "percent": 60,
                    "message": "Writing neural stems…",
                }
            )
        speakers = []
        stem_sum = np.zeros_like(y)
        for i, stem in enumerate(assigned[: len(clusters)]):
            path = out_stems / f"speaker_{i + 1}.wav"
            sf.write(str(path), stem, sr)
            stem_sum += stem
            segs = clusters[i]["segments"] if i < len(clusters) else []
            dur = sum(max(0.0, float(s["end"]) - float(s["start"])) for s in segs)
            speakers.append(
                {
                    "id": f"spk_{i + 1}",
                    "label": f"Speaker {i + 1}",
                    "color": SPEAKER_COLORS[i % len(SPEAKER_COLORS)],
                    "durationSec": round(dur, 2),
                    "stemPath": str(path),
                    "segments": segs,
                }
            )
        residual = np.clip(y - stem_sum, -1.0, 1.0)
        residual_path = out_stems / "residual.wav"
        sf.write(str(residual_path), residual, sr)
        mode = "separated"
    else:
        stems_meta, residual_path, warning = separate_masked(
            y, sr, clusters, out_stems, emit=emit
        )
        speakers = []
        for i, meta in enumerate(stems_meta):
            speakers.append(
                {
                    **meta,
                    "color": SPEAKER_COLORS[i % len(SPEAKER_COLORS)],
                }
            )
        mode = "masked"
        mode_note = mode

    manifest = {
        "version": 1,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "audioPath": str(wav_path),
        "residualPath": str(residual_path),
        "mode": mode if neural else mode_note,
        "warning": warning,
        "speakers": speakers,
    }
    sp_path = speakers_path(report_dir)
    sp_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    project = default_project(report_dir, [s["id"] for s in speakers])
    save_project(voices_dir(report_dir) / "project.json", project)

    if emit:
        emit(
            {
                "type": "progress",
                "stage": "export",
                "percent": 100,
                "message": f"Voices ready — {len(speakers)} speaker(s)",
            }
        )
    return {
        "speakersPath": str(sp_path),
        "projectPath": str(voices_dir(report_dir) / "project.json"),
        "speakerCount": len(speakers),
    }
