from __future__ import annotations

import math
import struct
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from garuda_analyze.scoring import build_report  # noqa: E402
from garuda_analyze.audio_features import analyze_audio  # noqa: E402
from garuda_analyze.validation import validate_report, repair_report  # noqa: E402

_REQUIRED_METRIC_KEYS = {
    "id", "label", "value", "unit", "range", "method", "version",
    "confidence", "lowConfidence", "evidence", "severity", "recommendation", "group",
}
_EXPECTED_GROUPS = {"core", "visual", "audio", "language", "safety", "technical", "ml", "accessibility", "compliance"}


def _sine(path: Path, sec: float = 2.0, sr: int = 16000, f: float = 440.0) -> None:
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        for i in range(int(sec * sr)):
            wf.writeframes(struct.pack("<h", int(0.4 * 32767 * math.sin(2 * math.pi * f * i / sr))))


def _rich_report():
    n = 14
    fd = {
        "brightness": [120.0] * n, "contrast": [40.0] * n, "motion": [4.0 + (i % 5) for i in range(n)],
        "hue_means": [20.0] * n, "sat_means": [80.0] * n, "sharpness": [90.0] * n,
        "rgb_means": [[130.0, 120.0, 90.0]] * n, "shadow_clip": [0.02] * n, "highlight_clip": [0.01] * n,
        "scene_cuts": [1.0, 4.0], "timeline_bins": [{"t": i * 0.5, "motion": 4.0, "brightness": 120, "contrast": 40} for i in range(n)],
        "palette": [], "on_cam_presence": 0.6, "face_boxes": [{"t": 1.0, "cx": 0.5, "cy": 0.4, "w": 0.2, "h": 0.3}],
        "face_backend": "haar", "fps": 30, "duration": 7,
    }
    tx = [{"start": 0.5, "end": 3.0, "text": "um so here is how to fix your hook and win", "language": "en", "confidence": 0.8}]
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        _sine(wav)
        audio = analyze_audio(wav, 7.0)
    return build_report(
        video_path=Path("x.mp4"),
        meta={"duration": 7, "fps": 30, "width": 1280, "height": 720, "bit_rate": 6_000_000},
        frame_data=fd, audio_data=audio, transcript=tx,
    )


def test_metric_contracts_shape():
    report = _rich_report()
    metrics = report.get("metrics") or {}
    assert len(metrics) >= 40, f"expected a rich catalog, got {len(metrics)}"
    groups = set()
    for mid, mc in metrics.items():
        missing = _REQUIRED_METRIC_KEYS - set(mc.keys())
        assert not missing, f"{mid} missing keys {missing}"
        assert 0.0 <= mc["confidence"] <= 1.0
        groups.add(mc["group"])
        rng, val = mc["range"], mc["value"]
        if rng and isinstance(val, (int, float)) and not isinstance(val, bool):
            assert rng[0] - 1e-6 <= val <= rng[1] + 1e-6, f"{mid} value {val} outside {rng}"
    # broad coverage across domains
    assert {"core", "visual", "audio", "language", "technical", "accessibility"} <= groups


def test_report_has_foundation_blocks():
    report = _rich_report()
    assert report["provenance"]["configHash"]
    assert report["provenance"]["seed"] is not None
    diags = report["diagnostics"]
    assert diags["pluginModulesMissing"] == {} or isinstance(diags["pluginModulesMissing"], dict)
    assert len(diags["pluginModulesLoaded"]) >= 9
    assert len(report["dropRiskTimeline"]) == len(report["timeline"])
    assert isinstance(report["topDrivers"], list)


def test_full_report_schema_valid():
    report = repair_report(_rich_report())
    ok, errors = validate_report(report)
    assert ok, f"schema invalid: {errors[:5]}"


if __name__ == "__main__":
    test_metric_contracts_shape()
    test_report_has_foundation_blocks()
    test_full_report_schema_valid()
    print("ok")
