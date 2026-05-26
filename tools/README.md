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

## Other tools

- **`rename_entities.py`** — bulk entity_id rename via the HA WebSocket
  API. Used 2026-05-20 to rename the Jasco fan controllers from auto-
  generated stems to function-first IDs.
