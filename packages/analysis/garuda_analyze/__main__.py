from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from .pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Garuda local video analyzer")
    parser.add_argument("--path", required=True, help="Input video path")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--whisper-model", default="base", help="faster-whisper model size")
    parser.add_argument("--skip-asr", action="store_true", help="Skip speech recognition")
    args = parser.parse_args(argv)

    def emit(obj: dict) -> None:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    try:
        report_path = run_pipeline(
            video_path=Path(args.path),
            out_dir=Path(args.out),
            ffmpeg=args.ffmpeg,
            ffprobe=args.ffprobe,
            whisper_model=args.whisper_model,
            skip_asr=args.skip_asr,
            emit=emit,
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
