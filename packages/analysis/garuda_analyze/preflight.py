"""Input QC + capability check, run before the heavy analysis stages.

Cheap: derives everything from the single ffprobe `meta` dict plus module
import probes. Black/freeze detection is done post-hoc in `qc.py` from the
already-decoded brightness/motion arrays (no second decode pass).
"""

from __future__ import annotations

import importlib
import math

_OPTIONAL_MODULES = [
    "cv2",
    "librosa",
    "faster_whisper",
    "scenedetect",
    "pyloudnorm",
    "onnxruntime",
    "torch",
    "sklearn",
    "jsonschema",
]


def capability_report() -> dict:
    caps: dict = {}
    for mod in _OPTIONAL_MODULES:
        try:
            importlib.import_module(mod)
            caps[mod] = True
        except Exception:
            caps[mod] = False
    return caps


def _aspect_label(w: int, h: int) -> str:
    if w <= 0 or h <= 0:
        return "unknown"
    r = w / h
    if abs(r - 16 / 9) < 0.06:
        return "16:9"
    if abs(r - 9 / 16) < 0.06:
        return "9:16"
    if abs(r - 1.0) < 0.06:
        return "1:1"
    if abs(r - 4 / 3) < 0.06:
        return "4:3"
    return f"{r:.2f}:1"


def _rate(s: object) -> "float | None":
    if isinstance(s, str) and "/" in s:
        try:
            n, d = s.split("/", 1)
            n, d = float(n), float(d)
            return n / d if d else None
        except (TypeError, ValueError):
            return None
    try:
        return float(s)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def preflight(meta: dict) -> dict:
    w = int(meta.get("width") or 0)
    h = int(meta.get("height") or 0)
    fps = float(meta.get("fps") or 0.0)
    warnings: list[str] = []

    avg = _rate(meta.get("avg_frame_rate"))
    r = _rate(meta.get("r_frame_rate"))
    vfr = bool(avg and r and r > 0 and abs(avg - r) / r > 0.05)
    if vfr:
        warnings.append("Variable frame rate detected — timestamps may drift.")

    ct = (meta.get("color_transfer") or "").lower()
    hdr = ct in {"smpte2084", "arib-std-b67", "smpte428"}

    rotation = int(meta.get("rotation") or 0) % 360
    if rotation in (90, 270):
        warnings.append(f"Video is rotated {rotation}° — orientation may be portrait/landscape flipped.")

    if not meta.get("has_audio"):
        warnings.append("No audio stream — audio metrics and ASR will be skipped.")

    bitrate_kbps = None
    br = meta.get("bit_rate")
    if isinstance(br, (int, float)) and math.isfinite(br) and br > 0:
        bitrate_kbps = round(br / 1000.0, 1)
        # crude low-bitrate flag relative to resolution
        px = max(1, w * h)
        if bitrate_kbps < (px / 1000.0) * 1.5:
            warnings.append("Bitrate looks low for the resolution — expect compression artifacts.")

    return {
        "resolution": [w, h],
        "aspect": _aspect_label(w, h),
        "fps": round(fps, 3),
        "vfr": vfr,
        "hdr": hdr,
        "pixFmt": meta.get("pix_fmt"),
        "rotationDeg": rotation,
        "hasAudio": bool(meta.get("has_audio")),
        "audioChannels": int(meta.get("audio_channels") or 0),
        "bitrateKbps": bitrate_kbps,
        "codec": meta.get("codec"),
        "warnings": warnings,
        "capabilities": capability_report(),
    }
