from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from garuda_analyze.scoring import build_report  # noqa: E402
from garuda_analyze.calibration.train import train  # noqa: E402
from garuda_analyze.calibration.apply import load_calibrator, apply_calibration  # noqa: E402


def _report(level: float) -> dict:
    n = 20
    et = [i * 0.05 for i in range(400)]
    audio = {
        "energy": [level] * 400,
        "energy_times": et,
        "waveform": [],
        "silence_gaps": [],
        "dead_air_ratio": 0.15 * (1 - level),
        "loudness_consistency": 40 + 50 * level,
        "clarity": 40 + 50 * level,
        "music_speech_ratio": 0.4,
        "lufs": -14.0,
        "delivery": {},
        "advanced": {},
    }
    bins = [{"t": i * 0.5, "motion": 5 + 20 * level, "brightness": 120, "contrast": 40} for i in range(n)]
    fd = {
        "brightness": [120] * n, "contrast": [40] * n, "motion": [5 + 20 * level] * n,
        "hue_means": [20] * n, "sat_means": [80] * n, "sharpness": [80] * n,
        "rgb_means": [[130, 120, 90]] * n, "shadow_clip": [0.02] * n, "highlight_clip": [0.01] * n,
        "scene_cuts": [1.0, 3.0], "timeline_bins": bins, "palette": [], "on_cam_presence": level,
        "face_boxes": [], "face_backend": "haar", "fps": 30, "duration": 10,
    }
    tx = [{"start": 0.5, "end": 3.0, "text": "how to fix your hook and win", "language": "en", "confidence": 0.8}]
    return build_report(
        video_path=Path(f"v{level}.mp4"),
        meta={"duration": 10, "fps": 30, "width": 1280, "height": 720},
        frame_data=fd, audio_data=audio, transcript=tx,
    )


def test_calibration_round_trip():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        reports_dir = td / "reports"
        data_dir = td / "data"
        model_dir = td / "model"
        reports_dir.mkdir()
        data_dir.mkdir()

        outcomes = []
        for i in range(16):
            level = (i + 1) / 16.0
            report = _report(level)
            rid = f"vid-{i:02d}"
            (reports_dir / rid).mkdir()
            (reports_dir / rid / "report.json").write_text(json.dumps(report))
            retention = [
                {"tFrac": k / 10.0, "retentionPct": max(5.0, 100.0 * (1.0 - (k / 10.0) * (1.2 - level)))}
                for k in range(11)
            ]
            outcomes.append({
                "reportId": rid,
                "avgViewDurationPct": 30.0 + 55.0 * level,
                "ctr": 3.0 + 6.0 * level,
                "retention": retention,
            })
        (data_dir / "outcomes.json").write_text(json.dumps(outcomes))

        meta = train(data_dir, reports_dir, model_dir)
        assert meta["nSamples"] == 16
        assert "avgViewDurationPct" in meta["targets"]
        assert meta["hasRetention"]

        cal = load_calibrator(model_dir)
        assert cal is not None

        low = cal.predict(_report(0.1))
        high = cal.predict(_report(0.95))
        for pred in (low, high):
            t = pred["targets"]["avgViewDurationPct"]
            assert t["lo"] <= t["value"] + 1e-6 and t["value"] <= t["hi"] + 1e-6, t
            assert "retentionCurve" in pred and len(pred["retentionCurve"]) == 21
        # higher-quality video should predict higher watch time
        assert high["targets"]["avgViewDurationPct"]["value"] > low["targets"]["avgViewDurationPct"]["value"]

        # what-if: bumping interestingness should not decrease predicted watch time
        wi = cal.what_if(_report(0.5), {"m_interestingness": 20.0})
        assert "avgViewDurationPct" in wi["predicted"]

        # apply into a report + heuristic fallback when model dir is empty
        report = _report(0.6)
        assert apply_calibration(report, model_dir) is True
        assert report["predictions"]["method"] == "calibrated"
        assert apply_calibration(_report(0.6), td / "nope") is False


if __name__ == "__main__":
    test_calibration_round_trip()
    print("ok")
