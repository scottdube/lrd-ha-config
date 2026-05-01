# ADR-006: Actively-heating vs enabled — pump flow tied to compressor demand

**Status:** Proposed
**Date:** 2026-05-01
**Decider:** Scott
**Blueprint version that will implement this:** TBD (v1.9.0 candidate)
**Supersedes / amends:** ADR-002 (heater set-and-hold)

---

## Context

ADR-002 split heater control into two layers:
- **HA's job:** set the heater enabled (`on`) for swim days, disabled (`off`) otherwise. Set-and-hold.
- **Heat pump's job:** decide *when* the compressor actually runs based on its own thermostat and hysteresis.

That split fixed the missed-heater-start race conditions and is sound. **But it left a downstream consumer of `heater_state` — the pump-management logic — operating on incorrect assumptions.**

### The bug

Blueprint v1.7.0+ defines:

```yaml
heater_is_on: >
  {{ not is_state(heater_entity, 'off') }}
```

Anything that isn't `off` is treated as "the heater is currently delivering heat." That conflates two distinct conditions:

| HA-visible state | What HA thinks | What's actually happening |
|---|---|---|
| `off` | Heater off | Compressor off, no heat demand |
| `on` (compressor running) | Heater on | Compressor running, water flowing through heat exchanger absorbing heat |
| `on` (compressor idle) | Heater on | Compressor off because heat pump's internal thermostat is satisfied; *no heat being delivered* |

The third row is the problem. Per ADR-002, the heat pump cycles itself based on water temp vs setpoint. Once water reaches setpoint, the compressor shuts off. The HA `water_heater` entity stays `on` (still enabled). The blueprint sees `heater_is_on=True` and:

1. **Refuses to turn off the pump** in the WATERFALL END branch (`condition: not heater_is_on and filtration_complete`), because `not heater_is_on` is False.
2. **Holds pump speed at 77%** (heater speed) instead of dropping to 55% (normal speed), because `heater_needed = swimming_day and heatpump_ok` doesn't reflect actual compressor state.

Net effect on swim-day stretches: pump runs 24/7 at 77%. Confirmed empirically in `pool_temp_log.csv` 2026-04-28 through 2026-05-01: 595 logged pump=on rows, 0 pump=off rows, pump_speed=77 throughout.

This is wasted energy and unnecessary mechanical wear. The pump only needs flow when the heat exchanger is actively heating, plus during the daily filtration window.

### Why this is structurally a v1.2 regression masked by v1.7

Blueprint v1.2 added a `heater_idle` trigger that detected when the heater stopped on its own and shut the pump off accordingly. v1.7 deleted it ("no longer needed") because set-and-hold removed HA's role as heater controller. **But heater_idle was doing two jobs**: it (a) controlled the heater logic, and (b) controlled pump flow management. Deleting it for reason (a) silently broke (b).

---

## Decision

Refactor the blueprint to operate on **observed compressor activity**, not commanded heater state. Specifically:

1. Introduce a new template variable `heater_actively_delivering` (name TBD) representing "the heat exchanger is currently absorbing heat."
2. Replace `heater_is_on` with `heater_actively_delivering` in:
   - WATERFALL END pump-shutoff gate.
   - HEATER AND PUMP SPEED MANAGEMENT speed selection.
3. Keep `heater_is_on` (or its replacement that means "enabled") only for the heater set-and-hold logic itself.

### Signal for `heater_actively_delivering` — TWO SOURCES IDENTIFIED

Confirmed by source-code inspection of `cryptk/haomnilogic-local` and `cryptk/python-omnilogic-local`, plus empirical observation of the cloud activity log on 2026-05-01:

The library defines `HeaterState` (in `pyomnilogic_local/omnitypes.py`) with three values per physical heater unit:

| Enum | Int | Meaning |
|---|---|---|
| `HeaterState.OFF` | 0 | Physical unit disabled |
| `HeaterState.ON` | 1 | Compressor actively running, heat being delivered |
| `HeaterState.PAUSE` | 2 | Unit enabled but idle (at setpoint, freeze prevention, etc.) |

This is exposed by the HA integration in two equivalent ways:

1. **Primary: a dedicated binary_sensor.** `OmniLogicHeaterEquipBinarySensorEntity` (`custom_components/omnilogic_local/binary_sensor.py:68-83`). Its `is_on` is True iff `HeaterState.ON`. Entity ID will be `binary_sensor.omnilogic_pool_heater_heater_equipment_status` — exact name depends on the physical-equipment name configured in the OmniLogic. Find via Settings → Devices & Services → OmniLogic Local → entities → filter `binary_sensor`.

2. **Alternative: attribute on the water_heater entity.** `water_heater.omnilogic_pool_heater` exposes `omni_heater_equip_<name>_state` as an extra state attribute (`water_heater.py:114`), value is `str(HeaterState)` → `"OFF"` / `"ON"` / `"PAUSE"`. Richer than the binary because it distinguishes OFF from PAUSE.

3. **Independent: cloud water_heater entity state.** The cloud integration (`djtimca/haomnilogic`) exposes `state` on its water_heater entity `water_heater.pool_pool_heater_heater`, derived from `heaterState` field in the cloud telemetry. **Empirically confirmed 2026-05-01** via the Hayward cloud activity log: state transitioned `on` at 04:02:26 EDT and `off` at 06:47:26 EDT, matching a 2h45m compressor window during which water temp rose by ~2°F (consistent with ~0.73°F/hr observed vs. ~1°F/hr documented). Initial source-code reading suggested cloud only exposed enable/disable; the activity log shows otherwise — `heaterState` *is* a compressor-activity signal, just with the cloud's polling cadence (multiple minutes) rather than local UDP's near-real-time.

**These are two independent signals for the same physical reality.** Capture both in logger v2 and let the auditor flag any disagreement between them — divergence indicates an integration bug rather than a real disagreement, which is exactly the failure mode we want surfaced.

**Decision: use option 1 (local binary_sensor) as the blueprint signal.** Reasons:
- A boolean is sufficient for the pump-speed and pump-shutoff branches — we don't need to distinguish OFF from PAUSE in those branches; both mean "no compressor activity, no flow needed."
- A binary_sensor entity is first-class in HA (history, device_class=heat, dashboard tile), where attribute-reads are clunkier.
- Local UDP cadence is faster than cloud polling — important if we want the pump to drop to 55% promptly when compressor cycles off.
- Logger v2 captures all three signals (binary_sensor, attribute, cloud), so we keep the richer data and the cross-validation in storage without making the blueprint logic deal with it.

Define a new template variable in the blueprint:

```yaml
heater_actively_delivering: >
  {{ is_state(heater_active_binary_sensor, 'on') }}
```

Where `heater_active_binary_sensor` is a new blueprint input (default empty; user must configure the right entity for their physical equipment). Defensive default: if the sensor is `unavailable`, fall back to treating it as `True` — keeps pump running rather than starving the heat exchanger.

### Why the water-temp-delta proxy was rejected

Considered as a fallback during initial design when the integration was assumed to lack a direct signal. With the binary_sensor confirmed available, the proxy is unnecessary:

- It lags by 20–30 min vs. an immediate boolean.
- It fails during the first heat-up of the day before water-temp delta is measurable.
- It's confused by overnight evaporative cooling and morning solar gain.

Documented here only to preserve the design rationale.

### Why power monitoring was deferred

A CT clamp on the heat pump compressor circuit would be the most authoritative signal — and the integration already exposes a `Filter Power` sensor (`sensor.py`, `filter.power`) for the filter pump, demonstrating the pattern works. But:

- The OmniLogic doesn't appear to expose a `heater.power` field.
- We'd need separate instrumentation, separate integration.
- The binary_sensor signal is good enough.

Re-evaluate if the binary_sensor proves unreliable in practice (e.g. integration outages cause it to flap False during compressor activity).

### Behavior change summary

| Condition | Today (v1.7) | Proposed (v1.9) |
|---|---|---|
| Swim day, compressor running | Pump on @ 77% ✓ | Pump on @ 77% ✓ |
| Swim day, compressor idle (at setpoint) | Pump on @ 77% (waste) | Pump on @ 55% (or off if filtration met and outside waterfall window) |
| Swim day, post-20:00, compressor idle, filtration met | Pump on (heater_is_on blocks shutoff) | Pump off |
| Swim day, post-20:00, compressor running | Pump on @ 77% | Pump on @ 77% (let compressor finish) |
| Non-swim day | Pump off (set by NOT-A-SWIM-DAY branch) | Same |

---

## Consequences

### Positive
- Pump only runs when filtration or active heating demands it.
- Pump speed drops to 55% when heater is idle, even on swim days — material kWh savings.
- Logger v2 + auditor can verify this by comparing pump-on hours to compressor-active hours rather than the meaningless current "pump-on hours == 24."
- Aligns blueprint behavior with the actual physics — flow follows compressor, not enable.

### Negative
- **Adds a new failure mode if the chosen signal is wrong.** If `heater_actively_delivering` falsely reports inactive while compressor is running, pump speed drops to 55% and may starve the heat exchanger. Mitigation: pick the highest-signal source, validate over multiple swim days before declaring stable. Auditor catches false-negatives by comparing water-temp rise vs predicted heater-active hours.
- **Adds template complexity.** Especially if signal hierarchy fallback is implemented in YAML, the templates get gnarly. Acceptable; can be refactored to a single dedicated template sensor in `templates.yaml`.
- **May surface latent OmniLogic Local reliability issues.** If the integration's compressor attribute goes `unavailable` during the midnight error burst (see `scratch/omnilogic-local-midnight-burst-2026-05-01.md`), the proxy needs a sane default. Suggest: if signal is unavailable, treat as "actively delivering" (fail-safe: keeps pump running rather than starving the heat exchanger).

### Open questions

1. **What's the highest-signal source on the live system?** Investigation needed before we pick (1), (2), or (3). Logged as pending step.
2. **Hysteresis for the water-temp-delta proxy.** If we end up using (2), need to tune the threshold and window. Suggested starting point: `+0.2°F over 30 min` based on the documented heat rate of ~1°F/hr (see ADR notes on heater performance).
3. **Should the auditor fail-loud if pump-on-hours diverges from compressor-active-hours by more than X%?** Probably yes — it's the cleanest single-metric integrity check.

---

## Implementation plan

1. **Heater equipment binary_sensor entity ID confirmed:** `binary_sensor.omnilogic_pool_heater_heater_equipment_status` (Scott confirmed 2026-05-01). Cloud counterpart: `water_heater.pool_pool_heater_heater`.
2. **Update `pool_automation.yaml` blueprint to v1.9.0:**
   - New blueprint input `heater_active_binary_sensor` (selector: binary_sensor).
   - New template variable `heater_actively_delivering: {{ is_state(heater_active_binary_sensor, 'on') }}` with unavailable→True fail-safe.
   - Replace `heater_is_on` with `heater_actively_delivering` in WATERFALL END pump-shutoff gate (line ~520).
   - Replace `heater_needed` with `heater_actively_delivering` in pump-speed selection (line ~579).
   - Add `swimming_day` guard to WATERFALL ON branch (the bug surfaced 2026-05-01 — opens valve unconditionally in window).
   - Add `swimming_day` guard to PUMP START branch (parallel bug — starts pump on non-swim days too).
   - **Shift poll cadence from `:00 :10 :20 :30 :40 :50` to `:05 :15 :25 :35 :45 :55`** to avoid the midnight controller-burst window (per `scratch/omnilogic-local-midnight-burst-2026-05-01.md` — 00:30 lands squarely inside the burst).
   - Bump version header and changelog.
3. Add the new signals to logger v2 captured columns (see `pool/docs/logger-v2.md`):
   - `local_heater_equip_status` (binary_sensor)
   - `local_heater_equip_state` (string enum)
   - `cloud_heater_state` (string `on`/`off` from cloud water_heater entity)
4. Add audit assertions (see `pool/docs/auditor.md`):
   - **H4 (new):** `local_heater_equip_status` agrees with `cloud_heater_state` within 5-min tolerance window. Disagreement = integration bug.
   - **H5 (new):** Pump speed = 77% iff `heater_actively_delivering=True`; 55% otherwise. Validates v1.9.0 fix.
   - **H6 (new):** Pump-on hours / compressor-active hours ratio within reasonable bound (TBD, expect ~1.5–3× compressor hours due to filtration window).
5. Update `automations.yaml:518` alias to `Pool Automation v1.9.0`.
6. Status: Proposed → Accepted once shipped.

---

## Related

- ADR-002: heater set-and-hold (this ADR amends, doesn't supersede)
- `pool/docs/logger-v2.md`: logger redesign that captures the new signal
- `pool/docs/auditor.md`: nightly audit script that verifies the new behavior
- `scratch/omnilogic-local-midnight-burst-2026-05-01.md`: integration reliability investigation that surfaced this issue
