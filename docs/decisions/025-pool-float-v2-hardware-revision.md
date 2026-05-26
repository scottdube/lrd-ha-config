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
