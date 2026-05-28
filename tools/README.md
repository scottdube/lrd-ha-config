# tools/

Standalone utilities that support the LRD HA stack but aren't part of HA
core or any HA package. Each tool is self-contained.

## Z-Wave node health monitoring

Captures structured per-node RF telemetry over time so we can quantify
mesh changes (added repeaters, healed routes, dying batteries, weak
links) instead of relying on point-in-time Z-Wave JS UI snapshots.

Pattern + rationale: `docs/decisions/021-zwave-node-health-monitoring.md`.

### Components

| File | Purpose | Runs on |
|---|---|---|
| `zwave_health_probe.py` | Calls `node.check_lifeline_health` via the zwave-js-server WebSocket against a target node, summarises the result, appends a row to a per-node CSV. | Mac mini |
| `launchd/com.scottdube.ha.zwave-health-probe-node-XXX.plist` | macOS launchd schedule for one monitored node. | Mac mini |
| HA automation `zwave_health_keepalive_<area>` (in `automations.yaml`) | 30-min `zwave_js.ping` against a specific entity to keep HA's per-frame RSSI sensor populated. Only needed for mains nodes with low natural traffic. Not needed for battery FLiRS devices (locks generate traffic on every use) OR for mains nodes once they have a healthy neighbor that itself generates organic traffic. Currently no instances deployed — the original lamp-post-node-55 keepalive was deleted 2026-05-26 once ZEN05 (node 56) provided enough background traffic on the same route. | HA |

### Currently monitored nodes

| Node | Device | Schedule | Rounds | CSV |
|---|---|---|---|---|
| 55 | Fibaro FGD-212 lamp post dimmer | 4h | 5 | `~/zwave-health/node-55.csv` |
| 008 | Kwikset 916 deadbolt (front door) | 6h | 3 | `~/zwave-health/node-008.csv` |
| 038 | Kwikset 916 deadbolt (lanai door) | 12h | 3 | `~/zwave-health/node-038.csv` |

Schedules vary because the cost of probing a node depends on its power
profile. Mains-powered routing nodes cost essentially nothing — probe
often. Battery FLiRS devices burn beam-wake energy per probe round —
probe sparingly, especially below 50% battery.

### CSV schema

`zwave_health_probe.py` writes these columns:

| Column | Meaning |
|---|---|
| `timestamp_utc` | ISO8601 timestamp of probe start, UTC |
| `node` | Target node ID |
| `rounds` | Number of probe rounds |
| `rating` | Overall lifeline health rating, 0–10 (10 = perfect) |
| `worst_round_rating` | Minimum per-round rating across all rounds |
| `worst_route_changes` | Max route changes observed in any single round |
| `max_latency_ms` | Maximum round-trip latency across rounds |
| `total_failed_pings` | Sum of failed pings across all rounds |
| `worst_min_powerlevel` | Worst (lowest) min-powerlevel margin across rounds |
| `worst_snr_margin_db` | Lowest SNR margin (dB) across rounds |
| `raw_summary_json` | Full Z-Wave JS response, preserved for re-parsing |

### Adding a new node

1. **Pick the schedule** based on power profile:
   - Mains routing node, high RF importance → 4h / 5 rounds
   - Mains routing node, low RF importance → 8h / 3 rounds
   - Battery FLiRS at >50% battery → 6h / 3 rounds
   - Battery FLiRS at <50% battery → 12h / 3 rounds
   - Sleeping (non-FLiRS) battery node → not currently supported; the probe will return an error if the node is asleep when the probe runs
2. **Copy** an existing plist to `tools/launchd/com.scottdube.ha.zwave-health-probe-node-NNN.plist`
3. **Edit** the Label, `--node`, `--rounds`, `--csv`, `StartInterval`, log paths
4. **Commit + push** the new plist
5. **On the Mac mini:** `git pull --ff-only`. If this is the first probe being installed, also create the venv:
   ```
   python3 -m venv ~/.venv/zwave-health
   ~/.venv/zwave-health/bin/pip install websockets
   ```
   The Mac mini's Homebrew-managed Python blocks `pip3 install --user` (PEP 668), so the venv is the canonical install path. All plists invoke `~/.venv/zwave-health/bin/python3` directly.
6. **Install the launchd:**
   ```
   ln -sf ~/code/home-assistant/tools/launchd/com.scottdube.ha.zwave-health-probe-node-NNN.plist \
          ~/Library/LaunchAgents/
   launchctl bootstrap gui/$(id -u) \
          ~/Library/LaunchAgents/com.scottdube.ha.zwave-health-probe-node-NNN.plist
   ```
7. **Verify** the first row lands in the CSV (RunAtLoad fires the probe immediately on bootstrap).
8. **Optional — add a keepalive ping in HA** for mains nodes with low natural traffic, mirroring the existing `zwave_health_keepalive_lamp_post` automation in `automations.yaml`. Skip for battery devices.

### Removing a node

```
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.scottdube.ha.zwave-health-probe-node-NNN.plist
rm ~/Library/LaunchAgents/com.scottdube.ha.zwave-health-probe-node-NNN.plist
```

Keep the CSV for historical context; gitignored (not in repo).

### Manual one-off probe

```
python3 ~/code/home-assistant/tools/zwave_health_probe.py --node N --rounds 5 --csv /tmp/probe.csv
```

Useful when troubleshooting a specific incident — pin a CSV path you'll
discard after analysis.

### When the probe fails

The script exits with code 2 on failure and writes a single line to
stderr. The launchd log files capture stderr. Common failures:

- **`ConnectionRefusedError`** — Z-Wave JS app WS isn't bound to the
  expected interface. Override `--uri` in the plist's `ProgramArguments`
  to whichever interface the addon listens on, or change the addon
  config to bind to all interfaces.
- **`asyncio.TimeoutError`** — node didn't respond within 180s. For
  FLiRS devices this can happen if the device is in a transient
  unresponsive state (e.g. mid-firmware-update or freshly excluded).
- **`set_api_schema failed`** — zwave-js-server schema version
  incompatible with the connected driver. Update `SCHEMA_VERSION` in
  `zwave_health_probe.py` to match the driver's max schema.

## Whole-home energy audit (ADR-026)

Daily anomaly + opportunity scan over the Vue 3 long-term statistics.
Mirrors the pool auditor pattern: silent on clean, push-notifies on
findings, appends one row per day to a durable CSV for trending.

Pattern + rationale: `docs/decisions/026-whole-home-energy-audit.md`.

### Components

| File | Purpose | Runs on |
|---|---|---|
| `energy_audit.py` | Pulls yesterday's per-circuit kWh + overnight power means from HA, runs 11 anomaly checks + Monday weekly-opportunity scan, appends to `~/energy-audit/energy_audit.csv`, push-notifies via `notify.scott_and_ha` on findings. | Mac mini |
| `energy_pull_stats.py` | Ad-hoc helper: dumps `recorder/statistics_during_period` for the canonical energy entity set to JSON for offline analysis. | MacBook |
| `energy_analyze.py` | Ad-hoc trend analyzer over a stats JSON: daily totals, top consumers, HVAC split, hour-of-day profile. | MacBook |
| `launchd/com.scottdube.ha.energy-audit.plist` | Schedules `energy_audit.py` at 06:30 EDT daily on Mac mini, with `git pull --ff-only` first so pushes to main are picked up on the next tick. | Mac mini |

### Anomaly checks

| ID | Signal | Threshold |
|---|---|---|
| A1 | Daily whole-home total above rolling baseline | > 1.25× 7d rolling avg |
| A2 | Daily whole-home total below baseline (data loss flag) | < 0.60× 7d rolling avg |
| A3 | Overnight baseload spike | `whole_home_power` 02:00-04:00 EDT mean > 2500 W |
| A4 | Always-on creep | `always_on_power` overnight mean > 1.50× 7d median |
| A5/A8 | Per-system HVAC runaway | Air 1/Air 2 > 40 kWh/day; Garage MS > 25 kWh/day |
| A6 | Pool subpanel high | > 30 kWh/day |
| A7 | Water heater high | > 30 kWh/day |
| A9 | Vue unmonitored fraction out of range | Panel A > 2%, Panel B > 8% |
| A10 | Panel total suspiciously low (Vue offline) | Panel A < 20 kWh, Panel B < 5 kWh per day |
| A11 | OmniLogic pump est > Vue pool subpanel (cross-val) | OmniLogic > Vue × 1.15 |

### Opportunity scan (Mondays only)

| ID | Signal |
|---|---|
| O1 | Any of whole-home / HVAC / pool / water heater / garage MS shifted >20% week-over-week |
| O3 | `whole_home_power - always_on_power` overnight gap exceeds 800 W non-HVAC, suggesting always-on template under-counts |

Thresholds are tunable in the top of `energy_audit.py` — review after ~30 days of CSV history when seasonal patterns are clear.

### Vacation profile (v1.1.0)

When `input_boolean.vacation` is on (ADR-012), the audit switches to a
tighter, mode-aware threshold profile. The full table lives in
ADR-026's 2026-05-27 amendment, but in short:

- **Tightened absolute thresholds:** A3 baseload 2500 W → 1200 W, A5 Air-system 40 → 15 kWh/day. Disabled A10 (low panel) and Monday O1 (WoW) for 14 days after a mode flip.
- **New vacation-only checks:**
  - **V1** Water heater > 1.0 kWh/day — should be off
  - **V2** Garage MS > 8.0 kWh/day — dehumidify-only ceiling
  - **V3** Whole-home > 80 kWh/day — vacation-mode-not-engaged guard
  - **V4** Pool subpanel **< 1.0 kWh/day** — stagnant-pool floor (P1 condition)
  - **V5** Cooktop > 0.3, oven > 0.3, kitchen stove > 2.0 kWh — "left on?"
  - **V6** Dryer > 0.3 kWh/day — dryer running
  - **V7** Recirc pump mean power > 10 W — should be off
- **Mode-aware rolling avg:** A1/A2/A4 compute over same-mode rows only. Guard: A1/A2 need ≥3 same-mode rows, A4 needs ≥5.
- **Mode-flip notification:** one-time push the day the flag changes.

Backfill historical days with explicit mode:

```
python3 tools/energy_audit.py --for-date 2026-05-14 --vacation-override off --no-notify --print-clean
```

### CSV schema (`~/energy-audit/energy_audit.csv`)

| Column | Meaning |
|---|---|
| `audit_date` | Local LRD date being audited (yesterday at run time) |
| `whole_home_kwh` | Panel A + Panel B daily kWh |
| `hvac_kwh` | Air 1 + Air 2 + Garage MS daily kWh (summed from underlying Vue circuits, NOT the `air_X_total_daily_energy` templates — those double-count via `recorder/statistics_during_period`; see ADR-026 §Gotchas) |
| `pool_kwh` | Vue Panel A C1 pool subpanel |
| `water_heater_kwh` | Vue Panel A C3 |
| `garage_ms_kwh` | Vue Panel A C10 |
| `air_1_kwh` / `air_2_kwh` | condenser + handler sums |
| `always_on_kwh` | ADR-020 `always_on_daily_energy` template |
| `panel_a_kwh` / `panel_b_kwh` | Panel totals |
| `panel_a_unmon_pct` / `panel_b_unmon_pct` | Vue unmonitored as fraction of panel total |
| `baseload_w_overnight` | `whole_home_power` mean, 02:00-04:00 EDT |
| `always_on_w_overnight` | `always_on_power` mean, 02:00-04:00 EDT |
| `rolling_avg_kwh` | 7-day rolling avg of `whole_home_kwh` from prior audit rows |
| `pool_vue_kwh` | Same as `pool_kwh` (alias for the cross-val column pair) |
| `pool_omni_kwh_est` | OmniLogic filter pump mean power × 24h (estimate, pump-only) |
| `finding_count` | Number of findings this run |
| `findings` | Pipe-separated finding strings |
| `audit_version` | `energy-audit-X.Y.Z` |

### Install on Mac mini

```
ssh mac-mini-lrd
cd ~/code/home-assistant && git pull --ff-only
ln -sf ~/code/home-assistant/tools/launchd/com.scottdube.ha.energy-audit.plist \
       ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) \
       ~/Library/LaunchAgents/com.scottdube.ha.energy-audit.plist
```

The Mac mini already has the `~/.venv/zwave-health` venv with `websockets` installed (shared with the Z-Wave probes) and `~/.ha_token` (shared with the pool auditor).

### Backfill historical days

```
cd ~/code/home-assistant
for d in $(seq -f "2026-05-%02g" 14 26); do
    ~/.venv/zwave-health/bin/python3 tools/energy_audit.py \
        --for-date "$d" --no-notify --print-clean
done
```

### Ad-hoc trend analysis (MacBook)

```
python3 tools/energy_pull_stats.py \
    --token ~/Documents/Claude/Projects/home-assistant/.ha-token \
    --days 14 --out /tmp/energy_stats.json
python3 tools/energy_analyze.py --stats /tmp/energy_stats.json
```

## Other tools

- **`rename_entities.py`** — bulk entity_id rename via the HA WebSocket
  API. Used 2026-05-20 to rename the Jasco fan controllers from auto-
  generated stems to function-first IDs.
