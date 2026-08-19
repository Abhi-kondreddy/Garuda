"""Provenance block: everything needed to reproduce / audit a report."""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys

from . import config
from .seeding import DEFAULT_SEED


def _config_hash() -> str:
    """Stable hash of the scoring tunables so a config change is auditable."""
    items = sorted(
        (k, repr(v)) for k, v in vars(config).items() if k.isupper() and not k.startswith("_")
    )
    blob = "|".join(f"{k}={v}" for k, v in items)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _ffmpeg_version(binary: str) -> "str | None":
    try:
        proc = subprocess.run(
            [binary, "-version"],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=10,
        )
        first = (proc.stdout or "").splitlines()[:1]
        return first[0].strip() if first else None
    except Exception:
        return None


def build_provenance(
    *,
    ffmpeg: "str | None" = None,
    ffprobe: "str | None" = None,
    seed: int = DEFAULT_SEED,
    model_versions: "dict | None" = None,
) -> dict:
    return {
        "scoringVersion": config.SCORING_VERSION,
        "engine": "garuda-analyze",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "configHash": _config_hash(),
        "seed": seed,
        "ffmpeg": _ffmpeg_version(ffmpeg) if ffmpeg else None,
        "ffprobe": _ffmpeg_version(ffprobe) if ffprobe else None,
        "models": model_versions or {},
    }
