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
- **Used for:** salt level (smoothed + instant), per-equipment alarm binary_sensors, plus a few sensors not exposed by the local integration. **Correction 2026-05-22:** the LRD install does NOT have ORP or pH probes installed at the controller — those are optional OmniLogic Pro hardware add-ons that this site doesn't have. Earlier text claiming cloud exposes ORP/pH was overstated and reflected the upstream integration's possible-entity set, not the installed-and-exposed set. Verified entity inventory at LRD: `sensor.pool_pool_chlorinator_average_salt_level`, `sensor.pool_pool_chlorinator_instant_salt_level`, `sensor.pool_pool_chlorinator_setting`, `binary_sensor.pool_pool_{chlorinator,filter_pump,heater_heater,light,waterfall}_alarm`, `binary_sensor.omnilogic_pool_pool_flow` (local integration, despite the cloud-style naming). No ORP, no pH.

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
- **Power-cycle the controller after any ethernet disturbance.** Cable swap, switch port move, switch reboot — anything that interrupts L1 to the controller. The local UDP listener doesn't recover gracefully from a link-down event even though ICMP, ARP, and the outbound cloud channel do. Observed 2026-05-16 — cable disconnect for in-wall run wedged the local listener; controller continued cloud-reachable and ping-reachable but silent on UDP 5858. **Two procedures** (see ADR-019 Recovery section for full discussion):
    - **Preferred — staged power-cycle at equipment-pad breakers:** controller breaker off + pump breaker off, then controller breaker on FIRST, wait 20-30 sec, then pump breaker on. Lets MSP finish booting before equipment loads ask it to re-handshake their HUAs. Empirically more reliable once comm boards are degraded (2026-05-17 evening + 2026-05-18 morning — simultaneous failed, staged succeeded).
    - **Acceptable — simultaneous pool-sub-panel breaker at indoor main service panel:** kill for ~30 sec, restore. Works on healthy boards, useful when equipment-pad access is impractical. UDP listener takes 60–120 sec to come back after the display lights up.

---

## Failure-mode triage

Three distinct failure modes have been observed within a 24-hour window. Classes 1 and 2 are fixed by a controller power-cycle; class 3 requires physical intervention. **Triage step 1: ping the controller (`ping -c 3 192.168.11.19`).** That disambiguates class 3 from 1/2. Then check the OmniLogic UI alarms panel to disambiguate class 1 from class 2. Full reasoning in ADR-019.

| ICMP | Symptom in HA | Symptom in OmniLogic UI | Class | Severity | Recovery |
|---|---|---|---|---|---|
| ✓ Reachable | Sensors stale, integration logs `Failed to update data`, eventually entities go `unavailable` | Usually clean (no alarms) | 1 — Integration↔MSP wedge | Read-side stale | Try integration reload first. If no recovery in ~60 sec, breaker-cycle. |
| ✓ Reachable | State changes ack cleanly in HA but `local_filter_power = 0` with pump claimed on; `local_water_temp` stays `unknown` despite pump claimed on | `MSP_DEV_COMM_LOSS,Comm Loss Device:<device> HUA:<address>` alarm(s) | 2 — MSP↔peripheral comm-loss | Write-side dead (chlorinator may dose into dead leg — worst for salt cell) | Breaker-cycle directly (HUA re-handshake on boot). Do NOT reload integration first — integration is healthy. |
| ✗ Unreachable | All entities `unavailable` simultaneously; ICMP fails from both HA and any workstation on the IoT VLAN | Likely inaccessible (UI may not load either) | 3 — Physical/network | Controller off the network entirely | Physical triage at equipment pad. Display lit = network-side (reseat RJ45 at controller, check switch port). Display dark = power-side (check pool sub-panel breaker, then controller PSU). |
| ✗ Unreachable at `192.168.11.19` but UniFi Clients page shows the Hayward MAC connected on a *different* network/IP | All OmniLogic Local entities `unavailable`; integration UI shows "Failed setup, will retry: No ACK received for message type GET_TELEMETRY" | OmniLogic web/app may still work (cloud channel is independent of local LAN IP) | **3c — Port VLAN drift** | Controller is fine but UniFi switch port reverted its Native VLAN, putting MSP on wrong network. Triggered by UDM auto-reboot OR UI port disable/enable. | Set port's Native VLAN back to IoT (4). **Do NOT bounce the port** — same code path causes the revert again. With VNO-checked Fixed IP reservation, MSP self-recovers at next DHCP renewal (could be hours). To force immediate recovery: power-cycle the MSP at the equipment-pad breakers (MSP has no soft-reboot option). See ADR-019 Addendum 2026-05-22. |

**Detection layers (all three implemented in `packages/pool/pool_health_watcher.yaml`):**

- **Proactive class 1:** `automation.pool_alert_on_omnilogic_integration_wedge` — template trigger on `{{ states('switch.omnilogic_pool_filter_pump') == 'unavailable' }}` with `for: 10m`. Tag: `pool_integration_wedge`. **Note (2026-05-18):** originally used a state trigger with `to: "unavailable"`; that did not fire across a 10-hour overnight unavailable period, validating that HA's state-trigger semantics for `to: "unavailable"` are unreliable. Switched to template trigger, which re-evaluates on every state change and is robust to startup-initialized-as-unavailable edge cases.
- **Proactive class 2:** `automation.pool_alert_on_pump_on_but_no_power` — inline `platform: template` trigger (`for: 2m`) on pump_state=on AND power<50W. Gated by `pool_integration_recovering` (ADR-016) + `pool_service_lockout` (ADR-011). Tag: `pool_pump_no_power`.
- **Proactive class 3:** `automation.pool_alert_on_omnilogic_controller_unreachable` — state trigger on `binary_sensor.pool_controller_reachable` going `off` for 5+ min. Tag: `pool_controller_unreachable`. (If this turns out to also have state-trigger reliability issues over time, switch to a template trigger using the same pattern as class 1.)
- **Retrospective (class 2):** auditor assertion P5 (`pump_on_actually_drawing_power`) in `pool/scripts/auditor.py` — same logic as proactive class 2, runs nightly on the daily slice.
- **Independent vendor channel — Hayward's own alarm emails.** OmniLogic emails `no-reply@haywardomnilogic.com` on alarm fired AND alarm cleared events. Out-of-band — independent of HA, the integration, the LRD network, anything we run. Gmail filter: `from:no-reply@haywardomnilogic.com`. Useful as audit trail when presenting to Hayward dealer (their own system documents the events) and as a fallback when HA detection is itself down.

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

**Diagnostic entities (packet loss, jitter, RTT average/min/max)** are disabled by default. Enable them in Settings → Devices & Services → Ping → click the device → enable in the entity list. Once enabled, they're referenced by:

- `automation.pool_alert_on_controller_network_degrading` (watcher on packet loss >10%) — see `packages/pool/pool_health_watcher.yaml`
- "Pool Controller Network Health" dashboard card — see `pool/docs/dashboard-cards.md` for paste-ready Mushroom YAML

Note that diagnostic entity IDs use the host IP (`sensor.192_168_11_19_packet_loss` etc.) rather than the device name. If the controller IP ever changes, all references in the watcher YAML and the dashboard card YAML need to be updated.

---

## Known network-side gotchas

Operational quirks observed and confirmed in the wild. Deep reasoning in the linked ADRs.

### UniFi port Native VLAN reverts on port state-machine transition (class-3c)

The USW Pro Max 16 PoE (firmware 7.4.1 as of 2026-05-22) has a bug where any port-config re-evaluation event reverts the port's Native VLAN override to the controller's default network (Trusted-LRD in our config). Confirmed triggers:

- **UDM Pro auto-reboot.** UniFi OS auto-update windows are enabled by default; when the UDM reboots during an update, the post-boot config push to the switch clobbers Native VLAN overrides. Today's 2026-05-22 incident.
- **UI port disable/enable.** Administratively bouncing a port from UniFi → Devices → switch → port settings reverts the Native VLAN. Confirmed during 2026-05-22 troubleshooting — every cycle reverted port 12 from IoT(4) back to Trusted-LRD.

**Implication for the MSP and other VLAN-pinned IoT devices:** when port 12 reverts, the MSP DHCPs into Trusted-LRD scope at next renewal, gets a `.0.0/24` IP, and HA's hardcoded `192.168.11.19` reference can't reach it. This is class-3c — see Failure-mode triage table above and ADR-019 Addendum 2026-05-22.

**Mitigations (defense in depth):**

1. **Disable UniFi OS auto-updates** on the UDM Pro. UniFi → Console → Settings → Auto-Update → off. Single most effective mitigation — removes the dominant trigger.
2. **Check Virtual Network Override on Fixed IP reservations.** UniFi Network → Clients → device → IP Settings → Fixed IP Address + **Virtual Network Override**. With VNO checked, the Fixed IP applies regardless of which VLAN the device shows up on — so even if the port drifts, the device still gets its expected IP at next DHCP renewal. Without VNO, the reservation is silently ignored on the wrong VLAN.
3. **Avoid UI port disable/enable as a troubleshooting tool.** It triggers the same revert. Use physical link bounce (unplug/replug at the device end) if you need to force link renegotiation, or restart the switch.

### MSP has no software reboot path (correction to earlier docs)

The OmniLogic MSP touchscreen (firmware R.5.2.0-b28706) does NOT expose a software reboot option. There is no "Restart Controller" menu item. The only way to restart the MSP is to remove power.

This was assumed earlier in this file and in ADR-019 ("MSP soft-reboot via touchscreen" was suggested as a clean recovery path) — that assumption was incorrect. Updated 2026-05-22 after Scott confirmed via direct inspection at the equipment pad. Always plan recovery sequences around breaker access, not cloud or local UI commands.

### UniFi UI "Remove" doesn't clear DHCP leases

Removing a client from UniFi → Clients only removes the controller's tracked record. The UDM Pro's dnsmasq backend retains the lease in `/ssd1/.data/udapi-config/dnsmasq.lease` until natural expiry. To actually release a lease requires SSH access to the UDM (toggle SSH on at UniFi → Console → Settings → Advanced) and either:

```
dhcp_release <br_iface> <ip> <mac>
```

(if `dhcp_release` is available — it wasn't on UDM SE as of 2026-05-22) or the sed + SIGHUP fallback:

```
sed -i '/<mac>/d' /ssd1/.data/udapi-config/dnsmasq.lease
kill -HUP $(cat /run/dnsmasq-main.pid)
```

Lease release alone doesn't force the client to re-DHCP — the client only learns its lease was invalidated when it tries to renew at T1 or sees a NAK on a new request. To force immediate re-DHCP, drop the client's L2 link (physical cable bounce, switch restart, or MSP power-cycle in the case of OmniLogic).

---

## Useful commands

When the integration goes weird, in order of escalation:

0. **Check the OmniLogic web UI alarms panel FIRST** — if `MSP_DEV_COMM_LOSS` alarms are present, this is a class-2 failure (see Failure-mode triage). Skip directly to step 6; reloading the integration won't help and the integration may already report healthy.
1. **Reload integration** — Settings → Devices & Services → OmniLogic Local → Reload
2. **Restart HA** — handles deeper state issues
3. **Audit registry** — Settings → Devices & Services → entities, filter `omnilogic`, look for `unavailable`
4. **Check controller link** — UniFi → Client Devices → confirm controller is on ethernet, check switch port for errors
5. **Diagnostic dump** — for new issues, integration → ⋮ menu → Download diagnostics
6. **Power-cycle the controller** — if reload, restart, and link checks all pass but local UDP is still silent (cloud + ping still working), the controller's UDP listener is wedged. Also the recovery for `MSP_DEV_COMM_LOSS` alarms (HUA re-handshake on boot). **Two procedures, see Setup quirks and ADR-019 — prefer the staged equipment-pad sequence (controller breaker on first, 20-30 sec gap, then pump breaker) once comm boards are degraded; the simultaneous indoor breaker is only reliable on healthy boards.** UDP listener takes 60–120 seconds to recover after the display lights up.
