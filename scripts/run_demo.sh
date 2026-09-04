#!/usr/bin/env bash
# Run the CaseFile demo backend.
#
# Regenerates the deterministic dataset and starts the FastAPI engine on :8000.
# The Vite frontend dev server is managed separately (see AGENTS.md), so this
# script only owns the Python backend.
#
# Prerequisites (on the user's machine, with network pip):
#   python3 -m venv .venv && source .venv/bin/activate
#   pip install -r backend/requirements.txt
#
# Usage: scripts/run_demo.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Dataset size / seed are configurable (defaults: 100000 canonical txns, seed 42).
RECORDS="${CASEFILE_DATASET_SIZE:-100000}"
SEED="${CASEFILE_SEED:-42}"

echo "[casefile] generating deterministic dataset (${RECORDS} canonical txns, seed ${SEED})..."
python3 -m backend.data.generate --records "$RECORDS" --seed "$SEED"

echo "[casefile] starting FastAPI backend on http://localhost:8000 ..."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
