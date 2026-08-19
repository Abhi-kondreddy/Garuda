from __future__ import annotations

import json
import math
from typing import Any


def sanitize(obj: Any) -> Any:
    """Recursively coerce a value into something JSON-safe for the Electron side.

    JavaScript's ``JSON.parse`` rejects the ``NaN`` / ``Infinity`` tokens that
    Python's ``json.dumps`` emits by default, which would silently break the
    NDJSON progress stream and the report load. We replace every non-finite
    float with ``None`` and unwrap numpy scalars to native Python types.
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, int):
        return obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    if isinstance(obj, (str, bytes)) or obj is None:
        return obj
    # numpy scalars / 0-d arrays expose .item()
    item = getattr(obj, "item", None)
    if callable(item):
        try:
            return sanitize(item())
        except Exception:
            return None
    return obj


def dumps(obj: Any, *, indent: int | None = None) -> str:
    """``json.dumps`` that never emits NaN/Infinity and always round-trips in JS."""
    return json.dumps(sanitize(obj), ensure_ascii=False, allow_nan=False, indent=indent)
