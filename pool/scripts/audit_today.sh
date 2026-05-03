#!/usr/bin/env bash
# Run the pool auditor against today's slice of the live (rsync'd) CSV.
#
# Assumes:
#   - rsync agent is running and pool/analysis/pool_state_log_live.csv is fresh
#   - python3 is on PATH
#
# Output: JSON to pool/audit/, plus stdout summary.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIVE_CSV="${REPO_ROOT}/pool/analysis/pool_state_log_live.csv"
OUT_DIR="${REPO_ROOT}/pool/audit"
TODAY="$(date +%Y-%m-%d)"

if [[ ! -f "$LIVE_CSV" ]]; then
    echo "ERROR: live CSV not found at $LIVE_CSV" >&2
    echo "Check that the rsync launchd agent is loaded and running." >&2
    exit 1
fi

mkdir -p "$OUT_DIR"

python3 "${REPO_ROOT}/pool/scripts/auditor.py" \
    --date "$TODAY" \
    --csv "$LIVE_CSV" \
    --out "$OUT_DIR" \
    --no-notify \
    --print
