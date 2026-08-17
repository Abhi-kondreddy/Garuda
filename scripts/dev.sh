#!/usr/bin/env bash
# Convenience launcher for Garuda desktop app
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PATH="${HOME}/.local/node/bin:${PATH}"
cd "$ROOT"
if [[ ! -d packages/analysis/.venv ]]; then
  echo "Python venv missing. Run: cd packages/analysis && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi
npm run dev
