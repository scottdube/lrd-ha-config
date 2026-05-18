# OmniLogic

Hayward pool controller. Two integrations running side-by-side. See ADR-001 for the why.

---

## Local integration (control)

- **HACS repo:** [`cryptk/haomnilogic-local`](https://github.com/cryptk/haomnilogic-local)
- **Status:** Stable
- **Current version:** `1.0.4`
- **Communication:** UDP, direct LAN to controller
- **Controller IP:** `192.168.11.19` (DHCP reservation in UniFi)
- **Network:** IoT VLAN

### What it controls
- Pump (variable speed via `number.set_value` on speed entity)
- Heater (`water_heater.omnilogic_pool_heater`) — Hayward HP31005T (heat AND cool, 7.0–7.8 kW @ 208/230V, recommended flow 42.7 gpm)
- Waterfall (`valve.omnilogic_pool_waterfall` — see ADR-004)
- Chlorinator (`number.set_value` on timed percent entity)
- Pool light
- Water temperature
- Air temperature

### What it does NOT expose
- **Heater power consumption.** The integration parses filter pump power telemetry but no heater power. Estimated via runtime × HEATER_RATED_POWER_W in `pool/scripts/state_logger.py`. Real measurement requires external instrumentation (CT clamp on the heat pump's circuit, or whole-panel monitor like Emporia Vue 2).

### Entity naming convention
`*.omnilogic_pool_*` (vs cloud's `*.pool_pool_*`). Easy to confuse. Always grep for `omnilogic_pool_` when wiring blueprints.

### Known issues
- **Version churn.** Schema/domain changes have occurred between releases historically. Check release notes; audit blueprint for entity references after every upgrade. Audit unavailable entities in registry.
- **Stale entities post-rename.** When devices are re-included or domains change, ghost entities persist with `_2` suffix. Manual cleanup required.

### Open
- **Midnight burst of `Failed to update data from OmniLogic` errors** (discovered 2026-05-01). Local coordinator throws ~18 errors clustered between 00:27 and 01:00 EDT, plus single isolated errors scattered through 01:00–07:00. Evening hours (17:00–23:59) show zero errors. Cloud integration unaffected throughout. Pattern is consistent with controller-side scheduled housekeeping (log rotation, cloud telemetry sync, etc.) rather than network instability. Needs multi-night confirmation. Full analysis: `scratch/omnilogic-local-midnight-burst-2026-05-01.md`.

### Resolved
- **WiFi packet loss to controller (~30-40% per ping test).** Resolved 2026-04-30 by temporary ethernet run (zero errors over 7 hours). Permanent in-wall Cat 6 run completed by Shepard Electric on 2026-05-16. Soffit-dangling temp cable retired.
- **Local API wedge from ethernet disturbance (2026-05-16, ~11:00 EDT).** Controller's local UDP listener stopped ACKing `GET_TELEMETRY` packets after the Cat 6 was disconnected at ~11:19 EDT during the in-wall run. Cloud channel and ICMP unaffected throughout (controller's outbound TCP stack recovered cleanly; only the inbound UDP listener got stuck). HA restart bought ~12 min of working state before re-wedging — log shows clean polling from 21:53 to 22:04:33, then 6 retries with no ACK, then graceful UDP teardown ("connection lost: None"). Resolved by power-cycling the controller via the pool sub-panel breaker at the main service panel. Plausible mechanism: controller firmware's UDP protocol state machine doesn't recover from an L1 link interruption (inferred from single incident; not vendor-confirmed). Diagnostic log: `scratch/omnilogic-local-2026-05-16-ethernet-wedge.log`.
- **MSP↔peripheral comm-loss to VSP and OPLMP (2026-05-17, ~08:00 EDT).** OmniLogic UI displayed `MSP_DEV_COMM_LOSS,Comm Loss Device:VSP HUA:10-01-15-49-9a` and `MSP_DEV_COMM_LOSS,Comm Loss Device:OPLMP HUA:a1-44-15-1b-56`. From HA's perspective the integration was healthy — toggle commands round-tripped cleanly through `unavailable → off → on`, `local_filter_state_enum` transitioned `Off → Priming → On`, `local_filter_speed` updated to 55. But `sensor.omnilogic_pool_filter_pump_power` stayed at 0 W and `local_water_temp` stayed `unknown` because no physical equipment was actually responding. Failure was at the proprietary 4-wire Hayward bus between the MSP and the two specific peripheral devices, not at any layer HA can see. Resolved by power-cycling the controller via the pool sub-panel breaker (same physical action as the 2026-05-16 wedge, but for a different reason — HUA re-handshake on boot per Hayward TSG-OL150c). Plausible triggers: surge damage from the prior day's thunderstorm, comm-module stress from the 22:12 breaker cycle, age-related comm-board degradation; not disambiguated by this incident. Watch-item: if `MSP_DEV_COMM_LOSS` recurs within 30 days, schedule VSP/OPLMP comm-board replacement rather than continuing to power-cycle through it. Full reasoning in ADR-019.
- **GitHub issue #173.** Resolved by maintainer in newer integration releases.

---

## Cloud integration (monitoring only)

- **HACS repo:** [`djtimca/haomnilogic`](https://github.com/djtimca/haomnilogic)
- **Status:** Stable
- **Communication:** Cloud relay through Hayward servers
- **Authentication:** Hayward app credentials
- **Used for:** ORP, salt level, pH (sensors not exposed by local integration)

### Entity naming convention
`*.pool_pool_*` (note the doubled "pool"). Not used in blueprint service calls — sensors only.

### Known issues
- Internet-dependent. State updates pause during outages.
- Polling interval — confirm against current docs. Roughly minutes.

---

## Cross-integration notes

- **Both integrations create separate entity sets** for the same physical equipment. Don't delete one assuming the other will pick it up.
- **Dashboards reference both.** Cloud row shows ORP/salt/pH. Local row shows everything else.
- **Watchdog dashboard** monitors cloud availability. Confirmed: when cloud is firewalled, watchdog fires after a delay (cloud uses persistent connection that takes time to drop).

---

## Setup quirks

- **Temperature sensor naming.** If renamed in the Hayward app, the cloud integration won't find them. Defaults are `airTemp` and `waterTemp`.
- **Static IP for controller.** DHCP reservation in UniFi. Critical for local integration to reach it reliably.
- **Heat pump in AUTO mode.** Per ADR-002, the heat pump owns cycling. Confirm AUTO is set on the unit itself, not just in HA.
- **Power-cycle the controller after any ethernet disturbance.** Cable swap, switch port move, switch reboot — anything that interrupts L1 to the controller. The local UDP listener doesn't recover gracefully from a link-down event even though ICMP, ARP, and the outbound cloud channel do. Observed 2026-05-16 — cable disconnect for in-wall run wedged the local listener; controller continued cloud-reachable and ping-reachable but silent on UDP 5858. Fastest path to recover without going outside: kill the pool sub-panel breaker at the main service panel for ~30 seconds, then restore. UDP listener takes 60–120 seconds to come back after the controller display lights up.

---

## Failure-mode triage

Three distinct failure modes have been observed within a 24-hour window. Classes 1 and 2 are fixed by a controller power-cycle; class 3 requires physical intervention. **Triage step 1: ping the controller (`ping -c 3 192.168.11.19`).** That disambiguates class 3 from 1/2. Then check the OmniLogic UI alarms panel to disambiguate class 1 from class 2. Full reasoning in ADR-019.

| ICMP | Symptom in HA | Symptom in OmniLogic UI | Class | Severity | Recovery |
|---|---|---|---|---|---|
| ✓ Reachable | Sensors stale, integration logs `Failed to update data`, eventually entities go `unavailable` | Usually clean (no alarms) | 1 — Integration↔MSP wedge | Read-side stale | Try integration reload first. If no recovery in ~60 sec, breaker-cycle. |
| ✓ Reachable | State changes ack cleanly in HA but `local_filter_power = 0` with pump claimed on; `local_water_temp` stays `unknown` despite pump claimed on | `MSP_DEV_COMM_LOSS,Comm Loss Device:<device> HUA:<address>` alarm(s) | 2 — MSP↔peripheral comm-loss | Write-side dead (chlorinator may dose into dead leg — worst for salt cell) | Breaker-cycle directly (HUA re-handshake on boot). Do NOT reload integration first — integration is healthy. |
| ✗ Unreachable | All entities `unavailable` simultaneously; ICMP fails from both HA and any workstation on the IoT VLAN | Likely inaccessible (UI may not load either) | 3 — Physical/network | Controller off the network entirely | Physical triage at equipment pad. Display lit = network-side (reseat RJ45 at controller, check switch port). Display dark = power-side (check pool sub-panel breaker, then controller PSU). |

**Detection layers (all three implemented in `packages/pool/pool_health_watcher.yaml`):**

- **Proactive class 1:** `automation.pool_alert_on_omnilogic_integration_wedge` — state trigger on `switch.omnilogic_pool_filter_pump` going `unavailable` for 10+ min. Tag: `pool_integration_wedge`.
- **Proactive class 2:** `automation.pool_alert_on_pump_on_but_no_power` — inline `platform: template` trigger (`for: 2m`) on pump_state=on AND power<50W. Gated by `pool_integration_recovering` (ADR-016) + `pool_service_lockout` (ADR-011). Tag: `pool_pump_no_power`.
- **Proactive class 3:** `automation.pool_alert_on_omnilogic_controller_unreachable` — state trigger on `binary_sensor.pool_controller_reachable` going `off` for 5+ min. Tag: `pool_controller_unreachable`.
- **Retrospective (class 2):** auditor assertion P5 (`pump_on_actually_drawing_power`) in `pool/scripts/auditor.py` — same logic as proactive class 2, runs nightly on the daily slice.

All three proactive automations route through `notify.scott_and_ha` with distinct iOS notification tags so they collapse into separate threads.

### Ping binary_sensor setup (`binary_sensor.pool_controller_reachable`)

The class-3 watcher references this entity, which is configured via the HA UI rather than YAML because the ping integration's YAML configuration was deprecated in HA 2023.12 (triggers HA Repair warnings on modern versions).

Setup:
1. Settings → Devices & Services → Add Integration
2. Search "Ping (ICMP)" and select it
3. Host: `192.168.11.19`
4. Name: `Pool Controller Reachable` (this exact name — HA's slugifier produces `binary_sensor.pool_controller_reachable`)
5. Count: 3
6. Scan interval: 30 (seconds)

The integration's config entry lives in `.storage/core.config_entries` (not version-controlled). If `.storage` is ever rebuilt, repeat these steps to restore the entity; the watcher automation in `packages/pool/pool_health_watcher.yaml` will start working again as soon as the entity exists.

---

## Useful commands

When the integration goes weird, in order of escalation:

0. **Check the OmniLogic web UI alarms panel FIRST** — if `MSP_DEV_COMM_LOSS` alarms are present, this is a class-2 failure (see Failure-mode triage). Skip directly to step 6; reloading the integration won't help and the integration may already report healthy.
1. **Reload integration** — Settings → Devices & Services → OmniLogic Local → Reload
2. **Restart HA** — handles deeper state issues
3. **Audit registry** — Settings → Devices & Services → entities, filter `omnilogic`, look for `unavailable`
4. **Check controller link** — UniFi → Client Devices → confirm controller is on ethernet, check switch port for errors
5. **Diagnostic dump** — for new issues, integration → ⋮ menu → Download diagnostics
6. **Power-cycle the controller** — if reload, restart, and link checks all pass but local UDP is still silent (cloud + ping still working), the controller's UDP listener is wedged. Also the recovery for `MSP_DEV_COMM_LOSS` alarms (HUA re-handshake on boot). Kill the pool sub-panel breaker at the main service panel for ~30 seconds, then restore. UDP listener takes 60–120 seconds to recover after the display lights up. Required after any ethernet disturbance (see Setup quirks).
