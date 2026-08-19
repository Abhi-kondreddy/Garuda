"""Accessibility & compliance parameters.

Algorithmic (always available): photosensitivity flash risk + caption reading
speed. Model-dependent (copyright fingerprint, PII-in-frame, OCR contrast) are
present in the catalog but reported as ``unavailable`` until wired.
"""

from __future__ import annotations

from .metrics import REGISTRY, Metric, unavailable


@REGISTRY.register("accessibility", group="accessibility")
def _accessibility(ctx: dict) -> "list[Metric]":
    out: list[Metric] = []
    timeline = ctx.get("timeline") or []

    # Photosensitivity: large luminance transitions per second (WCAG 2.3.1 spirit).
    if len(timeline) > 1:
        b = [float(p.get("brightness", 0.0)) for p in timeline]  # 0..100
        ts = [float(p.get("t", 0.0)) for p in timeline]
        flashes = sum(1 for i in range(1, len(b)) if abs(b[i] - b[i - 1]) >= 25.0)
        span = max(1e-6, ts[-1] - ts[0])
        rate = flashes / span
        worst = next(
            (round(ts[i], 2) for i in range(1, len(b)) if abs(b[i] - b[i - 1]) >= 25.0), 0.0
        )
        out.append(
            Metric("flashRate", "Flash rate (photosensitivity)", round(rate, 2), "flashes/s", (0, 30),
                   "luminance_delta", confidence=0.4, group="accessibility",
                   evidence=[{"t": worst}], severity=("high" if rate > 3 else "low"),
                   recommendation=("Exceeds 3 flashes/s — photosensitive-seizure risk" if rate > 3 else None))
        )
    else:
        out.append(unavailable("flashRate", "Flash rate (photosensitivity)", "luminance_delta", "accessibility", "No timeline"))

    # Caption reading speed (chars/sec) from transcript timing.
    tx = ctx.get("transcript") or []
    if tx:
        cps = []
        for s in tx:
            dur = max(0.1, float(s.get("end", 0.0)) - float(s.get("start", 0.0)))
            cps.append(len(s.get("text") or "") / dur)
        avg = sum(cps) / len(cps) if cps else 0.0
        out.append(
            Metric("captionReadingSpeed", "Caption reading speed", round(avg, 1), "chars/s", (0, 40),
                   "transcript_timing", confidence=0.5, group="accessibility",
                   severity=("medium" if avg > 20 else "low"),
                   recommendation=("Captions may be too fast — split long lines" if avg > 20 else None))
        )
    else:
        out.append(unavailable("captionReadingSpeed", "Caption reading speed", "transcript_timing", "accessibility", "No transcript"))

    out.append(unavailable("textContrastWcag", "Text contrast (WCAG)", "ocr_contrast", "accessibility", "Needs OCR"))
    out.append(unavailable("copyrightedMusic", "Copyrighted music", "fingerprint", "compliance", "Not measured"))
    out.append(unavailable("piiInFrame", "PII in frame", "detector", "compliance", "Not measured"))
    return out
