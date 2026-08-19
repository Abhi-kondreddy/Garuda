"""Import side-effect module: pulls in every parameter plugin so its
`@REGISTRY.register(...)` decorators run. `scoring.build_report` imports this
once before invoking the registry.

Each import is guarded so a module with a missing optional dependency never
prevents the others (and the rest of the report) from loading.
"""

from __future__ import annotations

import importlib

# Order-independent; every module registers into the shared REGISTRY.
_PLUGIN_MODULES = [
    "vision_exposure",
    "vision_quality",
    "vision_composition",
    "audio_quality2",
    "nlp",
    "qc",
    "ml_vision",
    "nlp_ml",
    "accessibility",
]

loaded: list[str] = []
missing: dict[str, str] = {}

for _name in _PLUGIN_MODULES:
    try:
        importlib.import_module(f".{_name}", __package__)
        loaded.append(_name)
    except Exception as exc:  # noqa: BLE001 — a plugin module is optional
        missing[_name] = f"{type(exc).__name__}: {exc}"
