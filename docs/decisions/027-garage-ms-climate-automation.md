# ADR-027: Garage mini split climate automation

- Status: Accepted
- Date: 2026-05-28

## Context

The 14-day energy audit (ADR-026 baseline) flagged the garage mini split
as the highest-leverage non-essential load in the house:

- 18.8 kWh/day average — bigger than Air 2 (master HVAC), bigger than
  the pool, more than 15% of whole-home daily energy.
- 391 W persistent at 03:00-04:00 EDT — running essentially 24/7 against
  a static 76°F setpoint, regardless of whether anyone's in the garage.
- ~$933/year at current $0.136/kWh.

Scott uses the garage as a workshop only a few times a week (confirmed
via 14d motion data — see `tools/garage_motion_report.py` output for
2026-05-14..28: total person-detected minutes in the single digits per
peak hour, scattered Mon-Sat with Tuesday afternoons and Saturday
mornings being the heaviest blocks).

But the garage also stores temperature/humidity-sensitive items:

- **Golf grips** (EPDM rubber / TPE / polyurethane) — Arrhenius aging
  ~doubles per 18°F above baseline. At 95°F continuous, grip life is
  roughly halved vs 75°F.
- **Lead-acid golf cart batteries** — calendar life halves per 18°F
  above 77°F (IEEE 1188).
- **Cart electronics** (electrolytic capacitors) — same Arrhenius rule.
- **Leather** (golf bags, gloves, headcovers) — mildew threshold ~65% RH
  sustained, cracking below ~30% RH.

So a naïve "let it drift to 88°F when no one's in there" misses the
storage requirement. The right design conditions on temp AND humidity,
with the cooling setpoint chosen to keep materials in a safe envelope.

## Materials analysis

Conservative storage envelope: **≤ 82°F sustained, ≤ 55% RH**.

| Material | Sensitivity | Safe target |
|---|---|---|
| Golf grips (EPDM, TPE, PU) | Heat-driven plasticizer loss + oxidation | < 85°F, < 60% RH |
| Cart lead-acid batteries | Arrhenius (calendar life) | < 85°F |
| Cart electronics (controllers, charger, motor) | Arrhenius (capacitor failure) | < 85°F |
| Leather (bags, gloves, headcovers) | Mildew at sustained > 65% RH; cracking at < 30% RH | 35-55% RH |
| Wood (legacy clubs, shelving) | Warping + glue breakdown > 70% RH | < 60% RH |

82°F at 55% RH keeps everything well inside spec with margin. Sources:
ASTM D573 (rubber aging), IEEE 1188 (lead-acid life), capacitor
manufacturer datasheets (Nichicon / Rubycon — 10°C rule). Citations not
pulled fresh; flag if specific PDFs needed.

## Temp ↔ humidity tradeoff in FL summer

An A/C in `cool` mode removes humidity as a side effect — water
condenses on the cold coil whenever the compressor cycles. Higher
setpoint = shorter run cycles = less coil-time = less moisture removed.

Observed datapoint (2026-05-28 08:16 EDT): setpoint 76°F → 74°F actual,
**58% RH**. Already at the edge of the 55% storage ceiling at the most
aggressive (lowest) setpoint. Predicted behavior at higher setpoints
(extrapolating from this datapoint + typical 24k BTU mini-split
performance in FL summer outdoor 78-90°F at 70-80% RH):

| Setpoint | Predicted RH (cool-only) | Energy vs current 76°F |
|---|---|---|
| 76°F | 55-58% (baseline) | — |
| 80°F | 58-62% | ~15% savings |
| 82°F | 60-65% (above 55% ceiling) | ~25% savings |
| 84°F | 62-68% | ~33% savings |

To hold 55% RH at any setpoint > 76°F, the unit needs to periodically
run `dry` mode (compressor + slow fan, maximizing latent removal vs
sensible cooling). `dry` mode costs energy but only triggers when
needed.

## Decision

Implement a state-machine-driven climate controller in
`packages/garage_ms/climate.yaml` with six modes:

| Mode | Setpoint | HVAC | When |
|---|---|---|---|
| **DoorOpen** | — | off | Either overhead door open OR within 5 min of last close |
| **ManualOff** | — | off | `input_boolean.garage_ms_manual_off` on |
| **Vacation** | 85°F | cool, dry-guardrail | `input_boolean.vacation` on (shared with energy audit + pool) |
| **Active** | 76°F | cool (no humidity guard) | Schedule window OR `input_boolean.garage_active_now` |
| **Sleep** | 83°F | cool, dry-guardrail | 22:00-06:00 |
| **Storage** | 82°F | cool, dry-guardrail | default |

Priority order is the table order (highest first). DoorOpen always wins.
Manual override (`garage_active_now`) supersedes the time-of-day schedule
but loses to Vacation (no point cooling the workshop when no one's home).

### Humidity guardrail

In any non-Active mode (Storage / Sleep / Vacation), if the unit is
cooling and `climate.garage_ms.attributes.current_humidity` exceeds
55% (ceiling), switch HVAC mode to `dry`. When humidity drops below 53%
(release — 2 pt deadband prevents thrashing), switch back to `cool` at
the mode's setpoint. Active mode does not engage the guardrail —
comfort cooling at 76°F already removes plenty of humidity, and the
guardrail would chase RH at the cost of comfort.

### Active schedule

Initial: 09:00-13:00 daily (`input_datetime.garage_active_start` /
`garage_active_end`, tunable via UI). Set to be ready by 10 AM as Scott
requested — 1 hour pre-cool from Storage 82°F to Active 76°F is enough
for a 24k BTU unit on a moderate-sized garage.

The 14-day motion baseline (collected before this package landed via
`tools/garage_motion_report.py`) suggests the initial schedule
**misses Mon evenings (18-20)** and **over-cools Fri/Sun**. Tunable —
revisit after 30 days of post-deploy data when we know whether the
schedule + manual-override pattern actually fits Scott's usage.

### Manual override

`input_boolean.garage_active_now` provides on-demand Active mode for
ad-hoc workshop trips. Auto-clears 2 hours after activation
(`garage_ms_active_timer_expire`) so a forgotten toggle doesn't leave
the unit at 76°F overnight. Triggers from Echo voice ("Alexa, garage
active"), Companion app dashboard button, or iOS Shortcut.

### Door pause

A composite template binary sensor `binary_sensor.garage_overhead_door_open`
ORs both overhead-door tilt sensors and uses `delay_off: "00:05:00"` to
hold the "open" state for 5 minutes after both doors close. This gives
the climate entity time to stabilize and prevents the unit from
short-cycling on brief in-and-out trips. Walk-in door
(`binary_sensor.garage_door`) is intentionally NOT in the composite —
transient walk-in traffic doesn't dump conditioned air en masse.

A separate notify automation fires if an overhead door stays open >2
minutes — both for the climate impact and as a basic security flag.

### Reconciliation

A single "Apply target state" automation listens for changes to:
- `sensor.garage_ms_target_mode` (template)
- `sensor.garage_ms_target_hvac_mode` (template, includes humidity logic)
- `sensor.garage_ms_target_temperature` (template)
- `climate.garage_ms` (external changes via wall remote / Midea app)
- Time triggers at 06:00, 22:00, `garage_active_start`, `garage_active_end`
- Every 15 min (safety tick — re-asserts state in case of any miss)

Idempotent: only calls `climate.set_hvac_mode` when current ≠ target,
only calls `climate.set_temperature` when abs(current − target) > 0.5°F.

## Expected savings

Predicted reduction from baseline (18.8 kWh/day avg, $0.136/kWh):

- Storage default 82°F vs 76°F: ~25-30% sensible cooling reduction
- Sleep setback 83°F (22-06): ~5% additional
- Dry-mode cycles to hold RH ≤ 55%: adds back ~5-8% (offsets some savings)
- Active 76°F for 4 h/day on average: ~10% of baseline
- Door-pause savings: small but real (~1-2%)

**Net expected: ~25-35% reduction = $230-330/year**

V2 vacation policy (ADR-026 §amendment): garage MS daily energy V2
threshold at 8 kWh/day. This automation should land vacation days
around 5-7 kWh/day — well inside the V2 threshold.

## Validation plan

Week 1 post-deploy (2026-05-28..06-04):
- Confirm `sensor.garage_ms_target_mode` cycles through expected modes
  by hour-of-day (Activity tab on the input_select).
- Spot-check the apply automation's trace at each mode transition.
- Verify climate.garage_ms `current_humidity` stays ≤ 60% (allowing a
  little overshoot during dry-mode catch-up).

Week 2+:
- Compare energy audit's `garage_ms_kwh` rolling avg before/after.
  Expect 18.8 → 12-14 kWh/day in occupied mode.
- Cross-check with Vue Panel A C10 mean overnight power — expect
  drop from 391 W to <250 W.
- If vacation kicks in (Scott leaves 2026-05-30), expect 5-7 kWh/day in
  vacation mode.

If after 2 weeks any of:
- RH consistently > 60% — lower RH ceiling, accept more dry cycles
- Energy savings < 15% — schedule may be wrong (too much Active time)
  or storage setpoint too low; tune via the input_number helpers
- Comfort complaints on workshop days — Active schedule too narrow,
  or active setpoint too high; tune via the input_number helpers

## Future work

- **Schedule refinement** after a month of post-deploy motion data via
  `tools/garage_motion_report.py`. Likely candidates: extend Tue
  schedule into the afternoon, add Mon evening window, remove Fri/Sun.
- **Echo voice command** to fire `input_boolean.garage_active_now` —
  needs an Alexa-Routine bridge or Nabu Casa skill route. Not blocking.
- **Predictive cooling** based on Scott's outdoor presence — if his
  phone enters the LRD geofence and it's a typical workshop day, start
  pre-cooling. Lower priority; manual + schedule cover 95%.
- **Rename the z_wave_plus_gold_plated_reliability_* entities** to
  function-first IDs (per Scott's naming preference). Standalone
  cleanup task — would simplify this package's YAML.

## Files

- `packages/garage_ms/climate.yaml` — the state machine + helpers + automations
- `tools/garage_motion_report.py` — 14d motion / occupancy / door / climate report
- `docs/decisions/027-garage-ms-climate-automation.md` — this ADR
