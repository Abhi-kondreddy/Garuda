"""Calibration engine: turn heuristic metrics into outcome predictions.

Trains on real audience outcomes (retention/CTR) you export and drops under
`calibration/data/`, fits scikit-learn regressors with confidence intervals,
and applies calibrated predictions to new reports. Degrades to the heuristic
retention curve when no trained model is present.
"""

from __future__ import annotations

DEFAULT_DATA_DIR = "data"
DEFAULT_MODEL_DIR = "model"
