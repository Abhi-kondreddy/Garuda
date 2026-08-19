"""ML vision parameters (aesthetics/NIMA, shot-type, emotion, object tags).

Activates when the corresponding ONNX model is bundled and onnxruntime is
installed; otherwise every metric reports as ``unavailable`` (never fails).
"""

from __future__ import annotations

import numpy as np

from .metrics import REGISTRY, Metric, unavailable
from .models import MODELS
from .util import clamp


def _sample_frames(path, timestamps, size=(224, 224), max_n: int = 5):
    try:
        import cv2
    except Exception:
        return []
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return []
    frames = []
    try:
        for t in timestamps[:max_n]:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
            ok, f = cap.read()
            if ok and f is not None:
                frames.append(cv2.resize(f, size))
    finally:
        cap.release()
    return frames


@REGISTRY.register("ml_vision", group="ml")
def _ml_vision(ctx: dict) -> "list[Metric]":
    out: list[Metric] = []
    report = ctx.get("report") or {}

    sess = MODELS.onnx_session("aesthetic")
    if sess is None:
        out.append(unavailable("aesthetics", "Aesthetic score", "nima_onnx", "ml", "Model not bundled"))
    else:
        src = report.get("sourcePath")
        ts = [float(h["t"]) for h in (report.get("highlights") or [])] or [
            float(report.get("durationSec", 0.0)) / 2.0
        ]
        frames = _sample_frames(src, ts)
        scores: list[float] = []
        if frames:
            inp = sess.get_inputs()[0].name
            for f in frames:
                x = (f[:, :, ::-1].astype("float32") / 255.0).transpose(2, 0, 1)[None]
                try:
                    y = np.asarray(sess.run(None, {inp: x})[0]).ravel()
                    if y.size >= 10:
                        dist = y[:10]
                        scores.append(float(np.dot(dist, np.arange(1, 11)) / max(dist.sum(), 1e-6)))
                    elif y.size:
                        scores.append(float(y[0]))
                except Exception:
                    continue
        if scores:
            out.append(
                Metric("aesthetics", "Aesthetic score", round(clamp(float(np.mean(scores)) * 10.0), 1),
                       "points", (0, 100), "nima_onnx", confidence=0.7, group="ml")
            )
        else:
            out.append(unavailable("aesthetics", "Aesthetic score", "nima_onnx", "ml", "Inference unavailable"))

    for name, mid, label, method in (
        ("shottype", "shotType", "Shot type", "cnn"),
        ("emotion", "emotionEnergy", "On-cam emotion energy", "fer"),
        ("objecttags", "objectTags", "Object / scene tags", "detector"),
    ):
        if not MODELS.available(name):
            out.append(unavailable(mid, label, method, "ml", "Model not bundled"))
    out.append(unavailable("thumbnailability", "Thumbnail-ability", "cnn", "ml", "Model not bundled"))
    return out
