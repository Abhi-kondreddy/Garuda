from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Optional

from ..performance import ffmpeg_thread_args
from .analyze_clips import load_clip_report

Emit = Optional[Callable[[dict], None]]

QUALITY_PRESETS = {
    "draft": {"preset": "ultrafast", "crf": "28", "audio_k": "128k"},
    "good": {"preset": "veryfast", "crf": "20", "audio_k": "160k"},
    "high": {"preset": "slow", "crf": "17", "audio_k": "192k"},
}

RES_MAP_WIDE = {
    "720": (1280, 720),
    "1080": (1920, 1080),
    "1440": (2560, 1440),
}

RES_MAP_VERT = {
    "720": (720, 1280),
    "1080": (1080, 1920),
    "1440": (1440, 2560),
}


def _emit(
    emit: Emit,
    percent: float,
    message: str,
    *,
    phase: str | None = None,
    phase_percent: float | None = None,
    clip_index: int | None = None,
    clip_total: int | None = None,
    clip_name: str | None = None,
    t0: float | None = None,
) -> None:
    if emit:
        evt: dict[str, Any] = {
            "type": "progress",
            "stage": "export",
            "percent": int(max(0, min(100, percent))),
            "message": message,
        }
        if phase is not None:
            evt["phase"] = phase
        if phase_percent is not None:
            evt["phasePercent"] = int(max(0, min(100, phase_percent)))
        if clip_index is not None:
            evt["clipIndex"] = clip_index
        if clip_total is not None:
            evt["clipTotal"] = clip_total
        if clip_name is not None:
            evt["clipName"] = clip_name
        if t0 is not None:
            elapsed = max(0.0, time.time() - t0)
            evt["elapsedSec"] = round(elapsed, 1)
            if percent > 3:
                evt["etaSec"] = round(max(0.0, elapsed * (100.0 / float(percent) - 1.0)))
        emit(evt)


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {(proc.stderr or proc.stdout)[-1200:]}")


def _look_eq(look: str) -> str:
    if look == "warm":
        return "eq=contrast=1.05:saturation=1.12:brightness=0.02"
    if look == "contrast":
        return "eq=contrast=1.18:saturation=1.05:brightness=-0.02"
    return "eq=contrast=1.02:saturation=1.0"


def _audio_filter() -> str:
    return "loudnorm=I=-14:TP=-1.5:LRA=11"


def _vertical_scale_filter(
    w: int,
    h: int,
    fps: int,
    look: str,
    face_center_x: float | None,
) -> str:
    eq = _look_eq(look)
    if face_center_x is not None and 0.05 <= face_center_x <= 0.95:
        crop_x = f"min(max(iw*{face_center_x:.4f}-{w}/2\\,0)\\,iw-{w})"
        return (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}:{crop_x}:0,setsar=1,fps={fps},{eq}"
        )
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},setsar=1,fps={fps},{eq}"
    )


def _clip_face_center_x(project_path: Path | None, clip_id: str | None) -> float | None:
    if not project_path or not clip_id:
        return None
    report = load_clip_report(project_path, clip_id)
    if not report:
        return None
    visual = report.get("visual") or {}
    raw = visual.get("faceCenterX")
    if raw is None:
        return None
    try:
        cx = float(raw)
    except (TypeError, ValueError):
        return None
    if cx < 0.05 or cx > 0.95:
        return None
    return cx


def _dims(aspect: str, resolution: str) -> tuple[int, int]:
    key = resolution if resolution in RES_MAP_WIDE else "1080"
    if aspect == "9:16":
        return RES_MAP_VERT.get(key, RES_MAP_VERT["1080"])
    return RES_MAP_WIDE.get(key, RES_MAP_WIDE["1080"])


def export_output(
    *,
    project: dict,
    output_id: str,
    ffmpeg: str,
    out_path: Path,
    emit: Emit = None,
    quality: str = "good",
    resolution: str = "1080",
    burn_title: bool = True,
    fps: int = 30,
) -> dict[str, Any]:
    outputs = project.get("outputs") or []
    out = next((o for o in outputs if o.get("id") == output_id), None)
    if not out:
        raise ValueError(f"Output not found: {output_id}")

    clips = [c for c in (out.get("timeline") or {}).get("clips") or [] if c.get("enabled", True)]
    if not clips:
        raise ValueError("No enabled clips on this output timeline.")

    briefing = project.get("briefing") or {}
    look = briefing.get("look") or "warm"
    aspect = out.get("aspect") or "16:9"
    kind = out.get("kind") or "long"

    q = QUALITY_PRESETS.get(quality) or QUALITY_PRESETS["good"]
    w, h = _dims(aspect, resolution)
    fps = int(fps) if fps in (24, 30, 60) else 30
    project_path = Path(project.get("projectPath") or "") if project.get("projectPath") else None
    audio_af = _audio_filter()
    export_t0 = time.time()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _emit(
        emit,
        5,
        f"Exporting {output_id} ({quality}, {w}x{h})…",
        phase="encode",
        phase_percent=5,
        t0=export_t0,
    )

    with tempfile.TemporaryDirectory(prefix="garuda-edit-") as tmp:
        tmp_p = Path(tmp)
        parts: list[Path] = []
        n = len(clips)
        for i, clip in enumerate(clips):
            src = Path(clip["path"])
            if not src.exists():
                raise RuntimeError(f"Missing clip file: {src}")
            inn = float(clip.get("inSec", clip.get("in") or 0))
            out_t = clip.get("outSec", clip.get("out"))
            clip_name = src.name
            clip_id = clip.get("clipId")
            if aspect == "9:16":
                face_x = _clip_face_center_x(project_path, str(clip_id) if clip_id else None)
                scale = _vertical_scale_filter(w, h, fps, look, face_x)
            else:
                scale = (
                    f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                    f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},{_look_eq(look)}"
                )
            part = tmp_p / f"part_{i:03d}.mp4"
            cmd = [
                ffmpeg,
                "-y",
                "-ss",
                str(inn),
                "-i",
                str(src),
            ]
            if out_t is not None:
                dur = max(0.2, float(out_t) - inn)
                cmd += ["-t", str(dur)]
            cmd += [
                "-vf",
                scale,
                *ffmpeg_thread_args(),
                "-c:v",
                "libx264",
                "-preset",
                q["preset"],
                "-crf",
                q["crf"],
                "-af",
                audio_af,
                "-c:a",
                "aac",
                "-b:a",
                q["audio_k"],
                "-ar",
                "48000",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(part),
            ]
            pct = 10 + int(70 * i / max(n, 1))
            _emit(
                emit,
                pct,
                f"[{i + 1}/{n}] Encoding {clip_name}",
                phase="encode",
                phase_percent=int(100 * i / max(n, 1)),
                clip_index=i + 1,
                clip_total=n,
                clip_name=clip_name,
                t0=export_t0,
            )
            _run(cmd)
            parts.append(part)
            _emit(
                emit,
                10 + int(70 * (i + 1) / max(n, 1)),
                f"[{i + 1}/{n}] Encoded {clip_name}",
                phase="encode",
                phase_percent=int(100 * (i + 1) / max(n, 1)),
                clip_index=i + 1,
                clip_total=n,
                clip_name=clip_name,
                t0=export_t0,
            )

        concat_list = tmp_p / "concat.txt"
        concat_list.write_text(
            "".join(f"file '{p.as_posix()}'\n" for p in parts),
            encoding="utf-8",
        )
        merged = tmp_p / "merged.mp4"
        _emit(emit, 85, "Concatenating…", phase="concat", phase_percent=40, t0=export_t0)
        _run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                str(merged),
            ]
        )
        _emit(emit, 90, "Concatenated", phase="concat", phase_percent=100, t0=export_t0)

        overlays = (out.get("timeline") or {}).get("overlays") or []
        title_overlay = next((o for o in overlays if o.get("type") == "title" and o.get("text")), None)
        if burn_title and title_overlay:
            text = str(title_overlay["text"]).replace(":", "\\:").replace("'", "\\'")
            start = float(title_overlay.get("start") or 0)
            end = float(title_overlay.get("end") or 4)
            fontsize = max(36, int(64 * (h / 1920.0))) if kind == "short" else max(28, int(48 * (h / 1080.0)))
            y = "h*0.12" if kind == "short" else "h*0.08"
            vf = (
                f"drawtext=text='{text}':fontsize={fontsize}:fontcolor=white:"
                f"borderw=3:bordercolor=black@0.6:x=(w-text_w)/2:y={y}:"
                f"enable='between(t\\,{start}\\,{end})'"
            )
            _emit(emit, 92, "Burning title…", phase="title", phase_percent=20, t0=export_t0)
            _run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(merged),
                    "-vf",
                    vf,
                    *ffmpeg_thread_args(),
                    "-c:v",
                    "libx264",
                    "-preset",
                    q["preset"],
                    "-crf",
                    q["crf"],
                    "-c:a",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(out_path),
                ]
            )
            _emit(emit, 98, "Title burned", phase="title", phase_percent=100, t0=export_t0)
        else:
            merged.replace(out_path)

    _emit(emit, 100, "Export complete", phase="encode", phase_percent=100, t0=export_t0)
    meta = {
        "outputPath": str(out_path),
        "outputId": output_id,
        "aspect": aspect,
        "clipCount": len(clips),
        "quality": quality,
        "resolution": f"{w}x{h}",
        "fps": fps,
    }
    side = out_path.with_suffix(".json")
    side.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta
