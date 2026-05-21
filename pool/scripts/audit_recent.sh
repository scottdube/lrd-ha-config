#!/usr/bin/env bash
# Pool recent-state audit wrapper.
#
# Runs the recent-audit Python script. Designed for unattended cadence
# (launchd every 3 hours). Silent on clean, push notification on problems.
#
# Assumes:
#   - rsync agent is running and pool/analysis/pool_state_log_live.csv is fresh
#   - python3 is on PATH
#   - HA long-lived access token at ~/.ha_token (mode 600), same token used by
#     audit_yesterday.sh
#   - notify.scott_and_ha group deployed in HA

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIVE_CSV="${REPO_ROOT}/pool/analysis/pool_state_log_live.csv"

if [[ ! -f "$LIVE_CSV" ]]; then
    echo "ERROR: live CSV not found at $LIVE_CSV" >&2
    exit 1
fi

# Pull latest auditor code before each run so any push to main is picked up
# on the next 3-hour tick. Mirrors audit_yesterday.sh pattern.
cd "$REPO_ROOT"
if ! git pull --ff-only --quiet 2>&1; then
    echo "WARN: git pull failed; running audit against last-known code" >&2
fi

python3 "${REPO_ROOT}/pool/scripts/audit_recent.py" \
    --csv "$LIVE_CSV" \
    --print-clean
