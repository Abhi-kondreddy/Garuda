"""Unit tests for heuristic + analyzed edit proposer."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from garuda_analyze.editor.propose import propose_outputs  # noqa: E402


def _fake_report(dur=40.0, hook=80.0, interest=70.0, peak_t=12.0):
    return {
        "durationSec": dur,
        "sourcePath": "/tmp/x.mp4",
        "scores": {
            "hook": hook,
            "interestingness": interest,
            "overall": (hook + interest) / 2,
            "audioQuality": 60,
        },
        "timeline": [
            {"t": 2, "interestingness": 40},
            {"t": peak_t, "interestingness": interest},
            {"t": dur - 5, "interestingness": 30},
        ],
        "highlights": [{"t": peak_t, "score": interest, "label": "Peak"}],
        "audio": {"silenceGaps": [{"start": 0, "end": 1.5}]},
        "companion": {
            "shortsClips": [
                {
                    "start": peak_t - 2,
                    "end": peak_t + 20,
                    "score": interest,
                    "label": "Best window",
                    "captionHook": "Watch this",
                }
            ]
        },
    }


def test_propose_uses_analysis_for_order_and_trims():
    project = {
        "name": "Test day",
        "clips": [
            {"id": "weak", "path": "/tmp/a.mp4", "name": "weak.mp4", "durationSec": 50, "mtimeMs": 1},
            {"id": "strong", "path": "/tmp/b.mp4", "name": "strong.mp4", "durationSec": 40, "mtimeMs": 2},
        ],
        "sectionHints": [],
        "shortBins": [],
        "briefing": {
            "title": "Day",
            "subtitle": "",
            "cta": "Sub",
            "look": "warm",
            "format": {"longCount": 1, "shortsCount": 1},
            "longTargetMin": 10,
            "shortMaxSec": 60,
            "texts": [],
        },
    }
    reports = {
        "weak": _fake_report(hook=30, interest=35, peak_t=10),
        "strong": _fake_report(hook=90, interest=85, peak_t=8),
    }
    result = propose_outputs(project, reports=reports)
    longs = [o for o in result["outputs"] if o["kind"] == "long"]
    shorts = [o for o in result["outputs"] if o["kind"] == "short"]
    assert len(longs) == 1
    assert longs[0]["timeline"]["clips"][0]["clipId"] == "strong"
    # leading silence trimmed ~1.5s
    assert longs[0]["timeline"]["clips"][0]["inSec"] >= 1.0
    assert shorts[0]["success"]["score"] >= 60
    assert result["analyzedCount"] == 2


def test_propose_requires_clips():
    try:
        propose_outputs({"clips": [], "briefing": {"format": {"longCount": 1, "shortsCount": 1}}})
        assert False, "expected ValueError"
    except ValueError:
        pass


if __name__ == "__main__":
    test_propose_uses_analysis_for_order_and_trims()
    test_propose_requires_clips()
    print("ok")
