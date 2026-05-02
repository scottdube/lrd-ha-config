# Pool Logger v2 — Spec

**Status:** Proposed (for Scott review before implementation)
**Replaces:** Current logger documented in `pool/README.md` and `pool/docs/data-schema.md` (v1).
**Related:** ADR-006 (introduces compressor-active signal), `pool/docs/auditor.md` (consumes logger output).

---

## Why v2

The v1 logger has structural blind spots that masked at least two distinct bugs for weeks:

1. **Conditional on `pump_state=on`.** Logger only fires when pump is running, so it cannot represent pump-off intervals. Verification of "pump should be off right now" is impossible because the data simply isn't there.
2. **Captures HA-observed state only.** No record of what the blueprint *intended* to do, so when state and intent diverge, the disagreement is invisible.
3. **Pointed at orphan entity for the waterfall.** Captured `valve.omnilogic_pool_waterfall` while blueprint controlled `valve.omnilogic_pool_waterfall_2`. Fixed 2026-05-01.
4. **Captured one source of truth, not two.** The two OmniLogic integrations (local UDP and Hayward cloud) often disagree. v1 captured local-only for most fields. The 2026-05-01 incident exposed this when the cloud activity log showed the heater compressor cycling on/off (04:02 → 06:47) while the local water_heater entity sat at "on" all day. We had no logged record of the cloud signal to compare against.
5. **No assertions.** A 24-day CSV nobody reads has zero alerting value.

v2 addresses all five.

---

## Design principles

1. **Always log, never gated.** Capture pump-off behavior with the same fidelity as pump-on.
2. **Capture local AND cloud for every overlapping field.** Two sources, side-by-side. Disagreements become visible immediately. Auditor flags them.
3. **Three layers per row:** observed state (local), observed state (cloud), expected state (blueprint math). Eventually a fourth: commanded state from action log (Phase 4).
4. **Capture more than we think we need.** Storage is cheap. We can always cut columns; we can't recover data we didn't capture. (Per Scott's direction 2026-05-01: "capture all that the local and cloud offer.")
5. **Event-driven supplements time-driven.** Time-pattern row every 10 min for the trend baseline; transition rows on state changes for exact timestamps.
6. **Self-describing.** Schema versioning in a header file so future column additions don't break old data.
7. **Single CSV, prefixed columns.** Decision rationale below.

---

## File structure decision: one file with prefixed columns

Considered alternatives:

| Option | Pros | Cons |
|---|---|---|
| **Single file, prefixed columns** | Cross-validation trivial (read row, compare columns). One shell_command. Timestamps auto-aligned. | Wide rows (~60 columns). Schema changes require row-format updates. |
| Two files (local, cloud), joined by timestamp | Cleaner per-integration schemas. Independent failure handling. | Cross-validation requires join step. Two shell_commands. Timestamp alignment edge cases. |
| Per-domain files (heater, pump, chemistry...) | Tight schemas per concern | Way too many files. Joins everywhere. Auditor complexity. |

**Decision: single file with prefixed columns.** `local_*` for OmniLogic Local integration values, `cloud_*` for Hayward cloud, no prefix for environmental/computed. Auditor's job is much simpler with one wide row. CSV at ~60 columns × ~160 rows/day × 365 days/year = ~3.5M cell-writes/year — still well within CSV's comfort zone.

If schema gets unwieldy in practice, migrate to SQLite later — auditor design accommodates either backend.

---

## Schema v2 — column inventory

Entity IDs confirmed by Scott 2026-05-01:
- Heater compressor (local): `binary_sensor.omnilogic_pool_heater_heater_equipment_status`
- Heater (cloud): `water_heater.pool_pool_heater_heater`
- OmniLogic Local v1.0.4, 22 entities exposed.

Other entity IDs below follow the documented naming conventions (`*.omnilogic_pool_*` for local, `*.pool_pool_*` for cloud per `integrations/omnilogic.md`). Confirm or correct in `pool/docs/data-schema-v2.md` during Phase 1 implementation.

### Time

| Column | Type | Source | Notes |
|---|---|---|---|
| `timestamp` | string `YYYY-MM-DD HH:MM:SS` | `datetime.now()` | Local time (HA host TZ). |
| `row_type` | string | logger | `time_pattern` or `state_change`. Lets the auditor distinguish 10-min snapshots from transition events. |
| `trigger_entity` | string | logger | For `state_change` rows: which entity transitioned. Empty for `time_pattern` rows. |

### Environmental (no prefix — single source)

| Column | Type | Source | Notes |
|---|---|---|---|
| `forecast_high` | float (°F) | `sensor.pool_forecast_high` | Today's WeatherFlow forecast high. |
| `swim_day` | bool | `sensor.pool_swimming_day` parsed | Normalize "Yes" → True, "No - Forecast..." → False. |
| `oat_weatherflow` | float (°F) | `weather.lake_ridge_dr` attr `temperature` | Source-of-truth air temp. |
| `illuminance_lux` | float | `sensor.st_00184974_illuminance` | For pool-light trigger validation. |
| `precipitation_today` | float (mm or inch?) | `sensor.lake_ridge_dr_precipitation_today` | Validates rain-boost chlorinator logic. |
| `precipitation_yesterday` | float | `sensor.lake_ridge_dr_precipitation_yesterday` | Same. |

### Water temperature — interim reliability columns (until external sensor lands)

Per Scott 2026-05-01: the OmniLogic water temp sensor is unreliable when the pump is off (sensor sits in pump return path; needs flow to read accurately). v1 logger gated on `pump_state=on` so this was hidden. v2 always-logs, which surfaces the bad readings — they need to be tagged. **Long-term fix is an external water temp sensor (DS18B20 + ESP32 + ESPHome — see ADR-008).** Until then, mark reliability:

| Column | Type | Source / logic | Notes |
|---|---|---|---|
| `local_water_temp` | float (°F) | `sensor.omnilogic_pool_watersensor` | Raw — may be stale during pump-off intervals. |
| `local_water_temp_reliable` | bool | derived: `pump_state=on` for ≥10 min AND sensor not `unavailable` | Auditor and any consumer of water temp gates on this. 10-min settling threshold is tunable (current best guess). |
| `local_water_temp_trusted` | float (°F) | last value of `local_water_temp` while `_reliable=True`, persisted in `input_number.pool_water_temp_last_reliable` | Best-available water temp at any moment. Blueprint v1.10.0 will source `current_water_temp` from this. |
| `external_water_temp` | float (°F) | placeholder — `sensor.pool_water_temp_external` once ESPHome probe lands | Becomes the source-of-truth column when present. |
| `water_temp_authoritative` | float (°F) | derived: `external_water_temp` if fresh, else `local_water_temp_trusted` | Final consumer-facing value. |

### Local OmniLogic (prefix `local_`)

Source: `cryptk/haomnilogic-local` (UDP). Reference: `custom_components/omnilogic_local/`.

#### Heater (the ADR-006 critical fields)

| Column | Source entity / attribute | Notes |
|---|---|---|
| `local_heater_state` | `water_heater.omnilogic_pool_heater` state | "on"/"off" — virtual heater **enable** state. The misleading-because-named-on signal. |
| `local_heater_equip_status` | `binary_sensor.omnilogic_pool_heater_heater_equipment_status` | **Compressor active** (boolean). The ADR-006 signal. |
| `local_heater_equip_state` | `water_heater.omnilogic_pool_heater` attr `omni_heater_equip_<name>_state` | 3-state enum: `OFF` / `ON` / `PAUSE`. PAUSE = enabled but not running. |
| `local_heater_equip_enabled` | attr `omni_heater_equip_<name>__enabled` | Per-equipment enabled flag. |
| `local_heater_equip_current_temp` | attr `omni_heater_equip_<name>__current_temp` | Solar/refrigerant return temp depending on heater type. |
| `local_heater_target` | `water_heater.omnilogic_pool_heater` `target_temperature` | Setpoint as HA sees it. |
| `local_heater_solar_set_point` | attr `omni_solar_set_point` | Solar override setpoint. |
| `local_heater_why_on` | attr `omni_why_on` | Reason heater is currently on. (Heater-specific enum.) |

#### Filter pump

| Column | Source entity / attribute | Notes |
|---|---|---|
| `local_filter_state` | `switch.omnilogic_pool_filter_pump` | on/off. |
| `local_filter_state_enum` | switch attr `omni_filter_state` | `FilterState` enum: includes `HEATER_EXTEND`, `PRIMING`, `COOLDOWN`, `CSAD_EXTEND`, etc. **Cross-signal for "filter on because heater needs flow."** |
| `local_filter_why_on` | switch attr `omni_why_on` | `FilterWhyOn` enum: `HEATER_EXTEND=4`, `MANUAL_ON=11`, `FREEZE_PROTECT=15`, `TIMED_EVENT=14`, etc. Tells us *why*. |
| `local_filter_speed` | `number.omnilogic_pool_filter_pump_speed` | Speed % (0-100). |
| `local_filter_power` | filter `power` sensor | **Actual W consumption.** Validates speed against load. |
| `local_filter_max_rpm` | number attr `omni_max_rpm` | Pump capability. |
| `local_filter_min_rpm` | number attr `omni_min_rpm` | Pump capability. |
| `local_filter_current_rpm` | number attr `omni_current_rpm` | Computed. |

#### Waterfall (valve)

| Column | Source entity / attribute | Notes |
|---|---|---|
| `local_waterfall_state` | **`valve.omnilogic_pool_waterfall_2`** | open/closed. Fixed entity per orphan-bug fix 2026-05-01. |
| `local_waterfall_function` | valve attr `omni_function` | RelayFunction — confirms it's `RLY_WATERFALL`. |
| `local_waterfall_why_on` | valve attr `omni_why_on` | `RelayWhyOn` enum. |

#### Chlorinator

| Column | Source entity / attribute | Notes |
|---|---|---|
| `local_chlorinator_state` | `switch.omnilogic_pool_chlorinator` | on/off. |
| `local_chlorinator_percent` | `number.omnilogic_pool_chlorinator_timed_percent` | Timed % output. |
| `local_salt_avg` | chlorinator avg salt sensor | PPM. |
| `local_salt_instant` | chlorinator instant salt sensor | PPM. |

#### CSAD (chemistry sense and dispense)

| Column | Source entity / attribute | Notes |
|---|---|---|
| `local_csad_ph` | csad pH sensor | Includes calibration offset. |
| `local_csad_ph_target` | sensor attr `omni_target_value` | |
| `local_csad_orp` | csad ORP sensor | mV. |
| `local_csad_orp_target` | sensor attr `omni_target_level` | |
| `local_csad_mode` | sensor attr `omni_mode` | `CSADMode` enum: OFF/AUTO/FORCE_ON/MONITORING/DISPENSING_OFF. |

#### Pool light

| Column | Source entity / attribute | Notes |
|---|---|---|
| `local_pool_light_state` | `switch.omnilogic_pool_light` (or light entity) | on/off. |
| `local_pool_light_brightness` | light entity `brightness` | If using ColorLogic light. |
| `local_pool_light_show` | light entity `effect` | Current show. |
| `local_pool_light_state_enum` | light attr `omni_state` | `ColorLogicPowerState` enum. |

#### Body of water

| Column | Source entity / attribute | Notes |
|---|---|---|
| `local_water_temp` | `sensor.omnilogic_pool_watersensor` | °F. Source-of-truth water temp. |
| `local_air_temp` | air temp sensor (omnilogic-local backyard) | °F. **Cross-validate with `oat_weatherflow`.** |
| `local_bow_flow` | bow flow binary_sensor | Flow detected in the body of water. **Safety-critical signal.** |

#### Integration health

| Column | Source | Notes |
|---|---|---|
| `local_service_mode` | service mode binary_sensor | True if controller is in service mode (will block control commands). |
| `local_integration_healthy` | derived | True if at least one critical local entity returned a fresh value this poll. False = comm failure. |

### Cloud OmniLogic (prefix `cloud_`)

Source: `djtimca/haomnilogic` (cloud relay). Reference: `custom_components/omnilogic/`. Naming: `*.pool_pool_*` (note the doubled `pool` per `integrations/omnilogic.md:46`).

Updated 2026-05-01 after the activity-log discovery: cloud `heaterState` IS a compressor-activity signal, not just enable. Independent of local binary_sensor — cross-validation source.

| Column | Source entity / attribute | Notes |
|---|---|---|
| `cloud_water_temp` | water temp sensor | Cross-validate with `local_water_temp`. |
| `cloud_air_temp` | air temp sensor | Cross-validate with `local_air_temp`. |
| `cloud_heater_state` | `water_heater.pool_pool_heater_heater` `state` attribute | **Compressor active** signal from cloud (per 2026-05-01 activity log evidence). 0/1 from `heaterState` field. |
| `cloud_heater_enable` | `water_heater.pool_pool_heater_heater` `current_operation` | yes/no — enable state. Should track `local_heater_state`. |
| `cloud_heater_target` | `water_heater.pool_pool_heater_heater` `target_temperature` | Cross-validate. |
| `cloud_filter_state` | filter switch | Cross-validate with `local_filter_state`. |
| `cloud_filter_speed` | filter speed sensor | %. Cross-validate with `local_filter_speed`. |
| `cloud_chlorinator_state` | chlorinator switch | Cross-validate. |
| `cloud_chlorinator_percent` | chlorinator setting sensor (`Timed-Percent`) | Cross-validate. |
| `cloud_chlorinator_super` | superchlorinate switch | scMode — feature only on cloud. |
| `cloud_salt_avg` | avg salt sensor | Cross-validate (cloud is the historical source for salt trending). |
| `cloud_salt_instant` | instant salt sensor | Cross-validate. |
| `cloud_csad_ph` | pH sensor (with offset) | Cross-validate. |
| `cloud_csad_orp` | ORP sensor | Cross-validate. |
| `cloud_alarm_filter` | filter alarm binary_sensor | Cloud-only — not exposed by local. |
| `cloud_alarm_pump` | pump alarm binary_sensor | Cloud-only. |
| `cloud_alarm_heater` | heater alarm binary_sensor | Cloud-only. |
| `cloud_alarm_chlorinator` | chlorinator alarm binary_sensor | Cloud-only. |
| `cloud_alarm_csad` | csad alarm binary_sensor | Cloud-only. |
| `cloud_alarm_lights` | lights alarm binary_sensor | Cloud-only. |
| `cloud_alarm_relays` | relays alarm binary_sensor | Cloud-only. |
| `cloud_alarm_system` | system alarm binary_sensor | Cloud-only. |
| `cloud_alarm_message` | system alarm `alarm` attr | First message text when system alarm fires. |
| `cloud_integration_healthy` | derived | True if cloud returned a fresh value this poll. |

### Computed: blueprint expected-state (no prefix)

Templates that mirror the blueprint's math. Source the same template logic via `templates.yaml` so the blueprint and logger never drift.

| Column | Type | Logic | Why |
|---|---|---|---|
| `expected_pump_state` | string `on`/`off` | template based on swim_day, time-of-day, expected heater activity, filtration_complete | Audit baseline. |
| `expected_pump_speed` | int % | template: 77 if `local_heater_equip_status=on` else 55 (after v1.9.0) | Validates ADR-006 fix once shipped. |
| `expected_waterfall_state` | string `open`/`closed` | template: open in 08:00–20:00 AND swim_day | Includes the swim_day guard the current blueprint lacks. |
| `expected_heater_state` | string `on`/`off` | template: on iff swim_day | Validates set-and-hold. |
| `pump_should_start_minutes` | int | blueprint formula | Lets us see *when* the blueprint thinks the pump should start each day. |
| `hours_to_heat` | float | blueprint formula | Sanity-check the heat-time math. |
| `filtration_complete` | bool | blueprint formula | Validates the filter-hours accounting. |

### Phase 4: action log (separate file)

Per Scott's earlier review, action commands from the blueprint go into a separate file:

```
/config/pool_state_log.csv     ← this spec (state observations)
/config/pool_action_log.csv    ← Phase 4: one row per blueprint action
```

`pool_action_log.csv` columns (provisional):

| Column | Notes |
|---|---|
| `timestamp` | When the blueprint emitted the action event. |
| `entity_id` | Target entity. |
| `service` | E.g. `valve.open_valve`, `switch.turn_on`, `number.set_value`. |
| `data` | JSON blob of service data (target value, etc.). |
| `branch` | Which branch of the blueprint `choose` block fired (e.g. `pump_start`, `waterfall_on`, `waterfall_end`). |
| `reason` | Free-text reason from the blueprint (optional). |

Implementation: blueprint v1.9.0 emits a `pool_automation_action` event at every command point; a separate logger automation listens and appends.

---

## Cadence

- **Time-pattern row every 10 min** — always. No `pump_state=on` condition.
- **State-change row on transition** of any entity that has a `local_*` or `cloud_*` column. Captures exact transition timestamps.
- **Recommend matching the v1.9.0 poll-time shift** (`:05 :15 :25 :35 :45 :55`). Keeps logger and blueprint sampling the same instants.

Estimated row volume: 6/hour × 24h = 144 base + ~20–40 transitions/day = **~170 rows/day**, ~62K rows/year. CSV-comfortable indefinitely.

---

## Migration plan

1. **Phase 1 — non-breaking parallel**: Keep `temp_logger.py` writing v1 schema. Add `state_logger.py` writing v2 to a new file `pool_state_log.csv`. Both run for 7 days to validate v2 captures everything v1 did + new fields work.
2. **Phase 2 — switch primary**: Update `automations.yaml:pool_temp_logger` to call v2 script. Stop v1. Archive v1 CSV with date suffix.
3. **Phase 3 — auditor**: Bring auditor online once Phase 2 has 7 days of clean v2 data to validate against. Auditor depends on v2 columns (especially `local_heater_equip_status`, `cloud_heater_state`, `expected_*`).
4. **Phase 4 — action log**: Implement event emission in blueprint v1.9.0 (the same release that fixes ADR-006). Logger consumes events.

Phases 1 and 2 are mechanical. Phase 3 depends on auditor design. Phase 4 depends on ADR-006 implementation and blueprint v1.9.0.

---

## Open questions

1. **Cloud entity IDs.** Need to grep the live HA registry for actual entity names (e.g. `water_heater.pool_pool_heater`?). Document in `pool/docs/data-schema-v2.md` once known.
2. **Heater equipment binary_sensor entity ID.** Same — needs Settings → Devices & Services check. Likely `binary_sensor.<heater_name>_heater_equipment_status`.
3. **Where to source `local_integration_healthy`.** Coordinator may not expose a single boolean; may need to template off "any local entity is fresh in last 60s." TBD.
4. **Cloud cadence reliability.** Cloud polls every ~minute. State-change capture from cloud will be coarser than local. Acceptable; document as expected.
5. **Pre-cleanup of v1 data.** The `_2`-mismatched waterfall rows from 2026-04-?? through 2026-05-01 are now known-bad. Decision: leave in archive with annotation in `data-schema.md` (already done 2026-05-01), don't delete. Future analysis layer can filter.
6. **CSV vs. SQLite.** At ~60 columns, ~62K rows/year, CSV is fine for years. Defer SQLite migration until row count or query patterns demand it.
7. **Per-row size.** Wide rows mean larger files (~5–10 KB/row vs v1's ~100 bytes). 365 days × 170 rows × 8 KB = ~500 MB/year. Acceptable for years; consider compression of >1-year-old data.

---

## Backup strategy

CSV lives at `/config/pool_state_log.csv` on the HA NUC. Three-tier backup:

1. **Primary: HA OS Supervisor backup.** Already running. Includes `/config/`, so the CSV is captured automatically. Covers HA-software failure modes.
2. **Secondary: nightly rsync to Mac mini (`192.168.50.10`)** over SSH. Survives total HA OS rebuild or NUC failure.
   - **From:** HA NUC (`192.168.50.11`), runs as `shell_command.pool_log_backup`.
   - **To:** `scott@192.168.50.10:/Users/scott/Backups/HA/pool_state_log.csv` (path TBD with Scott).
   - **Auth:** ed25519 SSH key (the one already generated for GitHub auth on 2026-04-30 — verify it's authorized on the mini, generate a separate dedicated key if Scott prefers separation of concerns).
   - **Schedule:** time-pattern automation at 01:00 daily.
   - **Yaml additions:**
     ```yaml
     # configuration.yaml
     shell_command:
       pool_log_backup: rsync -avz /config/pool_state_log.csv scott@192.168.50.10:/Users/scott/Backups/HA/

     # automations.yaml
     - alias: Pool State Log Backup
       trigger:
         - platform: time
           at: "01:00:00"
       action:
         - action: shell_command.pool_log_backup
     ```
3. **Tertiary (optional, deferred):** monthly compressed snapshots to a separate location for point-in-time recovery. Tier 1 + Tier 2 give us "fresh + recent" coverage; tier 3 is for long-term archival, not currently a need.

**Not git.** CSV grows ~500 MB/year per the spec; gitignored at `/config/.gitignore`. Runtime data doesn't belong in version control.

**Same backup pattern applies to `pool_action_log.csv`** once it exists in Phase 4. Add a parallel rsync line at that time.

---

## Phase 1.5 — state-change triggers + context capture (shipped 2026-05-02)

**What was added:**

1. **State-change triggers on `automation.pool_state_logger_v2`.** Three new triggers fire the logger immediately on any state transition of `switch.omnilogic_pool_filter_pump`, `valve.omnilogic_pool_waterfall`, or `water_heater.omnilogic_pool_heater`. Existing `time_pattern: /10` trigger retained for the cadence baseline. Automation `mode: queued` (with `max: 10`) ensures bursts don't drop rows. Row tagging via `row_type` (`time_pattern` vs `state_change`) and `trigger_entity` columns lets the auditor distinguish snapshot rows from transition rows and grep "rows triggered by waterfall transitions" trivially.

2. **Per-entity context columns (9 new columns).** For each of pump, waterfall, heater:
   - `<entity>_state_context_user_id` — non-null when a HA user initiated the change
   - `<entity>_state_context_parent_id` — non-null when an automation/script initiated
   - `<entity>_state_last_changed` — ISO timestamp of the last state transition

   `user_id=None AND parent_id=None` indicates the change came through the integration's coordinator update (external / autonomous controller behavior). This is the same signal the service-lockout detection automations use to distinguish HA-initiated state changes from external panel toggles. Capturing it here lets the auditor flag the same class of events without needing to scrape the Activity log.

**Schema rotation:** `state_logger.py` now checks the existing CSV's `# schema_version=` header on every write. If it doesn't match `SCHEMA_VERSION` constant, the existing file is renamed to `pool_state_log.<old_version>.csv` and a fresh file is created with the new header. This preserves phase 1 data side-by-side with phase 1.5 data without breaking parsers on ragged rows.

**Operational value demonstrated 2026-05-02:** the v1.10.1/v1.10.2 incident debug session required ~5 round trips to HA Activity to attribute pump/waterfall/heater transitions to their causes (blueprint, integration coordinator, manual). With phase 1.5 in place, the same data lives in the CSV directly and the auditor can flag false-positive lockout candidates ("transition with both context_*_id null AND `pool_integration_recovering=off` AND last_triggered_window > 30s on blueprint") automatically.

**Phase 2 still pending:** cloud columns + expected_state computed columns + trusted-temp helper.

---

## File layout (proposed)

```
pool/
├── README.md                   ← updated to point at v2 paths and explain dual-source rationale
├── scripts/
│   ├── temp_logger.py          ← v1, retained during Phase 1, removed after Phase 2
│   ├── state_logger.py         ← v2 — new, captures all local + cloud + expected
│   └── action_logger.py        ← Phase 4 — listens for blueprint events
├── docs/
│   ├── data-schema.md          ← v1 schema, archived
│   ├── data-schema-v2.md       ← v2 schema (this spec's columns in canonical form, with concrete entity IDs filled in)
│   ├── logger-v2.md            ← this file
│   └── auditor.md              ← sibling spec
└── analysis/                   ← unchanged
```
