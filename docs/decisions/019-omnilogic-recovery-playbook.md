# ADR-019: OmniLogic recovery playbook — two failure modes, one recovery action

**Status:** Accepted
**Date:** 2026-05-17
**Decider:** Scott
**Implementation:** `integrations/omnilogic.md` (triage table + playbook), `pool/scripts/auditor.py` (P5 assertion), `packages/pool/pool_health_watcher.yaml` (proactive watcher)
**Related:** ADR-001 (local for control / cloud for monitoring), ADR-016 (integration-recovery debounce)

---

## Context

Three distinct OmniLogic failure modes observed within 24 hours, prompting the three-class taxonomy this ADR defines. Note (added 2026-05-18): a sweep of Hayward's own alarm-notification emails (`from:no-reply@haywardomnilogic.com`) revealed the VSP comm-loss is a **6-week intermittent trend**, not a fresh failure — class-2 events on Apr 7 (VSP only, minutes) and May 1 (VSP only, ~12 min, with No Water Flow co-alarm) predate any of the recent cable work. The May 16-17 and May 17-18 dual-device 10.5-hour overnight events are an escalation of an existing trend, not a new failure mode. The recent in-wall Cat 6 work + breaker cycles likely accelerated an already-failing comm board — they didn't cause it.

| Date | Symptom in HA | Symptom in OmniLogic UI | ICMP to controller | Resolution | Class |
|---|---|---|---|---|---|
| 2026-05-16 ~11:00 EDT | Local integration stopped ACKing `GET_TELEMETRY`; entities went stale then unavailable | None (no alarms) | ✓ Reachable | Power-cycle controller via pool sub-panel breaker | 1 — integration↔MSP UDP wedge |
| 2026-05-17 ~08:00 EDT | HA state-change commands acked cleanly through integration (off→Priming→On at 55%) but `sensor.omnilogic_pool_filter_pump_power` stayed at 0 W; `local_water_temp` stayed `unknown` | `MSP_DEV_COMM_LOSS` alarms for `VSP` (HUA `10-01-15-49-9a`) and `OPLMP` (HUA `a1-44-15-1b-56`) | ✓ Reachable | Power-cycle controller via pool sub-panel breaker (HUA re-handshake on boot per Hayward TSG-OL150c) | 2 — MSP↔peripheral comm-loss |
| 2026-05-17 ~19:00–20:50 EDT | All entities `unavailable` for 1h50m, brief recovery, then off again | None visible (couldn't reach UI either) | ✗ Unreachable from both HA (cross-VLAN) and Scott's MacBook (same VLAN as controller) | Reseat RJ45 connector at controller end (in-wall pass had been completed by Shepard 5-16; connector worked loose under thermal cycling) | 3 — physical/network |

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

1. **Ping the controller from a workstation on the IoT VLAN** (or check the `binary_sensor.pool_controller_reachable` state in HA): `ping -c 3 192.168.11.19`.
   - **If unreachable** → class 3 (physical/network). Skip to recovery step 4 below; do not breaker-cycle blindly.
   - **If reachable** → continue to step 2.
2. **Check the OmniLogic web UI** (`hayward.com` / OmniLogic app) for active alarms.
   - **If `MSP_DEV_COMM_LOSS` alarms are present** → class 2 (peripheral comm-loss). Skip to recovery step 3 below.
   - **If no alarms but HA sensors are stale or unavailable** → class 1 (integration wedge). Try integration reload first (Settings → Devices & Services → OmniLogic Local → Reload). If reload doesn't restore polling within ~60 sec, escalate to power-cycle.
3. **If no alarms and HA reports look healthy but physical equipment isn't doing what HA says** → cross-check `sensor.omnilogic_pool_filter_pump_power` (should be >50 W if pump claims to be running) and `local_water_temp` (should leave `unknown` within 90 sec of real pump-on). If those are wrong, treat as class 2 and check OmniLogic UI more carefully — alarms can sometimes lag the actual failure.

### 2. Recovery procedure for classes 1 and 2

**Two procedures, pick based on board health (updated 2026-05-18):**

**Preferred — staged power-cycle at the equipment-pad breakers:**

1. At the pool sub-panel at the equipment pad, kill BOTH the controller breaker and the pump (equipment) breaker.
2. Restore the **controller breaker FIRST**.
3. Wait 20–30 seconds for the controller display to come up and reach the home screen.
4. **Then** restore the pump/equipment breaker.

This sequence lets the MSP finish booting and stabilize its bus before the equipment loads ask it to re-handshake their HUAs. Empirically more reliable than the simultaneous procedure when comm boards are degraded — observed 2026-05-17 evening and 2026-05-18 morning: simultaneous failed to clear the alarms, sequenced succeeded.

**Acceptable — simultaneous pool-sub-panel breaker at the indoor main service panel:**

1. Kill the pool sub-panel breaker at the main service panel.
2. Wait 30 seconds.
3. Restore.
4. Wait for display to come up (~30–60 sec).

Works when comm boards are healthy. Doesn't require equipment-pad access (useful at night, in storms, etc.). Becomes unreliable once boards are degraded — last reliable use 2026-05-17 morning; subsequent attempts have not cleared the alarms.

**Verify after either procedure:**

- OmniLogic UI: alarms should auto-clear if HUA re-handshake succeeded.
- HA: integration entities should leave `unavailable` within ~60-120 sec; `local_filter_power` should jump to its expected range when next pump-on cycle fires.

**Why the staged procedure works better on degraded boards (inferred):** per Hayward TSG-OL150c, HUA can be "lost" on breaker trips — the boards must re-register on boot. A simultaneous power restore brings equipment power up at the same instant as MSP power, so the equipment side starts trying to handshake with an MSP that hasn't finished its own boot/bus initialization. Healthy boards retry until the MSP is ready; degraded boards apparently don't retry reliably. The 20-30 sec staged delay gives the MSP time to be ready when the equipment first talks to it.

### 3. Recovery procedure for class 3 (physical/network)

Breaker-cycling does NOT help class 3 — the controller is already alive (or already powerless); the failure is the connection between it and the network. Physical triage in this order:

1. **Look at the OmniLogic display at the equipment pad.**
   - **Dark / unlit** → power issue. Check the pool sub-panel breaker (could be tripped). If the breaker is fine, the controller's internal PSU may be failing — dealer call.
   - **Lit and showing the home screen** → controller is alive, network side is the failure. Move to step 2.
2. **Reseat the Cat 6 / RJ45 at the controller.** First diagnostic and often the immediate fix. Observed 2026-05-17 evening: the in-wall pass completed by Shepard on 5-16 left a marginal connector that worked loose under thermal cycling and disconnected entirely 48 hours later. Reseating restored the link.
3. **If reseat brings it back, do NOT consider this fixed.** A marginal connector that just "reseat-worked" will fail again on a timeframe of days. Permanent fix: re-crimp the RJ45 at the controller end (5-min DIY job if you have a crimper, or call Shepard back).
4. **Check the UniFi switch port** the controller connects to: Devices → switch → port stats. Look for recent link-down events, flap counts, error counters.

### 4. Standing watch-item: controller-end RJ45 reliability

The 2026-05-17 escalation (three incidents in 24h with arguably progressively-worse symptoms) plausibly traces to the single root cause of a marginal RJ45 connection at the controller end. Until the connector is re-crimped (not just reseated), expect recurrence. If recurrence happens after a confirmed re-crimp, the next escalation is to check the in-wall cable run itself for damage and/or the switch port hardware.

### 5. Detection

Two layers, both implemented as part of this ADR:

- **Retrospective (auditor):** new P5 assertion in `pool/scripts/auditor.py` — flags any pump-on run >5 min where `local_filter_power < 50 W`. Surfaces class-2 incidents in the nightly audit pass.
- **Proactive (HA), three layers in `packages/pool/pool_health_watcher.yaml`** — extended 2026-05-17 evening after a third incident the same day revealed two more failure classes the original single-layer design didn't catch:
  - **Class 1 — integration↔MSP wedge.** `automation.pool_alert_on_omnilogic_integration_wedge` — state trigger on `switch.omnilogic_pool_filter_pump` going `unavailable` for 10+ min. No recovery-debounce gate because by definition this fires BEFORE recovery, so ADR-016's boolean isn't relevant.
  - **Class 2 — MSP↔peripheral comm-loss.** `automation.pool_alert_on_pump_on_but_no_power` — inline `platform: template` trigger (`for: 2m`) on pump_state=on AND power<50W. Gated by `input_boolean.pool_integration_recovering` (ADR-016) to suppress false positives during the post-recovery reconciliation window, and `input_boolean.pool_service_lockout` (ADR-011) to stay quiet during tech service work.
  - **Class 3 — physical/network.** `automation.pool_alert_on_omnilogic_controller_unreachable` — state trigger on `binary_sensor.pool_controller_reachable` going `off` for 5+ min. The ping binary_sensor is set up via HA UI (Settings → Devices & Services → Add Integration → Ping (ICMP), host `192.168.11.19`, name `Pool Controller Reachable`, count 3, scan_interval 30) because the ping YAML configuration was deprecated in HA 2023.12 — `binary_sensor: - platform: ping` now triggers HA Repair warnings. The UI-created entity lives in `.storage` (not git), but the referencing automation is in git and the setup procedure is documented in `integrations/omnilogic.md`.
  - All three automations use distinct iOS notification tags so they collapse into separate threads — at-a-glance you know which layer is broken. Class-3 fires first when the controller goes off the network entirely; class-1 follows ~5 min later (integration times out); seeing both together is the canonical class-3 signature.
- **Independent vendor channel — Hayward's own alarm emails.** Hayward's OmniLogic system emails `scott@dubecars.com` from `no-reply@haywardomnilogic.com` on alarm fired AND alarm cleared events, with exact timestamps, device names, and HUA addresses. This is OUT-of-band — doesn't depend on HA, the integration, the LRD network, or anything in our stack. Independent of class-1/2/3 detection above. Useful for two reasons: (a) audit trail when presenting to Hayward dealer / service tech (their own system documents the events, can't be argued with), (b) catches events HA can miss if HA is down or the integration is wedged. Gmail filter: `from:no-reply@haywardomnilogic.com`. Discovered 2026-05-18 — was passively accumulating in inbox; the 6-week VSP comm-loss trend was reconstructed from these emails after the fact.
  - **Implementation history for class 2 (2026-05-17):** two prior attempts using separate template binary_sensor entities both failed silently — modern `template: - binary_sensor:` was dropped by HA's package merge (collides with `template: !include config/templates.yaml` in main config), and legacy `binary_sensor: - platform: template` parsed without error but never registered an entity (consistent with deprecation/restriction of the legacy platform in HA 2026.x with silent-fail shim). The template-trigger-inside-automation pattern sidesteps both by not touching the `template:` or `binary_sensor:` top-level keys at all.

### 6. Documentation

`integrations/omnilogic.md` carries the operational table + triage rule for in-the-moment reference. ADRs (016, 017, this one) carry the reasoning. `docs/current-state.md` carries the incident log.

---

## Trade-offs

**Not addressed:** automatic recovery. A `script.omnilogic_power_cycle_recovery` that toggles a smart breaker / contactor was considered and rejected because (a) Scott does not have a controllable breaker on the pool sub-panel, (b) automating physical infrastructure cycles without human-in-the-loop diagnosis risks masking equipment faults that should escalate to a service call rather than be reflexively cycled.

**Not addressed:** surge protection. Two comm-loss incidents in 24h with overlapping thunderstorm exposure is a yellow flag for surge damage on the outdoor Hayward bus cabling. Adding a surge suppressor at the MSP terminal block would mitigate the most likely root cause. Separate decision — defer until incident frequency justifies the spend, or until equipment-pad work creates a natural integration window.

**Not addressed:** dealer service-mode access. If HUA re-handshake fails after a power-cycle (the device is permanently lost from the MSP), the recovery path is dealer / installer-mode re-add. Scott does not currently have the installer code. If class 2 recurs and breaker-cycle stops resolving it, dealer call becomes the next step. Procuring the installer code defensively is out of scope.

**Watch-item:** if class-2 incidents recur within a 30-day window, the VSP or OPLMP comm board is the most likely failing component and replacement should be scheduled rather than continuing to power-cycle through it. Comm boards that fail intermittently typically fail permanently within weeks of the first incident.

---

## Addendum 2026-05-18: firmware-version diagnostic + multi-issue synthesis

### Controller firmware versions (captured 2026-05-18 from System Info screen)

| Component | HUA | Version |
|---|---|---|
| MSP | 06-44-15-01-ab | R.5.2.0-b28706 |
| VSP | 10-01-15-49-9a | R.1.0.17 |
| Heater | 20-01-70-3a-03 | R.1.1.3 |
| OPLMP | a1-44-15-1b-56 | R.4.0.1 |

MSP ID: 324825. Photo: `pool-controller-firmware-2026-05-18.jpg` (workspace).

**MSP is on 5.2.0** — the Hayward-recommended version after the April 2026 5.3.0 revert advisory (community evidence on Trouble Free Pool). This rules out the "5.3.0 firmware bug → revert to 5.2.0" remediation path; Scott was never on 5.3.0. Whatever's causing the class-2 alarms is present in 5.2.0 itself or in one of the peripheral firmwares.

**VSP firmware R.1.0.17** is a low version number — worth checking if newer VSP firmware exists that addresses comm-board reset behavior. If a VSP firmware update is available and clears the alarms, that's the cheapest fix path before any hardware replacement.

### T&D Pool Construction professional opinion (Billy Blackburn, 2026-05-18)

Billy's diagnosis via text exchange:

> "The issue is the pump is not resetting if you turn the breaker off in the garage for 5mins then back in it should correct the issue. Hayward is working on an update to fix it but until that comes out, this is how you will have to clear it."

Follow-up:

> "No it's been an ongoing thing for a few months now. It takes the pump 3 to 5 minutes to completely deenergize to allow for it to reset."

Four takeaways:

1. **Field prevalence — widespread, not site-specific.** Billy is seeing this across his customer base for "a few months." That rules out site-specific causes (failing comm board on a single unit, marginal cable, surge damage, etc.) and points to a firmware-level behavior change affecting the whole VSP field population.

2. **Mechanism — VFD DC-bus capacitor discharge time.** Pool VSPs are variable-frequency drives with large DC-bus capacitors that retain high-voltage charge for minutes after breaker-off. While charged, the VSP's MCU is partially alive on residual rails — it never cleanly cold-boots. If the breaker comes back on before caps fully discharge (~3-5 min per Billy, consistent with standard industrial-drive electronics), the MCU comes up from an indeterminate state and the HUA handshake with MSP doesn't reliably re-establish. The "MSP_DEV_COMM_LOSS" alarms are the downstream effect of this incomplete cold-boot.

3. **5-minute breaker-off duration is the operative recovery procedure** — adds a third tier to the recovery hierarchy:
    - **Tier 1 — simultaneous indoor breaker (~30 sec):** works when boards / firmware happy; fastest. Fails reliably with degraded state.
    - **Tier 2 — extended indoor breaker (5+ minutes):** allows full VSP cap discharge before re-power. Per Billy, the canonical workaround as of 2026-05.
    - **Tier 3 — staged equipment-pad sequence (controller-first, 20-30 sec gap, then pump):** as in the original ADR-019. Useful when even tier 2 doesn't clear.

4. **A Hayward firmware update is in the pipeline.** Scott is already on the latest stable MSP (5.2.0), so the pending fix would have to be a 5.2.1 patch, a future 5.4.x, or targeted at the VSP firmware level (currently R.1.0.17 — low version number suggests room for newer revs). Open question for the next dealer conversation: "what version is Hayward targeting for the fix, and what's the rollout timeline?"

**Update 2026-05-19 (Billy via text):** target version is **MSP 5.4.0**, specifically intended to address the comm-loss issues. Rollout timeline still unknown. Billy also flagged that VSP firmware has been pinned at R.1.0.17 for years — MSP firmware has continued evolving while the VSP comm-board firmware sat still, suggesting the bug may live in the protocol drift between newer MSPs and older VSPs. Billy is raising this with his Hayward contacts as a candidate architectural fix beyond the 5.4.0 patch. **Watch path:** check the [Hayward firmware page](https://www.hayward.com/support/resources/firmware) weekly for 5.4.0 release, and watch the inbox for community reports on TFP threads.

### Multi-issue synthesis (revised after Billy's 2026-05-18 explanation)

Walking through the events of 2026-04-30 through 2026-05-18, the picture simplifies to **two root causes** plus their downstream effects:

| # | Issue | Layer | Trigger | Notes |
|---|---|---|---|---|
| **A** | Marginal RJ45 termination at controller | Physical / cable | Shepard's 2026-05-16 in-wall Cat 6 pass left an imperfect crimp; thermal cycling progressively loosened it | Site-specific. Independent of D. Re-crimp eliminates. |
| **D** | VSP DC-bus cap discharge requires ~3-5 min for clean cold-boot | VSP firmware behavior | Any breaker cycle shorter than full discharge time | Field-wide per Billy. Hayward firmware update pending. Workaround: 5-min breaker-off. |

**Downstream effects (not separate root causes, just symptoms of A and D interacting):**

- **B (UDP listener wedge after L1 disturbance):** caused by A's link flapping. Cleared by any controller power-cycle. Surfaces as class-1 alarms.
- **C (HUA loss / `MSP_DEV_COMM_LOSS` on VSP and OPLMP after breaker cycle):** caused by D's incomplete reset when breaker cycle was too short. Surfaces as class-2 alarms. Cleared by 5-min breaker-off OR staged equipment-pad cycle.

**Cascade dynamics:**

- **A flaps the link → B (UDP wedge)** → user does breaker cycle to recover B
- **breaker cycle (if quick) hits D's bug → C (HUA loss)** → user does another breaker cycle to clear C
- **second cycle, if also quick, also hits D → C persists**
- **eventually: longer cycle (5+ min) satisfies D → C clears, system recovers**
- **A still latent** → next thermal cycle repeats the loop

**Implication: A and D are independent. Fix either one to break the loop:**

- **Fix A (re-crimp the RJ45):** cable stops flapping → B doesn't fire → no breaker cycles needed → D's bug never activates. Site-specific fix, completely under Scott's control.
- **Fix D (wait for Hayward firmware update OR always use 5-min recovery):** even if cable flaps, D no longer breaks the recovery. Field-wide fix, depends on Hayward release timeline.

Best path is to fix both — RJ45 re-crimp this week (eliminates the trigger), and update to Hayward's patched firmware whenever it ships (eliminates the underlying bug).

**Status as of 2026-05-18 13:30 EDT:** RJ45 reseated 2026-05-17 evening; held for 6 min then failed; recovery via staged power-cycle 2026-05-18 ~09:04 EDT cleared all alarms. Pool currently running cleanly (power=691W at 09:30 EDT). System under observation; re-crimp scheduled for this week.

### Pre-departure (2026-05-30) plan

Scott departs 2026-05-30. 12 days for diagnostic and fix runway. With the cascade now understood as A + D (not a hardware-degradation problem), the plan tightens:

| Priority | Action | Why | Owner |
|---|---|---|---|
| HIGH | Re-crimp RJ45 at controller this week | Removes A — the only site-specific trigger. Independent of Hayward's firmware timeline. | Scott or Shepard |
| HIGH | Identify local emergency contact who can run 5-min breaker cycle | Insurance against D firing while Scott is away. If D fires, the 5-min cycle clears it. | Scott (neighbor or T&D) |
| MEDIUM | T&D VIP weekly service during absence | Eyes on the pool. Can do the 5-min cycle proactively if alarms appear in their inbox. | Scott to schedule with Billy/Dianne |
| MEDIUM | 3-4 clean days post-crimp as observation window | Class-1 watcher (template-trigger after 2026-05-18 patch) will fire if A wasn't actually fixed. | Scott + HA automation |
| LOWER | Ask Billy/T&D about VSP firmware update path | If newer VSP firmware (above R.1.0.17) exists that addresses D, that's the cheapest pre-departure fix. | Scott to ask Billy |
| DROP | Pre-emptive VSP/OPLMP comm-board replacement | No longer indicated. Field-wide firmware behavior, not site-specific hardware failure. | — |

**Decision tree for departure go/no-go:**

- **If RJ45 is re-crimped and 7+ days clean** → low-risk departure. T&D weekly service is sufficient backup.
- **If alarms recur post-crimp** → escalate to T&D for diagnosis (could be RJ45 still bad, or D fired on its own without an L1 trigger). May still be firmware-only; not necessarily hardware.
- **If Hayward ships the firmware fix before May 30** → update and re-test. Highest confidence path.

**HA automation re-enable decision (day of departure):** depends on confidence. If 7+ clean days, re-enable for remote visibility. If still unstable, keep disabled, rely on T&D weekly service + 5-min cycle for recovery.

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
