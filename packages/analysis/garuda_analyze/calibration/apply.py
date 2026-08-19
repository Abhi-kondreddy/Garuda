"""Apply trained calibration models to a report (predictions + intervals).

Falls back cleanly (returns False, leaves the heuristic retention curve) when no
model is present or scikit-learn/joblib are unavailable.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .ingest import feature_vector

_DEFAULT_MODEL_DIR = Path(__file__).resolve().parent / "model"


class Calibrator:
    def __init__(self, bundle: dict, meta: dict) -> None:
        self.feature_names = bundle.get("feature_names", [])
        self.targets = bundle.get("targets", {})
        self.retention = bundle.get("retention")
        self.version = meta.get("calibrationVersion", "cal-unknown")

    def _x(self, feats: dict) -> "list[float]":
        return [float(feats.get(f, 0.0)) for f in self.feature_names]

    def predict(self, report: dict) -> dict:
        feats = feature_vector(report)
        x = np.array([self._x(feats)])
        out: dict = {"calibrationVersion": self.version, "method": "calibrated", "targets": {}}
        for tgt, mset in self.targets.items():
            try:
                out["targets"][tgt] = {
                    "value": round(float(mset["median"].predict(x)[0]), 2),
                    "lo": round(float(mset["lo"].predict(x)[0]), 2),
                    "hi": round(float(mset["hi"].predict(x)[0]), 2),
                }
            except Exception:
                continue
        if self.retention is not None:
            curve = []
            for k in range(0, 101, 5):
                tf = k / 100.0
                xr = np.array([self._x(feats) + [tf]])
                try:
                    curve.append({"tFrac": tf, "retentionPct": round(float(self.retention.predict(xr)[0]), 1)})
                except Exception:
                    break
            if curve:
                out["retentionCurve"] = curve
        return out

    def what_if(self, report: dict, deltas: "dict[str, float]") -> dict:
        """Predict outcome change if given features shift by deltas (feature id -> +/-)."""
        base = self.predict(report)
        feats = feature_vector(report)
        for k, dv in deltas.items():
            feats[k] = feats.get(k, 0.0) + dv
        x = np.array([self._x(feats)])
        changed: dict = {}
        for tgt, mset in self.targets.items():
            try:
                new = float(mset["median"].predict(x)[0])
                cur = base["targets"].get(tgt, {}).get("value", new)
                changed[tgt] = {"value": round(new, 2), "delta": round(new - cur, 2)}
            except Exception:
                continue
        return {"deltas": deltas, "predicted": changed}


def load_calibrator(model_dir=_DEFAULT_MODEL_DIR) -> "Calibrator | None":
    model_dir = Path(model_dir)
    try:
        import joblib

        bundle = joblib.load(model_dir / "model.joblib")
        meta = json.loads((model_dir / "model.json").read_text(encoding="utf-8"))
        return Calibrator(bundle, meta)
    except Exception:
        return None


def apply_calibration(report: dict, model_dir=_DEFAULT_MODEL_DIR) -> bool:
    cal = load_calibrator(model_dir)
    if cal is None:
        return False
    try:
        preds = cal.predict(report)
        report["predictions"] = preds
        # Upgrade the retention curve to the calibrated one when available.
        if preds.get("retentionCurve"):
            report["retentionCurveCalibrated"] = preds["retentionCurve"]
        return True
    except Exception:
        return False
