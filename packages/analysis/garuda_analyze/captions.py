"""Subtitle generation (SRT / WebVTT) from a Garuda transcript."""

from __future__ import annotations

from pathlib import Path


def _timestamp(t: float, sep: str) -> str:
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms >= 1000:
        ms = 999
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(transcript: list[dict]) -> str:
    blocks: list[str] = []
    n = 1
    for seg in transcript or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = _timestamp(float(seg.get("start") or 0.0), ",")
        end = _timestamp(float(seg.get("end") or 0.0), ",")
        blocks.append(f"{n}\n{start} --> {end}\n{text}\n")
        n += 1
    return "\n".join(blocks)


def to_vtt(transcript: list[dict]) -> str:
    out = ["WEBVTT", ""]
    for seg in transcript or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = _timestamp(float(seg.get("start") or 0.0), ".")
        end = _timestamp(float(seg.get("end") or 0.0), ".")
        out.append(f"{start} --> {end}")
        out.append(text)
        out.append("")
    return "\n".join(out)


def write_captions(transcript: list[dict], out_dir, base: str = "captions") -> dict:
    """Write ``<base>.srt`` and ``<base>.vtt`` into ``out_dir``. No-op if empty."""
    if not transcript:
        return {}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    srt_path = out_dir / f"{base}.srt"
    vtt_path = out_dir / f"{base}.vtt"
    srt_path.write_text(to_srt(transcript), encoding="utf-8")
    vtt_path.write_text(to_vtt(transcript), encoding="utf-8")
    return {"srt": str(srt_path), "vtt": str(vtt_path)}
