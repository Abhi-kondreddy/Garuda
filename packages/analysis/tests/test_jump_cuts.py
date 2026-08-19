from garuda_analyze.editor.jump_cuts import middle_jump_segments


def test_middle_jump_splits_on_silence():
    report = {
        "audio": {
            "silenceGaps": [
                {"start": 0, "end": 1.0},
                {"start": 20, "end": 23.5},
                {"start": 55, "end": 56},
            ]
        },
        "companion": {"cutList": []},
    }
    segments = middle_jump_segments(0.0, 60.0, report)
    assert len(segments) >= 2
    assert segments[0][0] == 0.0
    assert any("Jump-cut" in r for seg in segments for r in seg[2])


def test_middle_jump_skips_short_windows():
    report = {"audio": {"silenceGaps": [{"start": 5, "end": 7}]}, "companion": {"cutList": []}}
    segments = middle_jump_segments(0.0, 12.0, report)
    assert segments == [(0.0, 12.0, [])]
