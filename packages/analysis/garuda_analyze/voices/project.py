from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_FX = {
    "gainDb": 0.0,
    "bassDb": 0.0,
    "clarityDb": 0.0,
    "presenceDb": 0.0,
    "compress": 0.0,
    "deess": 0.0,
    "gate": 0.0,
    "mlEnhance": False,
}


def voices_dir(report_dir: Path) -> Path:
    d = report_dir / "voices"
    d.mkdir(parents=True, exist_ok=True)
    return d


def stems_dir(report_dir: Path) -> Path:
    d = voices_dir(report_dir) / "stems"
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_path(report_dir: Path) -> Path:
    return voices_dir(report_dir) / "project.json"


def speakers_path(report_dir: Path) -> Path:
    return voices_dir(report_dir) / "speakers.json"


def load_project(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    fx = data.get("fx") or {}
    # normalize missing keys
    for sid, params in list(fx.items()):
        fx[sid] = {**DEFAULT_FX, **(params or {})}
    data["fx"] = fx
    return data


def save_project(path: Path, project: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")


def default_project(report_dir: Path, speaker_ids: list[str]) -> dict[str, Any]:
    return {
        "version": 1,
        "reportDir": str(report_dir),
        "speakersPath": str(speakers_path(report_dir)),
        "previewMixPath": None,
        "fx": {sid: dict(DEFAULT_FX) for sid in speaker_ids},
    }
