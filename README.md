# Garuda

Local-first desktop video analyzer for YouTube creators. Drop in a video, watch live analysis progress, and get a rich report covering hook strength, interestingness, color evenness, visual quality, and Telugu/English audio — plus SRT/VTT captions, YouTube chapters, a keyword/SEO pack, face-aware thumbnail candidates, a retention-risk curve, framing/b-roll analysis, and true LUFS loudness. The **Editor** builds a day project (clips → long + Shorts proposals → preview → export).

See **[FEATURES.md](FEATURES.md)** for what’s shipped vs deferred, including the **future enhancements** roadmap.  
See **[INSTALL.md](INSTALL.md)** for the complete, detailed dependency list (every module, optional groups, models, env vars, per-OS notes).  
See **[SETUP.md](SETUP.md)** for the fresh-machine checklist and **optimum performance** installs (core → neural Voices → pyannote), if present.

## Stack

- **Desktop:** Electron + Vite + React + TypeScript
- **Engine:** Python (OpenCV, librosa, faster-whisper; optional torch/speechbrain for voices)
- **Decode:** Bundled FFmpeg under `tools/ffmpeg/`

## Quick setup

### 1. Prerequisites

| Need | Notes |
|---|---|
| **Node.js 20+** | `node -v` / `npm -v` |
| **Python 3.9+** | `python3 -V` (3.9–3.12 recommended) |
| **Disk** | ~1 GB core; **+2–4 GB** if installing neural voices / ML pack |
| **RAM** | 8 GB works (use Eco); 16 GB+ more comfortable with neural voices |

FFmpeg/ffprobe are **bundled** in `tools/ffmpeg/` — no system install required for normal use.

### 2. Node packages

```bash
cd Garuda          # repo root
npm install
```

### 3. Python analysis engine (required)

```bash
cd packages/analysis
python3 -m venv .venv
source .venv/bin/activate                    # Windows: .venv\Scripts\activate
pip install -r requirements.txt              # core (runs a full report)
pip install -r requirements-accuracy.txt     # optional: PySceneDetect + LUFS
pip install -r requirements-ml.txt           # optional: ML params (aesthetics/emotion/NER)
pip install jsonschema scikit-learn          # optional: report validation + calibration
```

Every report carries a `metrics` block (each parameter with unit, range, method,
confidence, and evidence timestamps), plus `provenance`, `diagnostics` (preflight
QC + capabilities), `dropRiskTimeline`, `topDrivers`, and — once a calibration
model is trained — `predictions` with confidence intervals. See the
[calibration data guide](packages/analysis/garuda_analyze/calibration/data/README.md).

> First ASR run downloads a Whisper model (`tiny`/`base` from Settings). The core
> engine degrades gracefully when optional deps aren't installed. Set
> `GARUDA_WHISPER_DEVICE=cuda` (or `metal`) for a GPU build of faster-whisper;
> drop `face_detection_yunet_2023mar.onnx` into `packages/analysis/models/` to
> enable the YuNet face detector (else it falls back to Haar).

### 4. Neural voice isolation (recommended for Voices)

Without this, Voices uses **STFT MASKED** isolation. With it, **Re-detect** can use SepFormer (neural).

```bash
cd packages/analysis
source .venv/bin/activate
pip install -r requirements-voices.txt
```

Then in the app:

1. **Settings → Download voice models** = on
2. (Optimum) HuggingFace token + accept pyannote model terms on HF
3. Report → **Voices → Re-detect** (first run downloads model weights)

### 5. Run the app

```bash
cd Garuda          # repo root
npm run dev
```

Electron uses `packages/analysis/.venv/bin/python` when that venv exists.

### Verify installs

```bash
cd packages/analysis
source .venv/bin/activate
python -c "import cv2, librosa, faster_whisper; print('core ok')"
python -c "import torch, speechbrain; print('voices ok', torch.__version__)"
```

## CLI analyze (optional)

```bash
cd packages/analysis
source .venv/bin/activate
python -m garuda_analyze \
  --path /path/to/video.mp4 \
  --out /tmp/garuda-out \
  --ffmpeg ../../tools/ffmpeg/ffmpeg \
  --ffprobe ../../tools/ffmpeg/ffprobe
```

Progress is newline-delimited JSON (`progress` / `error` / `done`).

## Tests

```bash
cd packages/analysis
source .venv/bin/activate
python tests/test_scoring.py
python tests/test_engine.py        # degenerate inputs, JSON-safety, SRT, perf
python tests/test_foolproof.py     # golden report + fuzz (valid report or clean error)
python tests/test_metrics.py       # metric-contract shape + schema validation
python tests/test_calibration.py   # calibration train/apply round-trip
python tests/test_pacing_metrics.py
python tests/test_voice_separate.py
python tests/test_editor_propose.py
```

## Packaging

```bash
cd apps/desktop
npm run dist
```

`electron-builder` packs renderer/main and copies:

- `packages/analysis` → `resources/analysis`
- `tools/ffmpeg` → `resources/ffmpeg`

On end-user machines, create/activate a venv inside the packaged analysis folder (or ship a frozen binary later). Dev prefers `packages/analysis/.venv/bin/python`.

## Data locations

| What | Where |
|---|---|
| Reports | Electron `userData/garuda/reports/` |
| Edit projects | Electron `userData/garuda/projects/` |
| Settings | Electron `userData/garuda/` |

These do **not** travel with the git repo — copy `userData` if you need the same reports on another machine.
