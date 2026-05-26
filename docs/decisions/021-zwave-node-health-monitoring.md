# ADR-021 — Z-Wave node health monitoring as durable infrastructure

**Status**: accepted 2026-05-23

## Context

The Z-Wave fleet at LRD has produced enough RF incidents in the last
~30 days that ad-hoc "open Z-Wave JS UI and look at the Network Graph"
diagnostics aren't enough:

- **Lamp post Fibaro FGD-212** went `unavailable` 2026-05-22, required
  full re-inclusion 2026-05-23 (now node 55). Post-reinclusion signal is
  marginal. Zooz ZEN05 outdoor repeater ordered to close the RF gap.
- **Toilet fan Zooz ZEN75** (formerly node 256) failed on Z-Wave LR,
  required Classic re-include as node 51 on 2026-05-20 — single-link
  failures in the bathroom RF environment, not a device failure.
- **Kwikset 916 lanai (node 038)** documented `neighbors:[]` / weak LWR
  pattern with battery drain attributed to retry storm. Battery at 30%
  per current-state.md (2026-05-22).

The pattern across these incidents is that the controller-side
diagnostic snapshot (Network Graph, node statistics page) reflects a
moment in time. What we actually want is **time-series telemetry** so
we can see drift before it becomes a failure, and quantify the impact
of mesh interventions (adding a repeater, healing a node, re-including
on a different protocol).

Z-Wave JS itself has the right primitive: `node.check_lifeline_health`
returns a structured result with rating, route changes, latency, failed
pings, SNR margin, and powerlevel margin. That output is rich enough to
spot trends if captured periodically.

HA's Z-Wave JS integration also exposes per-frame RSSI as a diagnostic
sensor on every node — disabled by default, but once enabled the
recorder + LTS captures it for free. The sensor only updates when the
node communicates, so for low-natural-traffic nodes (like a lamp post
that only fires sunrise/sunset) we need to generate keepalive traffic
to make the sensor useful.

## Decision

Stand up Z-Wave node health monitoring as **durable infrastructure**,
not as one-off baselining for the lamp post incident.

The components:

1. **`tools/zwave_health_probe.py`** — Python script that connects to
   zwave-js-server WebSocket, runs `node.check_lifeline_health` against
   a target node, appends a structured row to a per-node CSV. CLI args
   for node, rounds, URI, CSV path. Runs on the Mac mini (always-on,
   already host for the pool auditor + rsync).

2. **Per-node launchd schedules** at
   `tools/launchd/com.scottdube.ha.zwave-health-probe-node-NNN.plist`.
   One plist per monitored node. Schedule and rounds tuned to the
   node's power profile (mains vs battery FLiRS).

3. **HA keepalive automation** for mains nodes with low natural traffic,
   sending `zwave_js.ping` every 30 min to populate the per-frame RSSI
   diagnostic sensor. Currently only `zwave_health_keepalive_lamp_post`
   (node 55) — added because the lamp post only naturally communicates
   twice a day at sunrise/sunset. Most other mains nodes have enough
   organic traffic that they don't need keepalives.

4. **CSVs live at `~/zwave-health/node-NNN.csv`** on the Mac mini.
   Gitignored, ephemeral storage (rebuildable from the Z-Wave JS
   statistics layer if lost, but historical timeline would be gone).

5. **Initial node coverage:**
   - Node 55 (Fibaro lamp post) — 4h / 5 rounds. Highest-RF-importance
     property-edge node, currently marginal signal.
   - Node 008 (Kwikset 916 front door) — 6h / 3 rounds. Battery 100%,
     mains-equivalent observation cadence acceptable.
   - Node 038 (Kwikset 916 lanai door) — 12h / 3 rounds. Battery 30%
     with documented mesh weakness. Conservative cadence avoids
     contributing to drain while battery is low; retarget to 6h after
     battery replacement.

## What this ADR explicitly defers

- **Coverage of all 34 nodes.** Initial set targets the documented
  problem children. Extending to other nodes is `tools/README.md`'s
  "Adding a new node" runbook — no architecture changes needed.
- **Automated alerting on degradation.** No threshold-triggered push
  notifications yet. CSV inspection is manual until we have ~30 days
  of baseline data to set meaningful per-node thresholds. Future
  iteration: a separate auditor pattern that diffs the rolling 7d
  mean against the 30d mean per node and alerts on N-sigma deviations.
  Same shape as `pool/scripts/auditor.py`.
- **Dashboards.** No Lovelace card for these CSVs yet. Manual `pandas`
  / spreadsheet analysis is sufficient until coverage stabilises.
- **Battery-impact validation on FLiRS nodes.** The decision to probe
  node 038 every 12h vs not at all is a judgment call — the marginal
  drain from 18 wake events/day is likely small but unmeasured. Watch
  `sensor.<lock>_battery_level` slope for 1-2 weeks; if drain
  accelerates noticeably, back off further or pause until replacement.
- **Sleeping (non-FLiRS) battery nodes.** Ecolink tilt sensors and any
  other pure-sleeping device can't be probed on demand — the lifeline
  health check requires the node to be awake. Out of scope for v1.
- **Z-Wave LR coverage.** Mixed-protocol monitoring isn't structurally
  different but no LR devices currently exist on the network. Trivial
  to add when one shows up.

## Validation — node 55 / ZEN05 case study (2026-05-23 → 2026-05-26)

The lamp post Fibaro FGD-212 (node 55) is the inaugural test case for
this monitoring pattern. Three days of data spanning before and after
the Zooz ZEN05 outdoor repeater install (node 56, 2026-05-25 ~12:34Z)
validates that the metrics captured here cleanly surface mesh changes.

**Pre-ZEN05 baseline (12 probes, 5/23 16:37Z → 5/25 13:28Z):**

| Metric | Range / Avg |
|---|---|
| `max_latency_ms` | 5,607–11,555ms, avg ~8,030ms |
| `total_failed_pings` per 50-ping probe | 2–38, avg ~21 |
| `worst_route_changes` | 0–3 |
| `worst_snr_margin_db` | -21 to +33 (volatile) |
| numNeighbors in route | 7 |

**Post-ZEN05, settled (7 scheduled probes, 5/25 20:06Z → 5/26 20:25Z):**

| Metric | Range / Avg |
|---|---|
| `max_latency_ms` | 60–350ms, avg ~129ms (60ms floor hit in 5 of 7) |
| `total_failed_pings` per 25-ping probe | 0 in every probe |
| `worst_route_changes` | 0 in every probe |
| per-round `snrMargin` | mostly 50–70 dB; occasional single-round dips |
| numNeighbors in route | 2 (direct + ZEN05 hop) |

**Observations the data made visible that a Network Graph snapshot
wouldn't:**

1. **Mesh-settling tail after heal.** The first post-install probe at
   12:34Z (immediately after the single-node heal on node 55) showed
   76% failure rate — worse than baseline. The 15:56Z probe (~3 hours
   later) was the first to show the structural improvement. A graph
   snapshot at 12:35Z would have shown the new route through node 56
   but masked that the route hadn't stabilized yet. The CSV
   time-series caught the transient clearly.
2. **Single-round SNR dips don't indicate degradation.** The
   `worst_snr_margin_db` column reflects the worst single round per
   probe. Several post-install probes show -16 to -2 dB in this
   column despite per-round SNR averaging 50-70 dB. Reading the raw
   per-round data is necessary to distinguish "transient
   single-round noise" from "actual link weakness."
3. **`failedPingsController = 10` sentinel masks meaningful rating.**
   Across all probes for both the FGD-212 and the Kwikset 916 (node
   008), the `failedPingsController` field is always 10 and `rating`
   is always 0. The sentinel value indicates the controller-side
   ping test wasn't able to use Powerlevel CC on these nodes. Look
   at the other fields (latency, failedPingsNode, snrMargin,
   routeChanges, numNeighbors) — not the top-level rating.
4. **FW update visible in the data.** Scott applied a Zooz FW update
   2.0 → 2.30 on node 56 sometime in the 12:18Z–16:21Z window on
   5/26. The latency floor of 60ms held in every probe before that
   window; the two probes after (16:21Z, 20:25Z) show 250–350ms max
   latency — still excellent but slightly off the floor. Consistent
   with the repeater briefly leaving the route during FW reboot,
   then re-inserting. Useful as a future signature for "non-routing
   transient event."

After the ZEN05 was confirmed stable, the temporary
`zwave_health_keepalive_lamp_post` automation in `automations.yaml`
was deleted (2026-05-26) — node 56's organic traffic provides enough
RF activity for HA's per-frame RSSI sensor on node 55 to populate
without forced 30-min pings. Future low-natural-traffic mains nodes
may still want the keepalive pattern; see `tools/README.md`.

## Why this shape

**Why probe via direct zwave-js-server WebSocket and not HA service
call?** Two reasons. First, the HA Z-Wave JS integration's WebSocket
command surface for health check is less stable across HA versions
than the underlying zwave-js-server protocol — going to the source
avoids one layer of churn. Second, this script is intentionally
HA-independent so it can survive HA restarts mid-probe and doesn't
need an HA long-lived token (the auditor's pattern). Tradeoff: needs
the zwave-js-server port (3000) reachable from the Mac mini.

**Why launchd on the Mac mini and not an HA-side automation?** The
probe takes 30-60s and produces structured CSV output. HA automations
are awkward for both the I/O wait and the CSV append. The Mac mini
already hosts the pool auditor + rsync agent + overnight audit
launchd, so the operational pattern is familiar.

**Why per-node CSVs rather than one combined file?** Different
schedules per node would produce ragged rows. Separate files are
trivially joinable in pandas if cross-node analysis is needed. Each
file stays manageable size — at 4h cadence × 1 year × ~3KB raw_json =
~13MB/year per high-frequency node.

**Why keep `raw_summary_json` in every row?** The summarized columns
encode my current understanding of which fields matter. If the
zwave-js Library evolves the response shape or I want to extract a
field I didn't think to capture (like per-hop route detail), the raw
column lets me re-parse historical rows without losing data. Cheap
insurance.

**Why the 30-minute HA keepalive ping cadence?** Empirical: the HA
per-frame RSSI sensor is one-shot per received frame. With 30-min
pings we get ~48 samples/day, plus organic traffic. With 60-min we'd
get ~24 — still adequate but less resolution. 15-min would be overkill
and add small but real RF noise to the mesh.

## Trade-offs

**Battery drain on FLiRS probe targets is real but unmeasured.** A
beam-wake on a FLiRS device costs measurable energy. At 3 rounds × ~3
pings = 9 wake events per probe, 2 probes/day for node 038 = 18 events/
day. Compared to a Kwikset 916's typical 5-15 user-initiated wake
events per day (lock/unlock + status reports), the probe contribution
is non-trivial. Mitigated by the conservative schedule below 50%
battery; flagged in the deferred-items list for empirical validation.

**Mac mini single point of failure.** If the Mac mini dies, monitoring
stops. The data captured to date is in CSVs on the Mac mini — they get
rsynced to the MacBook via the existing pool log rsync pattern? No, the
current rsync is for the pool log specifically. Future work: extend the
rsync to also pull `~/zwave-health/` so the MacBook has a backup. Or
just accept that monitoring data is ephemeral; the Z-Wave JS Statistics
panel survives independently.

**The script depends on `websockets` Python library on the Mac mini.**
Adds one pip dependency vs the auditor's pure stdlib + requests. Trivial
to install (`pip3 install --user websockets`) but worth noting.

**Schema version skew.** zwave-js-server's protocol schema evolves. The
script pins `SCHEMA_VERSION = 34` at the top. If the driver gets ahead
of this, `set_api_schema` should still negotiate down to a compatible
version (servers maintain backward compat in their min schema), but if
that fails the constant needs bumping. Errors surface in the launchd
err.log.

## References

- Z-Wave JS lifeline health check API:
  https://zwave-js.github.io/node-zwave-js/#/api/node?id=checklifelinehealth
- zwave-js-server protocol:
  https://github.com/zwave-js/zwave-js-server
- HA Z-Wave JS service docs:
  https://www.home-assistant.io/integrations/zwave_js/
- Related ADRs: ADR-014 (Battery health tracking — separately addresses
  battery decay observability via HACS Battery Notes + logger v2).
- Companion file: `tools/README.md` runbook for adding/removing nodes.
