from __future__ import annotations

from typing import Optional

import argparse
import json
import sys
import traceback
from pathlib import Path


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Garuda voices / render sidecar")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_analyze = sub.add_parser("analyze", help="Diarize + separate speakers")
    p_analyze.add_argument("--report-dir", required=True)
    p_analyze.add_argument("--ffmpeg", default="ffmpeg")
    p_analyze.add_argument("--hf-token", default="")
    p_analyze.add_argument("--allow-download", action="store_true")

    p_preview = sub.add_parser("preview", help="Apply FX and build preview mix")
    p_preview.add_argument("--report-dir", required=True)
    p_preview.add_argument("--project", required=True)
    p_preview.add_argument("--ffmpeg", default="ffmpeg")

    p_render = sub.add_parser("render", help="Run a RenderJob JSON")
    p_render.add_argument("--job", required=True)
    p_render.add_argument("--ffmpeg", default="ffmpeg")

    p_solo = sub.add_parser("solo-enhance", help="Build enhanced solo stem cache")
    p_solo.add_argument("--report-dir", required=True)
    p_solo.add_argument("--speaker-id", required=True)
    p_solo.add_argument("--project", required=True)
    p_solo.add_argument("--out", required=True)
    p_solo.add_argument("--ffmpeg", default="ffmpeg")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "analyze":
            from .pipeline_voices import run_voice_analyze

            result = run_voice_analyze(
                report_dir=Path(args.report_dir),
                ffmpeg=args.ffmpeg,
                hf_token=args.hf_token or None,
                allow_download=bool(args.allow_download),
                emit=_emit,
            )
            _emit({"type": "done", **result})
            return 0

        if args.cmd == "preview":
            from .enhance import build_preview_mix
            from .project import load_project, save_project

            project = load_project(Path(args.project))
            out = build_preview_mix(
                report_dir=Path(args.report_dir),
                project=project,
                ffmpeg=args.ffmpeg,
                emit=_emit,
            )
            project["previewMixPath"] = str(out)
            save_project(Path(args.project), project)
            _emit({"type": "done", "previewMixPath": str(out)})
            return 0

        if args.cmd == "solo-enhance":
            from .enhance import enhance_stem_to_file
            from .project import load_project

            project = load_project(Path(args.project))
            path = enhance_stem_to_file(
                report_dir=Path(args.report_dir),
                speaker_id=args.speaker_id,
                project=project,
                out_path=Path(args.out),
                ffmpeg=args.ffmpeg,
                emit=_emit,
            )
            _emit({"type": "done", "path": str(path)})
            return 0

        if args.cmd == "render":
            from .render import run_render_job

            result = run_render_job(Path(args.job), ffmpeg=args.ffmpeg, emit=_emit)
            _emit({"type": "done", **result})
            return 0

        _emit({"type": "error", "message": f"Unknown command {args.cmd}"})
        return 1
    except Exception as exc:  # noqa: BLE001
        _emit(
            {
                "type": "error",
                "message": str(exc) or "Voices job failed",
                "detail": traceback.format_exc()[-2000:],
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
