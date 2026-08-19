"""Report schema validation + repair + atomic write.

`validate_report` uses jsonschema when available (falling back to a minimal
structural check). `repair_report` clamps out-of-range scores and drops
non-finite numbers so we always emit a valid, JS-safe report. `write_report`
writes atomically (tmp -> rename) so a crash never leaves a half-written file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import jsonio

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "report.schema.json"
_REQUIRED_TOP = [
    "version",
    "createdAt",
    "sourcePath",
    "sourceName",
    "durationSec",
    "fps",
    "scores",
    "visual",
    "audio",
    "timeline",
    "transcript",
]


def _load_schema() -> "dict | None":
    try:
        return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def validate_report(report: dict) -> "tuple[bool, list[str]]":
    """Return (ok, errors). Never raises."""
    schema = _load_schema()
    try:
        import jsonschema

        if schema is not None:
            validator = jsonschema.Draft7Validator(schema)
            errors = [f"{'/'.join(map(str, e.path))}: {e.message}" for e in validator.iter_errors(report)]
            return (len(errors) == 0, errors[:50])
    except Exception:
        pass
    # Fallback: minimal structural check.
    missing = [k for k in _REQUIRED_TOP if k not in report]
    return (len(missing) == 0, [f"missing key: {k}" for k in missing])


def repair_report(report: dict) -> dict:
    """Clamp scores to 0..100 and sanitize non-finite numbers (best-effort)."""
    scores = report.get("scores")
    if isinstance(scores, dict):
        for k, v in list(scores.items()):
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            scores[k] = max(0.0, min(100.0, fv))
    # jsonio.sanitize turns NaN/Inf -> None recursively.
    return jsonio.sanitize(report)


def write_report(report: dict, path) -> "tuple[bool, list[str]]":
    """Validate + repair, then write atomically. Returns (valid, errors)."""
    report = repair_report(report)
    ok, errors = validate_report(report)
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(jsonio.dumps(report, indent=2), encoding="utf-8")
    os.replace(tmp, path)  # atomic on same filesystem
    return ok, errors
