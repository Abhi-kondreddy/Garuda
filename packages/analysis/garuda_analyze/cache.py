"""Content-hash helpers for incremental / cached analysis.

`content_hash` is cheap (size + head/tail bytes) and stamped into the report so
the app can detect a re-analysis of the exact same file. Full segment-level
incremental recompute is a future extension keyed off this hash.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_CHUNK = 65536


def content_hash(path) -> "str | None":
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        return None
    h = hashlib.sha256()
    h.update(str(st.st_size).encode())
    try:
        with open(p, "rb") as f:
            h.update(f.read(_CHUNK))
            if st.st_size > _CHUNK * 2:
                f.seek(-_CHUNK, 2)
                h.update(f.read(_CHUNK))
    except OSError:
        return None
    return h.hexdigest()[:24]


def find_cached_report(reports_root, chash: "str | None") -> "str | None":
    if not chash:
        return None
    root = Path(reports_root)
    if not root.exists():
        return None
    for sub in sorted(root.iterdir()):
        rp = sub / "report.json"
        if not rp.is_file():
            continue
        try:
            if json.loads(rp.read_text(encoding="utf-8")).get("contentHash") == chash:
                return str(rp)
        except Exception:
            continue
    return None
