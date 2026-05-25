# ADR-023: Switch Lanai U7 Outdoor antenna from Built-in (directional) to Omni

**Date:** 2026-05-24
**Status:** Accepted (in test; pending 24h verification)
**Related:** ADR-015 (external water temp sensor), `docs/pool-float-wifi-baseline-2026-05-24.md`

## Context

Throughout May 23-24 we tracked the pool water temp float (XIAO ESP32-C6, 10-min deep-sleep cadence) showing ~60% WiFi connect success — clean post-tuning numbers, no submersion confounding. RSSI sat at -85 to -89 dBm, scraping the WiFi sensitivity floor.

A series of firmware-side optimizations (static IP, BSSID lock, max TX power, extended wait-until budgets, on-boot race fix, ESP-IDF DFS + tickless idle, connect-time instrumentation via `pool_float_uptime`) compounded but did not change the underlying RF link quality. With successive captures all landing in the same -85 to -89 dBm RSSI band regardless of firmware-side changes, the bottleneck was clearly RF, not software.

Link-budget analysis at the actual geometry (AP 14 ft up + 26 ft horizontal, ~30 ft diagonal, AP TX +20 dBm + 8 dBi gain) predicted free-space RSSI of approximately -31 dBm. The measured -85 dBm at the float represents ~55 dB more loss than free space — most of it (~20-30 dB) attributable to the float's onboard chip antenna inside a sealed case near the waterline, the remainder split between lanai screen enclosure, polarization mismatch, and water proximity.

While investigating AP-side options, the Lanai U7 Outdoor settings revealed two facts that were not previously understood:

1. The "Antenna Type" dropdown in UniFi → Devices → U7 → Radios offers two options: **Built-in Antenna** (the 8-12.5 dBi internal directional "Super Antenna") and **Omni Antenna** (the two external 3-4 dBi omni elements visible as the "ear" pods on the unit). The U7 Outdoor is NOT internal-antenna-only; it ships with two software-switchable RP-SMA omni antennas plus the integrated directional.
2. The factory default in our deployment was **Built-in Antenna** — the directional. The U7 Outdoor's directional element is designed for the typical wall/pole mount orientation where the beam projects horizontally toward a target area. With this AP ceiling-mounted in the lanai, that beam was pointing in an orientation that did not include the pool location at LRD.

The "Built-in" label is misleading. It sounds like the only / default / always-correct choice. In practice, for a ceiling-mounted U7 Outdoor covering a horizontal area below it, **Omni Antenna is almost certainly the right choice** unless the directional beam happens to be aimed at the target.

## Decision

Switch Lanai U7 Outdoor → Antenna Type → **Omni Antenna**. Switch Mode → **Outdoor** (was Indoor). Channel and TX power unchanged (Auto / 20 MHz / High).

Verified empirically with a UniFi WiFiman test from a phone held near the pool surface, same position before and after the switch:

| Antenna Type | Phone RSSI (Legacy IoT SSID) at pool |
|---|---|
| Built-in (directional) | -63 to -70 dBm |
| Omni | -55 to -57 dBm |

Improvement: ~8-13 dB, midpoint **~10 dB**. Free fix, no hardware change, no firmware change.

## Expected impact on the pool float

If the float sees a similar uplift (uplink direction; symmetric WiFi suggests it will), its -85 to -89 dBm baseline becomes ~-75 to -79 dBm. That should push the connection from "marginal / at floor" to "workable" and significantly reduce the 40% timeout rate observed in May 24's data.

If float-side benefit lands at the full ~10 dB:
- Connect-success rate likely climbs from ~60% to ~85-90%.
- Wake-time average drops because fewer cycles hit the 35s timeout wall.
- Battery-life budget improves, and 30-min cadence (previously borderline) becomes viable for summer-long deployment.

## Verification plan

24-hour clean window starting 2026-05-24 evening. Same data sources as the prior baseline:

- UniFi connect-events count (target: >120/24h, vs prior 88)
- HA `sensor.pool_water_temp_external_pool_float_uptime` histogram (target: p95 drops below 20s, vs prior near-35s observed)
- Per-event RSSI trend (target: median in -75 to -80 dBm range)

If verification confirms ~85% success rate or better, defer the external float antenna upgrade and the case modifications to "next season" improvements. Keep the Tenmory U.FL antenna order on hand for backup or future battery-life optimization (external + above-water antenna would stack additional dB on top of the AP-side fix).

## Why this wasn't caught earlier

The "Antenna Type" setting was at the factory default "Built-in Antenna" and the UI doesn't surface the choice prominently — you have to click into the AP's Radio settings to see it, and the label doesn't telegraph that there are two physical antennas to choose between. The U7 Outdoor product page mentions both internal and external antennas in the specs, but the casual reading is that "internal" is the default and "external" is for special cases. Reality is the opposite for ceiling-mount: the directional beam misses most of the coverage area unless you aim the AP at it.

Operationally relevant for the future: any time a UniFi AP shows "Antenna Type" in its radio settings, expand the dropdown and confirm which choice matches the deployed geometry. Don't trust the default.

## Future work (deferred)

- 24h verification window per above
- External float antenna (Tenmory MHF1, ordered): stack additional gain on top of the AP-side fix for future battery optimization or harsher conditions
- PPK2 bench measurement (arriving 2026-05-25): characterize actual battery consumption with the improved RF link
- Consider whether a second AP closer to the pool is needed — likely not after this fix, but the data will tell
