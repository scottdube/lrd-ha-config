# ADR-022: PUMP RECONCILE — claim a running pump whose start time is unknown to the blueprint

**Date:** 2026-05-23
**Status:** Accepted
**Related:** ADR-006 (actively-heating vs enabled), ADR-011 (pool service mode), ADR-012 (vacation mode), ADR-017 (sticky swim_day)

## Context

On 2026-05-22, the recent-state audit (`pool/scripts/audit_recent.py`) fired a `[schedule] Pump ON during scheduled off-window for 170 min (threshold 30)` alert against the morning 05:00-08:00 EDT window. Investigation showed the pump had run continuously since at least 13:50 the prior day (~22 h), with `local_filter_why_on = "Manual On"` and a real 411-445 W power draw the whole time, briefly 650 W from 02:52-03:42 (consistent with heater compressor cycling).

Timeline of how the pump got stuck on:

- Earlier in the day: pool service work in progress. Blueprint disabled. Pump driven by Hayward MSP local schedule for soak.
- Mid-afternoon: soak complete. Hayward schedules turned off. Blueprint re-enabled. Pump was still on at the moment of handover.
- Blueprint polls at /10 minutes: PUMP START branch evaluated `not pump_is_on AND current_minutes >= pump_should_start_minutes AND ...` — `not pump_is_on` was False (pump on), so PUMP START did not fire. `input_datetime.pool_pump_actual_start` was never written.
- Throughout the rest of the day: `hours_pumped_today` template (lines 636-644) returned 0 because `pool_pump_actual_start` was still at the midnight-reset sentinel (`1970-01-01 00:00:00`). `filtration_complete` (line 645-646) was therefore False.
- 20:00:01: WATERFALL END branch (lines 825-841) fired. It closed the waterfall (unconditional). Its inline pump-off gate evaluated `not heater_actively_delivering AND filtration_complete AND not service_active` — `filtration_complete` was False, gate failed, sequence short-circuited, pump stayed on.
- Overnight: HEATER AND PUMP SPEED MAINTENANCE branch (lines 900-933) continued polling and adjusting pump speed based on `heater_actively_delivering`. No path to turn the pump off existed.
- Next morning: audit fired ~08:15 (per launchd schedule), found 170 min of off-window pump-on in the 3 h window.

Root cause: the blueprint maintains no reconciliation for pump runtime accumulated under non-blueprint control. PUMP START is the only branch that records the run's start time, and PUMP START is gated by `not pump_is_on`. When the blueprint takes over a running pump, the runtime accumulator is permanently stuck at zero for that day. Downstream, every gate that depends on `filtration_complete` fails silently.

This is a structural gap in the day-shape model. The blueprint is event-driven (poll fires, transition branches evaluate) but lacks a state-reconciliation step for the case where its internal model disagrees with physical reality at the moment of (re-)engagement.

## Decision

Add a new PUMP RECONCILE branch as the FIRST item in the inner choose of MAIN POLL. Fires when the pump is on AND the blueprint's start-time helper is at the midnight-reset sentinel (or unknown/unavailable) AND service lockout is off. Action: set the helper to the pump switch's `last_changed` attribute (clamped to `<= now()`), falling back to `now()` if `last_changed` is not usable.

```yaml
- conditions:
    - condition: template
      value_template: >
        {% set start = states('input_datetime.pool_pump_actual_start') %}
        {{ pump_is_on
           and not service_active
           and (start in ['unknown', 'unavailable', '']
                or start.startswith('1970')) }}
  sequence:
    - action: input_datetime.set_datetime
      target:
        entity_id: input_datetime.pool_pump_actual_start
      data:
        datetime: >
          {% set st = states[pump_switch] %}
          {% if st is not none and st.last_changed is not none
                and as_local(st.last_changed) <= now() %}
            {{ as_local(st.last_changed).strftime('%Y-%m-%d %H:%M:%S') }}
          {% else %}
            {{ now().strftime('%Y-%m-%d %H:%M:%S') }}
          {% endif %}
```

Three design choices warrant explicit discussion.

**Placement: FIRST in choose.** The inner choose is mutually-exclusive — only the first branch whose condition is true fires that poll. If PUMP RECONCILE were placed after WATERFALL END, the 20:00 poll on a buggy day would still fail (WATERFALL END runs first with stale `filtration_complete=False`, pump stays on, PUMP RECONCILE never gets to run that poll). Placing it first means WATERFALL END is deferred one 10-min poll on the rare reconciliation cycle — waterfall closes at 20:10 instead of 20:00 on that one day. Acceptable for a once-per-handover edge case. PUMP START and NOT-A-SWIM-DAY are mutex by construction (PUMP START requires `not pump_is_on`, NOT-A-SWIM-DAY requires `not swimming_day`, neither overlaps with the reconcile condition).

**Backdate to `last_changed`, not `now()`.** Two variants were considered:

1. Conservative — set `actual_start = now()`. Simple, always correct in the "blueprint takes over a freshly-started pump" sense, but undercounts when the pump has been running for hours under non-blueprint control. In the 2026-05-22 scenario, reconciling at, say, 14:00 with `now()` would yield `hours_pumped_today = 6` at 20:00 with `min_filter_hours = 6`. Filtration_complete just barely satisfied if min is 6, fails if min is 8 (default for vacation_filter). Behavior depends on reconciliation timing relative to 20:00 boundary.

2. Backdate — set `actual_start = pump_switch.last_changed`. Accurate when `last_changed` reflects the real off→on transition. In the 2026-05-22 verification, `last_changed = 2026-05-22 19:38:46` (pump's actual on-transition the prior evening), yielding `hours_pumped_today ≈ 16.5` at noon today — well above any reasonable `min_filter_hours`, gate passes at 20:00 trivially.

Backdate chosen because:
- It accurately reflects the physical situation. `filtration_complete` is meant to be a model of "has this water been filtered enough today" — physical runtime is the better signal than blueprint-managed runtime.
- The `<= now()` clamp protects against clock skew producing absurd future timestamps.
- The fallback to `now()` covers the case where `states[pump_switch].last_changed` evaluates to None (entity missing, integration startup gap).
- Cross-day backdate (`last_changed` from yesterday or earlier) is correct in this context: if the pump has been continuously on across midnight, we want filtration accounting to reflect that, not to reset at midnight and pretend the day started with the pump off.

**Use `states[entity_id]` bracket notation.** HA Jinja supports `states[entity_id]` for dynamic State-object lookup (returns the State object, not the state string). No precedent existed in this repo, so the syntax was sanity-checked via the template editor before deploy. Verified working in HA 2026.x. The verbose alternative (`states.switch | selectattr('entity_id', 'eq', pump_switch) | first`) was the planned fallback if bracket notation failed, but proved unnecessary.

## Implementation

**Blueprint changes** (`blueprints/automation/LRD/pool_automation/pool_automation.yaml`, v1.12.0): single new branch added as first item in the inner choose of MAIN POLL. Header changelog block added. No new inputs, no helper changes. Existing `input_datetime.pool_pump_actual_start` and existing `pump_switch` blueprint variable both reused as-is.

**Deploy:** standard MacBook-first workflow — edit + commit + push on MacBook, git pull on NUC /config, `automation.reload` via `curl -X POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/core/api/services/automation/reload` from SCS terminal. No HA core restart needed — `automation.reload` re-reads blueprints referenced by reloaded automations.

**Verification:** the bug state (pump on, `pool_pump_actual_start = 1970-01-01 00:00:00`) persists at the moment of reload. The first /10 poll after reload should write a real timestamp to the helper. Confirmed 2026-05-23: helper transitioned from `1970-01-01 00:00:00` to `2026-05-22 19:38:46` (the pump's actual `last_changed`) on the first post-reload poll.

## Consequences

**Positive:**

- Closes the 2026-05-22 regression class: blueprint can no longer get stuck with a 1970-sentinel start time while the pump is physically running.
- Reconciliation uses physical runtime (`last_changed`), so `filtration_complete` reflects what's actually happened to the water, not just what the blueprint has been managing.
- Safe across the midnight_reset cycle: if the pump is still on at 00:01 when actual_start gets zeroed, PUMP RECONCILE catches it again on the next 10-min poll and rebackdates.
- No new helpers, no new inputs, no new automations — single localized branch in the existing blueprint.

**Negative:**

- One 10-min poll delay at the boundary case where PUMP RECONCILE fires the same poll WATERFALL END would have. Waterfall closes at 20:10 instead of 20:00 on that one reconciliation cycle. Acceptable.
- Adds a small dependency on `states[entity_id]` bracket notation behavior. If a future HA version regresses this, the fallback to `now()` activates silently — reconciliation still happens, just less accurately. The repo's lint or template-test layer doesn't currently catch this kind of silent-fallback drift.
- Reconciliation runs every poll (cheap template eval) on top of existing branches. Negligible.

**Neutral:**

- Service lockout is respected (`not service_active` gate). If a tech is mid-work and the pump comes on under their control, PUMP RECONCILE doesn't claim it. The branch is purposely non-disruptive to the service workflow established in ADR-011.
- The recent-state audit (`pool/scripts/audit_recent.py`) is unchanged by this ADR. The audit still flags pump-on during scheduled off-window. The 2026-05-22 alert was correct — the audit caught a real failure. ADR-022 fixes the underlying blueprint behavior; the audit retains its independent watchdog role.

## Alternatives considered

**Add an overnight pump-stop branch.** Trigger at 22:00 or 00:01, turn off pump unconditionally if it's on (with safety gates for service_active, heater_actively_delivering). Would have caught the 2026-05-22 case as a backstop. Rejected as the primary fix because it hides the gap — the blueprint can still think the pump has been running 0 hours when it's actually been running 16. Filtration accounting remains wrong, just less visibly. Could be added later as defense-in-depth on top of PUMP RECONCILE if a similar regression slips through.

**Move pool_pump_actual_start updates out of PUMP START/WATERFALL ON, into a state-trigger automation.** Watch the pump entity transitioning `off → on` and always set actual_start = `now()` at that moment, regardless of who turned it on. Rejected because it moves reconciliation logic out of the blueprint into a separate file, splitting the day-shape model across two surfaces. The blueprint already has the state-reconciliation responsibility — PUMP RECONCILE keeps it there.

**Remove the `filtration_complete` gate from WATERFALL END.** Simplest possible fix — at 20:00, close waterfall AND turn off pump, regardless of filtration target. Rejected because the gate exists for a reason: if filtration target isn't met on a hot/dirty day, the pump SHOULD keep running past 20:00 until the target is met (the third case enumerated in the PUMP START hotfix comment block, lines 727-728). Removing the gate breaks that intentional behavior. PUMP RECONCILE fixes the bug without compromising the design.

## Audit support

The recent-state audit (`pool/scripts/audit_recent.py`) caught this regression as written — its hardcoded 08:30-20:00 off-window check fired on the morning 05:00-08:00 sample. No audit change required for detection. A related ADR-022 follow-on (separate change, same session): the schedule check is now skipped when `input_boolean.vacation` is on (or when CLI flag `--skip-schedule-check` is passed), so the audit doesn't false-positive against the blueprint's filter-only window during absences. See pool/scripts/audit_recent.py docstring for the updated semantics.

## Migration

1. Bump blueprint to v1.12.0 (this ADR).
2. Push and reload — `automation.reload` is sufficient, no HA core restart needed.
3. If the bug state is currently active, verify by checking `input_datetime.pool_pump_actual_start` before and after the next /10 poll boundary — should transition from 1970 to a real timestamp.
4. No data migration. No helper changes. No automations.yaml changes (blueprint input wiring unchanged).
