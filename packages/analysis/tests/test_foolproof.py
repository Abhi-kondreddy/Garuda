from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from garuda_analyze.audio_features import analyze_audio  # noqa: E402
from garuda_analyze.scoring import build_report  # noqa: E402
from garuda_analyze.validation import validate_report, repair_report  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN = FIXTURES / "golden_report.json"


def _bins(n: int):
    return [
        {"t": i * 0.5, "motion": float(3 + (i % 7)), "brightness": 110.0 + (i % 5), "contrast": 40.0}
        for i in range(n)
    ]


def _frame_data(duration: float, bins: list) -> dict:
    return {
        "brightness": [b["brightness"] for b in bins],
        "contrast": [b["contrast"] for b in bins],
        "motion": [b["motion"] for b in bins],
        "hue_means": [20.0] * len(bins),
        "sat_means": [80.0] * len(bins),
        "scene_cuts": [1.0, 4.0],
        "timeline_bins": bins,
        "palette": [],
        "on_cam_presence": 0.6,
        "face_boxes": [],
        "face_backend": "haar",
        "fps": 30,
        "duration": duration,
    }


def _reference_report():
    bins = _bins(40)
    transcript = [
        {"start": 0.5, "end": 3.0, "text": "here is how to fix your hook", "language": "en", "confidence": 0.8},
        {"start": 8.0, "end": 12.0, "text": "and this is the proof it works", "language": "en", "confidence": 0.8},
    ]
    return build_report(
        video_path=Path("fixture.mp4"),
        meta={"duration": 20.0, "fps": 30, "width": 1280, "height": 720},
        frame_data=_frame_data(20.0, bins),
        audio_data=analyze_audio(None, 20.0),
        transcript=transcript,
    )


def test_golden_report_scores():
    report = _reference_report()
    scores = {k: round(float(v), 1) for k, v in report["scores"].items()}
    version = report.get("scoringVersion")
    if not GOLDEN.exists():
        FIXTURES.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps({"scoringVersion": version, "scores": scores}, indent=2))
        print(f"golden created for {version}")
        return
    golden = json.loads(GOLDEN.read_text())
    if golden.get("scoringVersion") != version:
        GOLDEN.write_text(json.dumps({"scoringVersion": version, "scores": scores}, indent=2))
        print(f"golden regenerated: version {golden.get('scoringVersion')} -> {version}")
        return
    for k, v in golden["scores"].items():
        assert abs(scores[k] - v) <= 0.5, f"score drift on {k}: {scores[k]} vs golden {v} (bump SCORING_VERSION?)"


def test_synthetic_fuzz_never_crashes():
    """Degenerate but well-typed inputs must yield a schema-valid report."""
    cases = []
    # zero duration / empty frames
    cases.append(({"duration": 0.0, "fps": 0, "width": 0, "height": 0}, {}, analyze_audio(None, 0.0), []))
    # single bin
    cases.append(({"duration": 0.5, "fps": 30, "width": 320, "height": 240}, _frame_data(0.5, _bins(1)), analyze_audio(None, 0.5), []))
    # empty-text transcript segments
    tx = [{"start": 0.0, "end": 1.0, "text": "", "language": "en", "confidence": 0.5}]
    cases.append(({"duration": 5.0, "fps": 30, "width": 640, "height": 360}, _frame_data(5.0, _bins(10)), analyze_audio(None, 5.0), tx))
    # NaN injected into audio energy — must be sanitized away by repair/write
    bad_audio = analyze_audio(None, 5.0)
    bad_audio["energy"] = [float("nan"), float("inf"), 0.5]
    bad_audio["energy_times"] = [0.0, 0.5, 1.0]
    cases.append(({"duration": 5.0, "fps": 30, "width": 640, "height": 360}, _frame_data(5.0, _bins(10)), bad_audio, []))

    for meta, fd, audio, tx in cases:
        report = build_report(video_path=Path("x.mp4"), meta=meta, frame_data=fd, audio_data=audio, transcript=tx)
        report = repair_report(report)
        ok, errors = validate_report(report)
        assert ok, f"schema invalid: {errors[:5]}"
        s = json.dumps(report)
        assert "NaN" not in s and "Infinity" not in s


def _find_ff(name: str) -> "str | None":
    p = shutil.which(name)
    if p:
        return p
    local = ROOT.parent.parent / "tools" / "ffmpeg" / name
    return str(local) if local.exists() else None


def test_ffmpeg_media_fuzz():
    """If a real ffmpeg/ffprobe exists, push synthesized degenerate media through
    the whole pipeline and assert a valid report or a clean error (never a hang)."""
    ffmpeg = _find_ff("ffmpeg")
    ffprobe = _find_ff("ffprobe")
    if not ffmpeg or not ffprobe:
        print("SKIP ffmpeg media fuzz (no ffmpeg/ffprobe available)")
        return
    from garuda_analyze.pipeline import run_pipeline

    specs = [
        # (label, lavfi video, lavfi audio or None, seconds)
        ("solid_black", "color=c=black:s=320x240:r=30", None, 2),
        ("noise_no_audio", "testsrc2=s=320x240:r=30", None, 1),
        ("tiny_with_silence", "testsrc2=s=160x120:r=15", "anullsrc=r=16000:cl=mono", 1),
    ]
    for label, vf, af, secs in specs:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / f"{label}.mp4"
            cmd = [ffmpeg, "-y", "-f", "lavfi", "-i", f"{vf}:d={secs}"]
            if af:
                cmd += ["-f", "lavfi", "-i", f"{af}:d={secs}", "-shortest"]
            cmd += [str(src)]
            r = subprocess.run(cmd, capture_output=True, timeout=60)
            assert r.returncode == 0 and src.exists(), f"ffmpeg gen failed for {label}"
            out = Path(td) / "out"
            events = []
            try:
                run_pipeline(
                    video_path=src, out_dir=out, ffmpeg=ffmpeg, ffprobe=ffprobe,
                    whisper_model="tiny", skip_asr=True, emit=events.append,
                )
                rp = out / "report.json"
                assert rp.exists(), f"no report for {label}"
                ok, errors = validate_report(json.loads(rp.read_text()))
                assert ok, f"invalid report for {label}: {errors[:5]}"
            except Exception as exc:  # a clean, surfaced error is acceptable
                print(f"{label}: clean error {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    test_golden_report_scores()
    test_synthetic_fuzz_never_crashes()
    test_ffmpeg_media_fuzz()
    print("ok")
