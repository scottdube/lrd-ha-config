# Pool Temp Log — Data Schema

Schema for `/config/pool_temp_log.csv`, written by `pool/scripts/temp_logger.py`.

## Columns

| Column | Type | Source | Notes |
|---|---|---|---|
| `timestamp` | string `YYYY-MM-DD HH:MM:SS` | `datetime.now()` at script invocation | Local time (HA host TZ). No timezone marker. |
| `water_temp` | int (°F) | `sensor.omnilogic_pool_watersensor` | OmniLogic Local. Can be `unknown` during integration outages. |
| `oat` | int (°F) | `weather.lake_ridge_dr` attribute `temperature` | WeatherFlow current air temp. Can be `unavailable` if WeatherFlow is down. |
| `heater_state` | string | `water_heater.omnilogic_pool_heater` | Values seen: `on`, `off`. (`heating`/`idle` modes possible — not yet observed.) |
| `pump_state` | string | `switch.omnilogic_pool_filter_pump` | `on` / `off`. Logger only fires when this is `on` (per automation condition). |
| `pump_speed` | int (%) | `number.omnilogic_pool_filter_pump_speed` | Observed values: 0, 55, 65, 77, 90. Can be `unavailable`. |
| `waterfall_state` | string | `valve.omnilogic_pool_waterfall_2` | `open` / `closed`. (Earlier dataset has `on`/`off` from pre-v1.8 switch domain, plus `open`/`closed` rows that were observing the orphan `valve.omnilogic_pool_waterfall` before the 2026-05-01 entity-reference fix — see "Known-bad ranges" below.) |
| `forecast_high` | float (°F) | `sensor.pool_forecast_high` | Template sensor in `config/templates.yaml`. |
| `swimming_day` | string | `sensor.pool_swimming_day` | Free-text, e.g. `Yes` or `No - Forecast 75.0°F`. Not machine-friendly; consider parsing or restructuring. |

## Cadence

Every 10 minutes while pump is on. ~144 rows/day at full pump-day coverage. Pump-off windows (overnight, non-swim days) are not represented — see cleanup-plan 5.3.

## Edge cases

- **`unknown` water_temp** — OmniLogic integration not reporting. Historical event 2026-04-08 → 2026-04-10 cleaned out (see below).
- **`unavailable` pump_speed** — usually transient OmniLogic communication failure. 2 rows on 2026-04-15 cleaned out.
- **Logger script writes raw HA state strings.** No type coercion. Numeric columns are strings in the CSV when they parse cleanly, and string sentinels (`unknown`, `unavailable`) when they don't. Downstream parsers should expect this.

## Known-bad ranges (cleaned)

These rows were removed from the live CSV on 2026-04-28 to simplify analysis:

| Range | Symptom | Rows | Cause |
|---|---|---|---|
| 2026-04-08 20:20 → 2026-04-10 00:00 | `water_temp=unknown` | 39 | Mix of WiFi packet loss to OmniLogic controller AND a separately-fixed integration bug (resolved by maintainer in newer release of `cryptk/haomnilogic-local`). |
| 2026-04-15 (2 timestamps) | `pump_speed=unavailable` | 2 | Transient OmniLogic Local communication failure. |

Cleanup applied via:
```bash
awk -F',' 'NR==1 || ($2!="unknown" && $6!="unavailable")' pool_temp_log.csv > pool_temp_log.csv.tmp
mv pool_temp_log.csv.tmp pool_temp_log.csv
```

A `.bak` of the pre-cleanup file was retained on the NUC at the time. If raw rows are ever needed for forensic purposes, restore from that backup.

## Schema migrations / domain churn

- **2026-04-?? (v1.8.0):** `waterfall_state` switched from `on`/`off` (switch domain) to `open`/`closed` (valve domain) when the OmniLogic Local integration migrated to the valve platform. Earlier rows have the old values. Filter logic should accept both.
- **2026-05-01: orphan-entity bug fix.** Between the v1.8.0 migration and 2026-05-01, the logger and `sensor.pool_automation_status` template were both pointing at the un-suffixed orphan `valve.omnilogic_pool_waterfall` (left over from the domain migration), while the blueprint actually controls `valve.omnilogic_pool_waterfall_2`. Any `open`/`closed` value in rows between those dates reflects the orphan's stale state, not the live valve. Discovered while diagnosing a 2026-05-01 early-morning waterfall run; logger was reporting "open" continuously for 4+ days while we had no signal whether the live valve was actually being closed at 20:00. Fix: `valve.omnilogic_pool_waterfall_2` is now the source.
