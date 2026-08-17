from __future__ import annotations

import json
import math
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from garuda_analyze.scoring import build_report  # noqa: E402
from garuda_analyze.audio_features import analyze_audio  # noqa: E402


def _write_sine_wav(path: Path, seconds: float = 2.0, freq: float = 440.0, sr: int = 16000) -> None:
    n = int(seconds * sr)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        for i in range(n):
            # early punch then quieter — for hook/audio tests
            amp = 0.55 if i < sr * 0.4 else 0.12
            val = int(amp * 32767 * math.sin(2 * math.pi * freq * (i / sr)))
            wf.writeframes(struct.pack("<h", val))


def test_scoring_hook_and_color():
    motion = [20.0] * 10 + [2.0] * 40
    brightness = [120.0 + (i % 3) for i in range(len(motion))]
    contrast = [40.0] * len(motion)
    times = [i * 0.5 for i in range(len(motion))]
    bins = [
        {"t": t, "motion": motion[i], "brightness": brightness[i], "contrast": contrast[i]}
        for i, t in enumerate(times)
    ]
    frame_data = {
        "brightness": brightness,
        "contrast": contrast,
        "motion": motion,
        "hue_means": [20.0] * len(motion),
        "sat_means": [80.0] * len(motion),
        "scene_cuts": [0.5, 1.0],
        "timeline_bins": bins,
        "palette": [{"hex": "#c87941", "weight": 0.6}, {"hex": "#1c1916", "weight": 0.4}],
        "on_cam_presence": 0.7,
        "fps": 30,
        "duration": 25,
    }
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        _write_sine_wav(wav, seconds=2.0)
        audio = analyze_audio(wav, 25.0)

    transcript = [
        {"start": 0.2, "end": 1.5, "text": "Hello world this changes everything", "language": "en", "confidence": 0.8},
        {"start": 2.0, "end": 3.0, "text": "నమస్కారం", "language": "te", "confidence": 0.7},
        {"start": 10.0, "end": 12.0, "text": "Here is the proof step by step", "language": "en", "confidence": 0.8},
        {"start": 20.0, "end": 22.0, "text": "And that is the payoff", "language": "en", "confidence": 0.8},
    ]
    report = build_report(
        video_path=Path("fixture.mp4"),
        meta={"duration": 25, "fps": 30, "width": 1280, "height": 720},
        frame_data=frame_data,
        audio_data=audio,
        transcript=transcript,
    )
    assert report["scores"]["hook"] > 20
    assert 0 <= report["scores"]["colorEvenness"] <= 100
    assert report["audio"]["englishPercent"] > 0
    assert report["audio"]["teluguPercent"] > 0
    assert len(report["timeline"]) > 0
    assert "companion" in report
    c = report["companion"]
    assert c["hookDoctor"]["findings"]
    assert len(c["titlesThumbnails"]["titles"]) >= 3
    assert c["pacing"]["format"] in ("shorts", "long_form")
    assert c["publishChecklist"]["total"] >= 5
    assert c["talkingPoints"]["structure"]
    assert c["coachFeed"] is not None
    assert c["nextGoals"]
    assert c.get("beforeAfter")
    assert c.get("sectionEnergy")
    assert c.get("endingCta")
    assert c.get("scoreDrivers")
    assert c.get("fixActions") is not None


def test_cli_help_import():
    from garuda_analyze.__main__ import main

    assert callable(main)


if __name__ == "__main__":
    test_scoring_hook_and_color()
    test_cli_help_import()
    print("ok")
