import numpy as np

from garuda_analyze.voices.separate import separate_stft_masked


def test_stft_separation_writes_stems(tmp_path):
    sr = 16000
    t = np.linspace(0, 2.0, sr * 2, endpoint=False)
    # two alternating tones as fake speakers
    y = (0.3 * np.sin(2 * np.pi * 220 * t) + 0.25 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    clusters = [
        {"segments": [{"start": 0.0, "end": 1.0}]},
        {"segments": [{"start": 0.8, "end": 2.0}]},
    ]
    stems, residual, warning = separate_stft_masked(y, sr, clusters, tmp_path)
    assert len(stems) == 2
    assert (tmp_path / "speaker_1.wav").exists()
    assert (tmp_path / "speaker_2.wav").exists()
    assert residual.exists()
    assert "STFT" in warning


if __name__ == "__main__":
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_stft_separation_writes_stems(Path(d))
    print("ok")
