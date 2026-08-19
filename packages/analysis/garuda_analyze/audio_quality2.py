"""Advanced audio QC parameters (true-peak, LRA, SNR, hum, sibilance, plosives)."""

from __future__ import annotations

from .metrics import REGISTRY, Metric, unavailable


@REGISTRY.register("audio_quality2", group="audio")
def _audio2(ctx: dict) -> "list[Metric]":
    ad = ctx.get("audio_data") or {}
    adv = ad.get("advanced") or {}
    out: list[Metric] = []

    if "truePeakDb" in adv:
        tp = adv["truePeakDb"]
        out.append(
            Metric("truePeak", "True peak", tp, "dBFS", (-60, 0), "peak_sample", confidence=0.7,
                   group="audio", severity=("high" if tp > -1 else "low"),
                   recommendation=("Bring peaks below -1 dBTP with a limiter" if tp > -1 else None))
        )
    if "lraDb" in adv:
        out.append(
            Metric("loudnessRange", "Loudness range (LRA)", adv["lraDb"], "LU", (0, 30),
                   "block_spread", confidence=0.5, group="audio")
        )
    if "snrDb" in adv:
        snr = adv["snrDb"]
        out.append(
            Metric("snr", "Signal-to-noise", snr, "dB", (0, 80), "rms_percentile", confidence=0.5,
                   group="audio", severity=("medium" if snr < 20 else "low"),
                   recommendation=("Reduce background noise / denoise" if snr < 20 else None))
        )
    if "humRatio" in adv:
        hum = adv["humRatio"]
        out.append(
            Metric("mainsHum", "Mains hum (50/60Hz)", round(hum * 100.0, 2), "%", (0, 100), "fft_band",
                   confidence=0.4, group="audio", severity=("medium" if hum > 0.05 else "low"),
                   recommendation=("Notch 50/60Hz + harmonics" if hum > 0.05 else None))
        )
    if "sibilanceRatio" in adv:
        out.append(
            Metric("sibilance", "Sibilance energy", round(adv["sibilanceRatio"] * 100.0, 2), "%", (0, 100),
                   "fft_band", confidence=0.4, group="audio")
        )
    if "plosiveCount" in adv:
        out.append(
            Metric("plosives", "Plosive bursts", adv["plosiveCount"], "count", (0, 1000),
                   "lowband_transient", confidence=0.3, group="audio")
        )

    if not adv:
        out.append(unavailable("truePeak", "True peak", "peak_sample", "audio", "No audio analyzed"))

    # Mono extraction means channel balance is unmeasurable; reverb/AV-sync need more.
    out.append(unavailable("stereoBalance", "Stereo balance", "channel_rms", "audio", "Audio analyzed as mono"))
    out.append(unavailable("reverbRt60", "Reverb (RT60)", "decay_fit", "audio", "Not measured"))
    out.append(unavailable("avSync", "A/V sync offset", "xcorr", "audio", "Not measured"))
    return out
