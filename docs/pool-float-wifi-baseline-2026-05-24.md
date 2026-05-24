# Pool Float WiFi Baseline — 2026-05-24

Snapshot of post-tuning WiFi reliability data for the pool water temp float,
captured the morning after applying static IP + max TX power + extended wait
budget + on_boot race fix (per ADR-015 / pool-water-temp-external.yaml).

## Sample window

- Start: 2026-05-23 16:26:30 EDT
- End:   2026-05-24 12:48:22 EDT
- Duration: ~20.4 hours
- Cadence target: 10-min (6 wakes/hour, 144/day)

## Confounding event

Pool float was pinned under a ladder rung and submerged from
**~23:00 EDT 2026-05-23 until ~09:30 EDT 2026-05-24** (~10.5 hours).
Submerged data is not representative of normal operation — 2.4 GHz
attenuation in water at this frequency is roughly 1 dB/mm.

## Long gaps (>14 min)

```
05-23 17:05 -> 05-23 17:25 EDT  gap=19min
05-23 19:35 -> 05-23 19:55 EDT  gap=19min
05-23 20:05 -> 05-23 20:25 EDT  gap=20min
05-23 22:53 -> 05-23 23:22 EDT  gap=29min
05-23 23:22 -> 05-23 23:43 EDT  gap=20min   # submerged begins ~23:00
05-23 23:43 -> 05-24 00:03 EDT  gap=19min
05-24 00:27 -> 05-24 00:47 EDT  gap=20min
05-24 03:07 -> 05-24 03:27 EDT  gap=20min
05-24 03:57 -> 05-24 04:17 EDT  gap=19min
05-24 04:17 -> 05-24 04:37 EDT  gap=20min
05-24 04:47 -> 05-24 05:07 EDT  gap=19min
05-24 06:37 -> 05-24 06:57 EDT  gap=20min
05-24 07:47 -> 05-24 08:17 EDT  gap=29min
05-24 09:37 -> 05-24 09:57 EDT  gap=20min   # submerged ends ~09:30
05-24 09:57 -> 05-24 10:18 EDT  gap=20min
05-24 10:28 -> 05-24 10:58 EDT  gap=30min
```

## Counts

| Source | Count | Window |
|---|---|---|
| HA `sensor.pool_water_temp_external` state changes | 103 | 20.4h |
| HA `sensor.pool_water_temp_external_pool_float_wifi_signal` | 87 | 20.4h |
| HA `sensor.pool_water_temp_external_pool_float_uptime` | 70 | 20.4h |
| UniFi client-connected events | 88 | ~23.5h |

UniFi count is the authoritative "wake succeeded" signal. HA state-change
counts overstate because each wake fires both "unavailable → value" and
"value → new value" transitions.

## Success-rate estimates

| Slice | Hours | Misses observed | Estimated success |
|---|---|---|---|
| Floating pre-submersion (16:26–23:00 EDT 05-23) | 6.6 | 3 single + 1 straddle | ~89% |
| Submerged (23:00 EDT 05-23 → 09:30 EDT 05-24) | 10.5 | 11 events | ~50% |
| Floating post-submersion (09:30–12:38 EDT 05-24) | 3.1 | 1 single + 1 double | ~84% |
| Full window (mixed) | 20.4 | 16 events / ~19 missed wakes | ~62% (UniFi-based) |

Pre-tuning UniFi baseline for comparison: 97 events in 23.8h = 4.08/h = 68%.

## Tuning timeline reference

Race-fix flash + OTA-flag-OFF completed approximately 00:10 EDT 2026-05-24.
Submersion overlapped roughly the first 9 hours of post-flash operation, so
the post-flash floating-freely sample is only ~3.1 hours so far.

## Next step

Re-query 2026-05-25 ~12:30 EDT with a fresh 24h window, assuming float
remains at surface. Use the same query pattern (`START` = now-86400s,
`sensor.pool_water_temp_external` history). Target: clean 24h sample to
isolate physical-RF performance from submersion contamination.

Pending decision: external antenna (XIAO ESP32-C6 supports IPEX/U.FL
external antenna connector; no suitable part identified yet — needs
selection criteria: form factor, where antenna mounts to stay above
waterline, pigtail length, weatherproofing).
