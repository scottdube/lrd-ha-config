# ADR-015: Independent water temp sensor — reuse existing TX13-class float case + NTC for v1

**Status:** Accepted (requirements + hardware path commitment; build-phase details open)
**Date:** 2026-05-02
**Decider:** Scott
**Supersedes / amends:** none
**Related:** ADR-013 (current_water_temp fallback — tactical predecessor)

---

## Context

ADR-013 patched the immediate `current_water_temp` math bug by changing the fallback from `float(75)` to `float(target_temp)` when the OmniLogic in-line probe reports `unknown`. That patch is tactical: it stops the PUMP START gate from firing every poll during pump-off windows, but leaves the structural problem unsolved — **the blueprint has no real water temperature reading whenever the pump is off, because the OmniLogic probe sits in the return path and needs flow to settle.**

ADR-013 identified two follow-up tracks to close that gap:

- Track A (trusted-temp helper) — persist last good reading via `input_number.pool_water_temp_trusted`. Drafted in `pool/docs/logger-v2.md` phase 2. Doesn't help if water has actually drifted since the last good reading.
- Track B (independent sensor) — real-time temp during pump-off. Subsumes Track A.

This ADR is Track B. It captures the requirements analysis completed 2026-05-02 and commits to a v1 hardware path. Calibration values, exact build steps, power-source detail, and notification policy are explicitly deferred — flagged in "Open design decisions" below.

---

## Requirements summary

Worked through 8 sections in the 2026-05-02 conversation. Condensed:

**1. Functional.** Only blueprint consumer is `current_water_temp` → `hours_to_heat` → `heat_start_minutes` → PUMP START gate (`pool_automation.yaml` line 521). `min_swim_temp` (line 506) gates `swimming_day` against `forecast_high` (air-temp), not water. No freeze-protection or overheat-alert branches exist. Logger v2 already has placeholder columns for this sensor.

Tiered need:
- **Must-have:** `hours_to_heat` math correct by ~07:00 daily
- **Should-have:** 24/7 sample continuity for logger v2 + auditor cross-validation
- **Nice-to-have:** continuous data for predictive-heating model (`pool/README.md`)

Cadence: 30 min sensor sample. Availability: 24/7 for logging continuity.

**2. Accuracy and behavior.** ±1°F floor, ±0.5°F preferred. Lag tolerance: minutes. Single point. Non-inline / non-plumbing-mounted (eliminates inline thermowells, return-line probes, heat-pump-mounted sensors). Stratification-aware placement (probe ≥12–18" below surface — pin in build phase). No freeze concern (Florida).

**3. Environmental.** Continuous submersion. Salt water (`switch.omnilogic_pool_chlorinator` confirmed in `state_logger.py`). UV-exposed top. Materials must tolerate continuous salt + chlorine + UV. Acceptable: titanium, PTFE, PVC, HDPE, marine silicone, 316L stainless minimum. Mounting: floating only. Plumbed work out of scope.

**4. Power and network.** Battery only (mains and USB out). 6-month minimum life, 12+ preferred per maintenance section. All wireless paths in scope at requirements level. 2.4 GHz viable on-site (LOS to Great Room AP or upcoming Lanai AP — Hayward issue is different geometry).

**5. Integration / HA interface.** Local-first. Cloud-only eliminated (no Govee Cloud, no Inkbird Cloud-only modes). Entity contract:

- Entity: `sensor.pool_water_temp_external`
- `device_class: temperature`, `unit_of_measurement: °F`, `state_class: measurement`
- Healthy: numeric float
- `unavailable`: > 90 min stale (proposed; tunable)
- `unknown`: out of range (< 40 / > 110 °F)

Cascading fallback chain (replaces direct sensor read in blueprint):

1. Tier 1: `external_water_temp` when fresh + numeric
2. Tier 2: `local_water_temp` when `local_water_temp_reliable=true` (already in logger v2)
3. Tier 3: `target_temp` (ADR-013 — already in v1.10.1)

Logger v2 columns added: `external_water_temp`, `external_water_temp_age_min`, `external_water_temp_fresh`, `water_temp_authoritative`, `water_temp_delta`.

**6. Operational.** Minimize maintenance across battery swaps, cleaning, reseating. Parameterized auditor inputs:

- `EXTERNAL_TEMP_FRESH_MIN` (proposed 60 min)
- `EXTERNAL_TEMP_AGREEMENT_THRESHOLD_F` (proposed ±1°F)
- `EXTERNAL_TEMP_AGREEMENT_WINDOW_MIN` (proposed 30 min overlap of both fresh + pump on)

**7. Constraints.** Budget $100. Deploy by EOM 2026-05-31. Out-of-scope: chemistry sensing, flow sensing, surface-temp-only use cases.

**8. Success criteria.** Two-stage milestone — deployed/contract by EOM, verified 5–7 days later. Six gates A–F. Auditor assertions W1/W2 are post-v1 monitoring targets, not v1 gates.

---

## Decision

**v1 hardware path: reuse the existing TX13-class float case and its in-place NTC thermistor, replacing only the electronics, gasket, and battery contacts.**

**Reuse:**

- Float body, vented probe chamber, threaded gasket ring, battery compartment layout
- In-place NTC thermistor (verified alive — 41.4 kΩ at lanai-ambient ~87°F, consistent with 50 kΩ @ 25°C, Beta ≈ 3400–3500 class)
- Wire pass-through epoxy — confirmed intact via the healthy NTC reading. The original failure point was the threaded gasket, not the wire seal

**Replace:**

- Main PCB (corroded beyond repair — visible green oxidation at solder joints, slide switches, screw posts; consistent with humid salt-air ingress through degraded gasket)
- Battery contacts (corroded)
- Threaded gasket O-ring
- Conformal coat new PCB

**Build:**

- MCU: ESP32-C3 or ESP32-C6 class (3.0 V minimum compatible with battery options under consideration; ESPHome support; deep-sleep current adequate for 6+ month life at 30-min cadence)
- Sensor interface: voltage divider with 47 kΩ 0.1% metal-film reference + ESP32 ADC. ESPHome `resistance` + `ntc` platforms with declarative Steinhart-Hart calibration (no Arduino sketch, no hand-rolled math)
- Network: 2.4 GHz WiFi via ESPHome native API to HA, deep-sleep between samples
- Calibration: 3-point Steinhart-Hart at build time (ice bath, reference-thermometer-confirmed room temp, warm water ~104°F). Calibration values land in YAML

---

## Why not alternatives

**Off-the-shelf BLE (Inkbird IBS-P02R class).** Eliminated by case-reuse opportunity. Inkbird is a different form factor, requires a BLE proxy in range (Lanai voice satellite not on confirmed EOM build path; NUC USB BT range marginal), and surface-only measurement contradicts the section 2 stratification requirement. Reusing a known-good case dominates on cost, time-to-deploy, and accuracy.

**Full DIY ESP32 with newly-designed case.** Eliminated by the existing case being free, pool-validated, and already solving the float / probe-chamber / sealed-electronics packaging problem. Designing a new floating waterproof enclosure in Fusion + 3D-printing + iterating waterproofing is multiple weekends of work that's already done in this case.

**DIY Z-Wave LR 800-series.** Eliminated for v1 by EOM deadline — module sourcing + custom Z-Wave SDK firmware learning curve doesn't fit 29 days. Remains a candidate for v2 if WiFi power management proves marginal.

**Thread / Matter DIY.** Eliminated for v1 by firmware maturity. ESP32-C6/H2 Thread builds for battery temperature sensors are still evolving territory.

**Replace NTC with DS18B20 (drilling out the original).** Held in reserve as Path B fallback. Not chosen for v1 because the in-place NTC tested healthy at 41.4 kΩ — drilling out a working sensor adds risk (chamber wall puncture, debris, new seal point to engineer) for marginal benefit (DS18B20 plug-and-play vs. one-time Steinhart-Hart calibration). The NTC's original sealed pass-through is the only original seal that demonstrably survived 20+ years in salt + UV.

---

## Open design decisions (deferred to build phase)

1. **Specific MCU SKU.** ESP32-C3 vs C6 — C6 adds Thread/Matter and BLE 5 (future-proofing); C3 is cheaper and proven. Both meet the 3.0 V floor and ESPHome compatibility.
2. **Power source detail.** 2× AA as-is (~3.0 V fresh, drops to ~2.0 V end-of-life — below ESP32-C3 minimum) vs. 3× AA (~4.5 V, requires LDO) vs. 1× 18650 LiPo (~3.7 V nominal, requires modifying battery compartment). Affects 6-month battery target verification.
3. **Voltage regulator / boost circuit** if 2× AA retained.
4. **Antenna geometry inside ABS plastic case at 2.4 GHz.** Plastic is RF-transparent at this frequency, but range-test before sealing.
5. **Tether strategy.** Untethered drifter vs. fixed-point tether vs. captive zone. Affects antenna position consistency, recovery effort.
6. **Probe chamber depth below surface.** Working assumption 12–18"; verify against stratification concern.
7. **New gasket material spec.** EPDM vs. silicone vs. Viton — chlorine + salt + UV durability ranking.
8. **Calibration values.** Three (T, R) data points from build-week calibration session.
9. **Notification policy thresholds.** Every-tier-degradation vs. prolonged-only — deferred from section 5.
10. **Replacement strategy.** Spare-on-shelf vs. on-demand build. No second TX13-class case on hand, so v2 of this sensor would either reuse the v1 case (no spare) or commit to a from-scratch DIY build with fresh enclosure.

---

## Build sequence (EOM 2026-05-31 target)

Two-stage milestone per section 8:

**Stage 1 — deployed and meeting contract (target EOM):**

1. Source remaining parts (ESP32-C3 dev board, 47 kΩ 0.1% reference, fresh O-ring, battery holder per power decision, marine silicone)
2. Calibration session: 3 (T, R) data points
3. Bench-build: new PCB or perfboard with ESP32 + voltage divider, ESPHome firmware with calibration values
4. Range test antenna inside cleaned case before sealing
5. Replace gasket, install electronics, conformal-coat, seal threaded ring
6. 72-hour dry-bench burn-in (verify deep-sleep current, WiFi reconnect behavior)
7. 24-hour empty-case submersion test (gasket + new wire passages — verify no ingress before risking electronics)
8. Deploy to pool with electronics, confirm `sensor.pool_water_temp_external` populating in HA
9. Add Logger v2 columns
10. Update blueprint to read `water_temp_authoritative` (or external direct if logger phase 2 not ready by deploy)

**Stage 2 — verified (target EOM + 5–7 days):**

- Gate C 5–7 day soak window
- Gates A, B, D, E, F per section 8

---

## Success criteria

Per section 8:

**Gate A — Hardware in place.** Floating sensor deployed; tether per design decision; 72h leak/seal observation zero ingress; signal/RSSI acceptable on ≥3 readings.

**Gate B — Entity contract met.** `sensor.pool_water_temp_external` exists per section 5 contract; `unavailable` triggers at staleness threshold (verified by removing battery / blocking radio); out-of-range triggers `unknown`.

**Gate C — Data quality.** 5-day soak min (7 preferred); ≥8 pump-on intervals of ≥30 min; median |external − local| ≤ 1°F; 95th percentile |delta| ≤ 2°F; no flat-line failure (sensor doesn't report identical value > 2h while local probe moves > 0.5°F).

**Gate D — Functional integration.** Blueprint reads from `water_temp_authoritative` (or external direct if logger phase 2 not ready). Test: induce overnight pump-off; next morning's PUMP START fires at `heat_start_minutes` from real cooled water temp, not v1.10.1 fallback.

**Gate E — Logger v2 captures it.** New columns populating; 7-day CSV: < 5% empty rows during expected-fresh windows.

**Gate F — Failure modes verified.** Tier 1 → 2 cascade tested (simulate sensor offline; blueprint correctly falls to `local_water_temp_trusted`). Tier 2 → 3 already verified by ADR-013.

**Auditor assertions (post-v1 monitoring, NOT v1 gates):**

- **W1:** `external_water_temp_fresh` ≥ 90% of overnight pump-off windows (rolling 14-day)
- **W2:** median `water_temp_delta` within ±1°F (rolling 14-day, both-fresh subset)

Drafted in `pool/docs/auditor.md` post-v1, monitored 30 days before tightening to formal assertions.

---

## Trade-offs

**Better than full DIY with new case:**

- Free pool-validated case form factor
- In-place NTC + sealed pass-through avoids the highest-risk DIY task (waterproofing a new sensor entry)
- Compresses build time meaningfully — EOM achievable instead of marginal

**Better than off-the-shelf BLE:**

- Local-first, no BLE proxy dependency
- Probe-chamber depth solves stratification (BLE pucks are surface-only)
- ESPHome WiFi is already the house standard — one fewer tool family
- Material spec under control (we pick the gasket, the conformal coating, the cable gland)

**Worse than off-the-shelf BLE:**

- Custom build vs. plug-and-play
- Calibration step required (mitigated by ESPHome declarative YAML)
- Replacement strategy harder — no Amazon Prime spare, must build the next one

**Worse than full DIY with new case:**

- Inherits the case's failure mode (threaded gasket integrity, ABS UV degradation continues even with fresh gasket)
- Plan for ~3–5 year total service life on the housing before structural rework, vs. 5–10 years for a freshly-printed UV-stabilized polymer. Counter: by then, the predictive-heating model gates a v2 redesign anyway.

---

## Consequences and follow-ups

- v1.10.1 `target_temp` fallback (ADR-013) becomes the **deepest tier** of the cascade rather than the only fallback. Doesn't get removed — just demoted to tier 3.
- Logger v2 phase 2 (`local_water_temp_trusted` helper) becomes lower priority once external sensor lands; tier 1 alone covers the pump-off blind spot. Phase 2 still has value as the tier-2 buffer when external goes unavailable.
- Battery health tracking (ADR-014 candidate) gains a new client — battery telemetry from this sensor (if exposed via ESPHome) feeds the same Battery Notes pipeline.
- Auditor `pool/docs/auditor.md` gets new W1/W2 assertion candidates added post-v1.

---

## Verification

ADR closes when all gates A–F pass per stage 1 + stage 2 timeline above. Auditor assertions W1/W2 monitored separately for 30 days before formalization.

---

## Sources

- ADR-013 (`docs/decisions/013-water-temp-fallback.md`) — tactical predecessor
- `blueprints/automation/LRD/pool_automation/pool_automation.yaml` lines 472–547 — blueprint consumer chain
- `pool/scripts/state_logger.py` — chlorinator entity confirms salt water; existing trusted-temp pattern (`WATER_TEMP_SETTLING_SECONDS = 600`)
- `pool/docs/logger-v2.md` — placeholder columns already designed for this sensor
- `pool/docs/auditor.md` — assertion framework
- `pool/README.md` — predictive-heating long-term goal
- `docs/current-state.md` — Lanai AP, Lanai voice satellite, Zooz ZST39 LR controller availability
- 2026-05-02 conversation: 8-section requirements analysis + case-reuse evaluation; existing TX13-R1 VER1.0 transmitter board identified, NTC measured 41.4 kΩ at ~87°F lanai-ambient, leak path attributed to threaded gasket (not wire pass-through)
