from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path
from typing import Callable

from . import jsonio
from .performance import configure_performance
from .pipeline import run_pipeline


def _make_emit() -> Callable[[dict], None]:
    """Reserve the real stdout for the NDJSON protocol.

    faster-whisper / numba / ctranslate2 (and stray ``print``s) sometimes write
    to stdout, which would corrupt the JSON event stream the Electron main
    process parses. We dup the original stdout to a private fd used only for the
    protocol, then point fd 1 at stderr so any accidental stdout goes to logs.
    """
    try:
        protocol_fd = os.dup(1)
        os.dup2(2, 1)  # fd 1 (stdout) now writes to stderr
        stream = os.fdopen(protocol_fd, "w", encoding="utf-8")
    except Exception:
        stream = sys.stdout  # pragma: no cover - platform fallback

    def emit(obj: dict) -> None:
        try:
            stream.write(jsonio.dumps(obj) + "\n")
            stream.flush()
        except Exception:
            # Telemetry must never crash the analysis run.
            pass

    return emit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Garuda local video analyzer")
    parser.add_argument("--path", required=True, help="Input video path")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--whisper-model", default="base", help="faster-whisper model size")
    parser.add_argument("--skip-asr", action="store_true", help="Skip speech recognition")
    parser.add_argument("--asr-beam", type=int, default=1, help="faster-whisper beam size")
    parser.add_argument(
        "--no-word-timestamps",
        dest="word_timestamps",
        action="store_false",
        help="Disable per-word timestamps (faster, but no word-level captions)",
    )
    parser.set_defaults(word_timestamps=True)
    parser.add_argument(
        "--performance-mode",
        default=None,
        choices=["eco", "balanced", "high"],
        help="Eco = slower & lighter on CPU; high = full speed. Same analysis depth.",
    )
    args = parser.parse_args(argv)
    configure_performance(args.performance_mode)

    emit = _make_emit()

    try:
        report_path = run_pipeline(
            video_path=Path(args.path),
            out_dir=Path(args.out),
            ffmpeg=args.ffmpeg,
            ffprobe=args.ffprobe,
            whisper_model=args.whisper_model,
            skip_asr=args.skip_asr,
            emit=emit,
            asr_beam=args.asr_beam,
            word_timestamps=args.word_timestamps,
        )
        emit({"type": "done", "reportPath": str(report_path)})
        return 0
    except Exception as exc:  # noqa: BLE001 — surface all engine failures to UI
        emit(
            {
                "type": "error",
                "message": str(exc) or "Analysis failed",
                "detail": traceback.format_exc()[-2000:],
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
