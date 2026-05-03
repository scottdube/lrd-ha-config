#!/usr/bin/env bash
# Run the pool auditor against yesterday's data and push notification on FAIL.
#
# Designed for unattended overnight execution (launchd at 00:05 local).
#
# Assumes:
#   - rsync agent is running and pool/analysis/pool_state_log_live.csv is fresh
#   - python3 is on PATH
#   - HA long-lived access token is in ~/.ha_token (mode 600)
#   - notify.scott_and_ha group is deployed in HA
#
# Output: JSON to pool/audit/, mobile push + bell entry on FAIL via the
# scott_and_ha notify group.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIVE_CSV="${REPO_ROOT}/pool/analysis/pool_state_log_live.csv"
OUT_DIR="${REPO_ROOT}/pool/audit"
YESTERDAY="$(date -v-1d +%Y-%m-%d)"
TOKEN_FILE="${HOME}/.ha_token"
HA_BASE="http://192.168.50.11:8123"

if [[ ! -f "$LIVE_CSV" ]]; then
    echo "ERROR: live CSV not found at $LIVE_CSV" >&2
    exit 1
fi

if [[ ! -f "$TOKEN_FILE" ]]; then
    echo "ERROR: HA token file not found at $TOKEN_FILE" >&2
    echo "Create a long-lived access token in HA (Profile -> Security) and" >&2
    echo "save it to $TOKEN_FILE with mode 600." >&2
    exit 1
fi

cd "$REPO_ROOT"
if ! git pull --ff-only --quiet 2>&1; then
    echo "WARN: git pull failed; running audit against last-known code" >&2
fi

mkdir -p "$OUT_DIR"

python3 "${REPO_ROOT}/pool/scripts/auditor.py" \
    --date "$YESTERDAY" \
    --csv "$LIVE_CSV" \
    --out "$OUT_DIR" \
    --ha-base "$HA_BASE" \
    --token-file "$TOKEN_FILE" \
    --notify-target scott_and_ha \
    --print
