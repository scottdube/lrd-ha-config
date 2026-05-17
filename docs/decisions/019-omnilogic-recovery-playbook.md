# ADR-019: OmniLogic recovery playbook — two failure modes, one recovery action

**Status:** Accepted
**Date:** 2026-05-17
**Decider:** Scott
**Implementation:** `integrations/omnilogic.md` (triage table + playbook), `pool/scripts/auditor.py` (P5 assertion), `packages/pool/pool_health_watcher.yaml` (proactive watcher)
**Related:** ADR-001 (local for control / cloud for monitoring), ADR-016 (integration-recovery debounce)

---

## Context

Two distinct OmniLogic failure incidents occurred within a 22-hour window:

| Date | Symptom in HA | Symptom in OmniLogic UI | Resolution |
|---|---|---|---|
| 2026-05-16 ~11:00 EDT | Local integration stopped ACKing `GET_TELEMETRY`; entities went stale then unavailable | None (no alarms) | Power-cycle controller via pool sub-panel breaker |
| 2026-05-17 ~08:00 EDT | HA state-change commands acked cleanly through integration (off→Priming→On at 55%) but `sensor.omnilogic_pool_filter_pump_power` stayed at 0 W; `local_water_temp` stayed `unknown` | `MSP_DEV_COMM_LOSS` alarms for `VSP` (HUA `10-01-15-49-9a`) and `OPLMP` (HUA `a1-44-15-1b-56`) | Power-cycle controller via pool sub-panel breaker (HUA re-handshake on boot per Hayward TSG-OL150c) |

The 2026-05-16 incident was traced to a deliberate L1 disturbance (electrician disconnecting the Cat 6 during the in-wall run). The 2026-05-17 incident had no known trigger — it appeared sometime between 22:20 on 5-16 and 08:00 on 5-17. One plausible inference: the 22:12 breaker cycle on 5-16 induced it (power-cycling under load can stress comm modules), but this is unconfirmed and could equally be coincidence with the prior thunderstorm or independent age-related degradation of the VSP / OPLMP comm boards.

### Why they look similar at first glance

In both cases the user-facing symptom is "the pool isn't doing what HA says it's doing." The temptation is to treat them as one class. They're not — they fail at different layers of the stack:

```
HA (blueprint, scripts, dashboard)
   ↓  switch.turn_on / number.set_value
HACS OmniLogic Local integration (UDP, port 5858)
   ↓  GET_TELEMETRY / SET_EQUIPMENT
OmniLogic MSP (controller, IP 192.168.11.19)
   ↓  proprietary 4-wire Hayward bus (RS-485-class)
VSP driver / OPLMP / heater / chlorinator / valve actuators
   ↓  motor / relay / power electronics
Physical equipment (pump motor, pool light, etc.)
```

- **2026-05-16 wedge** broke the integration ↔ MSP link (rows 2-3). The MSP's UDP listener stopped responding; everything below was still fine. From HA's view: sensors stale or unavailable.
- **2026-05-17 wedge** broke the MSP ↔ peripheral link (rows 4-5). The integration ↔ MSP path stayed healthy and the MSP accepted every command. The MSP just couldn't relay the commands to the VSP and OPLMP because the Hayward bus to those two specific devices was silent. From HA's view: every command succeeds, every state change is observed, but the equipment never moves.

### Why both are fixed by the same action

A controller power-cycle resets state at every layer of the MSP that holds it: the network listener (fixing class 1), the bus address table for peripheral re-handshake (fixing class 2), and any other transient firmware state. Per Hayward TSG-OL150c, the recommended recovery for `MSP_DEV_COMM_LOSS` alarms is exactly this — kill the equipment breakers, restore the MSP breaker first, then equipment, and let the HUA re-handshake.

The 5-17 incident validated this: alarms cleared and pump began drawing power within minutes of the breaker cycle.

### Why distinguishing them still matters

Three operational reasons not to collapse them into one rule:

1. **Severity / urgency.** Class 1 (integration wedge) is read-side stale-data — the equipment is still doing whatever it was last commanded, which is usually safe. Class 2 (peripheral comm-loss) is write-side dead — the chlorinator can be commanded to dose into a dead leg with no flow, building chlorine concentration in the cell housing and stressing the salt cell. Class 2 deserves faster response.
2. **Diagnostic accuracy.** Class 1 alone, repeated, is a network or controller-firmware issue. Class 2 alone, repeated, is a hardware-reliability issue on the VSP / light module / data cable. Conflating them obscures which trend is which.
3. **When power-cycle is the wrong move.** If `MSP_DEV_COMM_LOSS` is present *and* the integration is healthy, power-cycling will resolve it. But if a third failure mode emerges (e.g., MSP itself is failing such that a cycle won't bring it back), the right action is service call, not another breaker cycle. The triage step ensures we look at the OmniLogic alarms panel first instead of reflexively cycling.

---

## Decision

### 1. Triage flow

When HA reports anomalous pool state, do the following in order:

1. **Check the OmniLogic web UI** (`hayward.com` / OmniLogic app) for active alarms.
2. **If `MSP_DEV_COMM_LOSS` alarms are present** → class 2 (peripheral comm-loss). Skip to recovery step 3 below.
3. **If no alarms but HA sensors are stale or unavailable** → class 1 (integration wedge). Try integration reload first (Settings → Devices & Services → OmniLogic Local → Reload). If reload doesn't restore polling within ~60 sec, escalate to power-cycle.
4. **If no alarms and HA reports look healthy but you observe physical equipment is not doing what HA says** → unknown class. Cross-check `sensor.omnilogic_pool_filter_pump_power` (should be >50 W if pump claims to be running) and `local_water_temp` (should leave `unknown` within 90 sec of real pump-on). If those are wrong, treat as class 2 and check OmniLogic UI more carefully — alarms can sometimes lag the actual failure.

### 2. Recovery procedure (both classes)

1. Kill the equipment breakers at the main service panel: pool sub-panel breaker. (For class 2 specifically, Hayward recommends killing both the MSP and equipment-power breakers separately — but the pool sub-panel kills both simultaneously, which is operationally simpler and has worked twice now.)
2. Wait 30 seconds.
3. Restore the pool sub-panel breaker.
4. Wait for the controller display to light up and reach the home screen (~30-60 sec).
5. Verify in OmniLogic UI: alarms should auto-clear if HUA re-handshake succeeded.
6. Verify in HA: integration entities should leave `unavailable` within ~60-120 sec; `local_filter_power` should jump to its expected range when next pump-on cycle fires.

### 3. Detection

Two layers, both implemented as part of this ADR:

- **Retrospective (auditor):** new P5 assertion in `pool/scripts/auditor.py` — flags any pump-on run >5 min where `local_filter_power < 50 W`. Surfaces class-2 incidents in the nightly audit pass.
- **Proactive (HA):** new package `packages/pool/pool_health_watcher.yaml` — single automation `automation.pool_alert_on_pump_on_but_no_power` with an inline `platform: template` trigger (`for: 2m`) that fires `notify.scott_and_ha` when pump_state=on AND power<50W for sustained period. Gated by `input_boolean.pool_integration_recovering` (ADR-016) to suppress false positives during the post-recovery reconciliation window. **Implementation history (2026-05-17):** two prior attempts using separate template binary_sensor entities both failed silently — modern `template: - binary_sensor:` was dropped by HA's package merge (collides with `template: !include config/templates.yaml` in main config), and legacy `binary_sensor: - platform: template` parsed without error but never registered an entity (consistent with deprecation/restriction of the legacy platform in HA 2026.x with silent-fail shim). The template-trigger-inside-automation pattern sidesteps both by not touching the `template:` or `binary_sensor:` top-level keys at all.

Neither detection layer distinguishes between class 1 and class 2 on its own — both observe "pump_on with no power." The triage step (check OmniLogic UI) is what disambiguates them. This is intentional: the alert is "something is wrong, go look," and the human-in-the-loop interpretation is the diagnostic.

### 4. Documentation

`integrations/omnilogic.md` carries the operational table + triage rule for in-the-moment reference. ADRs (016, 017, this one) carry the reasoning. `docs/current-state.md` carries the incident log.

---

## Trade-offs

**Not addressed:** automatic recovery. A `script.omnilogic_power_cycle_recovery` that toggles a smart breaker / contactor was considered and rejected because (a) Scott does not have a controllable breaker on the pool sub-panel, (b) automating physical infrastructure cycles without human-in-the-loop diagnosis risks masking equipment faults that should escalate to a service call rather than be reflexively cycled.

**Not addressed:** surge protection. Two comm-loss incidents in 24h with overlapping thunderstorm exposure is a yellow flag for surge damage on the outdoor Hayward bus cabling. Adding a surge suppressor at the MSP terminal block would mitigate the most likely root cause. Separate decision — defer until incident frequency justifies the spend, or until equipment-pad work creates a natural integration window.

**Not addressed:** dealer service-mode access. If HUA re-handshake fails after a power-cycle (the device is permanently lost from the MSP), the recovery path is dealer / installer-mode re-add. Scott does not currently have the installer code. If class 2 recurs and breaker-cycle stops resolving it, dealer call becomes the next step. Procuring the installer code defensively is out of scope.

**Watch-item:** if class-2 incidents recur within a 30-day window, the VSP or OPLMP comm board is the most likely failing component and replacement should be scheduled rather than continuing to power-cycle through it. Comm boards that fail intermittently typically fail permanently within weeks of the first incident.

---

## Verification

- 2026-05-17 incident: post-cycle observation confirmed `sensor.omnilogic_pool_filter_pump_power` left 0 W and `local_water_temp` left `unknown` within the expected window. Live state log timestamps captured in `docs/current-state.md` Pool automation in-flight section.
- P5 assertion: validated against the 2026-05-17 daily slice — should FAIL on the 08:00:01-08:44:05 window (43 min of pump_on with power=0).
- Watcher: bench-validate by temporarily editing `value_template` to a constant `true`, restart HA, confirm the automation fires within 2 min and routes through `notify.scott_and_ha` to both mobile and bell, then revert. (The template trigger has no separate state-publishable entity, so the trigger expression itself is what needs to be forced for the test.)

---

## Sources

- 2026-05-17 incident:
  - Hayward OmniLogic UI screenshot (alarms panel showing `MSP_DEV_COMM_LOSS,Comm Loss Device:VSP HUA:10-01-15-49-9a` and `MSP_DEV_COMM_LOSS,Comm Loss Device:OPLMP HUA:a1-44-15-1b-56`)
  - `pool/analysis/pool_state_log_live.csv` (08:00:01 PUMP START, 08:02:11 Priming→On transition, both with `local_filter_power=0`; 08:44:05 unavailable rows confirming breaker cycle)
- 2026-05-16 incident: `scratch/omnilogic-local-2026-05-16-ethernet-wedge.log`, `docs/current-state.md` Recently completed section
- Hayward troubleshooting: [TSG-OL150c (PDF)](https://www.royalswimmingpools.com/Merchant2/manuals/Hayward/Troubleshooting/OmniLogic-TSG_OL150c.pdf), [TSG-OPL42a (PDF)](https://hayward.com/media/akeneo_connector/asset_files/O/m/OmniPL_Troubleshooting_Guide___TRR_7804.pdf)
- Community references on `MSP_DEV_COMM_LOSS` + HUA recovery: [JustAnswer thread](https://www.justanswer.com/pool-and-spa/pc9k9-keep-getting-error-message-msp-dev-comm-loss-hua-vsp.html), [Trouble Free Pool VSP HUA thread](https://www.troublefreepool.com/threads/pump-not-working-hayward-omnilogic-alert-msp_dev_comm_loss-comm-loss-device-vsp-hua-10-01-17-65-99.297968/)
- ADR-016 (integration-recovery debounce — supplies `input_boolean.pool_integration_recovering`)
