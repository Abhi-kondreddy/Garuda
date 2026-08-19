"""Pluggable vision detectors with graceful fallbacks.

- ``FaceDetector`` prefers the OpenCV YuNet DNN model (more robust than Haar,
  and it returns boxes we reuse for thumbnail crops / reframing) and falls back
  to the classic Haar cascade when the YuNet ONNX file isn't bundled.
- ``detect_scenes`` uses PySceneDetect's content detector when installed, else
  returns ``None`` so the caller keeps its lightweight histogram cuts.
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2

_YUNET_ENV = "GARUDA_YUNET_MODEL"
_YUNET_NAMES = (
    "face_detection_yunet_2023mar.onnx",
    "face_detection_yunet.onnx",
)


def _find_yunet_model() -> str | None:
    env = os.environ.get(_YUNET_ENV)
    if env and Path(env).exists():
        return env
    here = Path(__file__).resolve().parent
    roots = [here / "models", here.parent / "models", here.parent.parent / "models"]
    for root in roots:
        for name in _YUNET_NAMES:
            p = root / name
            if p.exists():
                return str(p)
    return None


class FaceDetector:
    """Detect faces in a BGR frame, returning pixel boxes ``(x, y, w, h)``."""

    def __init__(self) -> None:
        self.backend = "none"
        self._yunet = None
        self._cascade = None

        model = _find_yunet_model()
        creator = getattr(cv2, "FaceDetectorYN_create", None)
        if model and callable(creator):
            try:
                self._yunet = creator(model, "", (320, 320), 0.7, 0.3, 5000)
                self.backend = "yunet"
            except Exception:
                self._yunet = None

        if self._yunet is None:
            try:
                casc = cv2.CascadeClassifier(
                    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                )
                if not casc.empty():
                    self._cascade = casc
                    self.backend = "haar"
            except Exception:
                self._cascade = None

    @property
    def available(self) -> bool:
        return self.backend != "none"

    def detect(self, frame_bgr) -> list[tuple[int, int, int, int]]:
        if self._yunet is not None:
            h, w = frame_bgr.shape[:2]
            try:
                self._yunet.setInputSize((int(w), int(h)))
                _, faces = self._yunet.detect(frame_bgr)
            except cv2.error:
                return []
            out: list[tuple[int, int, int, int]] = []
            if faces is not None:
                for f in faces:
                    x, y, bw, bh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
                    if bw > 0 and bh > 0:
                        out.append((max(0, x), max(0, y), bw, bh))
            return out
        if self._cascade is not None:
            g = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            try:
                faces = self._cascade.detectMultiScale(
                    g, scaleFactor=1.15, minNeighbors=4, minSize=(24, 24)
                )
            except cv2.error:
                return []
            return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]
        return []


def detect_scenes(video_path) -> "list[float] | None":
    """Return scene-cut times (seconds) via PySceneDetect, or None if it's
    unavailable/failed so the caller can fall back to histogram cuts."""
    try:
        from scenedetect import detect, ContentDetector
    except Exception:
        return None
    try:
        scenes = detect(str(video_path), ContentDetector())
    except Exception:
        return None
    cuts: list[float] = []
    for i, (start, _end) in enumerate(scenes):
        if i == 0:
            continue  # first scene starts at 0; cuts are the boundaries after it
        try:
            cuts.append(float(start.get_seconds()))
        except Exception:
            continue
    return cuts
