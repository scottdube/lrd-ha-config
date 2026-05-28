# ADR-026: Whole-home energy daily audit

- Status: Accepted
- Date: 2026-05-27

## Context

The Vue 3 install completed 2026-05-14 (Panel A) and 2026-05-12 (Panel B),
giving us ~14 days of two-panel monitoring. ADR-020 shipped the
templates + dashboards on 2026-05-18. The first multi-day pull (in that
same session) and a 14-day retrospective on 2026-05-27 surfaced findings
that would have benefited from earlier detection:

1. A baseload spike on 2026-05-23 to ~9.3 kW at 03:30 EDT — visible only
   in retrospect when we explicitly pulled `whole_home_baseload` history.
2. The `always_on_power` template under-counts the real overnight baseload
   by ~1300 W — discovered by comparing the captured baseload value
   against the hour-of-day profile.
3. The `air_1_total_daily_energy` / `air_2_total_daily_energy` Carrier
   templates double-count when queried via `recorder/statistics_during_period`
   — discovered only because the audit's first dry-run flagged Air 1 at
   64 kWh on a day the underlying components summed to 31 kWh.

Without a daily check, these signals all required ad-hoc investigation.
At ~$0.136/kWh and ~120 kWh/day, every persistent 200 W of unflagged
drift is ~$24/month. We need passive, durable detection.

The pool auditor pattern (ADR-006 / ADR-021 / pool/scripts/auditor.py)
already proves the architecture works for HA monitoring: launchd-driven,
silent on clean, push-notify on findings, append-only CSV for trending.
Mirror it.

## Decision

Ship `tools/energy_audit.py` as a daily launchd-scheduled script on the
Mac mini at LRD that:

1. Pulls yesterday's local-day energy from HA's `recorder/statistics_during_period`
   WebSocket API.
2. Computes 18 derived metrics per day (per-circuit kWh, per-system HVAC,
   overnight baseload, panel unmonitored %, OmniLogic cross-val).
3. Runs 11 anomaly checks (A1–A11) against thresholds tuned to the
   2026-05-13..26 baseline.
4. Runs a weekly opportunity scan (O1/O3) on Mondays for week-over-week
   creep detection.
5. Appends one row per day to `~/energy-audit/energy_audit.csv`.
6. Push-notifies via `notify.scott_and_ha` only when findings exist
   (silent on clean — same policy as `pool/scripts/audit_recent.py`).

Pair it with two ad-hoc utilities for one-off trend questions:

- `tools/energy_pull_stats.py` — pulls the canonical entity set to JSON.
- `tools/energy_analyze.py` — prints daily totals / top consumers /
  HVAC split / hour-of-day from a stats JSON.

## Anomaly check set (initial)

Thresholds in `energy_audit.py` under `THR_*` constants. Documented in
`tools/README.md` and reproduced compactly here:

| ID | Signal | Threshold | Detects |
|---|---|---|---|
| A1 | Daily WH high vs rolling | > 1.25× 7d avg | Hot day, stuck load, runaway HVAC |
| A2 | Daily WH low | < 0.60× 7d avg | Vue offline, recorder gap, vacancy |
| A3 | Overnight baseload | > 2500 W 02:00–04:00 EDT mean | Unexpected overnight load (heater, AC misconfig) |
| A4 | Always-on creep | > 1.50× 7d median | New standby load, vampire device |
| A5 | Per-AC daily | > 40 kWh (Air 1/2) | Stuck thermostat, ductwork failure |
| A6 | Pool daily | > 30 kWh | Heater runaway, pump stuck high |
| A7 | Water heater daily | > 30 kWh | Element stuck, thermostat drift, recirc fault |
| A8 | Garage MS daily | > 25 kWh | Setpoint accidentally too cold |
| A9 | Unmonitored fraction | Panel A > 2%, B > 8% | CT slip, new un-CT'd circuit |
| A10 | Panel total very low | A < 20, B < 5 kWh | Vue panel offline |
| A11 | OmniLogic > Vue pool | > 1.15× | CT polarity flip, Vue offline |

## Opportunity scan (Mondays)

| ID | Signal |
|---|---|
| O1 | WoW shift > 20% on whole-home / HVAC / pool / water heater / garage MS |
| O3 | overnight baseload − always-on subtotal > 800 W (template under-counts) |

Two slots left intentionally unallocated (O2, O4) for future signals
without renumbering: per-circuit standby pattern detection, un-CT'd
load identification from unmonitored growth, etc.

## Gotchas / non-obvious choices

### Carrier per-system templates double-count over time

`sensor.air_1_total_daily_energy` and `sensor.air_2_total_daily_energy`
sum a condenser + handler. Both underlyings are `total_increasing` and
reset at local midnight (independently — they're in different Vue panel
unit timestreams). The template's resulting state class is
`total_increasing`. When either underlying resets, the template state
drops by that component's pre-reset value. HA's stats engine records the
drop as a reset, banks the pre-reset value into the period's `change`,
then continues accumulating. With two underlyings each resetting once
per day, the period `change` ends up approximately **2× the real daily
energy**.

Real-time state is fine — the template correctly shows the live sum.
Only the per-period `change` from `recorder/statistics_during_period` is
broken. Workaround: the audit computes Air 1 / Air 2 by summing the
underlying Vue circuit `_daily_energy` entities directly. Fix candidates
(not blocking the audit landing):

- Replace the template with two independent template sensors (one per
  underlying) and aggregate in the dashboard / energy panel grouping.
- Migrate to a trigger-based template that captures the daily total
  just before midnight and resets at midnight (a "snapshot" sensor),
  exposing a clean `total_increasing` view.

Filed as backlog under "Energy cross-validation gaps".

### Always-on template under-counts by ~1300 W

The `Always On Power` template in `packages/energy/templates.yaml` sums
six circuits totaling ~400 W overnight. The measured `whole_home_power`
overnight baseload (after subtracting HVAC + pool) is ~1700 W. Gap is
real. Likely missing items:

- Hot-water-recirc-pump circuit reading 0 W when commanded off (true);
  its on-cycle isn't captured because it's a state-class issue, not a
  template-membership issue.
- Inverter-driven loads on the lanai (TVs in standby, network gear in
  the family room — currently only the "Family Rm Lanai" circuit is
  in the subtotal, but standby loads exist on other circuits too).
- The summer kitchen circuits (P-A C6, P-B C16) — refrigeration or LED
  strips left on.
- Master bath GFI (P-B C13) — towel warmer? Heated mirror?

O3 fires on this and pushes a Monday-only reminder. Not a P1 fix.

### Why this isn't an HA-side automation

Three reasons to keep this as a Python script on the Mac mini, not an
HA automation:

1. Statistics-engine queries via the WS API are awkward to express in
   automation YAML — they need `recorder/statistics_during_period`
   service calls plus heavy template logic to extract per-day deltas.
2. The audit needs a durable CSV history that survives HA recorder
   purges (default 10 days). Python writing to disk on the always-on
   Mac mini is the right durability layer.
3. Pattern consistency — the pool auditor, Z-Wave health probes, and
   nightly retrospective all live as Mac-mini-resident scripts. Energy
   is the natural fourth member of that family.

### Timing — 06:30 EDT

Late enough that yesterday's local-day is fully closed in HA's recorder
(midnight reset + ESPHome publish latency + LTS flush, typically <10
min) but early enough that the notification lands before the morning
routine. Same window as the original pool nightly audit cron, just
shifted later by ~30 min to clear LTS flush stragglers.

## Rollout

1. `tools/energy_audit.py`, `tools/energy_pull_stats.py`,
   `tools/energy_analyze.py`, `tools/launchd/com.scottdube.ha.energy-audit.plist`,
   `tools/README.md` updates committed in this branch.
2. Pull on the Mac mini: `cd ~/code/home-assistant && git pull --ff-only`.
3. Install launchd:
   ```
   ln -sf ~/code/home-assistant/tools/launchd/com.scottdube.ha.energy-audit.plist \
          ~/Library/LaunchAgents/
   launchctl bootstrap gui/$(id -u) \
          ~/Library/LaunchAgents/com.scottdube.ha.energy-audit.plist
   ```
4. Backfill historical days (Vue install onwards):
   ```
   for d in $(seq -f "2026-05-%02g" 14 26); do
       ~/.venv/zwave-health/bin/python3 ~/code/home-assistant/tools/energy_audit.py \
           --for-date "$d" --no-notify --print-clean
   done
   ```
5. First scheduled run: 2026-05-28 06:30 EDT, auditing 2026-05-27 local-day.

## Future work

- Tune thresholds after 30 days of CSV history when the seasonal envelope
  is clearer. Watch especially A1 (1.25× may be too tight as Florida
  summer ramps).
- Add a degree-day-normalized A1 variant — flag high days adjusted for
  cooling-degree-days against `sensor.whole_home_kwh_per_cdd_65_7d`.
- Fix the `air_X_total_daily_energy` template double-count by migrating to
  a trigger-based snapshot template (lifted to its own ADR if the audit
  surfaces additional cases of the same pattern).
- Expand the `Always On Power` template membership in
  `packages/energy/templates.yaml` to close the O3 gap, then tighten the
  A4 threshold.

---

## Amendment 2026-05-27 — vacation-mode profile (v1.1.0)

Scott leaves LRD 2026-05-30 for the summer. v1.0.0's occupied-baseline
thresholds would misbehave during the transition (A1/A2 false-positives
across a mix-mode rolling avg, A10 false-positives on legitimately-low
vacation panel totals, A7 silent on a re-energized water heater that's
supposed to be off, O1 weekly scan spamming WoW deltas across the mode
flip) and miss the canonical vacation anxieties ("did I leave the stove
on?", "is the pool pump still running?").

### Mechanism

`energy_audit.py` reads `input_boolean.vacation` at run time (CLI override
`--vacation-override on|off` for backfill or what-ifs) and switches between
two `Thresholds` profiles defined at the top of the file. The CSV gains a
`vacation` column (0/1) and migrates the v1.0.0 file in place on first
v1.1.0 run, backing up the original as `energy_audit.csv.pre-v1.1.0.bak`.

Rolling averages (A1/A2/A4) compute over **same-mode rows only**, which
eliminates the mixed-baseline noise during transitions. A safety guard
requires ≥3 same-mode rows before A1/A2 fire and ≥5 before A4 fires, so
the first few days post-flip operate purely on absolute checks.

A one-time `[MODE]` notification fires on the day the flag changes, so
Scott sees the transition logged explicitly.

### Threshold deltas

| ID | Occupied | Vacation | Why |
|---|---|---|---|
| A3 (overnight baseload) | > 2500 W | **> 1200 W** | Catches "AC running unexpectedly" when nobody's home |
| A5 (Air 1/2 per day) | > 40 kWh | **> 15 kWh** | HVAC should cycle far less at raised setpoints |
| A7 (WH per day) | > 30 kWh | unchanged (fallback) | Real signal is V1 |
| A8 (Garage MS per day) | > 25 kWh | unchanged (fallback) | Real signal is V2 |
| A10 (panel total low) | enabled | **disabled** | Vacation totals can legitimately drop into the teens |

### New vacation-only checks (V1–V7)

| ID | Signal | Threshold | Rationale |
|---|---|---|---|
| V1 | Water heater daily | > 1.0 kWh | Off in vacation per Scott's policy; any draw is signal |
| V2 | Garage MS daily | > 8.0 kWh | Dehumidify-only ceiling per Scott's policy |
| V3 | Whole-home daily cap | > 80 kWh | Vacation mode isn't really engaged |
| V4 | Pool subpanel daily | **< 1.0 kWh** | Inverted floor — pump unexpectedly off = stagnant pool (P1) |
| V5 | Cooktop / oven / stove | > 0.3 / 0.3 / 2.0 kWh | "Did I leave it on?" — stove threshold higher to allow for ~0.5 kWh/day digital-clock standby |
| V6 | Dryer daily | > 0.3 kWh | Dryer accidentally running while away |
| V7 | Recirc pump full-day mean power | > 10 W | Off in vacation per Scott's policy |

V4 is the standout — a floor, not a ceiling. A stagnant pool in FL summer
is a P1 condition (algae bloom, equipment damage from off-spec chemistry).
Other V-checks are nuisance prevention; V4 is real consequence prevention.

### O1 weekly scan suppression

`days_since_mode_flip()` counts the run length since the most recent
vacation-flag change. If < 14 days, Monday's WoW scan is suppressed —
WoW deltas spanning a mode transition are meaningless. If history shows
no flip (long-stable in one mode), the function returns 999 and weekly
scans run normally.

### What still needs validation

The vacation thresholds were chosen from policy + standby-load
measurement, not from observed vacation-mode baselines (we don't have
any yet). Plan: review the first 14 days of vacation CSV rows after
Scott leaves, tune V1–V7 + A3-vac if any are noisy or silent on real
signals. Most likely candidate for retuning is V5 kitchen-stove
(threshold may need to come down to 1.0 kWh if standby is lower than
expected) and A3-vac baseload (1200 W is a guess — could be too tight
if some unexpected always-on load survives the vacation prep).

### Schema migration

v1.0.0 CSV (20 cols) → v1.1.0 CSV (27 cols). New columns:
`vacation`, `recirc_w_avg`, `cooktop_kwh`, `wall_oven_kwh`,
`kitchen_stove_kwh`, `dryer_kwh`. Old rows get `0` defaults for new
columns and `audit_version = "energy-audit-1.0.0-migrated"`. The
migration runs automatically on the first v1.1.0 invocation; original
file preserved as `.pre-v1.1.0.bak`.

## Sources

- 2026-05-27 conversation: 14-day trend analysis identifying the three
  findings above.
- ADR-006 (audit architecture), ADR-020 (energy dashboard restructure),
  ADR-021 (Mac mini launchd pattern).
- `pool/scripts/audit_recent.py` (silent-on-clean reference pattern).
