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

# Heartbeat stamp (ADR-030): on a successful push, tell HA the result
# propagated by setting input_datetime.pool_audit_last_push = now. HA's
# pool_audit_heartbeat automation alerts at 06:00 if this stamp is stale,
# so any silent death of this job (push failure, auditor.py crash, launchd
# no-fire) surfaces as a missed heartbeat. Stamped ONLY on a confirmed push
# so a local-only commit never reads as propagated. Non-fatal if it fails.
stamp_heartbeat() {
    local token
    token="$(tr -d '\r\n' < "$TOKEN_FILE" 2>/dev/null)"
    [[ -n "$token" ]] || { echo "WARN: heartbeat stamp skipped — no token" >&2; return 0; }
    curl -s -o /dev/null -m 10 \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "{\"entity_id\": \"input_datetime.pool_audit_last_push\", \"datetime\": \"$(date '+%Y-%m-%d %H:%M:%S')\"}" \
        "${HA_BASE}/api/services/input_datetime/set_datetime" \
        || echo "WARN: heartbeat stamp POST to HA failed (non-fatal)" >&2
}

# Publish the audit JSON to the dedicated `audit` branch (LRD ADR-036) via
# plumbing — a temp index + commit-tree — so it reaches GitHub for the daily
# review task WITHOUT ever committing to main or touching this working tree's
# branch. Keeps main human-only and keeps the `git pull --ff-only` above from
# ever facing an unpushed local commit. The daily review reads it from the
# audit branch's raw URL. Non-fatal on failure; retried on the next run.
AUDIT_BRANCH="audit"
AUDIT_JSON="${OUT_DIR}/pool_audit_${YESTERDAY}.json"
AUDIT_REPO_PATH="pool/audit/pool_audit_${YESTERDAY}.json"
if [[ -f "$AUDIT_JSON" ]]; then
    cd "$REPO_ROOT"
    if ! git fetch origin "$AUDIT_BRANCH" --quiet 2>&1; then
        echo "WARN: could not fetch origin/${AUDIT_BRANCH}; JSON on disk only, retry next run." >&2
    else
        blob="$(git hash-object -w "$AUDIT_JSON")"
        existing="$(git rev-parse --quiet --verify "origin/${AUDIT_BRANCH}:${AUDIT_REPO_PATH}" 2>/dev/null || true)"
        if [[ "$blob" == "$existing" ]]; then
            stamp_heartbeat
        else
            tmp_index="$(mktemp)"
            if GIT_INDEX_FILE="$tmp_index" git read-tree "origin/${AUDIT_BRANCH}" \
               && GIT_INDEX_FILE="$tmp_index" git update-index --add --cacheinfo "100644,${blob},${AUDIT_REPO_PATH}" \
               && tree="$(GIT_INDEX_FILE="$tmp_index" git write-tree)" \
               && commit="$(git -c user.name='Pool Auditor' -c user.email='audit@dubecars.com' commit-tree "$tree" -p "origin/${AUDIT_BRANCH}" -m "audit: ${YESTERDAY} result")" \
               && git push origin "${commit}:refs/heads/${AUDIT_BRANCH}" --quiet 2>&1; then
                stamp_heartbeat
            else
                echo "WARN: audit-branch push failed; JSON on disk, not propagated, retry next run." >&2
            fi
            rm -f "$tmp_index"
        fi
    fi
else
    echo "WARN: expected audit JSON not found at $AUDIT_JSON" >&2
fi
