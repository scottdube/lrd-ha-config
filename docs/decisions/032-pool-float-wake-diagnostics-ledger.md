# ADR-032: Pool float wake-outcome diagnostics ledger (store-and-forward miss reasons)

**Status:** Accepted — **Phase 1 only** (failed-connection diagnostics). Value backfill / back-dated rows (Phase 2) decided **out of scope** 2026-06-14. **Implemented 2026-06-14** in `esphome/pool-water-temp-external.yaml` + `state_logger.py` (`SCHEMA_VERSION` → `2.0-phase2.2`); **not yet flashed (OTA pending) or deployed.**
**Date:** 2026-06-14
**Decider:** Scott
**Related:** ADR-015 (external probe + cascading fallback), ADR-025 (float v2 hardware / regulator bypass / battery math), ADR-031 (freshness via uptime heartbeat; the ~4% real-miss finding this ADR investigates). Touches `esphome/pool-water-temp-external.yaml` and `pool/scripts/state_logger.py`.

---

## Context

After ADR-031 the freshness metric is honest, and it surfaces a residual: the float genuinely misses ~4% of wakes (5 / 54 h). The probe connects with strong RSSI but irregularly, so the leading hypothesis is WiFi/API association occasionally blowing the 35 s connect budget — but we have **no per-wake evidence** of *why* any given wake failed, and we explicitly ruled battery depletion unlikely (ADR-025 math) without being able to rule out transient brownout.

Goal: give each wake a recorded outcome and, for failures, a reason — delivered into the state-log CSV ("the spreadsheet") even though the failing wake had no connection at the time. This is store-and-forward: the device detects and records the outcome locally, retains it across deep sleep, and forwards it on the next successful connect.

### Hard constraints discovered

1. **No native backdating in HA.** ESPHome publishes a single current value; HA stamps it with receipt time. A buffered reading delivered late lands at delivery time, not measurement time. Late data must therefore carry its own **age** and be reassembled HA-side. The device has no wall clock across sleep, so age (from the RTC millis counter, which survives deep sleep but not power loss) is the reliable currency; absolute time is reconstructed on ingest as `now − age`.
2. **`esp_reset_reason()` is unreliable for brownout.** Known ESP-IDF behavior: after a brownout the reset reason is often reported as `ESP_RST_WDT`, not `ESP_RST_BROWNOUT` (the brownout message prints to console but the programmatic code is overwritten by the watchdog reset path). So brownout detection cannot depend on reset reason alone.
3. **`restore_value` globals on ESP32 use NVS (flash), survive deep sleep and power loss**, coalesced by `flash_write_interval` (default 60 s) and flushed on `deep_sleep.enter`. There is a historical reliability caveat (esphome/issues#4265) — must be verified on-device before trusting.

## Decision (design)

Add a local **wake-outcome ledger** to the float firmware and matching ingest to `state_logger.py`. Two robust signals, combined into a small reason taxonomy, with a store-and-forward buffer for failed wakes.

### Two independent signals

- **`connected?`** — evaluated at the end of the wake script via `api.is_connected`. Distinguishes a successful publish from an association/API failure. Sub-split with `wifi.connected` to separate "never associated" from "associated but API never came up."
- **`clean_sleep?`** — a `restore_value` global flag set to **true only immediately before `deep_sleep.enter`**, and read at the *next* boot **before** being reset to false. If the next boot sees it still false, the previous cycle did **not** reach a planned sleep → it browned out, crashed, or was externally reset. This is the reset-reason-independent brownout/crash detector that works around constraint #2. `esp_reset_reason()` and `battery_at_wake` are captured as *corroborating* secondary signals, not the primary.

### Reason taxonomy (per wake)

| Code | Meaning | Signals |
|---|---|---|
| `OK` | Connected, published, clean sleep | connected=Y, clean_sleep=Y |
| `API_TIMEOUT` | WiFi associated, `api.connected` not reached in budget; slept cleanly; reading buffered | connected=N, wifi=Y, clean_sleep=Y |
| `WIFI_NO_ASSOC` | WiFi never associated in budget; slept cleanly; reading buffered | connected=N, wifi=N, clean_sleep=Y |
| `UNCLEAN` | Previous cycle never reached clean sleep (brownout/crash/reset) | clean_sleep=N at next boot (+ reset_reason, batt corroboration) |

This taxonomy maps directly onto the open question: a ledger dominated by `API_TIMEOUT`/`WIFI_NO_ASSOC` confirms the WiFi-association hypothesis; a ledger with meaningful `UNCLEAN` confirms brownout. Either way it settles it with data.

### Firmware additions (`esphome/pool-water-temp-external.yaml`) — IMPLEMENTED 2026-06-14 (not yet flashed)

Realized with **per-reason counters** rather than a JSON string buffer — simpler, NVS-robust (no `std::string` restore caveat), and sufficient for Phase 1 since we only need counts-by-reason since the last success, not a per-miss record.

- `globals` (all `restore_value: yes`, NVS-backed): `g_clean_sleep` (bool planned-sleep flag), `g_boot_count` (int wake counter), `g_connect_fail_count`, `g_wifi_noassoc_count`, `g_unclean_count` (since-last-success counters), `g_last_reset_reason` (int, `esp_reset_reason()`).
- `on_boot` priority 200 (after the GPIO antenna lambda at 800, before the wake script at -100): if `g_clean_sleep` is false → `g_unclean_count++` (previous wake never reached planned sleep); set `g_clean_sleep=false`; `g_boot_count++`; capture `esp_reset_reason()`.
- Wake script (`take_reading_and_sleep`): after `wait_until: api.connected`, branch on `api.connected`:
  - **connected:** publish temp/uptime/wifi + the ledger sensors, then zero `g_connect_fail_count` / `g_wifi_noassoc_count` / `g_unclean_count`.
  - **not connected:** `g_connect_fail_count++`; if `wifi` is also down, `g_wifi_noassoc_count++` (WIFI_NO_ASSOC vs API_TIMEOUT split).
  - Immediately before `deep_sleep.enter`: set `g_clean_sleep=true` (preferences flush on sleep).
- New entities (published only on a connected wake; HA-composed ids prefixed `sensor.pool_water_temp_external_pool_float_*`):
  - `..._boot_count` — monotonic wake counter.
  - `..._connect_ms` — boot-to-connect time this wake (budget-pressure signal; `millis()` at publish).
  - `..._fails_since_last`, `..._wifi_noassoc_since_last`, `..._unclean_since_last` — the counters.
  - `..._wake_diag` (text_sensor) — compact human-readable summary string `ok boot=N fails=N noassoc=N unclean=N connms=N reset=N`.

**Compile caveats (verify with the ESPHome toolchain before OTA):** `esp_reset_reason()` resolves under esp-idf without an explicit include in practice but confirm at build; and bench-confirm `restore_value` globals actually survive deep sleep on this C6 (esphome/issues#4265) before trusting the `UNCLEAN` signal.

### HA-side / spreadsheet additions (`state_logger.py`)

Phase 1 (the agreed scope) — IMPLEMENTED 2026-06-14 in `state_logger.py`:
- Seven new columns: `external_probe_boot_count`, `external_probe_connect_ms`, `external_probe_fails_since_last`, `external_probe_wifi_noassoc_since_last`, `external_probe_unclean_since_last`, `external_probe_wake_diag` (all `state`), and computed `external_probe_missed_since_last` = `fails_since_last + unclean_since_last` (a pure within-row sum — no prev-row state needed, so the logger stays stateless).
- The firmware's since-last-success counters mean the miss count is read directly off each fresh row; `boot_count` is the monotonic cross-check.
- Adding columns bumps the CSV schema → `state_logger.py`'s existing `maybe_rotate_csv` rotates to a fresh file; the auditors read columns by name so the additions are backward-compatible.

Phase 2 — **out of scope (decided 2026-06-14).** Back-dating the actual missed temperature readings into the CSV (`timestamp = now − age_s`) is not worth the time-attribution complexity for the marginal value (sub-degree drift over a single missed 30-min slot, and the cascade already falls back cleanly). Knowing the failed-connection reason — Phase 1 — is the value. Revisit only if gap-free temp history later proves necessary.

### Deployment
All over-the-air via the existing `input_boolean.pool_float_ota_mode` flag — no float retrieval. (Confirm the flag-clear step in the ADR-025 OTA checklist.)

## Consequences

### Positive
- Per-wake reason ledger settles brownout-vs-association with evidence instead of inference.
- Miss visibility becomes quantitative (`boot_count` diff) even before any JSON parsing.
- Store-and-forward means a failed wake is no longer invisible — its reason arrives at the next success.

### Negative / costs (accepted)
- Firmware complexity (globals, flag discipline, JSON buffer) on a sealed, in-pool device — reflash risk is OTA-only but still nonzero.
- Energy: negligible. A failed wake already burns the full 40 s `run_duration`; diagnostics add compute only. Extra NVS writes (~1–2/wake) are well within ESP32 wear-leveling at 48 wakes/day.
- The back-dated-row injection (Phase 2) is genuinely fiddly and is deliberately deferred and isolated.

### Caveats to verify at implementation
- `restore_value` actually surviving deep sleep on this C6 (issue #4265) — bench-verify before relying on it.
- `esp_reset_reason()` brownout misreport — corroborate `UNCLEAN` with `battery_at_wake`, don't trust the reset code alone.
- `battery_at_wake` is the trend-only ADC (ADR-025) — fine for correlation, not absolute.
- `text_sensor` diag only ships on connected wakes; if the float never reconnects, the ledger sits in NVS until it does (acceptable; recoverable over OTA).

## Resolved decisions (2026-06-14)
1. **Phase 1 only.** Failed-connection diagnostics are the value; value backfill (Phase 2) is out of scope.
2. **Age-only, no SNTP.** No `time:` component — `age_s` stays informational; no absolute-time reconstruction needed without backfill.
3. **Buffer depth 8 records** (≈ 4 h of total outage) — sufficient for the expected ~4% miss rate; revisit only if a longer disconnection is observed.

## Verification (when built)
- Bench: force association failure (wrong BSSID / AP off), confirm a buffered `WIFI_NO_ASSOC`/`API_TIMEOUT` record appears in `wake_diag` on the next good connect with a sane `age_s`.
- Bench: induce a brownout (sag supply during TX), confirm next boot logs `UNCLEAN`.
- Field: `external_probe_missed_since_last` over a week vs the ADR-031 uptime-gap count — the two miss counts must agree.

## Sources
- ADR-031 miss finding + uptime ground truth; ADR-025 battery math + ADC cal caveat.
- ESPHome globals / preferences / deep-sleep persistence: [Global Variables](https://esphome.io/components/globals/), [ESPHome Core Configuration (flash_write_interval)](https://esphome.io/components/esphome/), [Time, Preferences, and Deep Sleep](https://deepwiki.com/esphome/esphome/9.3-time-preferences-and-deep-sleep), restore_value ESP32 caveat [esphome/issues#4265](https://github.com/esphome/issues/issues/4265).
- `esp_reset_reason()` brownout misreport: [espressif/esp-idf#10834](https://github.com/espressif/esp-idf/issues/10834).
