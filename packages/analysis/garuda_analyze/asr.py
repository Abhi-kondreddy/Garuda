from __future__ import annotations

import multiprocessing as mp
import os
import queue as queue_mod
import socket
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


def _resolve_compute() -> tuple[str, str]:
    """Pick faster-whisper device/compute. Env overrides let power users opt
    into GPU/Metal builds; the safe default stays CPU int8."""
    device = os.environ.get("GARUDA_WHISPER_DEVICE", "cpu").strip() or "cpu"
    compute = os.environ.get("GARUDA_WHISPER_COMPUTE", "").strip()
    if not compute:
        compute = "int8" if device == "cpu" else "float16"
    return device, compute


def _asr_worker(
    wav_path_str: str,
    model_size: str,
    device: str,
    compute_type: str,
    beam_size: int,
    word_timestamps: bool,
    q: "mp.Queue",
) -> None:
    """Runs in a separate process so a hung load/transcribe can be terminated.

    Emits ``(kind, payload)`` tuples: ``model_loaded``, ``detected``,
    ``segment`` (a plain dict), ``done``, or ``error``. Everything put on the
    queue is picklable (no model objects cross the boundary).
    """
    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        q.put(("model_loaded", None))
        segments_iter, info = model.transcribe(
            wav_path_str,
            beam_size=beam_size,
            vad_filter=True,
            word_timestamps=word_timestamps,
            language=None,
        )
        q.put(("detected", getattr(info, "language", None)))
        for seg in segments_iter:
            text = (seg.text or "").strip()
            if not text:
                continue
            avg_lp = (
                float(seg.avg_logprob) if getattr(seg, "avg_logprob", None) is not None else -1.0
            )
            words = None
            if word_timestamps and getattr(seg, "words", None):
                words = [
                    {"start": float(w.start or 0), "end": float(w.end or 0), "word": w.word}
                    for w in seg.words
                    if getattr(w, "word", None)
                ]
            q.put(
                (
                    "segment",
                    {
                        "start": float(seg.start or 0),
                        "end": float(seg.end or 0),
                        "text": text,
                        "avg_logprob": avg_lp,
                        "words": words,
                    },
                )
            )
        q.put(("done", None))
    except Exception as exc:  # noqa: BLE001
        q.put(("error", f"{exc.__class__.__name__}: {exc}"))


def _finalize_segment(raw: dict, detected: str | None) -> dict:
    text = raw["text"]
    avg_lp = float(raw.get("avg_logprob", -1.0))
    seg = {
        "start": float(raw.get("start") or 0.0),
        "end": float(raw.get("end") or 0.0),
        "text": text,
        "language": _classify_language(detected, text),
        "confidence": max(0.0, min(1.0, 1.0 + avg_lp)),
    }
    if raw.get("words"):
        seg["words"] = raw["words"]
    return seg


def run_asr(
    wav_path: Path,
    *,
    model_size: str = "base",
    on_progress: ProgressCb | None = None,
    load_timeout_sec: float = 180.0,
    transcribe_timeout_sec: float = 3600.0,
    beam_size: int = 1,
    word_timestamps: bool = False,
) -> list[dict]:
    """Run local ASR with faster-whisper in a killable child process.

    Falls back to an empty/partial transcript (never raises) if the model is
    unavailable, the load times out, transcription crashes mid-stream, or the
    process overruns its wall-clock budget.
    """
    _force_ipv4()

    try:
        import faster_whisper  # noqa: F401
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

    device, compute_type = _resolve_compute()
    try:
        ctx = mp.get_context("spawn")
        q: "mp.Queue" = ctx.Queue()
        proc = ctx.Process(
            target=_asr_worker,
            args=(str(wav_path), model_size, device, compute_type, beam_size, word_timestamps, q),
            daemon=True,
        )
        proc.start()
    except Exception as exc:  # noqa: BLE001 — spawning unavailable/blocked
        _emit(
            on_progress,
            100,
            f"ASR could not start ({exc.__class__.__name__}) — continuing without transcript",
            phase=phase,
            phase_percent=100,
        )
        return []

    segments: list[dict] = []
    detected: str | None = None
    loaded = False
    started = time.time()
    load_deadline = started + load_timeout_sec
    transcribe_deadline = None  # set once the model reports loaded

    def _stop(message: str, terminal: bool = True) -> None:
        if terminal:
            _emit(on_progress, 100, message, phase="transcribe", phase_percent=100)
        try:
            if proc.is_alive():
                proc.terminate()
        except Exception:
            pass

    try:
        while True:
            try:
                kind, payload = q.get(timeout=1.0)
            except queue_mod.Empty:
                now = time.time()
                if not loaded and now > load_deadline:
                    _stop(
                        f"Whisper load timed out after {int(load_timeout_sec)}s — continuing without transcript"
                    )
                    return []
                if loaded and transcribe_deadline and now > transcribe_deadline:
                    _stop(
                        f"Transcription exceeded {int(transcribe_timeout_sec)}s — using partial transcript"
                    )
                    break
                if not proc.is_alive():
                    # died without a terminal message
                    _stop("ASR process exited early — continuing without transcript")
                    break
                elapsed = int(time.time() - started)
                if not loaded:
                    phase_pct = min(90, 5 + elapsed * (4 if cached else 2))
                    msg = (
                        f"Loading Whisper '{model_size}'… {elapsed}s"
                        if cached
                        else f"Downloading Whisper '{model_size}'… {elapsed}s (first run)"
                    )
                    _emit(on_progress, min(28, 10 + elapsed // 2), msg, phase=phase, phase_percent=phase_pct)
                continue

            if kind == "model_loaded":
                loaded = True
                transcribe_deadline = time.time() + transcribe_timeout_sec
                _emit(
                    on_progress,
                    32,
                    "Whisper ready — transcribing audio (auto language detect)…",
                    phase="transcribe",
                    phase_percent=0,
                )
            elif kind == "detected":
                detected = payload
            elif kind == "segment":
                segments.append(_finalize_segment(payload, detected))
                i = len(segments)
                if i % 2 == 1:
                    _emit(
                        on_progress,
                        min(95, 32 + i * 2),
                        f"Transcribing… segment {i}",
                        phase="transcribe",
                        phase_percent=min(95, 8 + i * 3),
                    )
            elif kind == "done":
                break
            elif kind == "error":
                _emit(
                    on_progress,
                    100,
                    f"Transcription failed ({payload}) — using {len(segments)} partial segment(s)",
                    phase="transcribe",
                    phase_percent=100,
                )
                break
    finally:
        try:
            if proc.is_alive():
                proc.terminate()
            proc.join(timeout=5)
        except Exception:
            pass

    _emit(
        on_progress,
        100,
        f"ASR complete — {len(segments)} segments (detected={detected})",
        phase="transcribe",
        phase_percent=100,
    )
    return segments
