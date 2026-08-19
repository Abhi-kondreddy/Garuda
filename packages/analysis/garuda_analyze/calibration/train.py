"""Train calibration models (scikit-learn) from joined outcomes.

Fits median + 10th/90th-percentile quantile regressors for each outcome target
(so predictions carry confidence intervals) and a retention-curve regressor.
Persists `model.joblib` (estimators) + `model.json` (versioned metadata).

CLI:
    python -m garuda_analyze.calibration.train --data <dir> --reports <dir> --out <dir>
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path

import numpy as np

from .ingest import build_dataset, load_outcomes

MIN_SAMPLES = 8
MIN_RETENTION_POINTS = 20
TARGETS = ["avgViewDurationPct", "ctr"]


def _matrix(rows: "list[dict]", feature_names: "list[str]") -> np.ndarray:
    return np.array(
        [[r["features"].get(f, 0.0) for f in feature_names] for r in rows], dtype=float
    )


def train(data_dir, reports_dir, out_dir) -> dict:
    from sklearn.ensemble import GradientBoostingRegressor

    outcomes = load_outcomes(data_dir)
    rows = build_dataset(reports_dir, outcomes)
    if len(rows) < MIN_SAMPLES:
        raise RuntimeError(f"Need >= {MIN_SAMPLES} joined samples, got {len(rows)}")

    feature_names = sorted({k for r in rows for k in r["features"]})
    X = _matrix(rows, feature_names)

    targets: dict = {}
    for target in TARGETS:
        y = np.array([float(r["outcome"].get(target, np.nan)) for r in rows])
        mask = np.isfinite(y)
        if int(mask.sum()) < MIN_SAMPLES:
            continue
        Xt, yt = X[mask], y[mask]
        median = GradientBoostingRegressor(random_state=0).fit(Xt, yt)
        lo = GradientBoostingRegressor(loss="quantile", alpha=0.1, random_state=0).fit(Xt, yt)
        hi = GradientBoostingRegressor(loss="quantile", alpha=0.9, random_state=0).fit(Xt, yt)
        targets[target] = {"median": median, "lo": lo, "hi": hi}

    # Retention: one row per (video, tFrac).
    ret_X, ret_y = [], []
    for r in rows:
        for pt in r["outcome"].get("retention", []) or []:
            try:
                tf = float(pt["tFrac"])
                rp = float(pt["retentionPct"])
            except (KeyError, TypeError, ValueError):
                continue
            ret_X.append([r["features"].get(f, 0.0) for f in feature_names] + [tf])
            ret_y.append(rp)
    retention = None
    if len(ret_y) >= MIN_RETENTION_POINTS:
        retention = GradientBoostingRegressor(random_state=0).fit(np.array(ret_X), np.array(ret_y))

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    import joblib

    joblib.dump(
        {"feature_names": feature_names, "targets": targets, "retention": retention},
        out_dir / "model.joblib",
    )
    version = _dt.datetime.now(_dt.timezone.utc).strftime("cal-%Y%m%d-%H%M%S")
    meta = {
        "calibrationVersion": version,
        "trainedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "nSamples": len(rows),
        "features": feature_names,
        "targets": list(targets.keys()),
        "hasRetention": retention is not None,
    }
    (out_dir / "model.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Train Garuda calibration models")
    here = Path(__file__).resolve().parent
    ap.add_argument("--data", default=str(here / "data"))
    ap.add_argument("--reports", required=True, help="Directory of <id>/report.json")
    ap.add_argument("--out", default=str(here / "model"))
    args = ap.parse_args(argv)
    meta = train(args.data, args.reports, args.out)
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
