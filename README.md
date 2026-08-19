# Garuda

Local-first desktop video analyzer for YouTube creators. Drop in a video, watch live analysis progress, and get a rich report covering hook strength, interestingness, color evenness, visual quality, and Telugu/English audio — plus SRT/VTT captions, YouTube chapters, a keyword/SEO pack, face-aware thumbnail candidates, a retention-risk curve, framing/b-roll analysis, and true LUFS loudness. The **Editor** builds a day project (clips → long + Shorts proposals → preview → export).

See **[FEATURES.md](FEATURES.md)** for what’s shipped vs deferred.

## Stack

- **Desktop:** Electron + Vite + React + TypeScript
- **Engine:** Python (OpenCV, librosa, faster-whisper)
- **Decode:** Bundled FFmpeg under `tools/ffmpeg/`

## Setup

> Full, detailed dependency list (system prerequisites, every npm/Python module,
> optional groups, models, env vars, per-OS notes): see **[INSTALL.md](INSTALL.md)**.

### 1. Node

```bash
export PATH="$HOME/.local/node/bin:$PATH"   # if using the local Node install
cd /path/to/Garuda
npm install
```

### 2. Python analysis engine

```bash
cd packages/analysis
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt              # core (runs a full report)
pip install -r requirements-accuracy.txt     # optional: PySceneDetect + LUFS
pip install -r requirements-ml.txt           # optional: ML params (aesthetics/emotion/NER)
pip install -r requirements-voices.txt       # optional: Voices module (heavy)
pip install jsonschema scikit-learn          # report validation + calibration engine
```

Every report now carries a `metrics` block (each parameter with unit, range,
method, confidence, and evidence timestamps), plus `provenance`, `diagnostics`
(preflight QC + capabilities), `dropRiskTimeline`, `topDrivers`, and — once a
calibration model is trained — `predictions` with confidence intervals. See the
[calibration data guide](packages/analysis/garuda_analyze/calibration/data/README.md).

> First ASR run downloads a Whisper model (`base` by default). The core engine
> degrades gracefully when the optional accuracy deps aren't installed. Set
> `GARUDA_WHISPER_DEVICE=cuda` (or `metal`) to use a GPU build of faster-whisper;
> drop `face_detection_yunet_2023mar.onnx` into `packages/analysis/models/` to
> enable the YuNet face detector (else it falls back to Haar).

### 3. Run the app

```bash
cd /path/to/Garuda
npm run dev
```

### 4. Analyze from CLI (optional)

```bash
cd packages/analysis
source .venv/bin/activate
python -m garuda_analyze \
  --path /path/to/video.mp4 \
  --out /tmp/garuda-out \
  --ffmpeg ../../tools/ffmpeg/ffmpeg \
  --ffprobe ../../tools/ffmpeg/ffprobe
```

Progress is streamed as newline-delimited JSON (`progress` / `error` / `done`).

## Tests

```bash
cd packages/analysis
source .venv/bin/activate
python tests/test_scoring.py
python tests/test_engine.py        # degenerate inputs, JSON-safety, SRT, perf
python tests/test_foolproof.py     # golden report + fuzz (valid report or clean error)
python tests/test_metrics.py       # metric-contract shape + schema validation
python tests/test_calibration.py   # calibration train/apply round-trip
python tests/test_editor_propose.py
```

## Packaging

```bash
cd apps/desktop
npm run dist
```

`electron-builder` packs the renderer/main bundles and copies:

- `packages/analysis` → `resources/analysis`
- `tools/ffmpeg` → `resources/ffmpeg`

On end-user machines, create/activate a venv inside the packaged analysis folder (or ship a frozen binary in a later release). For local development, Electron prefers `packages/analysis/.venv/bin/python`.

## Reports

Saved under Electron `userData/garuda/reports/<id>/report.json` and reopenable from the home screen.
