# Pool

Pool-related scripts, data, and analysis. Adjacent to but distinct from the pool *automation* (which lives at `blueprints/automation/LRD/pool_automation/`).

This folder is the home for cross-cutting pool work that doesn't belong inside a single blueprint or integration file: data logging, schema documentation, and (planned) predictive heating/cooling analysis.

---

## Structure

```
pool/
├── README.md          ← this file
├── scripts/
│   └── temp_logger.py ← runs every 10 min while pump is on, appends to /config/pool_temp_log.csv
├── docs/
│   └── data-schema.md ← CSV columns, units, edge cases, known-bad ranges
└── analysis/          ← future: notebooks, trained models, exports
```

---

## How `temp_logger.py` is wired

The script is invoked by HA, not by cron:

1. **Trigger:** `automation.pool_temp_logger` in `automations.yaml` (id: `pool_temp_logger`). Time-pattern every 10 min, conditional on `switch.omnilogic_pool_filter_pump = on`.
2. **Action:** calls `shell_command.pool_log` (defined in `configuration.yaml`).
3. **Shell command:** `python3 /config/pool/scripts/temp_logger.py` with 8 templated state values as positional args.
4. **Output:** appends one row to `/config/pool_temp_log.csv`.

**Live data file:** `/config/pool_temp_log.csv` (gitignored — it's runtime data, not code).

To take a snapshot for analysis: copy the live file into `pool/analysis/snapshots/` with a date suffix.

---

## Why this exists

The longer-term goal is predictive heating/cooling: given a known overnight low, expected morning OAT rise, and current water temperature, decide the optimal pump-start time to be at target by `target_ready_time`. Today the blueprint uses a static `(target_temp - current_water_temp)` heuristic. With enough logged data, that becomes a model.

A second logger pass (planned, not yet built) for pump-OFF intervals will close the data gap on overnight water-temp decay vs. OAT — that's the most predictively valuable window. See `scratch/cleanup-plan.md` item 5.3.

---

## Related files

- `blueprints/automation/LRD/pool_automation/pool_automation.yaml` — the automation logic
- `integrations/omnilogic.md` — entity reference (sensor names match the script's args)
- `docs/decisions/001-omnilogic-local-vs-cloud.md` — why entities have the `omnilogic_pool_*` prefix
- `docs/decisions/002-heater-set-and-hold.md` — heater control philosophy
