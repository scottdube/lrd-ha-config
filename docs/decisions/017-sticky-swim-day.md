# ADR-017: Sticky swim_day with morning lock + waterfall-window guard on shutdown branches

**Date:** 2026-05-03
**Status:** Accepted
**Related:** ADR-002 (heater set-and-hold), ADR-006 (actively-heating), ADR-013 (water-temp fallback)

## Context

On 2026-05-03 at 19:10:02 the pool blueprint executed an unexpected shutdown — pump turned off, waterfall closed — fifty minutes before the configured `waterfall_end_time` of 20:00. Activity log attribution was correct (Pool Automation v1.10.1, time pattern), but the resulting equipment state was wrong: a perfectly normal swim day had its evening cut short.

Root cause traced to live forecast re-evaluation:

- 18:50 — `sensor.pool_forecast_high` = 81.0, `swim_day_raw` = Yes
- 19:00 — WeatherFlow forecast updated; `sensor.pool_forecast_high` = 77.0, `swim_day_raw` flipped to No
- 19:10 — blueprint time-pattern fire evaluated NOT-A-SWIM-DAY branch condition `not swimming_day and pump_is_on`; both true → shutdown executed (pump.turn_off + valve.close_valve)

The blueprint variable `swimming_day` is computed every poll from `forecast_high >= min_swim_temp`. When forecast wiggles across the threshold mid-day, `swimming_day` flips with it, and shutdown branches that key off `swimming_day` fire as if the day was non-swim from the start.

This is a structural bug in the day-shape model. Forecasts wiggle. Pools shouldn't.

## Decision

Two-part fix:

**Part 1 — Morning lock on swim_day decision.**

Capture the swim_day determination once at 05:55 daily into `input_boolean.pool_swim_day_today`. The blueprint reads from this boolean instead of re-evaluating `forecast_high >= min_swim_temp` each poll. Mid-day forecast wiggles no longer affect today's run; tomorrow's lock at 05:55 picks up tomorrow's forecast.

**Part 2 — NOT-A-SWIM-DAY shutdown branch gated by waterfall window.**

Add `current_minutes < waterfall_start_minutes` to the NOT-A-SWIM-DAY branch condition. After the waterfall start time (08:00 default), this branch cannot fire even if `swimming_day` somehow flips to False. Equipment shutdown post-window is owned exclusively by WATERFALL END (which has no `swimming_day` dependency and respects `waterfall_end_time` directly).

Defense-in-depth: even if Part 1 has a bug or the morning automation fails to fire, Part 2 prevents mid-day shutdown of an active pool day.

## Implementation

**Helper** (`packages/pool/pool_modes.yaml`):

```yaml
input_boolean:
  pool_swim_day_today:
    name: Pool Swim Day Today
    icon: mdi:pool
```

**Morning lock automation** (`packages/pool/pool_modes.yaml`):

```yaml
- alias: "Pool: Lock swim_day decision at 05:55"
  trigger:
    - platform: time
      at: "05:55:00"
  action:
    - choose:
        - conditions:
            - condition: state
              entity_id: sensor.pool_swimming_day
              state: "Yes"
          sequence:
            - action: input_boolean.turn_on
              target:
                entity_id: input_boolean.pool_swim_day_today
      default:
        - action: input_boolean.turn_off
          target:
            entity_id: input_boolean.pool_swim_day_today
  mode: single
```

05:55 chosen to land before any morning blueprint activity (PUMP START gates start at 08:00 via `pump_should_start_minutes`, but earlier polls evaluate variables and we want them stable).

**Blueprint changes** (v1.11.0):

New input (with default empty for backward-compat):

```yaml
swim_day_boolean:
  name: Swim Day Locked Boolean (optional)
  description: >
    input_boolean that holds today's swim_day decision, set externally
    by a morning-lock automation at 05:55. If unset, blueprint falls
    back to live forecast evaluation (legacy v1.10.x behavior).
  default: ""
  selector:
    entity:
      domain: input_boolean
```

Variable computation:

```yaml
swimming_day: >
  {% if swim_day_boolean %}
    {{ is_state(swim_day_boolean, 'on') }}
  {% else %}
    {{ forecast_high >= min_swim_temp }}
  {% endif %}
```

NOT-A-SWIM-DAY branch condition (else clause inside the choose):

```yaml
{{ not swimming_day and pump_is_on and current_minutes < waterfall_start_minutes }}
```

## Consequences

**Positive:**
- Forecast updates mid-day no longer disrupt active pool days.
- Day-shape decision is auditable (`input_boolean.pool_swim_day_today` history shows the day's lock-in value).
- NOT-A-SWIM-DAY branch is now bounded to morning hours only — failure of Part 1 is contained.
- WATERFALL END remains the single source of truth for end-of-window equipment shutdown, simplifying the mental model.

**Negative:**
- Adds a new input_boolean and automation to the pool package — small ongoing maintenance cost.
- 05:55 lock window is slightly fragile if HA is restarting at exactly that moment. Acceptable: missed lock means the boolean retains yesterday's value, and the pool runs based on yesterday's swim_day decision until tomorrow. Worst case: one mismatched day.
- Backward-compatibility branch in `swimming_day` template adds two lines that are dead code once the new input is wired. Worth the safety margin during deploy.

**Neutral:**
- Existing NOT-A-SWIM-DAY behavior on actual non-swim days is preserved: morning lock returns False before 08:00, branch fires before 08:00, equipment stays off all day.

## Audit support

The auditor's D1 (`swim_day_consistency`) assertion would have FAILed against today's data because `swim_day_raw` took both 'Yes' and 'No' values. With this ADR shipped, swim_day_raw can still flip in the underlying sensor (it's recomputed from forecast), but the locked boolean is what the blueprint actually consumes. Add follow-on assertion D4 to the auditor: `pool_swim_day_today consistency` — the locked boolean should be constant from 05:55 to midnight.

## Migration

1. Add helper + automation to `packages/pool/pool_modes.yaml`.
2. Bump blueprint to v1.11.0.
3. Update `automations.yaml` Pool Automation entry: add `swim_day_boolean: input_boolean.pool_swim_day_today`.
4. Restart HA so the new input_boolean registers.
5. Manually set `input_boolean.pool_swim_day_today` to match today's `sensor.pool_swimming_day` value (one-time, since the morning automation won't fire until 05:55 tomorrow).
6. Tomorrow morning at 05:55, observe the automation fire and lock today's value.
7. Add D4 to auditor (follow-on, not blocking).
