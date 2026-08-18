from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Garuda edit project propose / export")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_propose = sub.add_parser("propose", help="Analyze clips + propose long/Shorts timelines")
    p_propose.add_argument("--project", required=True, help="Path to project.json")
    p_propose.add_argument("--ffmpeg", default="ffmpeg")
    p_propose.add_argument("--ffprobe", default="ffprobe")
    p_propose.add_argument("--whisper-model", default="tiny")
    p_propose.add_argument("--skip-asr", action="store_true")
    p_propose.add_argument("--with-asr", action="store_true", help="Also run Whisper (slower)")
    p_propose.add_argument("--force-reanalyze", action="store_true")
    p_propose.add_argument(
        "--quick",
        action="store_true",
        help="Skip per-clip analysis; metadata heuristics only",
    )

    p_export = sub.add_parser("export", help="Export one output via FFmpeg")
    p_export.add_argument("--project", required=True)
    p_export.add_argument("--output-id", required=True)
    p_export.add_argument("--out", required=True)
    p_export.add_argument("--ffmpeg", default="ffmpeg")
    p_export.add_argument("--quality", default="good", choices=["draft", "good", "high"])
    p_export.add_argument("--resolution", default="1080", choices=["720", "1080", "1440"])
    p_export.add_argument("--burn-title", default="1", choices=["0", "1"])
    p_export.add_argument("--fps", type=int, default=30, choices=[24, 30, 60])

    args = parser.parse_args(argv)

    try:
        project_path = Path(args.project)
        project = json.loads(project_path.read_text(encoding="utf-8"))

        if args.cmd == "propose":
            from .propose import propose_outputs

            reports = {}
            if not args.quick:
                from .analyze_clips import analyze_project_clips

                reports = analyze_project_clips(
                    project=project,
                    project_path=project_path,
                    ffmpeg=args.ffmpeg,
                    ffprobe=args.ffprobe,
                    whisper_model=args.whisper_model,
                    skip_asr=not bool(args.with_asr),
                    force=bool(args.force_reanalyze),
                    emit=_emit,
                )
            else:
                _emit(
                    {
                        "type": "progress",
                        "stage": "propose",
                        "percent": 20,
                        "message": "Quick propose (no deep clip analysis)…",
                        "phase": "assemble",
                        "phasePercent": 30,
                    }
                )

            _emit(
                {
                    "type": "progress",
                    "stage": "assemble",
                    "percent": 92,
                    "message": "Assembling long + Shorts timelines…",
                    "phase": "assemble",
                    "phasePercent": 70,
                }
            )
            result = propose_outputs(project, reports=reports)
            project["outputs"] = result["outputs"]
            project["status"] = result["status"]
            project["lastAnalyzedCount"] = result.get("analyzedCount", 0)
            project_path.write_text(json.dumps(project, indent=2), encoding="utf-8")
            _emit(
                {
                    "type": "progress",
                    "stage": "assemble",
                    "percent": 100,
                    "message": "Proposal ready",
                    "phase": "assemble",
                    "phasePercent": 100,
                }
            )
            _emit(
                {
                    "type": "done",
                    "outputs": result["outputs"],
                    "status": result["status"],
                    "analyzedCount": result.get("analyzedCount", 0),
                }
            )
            return 0

        if args.cmd == "export":
            from .export_timeline import export_output

            meta = export_output(
                project=project,
                output_id=args.output_id,
                ffmpeg=args.ffmpeg,
                out_path=Path(args.out),
                emit=_emit,
                quality=args.quality,
                resolution=args.resolution,
                burn_title=args.burn_title == "1",
                fps=args.fps,
            )
            for o in project.get("outputs") or []:
                if o.get("id") == args.output_id:
                    o["exportPath"] = meta["outputPath"]
            project["status"] = "exported"
            project_path.write_text(json.dumps(project, indent=2), encoding="utf-8")
            _emit({"type": "done", **meta})
            return 0

        _emit({"type": "error", "message": f"Unknown command {args.cmd}"})
        return 1
    except Exception as exc:  # noqa: BLE001
        _emit(
            {
                "type": "error",
                "message": str(exc) or "Editor job failed",
                "detail": traceback.format_exc()[-2000:],
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
