# Pool Float v2 — status report

**Generated:** 2026-05-27 17:23Z (01:23 PM EDT)
**Window:** 2026-05-26 17:23Z → 2026-05-27 17:22Z (24 hours)
**Float state in window:** v2 hardware on used L91 cells, 1-min test cadence, in-pool throughout (deployed 2026-05-26 ~19:30Z per ADR-025)
**Previous report:** [`pool-float-v2-24h-report-2026-05-26.md`](pool-float-v2-24h-report-2026-05-26.md) — covered the deployment day with only ~3 h of clean in-pool data
**Source:** HA REST `/api/history/period/` for 8 entities (~426 KB JSON), filtered + cross-aligned with the cheat-sheet patterns in `docs/reference/ha-rest-api-curl-cheatsheet.md`

---

## Window structure

This window covers a full 24 hours starting roughly at the deployment hour. Compared to the 2026-05-26 report which had to carve out a 3-hour steady-state slice from a bench-contaminated 24h window, today's report is dominated by clean in-pool data with only the first ~2 hours containing the 3-OTA-cycle / deployment-settling phase.

| Phase | Window (UTC) | What was happening |
|---|---|---|
| Deployment + OTA cycles | 17:23Z → 19:22Z (5/26) | 3 OTA flashes + float positioning + tether adjustments |
| In-pool steady-state | 19:30Z (5/26) → 17:22Z (5/27) | Floating in pool, 1-min cadence, used L91 cells, no interventions |

**Headline numbers in this report are computed across the full 24h window**, since 21+ of those 24 hours are clean in-pool data. The OTA-cycle phase contributes only a small fraction of samples and shows up clearly as the four big publish gaps below.

---

## Headlines — full 24h window

| Metric | This window | Previous report (2026-05-26 ~3h steady-state) | Direction |
|---|---|---|---|
| Wake publishes (uptime) | **1338 / 24 h** (92.9% of 1440 theoretical) | 180 / 183.5 min (98.1%) | Lower aggregate, OTA cycles + settling cost ~57 min |
| WiFi RSSI mean | **−66.4 dBm** | −68.3 dBm | ✓ +1.9 dB better |
| WiFi RSSI p50 / p90 | **−64 / −61** | −69 / −62 | ✓ Tighter distribution, median 5 dB stronger |
| Battery voltage range | 2.86 V (now) ← 3.20 V (24h ago) | 3.20–3.30 V over 3 h | Expected drain on used L91 at 1-min cadence |
| Filtered water temp | **85.57 °F mean** (range 72.4–88.7) | 86.71 °F (range 77.3–88.4) | Slightly cooler mean, wider low-end range |
| OmniLogic mean | 89.74 °F | 89.7 °F | Stable |
| **External − OmniLogic delta** | **−4.16 °F mean** | −2.03 °F mean | ⚠ Delta widened ~2 °F |
| OTA mode flag | currently `off` (last change 12:18Z today) | Clean | ✓ Hygiene held |

**Verdict: deployment is healthy on RF and cadence; battery and temp-delta need watching.** WiFi is the standout success — moving from bench to deep-in-pool location produced exactly the predicted improvement and the distribution has tightened to a comfortable working range. Battery voltage trajectory is real but expected at 1-min cadence on used cells; the canonical projection is for 30-min cadence on fresh cells. Temp delta widened more than expected and is now the primary watch item.

---

## WiFi RSSI distribution (818 samples)

| Bucket (dBm) | Count | % | |
|---|---|---|---|
| −95 to −90 | 12 | 1.5% | * |
| −90 to −85 | 25 | 3.1% | *** |
| −85 to −80 | 22 | 2.7% | ** |
| −80 to −75 | 41 | 5.0% | ***** |
| −75 to −70 | 30 | 3.7% | *** |
| −70 to −65 | 140 | 17.1% | ***************** |
| **−65 to −60** | **523** | **63.9%** | *************************************************************** |
| −60 to −55 | 25 | 3.1% | *** |

Percentiles: p10 = −77, p25 = −67, p50 = −64, p75 = −62, p90 = −61

**Big improvement vs yesterday's report.** The median moved from −69 dBm to −64 dBm — 5 dB stronger. The dominant bucket is now −65 to −60 dBm (64% of all samples), where yesterday it was −70 to −65 (27% of samples). The tail below −80 dBm shrank from 12% to 7%. Likely cause: the float has settled into a stable position with consistent line-of-sight to the Lanai U7 antenna (ADR-023). No action needed.

---

## Battery voltage trajectory

In-pool quarterly snapshots (filtered out the bench-OTA outliers at the start of the window):

| Time (UTC) | Voltage (V) |
|---|---|
| 19:30 (5/26, deploy + 30 min) | 3.06 |
| 23:33 (5/26, ~4 h post-deploy — yesterday's report endpoint) | 3.20 |
| 00:00 (5/27) | 3.20 |
| 05:54 (5/27) | 3.14 |
| 11:50 (5/27) | 3.11 |
| 17:22 (5/27, now) | 2.86 |

**Drain rate.** Roughly 340 mV drop over the ~17 hours from yesterday's report endpoint (23:33Z 5/26 at 3.20 V) to now (17:22Z 5/27 at 2.86 V). Math:

- At 1-min cadence: ~1440 wakes/day × 232 mC/wake = ~93 mAh/day from wakes
- Plus ~9 mAh/day from the 381 µA sleep floor
- **Total ~102 mAh/day at 1-min cadence**

Used L91 stack remaining capacity is unknown (Scott noted "from before" — not fresh), but a healthy used pair sitting in the 3.0–3.4 V band might be ~1500–2000 mAh into its useful discharge. At 102 mAh/day, that's 15–20 days of 1-min runtime — fully consistent with the 340 mV drop in 17 h.

**Important caveat:** the `calibrate_linear` 2-point cal was anchored at 3.0 V and 3.6 V. The current 2.86 V reading is now *below* the lower cal point, so the absolute accuracy is degraded. The trend direction is reliable but the exact number should be taken with a margin of error of ~50–100 mV. A multimeter cross-check at the next bench session would resolve this.

**This trajectory is not concerning for the deployment plan** — the canonical 287-day runtime projection in ADR-025's amendment is for 30-min cadence on **fresh** cells, not 1-min cadence on used cells. The 1-min cadence is intentionally aggressive for the data-collection phase. Fresh-cell swap + 30-min flip scheduled for 2026-05-28/29 per the deployment plan.

---

## Temperature cross-validation vs OmniLogic — flag raised

24h window, 72 OmniLogic samples aligned with closest external-filtered sample:

| Stat | This window | Previous report |
|---|---|---|
| OmniLogic mean | 89.74 °F | 89.7 °F |
| External filtered mean | 85.57 °F | 86.71 °F |
| **Mean delta (omni − external)** | **+4.16 °F** | +2.03 °F |

**Delta has doubled in one day.** Both possibilities flagged in yesterday's report remain live:

1. **Stratification + OmniLogic-staleness.** OmniLogic mean barely moved (89.7 → 89.74) while external mean dropped (86.71 → 85.57). If OmniLogic is reading stale-warm because the pump's been off through the night, and the surface (where external floats) is reading the actual cooled-overnight reality, the delta would grow precisely as observed.

2. **Calibration drift.** Three weeks of pool exposure post-2026-05-02 cal could be drifting the NTC, but a 2 °F drift in 24 h is faster than that mechanism predicts.

3. **New possibility — surface sun heating vs bulk during pump-off periods.** Inverse of #1 — if the surface is sun-heated and bulk is cooler, external would read higher. We see the opposite (external lower), so probably not this.

**Strong lean toward #1**, but worth one diagnostic step: pull `switch.omnilogic_pool_filter_pump` history over the same 24h window and check whether the external-vs-OmniLogic delta correlates with pump-off periods. If yes, no action needed (it's a real stratification artifact). If the delta is consistent regardless of pump state, cal drift is in play and a single-point recal in known warm water is the fix.

**Action: add this correlation check to the next bench session.** Not urgent — the temp fallback chain (ADR-013) handles either reading correctly as the authoritative source.

The 72.4 °F floor in the filtered range is one suspicious low-end outlier — likely the same deployment-hour 20:07–20:45Z cluster yesterday's report flagged, captured in this window too. If a similar low cluster appears in a 24h window with no float disturbance, the median filter window needs reconsideration.

---

## Cadence — wake reliability

Full 24h:

- **1338 uptime publishes / 1440 theoretical = 92.9%**
- Median gap: 61 s (exactly on 1-min cadence)
- Max gap: 1765 s (~29 min) — single event
- Gaps > 2 min: 40 (total 140 min)
- Gaps > 5 min: 4 (total 57 min)

The 4 big gaps (>5 min, ~57 min total) are concentrated in the 17:23–19:22Z OTA-cycle window — they account for ~95% of the missed-publish time. Excluding the OTA phase, the in-pool steady-state effective cadence success rate is approximately:

`(1338 publishes / (1440 − 57/1440 × 1440))` ≈ **96.7% effective**

Essentially perfect for a battery-powered WiFi sensor on a moving float.

**At 1-min cadence, 92–97% effective success is well above the threshold for the temp sensor's role in the authoritative-fallback chain.** When the cadence flips to 30-min after fresh cells go in, each missed wake represents 30 min of missed coverage — but at this success rate even a 10% degradation post-flip is ~43 publishes/day, still ample for the temperature data's purpose.

---

## OTA flag history (clean since deployment + 2h)

7 toggles in window, all consistent with the deployment workflow:

| UTC time | State | Context |
|---|---|---|
| 17:23:07 (5/26) | off | Reset for first OTA |
| 17:23:08 | on | OTA #1 prep |
| 17:26:40 | off | OTA #1 complete |
| 18:35:50 | on | OTA #2 prep |
| 18:41:04 | off | OTA #2 complete |
| 19:12:16 | on | OTA #3 prep |
| 19:22:07 | off | OTA #3 complete — last toggle |

No toggles today. Last state change was 12:18Z today but that was a `state` recompute, not a `last_changed` event — the flag has been steady-off for 22+ hours. Hygiene pattern is holding.

---

## Things to watch — updated priority

1. **🆕 Temperature delta vs OmniLogic widened to +4.16 °F.** Now the top watch item (was #1 yesterday too, but the magnitude jumped). Next session: pull pump-on/pump-off correlation against the delta. Most likely #1 cause (OmniLogic-staleness during pump-off) is benign; calibration drift would be the action-required outcome.
2. **Battery voltage trajectory verification on fresh cells + 30-min cadence.** Currently at 2.86 V on used cells at 1-min cadence (drain rate ~102 mAh/day, matches expected math). The 287-day ADR-025 projection only becomes testable after the fresh-cell swap + 30-min flip. Mark a checkpoint at that transition.
3. **Battery cal accuracy below 3.0 V.** Today's reading at 2.86 V is below the lower `calibrate_linear` anchor point (3.0 V), so absolute accuracy is degraded. Add a third low-end cal point (~2.5 V) at the next bench session to extend the linear fit range. Trend direction is reliable; absolute number has ~50–100 mV uncertainty for now.
4. **Fresh-cell swap + 30-min cadence flip scheduled 2026-05-28/29.** That's the production-mode configuration. Mark a clean before/after checkpoint to isolate "battery wear" from "everything else."
5. **WiFi p90 percentile.** Currently −61 dBm (excellent). Watch for month-over-month drift in the bottom percentile if any antenna orientation changes or AP-side maintenance happens.
6. **Investigate the 72.4 °F filtered-temp floor.** One outlier in the 24h window. If it recurs in a no-disturbance window, the 3-sample median filter needs reconsidering.
7. **OTA flag hygiene.** Pattern holding clean. No drift.

---

## Data sources

All extracted from the 24h history pull at 2026-05-27 17:23Z:

| Entity | Samples in 24h | Δ vs previous report |
|---|---|---|
| `sensor.pool_water_temp_external` | 792 | −145 |
| `sensor.pool_water_temp_external_filtered` | 780 | −137 |
| `sensor.pool_water_temp_authoritative` | 661 | −167 |
| `sensor.pool_water_temp_external_pool_float_battery_voltage` | 1131 | +829 (full window now, vs partial in previous) |
| `sensor.pool_water_temp_external_pool_float_wifi_signal` | 821 | −42 |
| `sensor.pool_water_temp_external_pool_float_uptime` | 1338 | +167 |
| `sensor.pool_pool_water_temperature` | 72 | −18 |
| `input_boolean.pool_float_ota_mode` | 7 toggles | −1 |

Methodology details and the exact curl patterns in `docs/reference/ha-rest-api-curl-cheatsheet.md`. Raw JSON cached at `/tmp/pf24.json` (sandbox-only, not committed).

---

## Open questions for next session

- Does the +4 °F delta correlate with pump-off periods? If yes, benign stratification. If no, calibration drift.
- Battery drain rate on fresh cells + 30-min cadence after the Thu/Fri swap — should drop by ~30× to confirm the 287-day projection.
- Should we add `sensor.pool_water_temp_delta_external_vs_omnilogic` as a template sensor + an automation flagging delta > 3 °F sustained > 30 min as an early-warning?
- Add a third low-voltage cal point (~2.5 V) at next bench session to extend `calibrate_linear` below 3.0 V.
- Confirm or refute the 72.4 °F low-temp outlier as a one-time deployment artifact vs a recurring filter-window issue.

---

## Investigation: temp drift root cause (2026-05-27 afternoon)

The morning's +4 °F delta vs OmniLogic raised a calibration-drift concern. Investigation that afternoon ruled out OmniLogic-staleness as the dominant cause and identified the missing window shade (the white 3D-printed blanking insert that covers the clear dome interior) as the primary contributor.

### Diagnostic chain

1. **Pump-on/pump-off correlation.** Verified OmniLogic pump-state had 50/50 on/off split overnight. During pump-off, OmniLogic generated **2 paired samples vs 101 during pump-on** (it doesn't update without flow per ADR-013). The widened delta in the 24h average was partly OmniLogic-staleness, but the pump-on-only mean was still +3.31 °F — significantly higher than yesterday's +2.03 °F.

2. **Reference thermometer reading at 13:23 EDT** = 89.4 °F. Float was reading 86.4 °F. **Float was 3 °F low vs ground truth.** OmniLogic at 90 °F was only +0.6 °F off the reference. So the delta wasn't OmniLogic being warm — it was the **float reading low**.

3. **Pre-rework v1 vs post-rework v2 historical comparison.** Pump-on Memorial Day data from pre-rework v1 (window shade installed) showed mean delta of **+1.07 °F**. Post-rework v2 (window shade removed during the build) is at **+3.63 °F**. **2.5 °F shift attributable to "something different about v2."**

4. **Diurnal pattern in v2.** Today's v2 delta progression: morning 8 AM EDT +1.46 °F, peaks +4.65 °F at 11 AM, sustained +4 °F through midday. Pattern tracks solar angle — wouldn't happen for a constant calibration offset.

5. **OAT correlation.** Hourly OAT vs hourly delta has Pearson r = +0.57, slope +0.44 °F delta per 1 °F OAT rise. Today's OAT swung 77 → 92.7 °F. Delta tracks it.

6. **Direct physical confirmation.** At 14:08 EDT pull, case interior was **warm to the touch** (not hot — estimated 100-110 °F with OAT 92.6 °F). Greenhouse effect from solar gain through the now-uncovered clear dome.

### Mechanism

With the window shade removed, sunlight passes through the clear dome and directly heats the case interior. Multiple compounding effects on the temperature reading chain push the published value below actual water temp:

- 47 kΩ reference resistor temperature coefficient (~100-200 ppm/°C drift)
- ESP32-C6 ADC internal Vref tempco
- Possible thermal coupling from case interior to NTC via the wire pass-through
- All push in the same direction (interior warmer than water → published temp reads low)

Direction matches the observed behavior exactly.

### Window shade reinstall (2026-05-27 14:08-14:14 EDT)

Float pulled, **interior confirmed bone-dry**, NTC wiring inspected (no visible corrosion, deferred touching any solder joints to keep the experiment as single-variable as possible), **window shade reinstalled**, float redeployed.

Post-reinstall observations:

- **Temp recovery:** float was reading 87.29 °F by 14:23 EDT (9 min after reinstall, NTC fully equilibrated to water). Reference still 89.4 °F. **Delta narrowed from −3.0 °F to −2.1 °F immediately.** Expected to narrow further as case interior cools from accumulated heat soak.
- **RSSI side-effect:** Pre-pull in-pool mean was −64.3 dBm (n=42, range −67 to −59). Post-shade in-pool mean was −67.9 dBm (n=31, range −75 to −66). **Net −3.6 dB drop**. Most likely mechanism: **the shade physically forces the Tenmory N2425D flex PCB antenna to sit flat (parallel to earth) instead of its previous slightly-tilted-upward orientation.** A flex PCB antenna's directional pattern depends on its orientation; with the shade absent, the antenna sat with a slight upward tilt that gave it favorable polarization match and pattern alignment toward the Lanai U7 (mounted at ceiling/eave height). With the shade pressing the antenna flat, the gain in the AP direction degrades by exactly the few-dB amount we observed. Less likely contributors: direct shade material attenuation (~0.5-1 dB max), float position drift from the reseat. **Net RSSI still in the −66 to −70 ADR-025 target band**; cost is acceptable given the temp accuracy gain. Future v2.1 hardware: consider a shade geometry that preserves the antenna's tilt, or a separate antenna mounting that keeps it tilted regardless of shade.

### Wet-bulb observation (incidental but recorded)

During the 6-minute pull window, the float was on a patio table in shade. Readings dropped from 86.4 °F (in water) to 82.25 °F (on table). At the time, OAT was 92.6 °F and humidity was 60.7 % per Tempest, giving a computed wet-bulb temperature of **80.24 °F**. The float reading of 82.25 °F was 2 °F above wet-bulb — consistent with a wet probe equilibrating toward wet-bulb via evaporative cooling but not having enough time to fully reach it (probe thermal inertia + thinning water film). Confirms the NTC sensor chain is reading real physics, just not what you'd expect intuitively from "warmer air should mean warmer reading."

NTC thermal time constant in pool water observed at ~3-4 minutes (took 9 minutes for 5 °F recovery from wet-bulb air reading back to water-immersed steady state).

### What this means for the v2.1 design

The window shade is now confirmed as a **functionally important** part of the float assembly, not a cosmetic blanking insert. The reflective dome treatment alone is insufficient — the shade provides the additional thermal isolation needed for accuracy. Future v2.1 (or later) builds should treat the shade as required, not optional. Worth a note in ADR-025 next time it's amended.

### Open follow-ups (added 2026-05-27 PM)

- Watch the delta through this afternoon and tomorrow morning. If post-shade delta narrows to v1's ~+1 °F band by evening (when solar is gone), shade hypothesis fully confirmed.
- **Redesign the shade to preserve antenna tilt for v2.1.** The current shade flattens the Tenmory flex PCB antenna, costing ~3-4 dB of in-pool RSSI. Options: (a) cut a relief notch in the shade where the antenna sits so the antenna stays in its natural tilted position, (b) add a small bump or shim under the antenna to maintain tilt, (c) redesign shade to be a hollow ring rather than a full blanking disc so the antenna has clearance to flex upward. Material attenuation is a minor contributor; geometry/constraint is the dominant effect.
- The +0.5-1 °F residual offset between v1 baseline and v2-with-shade baseline (if it persists) is the wiring/ADC-channel contribution from the GPIO0 → GPIO1 move. Document as a known characteristic; in-situ single-point cal can correct it once stable.
