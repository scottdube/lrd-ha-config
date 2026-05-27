# Pool Float v2 — 24-hour performance report

**Generated:** 2026-05-26 23:33Z (07:33 PM EDT)
**Window:** 2026-05-25 23:34Z → 2026-05-26 23:33Z (24 hours)
**Float state in window:** v2 hardware on used L91 cells, 1-min test cadence, deployed in pool 2026-05-26 evening EDT per ADR-025
**Source:** HA REST `/api/history/period/` for 8 entities (~1.9 MB JSON), filtered + cross-aligned with the cheat-sheet curl patterns in `docs/reference/ha-rest-api-curl-cheatsheet.md`

---

## Window structure

The 24-hour window straddles three phases. Important context for any number below:

| Phase | Approx window (UTC) | What was happening |
|---|---|---|
| Bench / pre-deploy | 23:34Z (5/25) → 17:00Z (5/26) | v2 hardware build, PPK2 captures, ADR-025 amendments, calibration work |
| OTA cycles | 17:23Z → 19:22Z | Three OTA flashes (firmware iterations), each ~3-10 min; `input_boolean.pool_float_ota_mode` toggled on/off cleanly each time |
| In-pool steady-state | 19:30Z onward (~4h captured) | Floating in pool, 1-min test cadence, used L91 cells |

The bench phase data is contaminated by intentional voltage sources (PPK2 at 3.300V), open-air RSSI in the garage (-75 to -95 dBm — not deployment-representative), and reset cycles during YAML edits. **Headline numbers in this report are from in-pool steady-state only (post 20:30Z), after the first hour of deployment settling.**

---

## Headlines — in-pool steady-state (3h 4min observed)

| Metric | Result | Target / context |
|---|---|---|
| **Wake cadence success** | **98.1% per-min** (180 wakes / 183.5 min) | 1-min test cadence; only 1 gap > 2 min in this window |
| **WiFi RSSI mean** | **−68.3 dBm** | ADR-025 amendment target: −66 to −70 dBm ✓ |
| **WiFi RSSI range** | −88 to −61 dBm | Tail outliers expected; see distribution below |
| **Battery voltage** | **3.24 V mean** (range 2.92–3.40 V) | Used L91s; trend over 4h essentially flat at ~3.20-3.30 V |
| **Filtered water temp** | **86.71°F mean** (range 77.3–88.4°F) | OmniLogic mean 89.7°F; delta analysis below |
| **OTA mode flag** | currently `off` (last toggled 23:14:58Z) | Clean — no stuck flag inflating sleep current |

**Verdict: deployment is healthy on all four primary metrics.** Cadence success at 98% on 1-min is essentially perfect; WiFi mean matches the predicted target exactly; battery voltage is in working range for used cells with no concerning slope yet; temperature reads believable values that authoritative-chain math is happily using as Tier 1.

---

## WiFi RSSI distribution (146 samples, steady-state)

| Bucket (dBm) | Count | % | |
|---|---|---|---|
| −88 to −85 | 3 | 2.1% | * |
| −85 to −80 | 14 | 9.6% | ********* |
| −80 to −75 | 27 | 18.5% | ****************** |
| −75 to −70 | 32 | 21.9% | ********************* |
| −70 to −65 | 39 | 26.7% | ************************** |
| −65 to −60 | 31 | 21.2% | ********************* |

Percentiles: p10 = −80, p25 = −75, p50 (median) = −69, p75 = −63, p90 = −62

Roughly 12% of samples sit below −80 dBm. None drop low enough to be persistent-failure-prone (the ESP32-C6 typically reconnects fine above −90 dBm) — these are the natural tail of an antenna-on-a-floating-buoy with water surface scatter and orientation drift. No action needed unless this percentage grows.

---

## Battery voltage trend (149 samples, steady-state)

| Time (UTC) | Voltage (V) |
|---|---|
| 19:30 (deploy + 30 min) | 3.06 |
| 20:42 | 3.30 |
| 21:42 | 3.24 |
| 22:38 | 3.22 |
| 23:33 | 3.20 |

Mean 3.24 V over 149 samples, with the 4-hour endpoint sitting at 3.20 V. Initial 3.06 V was a transient — likely the cells were still settling under load right after install. Over the steady 3-hour window the voltage is essentially flat, which is expected for L91s in this part of the discharge curve.

**Battery slope is too short a window to extrapolate runtime.** Wait 24-48h of true steady-state post-deploy with no OTA / bench reattachment before computing a meaningful mAh/day rate. The ADR-025 amendment projects 287 days runtime at 30-min cadence on fresh cells (current observation is 1-min cadence on used cells, so apparent drain rate will be ~30× faster than the projection — not comparable until cadence flips to 30-min).

---

## Temperature cross-validation vs OmniLogic

15 minute-aligned pairs in the steady-state window:

| Stat | Value |
|---|---|
| Min delta (omni − external) | +1.61°F |
| Max delta | +2.76°F |
| **Mean delta** | **+2.03°F** (OmniLogic consistently reads higher) |

**This is the single most important thing to watch.** A consistent +2°F offset is larger than the bench accuracy spec (±0.5°F at calibration, 2026-05-02), and the direction is reliable (omni > external in every pair). Three non-mutually-exclusive explanations:

1. **Real stratification.** External float reads surface temp; OmniLogic line probe reads water from the pool plumbing (drawn from deeper). On a sunny afternoon the surface can run cooler than the bulk if the pump has been off — but normally it'd be the other way (surface heated by sun). With pump off + cool evening + warm afternoon bulk, a +2°F bulk-vs-surface gradient is physically plausible.
2. **Pump-off OmniLogic staleness.** Per ADR-013, the OmniLogic in-line probe reads `unknown` when the pump is off; before that state, it holds the last-known value. A 2°F "drift" might be OmniLogic showing a stale-warm value while the actual surface cooled. The 24-hour OmniLogic data shows a range of 79-92°F with most readings clustered at 89-90°F — consistent with intermittent updates.
3. **NTC calibration drift.** Two-point Steinhart-Hart fit on 2026-05-02 from ice-bath + room-temp + warm-water references. Three weeks of pool exposure could have shifted the NTC. The bench test on 2026-05-02 had ±0.5°F gap at 75°F — at 87°F the gap could legitimately be larger without that being "drift."

**Recommendation:** track the delta over the next week. If it stays consistently at +1.5 to +2.5°F regardless of time of day and pump state, it's calibration offset and worth a single recal point in warm water. If it varies with pump state (smaller delta when pump is on, larger when off), it's stratification + OmniLogic staleness, no action needed. If it grows over time (e.g. trending +3°F by next week), it's drift — recalibrate.

A useful data refinement: add a derived sensor `sensor.pool_water_temp_delta_external_vs_omnilogic = sensor.pool_pool_water_temperature - sensor.pool_water_temp_external_filtered`. Trends visible in the HA Statistics view.

---

## Cadence — wake reliability

Whole 24h window: 1171 uptime publishes (uptime sensor only updates on wake, so it's the cleanest "successful wake" counter).

Steady-state (post 20:30Z):

- **180 wakes in 183.5 min = 98.1% of theoretical 1-min cadence**
- Median gap: 61s (exactly on cadence)
- Mean gap: 61s
- Max gap in steady-state: 123s (one event)

First-hour-of-deployment (19:30-20:30Z) had four longer gaps (629s, 690s, 239s, 122s) totaling ~28 min of missed time. These align with the physical settling — float was being positioned + tether adjusted + dome orientation tweaked. Not a firmware/RF issue.

**At 1-min cadence, 98% per-minute success is essentially perfect.** When you flip to 30-min cadence per the ADR-025 deployment plan, even a 90% per-cycle success rate gives ~43 publishes/day (vs target 48), which is still ample for the temperature sensor's role in the fallback chain.

---

## Things to watch

Ranked by priority.

1. **Temperature delta vs OmniLogic (+2.03°F mean).** Track for 1 week. See cross-validation section above for the diagnostic flow (is it calibration drift vs stratification vs OmniLogic-stale).
2. **Battery slope over the next 48h on the same cells at 1-min cadence.** Once we have ~2 days of clean steady-state, the slope tells us how the 12 mAh/day projection (per ADR-025 amendment math) holds against reality. Anything materially worse signals one of the suspected sleep-current issues isn't fully accounted for.
3. **Fresh-cell swap scheduled 2026-05-28/29.** Mark a "checkpoint" in the data — expect battery voltage to step up to ~3.40-3.60V, and the comparison of the same-cadence/same-RF environment before/after gives a clean delta to isolate "battery wear" from "everything else."
4. **30-min cadence flip after fresh cells in.** That's the production-mode setting per ADR-025 (gives 643-day projected runtime). After the flip, success-rate metrics will be more sensitive to occasional misses since each miss represents 30 minutes of missed temp reading rather than 1.
5. **WiFi bottom-end percentile (currently 12% < −80 dBm).** Not actionable today, but if this percentage grows month-over-month (e.g. >25% < −80 dBm), suspect float position drift, antenna orientation change, or AP-side issue. Re-check the ADR-023 omni antenna at the Lanai U7.
6. **First filtered-temp outlier cluster (77-78°F dips at 20:07-20:45Z).** Six samples of suspicious low readings during the early deployment hour. The 3-sample median filter didn't catch them — they were sustained, not single-spike. Possibly the NTC was briefly exposed to air during float placement, or the float dipped under transient surface chop. Worth one more look in the next 24h to confirm steady-state doesn't reproduce this. If it does, the median filter window size or the HA-side outlier filter may need a longer rolling window.
7. **OTA-flag hygiene.** ADR-025 amendment flags that leaving the flag on after an OTA flash blocks deep_sleep and burns the battery at ~200 mA. The 6-hour auto-clear automation is the safety net but the discipline is "always clear the flag before disconnecting from the bench." Three OTA cycles today, all cleaned up — pattern is holding. No drift here.

---

## Data sources

All extracted from the 24h history pull at 2026-05-26 23:33Z:

| Entity | Samples in 24h |
|---|---|
| `sensor.pool_water_temp_external` | 937 (raw NTC reading) |
| `sensor.pool_water_temp_external_filtered` | 917 (3-sample median in firmware, HA-side outlier filter) |
| `sensor.pool_water_temp_authoritative` | 828 (Tier 1 fallback chain — external takes precedence when fresh) |
| `sensor.pool_water_temp_external_pool_float_battery_voltage` | 302 (only began publishing 16:25Z — v2 firmware just added this sensor) |
| `sensor.pool_water_temp_external_pool_float_wifi_signal` | 863 |
| `sensor.pool_water_temp_external_pool_float_uptime` | 1171 |
| `sensor.pool_pool_water_temperature` | 90 (OmniLogic in-line probe — slower cadence) |
| `input_boolean.pool_float_ota_mode` | 8 toggles |

Methodology details and the exact curl patterns are in `docs/reference/ha-rest-api-curl-cheatsheet.md`. The raw JSON is in `/tmp/pf24.json` (sandbox-only, not committed).

---

## Open questions for next session

- Does the +2°F delta vs OmniLogic stay consistent over a week of mixed pump-on/pump-off windows?
- Battery mAh/day after 48h of true steady-state at 1-min cadence (and again after the fresh-cell swap + 30-min flip)
- Was the 20:07-20:45Z low-temp cluster a one-time deployment artifact, or does it recur?
- Should we add `sensor.pool_water_temp_delta_external_vs_omnilogic` as a template sensor for trend visibility?
- Any value in a HA-side automation that flags when `delta > 3°F` for >30 min as a calibration-drift early-warning?
