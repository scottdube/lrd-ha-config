# ADR-031: External water-temp freshness keys off the uptime heartbeat

**Status:** Accepted (supersedes the `last_reported` approach first recorded here on 2026-06-12; corrected 2026-06-14)
**Date:** 2026-06-12, corrected 2026-06-14
**Decider:** Scott
**Related:** ADR-015 (external water-temp probe + cascading fallback), ADR-025 (pool float v2 hardware), ADR-030 (alerting posture — this fixes a false-positive in the "unexpected happened" bucket), `pool/scripts/state_logger.py`, `pool/scripts/audit_recent.py`.

---

## Context

The lanai pool float (`pool-water-temp-external`, XIAO ESP32-C6, ESPHome deep-sleep, 40 s wake / 30 min sleep) generated a daily "external water temp probe — poor connectivity" alert (`audit_recent.py` check #3: external fresh ratio < 80% over a rolling 3 h window).

The probe itself is healthy on connectivity: the `uptime` diagnostic — seconds-since-boot, effectively unique every boot, so it cannot be deduplicated — records on **every wake** (117/117 over a 54 h window), spaced 29.7 min. The fault was in the freshness metric, not the device.

`state_logger.py` computed `external_water_temp_fresh` / `external_water_temp_age_min` from the temp sensor's **`last_changed`** (age ≤ `FRESHNESS_THRESHOLD_MIN` = 35 min). `last_changed` advances only on a **value transition**. The temp sensor runs a median-of-3 filter and reports to 0.1 °F; when pool temp is stable, consecutive 30-min samples produce an identical published value, so `last_changed` stalls 60–120 min even though the probe reported on schedule. Result: the fresh ratio collapsed (observed as low as 28%, 5/18 rows) and fired the alert. The metric was measuring value churn, not whether the probe reported.

### First attempt (2026-06-12) and why it failed

The initial fix re-keyed freshness onto **`last_reported`**, on the documented HA semantics that `last_reported` advances on every state report including unchanged ones (HA 2024.8+; live system 2026.4.4). This was deployed (commit `e2f2826`) and **did not work** — the audit still read 28%.

Empirical check on 2026-06-14 (live `/api/states` reads on the float's diagnostic entities right after a wake): the `wifi_signal` sensor had reported on the most recent wake (uptime and battery both showed `last_reported` ≈ 1.2 min) yet its own `last_reported` was stuck at 30.9 min — **identical to its `last_changed`**. So on this HA + ESPHome native-API path, an unchanged re-report advances **neither `last_changed` nor `last_reported`**. The assumption behind the first fix was false for this device, and it should have been verified empirically before shipping rather than trusting the documented behavior. (Likely mechanism: the ESPHome path does not surface a state write to HA's state machine when the value is unchanged, so there is nothing to bump `last_reported`. Not investigated further — the heartbeat approach sidesteps it entirely.)

## Decision

Key external-probe freshness and age off the **uptime heartbeat** — the `last_changed` of `sensor.pool_water_temp_external_pool_float_uptime` (`EXTERNAL_UPTIME_ENTITY`). Uptime's value is unique every boot, so its `last_changed` advances on every wake (directly observed, 117/117 wakes, zero dedup). Since the temp reading is published on the same wake as uptime, "uptime advanced within 35 min" is an exact proxy for "the external temp reading is current."

`build_row` fetches the uptime entity once and shares its `last_changed` across the `age_min`, `fresh`, and `water_temp_authoritative` columns. The temp **value** still comes from the temp entity. `FRESHNESS_THRESHOLD_MIN` stays at 35 min — it was always correct; it was being fed a clock that stalls. The `fetch_last_reported()` helper added in the first attempt is removed. The pump/waterfall/heater `*_last_changed` columns and `compute_water_temp_reliable` are unchanged — they legitimately want transition timing.

## Consequences

### Positive
- The daily false-positive connectivity alert stops, without weakening the 80% threshold or masking a real fault — uptime stalls only on a genuinely missed wake.
- `external_water_temp_fresh` reflects reality (~99–100% on a healthy probe, simulated from real wake times), so the `water_temp_authoritative` cascade (ADR-015) trusts the external reading on stable-temp nights instead of needlessly falling back.
- Establishes the correct pattern for deep-sleep ESPHome freshness: track a monotonic/unique per-wake heartbeat, never a measured value whose repeats stall every HA timestamp.

### Negative / costs (accepted)
- Freshness now depends on the uptime entity existing and keeping a unique-per-boot value. If a future firmware pins uptime to a constant or removes it, freshness breaks silently — noted alongside the constant. A genuine probe outage surfaces after 35 min of no wake, the intended semantic.
- Residual real misses remain visible (see Follow-up): the metric is now honest, so true dropped wakes legitimately reduce freshness.

### Belt-and-suspenders (deferred to next float retrieval)
- Adding `force_update: true` to the ESPHome temp/wifi/battery sensors would make HA record every report even when unchanged, restoring `last_changed` as a valid freshness clock at the source. Deferred because the float is sealed and in the pool; fold it into the firmware update done when the float comes out for its battery swap (see Follow-up).

## Follow-up (separate from the metric fix)
Around 2026-06-12 the probe began genuinely missing the occasional wake (5 real misses / 54 h vs 0 earlier; ~4% miss rate). **This is NOT battery depletion** (an earlier draft of this ADR wrongly claimed it was — corrected 2026-06-14):

- Per ADR-025 the 2× L91 stack has a **287–643 day** design runtime at 30-min cadence; deployed 2026-05-26, so ~19 days in = <7% of design life.
- The `battery_voltage` telemetry is explicitly **trend-only** (ADR-025 cal amendment: published 3.11 V at a *known* 3.300 V, ~6% midrange bowing, fit only over 3.0–3.6 V, "not absolute precision"). The observed ~4.1 V "highs" are extrapolation artifacts above 2× L91's ~3.6 V ceiling; the low-3 V readings map to ~3.4 V actual = mid-plateau-normal (L91 sits at 3.0–3.4 V for most of life).
- The misses did **not** correlate with the low readings (they occurred at 3.46–3.70 V). The ADR-025 "voltage trap" is a sleep-current/runtime effect, not a brownout mechanism.

Most likely cause of the occasional miss: WiFi/API association intermittently exceeding the 35 s connect budget inside the 40 s `run_duration` on this BSSID-locked `fast_connect` deep-sleep wake — consistent with the original UniFi "strong RSSI but irregular connect" observation. Tracked in `docs/current-state.md` for monitoring; **no battery action indicated.**

**Suspicion, not a conclusion (noted 2026-06-14):** the OTA reflash that day pushed a full firmware image over WiFi in ~4 s, and the post-flash `connect_ms` was 3.4 s. This *hints* that link throughput and signal are fine once connected, so the misses may be cold-wake association latency rather than bandwidth or signal — and a clean ~4 s sustained-radio OTA *may* argue the supply holds under load (against brownout). These are working hypotheses only; the `fails` / `wifi_noassoc` / `unclean` distribution from the ADR-032 ledger is what should confirm or refute them. If it leans `API_TIMEOUT`/`WIFI_NO_ASSOC`, the levers to examine are association-side (the hard BSSID lock; AP band-steering / min-RSSI on the Lanai U7), not signal or power.

## Verification
- `python3 -m py_compile pool/scripts/state_logger.py` passes; no remaining `last_reported`/`fetch_last_reported` code references.
- Post-deploy: `external_water_temp_fresh` should read ~100% except across genuine missed wakes; confirm `audit_recent.py` external-freshness check passes.

## Sources
- Live `/api/states` reads of the float's uptime/wifi/battery/temp entities and 54 h of history from `192.168.50.11:8123`, 2026-06-14 (wifi `last_reported` == `last_changed` while reporting; uptime 117/117 wakes; battery trend).
- Failed first attempt deployed as commit `e2f2826`; audit message "External temp sensor fresh ratio 28% (5/18 rows)".
- ESPHome design: `esphome/pool-water-temp-external.yaml`. Metric + alert: `pool/scripts/state_logger.py`, `pool/scripts/audit_recent.py` check #3.
