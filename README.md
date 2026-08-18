# Garuda

Local-first desktop video analyzer for YouTube creators. Drop in a video, watch live analysis progress, and get a rich report covering hook strength, interestingness, color evenness, visual quality, and Telugu/English audio. The **Editor** builds a day project (clips → long + Shorts proposals → preview → export).

See **[FEATURES.md](FEATURES.md)** for what’s shipped vs deferred.

## Stack

- **Desktop:** Electron + Vite + React + TypeScript
- **Engine:** Python (OpenCV, librosa, faster-whisper)
- **Decode:** Bundled FFmpeg under `tools/ffmpeg/`

## Setup

### 1. Node

```bash
export PATH="$HOME/.local/node/bin:$PATH"   # if using the local Node install
cd /Users/abhi/Desktop/Garuda
npm install
```

### 2. Python analysis engine

```bash
cd packages/analysis
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> First ASR run downloads a Whisper model (`base` by default).

### 3. Run the app

```bash
cd /Users/abhi/Desktop/Garuda
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
