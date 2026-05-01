# Pool State Log v2 — Data Schema (phase 1)

Schema for `/config/pool_state_log.csv`, written by `pool/scripts/state_logger.py`.

**Schema version:** `2.0-phase1`
**Status:** Phase 1 (local OmniLogic + environmental + computed water_temp_reliable). Cloud, trusted-temp, and expected-state columns deferred to phase 1.5/2.
**Source code:** `pool/scripts/state_logger.py`
**Spec:** `pool/docs/logger-v2.md`

---

## File header

The CSV file's first line is a comment row containing the schema version:

```
# schema_version=2.0-phase1
timestamp,row_type,trigger_entity,forecast_high,...
2026-05-02 09:10:00,time_pattern,,90.0,...
```

The schema version line is not a CSV row; downstream parsers must skip lines starting with `#`.

---

## Columns (phase 1, in order)

### Time

| Column | Type | Source / logic | Notes |
|---|---|---|---|
| `timestamp` | string `YYYY-MM-DD HH:MM:SS` | `datetime.now()` at script invocation | Local time (HA host TZ). No TZ marker. |
| `row_type` | string | passed via `--row-type` arg | `time_pattern` (default) or `state_change`. Phase 1 only writes `time_pattern`; state-change triggers added in phase 1.5. |
| `trigger_entity` | string | passed via `--trigger-entity` arg | For `state_change` rows: which entity transitioned. Empty for `time_pattern`. |

### Environmental

| Column | Type | Source | Notes |
|---|---|---|---|
| `forecast_high` | float (°F) | `sensor.pool_forecast_high` | Today's WeatherFlow forecast high. |
| `swim_day_raw` | string | `sensor.pool_swimming_day` | Free text — `Yes`, `No - Forecast 75.0°F`, etc. (Normalize at parse time.) |
| `oat_weatherflow` | float (°F) | `weather.lake_ridge_dr` attr `temperature` | Source-of-truth air temp. |
| `illuminance_lux` | float | `sensor.st_00184974_illuminance` | For pool-light trigger validation. |
| `precipitation_today` | float | `sensor.lake_ridge_dr_precipitation_today` | Validates rain-boost chlorinator logic. |
| `precipitation_yesterday` | float | `sensor.lake_ridge_dr_precipitation_yesterday` | Same. |

### Local — heater (the ADR-006 critical fields)

| Column | Source | Notes |
|---|---|---|
| `local_heater_state` | `water_heater.omnilogic_pool_heater` state | `on` / `off` — virtual heater **enable** state. |
| `local_heater_equip_status` | `binary_sensor.omnilogic_pool_heater_heater_equipment_status` | **Compressor active** boolean. The ADR-006 signal. |
| `local_heater_equip_state` | `water_heater.omnilogic_pool_heater` attr `omni_heater_equip_Heater__state` | 3-state enum string: `OFF` / `ON` / `PAUSE`. (Note double underscore in the attribute key — that's how the integration emits it.) **Verify the heater equipment name is `Heater` on the live system** — if it's named differently in OmniLogic config, the attribute key is `omni_heater_equip_<name>__state`. Adjust in `state_logger.py` COLUMNS list if needed. |
| `local_heater_equip_enabled` | same entity, attr `omni_heater_equip_Heater__enabled` | Per-equipment enabled flag. |
| `local_heater_target` | water_heater attr `temperature` | Setpoint. |
| `local_heater_solar_set_point` | water_heater attr `omni_solar_set_point` | Solar override setpoint. |
| `local_heater_why_on` | water_heater attr `omni_why_on` | Reason heater is currently on. |

### Local — filter pump

| Column | Source | Notes |
|---|---|---|
| `local_filter_state` | `switch.omnilogic_pool_filter_pump` state | `on` / `off`. |
| `local_filter_state_enum` | switch attr `omni_filter_state` | `FilterState` enum: `OFF`, `ON`, `PRIMING`, `WAITING_TURN_OFF`, `HEATER_EXTEND`, `COOLDOWN`, `SUSPEND`, `CSAD_EXTEND`, `FILTER_SUPERCHLORINATE`, `FILTER_FORCE_PRIMING`, `FILTER_WAITING_TURN_OFF`. **`HEATER_EXTEND` is a parallel signal that filter is running because heater needs flow** — useful cross-check. |
| `local_filter_why_on` | switch attr `omni_why_on` | `FilterWhyOn` enum, includes `HEATER_EXTEND=4`, `MANUAL_ON=11`, `FREEZE_PROTECT=15`, etc. |
| `local_filter_speed` | `number.omnilogic_pool_filter_pump_speed` | Speed % (0-100). |
| `local_filter_power` | `sensor.omnilogic_pool_filter_pump_power` | Actual W consumption. Replaces cube-law estimates with measured data. **Predictive maintenance signal:** if W-per-RPM ratio drifts up over time, that's impeller wear or filter pressure rising; sudden spikes = blockage; drop = mechanical issue. |

### Local — waterfall

| Column | Source | Notes |
|---|---|---|
| `local_waterfall_state` | `valve.omnilogic_pool_waterfall` state | `open` / `closed`. Verified live entity per Developer Tools → States 2026-05-02 (`_2` suffix turned out to be the orphan, not the live one — initial fix on 2026-05-01 was wrong-direction; reverted). |
| `local_waterfall_function` | valve attr `omni_function` | RelayFunction — should be `RLY_WATERFALL`. |
| `local_waterfall_why_on` | valve attr `omni_why_on` | RelayWhyOn enum. |

### Local — chlorinator

| Column | Source | Notes |
|---|---|---|
| `local_chlorinator_state` | `switch.omnilogic_pool_chlorinator` state | on/off. |
| `local_chlorinator_percent` | `number.omnilogic_pool_chlorinator_timed_percent` | Timed % output. |

### Local — water + reliability

| Column | Source / logic | Notes |
|---|---|---|
| `local_water_temp` | `sensor.omnilogic_pool_watersensor` | Raw — may be stale during pump-off intervals because the sensor is in the pump return path. |
| `local_water_temp_reliable` | `'true'` if pump on for ≥ 10 min, else `'false'` | Computed in script. 10-min settling threshold tunable via `WATER_TEMP_SETTLING_SECONDS` constant in `state_logger.py`. **All consumers of `local_water_temp` must gate on this.** |

### Local — pool light

| Column | Source | Notes |
|---|---|---|
| `local_pool_light_state` | `switch.omnilogic_pool_light` state | on/off. |

---

## Cadence (phase 1)

- **Every 10 min** via `automation.pool_state_logger_v2` (time pattern). Always — no pump-on gate.
- **State-change rows** added in phase 1.5.
- **Estimated row volume:** 144 rows/day, ~52K rows/year.

---

## Setup checklist

1. **Generate long-lived access token in HA:**
   - Profile (bottom-left) → Security tab → Long-Lived Access Tokens → "Create Token".
   - Name it `state_logger_v2`. Copy the token immediately — HA only shows it once.
2. **Save the token to the NUC:**
   - From Studio Code Server terminal, or any shell into the NUC:
     ```
     printf '%s' 'PASTE_TOKEN_HERE' > /config/.state_logger_token
     chmod 600 /config/.state_logger_token
     ```
3. **Verify gitignore covers it:** already in `.gitignore` as `.state_logger_token`. Confirm before any commit.
4. **Test the script manually before relying on the automation:**
   ```
   python3 /config/pool/scripts/state_logger.py --row-type time_pattern
   ```
   Should produce no output and append a row to `/config/pool_state_log.csv`.
5. **Reload automations** (or restart HA) to pick up the new automation entry.

---

## Failure modes and fallbacks

- **Missing token:** script exits with error code 1, HA logs it under `homeassistant.components.shell_command`.
- **HA REST API unavailable** (rare — script runs from same host): individual entities return `unavailable`, row is still written.
- **Single entity not found:** that column reads `unavailable`, row is still written. Useful for tolerating different-than-expected entity names — the script doesn't crash if the heater equipment is named differently than `Heater`, you just see `unavailable` in those columns and adjust the COLUMNS manifest.
- **Filesystem error writing CSV:** script exits non-zero. HA logs under shell_command's failure handling.
- **Parallel invocations** (state-change in phase 1.5): CSV append is line-atomic on POSIX for short rows — should be safe. If we ever exceed POSIX's `PIPE_BUF` (4KB) per row, switch to a lock file.

---

## Phase progression

Current = phase 1 (this doc).

| Phase | Adds |
|---|---|
| 1.5 | State-change triggers. Filter power sensor. Heater equipment current_temp. |
| 2 | Cloud columns (after Scott confirms cloud entity names). Computed `expected_*` columns. `input_number.pool_water_temp_last_reliable` helper + trusted-temp updater + `local_water_temp_trusted` column. |
| 3 | rsync backup to Mac mini (`192.168.50.10`). Action log via blueprint events. External water-temp sensor support (placeholder column already in spec). |

---

## Migration from v1 (`pool_temp_log.csv`)

- v1 still runs in parallel during phase 1 (~7 days) per spec.
- v2 starts a fresh CSV at `/config/pool_state_log.csv`. Schemas are different (v2 is much wider) — they don't share rows.
- v1 retired in `automations.yaml` once v2 validates. Final v1 CSV archived with date suffix.
