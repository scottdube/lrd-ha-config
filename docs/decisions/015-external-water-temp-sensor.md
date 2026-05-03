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

## Thermal and condensation analysis (added 2026-05-02)

The original case-reuse decision assumed the threaded gasket was the primary failure mode, with humid salt-air ingress as the corrosion driver. **Empirical observation during calibration changed that read.**

### Observation

During the 2026-05-02 NTC calibration session, **visible condensation formed inside the upper compartment within ~15 minutes of submerging the lower body in the 32°F ice bath** — without solar gain, without long-term humidity exposure, without gasket leakage. The case had been opened, electronics removed, then loosely reassembled at lab humidity (~75°F / 60% RH) before the calibration dunk.

### Why it happened (psychrometric basics)

- Trapped air inside the case at sealing time: ~75°F / 60% RH → dew point ~60°F
- Submerging the lower body in 32°F ice water rapidly cooled interior surfaces of the lower compartment well below the 60°F dew point
- Any surface below dew point condenses water vapor out of the trapped air — visible droplets formed within minutes

### Why this is the load-bearing failure analysis

The original PCB's corrosion pattern matches this mechanism better than gasket leakage:
- Corrosion concentrated at battery contacts and slide switches (interior surfaces, cool side)
- Wire pass-through epoxy intact (a continuous liquid-water seal would have failed if liquid water was the path)
- Original gasket condition consistent with normal compression-set aging, not catastrophic leak

### What this means in service

Condensation cycles run **continuously**, multiple times per day, regardless of gasket integrity:
- Overnight pool water cooling drops the lower body below dew point of trapped upper-compartment air
- Solar gain on the clear dome over the dark LCD drives a daily 30–60°F internal top-to-bottom gradient (worst-case Florida noon estimate)
- Each cycle re-exposes interior contacts to condensed moisture, accelerating salt-corrosion when any salt aerosol is present
- A "perfect" gasket only slows molecular permeation through ABS — it does not prevent condensation of already-trapped humidity

### Required mitigations (not optional — promoted from "open design decisions")

| Mitigation | Addresses |
|---|---|
| **Hydrophobic vent membrane** (Goretex / ePTFE breather) installed in upper compartment wall | Pressure equalization during thermal cycles without pumping air through gasket; root cause of breathing-induced air exchange |
| **Indicating silica gel desiccant** (1–2 g) inside upper compartment, replaced with each battery swap | Captures initial trapped humidity + any diffusion ingress between swaps |
| **Boeshield T-9** spray on PCB, battery contacts, and internal metal hardware | Single-product moisture mitigation: active moisture displacement + thin waxy protective film. Replaces both conformal coating and dielectric grease in this build. Marine/aviation-grade corrosion inhibitor with multi-year service records in similar environments. **Reapplied at each battery swap** (already an existing maintenance touch point — no incremental burden). Verify ABS plastic compatibility on a scrap before applying broadly. |
| **Reflective treatment** on inside of clear dome (aluminum tape or white vinyl) + remove dead LCD | Eliminates the daily solar-gain gradient driver |
| **Reuse existing silicone gasket with silicone grease lubricant** (replace only if inspection fails) | Reduces molecular permeation rate; secondary defense. Silicone grease prevents bunching during threaded-ring tightening, gives even compression around perimeter, fills micro-imperfections in the groove |

The vent membrane is the single highest-leverage mitigation because it addresses the root mechanism (thermal-cycle-driven air pumping). Without it, every other mitigation fights the symptoms of an air exchange that happens by design every time the case heats and cools.

---

## Open design decisions (deferred to build phase)

1. ~~**Specific MCU SKU.**~~ **Resolved 2026-05-02:** ESP32-C6 (XIAO form factor, on hand). Future-proofing via WiFi 6 / BLE 5 / 802.15.4 (Thread / Zigbee / Matter) was the deciding factor — v1 ships on WiFi 2.4 GHz, but v2 has the option to switch radio paths without a hardware respin. ESPHome supports it natively (verify ESPHome version ≥ 2024.x at build time).
2. ~~**Power source detail.**~~ **Fully resolved 2026-05-02:** 2× **AA** lithium primary (Energizer Ultimate Lithium class) in the existing battery compartment. Original case shipped with 2× AAA alkaline; AA cells fit "a little tight but doable" per fitment check 2026-05-02 evening — minor compartment adjustment may be needed but no custom holder required. Decision drivers: leakage immunity in the salt-humid environment (matches the case's inherited failure mode — original alkalines corroded the contacts), voltage stability across discharge keeps the ESP32-C6 fed directly without a regulator, low self-discharge for 6+ month unattended use, lower contamination consequence if the gasket ever fails, **2× AA lithium primary (~2700 mAh useful) gives comfortable margin across all power scenarios — 17 months optimized / 12 months typical / 6 months worst-case**, so we're not depending on hitting optimized targets. Trade-offs accepted: ~3–5× cost-per-swap vs alkaline, flatter discharge curve makes voltage-based remaining-life telemetry weak (mitigated by tracking cycle count + cumulative awake-time in ESPHome instead).
3. ~~**Voltage regulator / boost circuit.**~~ **Fully resolved 2026-05-02:** none. ESP32-C6 fed directly from 2× lithium primary AA. Cells hold ≥3.0 V series for ~80–85% of capacity, well within the C6's 3.0–3.6 V spec. The 15–20% remaining capacity past the discharge cliff isn't worth a $2–3 boost-converter BOM, 4–6 added components, ~10% efficiency penalty as regulator heat, and an extra failure mode. PCB design simplified accordingly — no boost-converter footprint reserved. If chemistry ever flips to alkaline mid-life, a boost converter rides on an inline daughterboard rather than a respin.
4. **Antenna geometry inside ABS plastic case at 2.4 GHz.** Plastic is RF-transparent at this frequency, but range-test before sealing.
5. **Tether strategy.** Untethered drifter vs. fixed-point tether vs. captive zone. Affects antenna position consistency, recovery effort.
6. **Probe chamber depth below surface.** Working assumption 12–18"; verify against stratification concern.
7. ~~**New gasket material spec.**~~ **Resolved 2026-05-02:** reuse the existing silicone gasket, lubricated with silicone grease (the same Permatex 22058 dielectric grease used on battery contacts — silicone-on-silicone compatibility is ideal, and the grease doubles as the contact corrosion inhibitor). Rationale: now that the thermal/condensation analysis identifies condensation as the dominant failure mode rather than gasket leakage, the original gasket's role is downgraded to "secondary defense against molecular permeation," for which a 20+ year-old silicone gasket in inspectable condition is adequate. Silicone is materially stable in storage; if it still has compression resilience (springs back when pressed with a thumbnail) and no visible tears or embedded debris, it's reusable. **Build-phase inspection criteria before reuse:** (1) press-test for compression resilience, (2) visual inspection for cracks / tears / embedded particles, (3) clean with IPA before re-greasing. **Fallback if inspection fails:** Viton square-section replacement per original BOM. Also resolves the square-section sourcing concern (existing gasket already fits its groove).
8. ~~**Calibration values.** Three (T, R) data points from build-week calibration session.~~ **Resolved 2026-05-02** — see `pool/docs/external-water-temp-calibration.md`. Three points captured (32.0°F/153kΩ, 73.7°F/52.6kΩ, 109.5°F/22.8kΩ), Steinhart-Hart coefficients fit, NTC characterized as 47 kΩ @ 25°C / Beta ≈ 3823. ESPHome multi-point calibration block ready to drop into firmware.
9. **Notification policy thresholds.** Every-tier-degradation vs. prolonged-only — deferred from section 5.
10. **OTA / maintenance access pattern (added 2026-05-03).** Production cadence is 30-min sleep / ~6-sec wake — OTA windows are too small to reliably hit from the dashboard. Solution pattern:
    - Add `input_boolean.pool_float_ota_mode` helper in HA
    - Firmware imports it via `binary_sensor: platform: homeassistant`
    - Script checks the flag at end of each wake cycle: if ON → call `deep_sleep.prevent` and stay awake; if OFF → normal `deep_sleep.enter`
    - **Operational workflow:** toggle ON → wait up to 30 min for next wake → device stays awake → push OTA from dashboard → toggle OFF → next wake resumes sleep cycle
    - **Worst-case OTA latency:** 30 min from intent to push.
    - **Dead-man backstops (consistent with ADR-011 service-lockout pattern):**
      - **Mobile notification at 60 min** if `input_boolean.pool_float_ota_mode` has been ON for ≥1h. "Pool float still in OTA mode — battery draining at ~50× normal rate."
      - **Auto-clear at 6h** (HA automation flips the boolean back to OFF if forgotten). 6 hours of continuous wake ≈ 480 mAh = ~18% of AA lithium capacity. Limits damage from forgotten state to ~2 months of normal-cycle equivalent.
    - **Confirmation sensor (refinement):** add a binary template sensor exposing the device's `deep_sleep.prevent` state back to HA, so we can confirm the flag was actually received before pushing. Avoids pushing into a still-sleeping device because the flag hadn't propagated yet.
    - **Followup item:** define the HA automation that watches the boolean's age and fires both notification + auto-clear. Belongs in `packages/pool/` alongside other pool-related automations.
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
7a. **Float buoyancy / trim test** — 2× AA lithium primary (~29 g) is ~6 g heavier than the original 2× AAA alkaline (~23 g) the case was balanced for. Float will ride slightly *lower* in water than original, which puts the probe chamber vent slots more deeply submerged — *better* for stratification immunity, not worse. Float in water with batteries installed, verify chamber stays comfortably submerged but doesn't sink. If float rides too low (water entering above the threaded ring line), reconsider battery choice. No ballast anticipated.
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
- `pool/docs/external-water-temp-calibration.md` — NTC calibration data, Steinhart-Hart fit, ESPHome calibration block
- `pool/docs/external-water-temp-bom.md` — bill of materials with sourcing notes; reflects the moisture-mitigation requirements from this ADR's thermal/condensation analysis
- `pool/README.md` — predictive-heating long-term goal
- `docs/current-state.md` — Lanai AP, Lanai voice satellite, Zooz ZST39 LR controller availability
- 2026-05-02 conversation: 8-section requirements analysis + case-reuse evaluation; existing TX13-R1 VER1.0 transmitter board identified, NTC measured 41.4 kΩ at ~87°F lanai-ambient, leak path attributed to threaded gasket (not wire pass-through)
