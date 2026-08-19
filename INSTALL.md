# Garuda — Installation & Dependencies

Complete, detailed list of everything required to run, develop, and package
Garuda (the local desktop video analyzer + Python analysis engine).

Garuda has two halves:

- **Desktop app** — Electron + Vite + React + TypeScript (Node/npm).
- **Analysis engine** — Python (`packages/analysis`), invoked as a subprocess.

The engine is built around a **core** that always runs, plus **optional
dependency groups** that light up extra parameters and degrade gracefully when
absent (a missing optional package never breaks a run).

---

## 1. System prerequisites

| Software | Version | Required? | Notes |
|---|---|---|---|
| **Node.js** | 20 LTS or newer (>=18) | Yes (desktop app) | Electron 34 bundles Node 20 at runtime; you need Node to install/build. |
| **npm** | 9+ (ships with Node) | Yes | `pnpm`/`yarn` also work but the repo uses npm workspaces. |
| **Python** | 3.9+ (3.10 / 3.11 recommended) | Yes (engine) | `requires-python = ">=3.9"`. |
| **pip** | latest (`python -m pip install --upgrade pip`) | Yes | |
| **FFmpeg + FFprobe** | 5.x / 6.x | Yes (decode/audio) | Bundle under `tools/ffmpeg/` **or** install system-wide (the engine falls back to `PATH`). |
| **Git** | any | Recommended | To clone the repo. |
| **C/C++ build tools** | platform default | Only for some optional deps | Most Python wheels are prebuilt; `numba`/`torch` ship wheels. |

**Disk budget (rough):**
- Base app + `node_modules` + core Python venv: ~1–1.5 GB.
- First ASR run downloads a Whisper model: ~145 MB (`base`).
- Optional **ML** pack (`torch`, `transformers`, ONNX models): +2–5 GB.
- Optional **Voices** pack (`torch`, `pyannote`, `speechbrain`): +2–5 GB.

---

## 2. Desktop app — Node/npm modules

Installed with a single `npm install` at the repo root (npm workspaces installs
`apps/desktop`).

**Runtime dependencies** (`apps/desktop/package.json`):

| Module | Version | Purpose |
|---|---|---|
| `react` | ^19.2.8 | UI |
| `react-dom` | ^19.2.8 | UI DOM renderer |
| `framer-motion` | ^13.1.0 | Animations/transitions |

**Dev / build dependencies:**

| Module | Version | Purpose |
|---|---|---|
| `electron` | ^34.2.0 | Desktop runtime |
| `electron-vite` | ^3.0.0 | Dev server + build for main/preload/renderer |
| `electron-builder` | ^26.15.3 | Packaging (dmg/zip/AppImage/nsis) |
| `vite` | ^6.1.0 | Bundler |
| `@vitejs/plugin-react` | ^4.3.4 | React plugin for Vite |
| `typescript` | ^5.7.3 | Types/compile |
| `@types/node` | ^22.13.4 | Node type defs |
| `@types/react` | ^19.2.18 | React type defs |
| `@types/react-dom` | ^19.2.4 | React DOM type defs |

```bash
# from the repo root
npm install
```

> The `electron` package runs a postinstall that downloads the Electron binary
> (needs network + write access to the Electron cache, e.g. `~/Library/Caches/electron`).

---

## 3. Analysis engine — Python modules

Create an isolated virtual environment under `packages/analysis/.venv`.

```bash
cd packages/analysis
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
```

### 3a. Core (required — a full report runs with just these)

`requirements.txt`:

| Module | Version | Purpose |
|---|---|---|
| `numpy` | >=1.24,<2.1 | Numerics |
| `opencv-python-headless` | >=4.8,<5 | Frame decode, vision metrics, face detection (headless = no GUI libs) |
| `librosa` | >=0.10,<0.11 | Audio features (RMS, spectral, pitch) |
| `soundfile` | >=0.12 | WAV I/O |
| `faster-whisper` | >=1.0,<2 | Local speech-to-text (Telugu/English) |

```bash
pip install -r requirements.txt
```

**Notable transitive dependencies pip resolves automatically:** `scipy`,
`numba`, `llvmlite`, `audioread`, `pooch`, `soxr`, `joblib`, `lazy_loader`
(via librosa); `ctranslate2`, `tokenizers`, `huggingface-hub`, and (for the VAD
filter) `onnxruntime` (via faster-whisper).

### 3b. Accuracy upgrades (optional, recommended)

`requirements-accuracy.txt` — better cuts + true loudness. Engine falls back to
histogram cuts / RMS loudness if absent.

| Module | Version | Purpose |
|---|---|---|
| `scenedetect` | >=0.6,<0.7 | PySceneDetect content-aware scene cuts |
| `pyloudnorm` | >=0.1 | EBU R128 integrated loudness (LUFS) |

```bash
pip install -r requirements-accuracy.txt
```

### 3c. ML parameter pack (optional)

`requirements-ml.txt` — aesthetics/shot-type/emotion/object + transformer NLP.
Metrics report `unavailable` until both the package **and** the model file exist.

| Module | Version | Purpose |
|---|---|---|
| `onnxruntime` | >=1.16 | Run bundled ONNX models |
| `torch` | >=2.0 | Deep-learning runtime |
| `torchaudio` | >=2.0 | Audio ML ops |
| `transformers` | >=4.40 | Sentiment / NER / topic models |

```bash
pip install -r requirements-ml.txt
# torch tip (CPU-only wheels):
# pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```

### 3d. Report validation + Calibration engine (optional, recommended)

Not in a requirements file (installed directly or via extras below):

| Module | Version | Purpose |
|---|---|---|
| `jsonschema` | >=4.0 | Validate `report.json` against the schema (engine has a minimal fallback if absent) |
| `scikit-learn` | >=1.2 | Calibration models (retention/CTR regressors + confidence intervals); brings `joblib` |

```bash
pip install jsonschema scikit-learn
```

### 3e. Voices module (optional, heavy)

`requirements-voices.txt` — speaker separation / diarization / enhancement.

| Module | Version | Purpose |
|---|---|---|
| `pedalboard` | >=0.9.0 | Parametric audio FX |
| `torch` | >=2.0 | DL runtime |
| `torchaudio` | >=2.0 | Audio ML |
| `pyannote.audio` | >=3.1 | Diarization (gated — needs a HuggingFace token) |
| `speechbrain` | >=1.0 | Source separation |
| `deepfilternet` | >=0.5 | Noise suppression |

```bash
pip install -r requirements-voices.txt
```

### 3f. Install groups via extras (alternative to requirements files)

`pyproject.toml` declares the same optional groups as extras:

```bash
cd packages/analysis
pip install -e .                                   # core only
pip install -e ".[accuracy,validation,calibration]"  # recommended set
pip install -e ".[accuracy,ml,validation,calibration,voices]"  # everything
```

---

## 4. Models (downloaded/placed separately)

| Model | Needed for | How to get it |
|---|---|---|
| Whisper (`tiny`/`base`/`small`) | ASR transcript | Auto-downloads on first run (~145 MB for `base`) to the HuggingFace cache. Size set in Settings. |
| `face_detection_yunet_2023mar.onnx` | YuNet DNN faces (accuracy) | Download from the [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) into `packages/analysis/garuda_analyze/models/`. Falls back to Haar if absent. |
| `aesthetic_nima.onnx`, `shot_type.onnx`, `emotion_fer.onnx`, `object_tags.onnx` | ML vision params | Place under `packages/analysis/garuda_analyze/models/` per `models/models.json`. Absent → those metrics are `unavailable`. |

---

## 5. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ELECTRON_RUN_AS_NODE` | (unset) | **Must be unset** when launching the app. If set to `1`, Electron boots as plain Node and the window fails to open. |
| `GARUDA_WHISPER_DEVICE` | `cpu` | faster-whisper device (`cpu`, `cuda`, ...). |
| `GARUDA_WHISPER_COMPUTE` | `int8` (cpu) / `float16` (gpu) | Compute type for the Whisper model. |
| `GARUDA_YUNET_MODEL` | (unset) | Absolute path to a YuNet ONNX model (overrides the `models/` lookup). |
| `GARUDA_SEED` | `1234` | Deterministic RNG seed (stamped into `report.provenance`). |

---

## 6. Calibration data (optional — powers predictions)

To turn heuristics into confidence-bounded predictions, drop labeled YouTube
outcomes under `packages/analysis/garuda_analyze/calibration/data/` and train.
Format and commands: see
[calibration/data/README.md](packages/analysis/garuda_analyze/calibration/data/README.md).

```bash
python -m garuda_analyze.calibration.train \
  --data packages/analysis/garuda_analyze/calibration/data \
  --reports "<userData>/garuda/reports" \
  --out packages/analysis/garuda_analyze/calibration/model
```

---

## 7. FFmpeg / FFprobe

The app looks for, in order:

1. `tools/ffmpeg/ffmpeg` and `tools/ffmpeg/ffprobe` (Windows: `.exe`) — **bundled** path.
2. `ffmpeg` / `ffprobe` on the system `PATH`.

Install one of them:

```bash
# macOS
brew install ffmpeg
# Debian/Ubuntu
sudo apt-get install ffmpeg
# Windows (winget)
winget install Gyan.FFmpeg
```

…or copy static `ffmpeg`/`ffprobe` binaries into `tools/ffmpeg/` (they are
`.gitignore`d and get bundled into packaged builds via `extraResources`).

---

## 8. Quick setup (scripts)

```bash
./scripts/setup.sh     # npm install + create core Python venv + run a test
./scripts/dev.sh       # launch the app in dev mode
```

Or manually:

```bash
npm install                                   # node deps
cd packages/analysis && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt               # (+ optional groups above)
cd ../.. && npm run dev                        # launch
```

---

## 9. Verify the install

```bash
# Engine tests (from packages/analysis, venv active)
python tests/test_scoring.py
python tests/test_engine.py         # degenerate inputs, JSON-safety, SRT, perf
python tests/test_foolproof.py      # golden report + fuzz
python tests/test_metrics.py        # metric-contract shape + schema validation
python tests/test_calibration.py    # calibration train/apply round-trip
python tests/test_editor_propose.py

# Desktop app
npm run dev
```

---

## 10. Build / package a distributable

```bash
cd apps/desktop
npm run dist        # electron-builder -> release/  (dmg+zip / AppImage / nsis)
```

`electron-builder` copies `packages/analysis` → `resources/analysis` (excluding
`__pycache__`, `.venv`, `tests`) and `tools/ffmpeg` → `resources/ffmpeg`. On
end-user machines, create/activate a Python venv inside the packaged analysis
folder (or ship a frozen engine binary in a later release).

---

## 11. Troubleshooting

- **Electron window won't open / "protocol undefined":** `unset ELECTRON_RUN_AS_NODE` before `npm run dev`.
- **Electron postinstall failed to download:** ensure network + write access to the Electron cache, then `npm rebuild electron` (or re-run `npm install`).
- **`torch` install is huge / wrong build:** use the CPU index URL shown in 3c, or match your CUDA version.
- **`opencv-python` vs `-headless`:** use `opencv-python-headless` (no GUI libs) — already pinned; don't install both.
- **First analysis is slow / downloads a model:** that's the one-time Whisper download; subsequent runs use the cache.
- **ML/accessibility metrics show `unavailable`:** the optional package and/or model file isn't present — see sections 3c and 4. This is expected, not an error.
