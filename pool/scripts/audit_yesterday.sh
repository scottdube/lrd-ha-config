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

# Silent-failure fix (2026-06-11, ADR-030): auditor.py exits 1 whenever it
# records any FAIL (auditor.py:778) — a valid audited result, not a script
# error. Under `set -e` that nonzero exit aborted this script before the
# commit/push below, so FAIL nights never propagated to GitHub (auditor was
# dark 2026-05-29 -> 2026-06-10). Suspend `set -e` across the auditor call;
# the `[[ -f "$AUDIT_JSON" ]]` guard below is the real "did we get a result"
# check, and a genuine crash writes no JSON and falls through to its WARN.
set +e
python3 "${REPO_ROOT}/pool/scripts/auditor.py" \
    --date "$YESTERDAY" \
    --csv "$LIVE_CSV" \
    --out "$OUT_DIR" \
    --ha-base "$HA_BASE" \
    --token-file "$TOKEN_FILE" \
    --notify-target scott_and_ha \
    --print
set -e

# Commit + push the audit JSON so it propagates to GitHub for the daily
# Claude review scheduled task to read via raw URL. pool/audit/ was
# un-gitignored 2026-05-21 specifically to enable this flow. Failure to
# push is non-fatal — the JSON is still on the Mac mini and the FAIL push
# notification already fired (if applicable); we'll retry on the next run.
AUDIT_JSON="${OUT_DIR}/pool_audit_${YESTERDAY}.json"
if [[ -f "$AUDIT_JSON" ]]; then
    cd "$REPO_ROOT"
    if ! git diff --quiet "$AUDIT_JSON" 2>/dev/null || ! git ls-files --error-unmatch "$AUDIT_JSON" >/dev/null 2>&1; then
        git add "$AUDIT_JSON"
        git -c user.name="Pool Auditor" -c user.email="audit@dubecars.com" \
            commit -m "audit: ${YESTERDAY} result" --quiet
        if ! git push origin main --quiet 2>&1; then
            echo "WARN: git push failed; audit JSON is on disk but not propagated. Will retry next run." >&2
        fi
    fi
else
    echo "WARN: expected audit JSON not found at $AUDIT_JSON" >&2
fi
