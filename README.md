# Garuda

Local-first desktop video analyzer for YouTube creators. Drop in a video, watch live analysis progress, and get a rich report covering hook strength, interestingness, color evenness, visual quality, and Telugu/English audio. The **Editor** builds a day project (clips → long + Shorts proposals → preview → export).

See **[FEATURES.md](FEATURES.md)** for what’s shipped vs deferred, including the **future enhancements** roadmap (interestingness, propose, export quality).  
See **[SETUP.md](SETUP.md)** for the fresh-machine checklist and **optimum performance** installs (core → neural Voices → pyannote).

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
| **Disk** | ~1 GB core; **+2–4 GB** if installing neural voices |
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
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> First ASR run downloads a Whisper model (`tiny`/`base` from Settings).

### 4. Neural voice isolation (recommended for Voices)

Without this, Voices uses **STFT MASKED** isolation. With it, **Re-detect** can use SepFormer (neural). Full **optimum** stack (pyannote + settings): **[SETUP.md](SETUP.md)**.

```bash
cd packages/analysis
source .venv/bin/activate
pip install -r requirements-voices.txt
# Optimum diarization (optional):
# pip install pyannote.audio
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
python tests/test_voice_separate.py
python tests/test_pacing_metrics.py
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
