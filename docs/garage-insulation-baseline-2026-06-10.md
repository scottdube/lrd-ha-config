# Garage door insulation — pre-install baseline

- Captured: 2026-06-10 (one day before install)
- Install date: 2026-06-11 **(completed by 13:00 EDT — confirmed by Scott)**
- Clean post-install measurement window starts: 2026-06-12 (skipping the transition day)
- Baseline window: 2026-05-31 → 2026-06-09 (10 days)
- Mode during window: vacation (`input_boolean.vacation` = on continuously since 5/31), garage MS in Vacation profile (target 85°F, humidity guardrail above 55% RH)
- Companion: task #42 (post-return analysis), task #43 (CDD-normalized template sensor)

## Experiment design

Compare garage MS energy consumption pre vs post insulation install. Both
windows are vacation-mode at 85°F target — same setpoint eliminates the
setpoint confound. Summer FL is the high-leverage period (high outdoor
temps + direct sun loading on uninsulated doors), so the signal-to-noise
ratio is at its annual best.

### Why same-setpoint comparison is the right call

Earlier methodology considered comparing pre-install occupied data
(76°F setpoint, 18.8 kWh/day) vs post-install vacation data (85°F, TBD).
That would have conflated setpoint shift with insulation effect. With
the vacation flag flipping 2026-05-31 BEFORE the install, we get
10 days of pre-install vacation data — same setpoint as the 4.5-month
post-install window.

### Confounders and controls

- **Outdoor temperature varies** across May vs Sep/Oct. Control: compute
  kWh per cooling-degree-day (CDD-65 base) for each day, compare the
  per-CDD efficiency instead of raw daily kWh. Build
  `sensor.garage_ms_kwh_per_cdd_65_7d` (task #43) mirroring the existing
  whole-home version in `packages/energy/degree_days.yaml`.
- **Solar heat gain varies** with sun angle (lower in fall vs summer
  solstice). Mitigated by analyzing the **overnight 03:00 EDT power
  draw**, when sun loading = 0 and the only thermal driver is conduction
  through the envelope. This signal is dominated by door insulation.
- **Humidity load varies** with outdoor RH. Vacation profile's `dry`
  mode cycles depend on this. Track separately —
  `sensor.garage_ms_humidity` (the Midea unit's internal sensor) gives
  us indoor RH; weather sensor gives outdoor RH.

## Pre-install baseline numbers

### Whole-home daily energy (10-day vacation window)

| Date | Day | Whole-home kWh |
|---|---|---|
| 2026-05-31 | Sun | 45.30 |
| 2026-06-01 | Mon | 43.59 |
| 2026-06-02 | Tue | 41.94 |
| 2026-06-03 | Wed | 39.34 |
| 2026-06-04 | Thu | 38.39 |
| 2026-06-05 | Fri | 38.47 |
| 2026-06-06 | Sat | 37.67 |
| 2026-06-07 | Sun | 40.73 |
| 2026-06-08 | Mon | 37.82 |
| 2026-06-09 | Tue | 41.91 |

**10-day average: 40.5 kWh/day** (range 37.7 - 45.3 kWh/day)

Cost at SECO Energy effective $0.136/kWh: ~$5.51/day, ~$165/month.

### ★ Garage MS — the experiment target

```
Total over 10-day window:  84.3 kWh
Daily average:             8.43 kWh/day
```

Comparison to May 13-26 occupied baseline (per ADR-027 analysis):

| Mode | Daily kWh | Setpoint |
|---|---|---|
| Occupied (May 13-26) | 18.8 kWh/day | mixed 76°F Active / 82°F Storage / 83°F Sleep |
| Vacation (May 31 - Jun 9) | **8.43 kWh/day** | 85°F constant + humidity guardrail |

Vacation mode achieves 55% reduction vs occupied — that's the expected
setpoint+occupancy effect. The insulation experiment isolates a
different variable: thermal flux through the envelope at constant
setpoint.

### Other HVAC vacation comparison

| System | Vacation kWh/day | Occupied (May 13-26) kWh/day | Vacation reduction |
|---|---|---|---|
| Air 1 condenser | 3.71 | 26.97 | 86% lower |
| Air 1 handler | 0.41 | 2.64 | 84% lower |
| Air 2 condenser | 0.55 | 11.79 | 95% lower |
| Air 2 handler | 0.22 | 0.87 | 75% lower |
| **Garage MS** | **8.43** | **18.82** | **55% lower** |

Garage MS shows the **smallest vacation reduction** among the HVAC
systems — direct evidence that the garage envelope is the leakiest
thermal boundary in the house. That's exactly the variable insulation
targets.

### Overnight baseload (envelope conduction signal)

```
Whole-home min-hour-avg (vacation): 868 W
  → Daily baseload: 20.8 kWh ($2.83/day)

vs occupied (May 13-26): ~1700 W min-hour-avg
  → Vacation reduction: 49% lower whole-home baseload
```

The pre-install overnight 03:00-04:00 EDT garage MS power specifically
(extracted from `sensor.emporia_vue_panel_a_circuit_10_garage_mini_split_power`
via the same `recorder/statistics_during_period` query, period: hour,
type: mean, hours 7-8 UTC = 03-04 EDT) is the cleanest insulation-effect
signal. Run the per-circuit hour-of-day analysis as part of the
post-return comparison.

### Other loads (top consumers during vacation)

| Circuit | 10-day kWh | Daily avg |
|---|---|---|
| Pool subpanel | 146.3 | 14.6 kWh/day (~36% of WH) |
| **Garage mini split** | **84.3** | **8.43** |
| Network rack | 52.6 | 5.26 (220 W constant always-on) |
| Air 1 condenser | 37.1 | 3.71 |
| Refrigerator | 18.2 | 1.82 |
| Family room lanai | 14.7 | 1.47 (~61 W standby — see watch-item below) |
| Water heater | 7.3 | 0.73 (see watch-item — policy says off) |
| Air 2 condenser | 5.5 | 0.55 |
| Master bed lanai | 4.8 | 0.48 |
| Air 1 handler | 4.1 | 0.41 |

## Watch-items spotted in the baseline data

These don't affect the insulation experiment but are worth chasing
when Scott has bandwidth:

1. **Water heater at 0.73 kWh/day during vacation.** Policy is "off"
   per Scott's earlier confirmation. Either the breaker wasn't actually
   opened, or there's element thermostat / standby draw at the tank.
   V1 audit threshold is 1 kWh/day so it's quietly sitting just below
   the alert. Verify breaker state next physical access.

2. **Family room lanai at 1.47 kWh/day** (~61 W continuous standby).
   That's the TV + AV equipment standby. Higher than expected for a
   "fully off" vacation prep. Possibly TV's not unplugged.

3. **Garage MS at exactly 8.43 kWh/day — right at the V2 audit
   threshold of 8 kWh/day.** Will likely trip V2 intermittently on
   hotter days. Recommend bumping `THR_GARAGE_PER_DAY` for the vacation
   profile from 8.0 to 10.0 in `tools/energy_audit.py` so we get
   meaningful escalation alerts instead of baseline-noise pings.

4. **`energy_analyze.py` "% of WH" column is bogus** (showing 14630%
   etc) — script bug in the percentage calc. kWh numbers themselves are
   fine. File as a tools/ cleanup followup.

## Post-return analysis procedure

When Scott returns mid-October:

1. **Pull the matched post-install vacation window.** Same script,
   wider `--days` to capture the multi-month interval:
   ```
   python3 tools/energy_pull_stats.py \
       --token ~/Documents/Claude/Projects/home-assistant/.ha-token \
       --days 130 --out /tmp/post_install_window.json
   python3 tools/energy_analyze.py --stats /tmp/post_install_window.json
   ```

2. **Build the CDD-normalized template** (task #43) if not already in
   place. Add a `garage_ms_kwh_per_cdd_65_7d` template sensor in
   `packages/energy/degree_days.yaml` mirroring the whole-home pattern.

3. **Compare the matched metrics:**
   - Garage MS daily kWh average (pre 8.43 vs post ?)
   - Garage MS overnight 03:00-04:00 EDT power (pre TBD W vs post ?)
   - Garage MS kWh per CDD (pre TBD vs post ?)
   - Indoor humidity dynamics during dry-mode cycles (frequency + duration)

4. **Document the result** in a `garage-insulation-result-2026-10-XX.md`
   sibling doc + an ADR if the finding is material enough to inform
   future envelope decisions (e.g., attic insulation, wall retrofits).

## Sources

- 2026-06-10 conversation pulling the baseline pre-install
- `tools/energy_pull_stats.py` + `tools/energy_analyze.py` output saved
  to `/tmp/pre_install_baseline.json` on Scott's MacBook (raw JSON
  archive — not in repo; pull again from HA recorder if needed within
  the LTS retention window)
- ADR-026 (energy audit), ADR-027 (garage MS climate state machine)
