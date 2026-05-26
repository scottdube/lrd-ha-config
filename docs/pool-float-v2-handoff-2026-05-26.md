# Pool Float v2 — Handoff Brief (2026-05-26)

Bench session in progress. Picking up from a context-full prior conversation.
Departure to NH is **tomorrow (2026-05-27)** — float must be redeployed today.

## Current physical state

XIAO ESP32-C6 (v2) is on the bench, float case open, PPK2 sourcing 3.300V into
BAT+/BAT− contacts. v2 hardware mods complete on this C6:

- NTC repinned GPIO0 → **GPIO1**
- BAT+ → 3V3 pad solder bridge (SGM6029 regulator bypassed)
- Tenmory U.FL flex PCB antenna installed on IPEX connector
- A0/GPIO0 now reads onboard battery voltage divider

Fresh L91 cells are out of the holder. NTC probe still on the C6.

## YAML state — `esphome/pool-water-temp-external.yaml`

**Remote + NUC (last pushed commit `db30ae1`)** has:
- GPIO3/14 priority-800 on_boot lambda (RF switch enable + external antenna select)
- `sleep_duration: 30min`
- Battery voltage `multiply: 2.0`

**MacBook local working tree (UNCOMMITTED)** has two edits on top of that:
- `sleep_duration: 1min` (reverted from 30min — testing continues at 1-min cadence)
- Battery voltage `multiply: 4.853` (calibrated from A0 multimeter reading)

Next action: commit + push + NUC pull + OTA flash these two edits.

```
cd ~/code/home-assistant
git add esphome/pool-water-temp-external.yaml
git commit -m "pool float: 1min testing cadence + battery voltage multiplier calibration"
git push
ssh sdube@192.168.50.11 "cd /config && sudo git pull"
```

NUC pull requires `sudo` — sdube is in wheel group but files are root:root in
`/config`. Without sudo: permission denied on git pull.

Then ESPHome dashboard → pool-water-temp-external → Install → Wirelessly.
MacBook must be on **Legacy IoT SSID** for OTA (UDM Pro blocks 3232 cross-VLAN).

## Critical finding — voltage trap (NOT fixable this season)

Sleep current is **335 µA** even with regulator bypass. Root cause confirmed
via Seeed forum: XIAO ESP32-C6 power management does not enter clean idle below
~3.5V supply. The 2× L91 series stack (3.0–3.4V across discharge curve) hits
this hardware trap. Regulator bypass had zero effect on sleep current.

**Decision:** accept 335 µA, run 30-min cadence for summer. Math:
- 247 days runtime (+79% margin over 138-day departure window)

**Next-season fix candidate:** single 14500 Li-Po with proper 3.3V LDO. Out of
scope for this deployment.

## Battery voltage calibration

Measurement on bench at PPK2 = 3.300V:
- Multimeter at A0 pin: **1.314V**
- Implied divider ratio: 2.51 (not 2.0 as documented)
- ESPHome published value (with multiplier 2.0): 1.36V → implied raw ADC 0.68V
- ADC under-reads actual A0 voltage by factor ~0.518 (ESP32-C6 ADC nonlinearity
  at 12dB attenuation, known issue)

Empirical single-point cal:
- `multiplier = 2.0 × (3.30 / 1.36) = 4.853`

Accurate at 3.3V. Across L91 range (3.0–3.4V) it'll be approximate due to ADC
nonlinearity — sufficient for state-of-charge trending, not absolute precision.
Could upgrade to `calibrate_linear` with two empirical points later.

## Pending pre-deployment sequence

1. Commit + push + NUC pull the multiplier + 1min cadence changes
2. OTA flash via Legacy IoT SSID
3. Verify published battery voltage now reads ~3.30V (PPK2 still on)
4. If verified, decide on final 30min cadence — separate commit/push/flash
5. Disable PPK2, disconnect leads
6. Install fresh 2× L91 lithium AAs (verify polarity)
7. Multimeter check fresh L91 stack ≤3.6V before final close-up
8. Close float case, confirm gasket
9. Place float in pool, reattach dual tether
10. Verify in UniFi: connection events at deployed cadence, RSSI target ~−70 dBm
    (powered RF switch + external antenna delivers +11 dB confirmed earlier)

## Key reference docs

- `docs/decisions/025-pool-float-v2-hardware-revision.md` — full v2 ADR (note:
  needs amendment with voltage trap finding)
- `docs/decisions/024-pre-departure-freeze-and-summer-update-policy.md` — summer
  update tier policy now in effect
- `docs/ppk2-c6-float-bench-quickref.md` — 1-page bench procedure
- `docs/ppk2-c6-float-bench-2026-05-26.md` — full 10-phase procedure
- `docs/current-state.md` — overall HA project state (needs update with this work)
- `esphome/pool-water-temp-external.yaml` — the float firmware

## Operating constraints (from Scott's preferences)

- Direct, precise, no-fluff
- One or two steps per reply, wait for result
- Flag inferences explicitly
- Don't say SCS when SSH works; sudo required for `/config` writes via sdube
- HA NUC: use 192.168.50.11 (not 192.168.11.155)
- Antenna inside float case dome, flat-to-earth, no case penetration
- Departure tomorrow — verify deployment same day, no margin for re-iteration
