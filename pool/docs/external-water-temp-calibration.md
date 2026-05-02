# External water temp sensor — NTC calibration data

**Calibration date:** 2026-05-02
**Operator:** Scott
**NTC source:** factory-installed thermistor in the existing TX13-class floating thermometer case (per ADR-015)
**Reference probe:** Scott's calibrated digital probe (verified against ice point — see "Reference probe verification" below)
**Multimeter:** measuring resistance across the daughterboard pads inside the float upper compartment

---

## Reference probe verification

Probe verified against ice-point physical reference (32.0°F, freezing point of water at 1 atm) before the NTC calibration session.

- Bath: distilled water + crushed ice, ~75/25 ice/water slurry, stirred, insulated container
- Probe stabilized reading: 31.9°F
- True bath temperature (physical reference): 32.0°F
- **Probe offset: −0.1°F** (well inside both consumer-grade tolerance and Scott's ±0.5°F accuracy spec)

For the NTC calibration data points below, the probe's −0.1°F offset is treated as zero — within measurement noise of all other sources (multimeter resolution, NTC self-heating from ohmmeter excitation, thermal lag).

The ice-point point (point 1) uses the bath's physical reference temperature of **32.0°F**, not the probe reading, because the bath itself IS the reference.

---

## Calibration data points

| Point | Bath / condition | T (°F) | T (°C) | T (K) | R (Ω) |
|---|---|---|---|---|---|
| 1 | Ice slurry (physical ref) | 32.0 | 0.00 | 273.15 | 153,000 |
| 2 | Tap water at room temp | 73.7 | 23.17 | 296.32 | 52,600 |
| 3 | Warm water bath | 109.5 | 43.06 | 316.21 | 22,800 |

**Procedure notes:**

- All three baths used filtered water (refrigerator-filtered for ice; tap for points 2 and 3)
- 15 min minimum stabilization time at each point with both probe and float chamber submerged at the same depth
- Float chamber vent slots fully submerged so chamber filled with bath water, not air
- Probe and NTC float at the same depth, occasional stirring
- Resistance measured at the daughterboard pads (preserves the original wire pass-through epoxy seal — see ADR-015 for why this matters)

---

## Steinhart-Hart fit

Standard Steinhart-Hart equation: `1/T(K) = A + B·ln(R) + C·(ln R)³`

Coefficients fit to the three data points above:

- **A = 1.132 × 10⁻³**
- **B = 1.795 × 10⁻⁴**
- **C = 2.271 × 10⁻⁷**

Verification: coefficients reproduce all three (T, R) data points within ~0.05 K. Clean fit, no statistical concerns.

---

## NTC characterization

Implied properties from the fit:

- **R₂₅ ≈ 47 kΩ** (resistance at 25°C / 77°F — the canonical NTC datasheet reference point)
- **Beta ≈ 3823** (between 0°C and 100°C span)
- **Class:** 47 kΩ @ 25°C consumer-grade NTC, slightly higher Beta than the most common 3950 spec — consistent with a 2003-era weather-station thermistor

This characterization is for reference only — the Steinhart-Hart fit is the truth-of-record for converting R to T.

---

## ESPHome calibration block

Drop directly into the ESPHome float firmware:

```
- platform: ntc
  sensor: pool_temp_resistance
  calibration:
    - 0.0°C -> 153kOhm
    - 23.17°C -> 52.6kOhm
    - 43.06°C -> 22.8kOhm
  name: "Pool Water Temp External"
  id: pool_temp_external
```

Build-phase verification needed: confirm exact `ntc` platform calibration syntax against current ESPHome docs (multi-point form vs `b_constant` form). The above is the multi-point form; ESPHome computes Steinhart-Hart internally from the three (T, R) pairs.

The companion `resistance` platform feeds this:

```
- platform: resistance
  sensor: pool_temp_voltage
  configuration: DOWNSTREAM
  resistor: 47kOhm
  id: pool_temp_resistance
```

`DOWNSTREAM` vs `UPSTREAM` selection follows from the physical wiring direction — verify against ESPHome docs and the chosen MCU's ADC input topology at build time.

---

## Predicted accuracy across the pool operational range

Pool operational range: 50–95°F (10–35°C). All three calibration points bracket this range — the blueprint reads from interpolation in service, not extrapolation.

**Estimated accuracy: ±0.2°C ≈ ±0.4°F across operational range.**

Inside Scott's ±0.5°F preferred accuracy spec with margin. Comfortably inside the ±1°F floor.

---

## Reference R values for in-service sanity check

Use this table during deployment / Gate C verification (ADR-015) to spot-check that live readings match the curve. If the float reports an R that's wildly off the table for the actual water temp, something's wrong (calibration drift, sensor degradation, electrical noise, divider reference resistor off-spec).

| Pool T (°F) | Pool T (°C) | Expected NTC R (kΩ) |
|---|---|---|
| 50 | 10.0 | ~95 |
| 60 | 15.6 | ~72 |
| 70 | 21.1 | ~57 |
| 75 | 23.9 | ~50 |
| 80 | 26.7 | ~45 |
| 85 | 29.4 | ~40 |
| 89 (target swim) | 31.7 | ~36 |
| 95 | 35.0 | ~32 |

---

## Re-calibration triggers

Re-run this calibration session if any of the following occurs:

- NTC sensor replaced (drilling out the original per ADR-015 Path B fallback)
- Auditor assertion W2 (rolling-14-day median |external − local| within ±1°F) trends toward the threshold for >7 days while local probe is verifiably accurate
- Gate C 5–7 day soak window fails on Δ-vs-local during stage 2 of EOM 2026-05-31 deploy
- Visible biofouling, scale buildup, or housing damage that would alter thermal coupling
- 12+ months elapsed since last calibration (drift baseline not yet established for this NTC; revisit cadence after first year of operation)

Document new calibration data by appending a new section to this file, dated, and replacing the active Steinhart-Hart coefficients + ESPHome calibration block. Old calibration data stays in the file as historical record.

---

## Sources

- ADR-015 (`docs/decisions/015-external-water-temp-sensor.md`) — parent decision document
- 2026-05-02 calibration session conversation — three measured points + reference probe verification
