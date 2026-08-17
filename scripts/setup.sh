#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.local/node/bin:${PATH}"

echo "==> Installing Node deps"
cd "$ROOT"
npm install

echo "==> Creating Python venv + deps"
cd "$ROOT/packages/analysis"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Running analysis unit tests"
python tests/test_scoring.py

echo "Setup complete. Run: npm run dev   (or ./scripts/dev.sh)"
