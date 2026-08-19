"""Ingest labeled outcomes and join them to report feature vectors.

Outcome data contract (place under calibration/data/ as .json or .jsonl):

    {
      "reportId": "<report folder name>",        # or "sourceName"
      "youtubeVideoId": "abc123",                  # optional
      "avgViewDurationPct": 44.5,                  # 0..100
      "ctr": 6.1,                                  # click-through %, 0..100
      "views": 12000, "impressions": 90000,        # optional
      "retention": [ {"tFrac": 0.0, "retentionPct": 100}, {"tFrac": 0.05, "retentionPct": 78}, ... ]
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator


def load_outcomes(data_dir) -> "list[dict]":
    data_dir = Path(data_dir)
    outcomes: list[dict] = []
    if not data_dir.exists():
        return outcomes
    for p in sorted(data_dir.glob("*")):
        if p.suffix.lower() == ".jsonl":
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        outcomes.append(json.loads(line))
                    except Exception:
                        continue
        elif p.suffix.lower() == ".json":
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            outcomes.extend(data if isinstance(data, list) else [data])
    return outcomes


def iter_reports(reports_dir) -> "Iterator[tuple[str, dict]]":
    reports_dir = Path(reports_dir)
    if not reports_dir.exists():
        return
    for sub in sorted(reports_dir.iterdir()):
        rp = sub / "report.json"
        if rp.is_file():
            try:
                yield sub.name, json.loads(rp.read_text(encoding="utf-8"))
            except Exception:
                continue


def feature_vector(report: dict) -> "dict[str, float]":
    """Flatten a report into numeric features for the calibrator."""
    feats: dict[str, float] = {}
    for mid, mc in (report.get("metrics") or {}).items():
        v = mc.get("value")
        if isinstance(v, bool):
            feats[f"m_{mid}"] = 1.0 if v else 0.0
        elif isinstance(v, (int, float)) and float(mc.get("confidence", 0.0)) > 0.0:
            feats[f"m_{mid}"] = float(v)
    feats["durationSec"] = float(report.get("durationSec") or 0.0)
    scores = report.get("scores") or {}
    for k, v in scores.items():
        try:
            feats[f"s_{k}"] = float(v)
        except (TypeError, ValueError):
            continue
    return feats


def build_dataset(reports_dir, outcomes: "list[dict]") -> "list[dict]":
    by_key: dict = {}
    for o in outcomes:
        for key in (o.get("reportId"), o.get("sourceName"), o.get("youtubeVideoId")):
            if key:
                by_key[str(key)] = o
    rows: list[dict] = []
    for rid, report in iter_reports(reports_dir):
        o = by_key.get(rid) or by_key.get(report.get("sourceName", ""))
        if not o:
            continue
        rows.append({"id": rid, "features": feature_vector(report), "outcome": o})
    return rows
