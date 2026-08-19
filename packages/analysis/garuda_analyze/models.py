"""Bundled-model manager: resolve, checksum-verify, and lazily load ONNX models.

Models live under ``packages/analysis/models/`` with a ``models.json`` manifest
mapping name -> {file, sha256, version, kind}. Everything degrades gracefully:
a missing model or missing onnxruntime yields ``None`` so ML metrics report as
``unavailable`` rather than failing the run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_MODELS_DIR = Path(__file__).resolve().parent / "models"
_MANIFEST = _MODELS_DIR / "models.json"


class ModelManager:
    def __init__(self, models_dir: Path = _MODELS_DIR) -> None:
        self.dir = Path(models_dir)
        self.manifest = self._load_manifest()
        self._sessions: dict = {}

    def _load_manifest(self) -> dict:
        try:
            return json.loads(_MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def path(self, name: str) -> "Path | None":
        entry = self.manifest.get(name) or {}
        fname = entry.get("file") or f"{name}.onnx"
        p = self.dir / fname
        return p if p.exists() else None

    def verify(self, name: str) -> bool:
        p = self.path(name)
        if p is None:
            return False
        sha = (self.manifest.get(name) or {}).get("sha256")
        if not sha:
            return True  # unpinned model — accept presence
        try:
            return hashlib.sha256(p.read_bytes()).hexdigest() == sha
        except Exception:
            return False

    def onnx_session(self, name: str):
        if name in self._sessions:
            return self._sessions[name]
        sess = None
        p = self.path(name)
        if p is not None and self.verify(name):
            try:
                import onnxruntime as ort

                sess = ort.InferenceSession(str(p), providers=["CPUExecutionProvider"])
            except Exception:
                sess = None
        self._sessions[name] = sess
        return sess

    def available(self, name: str) -> bool:
        return self.onnx_session(name) is not None

    def versions(self) -> dict:
        return {
            k: (v.get("version") or "?")
            for k, v in self.manifest.items()
            if self.path(k) is not None
        }


MODELS = ModelManager()
