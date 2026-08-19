"""Measurement layer (objective signals) — facade over the analyzers.

Garuda's engine is split into two layers:

* **measurement** (this module's re-exports): objective, reproducible signals
  extracted directly from the media — frames, audio features, ASR, face/scene
  detection, and derived series (retention, framing, chapters, keywords).
* **coaching** (`coaching.py` / `deep_analysis.py`): opinionated, heuristic
  advice built *on top of* the measurements. These carry `SCORING_VERSION` and
  are expected to evolve independently.

`scoring.build_report` fuses the measurement layer into scores and then attaches
the coaching layer. Import objective analyzers from here to keep that boundary
explicit.
"""

from __future__ import annotations

from .audio_features import analyze_audio
from .detectors import FaceDetector, detect_scenes
from .frames import analyze_frames
from .framing import build_framing
from .retention import build_retention_curve
from .text_analysis import build_chapters, build_keywords

__all__ = [
    "analyze_frames",
    "analyze_audio",
    "FaceDetector",
    "detect_scenes",
    "build_framing",
    "build_retention_curve",
    "build_chapters",
    "build_keywords",
]
