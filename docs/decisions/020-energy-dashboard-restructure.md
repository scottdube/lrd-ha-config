# ADR-020 — Energy dashboard restructure: HVAC / pool / always-on subtotals + baseload trend

**Status**: accepted 2026-05-18

## Context

Both Vue 3 panels have been on ESPHome with 32/32 branch CTs walk-flipped since 2026-05-14 (Panel A) and 2026-05-12 (Panel B). The built-in HA Energy dashboard renders all 30+ circuits as one bar chart, which is unreadable at this density and surfaces no roll-ups by category. The first multi-day data pull (2026-05-13 → 2026-05-17, hourly long-term statistics via `recorder/statistics_during_period`) produced these signals:

- **Daily total ~127 kWh** at the LRD property in May. Top consumer is Air 1 Condenser (133 kWh over 15 days), followed by Pool Subpanel, Water Heater, Garage Mini Split, Air 2 Condenser.
- **Vue calibration is excellent on Panel A** (unmonitored 0.4–1.0%) but Panel B is at 3–5% — the four CTs still pending walk-flip (slots 3 Washer, 13 Master Bath GFI, 14 Garage Dedicated GFI, 16 Summer Kitchen #2) plus the documented un-CT'd loads (Whirlpool standby, smokes, spare).
- **All three planned cross-validation sources read zero:**
  - `sensor.air_1_total_daily_energy` / `sensor.air_2_total_daily_energy` (Carrier Infinity rollups) — 0 Wh every day across the window.
  - `sensor.garage_ms_energy_total` / `_current` / `garage_ms_power_realtime` (Midea AC LAN) — 0 W / 0 kWh while the Vue CT shows the unit drawing 1.5 kW live.
  - `sensor.151732605885732_total_energy_consumption` / `_current_energy_consumption` (OmniLogic) — no long-term statistics returned at all.
- **A 4 PM "spike" in the initial hourly profile was a Panel B startup artifact** from its first day (79.56 kWh "change" in one hour on 2026-05-12). Real 4 PM hour is 7–9 kWh, comparable to the rest of the afternoon.
- **Non-HVAC baseload sums to ~780 W** (network rack 189 W, family-room lanai standby 110 W, pool subpanel idle 77 W, refrigerator cycle avg 60 W, garage GFI panel 45 W, master-bed lanai 41 W).

## Decision

Add a `packages/energy/` package with **template-sensor subtotals and trigger-based baseload samplers** rather than restructuring the built-in Energy dashboard or renaming Vue entities at this stage.

Specifically:

1. **Subtotal sensors** (Power and Daily Energy in matched pairs):
   - `sensor.whole_home_power` / `sensor.whole_home_daily_energy` — sum of Panel A + Panel B
   - `sensor.hvac_power` / `sensor.hvac_daily_energy` — Air 1 condenser + Air 1 handler + Air 2 condenser + Air 2 handler + garage mini split
   - `sensor.pool_subpanel_power` / `sensor.pool_subpanel_daily_energy_kwh` — pass-through with unit conversion to kWh
   - `sensor.always_on_power` / `sensor.always_on_daily_energy` — refrigerator + network rack + family-room lanai + master-bed lanai + garage GFI panel + recirc pump

2. **Baseload trigger sensors** sampled at 03:30 local each night:
   - `sensor.whole_home_baseload` — full-house draw at 03:30
   - `sensor.always_on_baseload` — non-HVAC always-on subset at 03:30
   Drift over time on these two is the early-warning signal for a load that's started running 24/7 (failing PSU, leaky valve on a pump, etc.).

3. **Energy Detail Lovelace dashboard** (`dashboards/energy-detail.yaml`) — three views: Live (gauges + glance of major loads), Trends (statistics-graph cards for daily totals + HVAC + baseload over 14–30 days), Calibration (unmonitored + voltage entities + cross-val sources with their broken status flagged).

## What this ADR explicitly defers

- **Entity friendly-name renames.** Several daily-energy entities are already renamed via the entity registry (Pool Sub Panel, Refrigerator (Kitchen), Water Heater, Kitchen Outlets Sink Side, Air Handler 2, Summer Kitchen). Completing the pattern across all 32 circuits is desirable but can be done independently. Not committed here because the registry rename is a UI/WS-API change that lives outside git and would create config drift if a partial pass were committed.
- **Anomaly notification automation.** Trigger when hourly kWh exceeds the 14-day rolling mean by N× for that hour-of-day. Threshold tuning requires ~30 days of clean data first, per the Vue analytics-layer plan in `current-state.md`. Punt until ~2026-06-15.
- **Energy dashboard device grouping** in the built-in dashboard. The UI grouping doesn't expose sum-of-children to other contexts (templates, automations, exports). The package above achieves the same readout with reusable entities.
- **Fixing the three broken cross-validation integrations.** Separate work — tracked as new items in `current-state.md` ("Energy cross-validation gaps").

## Why these specific subtotals

The split (HVAC / Pool / Always-on / Everything else) matches the bill-decomposition framework already in `energy/README.md` and ADR-009. It maps directly to the high-leverage questions:

- *"Is the HVAC tuning paying off?"* → watch `sensor.hvac_daily_energy` week-over-week.
- *"Is the pool work paying off?"* → `sensor.pool_subpanel_daily_energy_kwh` vs. the pre-tuning baseline.
- *"Did something start drawing 24/7 that shouldn't?"* → `sensor.always_on_baseload` trend (drift up = investigate).
- *"What does today look like compared to a normal day?"* → all three subtotals on a single dashboard view.

Group membership for HVAC and Always-on is auditable inline in `packages/energy/templates.yaml`. Adjusting is a single-file YAML edit.

## Trade-offs

**Why not entity-registry renames?** They're UI-only (live on the NUC, not in git). Doing it via the WS API and not capturing the choice in a YAML would create config drift the next time the NUC is rebuilt. The ESPHome `name:` field is the proper home for these, but updating it for 30 circuits is a separate change with its own validation cycle. Deferring keeps this ADR scoped to git-tracked, restart-safe changes.

**Why not edit ESPHome YAML to add subtotal sensors there?** ESPHome can compute power subtotals on the Vue itself (`platform: template`), but doing it in HA's template integration keeps the math close to where consumers live (dashboards, automations, statistics) and lets us combine entities from both panels and from non-Vue sources (`hot_water_recirc_pump_power`).

**Trigger-based baseload vs. statistic-based.** A statistic-based "mean of 2-5 AM kWh" would be more accurate but would require a custom statistics integration or external rollup. The 03:30 instantaneous sample is a defensible approximation — the dryer and dishwasher have ended any active cycles by then, and the value is bounded by HVAC compressor cycling (which is what we want for "true" baseload in FL May). If the 03:30 sample turns out to be cycle-phase-sensitive (catches HVAC mid-cycle vs. mid-rest), revisit with a min-of-window aggregation instead.

## Validation plan

1. Push `packages/energy/templates.yaml`. Auto-pull on NUC within 15 min.
2. Restart HA (or wait for the next nightly restart).
3. Verify sensors come up: `sensor.whole_home_power`, `sensor.hvac_power`, `sensor.pool_subpanel_power`, `sensor.always_on_power`, plus the matching daily energy + baseload pairs.
4. Confirm `sensor.whole_home_power` ≈ `sensor.emporia_vue_panel_a_total_power` + `sensor.emporia_vue_panel_b_total_power` to within 1 W.
5. Wait until 03:31 local — confirm `sensor.whole_home_baseload` populates with the captured 03:30 value.
6. After 24 hours: confirm `sensor.hvac_daily_energy` is close to the sum of the constituent Vue daily-energy entities (small drift expected from template-evaluation latency vs. ESPHome's 60s throttle).

## Related

- ADR-009: hardware decision (whole-home power monitoring)
- `energy/README.md`: sub-project structure, install context
- `integrations/emporia-vue-3.md`: Vue 3 ESPHome configuration details
- `docs/current-state.md`: open threads on energy cross-validation

## Update 2026-05-18 evening — Carrier "broken integration" was our typo

The first writeup attributed `sensor.air_1_total_daily_energy` and `sensor.air_2_total_daily_energy` reading 0 to a Carrier-integration regression. Wrong — these are template sensors in `config/templates.yaml` that sum `condenser + handler` per Carrier Infinity system, and the four templates referenced `sensor.emporiavue_panel_…` (no underscore) instead of the actual `sensor.emporia_vue_panel_…`. The summed entities never existed, so the templates always evaluated to `0 + 0 = 0`. The fix is a single replace-all in `config/templates.yaml`. After reload, `air_1_total_power` / `air_1_total_daily_energy` and the Air 2 pair report combined system load — these are the entities the Detail tab's HVAC chart and "Major loads" glance now use (replacing the per-circuit condenser-only entities, which under-counted by ~10-20% depending on handler load).

The OmniLogic energy cross-val was also a paper tiger — the `151732…` entities only exist in historical LTS (integration renamed them); the live `sensor.omnilogic_pool_filter_pump_power` reads correctly and matches Vue pool subpanel to ~1.4% at idle filter speeds. Only the Midea garage mini split cross-val remains permanently unavailable, and that's a model-level integration limit, not a config bug.

Net effect: Vue is no longer load-bearing-alone. The cross-checks are operational everywhere the hardware allows.
