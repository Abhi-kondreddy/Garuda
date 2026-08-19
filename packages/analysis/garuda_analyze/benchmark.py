"""Percentile every numeric metric against the creator's own history."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np


def build_benchmarks(report: dict, reports_root, max_history: int = 300) -> dict:
    root = Path(reports_root)
    if not root.exists():
        return {}
    hist: "defaultdict[str, list[float]]" = defaultdict(list)
    count = 0
    for sub in sorted(root.iterdir()):
        rp = sub / "report.json"
        if not rp.is_file():
            continue
        try:
            other = json.loads(rp.read_text(encoding="utf-8"))
        except Exception:
            continue
        count += 1
        if count > max_history:
            break
        for mid, mc in (other.get("metrics") or {}).items():
            v = mc.get("value")
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                hist[mid].append(float(v))

    out: dict = {}
    for mid, mc in (report.get("metrics") or {}).items():
        v = mc.get("value")
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        vals = hist.get(mid) or []
        if len(vals) >= 3:
            arr = np.asarray(vals, dtype=float)
            pct = float(np.mean(arr <= v) * 100.0)
            out[mid] = {"percentile": round(pct, 1), "cohortN": len(vals)}
    return out
