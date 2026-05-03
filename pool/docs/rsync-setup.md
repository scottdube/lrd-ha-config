# Pool Log Rsync — Setup

**Status:** Ready to deploy
**Purpose:** Mirror `/config/pool_state_log.csv` from the HA NUC to the Mac on a 5-min interval, so the auditor and Claude have always-fresh data without ad-hoc downloads.
**Related:** `logger-v2.md` Phase 3, `auditor.md`.

---

## Architecture

Pull-based: a launchd agent on the Mac runs `rsync` over SSH against the HA OS NUC every 5 minutes and writes the file into the repo working tree (gitignored).

```
NUC (HA OS)                    Mac
/config/pool_state_log.csv  ── rsync ──>  pool/analysis/pool_state_log_live.csv
                                          ^ gitignored, read by auditor.py
```

Rationale for pull (not push from the NUC):
- HA OS has no native cron; would need a time-pattern automation + `shell_command.rsync` + the SSH addon to host the rsync client. More moving parts than launchd on the Mac.
- Mac is always on (per existing assumption — same machine the repo lives on).
- launchd handles missed runs, log rotation, retry-on-network-failure cleanly.

---

## Prerequisites on the NUC

1. **SSH addon installed & running.** Settings → Apps → Advanced SSH & Web Terminal (community by Frenck). Default port is `22` if configured directly, or `2222` if the official "SSH & Web Terminal" is used. **Verify which port your install uses before running the rsync test.**
2. **`authorized_keys` configured.** The addon's config supports a `authorized_keys` array — paste the Mac's public key there (see step 2 below).
3. **rsync available in addon's shell.** The Frenck addon ships with rsync. Verify with: from the addon's terminal, run `which rsync` — should return `/usr/bin/rsync`.

---

## Setup steps (Mac side)

### 1. Generate dedicated SSH key

```
ssh-keygen -t ed25519 -C "ha-nuc-pool-log-rsync" -f ~/.ssh/ha_nuc_rsync -N ""
```

`-N ""` = no passphrase (required for unattended cron-style runs). The key is read-only-from-Mac; loss of the key file equals loss of access, no further compromise.

### 2. Add the public key to HA OS

```
cat ~/.ssh/ha_nuc_rsync.pub
```

Copy the line. In HA: Settings → Apps → Advanced SSH & Web Terminal → Configuration → `authorized_keys`. Add the public key as a string in the array. Save, restart the addon.

### 3. First-time SSH test (interactive)

```
ssh -i ~/.ssh/ha_nuc_rsync -p PORT root@192.168.11.155 "ls /config/pool_state_log.csv"
```

Replace `PORT` with `22` or `2222` depending on which addon. Confirm the host fingerprint when prompted (this is the only interactive step; subsequent runs are non-interactive once the host is in `~/.ssh/known_hosts`).

If the IP is wrong (memory has 192.168.11.155 but configuration.yaml binds to 192.168.50.11 — see prior IP-disambiguation note), substitute the working address.

### 4. First-time rsync test (manual)

```
rsync -avz -e "ssh -p PORT -i ~/.ssh/ha_nuc_rsync" \
  root@192.168.11.155:/config/pool_state_log.csv \
  /Users/scottdube/code/home-assistant/pool/analysis/pool_state_log_live.csv
```

Should output a single-file transfer report. Verify the local file mirrors the remote file's size and timestamp.

### 5. Install the launchd agent

```
cp /Users/scottdube/code/home-assistant/pool/scripts/launchd/com.scottdube.ha.pool-log-rsync.plist \
   ~/Library/LaunchAgents/

launchctl load ~/Library/LaunchAgents/com.scottdube.ha.pool-log-rsync.plist
```

The plist is preconfigured for port `22`; if you're on `2222`, edit the `ssh -p 22` argument before loading. The agent runs every 300 seconds (5 min) and logs to `~/Library/Logs/ha-pool-rsync.log` (stdout) and `~/Library/Logs/ha-pool-rsync.err.log` (stderr).

Verify it loaded:

```
launchctl list | grep pool-log-rsync
```

### 6. Verify scheduled runs

After 5–10 minutes:

```
ls -la /Users/scottdube/code/home-assistant/pool/analysis/pool_state_log_live.csv
tail -20 ~/Library/Logs/ha-pool-rsync.log
```

The file mtime should advance every ~5 min, and the log should show clean rsync invocations.

---

## Auditor wrapper

`pool/scripts/audit_today.sh` runs the auditor against the live file with today's date:

```
./pool/scripts/audit_today.sh
```

Cron-style: drop into a launchd job or HA shell_command if continuous unattended audit is wanted (deferred until rsync is proven stable).

---

## .gitignore

`pool/analysis/pool_state_log_live.csv` is added to `.gitignore`. The file is short-lived working data; periodic snapshots for historical reference go in `pool/analysis/pool_state_log_YYYY-MM-DD.csv` (committed manually when needed).

---

## Failure modes & checks

| Symptom | Likely cause | Fix |
|---|---|---|
| Empty stderr log, file mtime not advancing | Agent not loaded | `launchctl list \| grep pool-log-rsync`; reload if missing |
| `Permission denied (publickey)` | Key not in NUC's authorized_keys, or addon hasn't picked up the change | Restart Advanced SSH addon |
| `Connection refused` | Wrong port, addon stopped, or NUC unreachable | Check addon status, verify port via Settings → Apps → SSH addon → Configuration |
| `Host key verification failed` | NUC IP changed or addon container regenerated host keys | `ssh-keygen -R 192.168.11.155` then re-test SSH interactively |
| File present but stale | rsync succeeding but logger isn't writing on NUC | Check `automation.pool_state_log_time_pattern` is enabled; check `home-assistant.log` for shell_command errors |
| Auditor sees old data | Stale filesystem cache, or rsync is actually transferring an empty/partial file | `stat pool_state_log_live.csv` to confirm size; compare to NUC via `ssh ... wc -l /config/pool_state_log.csv` |

---

## Phase 4 — Mac mini deployment (always-on mirror + nightly audit)

The MacBook deployment above gets fresh data into the repo for interactive use, but isn't reliable for unattended overnight audits because the MacBook sleeps. The Mac mini deployment runs the same rsync plus the nightly auditor.

Goals:
1. Always-on backup of `/config/pool_state_log.csv`
2. Nightly audit at 00:05 with FAIL pushes via `notify.scott_and_ha`

### Setup (one-time, on the Mac mini)

1. **Clone the repo** to `/Users/scottdube/code/home-assistant` (same path as MacBook so all the launchd plists work without edits). If the username differs on the mini, edit the plist paths accordingly.

2. **Generate dedicated SSH key** for the Mac mini (separate from the MacBook's so each can be revoked independently):

   ```
   ssh-keygen -t ed25519 -C "ha-nuc-pool-log-rsync-mini" -f ~/.ssh/ha_nuc_rsync -N ""
   ```

3. **Add the Mac mini's pubkey to HA** alongside the MacBook key. In HA: Settings → Apps → Advanced SSH & Web Terminal → Configuration → `authorized_keys`, add as a third entry. Save, restart addon.

4. **Test SSH and rsync** from the Mac mini exactly as documented for the MacBook (Steps 3 and 4 above), substituting the mini's hostname/key as needed.

5. **Install the rsync launchd agent** (same plist file, identical paths):

   ```
   cp /Users/scottdube/code/home-assistant/pool/scripts/launchd/com.scottdube.ha.pool-log-rsync.plist \
      ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.scottdube.ha.pool-log-rsync.plist
   ```

6. **Create HA long-lived access token for the auditor**. In HA UI: Profile (bottom left) → Security → Long-Lived Access Tokens → Create. Name it "pool-auditor-mini". Copy the token. On the Mac mini:

   ```
   echo 'PASTE_TOKEN_HERE' > ~/.ha_token
   chmod 600 ~/.ha_token
   ```

7. **Test the audit notification path** by running once manually with `--success-summary` to force a push regardless of FAIL status:

   ```
   python3 /Users/scottdube/code/home-assistant/pool/scripts/auditor.py \
     --date "$(date -v-1d +%Y-%m-%d)" \
     --csv /Users/scottdube/code/home-assistant/pool/analysis/pool_state_log_live.csv \
     --out /Users/scottdube/code/home-assistant/pool/audit \
     --ha-base http://192.168.50.11:8123 \
     --token-file ~/.ha_token \
     --success-summary --print
   ```

   Should produce a "Pool Audit OK" notification on iPhone + HA bell.

8. **Install the nightly audit launchd agent**:

   ```
   cp /Users/scottdube/code/home-assistant/pool/scripts/launchd/com.scottdube.ha.pool-audit-overnight.plist \
      ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.scottdube.ha.pool-audit-overnight.plist
   ```

9. **Verify schedule**:

   ```
   launchctl print gui/$(id -u)/com.scottdube.ha.pool-audit-overnight | grep -E "(next fire|state)"
   ```

   Next fire should be tomorrow at 00:05.

### What runs when

| Time | Job | Effect |
|---|---|---|
| Every 5 min | rsync agent (both MacBook + Mac mini) | Pulls latest `/config/pool_state_log.csv` |
| 00:05 daily | overnight audit (Mac mini only) | Audits previous day, pushes FAIL via scott_and_ha |
| On demand | `audit_today.sh` (either machine) | Audits in-progress day, no notification |

### Long-term snapshot retention

Open question; defer until 30+ days of data accumulate. Options:
- Append daily slices to `pool/analysis/pool_state_log_YYYY-MM-DD.csv` (committed weekly via cron)
- Treat live file as ephemeral, accept loss on Mac mini disk failure
- Periodic dump of the NUC `/config` to a NAS (broader backup strategy, out of scope here)
