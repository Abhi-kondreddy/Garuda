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
| Pacing & hook metrics (retention risk, energy arc, cut rate) | Done | Report + Editor reasons |
| Face framing + 9:16 crop safety | Done | Visual metrics |
| SNR proxy + WPM variance | Done | Audio metrics |
| Near-duplicate clip detection (day pool) | Done | Editor propose skips similar Shorts |
| Optional ASR on deep propose | Done | Editor “+ Speech (ASR)” toggle |
| Timeline energy + silence gaps | Done | Used by coaching and editor |
| Telugu / English speech mix when ASR runs | Done | Whisper model configurable in Settings |
| Skip ASR option | Done | Settings / pipeline flag |
| Saved reports + reopen from home / library | Done | `userData/garuda/reports/` |
| Companion coaching (cuts, Shorts windows, hooks) | Done | On the report |
| SRT / VTT caption export | Done | Written next to report; "Export captions" on report |
| YouTube chapters from transcript + scene cuts | Done | `report.chapters` |
| Keyword / SEO pack from transcript | Done | `report.keywords` |
| Face-aware thumbnail candidate JPEGs | Done | `report.thumbnailFiles` (peak frames, subject-cropped) |
| Retention-risk curve + worst-drop marker | Done | `report.retentionCurve` |
| Framing checks + b-roll vs talking-head timeline | Done | `report.framing` (needs face data) |
| True integrated loudness (LUFS) + platform target | Done | `report.audio.lufs` / `lufsGap` (via pyloudnorm) |
| DNN face detection (YuNet) with Haar fallback | Done | Bundle YuNet ONNX to enable; else Haar |
| PySceneDetect content cuts (short clips) | Partial | Used when installed and clip ≤ 30 min; else histogram cuts |
| Resilience: subprocess timeouts, partial reports, NaN-safe JSON | Done | Engine can't hang/crash the run or corrupt the stream |
| Versioned scoring model + centralized tunables | Done | `report.scoringVersion`, `garuda_analyze/config.py` |
| Metric-contract layer (~56 params w/ unit, range, method, confidence, evidence) | Done | `report.metrics`; plugin registry in `metrics.py` |
| Parameter catalog: exposure/WB, sharpness/shake, framing, LUFS/true-peak/SNR/hum, fillers/readability/safety, technical QC | Done | `vision_*`, `audio_quality2`, `nlp`, `qc` plugins |
| ML params (aesthetics/shot-type/emotion/objects, sentiment, NER) | Partial | `ml_vision`/`nlp_ml`; activate by bundling ONNX + `requirements-ml.txt` |
| Accessibility/compliance (PSE flash, caption speed; WCAG contrast/copyright/PII stubs) | Partial | `accessibility.py` |
| Provenance + diagnostics + preflight QC + wall-clock/mem watchdog | Done | `provenance.py`, `preflight.py`, `watchdog.py` |
| Report JSON Schema validation + atomic write | Done | `schema/report.schema.json`, `validation.py` |
| Calibration engine (train on YT retention/CTR -> predictions + confidence intervals) | Done | `calibration/`; heuristic fallback when untrained |
| Percentile benchmarks vs history + multimodal drop-risk + top drivers | Done | `benchmark.py`, `fusion.py`, `report.topDrivers` |
| Content-hash for cache/dedupe | Done | `cache.py`, `report.contentHash` |

---

## Report & Voices

| Feature | Status | Notes |
|---|---|---|
| Score breakdown + evidence jump | Done | |
| Voices enhancement / export helpers | Partial | STFT soft-Wiener default; neural SepFormer + optional pyannote — see **SETUP.md** optimum tier |
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
| Live system monitor (CPU, RAM, Garuda load) | Done | Settings + titlebar + during jobs |
| Processing speed (Eco / Balanced / High) | Done | Same depth; throttles CPU only |
| Resource guard (warn / auto Eco on critical) | Done | Force Eco, stop job, snooze |

### What propose cuts today

| Behavior | Status |
|---|---|
| Trim leading / trailing silence (~0.8s+) | Done (deep propose) |
| Soft-trim very long takes (open near peak energy) | Done |
| Shorts: keep a peak / highlight / coach window | Done |
| Order long form by scores (or section hints as bias) | Done |
| Jump-cut middle silence / dull stretches inside a clip | Done | Long-form propose only |
| Dense auto cut-list like CapCut “remove dead air” | **Not yet** |
| Pacing metrics drive propose scoring | Done | Order + Shorts rank |
| Face-aware 9:16 export crop | Done | Uses `faceCenterX` from analysis |
| Loudness normalization on export (-14 LUFS) | Done | FFmpeg loudnorm |
| Stale clip cache detection + re-analyze toggle | Done | Editor header badge |
| Elapsed + ETA during analysis / propose / export | Done | Progress panels |

---

## Library & Settings

| Feature | Status | Notes |
|---|---|---|
| Past reports list | Done | |
| Whisper / voice model prefs | Done | |
| Clear local Garuda data | Done | |
| Bundled FFmpeg | Done | `tools/ffmpeg/` |

---

## Future enhancements

### Analysis roadmap

The raw measurement catalog is largely saturated; the next frontier is derived /
comparative / predictive features that combine the existing metrics. Not yet
shipped:

**Derived / comparative**
- Per-segment / per-chapter scorecards (hook/pacing/retention/energy graded per chapter, not just global + timeline).
- Comparative analysis vs a reference/competitor video (gap report).
- Real A/B diff of two cuts of the same video (measured, not the current `beforeAfter` simulation).
- Niche/topic classification + niche-specific norms (baselines per genre).

**New signals**
- Music/beat analysis: BPM, beat grid, cut-on-beat adherence, drop detection.
- Cross-modal moment detection: laughter, applause, silence→punchline, on-screen-text appearance.

**Scorecards / deliverables**
- Consolidated Accessibility scorecard (flash + captions + contrast + audio-description need as one grade).
- Hardened "publish-readiness" gate with platform presets (YouTube long / Shorts / Reels).
- Loudness one-click fix recipe (emit the exact `ffmpeg loudnorm` command to hit target).

**Predictive (gated on calibration data)**
- Calibrated virality / clip finder (rank clippable 15–60s windows by predicted performance).
- Rank `topDrivers` by predicted retention delta instead of severity.

**Quality / rigor (from the review of the current engine)**
- Full-resolution / ffmpeg `signalstats`-based vision QC (vs the 160×90 proxy).
- Data-driven `confidence` (from #frames, SNR, transcript coverage) instead of fixed constants.
- Implement the `unavailable` stubs: A/V sync, stereo balance (needs stereo extract), reverb RT60, horizon (Hough), on-screen-text legibility (OCR).
- Multilingual correctness: gate Flesch-Kincaid to Latin script; non-English filler/sentiment lexicons.
- Determinism for the ML/ASR path (torch seeds/flags); real-media CI + `hypothesis` property tests.

**Crosses out of "analysis" (Editor/renderer/UX)**
- Auto-EDL / auto-cut export, shareable PDF/HTML report, `chapters.txt`/tags export, real-time "record with live hook feedback", channel-level dashboards, and the parked Lakshya cloud integration.

### Editor / scoring roadmap

Planned improvements for **interestingness scoring**, **smarter propose**, **export quality**, and **multi-clip data**. Ordered by suggested build priority.

### Tier 1 — High impact, lower risk

| Enhancement | Goal |
|---|---|
| **Per-clip data panel (day pool)** | After adding many videos to an Editor project, show each clip’s scores (hook, interestingness, overall, audio, pacing) in the day pool — not just name + duration |
| **Clip detail drill-down** | Click a clip to open mini-report: timeline chart, risk zones, highlights, WPM / language mix, stale-cache badge |
| **Batch analyze without propose** | “Analyze all clips” action that fills `clip_analysis/` cache and refreshes the panel without running full propose/export |
| **Compare clips table** | Sortable grid across the day pool: rank by hook, interest, dead air, duration; spot weak clips before proposing |
| **Export readiness score** | Per output: predicted avg interestingness, hook, dead-air % before FFmpeg runs |
| **Export warning below threshold** | Warn (or optional block) when predicted export score &lt; ~50; link to proposal reasons |
| **Interest-driven jump cuts** | Remove low-interest stretches from `riskZones`, not only silence / coach `cutList` |
| **Shorts minimum window quality** | Reject or re-pick Shorts windows whose local interestingness avg is below ~45 |
| **“Tighten dull stretches” action** | One-click disable timeline segments that fall in low-interest zones |
| **Risk zones on Editor preview** | Show pink “low interestingness” overlays on the timeline (same as Report) |

**Today:** Deep propose writes per-clip `report.json` under `clip_analysis/<clipId>/`, but the Editor UI does not surface that data until you infer it from proposal reasons. Single-video **Analyze → Report** is the only full data view per file.

### Tier 2 — Better interestingness (scoring v2)

| Enhancement | Goal |
|---|---|
| **On-cam–aware weights** | Talking-head preset: less motion penalty when face presence is high |
| **Speech density signal** | Replace binary speech (0/80) with WPM / segment density on the timeline |
| **Risk-zone penalty in clip score** | Downrank clips with long stretches below interestingness ~35 |
| **Hook vs body interestingness** | Separate scores for first 30s vs rest; Shorts use hook-weighted local windows |
| **ASR default on deep propose** | Opt-in by default (with clear Eco note) so speech contributes to scoring |

Current formula (for reference): per 0.5s bin → **40% motion + 30% audio energy + 20% speech + 10% scene-cut boost**; report score = timeline average. Propose **ranks and trims** but does **not** block export on low scores.

### Tier 3 — Smarter propose logic

| Enhancement | Goal |
|---|---|
| **Clip inclusion threshold** | Skip or demote day-pool clips in bottom quartile for avg interestingness |
| **Long-form highlight mode** | Stitch above-median interest segments instead of whole clips minus dead air |
| **Open on first value** | Start long exports at `timeToFirstValueSec` when pacing metrics find a late punch |
| **Deep propose before export** | Warn or gate export when clips lack analysis cache (Quick propose only) |
| **Post-propose quality check** | Re-score the assembled timeline; surface in UI before mux |
| **Content-type presets** | Talking head / montage / podcast — switch score + propose weights in Settings |

### Tier 4 — Bigger bets

| Enhancement | Goal |
|---|---|
| **Semantic peaks from ASR** | Boost windows with questions, numbers, hooky keywords in transcript |
| **Face / expression change** | Use dense face sampling for expression or pose change as interest signal |
| **Learn from user edits** | Downweight patterns when user deletes proposed segments or drags trims |
| **LLM coach pass** | Optional local/API pass: “best 30s to post” from transcript + scores |
| **Dense dead-air cut-list** | CapCut-style aggressive middle removal beyond today’s jump-cut heuristics |

When shipped, move items into the tables above and drop them from this section.

---

## Explicitly out of scope for now

These were considered for a later “YouTube packager” phase and are **not** shipped:

- Learning from thumbs / drag-fixes, or channel stats
- LLM copy / reorder assist
- Background music ducking under speech
- Full end-card graphics / mid-roll text overlays beyond simple title burn
- Studio description paste pack (analysis now emits thumbnail candidates + keyword pack, but not a full paste bundle)
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

*Last updated: 2026-08-20 — analysis-engine overhaul + "legendary" build: metric-contract layer (~56 params), plugin registry, provenance/diagnostics, preflight QC + watchdog, JSON-Schema validation, a full parameter catalog (vision/audio/NLP/QC + optional ML), a calibration engine with confidence intervals, benchmarks, multimodal drop-risk, explainable top drivers; plus the Editor/scoring + resource-monitoring/neural-voices upgrades.*
