from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

Emit = Optional[Callable[[dict], None]]


def _emit(emit: Emit, percent: float, message: str) -> None:
    if emit:
        emit({"type": "progress", "stage": "render", "percent": int(percent), "message": message})


def mux_video(ffmpeg: str, video_path: Path, audio_path: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg mux failed: {proc.stderr[-800:]}")


def run_render_job(job_path: Path, *, ffmpeg: str, emit: Emit = None) -> dict[str, Any]:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job["status"] = "running"
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")

    output_path = job.get("outputPath")
    ops = job.get("ops") or []
    n = max(len(ops), 1)

    try:
        last_audio = None
        for i, op in enumerate(ops):
            pct = (i / n) * 90
            typ = op.get("type")
            if typ == "audioRemix":
                _emit(emit, pct, "Building enhanced mix…")
                from .enhance import build_preview_mix
                from .project import load_project

                project_path = Path(op["projectPath"])
                project = load_project(project_path)
                report_dir = Path(project["reportDir"])
                mix = build_preview_mix(
                    report_dir=report_dir,
                    project=project,
                    ffmpeg=ffmpeg,
                    emit=emit,
                )
                project["previewMixPath"] = str(mix)
                from .project import save_project

                save_project(project_path, project)
                last_audio = mix
            elif typ == "muxVideo":
                _emit(emit, pct + 5, "Muxing video…")
                video = Path(op["videoPath"])
                audio = Path(op.get("audioPath") or last_audio or "")
                if not output_path:
                    output_path = str(job_path.parent / "output.mp4")
                mux_video(ffmpeg, video, audio, Path(output_path))
            elif typ in ("timelineCuts", "colorGrade"):
                _emit(emit, pct, f"Skipping reserved op {typ} (not implemented yet)")
            else:
                raise RuntimeError(f"Unknown render op: {typ}")

        job["status"] = "done"
        job["progress"] = 100
        job["outputPath"] = output_path
        job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
        _emit(emit, 100, "Export complete")
        return {"outputPath": output_path, "jobPath": str(job_path)}
    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
        job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
        raise
