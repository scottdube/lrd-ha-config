# ADR-031: External water-temp freshness keys off `last_reported`, not `last_changed`

**Status:** Accepted
**Date:** 2026-06-12
**Decider:** Scott
**Related:** ADR-015 (external water-temp probe + cascading fallback), ADR-025 (pool float v2 hardware), ADR-030 (alerting posture — this fixes a false-positive in the "unexpected happened" bucket), `pool/scripts/state_logger.py`, `pool/scripts/audit_recent.py`.

---

## Context

The lanai pool float (`pool-water-temp-external`, XIAO ESP32-C6, ESPHome deep-sleep, 40 s wake / 30 min sleep) was generating a daily "external water temp probe — poor connectivity" alert. The UniFi client log appeared to corroborate it: connect events at irregular multiples of 30 min rather than a clean every-30-min cadence, which read as a flaky probe.

Direct inspection of HA state history shows the opposite. Over a continuous 15+ hour window the probe's `uptime` diagnostic — which changes every boot and therefore cannot be deduplicated — recorded on **32 of 32 wakes**, each spaced 29.7 min, with zero misses. WiFi RSSI held −49 to −70 dBm (1 of 49 samples at/below −70) and battery sat at 3.7–4.2 V. The device is connecting and reporting on schedule every cycle. The UniFi log simply under-records: with a static IP (`192.168.11.111`) and a hard-locked BSSID + `fast_connect`, the sub-2-second reconnects frequently don't emit a fresh "client connected" syslog entry. UniFi under-counting is a logging artifact, not a connectivity fault.

The real defect is in the freshness metric. `state_logger.py` computed `external_water_temp_fresh` / `external_water_temp_age_min` from the temp sensor's **`last_changed`** (age ≤ `FRESHNESS_THRESHOLD_MIN` = 35 min). `last_changed` advances only on a **value transition**. The temp sensor runs a median-of-3 filter and reports to 0.1 °F; when pool temp is stable, consecutive 30-min samples land on an identical published value, so HA records no change and `last_changed` stalls for 60–120 min even though the probe reported on time. Over the same wake set, the temp value produced a new record on only **17 of 32 wakes** — versus uptime's 32/32. Simulating the exact metric over one overnight window yields ~55% fresh, well under `audit_recent.py`'s 80% floor (`EXTERNAL_FRESH_RATIO_MIN`), which fires the alert. The metric was measuring value churn, not whether the probe reported.

The original code carried the assumption inline: *"every wake produces a different value in practice, so last_changed ≈ last_updated."* That assumption is false against the median filter + rounding, and the comment even named the remedy ("switch to last_updated"). Empirically `last_updated` is also insufficient — HA pins `last_updated` to `last_changed` on an unchanged-value report. Only **`last_reported`** (HA 2024.8+; live system is on 2026.4.4) advances on every state report regardless of value, which I confirmed on the live state object (`last_reported` 54 ms ahead of a pinned `last_changed`/`last_updated`).

## Decision

Base external-probe freshness and age on **`last_reported`**, the timestamp that advances on every state report. Added a dedicated `fetch_last_reported()` helper (a one-shot `/api/states` read that returns `last_reported`) rather than widening `fetch_entity`'s 4-tuple, to avoid churning ~15 existing unpack sites; the external probe is the only consumer that needs report-level freshness. `build_row` fetches it once per row and shares it across the `age_min`, `fresh`, and `water_temp_authoritative` columns. `compute_external_water_temp_fresh` / `compute_external_water_temp_age_min` take the reported timestamp; their parameters and docstrings were renamed accordingly.

`FRESHNESS_THRESHOLD_MIN` stays at 35 min — it was always correct (30 min cadence + 5 min grace); it was being fed the wrong clock. `pump/waterfall/heater` `*_last_changed` columns and `compute_water_temp_reliable` are unchanged — they legitimately want transition timing, not report timing.

## Consequences

### Positive
- The daily false-positive connectivity alert stops without weakening the threshold or masking a real fault.
- `external_water_temp_fresh` now reflects reality (~100% on a healthy probe), so the `water_temp_authoritative` cascade (ADR-015) trusts the external reading instead of falling back to the local sensor on stable-temp nights.
- Establishes the correct field for "did a device report" across future report-vs-change freshness checks.

### Negative / costs (accepted)
- One extra `/api/states` GET per logger row (every 10 min, single entity) — negligible.
- A *genuine* probe outage now surfaces only after 35 min of true silence (`last_reported` truly stops advancing). That is the intended semantic and remains well inside the alerting deadlines; the heartbeat posture of ADR-030 still applies.

## Verification
- `python3 -m py_compile pool/scripts/state_logger.py` passes; no remaining `ext_last_changed` references.
- Re-run `audit_recent.py --print-clean` against a fresh post-deploy CSV window and confirm the external-freshness check passes (expected ratio ~100%).

## Sources
- HA state history, wake-by-wake alignment (uptime 32/32 vs temp 17/32, same wakes), live `last_reported` vs `last_changed` on `sensor.pool_water_temp_external` — pulled from `192.168.50.11:8123` REST API, 2026-06-12.
- ESPHome design: `esphome/pool-water-temp-external.yaml` (deep_sleep 40 s/30 min, median-of-3 filter, 0.1 °F rounding, static IP + locked BSSID + fast_connect).
- Metric defect: `pool/scripts/state_logger.py` (`compute_external_water_temp_*`, `FRESHNESS_THRESHOLD_MIN`); alert: `pool/scripts/audit_recent.py` check #3 (`EXTERNAL_FRESH_RATIO_MIN`).
