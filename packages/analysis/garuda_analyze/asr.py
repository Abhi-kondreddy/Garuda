from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import Callable


ProgressCb = Callable[..., None]


def _force_ipv4() -> None:
    """Prefer IPv4. Broken IPv6 routes cause Whisper downloads to hang on SYN_SENT."""
    if getattr(socket, "_garuda_ipv4_patched", False):
        return
    original = socket.getaddrinfo

    def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):  # noqa: A002
        try:
            infos = original(host, port, socket.AF_INET, type, proto, flags)
            if infos:
                return infos
        except OSError:
            pass
        return original(host, port, family, type, proto, flags)

    socket.getaddrinfo = getaddrinfo_ipv4  # type: ignore[assignment]
    socket._garuda_ipv4_patched = True  # type: ignore[attr-defined]


# ISO-ish codes we surface in the UI
_LANG_ALIASES = {
    "telugu": "te",
    "te": "te",
    "english": "en",
    "en": "en",
    "hindi": "hi",
    "hi": "hi",
    "tamil": "ta",
    "ta": "ta",
    "kannada": "kn",
    "kn": "kn",
    "malayalam": "ml",
    "ml": "ml",
    "marathi": "mr",
    "mr": "mr",
    "bengali": "bn",
    "bn": "bn",
    "gujarati": "gu",
    "gu": "gu",
    "punjabi": "pa",
    "pa": "pa",
    "urdu": "ur",
    "ur": "ur",
    "spanish": "es",
    "es": "es",
    "french": "fr",
    "fr": "fr",
    "german": "de",
    "de": "de",
    "portuguese": "pt",
    "pt": "pt",
    "arabic": "ar",
    "ar": "ar",
    "chinese": "zh",
    "zh": "zh",
    "japanese": "ja",
    "ja": "ja",
    "korean": "ko",
    "ko": "ko",
}

LANG_LABELS = {
    "te": "Telugu",
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "kn": "Kannada",
    "ml": "Malayalam",
    "mr": "Marathi",
    "bn": "Bengali",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "ur": "Urdu",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ar": "Arabic",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "other": "Other",
}


def language_label(code: str) -> str:
    return LANG_LABELS.get(code, code.upper() if code else "Other")


def _normalize_lang_code(lang: str | None) -> str | None:
    if not lang:
        return None
    raw = lang.lower().strip().replace("_", "-")
    primary = raw.split("-", 1)[0]
    if primary in _LANG_ALIASES:
        return _LANG_ALIASES[primary]
    if raw in _LANG_ALIASES:
        return _LANG_ALIASES[raw]
    if len(primary) == 2 or len(primary) == 3:
        return primary
    return None


def _script_counts(text: str) -> dict[str, int]:
    counts = {
        "te": 0,  # Telugu
        "hi": 0,  # Devanagari (Hindi / related)
        "ta": 0,  # Tamil
        "kn": 0,  # Kannada
        "ml": 0,  # Malayalam
        "bn": 0,  # Bengali
        "gu": 0,  # Gujarati
        "pa": 0,  # Gurmukhi
        "ar": 0,  # Arabic / Urdu script
        "en": 0,  # Latin
    }
    for ch in text:
        o = ord(ch)
        if 0x0C00 <= o <= 0x0C7F:
            counts["te"] += 1
        elif 0x0900 <= o <= 0x097F:
            counts["hi"] += 1
        elif 0x0B80 <= o <= 0x0BFF:
            counts["ta"] += 1
        elif 0x0C80 <= o <= 0x0CFF:
            counts["kn"] += 1
        elif 0x0D00 <= o <= 0x0D7F:
            counts["ml"] += 1
        elif 0x0980 <= o <= 0x09FF:
            counts["bn"] += 1
        elif 0x0A80 <= o <= 0x0AFF:
            counts["gu"] += 1
        elif 0x0A00 <= o <= 0x0A7F:
            counts["pa"] += 1
        elif 0x0600 <= o <= 0x06FF:
            counts["ar"] += 1
        elif ("a" <= ch.lower() <= "z"):
            counts["en"] += 1
    return counts


def _classify_language(lang: str | None, text: str) -> str:
    """Prefer writing-system evidence; fall back to Whisper's detected language."""
    counts = _script_counts(text)
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    top_code, top_n = ranked[0]
    second_n = ranked[1][1] if len(ranked) > 1 else 0

    if top_n > 0 and top_n >= max(2, second_n):
        if top_code == "en":
            normalized = _normalize_lang_code(lang)
            if normalized and normalized not in {
                "te",
                "hi",
                "ta",
                "kn",
                "ml",
                "bn",
                "gu",
                "pa",
                "ar",
                "ur",
            }:
                return normalized
            return "en"
        if top_code == "ar":
            normalized = _normalize_lang_code(lang)
            return normalized if normalized in {"ur", "ar"} else "ar"
        return top_code

    normalized = _normalize_lang_code(lang)
    if normalized:
        return normalized
    return "other"


def refine_transcript_languages(transcript: list[dict], detected: str | None = None) -> list[dict]:
    """Re-label segments using script + optional Whisper language hint."""
    out = []
    for seg in transcript:
        text = seg.get("text") or ""
        hint = detected or seg.get("language")
        # If stored code is already a known non-other label, still allow script override
        code = _classify_language(None if hint == "other" else hint, text)
        out.append({**seg, "language": code})
    return out


def _model_likely_cached(model_size: str) -> bool:
    home = Path.home()
    candidates = [
        home / ".cache" / "huggingface" / "hub" / f"models--Systran--faster-whisper-{model_size}",
        home / ".cache" / "huggingface" / "hub" / f"models--guillaumekln--faster-whisper-{model_size}",
    ]
    for c in candidates:
        if c.exists() and any(c.rglob("*.bin")):
            return True
    return False


def _emit(
    on_progress: ProgressCb | None,
    pct: float,
    message: str,
    *,
    phase: str | None = None,
    phase_percent: float | None = None,
) -> None:
    if not on_progress:
        return
    on_progress(pct, message, phase=phase, phase_percent=phase_percent)


def _load_model(model_size: str, result: dict, error: list) -> None:
    try:
        from faster_whisper import WhisperModel

        result["model"] = WhisperModel(model_size, device="cpu", compute_type="int8")
    except Exception as exc:  # noqa: BLE001
        error.append(exc)


def run_asr(
    wav_path: Path,
    *,
    model_size: str = "base",
    on_progress: ProgressCb | None = None,
    load_timeout_sec: float = 180.0,
) -> list[dict]:
    """Run local ASR with faster-whisper. Falls back to empty transcript if unavailable."""
    _force_ipv4()

    try:
        from faster_whisper import WhisperModel  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        _emit(
            on_progress,
            100,
            f"ASR unavailable ({exc.__class__.__name__}) — continuing without transcript",
        )
        return []

    cached = _model_likely_cached(model_size)
    phase = "load" if cached else "download"
    if cached:
        _emit(on_progress, 12, f"Loading Whisper '{model_size}' from cache…", phase=phase, phase_percent=5)
    else:
        _emit(
            on_progress,
            10,
            f"Downloading Whisper '{model_size}' (~145MB, IPv4) — first run only…",
            phase=phase,
            phase_percent=2,
        )

    stop_heartbeat = threading.Event()

    def heartbeat() -> None:
        started = time.time()
        n = 0
        while not stop_heartbeat.wait(2.0):
            n += 1
            elapsed = int(time.time() - started)
            pct = min(28, 10 + n)
            # Soft phase bar: climbs toward 90 while waiting (unknown true download %)
            phase_pct = min(90, 5 + elapsed * (4 if cached else 2))
            msg = (
                f"Loading Whisper '{model_size}'… {elapsed}s"
                if cached
                else f"Downloading Whisper '{model_size}'… {elapsed}s (first run)"
            )
            _emit(on_progress, pct, msg, phase=phase, phase_percent=phase_pct)

    result: dict = {}
    error: list = []
    hb = threading.Thread(target=heartbeat, daemon=True)
    hb.start()
    loader = threading.Thread(target=_load_model, args=(model_size, result, error), daemon=True)
    loader.start()
    loader.join(timeout=load_timeout_sec)
    stop_heartbeat.set()

    if loader.is_alive():
        _emit(
            on_progress,
            100,
            f"Whisper load timed out after {int(load_timeout_sec)}s — continuing without transcript",
            phase=phase,
            phase_percent=100,
        )
        return []

    if error:
        exc = error[0]
        _emit(
            on_progress,
            100,
            f"Whisper failed ({exc.__class__.__name__}: {exc}) — continuing without transcript",
            phase=phase,
            phase_percent=100,
        )
        return []

    model = result.get("model")
    if model is None:
        _emit(on_progress, 100, "Whisper model missing — continuing without transcript")
        return []

    _emit(
        on_progress,
        32,
        "Whisper ready — transcribing audio (auto language detect)…",
        phase="transcribe",
        phase_percent=0,
    )

    try:
        segments_iter, info = model.transcribe(
            str(wav_path),
            beam_size=1,
            vad_filter=True,
            word_timestamps=False,
            language=None,
        )
    except Exception as exc:  # noqa: BLE001
        _emit(
            on_progress,
            100,
            f"Transcription failed ({exc.__class__.__name__}) — continuing without transcript",
            phase="transcribe",
            phase_percent=100,
        )
        return []

    detected = getattr(info, "language", None)
    segments: list[dict] = []
    for i, seg in enumerate(segments_iter):
        text = (seg.text or "").strip()
        if not text:
            continue
        lang = _classify_language(detected, text)
        avg_lp = float(seg.avg_logprob) if getattr(seg, "avg_logprob", None) is not None else -1.0
        segments.append(
            {
                "start": float(seg.start or 0),
                "end": float(seg.end or 0),
                "text": text,
                "language": lang,
                "confidence": max(0.0, min(1.0, 1.0 + avg_lp)),
            }
        )
        if i % 2 == 0:
            # Unknown total segments — climb asymptotically
            phase_pct = min(95, 8 + i * 3)
            _emit(
                on_progress,
                min(95, 32 + i * 2),
                f"Transcribing… segment {i + 1}",
                phase="transcribe",
                phase_percent=phase_pct,
            )

    _emit(
        on_progress,
        100,
        f"ASR complete — {len(segments)} segments (detected={detected})",
        phase="transcribe",
        phase_percent=100,
    )
    return segments
