# Pool Auditor — Spec

**Status:** Proposed (for Scott review before implementation)
**Depends on:** Logger v2 (`pool/docs/logger-v2.md`) — auditor consumes its CSV output.
**Related:** ADR-006 (auditor verifies the new pump-flow behavior).

---

## Purpose

A nightly script that scans the day's pool state log, asserts a catalog of expected behaviors, and notifies on failures. Catches drift between blueprint intent and actual equipment behavior without requiring Scott to manually scan a CSV.

The valve-stuck-open situation in late April was visible in the data for **four days** before being noticed. The auditor's existence reason is to make that span zero.

---

## Design principles

1. **Independent of the blueprint.** Auditor reads logger output, doesn't share runtime state with the automation. Catches blueprint bugs as well as equipment bugs.
2. **Tolerance, not equality.** Real systems have integration glitches and timing slop. Assertions take a tolerance window (e.g. waterfall closes within ±10 min of 20:00, not exactly at 20:00:00).
3. **PASS / FAIL with timestamps.** No qualitative output. Every assertion either passes or fails, and failures cite the specific row(s) that violated.
4. **Loud failures, silent success.** Mobile push only on FAIL (configurable: optional success summary on Sundays).
5. **Idempotent and offline-runnable.** Can be re-run against historical CSVs to validate fixes without waiting for a new day's data.

---

## Run model

- **Time-pattern automation** at 23:55 local time (or 00:05 the next morning, after midnight reset, TBD — both have edge cases).
- **Calls** `shell_command.pool_audit` → `python3 /config/pool/scripts/auditor.py --date YYYY-MM-DD`.
- **Reads** `/config/pool_state_log.csv` filtered to the requested date.
- **Optionally reads** `/config/pool_action_log.csv` for command-vs-observed reconciliation (Phase 4 of logger v2).
- **Writes** `pool/audit/pool_audit_YYYY-MM-DD.json` with full structured results.
- **Calls back** to HA via REST API or writes a `sensor.pool_audit_status` value via MQTT/file template — TBD which mechanism.
- **Notifies** via `notify.mobile_app_iphone_sd` on any FAIL.

CLI mode for offline use: `python3 auditor.py --date 2026-04-30 --no-notify` re-runs the audit without notifying. Useful for testing assertions against historical data.

---

## Assertion catalog

### Daily-shape assertions

| ID | Name | What it checks | Tolerance |
|---|---|---|---|
| **D1** | swim_day_consistency | `swimming_day` is the same value all day (it's computed from forecast_high which doesn't change mid-day). | All rows match. |
| **D2** | log_cadence | Time-pattern rows arrive every 10 min ±2 min. Gaps >12 min flagged. | <5% of intervals out of spec OK; >5% fail. |
| **D3** | sensor_availability | No sensor (`water_temp`, `oat`, `pump_state`, `waterfall_state`) is `unknown`/`unavailable` for >30 cumulative minutes. | 30 min cumulative threshold. |

### Pump-state assertions

| ID | Name | What it checks | Tolerance |
|---|---|---|---|
| **P1** | swim_day_pump_window | On swim days, pump on between `pump_should_start_minutes` and (waterfall_end OR heater_actively_delivering=False, whichever later). | ±10 min on transitions. |
| **P2** | nonswim_day_pump_off | On non-swim days, pump off ≥95% of the day. (Allow brief manual operation.) | <5% pump-on rows. |
| **P3** | pump_speed_when_heating | When `heater_actively_delivering=True`, `pump_speed` ≥ 75%. | All rows match (no mid-cycle drops). |
| **P4** | pump_speed_when_idle | When `heater_actively_delivering=False` AND pump on, `pump_speed` ≤ 60%. | After ADR-006 ships. Skip pre-v1.9.0. |
| **P5** | pump_command_landed | Each `pool_action_log` "pump on/off" command has a corresponding state change in `pool_state_log` within 5 min. | Phase 4 only. |

### Waterfall assertions

| ID | Name | What it checks | Tolerance |
|---|---|---|---|
| **W1** | waterfall_window_only | `waterfall_state=open` only between 08:00 and 20:00. Off-window opens flagged. | ±5 min on transitions. |
| **W2** | waterfall_opens_at_start | On swim days, waterfall transitions closed→open between 07:55 and 08:15. | 20-min window. |
| **W3** | waterfall_closes_at_end | On every day where waterfall was opened, transition open→closed between 19:55 and 20:15. **This is the assertion that would have caught the late-April bug.** | 20-min window. |
| **W4** | waterfall_command_landed | Each `pool_action_log` "valve open/close" has a state change within 2 min. | Phase 4 only. |

### Heater assertions

| ID | Name | What it checks | Tolerance |
|---|---|---|---|
| **H1** | heater_state_matches_swim_day | `heater_state=on` iff `swimming_day=True`. | Allow up to 1 transition mismatch in the first 10 min after midnight. |
| **H2** | heater_active_implies_pump_on | When `heater_actively_delivering=True`, pump must be on at heater speed. **This is a safety assertion.** | Zero violations allowed. |
| **H3** | water_temp_rising_when_heating | When `heater_actively_delivering=True`, water_temp delta over the next 60 min is ≥ +0.3°F. | Cross-checks the active-delivery signal — if False, the signal source itself is suspect. |

### Integration health assertions

| ID | Name | What it checks | Tolerance |
|---|---|---|---|
| **I1** | omnilogic_local_uptime | `omnilogic_local_last_update_success=True` for ≥97% of rows. | <3% failure rate. Currently failing this on 2026-05-01 due to midnight burst (~5% failure). |
| **I2** | midnight_burst_bounded | If errors cluster, the cluster ends by 01:30 local. (Tolerance for the known controller-side burst documented in `scratch/omnilogic-local-midnight-burst-2026-05-01.md`.) | Cluster end time ≤ 01:30. |

### Chemistry assertions (when v2 chemistry columns ship)

| ID | Name | What it checks | Tolerance |
|---|---|---|---|
| **C1** | chlorinator_responds_to_rain | If significant rain, `chlorinator_percent` should bump within 30 min of next pump start. | Verifies rain-boost logic. |
| **C2** | salt_ph_orp_in_range | Chemistry values within configurable normal ranges. | Sanity check, not equipment fault. |

---

## Output format

`pool_audit_YYYY-MM-DD.json`:

```json
{
  "date": "2026-05-01",
  "auditor_version": "1.0.0",
  "summary": { "passed": 14, "failed": 1, "skipped": 2 },
  "assertions": [
    {
      "id": "W3",
      "name": "waterfall_closes_at_end",
      "status": "FAIL",
      "expected": "open→closed transition between 19:55 and 20:15",
      "observed": "no open→closed transition found in log; waterfall_state=open at 23:59",
      "violating_rows": [{"timestamp": "2026-05-01 20:00:00", "waterfall_state": "open"}, ...],
      "severity": "high"
    },
    {
      "id": "P2",
      "name": "nonswim_day_pump_off",
      "status": "SKIP",
      "reason": "swim_day=True, assertion not applicable"
    }
  ]
}
```

Mobile push on FAIL:

```
Pool Audit FAIL — 2026-05-01
1 of 17 assertions failed:
- W3 waterfall_closes_at_end: no open→closed transition; waterfall_state=open at 23:59
[See pool_audit_2026-05-01.json for details]
```

---

## Severity levels

- **HIGH** — equipment doing something it shouldn't (W1 off-window, H2 unsafe). Push immediately.
- **MED** — something missed but no immediate damage (W3 didn't close, P1 missed start). Push at audit time.
- **LOW** — drift / chemistry / integration health. Push only if persistent (≥3 days).

---

## Implementation notes

- **Language:** Python, matches `temp_logger.py` pattern. Use pandas for CSV slicing.
- **Test fixtures:** `pool/scripts/tests/fixtures/` with hand-crafted CSVs that violate each assertion. Run via `pytest` to validate auditor logic before deploying.
- **Backfill capability:** `auditor.py --date-range 2026-04-08 2026-05-01` runs the entire historical CSV through the auditor, producing a JSON per day. Useful for confirming we're not introducing assertion logic that fails on known-good days.
- **Severity-aware notification.** HIGH on `time-sensitive` push (per `automations.yaml` pool API watchdog precedent). MED on regular push. LOW logged only.

---

## Open questions

1. **Audit run time.** 23:55 reads "today's data" but misses any 23:55–00:00 events. 00:05 reads "yesterday's data" cleanly but delays notification 5 min. Lean toward 00:05 — clean cutoff worth 5 minutes.
2. **Tolerance tuning.** Initial tolerances are guesses. After 2 weeks of running, review the FAIL distribution and tune (e.g. if W3's 20-min window catches 0 false positives, tighten to 10 min).
3. **What about manual overrides?** If Scott manually opens the waterfall at 22:00 to clean leaves, W1 fails. Acceptable: documented as expected when manual override happens. Future: optional `input_boolean.pool_manual_override` that suppresses W1/W2/W3 for the day.
4. **Rolling assertions vs daily.** Some patterns (water_temp delta, midnight burst trends) need rolling windows across days. Defer multi-day assertions to a v2 of the auditor. Daily-only for v1.
5. **Storage of historical results.** `pool/audit/*.json` accumulates ~365 files/year. Acceptable. Consider compressing oldest >90 days into a single archive file if it gets unwieldy.

---

## Implementation phases

| Phase | Scope | Depends on |
|---|---|---|
| **1** | Daily-shape + waterfall + heater assertions, JSON output, mobile push. CLI runnable against historical data. | Logger v2 Phase 2 deployed. |
| **2** | Pump assertions including ADR-006 P3/P4. | ADR-006 / Blueprint v1.9.0 shipped. |
| **3** | Action-log reconciliation (P5, W4). | Logger v2 Phase 4 (action log) shipped. |
| **4** | Chemistry assertions, rolling-window assertions. | Logger v2 chemistry columns deployed. |

Phase 1 alone catches the 2026-04-28 valve-stuck-open class of bug. That's the priority.
