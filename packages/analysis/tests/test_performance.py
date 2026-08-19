from garuda_analyze.performance import MODES, configure_performance, current_mode, normalize_mode


def test_normalize_mode():
    assert normalize_mode("eco") == "eco"
    assert normalize_mode("high") == "high"
    assert normalize_mode("nope") == "balanced"


def test_configure_modes():
    for mode in MODES:
        assert configure_performance(mode) == mode
    assert current_mode() in MODES
