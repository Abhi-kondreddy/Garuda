from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from garuda_analyze import jsonio  # noqa: E402
from garuda_analyze.captions import to_srt, to_vtt  # noqa: E402
from garuda_analyze.framing import build_framing  # noqa: E402
from garuda_analyze.pipeline import _parse_float, _parse_fps  # noqa: E402
from garuda_analyze.retention import build_retention_curve  # noqa: E402
from garuda_analyze.scoring import build_report  # noqa: E402
from garuda_analyze.audio_features import analyze_audio  # noqa: E402
from garuda_analyze.text_analysis import build_chapters, build_keywords  # noqa: E402

REQUIRED_TOP = {
    "version",
    "scoringVersion",
    "createdAt",
    "sourcePath",
    "sourceName",
    "durationSec",
    "fps",
    "width",
    "height",
    "scores",
    "visual",
    "audio",
    "timeline",
    "transcript",
    "riskZones",
    "highlights",
    "palette",
    "chapters",
    "keywords",
    "retentionCurve",
    "framing",
    "notes",
}


def _validate_report(report: dict) -> None:
    """Lightweight report schema validation (shape + score ranges + JSON-safe)."""
    missing = REQUIRED_TOP - set(report.keys())
    assert not missing, f"missing report keys: {missing}"
    for k in ("hook", "interestingness", "colorEvenness", "visualQuality", "audioQuality", "overall"):
        v = report["scores"][k]
        assert isinstance(v, (int, float)) and 0 <= v <= 100, f"score {k} out of range: {v}"
    serialized = jsonio.dumps(report)
    assert "NaN" not in serialized and "Infinity" not in serialized
    json.loads(serialized)  # must round-trip in a JS-compatible parser


def _frame_data(duration: float, bins: list[dict]) -> dict:
    return {
        "brightness": [b["brightness"] for b in bins],
        "contrast": [b["contrast"] for b in bins],
        "motion": [b["motion"] for b in bins],
        "hue_means": [20.0] * len(bins),
        "sat_means": [80.0] * len(bins),
        "scene_cuts": [],
        "timeline_bins": bins,
        "palette": [],
        "on_cam_presence": 0.0,
        "face_boxes": [],
        "fps": 30,
        "duration": duration,
    }


def test_no_audio_no_transcript():
    bins = [{"t": i * 0.5, "motion": 2.0, "brightness": 120.0, "contrast": 40.0} for i in range(10)]
    audio = analyze_audio(None, 5.0)
    report = build_report(
        video_path=Path("x.mp4"),
        meta={"duration": 5.0, "fps": 30, "width": 640, "height": 360},
        frame_data=_frame_data(5.0, bins),
        audio_data=audio,
        transcript=[],
    )
    _validate_report(report)
    assert report["audio"]["englishPercent"] == 0
    assert report["scoringVersion"]


def test_zero_duration_empty_frames():
    audio = analyze_audio(None, 0.0)
    report = build_report(
        video_path=Path("x.mp4"),
        meta={"duration": 0.0, "fps": 0, "width": 0, "height": 0},
        frame_data={},
        audio_data=audio,
        transcript=[],
    )
    _validate_report(report)


def test_fps_duration_parsing():
    assert _parse_fps("0/0") == 30.0
    assert abs(_parse_fps("30000/1001") - 29.97) < 0.01
    assert _parse_fps("N/A", "0/0") == 30.0
    assert _parse_fps("N/A", "25/1") == 25.0
    assert _parse_float("N/A") is None
    assert _parse_float(None) is None
    assert _parse_float("12.5") == 12.5


def test_jsonio_sanitize_nan_inf():
    obj = {"a": float("nan"), "b": float("inf"), "c": [1.0, float("-inf")], "d": "ok", "e": 3}
    s = jsonio.dumps(obj)
    assert "NaN" not in s and "Infinity" not in s
    parsed = json.loads(s)
    assert parsed["a"] is None
    assert parsed["b"] is None
    assert parsed["c"][1] is None
    assert parsed["d"] == "ok"
    assert parsed["e"] == 3


def test_srt_vtt_snapshot():
    tx = [
        {"start": 0.0, "end": 1.5, "text": "Hello", "language": "en"},
        {"start": 2.0, "end": 3.25, "text": "World", "language": "en"},
    ]
    srt = to_srt(tx)
    expected = (
        "1\n00:00:00,000 --> 00:00:01,500\nHello\n\n"
        "2\n00:00:02,000 --> 00:00:03,250\nWorld\n"
    )
    assert srt == expected, repr(srt)
    assert to_vtt(tx).startswith("WEBVTT")


def test_chapters_keywords_retention_framing_smoke():
    tx = [{"start": float(i), "end": float(i) + 0.9, "text": f"word{i} idea test", "language": "en"} for i in range(10)]
    assert build_chapters(tx, [0.5, 5.0], 60.0)  # non-empty with a title
    assert build_keywords(tx)
    tl = [{"t": i * 0.5, "interestingness": 40.0 + (i % 5) * 5} for i in range(20)]
    rc = build_retention_curve(tl)
    assert len(rc["points"]) == 20 and rc["predictedRetention"] is not None
    fr = build_framing([{"t": 1.0, "cx": 0.5, "cy": 0.7, "w": 0.2, "h": 0.3}], 10.0)
    assert fr["hasFaceData"] and any(f["id"] == "low_framing" for f in fr["findings"])


def test_perf_regression_long_video():
    n = 7200  # ~1h of 0.5s bins
    bins = [
        {"t": i * 0.5, "motion": float(i % 25), "brightness": 120.0, "contrast": 40.0}
        for i in range(n)
    ]
    et = np.linspace(0, n * 0.5, 20000)
    audio = {
        "energy": np.abs(np.sin(et)).tolist(),
        "energy_times": et.tolist(),
        "waveform": [],
        "silence_gaps": [],
        "dead_air_ratio": 0.1,
        "loudness_consistency": 50.0,
        "clarity": 50.0,
        "music_speech_ratio": 0.4,
        "lufs": -14.0,
        "delivery": {},
    }
    transcript = [
        {"start": i * 10.0, "end": i * 10.0 + 5.0, "text": "some spoken words here", "language": "en"}
        for i in range(300)
    ]
    fd = _frame_data(n * 0.5, bins)
    fd["scene_cuts"] = [float(i * 7) for i in range(500)]
    t0 = time.perf_counter()
    report = build_report(
        video_path=Path("x.mp4"),
        meta={"duration": n * 0.5, "fps": 30, "width": 1920, "height": 1080},
        frame_data=fd,
        audio_data=audio,
        transcript=transcript,
    )
    dt = time.perf_counter() - t0
    _validate_report(report)
    assert len(report["timeline"]) == n
    assert dt < 5.0, f"build_report too slow on 1h input: {dt:.2f}s"


if __name__ == "__main__":
    test_no_audio_no_transcript()
    test_zero_duration_empty_frames()
    test_fps_duration_parsing()
    test_jsonio_sanitize_nan_inf()
    test_srt_vtt_snapshot()
    test_chapters_keywords_retention_framing_smoke()
    test_perf_regression_long_video()
    print("ok")
