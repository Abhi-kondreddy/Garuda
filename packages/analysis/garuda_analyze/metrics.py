"""Metric contract + plugin registry — the backbone of the analysis engine.

Every parameter the engine reports is a `Metric`: a value plus the metadata
needed to trust and act on it (unit, range, method, model version, confidence,
the timestamps that evidence it, a severity, and a recommendation). New
parameters register a compute function against the `MetricRegistry`; the engine
runs them over a shared context and never lets one metric's failure abort the
run.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

# Metrics below this confidence are surfaced but flagged so the UI can grey them.
CONFIDENCE_FLOOR = 0.35


@dataclass
class Metric:
    id: str
    label: str
    value: Any
    unit: str = ""
    range: "tuple[float, float] | None" = None
    method: str = ""
    version: str = "1"
    confidence: float = 1.0
    evidence: list = field(default_factory=list)  # [{t} or {t, tEnd}]
    severity: "str | None" = None  # low | medium | high | None
    recommendation: "str | None" = None
    group: str = ""

    def to_dict(self) -> dict:
        conf = float(self.confidence)
        if not math.isfinite(conf):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        val = self.value
        if isinstance(val, float) and not math.isfinite(val):
            val = None
        return {
            "id": self.id,
            "label": self.label,
            "value": val,
            "unit": self.unit,
            "range": list(self.range) if self.range else None,
            "method": self.method,
            "version": self.version,
            "confidence": round(conf, 3),
            "lowConfidence": conf < CONFIDENCE_FLOOR,
            "evidence": self.evidence[:20],
            "severity": self.severity,
            "recommendation": self.recommendation,
            "group": self.group,
        }


def unavailable(mid: str, label: str, method: str, group: str, reason: str) -> Metric:
    """A metric whose backend (model/dep/data) is absent — present in the report
    with zero confidence so consumers can show it as 'not measured'."""
    return Metric(
        id=mid,
        label=label,
        value=None,
        method=method,
        confidence=0.0,
        recommendation=reason,
        group=group,
    )


ComputeFn = Callable[[dict], "list[Metric] | Metric | None"]


@dataclass
class _Plugin:
    name: str
    fn: ComputeFn
    group: str
    deps: "list[str]"


class MetricRegistry:
    def __init__(self) -> None:
        self._plugins: list[_Plugin] = []

    def register(self, name: str, *, group: str = "", deps: "list[str] | None" = None):
        def deco(fn: ComputeFn) -> ComputeFn:
            self._plugins.append(_Plugin(name=name, fn=fn, group=group, deps=deps or []))
            return fn

        return deco

    def run(self, context: dict) -> "tuple[dict[str, dict], list[dict]]":
        """Run every plugin over the context. Returns (metrics_by_id, diagnostics).

        A plugin raising an exception is recorded in diagnostics and skipped —
        it can never take down the report.
        """
        out: dict[str, dict] = {}
        diags: list[dict] = []
        for p in self._plugins:
            try:
                result = p.fn(context)
            except Exception as exc:  # noqa: BLE001 — isolate plugin failures
                diags.append({"plugin": p.name, "status": "error", "detail": f"{type(exc).__name__}: {exc}"})
                continue
            if result is None:
                continue
            metrics = result if isinstance(result, list) else [result]
            for m in metrics:
                if not isinstance(m, Metric):
                    continue
                if not m.group:
                    m.group = p.group
                out[m.id] = m.to_dict()
        return out, diags


# Global registry; parameter modules import and decorate against this.
REGISTRY = MetricRegistry()
