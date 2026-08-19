# Garuda — install & optimum performance

Use this on a **fresh machine**, or when Voices / analysis feels slow or stuck on STFT MASKED.

---

## Performance tiers

| Tier | Install | What you get |
|---|---|---|
| **Minimum** | Node + Python venv + `requirements.txt` | Analyze, Editor, Report, STFT voice masks |
| **Recommended** | Minimum + `requirements-voices.txt` | Neural SepFormer isolation (NEURAL in Voices) |
| **Optimum** | Recommended + `pyannote.audio` + HF token + app settings below | Best speaker labeling + neural stems + full FX path |

Disk: ~1 GB core · **+2–4 GB** neural voices · **+1–2 GB** pyannote / Whisper caches on first use.  
RAM: 8 GB works (use **Eco**); **16 GB+** is comfortable for neural Voices + deep propose.

---

## 1. Clone & system tools

- [ ] **Node.js 20+**
- [ ] **Python 3.9–3.12** (`python3 -V`)
- [ ] Clone the Garuda repo
- [ ] Confirm bundled FFmpeg: `tools/ffmpeg/ffmpeg` and `tools/ffmpeg/ffprobe`

No system FFmpeg install is required for normal use.

---

## 2. App (always)

```bash
cd Garuda
npm install
```

```bash
cd packages/analysis
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
```

| Package (via `requirements.txt`) | Used for |
|---|---|
| `numpy`, `opencv-python-headless` | Frames, faces, visual metrics |
| `librosa`, `soundfile` | Audio features, pacing, STFT voices |
| `faster-whisper` | ASR / language mix (model downloads on first use) |
| `pedalboard` | Voice FX (gain, EQ, compress, etc.) |

---

## 3. Voices neural stack (recommended → optimum)

Without this, Voices stays on **STFT MASKED**. With it, **Re-detect** can show **NEURAL**.

```bash
cd packages/analysis
source .venv/bin/activate
pip install -r requirements-voices.txt
```

| Package | Used for |
|---|---|
| `torch`, `torchaudio` | Neural audio runtime |
| `speechbrain` | SepFormer 2-speaker (+ cascade for 3–4) |

### Optimum add-on — better speaker diarization

```bash
pip install pyannote.audio
```

Then:

1. Create a [Hugging Face](https://huggingface.co/) account and token  
2. Accept terms for gated models (e.g. [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1))  
3. In Garuda → **Settings → HuggingFace token**  
4. **Settings → Download voice models** = **on**  
5. Report → **Voices → Re-detect** (first run downloads SepFormer / pyannote weights)

---

## 4. App settings for best results

| Setting | Optimum choice | Why |
|---|---|---|
| **Download voice models** | On | Allows SepFormer / pyannote downloads |
| **HuggingFace token** | Set (if pyannote installed) | Gated diarization models |
| **Whisper model** | `base` (or `small` if RAM allows) | Better ASR than `tiny`; slower |
| **Processing speed** | **Balanced** or **High** on 16 GB+; **Eco** on 8 GB / laptop battery | Same analysis depth; only CPU throttle changes |
| **Resource guard** | Leave on (Auto Eco ok) | Avoids freeze under Critical load |

During a heavy Voices / propose job: plug in power, close browsers, watch the titlebar CPU/RAM ticker.

---

## 5. Run

```bash
cd Garuda
npm run dev
```

Electron prefers `packages/analysis/.venv/bin/python` when the venv exists.

---

## 6. Verify (copy-paste)

```bash
cd packages/analysis && source .venv/bin/activate

python -c "import cv2, librosa, soundfile, faster_whisper, pedalboard; print('core ok')"

python -c "import torch, torchaudio, speechbrain; print('voices neural ok', torch.__version__)"

python -c "import pyannote.audio; print('pyannote ok')"   # optimum only
```

Smoke in the app:

- [ ] Analyze a short clip (progress + ETA)  
- [ ] Report → Metrics / Voices — after neural install, Re-detect should show **NEURAL** when possible  
- [ ] Editor → Quick propose; optionally Deep propose + Speech (ASR)

---

## What is *not* in git

| Item | Notes |
|---|---|
| `node_modules/` | Re-run `npm install` |
| `packages/analysis/.venv/` | Re-create venv + pip installs |
| Whisper / SepFormer / pyannote caches | Re-download on first use |
| Reports & edit projects | Electron `userData/garuda/` — copy that folder to move data |

---

## Troubleshooting performance

| Symptom | Fix |
|---|---|
| Voices shows **STFT MASKED** only | Install `requirements-voices.txt`; turn **Download voice models** on; Re-detect |
| Voices job “already running” / no bar after leaving screen | Stay on Voices or Cancel; progress reconnects on return after recent app update |
| Critical load / RAM ~100% | Force Eco, Stop Garuda job, or cancel Voices; close other apps |
| First neural Re-detect hangs a long time | Normal — model download; keep Download voice models on and wait |
| ASR weak / empty language mix | Raise Whisper model in Settings; ensure first download finished |

More product detail: **[README.md](README.md)** · Feature matrix: **[FEATURES.md](FEATURES.md)**.
