# ADR-025: Pool Float v2 hardware revision — pin reassignment, battery voltage monitoring, regulator bypass, external antenna

**Date:** 2026-05-26
**Status:** Accepted (pre-deployment validation pending)
**Related:** ADR-015 (external water temp sensor original design), ADR-023 (Lanai U7 Outdoor Built-in → Omni antenna), `docs/ppk2-c6-float-bench-quickref.md`

## Context

The PPK2 bench measurement on 2026-05-26 revealed three actionable issues with the v1 float hardware design (XIAO ESP32-C6, NTC on GPIO0, 2× L91 lithium AA → BAT+ → onboard SGM6029 buck-boost → 3V3 → ESP32). Each issue is resolvable in isolation, but they share a single hardware rework window (modifying a fresh XIAO C6 before installing in the float), so they're bundled into a v2 hardware revision per this ADR.

### Issue 1: SGM6029 buck-boost regulator quiescent current

Measured deep_sleep current at BAT+ (3.3V source) = **335 µA**. Theoretical breakdown:
- ESP32-C6 + RTC subsystem: ~5–10 µA (per Espressif datasheet, confirmed via 3V3-pad direct measurement: 15.33 µA)
- NTC voltage divider (47kΩ ref + ~35-50kΩ NTC at pool temp): ~35–40 µA
- SGM6029 buck-boost PFM quiescent (datasheet): ~30–60 µA
- Expected total: ~70–110 µA
- **Observed: 335 µA — ~225 µA more than expected**

Root cause: when fed BAT+ voltage near the regulator's 3.3V output (which happens with 2× L91 lithium AAs in series, delivering 3.0–3.4V across discharge curve), the SGM6029 operates at the buck/boost transition and cannot stay in low-power pulse-skip (PFM) mode. It runs continuously-switching with higher quiescent.

Verified by powering the C6 directly at the 3V3 pad (bypassing the regulator entirely): deep_sleep current drops to 15.33 µA — exactly matching the bare-chip spec.

### Issue 2: GPIO0 / A0 occupied by NTC ADC reading

The v1 design uses GPIO0 (which is A0) for the NTC temperature sensor ADC reading. This blocks use of the XIAO C6's onboard 200kΩ:200kΩ battery voltage divider, which is wired to A0 (per Seeed wiki).

Moving the NTC to a different ADC pin (GPIO1, 2, or 3 — all ADC1 channels on the C6) frees A0 for `analogReadMilliVolts(A0) × 2` battery voltage telemetry. This is essential telemetry for an unattended summer deployment: visibility into battery state-of-charge from HA without retrieving the float.

### Issue 3: WiFi RF marginality

Deployed float RSSI median = −86 dBm with the onboard PCB antenna and the RF switch (FM8625H) in unpowered leakage mode (because the v1 firmware doesn't configure GPIO3/GPIO14 to power the switch). Per Seeed forum empirical data, a properly-powered external antenna delivers ~+20 dB advantage over the leakage-mode onboard antenna scenario.

The Tenmory U.FL flex PCB antenna ordered for this project sits unused. Installing it during the v2 rework + properly powering the RF switch should land RSSI in the −66 to −70 dBm range, eliminating the marginal-link issues observed all spring.

## Decision

Bundled v2 hardware revision. All four changes applied to a fresh XIAO C6 (one of the boards arriving from the recent Amazon order) before installation in the float:

### Change 1 — Regulator bypass (BAT+ → 3V3 direct connection)

Solder a short wire from the BAT+ pad to the 3V3 pad on the underside of the XIAO C6. This bypasses the SGM6029 entirely — battery voltage feeds the ESP32 chip and onboard 3V3 rail directly.

**Voltage range verification required before deployment:** fresh 2× L91 in series measured at no-load should be ≤3.6V (XIAO ESP32-C6 absolute max). Typical fresh reading: 3.4V — well within spec. Cold-temperature peak: up to 3.62V briefly — at the edge of spec, acceptable for brief excursion.

Risk accepted: no regulation between battery and ESP32. If a single L91 cell faults to a high voltage during install, the chip could be damaged. Multimeter check before final assembly mitigates.

### Change 2 — NTC pin reassignment (GPIO0 → GPIO1)

Move the NTC analog input from GPIO0/A0 to GPIO1/A1. The 47kΩ reference resistor and NTC connection points on the custom 3D-printed ESP32_Deck need wire rerouting only — no PCB change.

YAML update: change `pin: GPIO0` to `pin: GPIO1` in the `pool_temp_voltage` ADC sensor definition.

### Change 3 — Battery voltage monitoring via onboard A0 divider

Free GPIO0/A0 is now connected to the XIAO C6's onboard 200kΩ:200kΩ voltage divider (already present on the board, sees BAT+÷2). With v2's BAT+ tied to 3V3, A0 sees half of supply voltage = ~1.65V at fresh-battery, ~1.5V mid-life, ~1.35V near-EOL.

YAML addition: a new ADC sensor on GPIO0 with 12dB attenuation, lambda multiplier of 2.0 to recover supply voltage. Publishes as `sensor.pool_water_temp_external_battery_voltage`. Update interval: every wake cycle.

### Change 4 — External antenna + RF switch enable

Install the Tenmory U.FL flex PCB antenna pigtail on the XIAO C6's IPEX (U.FL/MHF1) connector. Mount the antenna flex PCB inside the float case top dome, oriented to lay flat-to-earth in the existing molded channel.

YAML addition — `on_boot` priority 800 block to configure the FM8625H RF switch:
```
esphome:
  on_boot:
    - priority: 800
      then:
        - lambda: |-
            pinMode(3, OUTPUT);
            digitalWrite(3, LOW);
            pinMode(14, OUTPUT);
            digitalWrite(14, HIGH);
    - priority: -100
      then:
        - script.execute: take_reading_and_sleep
```

Priority 800 runs before WiFi init (which is around priority 200). GPIO3 LOW powers the FM8625H switch (datasheet ENABLE pin is active-low); GPIO14 HIGH selects the external U.FL antenna port (vs internal PCB antenna at LOW).

### What stays the same

- 2× Energizer L91 lithium AA in series, custom 3D-printed battery holder
- WiFi config (BSSID-locked to Lanai U7 Outdoor)
- Deep sleep cycle (cadence determined by pre-deploy battery math)
- DFS sdkconfig flags from v1
- 3-sample median ADC filter
- HA-side outlier filter sensor (`sensor.pool_water_temp_external_filtered`)
- The deployed v1 C6 stays in service through summer; v2 is the design pattern for next-season hardware refresh and any future float instances

## Expected outcomes

**Deep sleep current:** 335 µA → ~55 µA (15 µA chip + 40 µA NTC divider). Approximately 6× improvement in sleep contribution.

**Battery life at various cadences (v2 hardware, fresh L91s, 2700 mAh):**

| Cadence | Daily mA·h (wake + sleep) | Runtime | vs 138-day need |
|---|---|---|---|
| 5 min | 17.3 + 1.32 = 18.6 | 145 days | barely |
| 10 min | 8.6 + 1.32 = 9.9 | 273 days | +98% |
| 15 min | 5.8 + 1.32 = 7.1 | 380 days | +175% |
| 30 min | 2.9 + 1.32 = 4.2 | 643 days | +366% |

Wake energy assumed unchanged from v1 measurement (0.06 mA·h per cycle on a clean wake).

**WiFi RSSI:** −86 dBm → ~−70 dBm at the pool location (per Seeed forum empirical comparison + ADR-023's confirmation that the AP-side antenna change alone didn't move the needle for the float). Combined effect of powered RF switch + external antenna should be visible immediately.

**Battery voltage telemetry:** New HA entity `sensor.pool_water_temp_external_battery_voltage`. Visible degradation curve over the summer enables predictive notification before EOL.

## Pre-deployment validation

Before installing in the float, the v2 C6 needs:

1. **Bench voltage measurement of fresh 2× L91 in series under no load** — confirm <3.6V (typical: 3.4V).
2. **PPK2 source-mode capture at the bench** with the new firmware — confirm deep_sleep at ~55 µA range, wake cycle behavior nominal.
3. **External antenna RSSI test at bench** — same bench location with old C6 (current onboard antenna + unpowered RF switch) gave baseline X dBm; new C6 with external antenna should give X+15 to X+20 dBm.
4. **Float reassembly + redeployment** with fresh L91s — final pool RSSI check should be ~−70 dBm range.

## Rollback

If the v2 hardware exhibits issues in field (brownouts, premature battery depletion, instability), the v1 deployed float continues to function — it's still in the pool. The v2 hardware can be flashed back to v1 firmware (revert YAML pin assignments + remove RF switch config + accept the 335 µA sleep). The regulator bypass solder joint can be cut to restore the SGM6029 in the path.

## Related future work

- **Single 14500 Li-Po with proper LDO**: would eliminate the lithium-AA voltage range concern + give a higher cell voltage that lets the SGM6029 work cleanly. Different battery holder geometry required.
- **Custom PCB with sized LDO**: cleanest engineering path. Defer until summer-long deployment data informs design.
- **HA template + automation for low-battery notification**: triggered off the new battery voltage sensor. Phase 2 of battery health tracking (ADR-014).

---

## Amendment — 2026-05-26 deployment session

Pre-deployment validation revealed several findings that adjust the expected outcomes above. v2 flashed and deployed to the pool 2026-05-26 evening EDT.

### Voltage trap confirmed — bypass alone doesn't drop sleep current to 55 µA

PPK2 source-mode capture at 3.300 V on the v2 hardware (regulator bypassed, all four changes applied) measured deep_sleep current at ~381 µA, not the predicted 55 µA. Root cause: the SGM6029 bypass eliminates the regulator's switching quiescent contribution, but the XIAO C6's onboard charge-controller IC is parasitically powered from the 3V3 rail through internal protection diodes whenever the supply sits in the 3.0–3.6 V band. This is independent of whether USB is connected and is not addressed by the regulator bypass alone. Per Seeed forum threads, the ESP32-C6 power management does not enter clean sub-100 µA sleep below ~3.5 V supply, and the 2× L91 series stack range (3.0–3.4 V across discharge curve) sits squarely inside this trap.

Fully eliminating the residual draw would require cutting the trace feeding the charge IC from the 3V3 net (needs the board schematic) or replacing the cell topology with a single 14500 Li-Po behind a proper LDO (already listed under Related future work).

Updated runtime math at 30-min cadence: 381 µA sleep × 24 h = 9.14 mAh/day, plus 48 wakes × 232 mC per wake = 3.1 mAh/day, total ~12.2 mAh/day. Against the L91 stack's 3500 mAh nominal: ~287 days runtime, clearing the 138-day departure window with >100 % margin. The trap is accepted for the v2 deployment.

### Battery voltage cal needs 2-point `calibrate_linear`, not single-point multiplier

The 200 kΩ : 200 kΩ onboard divider feeding A0 has a measured ratio closer to 2.51 : 1, not 2.0 : 1 as the Change 3 section assumed. Combined with the ESP32-C6 ADC's nonlinearity at 12 dB attenuation, a single `multiply` filter cannot accurately recover supply voltage across the L91 discharge range.

Empirical cal procedure that landed: PPK2 source meter at two known voltages (3.000 V and 3.600 V bracket the L91 discharge curve), capture published `battery_voltage` with whatever filter is currently on the sensor, back-calculate raw ADC from `raw = published / current_multiplier`, then replace the multiplier with a `calibrate_linear` filter using the two points. Validated 2026-05-26: at PPK2 3.300 V midpoint the two-point fit predicts 3.43 V published; observed 3.11 V. Residual midrange bowing ~6 % from ADC nonlinearity — acceptable for trend monitoring (Tier 2 EOL detection), not absolute precision.

This is the canonical pattern for any ADC sensor on the C6 at 12 dB attenuation that needs accuracy beyond ±20 %.

### Charge LED flashes continuously in v2 modded topology

Once the SGM6029 is bypassed and L91s feed 3V3 directly, the onboard red charge-status LED flashes continuously even with no USB connected. Per Seeed docs the documented states are battery-only + no USB = LED off, battery + USB charging = LED flashes. The v2's continuous flash is a non-documented state caused by the charge IC's STAT pin entering an indeterminate toggling state when the 3V3 rail is energized via the bypass instead of via the IC's regulated output.

LED current contribution is small — PPK2 captured ~70 µA peak-to-peak oscillation in the sleep floor with mean 381 µA. Removing the LED (hot air or fine-tip iron, 280–300 °C, tweezer-lift) eliminates the visible flash but does not measurably change average sleep current; the charge IC continues toggling regardless. Cosmetic surgery, not a battery-life intervention. The series resistor next to the LED can stay — without the LED downstream it sits at an open node and draws zero.

### OTA workflow gotcha — `input_boolean.pool_float_ota_mode` must be cleared post-flash

The firmware's wake script gates `deep_sleep.enter` behind the `ota_mode_flag` binary sensor. If the flag is left on after an OTA flash, the device stays awake indefinitely and sleep-current measurements come back at ~200 mA instead of ~381 µA. Easy to miss because `automation.pool_float_ota_mode_auto_clear_at_6h` only fires 6 h later. Pre/post-OTA checklist now explicit: clear the flag with `curl ... /api/services/input_boolean/turn_off` before any PPK2 measurement or runtime expectation.

### In-pool RSSI baseline — target met

Final in-pool readings 2026-05-26 17:00 EDT onward: **−61 to −70 dBm, mean ~−66 dBm**, with publish reliability ~77 % per minute on the 1-min test cadence. Meets the predicted −66 to −70 dBm range from the bundled v2 changes (powered RF switch + external U.FL antenna + ADR-023's omni AP antenna). Bench readings during the LED-rework phase showed −75 to −95 dBm (garage, far from AP) — those values are not deployment-relevant.

### Bone-dry case after overnight bench cycle

After the v2 build the float was run on the bench overnight before deployment. Morning case-open revealed zero condensation inside the case — validates the ADR-015 condensation analysis and the gasket / dome / desiccant approach against the v1 moisture failure mode.

### Status

Pre-deployment validation complete; v2 deployed in pool 2026-05-26 evening on used L91 cells at 1-min cadence for continued in-pool data collection. Fresh-cell swap and final flip to 30-min cadence + final OTA scheduled for 2026-05-28/29 (Thu/Fri) before the 2026-05-30 (Sat) departure.
