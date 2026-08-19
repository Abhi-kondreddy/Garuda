from garuda_analyze.pacing_metrics import build_pacing_metrics
from garuda_analyze.editor.clip_similarity import clip_similarity, find_near_duplicates


def test_pacing_metrics_basic():
    timeline = [
        {"t": 0.0, "interestingness": 20, "motion": 10, "audioEnergy": 10},
        {"t": 2.0, "interestingness": 55, "motion": 50, "audioEnergy": 60},
        {"t": 10.0, "interestingness": 70, "motion": 40, "audioEnergy": 50},
    ]
    pacing = build_pacing_metrics(
        duration=60.0,
        timeline=timeline,
        cuts=[1.5, 12.0],
        transcript=[{"start": 1.0, "end": 3.0, "text": "hello world"}],
        on_cam=0.4,
    )
    assert pacing["timeToFirstValueSec"] == 2.0
    assert pacing["hookPattern"] in ("standard", "strong_open")
    assert pacing["energyArc"] in ("rising", "falling", "flat")
    assert len(pacing["cutRateBySegment"]) == 3


def test_clip_similarity_duplicate():
    a = {
        "durationSec": 30,
        "palette": [{"hex": "#aabbcc", "weight": 0.6}, {"hex": "#112233", "weight": 0.4}],
        "highlights": [{"t": 5.0}],
    }
    b = {
        "durationSec": 31,
        "palette": [{"hex": "#aabbcc", "weight": 0.55}, {"hex": "#112233", "weight": 0.45}],
        "highlights": [{"t": 5.5}],
    }
    c = {
        "durationSec": 120,
        "palette": [{"hex": "#ff0000", "weight": 1.0}],
        "highlights": [{"t": 60.0}],
    }
    assert clip_similarity(a, b) >= 0.72
    assert clip_similarity(a, c) < 0.5
    pairs = find_near_duplicates({"a": a, "b": b, "c": c})
    assert any(p["clipA"] == "a" and p["clipB"] == "b" for p in pairs)
