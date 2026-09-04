#!/usr/bin/env bash
# Reset the CaseFile demo to a clean, deterministic state.
#
# Removes generated CSVs + ground_truth.json and regenerates them from seed.
# The audit run and in-memory audit log are recomputed per request by the
# backend, so restarting the server clears investigations/approvals.
#
# Usage: scripts/reset_demo.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "[casefile] removing generated data..."
rm -f backend/data/*.csv backend/data/ground_truth.json backend/data/dataset_meta.json

echo "[casefile] regenerating deterministic dataset..."
python3 -m backend.data.generate --records "${CASEFILE_DATASET_SIZE:-100000}" --seed "${CASEFILE_SEED:-42}"

echo "[casefile] reset complete."
