# Garuda — Features

Local-first desktop app for YouTube creators. Everything runs on your machine; analysis and edit projects live under Electron `userData`.

**Status key:** Done · Partial · Not yet

---

## Analyze (single video)

| Feature | Status | Notes |
|---|---|---|
| Open a local video and run the analysis pipeline | Done | OpenCV + librosa + optional Whisper |
| Live progress (overall, stages, phase sub-bar) | Done | Progress theater on Analyze |
| Hook / interestingness / color / visual / audio scores | Done | |
| Timeline energy + silence gaps | Done | Used by coaching and editor |
| Telugu / English speech mix when ASR runs | Done | Whisper model configurable in Settings |
| Skip ASR option | Done | Settings / pipeline flag |
| Saved reports + reopen from home / library | Done | `userData/garuda/reports/` |
| Companion coaching (cuts, Shorts windows, hooks) | Done | On the report |

---

## Report & Voices

| Feature | Status | Notes |
|---|---|---|
| Score breakdown + evidence jump | Done | |
| Voices enhancement / export helpers | Partial | Voice tools on report; full NLE-style render ops still limited |
| Reveal exported voice files | Done | Library / Voices |

---

## Editor (multi-clip day project)

Route: **EDITOR** (`Cmd/Ctrl+4`). Projects under `userData/garuda/projects/`.

| Feature | Status | Notes |
|---|---|---|
| Create / load / save / delete edit projects | Done | |
| Day pool: add, reorder, remove clips | Done | |
| Format mix (N long + M Shorts) + duration targets | Done | Briefing panel |
| Title, subtitle, CTA, look, music mood fields | Done | Music **mood only** today — no bed track mix yet |
| Pinned Short bins (topic + clips, optional Shorts-only) | Done | |
| **Deep propose** — per-clip analysis then assemble | Done | Cached under `clip_analysis/<id>/`; ASR skipped by default for speed |
| **Quick propose** — heuristics only (no deep read) | Done | |
| Progress UI (overall, stages, phase, clip pills) | Done | Sticky panel while propose / export runs |
| Proposal reasons (“WHY THIS CUT”) | Done | Per output |
| Shorts success score + why | Done | |
| Timeline preview (16:9 / 9:16 cover crop) | Done | Sequential play with in/out |
| Drag-reorder clips on an output timeline | Done | |
| FFmpeg export (draft / good / high, 720–1440, fps, burn title) | Done | Long 16:9, Shorts 9:16 |
| Cancel in-flight propose / export | Done | |

### What propose cuts today

| Behavior | Status |
|---|---|
| Trim leading / trailing silence (~0.8s+) | Done (deep propose) |
| Soft-trim very long takes (open near peak energy) | Done |
| Shorts: keep a peak / highlight / coach window | Done |
| Order long form by scores (or section hints as bias) | Done |
| Jump-cut middle silence / dull stretches inside a clip | **Not yet** (deferred on purpose) |
| Dense auto cut-list like CapCut “remove dead air” | **Not yet** |

---

## Library & Settings

| Feature | Status | Notes |
|---|---|---|
| Past reports list | Done | |
| Whisper / voice model prefs | Done | |
| Clear local Garuda data | Done | |
| Bundled FFmpeg | Done | `tools/ffmpeg/` |

---

## Explicitly out of scope for now

These were considered for a later “YouTube packager” phase and are **not** shipped:

- Learning from thumbs / drag-fixes, or channel stats
- LLM copy / reorder assist
- Background music ducking under speech
- Full end-card graphics / mid-roll text overlays beyond simple title burn
- Per-output thumbnails + Studio description paste pack
- Adaptive AI that “gets smarter” over time

When we add them, update this file and keep Editor propose API pluggable.

---

## CLI (optional)

```bash
# Single-video analysis
python -m garuda_analyze --path video.mp4 --out /tmp/out …

# Editor propose / export
python -m garuda_analyze.editor propose --project path/to/project.json …
python -m garuda_analyze.editor export --project … --output-id long-1 --out …
```

Progress events are newline-delimited JSON (`progress` / `error` / `done`).

---

*Last updated: 2026-08-18 — reflects Editor deep propose, progress UI, and deferred middle-cut / packager items.*
