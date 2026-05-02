# ADR-013: current_water_temp fallback when sensor reads "unknown"

**Status:** Accepted
**Date:** 2026-05-02
**Decider:** Scott
**Blueprint version that implements this:** v1.10.1
**Supersedes / amends:** none (clarifies an unstated assumption in v1.5+)

---

## Context

The PUMP START branch in the pool automation blueprint computes a target start time based on how long the heat pump needs to bring the water up to setpoint by `target_ready_time` (default 11:00 AM):

```yaml
hours_to_heat: max(target_temp - current_water_temp, 0)
heat_start_minutes: target_ready_minutes - (hours_to_heat * 60)
filter_start_minutes: waterfall_start_minutes - (extra_filter_needed_hours * 60)
pump_should_start_minutes: min(heat_start_minutes, filter_start_minutes)

# PUMP START condition (simplified):
not pump_is_on AND current_minutes >= pump_should_start_minutes AND swimming_day
```

`current_water_temp` was defined:

```yaml
current_water_temp: >
  {{ states(water_temp_sensor) | float(75) }}
```

The OmniLogic in-line water temperature probe reports `unknown` when the pump is off — there's no flow for the sensor to settle against, so the integration suppresses stale readings. Whenever the pump goes off (overnight, NOT-A-SWIMMING-DAY, lockout-clear-then-poll, integration hiccup, etc.), `states(water_temp_sensor)` is `unknown`, the `| float(75)` fallback fires, and:

- `hours_to_heat = max(89 - 75, 0) = 14`
- `heat_start_minutes = 660 - (14 × 60) = -180`
- `pump_should_start_minutes = min(-180, 480) = -180`

The PUMP START gate `current_minutes >= -180` is true at every poll. So the moment any other gate clears (lockout off, swim_day true, etc.), the pump starts immediately regardless of the actual time of day or the actual water temperature.

### Confirmed empirically

`pool_state_log_2026-05-02.csv` row at 00:20 EDT: pump=on, compressor=on, water=86, lockout=off (cleared at 00:01 by midnight auto-clear). HA logbook for `switch.omnilogic_pool_filter_pump`:

> Omnilogic Pool Filter Pump turned on **triggered by automation Pool Automation v1.10.0 triggered by time pattern** — 12:10:01 AM

The blueprint's poll at 00:10:01 — the first poll after lockout cleared — fired PUMP START. The compressor then engaged shortly after via the heat pump's own thermostat seeing water below setpoint. Net cost: ~3 hours of compressor activity overnight + ~5 hours of pump-only running between cycles = roughly 30 kWh / $4 for the night. Annualized over the swim season: $150–250/year of marginal waste from the gate firing outside intended windows.

This is not a state-persistence issue in OmniLogic and not a heater-interlock issue. It's a HA-side template bug.

### Why this hadn't surfaced earlier

Two reasons it stayed latent:

1. **v1.7.0+ kept the heater enabled 24/7 on swim days** (set-and-hold per ADR-002), and the post-choose pump-speed maintenance kept the pump running whenever it was on. So "pump off" was rare — it required either NOT-A-SWIMMING-DAY or a manual intervention. The new v1.10.0 service-lockout mode introduced a routine "pump off → pump back on later" cycle for the first time, exposing the latent gate behavior.
2. **The OmniLogic Local integration's behavior of reporting "unknown" when pump is off** isn't formally documented and was discovered by inspection of the logger v2 CSV. Earlier code may have assumed a stale-but-numeric reading.

---

## Decision

Change the fallback from `float(75)` to `float(target_temp)`. When the sensor is unknown:

- `hours_to_heat` evaluates to `max(target_temp - target_temp, 0) = 0`
- `heat_start_minutes = target_ready_minutes - 0 = 660` (11:00 AM)
- `pump_should_start_minutes = min(660, 480) = 480` (08:00 AM, the morning filter window)

PUMP START then fires at the morning filter window only, not at every poll. Once the pump runs and the water sensor settles (~10 min), the real reading drives subsequent decisions.

### Why not skip evaluation when sensor is unknown

A `condition: states(water_temp_sensor) not in ['unknown', 'unavailable']` guard would also work, but creates a fail-stuck mode if the sensor never recovers (e.g., hardware failure, integration outage). The fallback approach degrades gracefully — pump still runs at the morning window even with a dead sensor.

### Why not use a higher fallback like target_temp + 5

Cleanly returns "no heat demand" without needing semantic explanation of why we're picking a number above target. `target_temp` exactly conveys "assume satisfied unless we know otherwise."

---

## Trade-offs

**Worse:** in shoulder-season conditions where overnight cooling is significant (40s/50s overnight in winter), the pump waiting for the morning filter window could mean a cold start at 08:00 with insufficient runway to reach 89°F by 11:00. v1.10.1 doesn't address this — it relies on filter_start_minutes being early enough to handle worst-case.

In Florida May–summer this is non-issue. In winter, target_temp is typically lowered to 80°F or heater is disabled outright (`min_swim_temp` gate), so the math still works.

**Better:** eliminates the most expensive failure mode (24/7 pump runs after pump-off events). Saves the marginal $150–250/year identified above.

---

## Consequences and follow-ups

This patch is a tactical fix. The structural problem — that the blueprint can't measure pool temp when the pump is off — remains. Two follow-up tracks:

### Track A: trusted-temp helper (logger v2 phase 2)

Maintain `input_number.pool_water_temp_trusted`, updated only when:
- `states(water_temp_sensor)` is numeric
- `pump_state == 'on'` for ≥ 600s (settling window)

Blueprint reads trusted instead of raw sensor. Persists last good reading across pump-off windows. Better than the v1.10.1 patch because it preserves real history when sensor goes unknown briefly, but still doesn't help if water has actually drifted since the last good reading.

### Track B: independent water temp sensor (ADR-015 candidate)

Real-time water temp sensor that reports while pump is off. Options:
- Waterproof DS18B20 wired into a pool-side ESP32 (Scott has hardware)
- Inkbird BLE/WiFi probe in skimmer
- Floating sensor

A working independent sensor subsumes Track A — no need for "trusted last reading" if you have continuous truth. ADR-015 will scope hardware choice and integration path.

Either track makes the v1.10.1 fallback irrelevant: the blueprint always has a real reading. v1.10.1 is the fallback strategy until then.

---

## Verification

Pump-on event after lockout clear should be gated by morning filter window (08:00 default), not by stale-sensor math. After deploy:

- Manual lockout cycle: set `input_boolean.pool_service_lockout` on, wait for pump to go off, clear lockout. Pump should *not* start until 08:00 the next morning (assuming clear during overnight hours).
- Tonight's normal cycle: pump should turn off at WATERFALL END (20:00) and stay off until 08:00 tomorrow. Confirm via `pool_state_log.csv` and HA logbook.

Auditor (per `pool/docs/auditor.md`) phase 1 will codify this as an assertion once it ships.

---

## Sources

- HA logbook: `switch.omnilogic_pool_filter_pump turned on triggered by automation Pool Automation v1.10.0` at 2026-05-02 00:10:01 EDT
- `pool/analysis/pool_state_log_2026-05-02.csv` rows 19:50, 20:10, 00:10, 00:20
- `blueprints/automation/LRD/pool_automation/pool_automation.yaml` lines 459–513 (variables block, pump_should_start_minutes derivation)
- v1.10.1 blueprint patch
