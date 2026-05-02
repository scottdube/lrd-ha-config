# ADR-016: Integration-recovery debounce for service-lockout detection

**Status:** Accepted
**Date:** 2026-05-02
**Decider:** Scott
**Implementation:** v1.10.2 — `packages/pool/pool_modes.yaml`
**Supersedes / amends:** ADR-011 (pool service mode) — adds a new condition to both detection automations

---

## Context

ADR-011 introduced two detection automations in `packages/pool/pool_modes.yaml` that watch `switch.omnilogic_pool_filter_pump` for state transitions with no HA context (`user_id` and `parent_id` both null), interpreting those as panel-toggle events from the pool tech and engaging/clearing `input_boolean.pool_service_lockout` accordingly.

This worked correctly for genuine panel-toggle events. It does not work correctly across HA restarts or any event that disconnects the OmniLogic Local integration from the Hayward controller.

### What happened on 2026-05-02

Deploy of v1.10.1 required a HA reload. The OmniLogic Local integration briefly went unavailable. During the disconnect, the controller continued running its own internal logic. When the integration recovered ~78 seconds later, HA observed a state different from what it had cached — pump off (was on), waterfall closed (was open), heater on (was off).

The `pool_detect_external_pump_off` automation fired on the on→off transition. From its perspective, the conditions were satisfied:
- `from: "on" to: "off"` matched
- No HA context (the change came through the integration's coordinator update, not from any blueprint action)
- `last_triggered > 30s` ago
- Lockout was off

Result: lockout engaged, false-positive mobile push fired, blueprint paused. The pool was held in service-pause until the controller cycled the pump back on at 10:30:11, which fired `pool_detect_external_pump_on` and cleared the lockout symmetrically. Net consequence was two extraneous notifications and ~3 minutes of inappropriately blocked equipment branches (waterfall stayed closed past the WATERFALL ON window until the next /10 poll after the lockout cleared).

### Root cause

The detection logic conflates two distinct scenarios:

| Scenario | What actually happened | What detection sees | Should engage lockout? |
|---|---|---|---|
| Tech taps panel | Pump off via Hayward panel during normal operation | on → off, no HA context | Yes |
| Integration recovery | Controller cycled state during HA disconnect; HA observes the new state on reconnect | on → off, no HA context | **No** |

The detection automation can't distinguish them because the surface signal (transition with no HA context) is identical in both cases.

### What `from_state.state` checks alone don't fix

A cleaner state guard (`trigger.from_state.state == 'on'`) was considered. It would have rejected only the specific case where the transition was strictly `unavailable → off` (skipping the intermediate 'on' the trigger seems to bridge across). But:

1. The exact behavior of HA's state platform across `unavailable` transitions is integration- and version-dependent. Not safe to rely on.
2. Even if it worked for pump on/off, it doesn't handle the broader class of controller-side phantom changes (heater on, waterfall close, etc.) that could trigger other automations or affect the blueprint's MAIN POLL evaluation.

A time-based debounce after recovery handles all of these uniformly.

---

## Decision

Add `input_boolean.pool_integration_recovering`, a watcher automation that flips it on for 5 minutes after every integration recovery, and a gate condition on both detection automations:

```yaml
- condition: state
  entity_id: input_boolean.pool_integration_recovering
  state: "off"
```

The watcher automation triggers on `state` of `switch.omnilogic_pool_filter_pump` with `from: "unavailable"` (any new state). It uses `mode: restart` so a flapping integration extends the window rather than allowing detection to fire mid-flap.

### Why 5 minutes

Empirical: the 2026-05-02 incident's full controller-side reconciliation cycle ran 10:25:27 (unavailable) through 10:30:11 (final pump-on), about 4m 44s. 5 min covers that with margin. Increase if longer cycles are observed; decrease (probably to 2 min) once we have logger v2 phase 1.5 captures of several recovery events to confirm the typical duration.

### Why watch only the pump entity for recovery

All OmniLogic Local entities share the integration's coordinator and go unavailable as a group. The pump entity is the most-tracked, so its recovery is a faithful proxy for the integration's overall recovery. Watching multiple entities would produce the same trigger sooner than `mode: restart` could update the boolean, leading to conflict.

---

## Trade-offs

**Suppressed:** any genuine tech action that occurs within 5 minutes of a HA restart or integration recovery would NOT engage automatic lockout. Tech would need to use the manual `input_boolean.pool_service_lockout` toggle on the dashboard.

Likelihood of this scenario: very low. Tech actions during HA restart windows are rare. If it happens, the failure mode is non-destructive (no lockout means blueprint continues operating; tech is physically present at the pool and would notice if equipment cycled unexpectedly).

**Not suppressed:** every other tech action (>5 min after any integration recovery) engages lockout exactly as before.

**Not addressed in this ADR:** the blueprint's MAIN POLL is not gated on `pool_integration_recovering`. If a controller-side state change during the recovery window puts the system in a state that satisfies a blueprint branch (e.g., NOT-A-SWIM-DAY's `not swimming_day and pump_is_on`), the blueprint could still react to phantom data. Risk is low because the blueprint's branches mostly require positive conditions (e.g., pump_is_on, swimming_day=true, current_minutes >= window) that won't trigger on transient controller drift, but worth empirically verifying via logger v2 phase 1.5.

If MAIN POLL gating turns out to be needed, add the same condition to the existing integration-health gate at line 614 of `pool_automation.yaml`. Defer this decision until we have data.

---

## Verification

After deploy:

1. Toggle `switch.omnilogic_pool_filter_pump` off via Hayward panel during normal operation. Confirm lockout engages and mobile push arrives within 30 sec.
2. Restart HA. Confirm `input_boolean.pool_integration_recovering` flips on within ~10 sec of the pump entity recovering from unavailable. Confirm it auto-clears 5 minutes later.
3. Observe a HA restart that causes controller-side state changes (similar to today's incident). Confirm NO mobile push for "Pool Service Lockout Engaged" appears during the recovery window.

---

## Sources

- `packages/pool/pool_modes.yaml` lines 33–87 (the two detection automations being modified)
- 2026-05-02 incident timeline:
  - Hayward app activity log: pump off 10:26:45, waterfall closed 10:26:45, heater on 10:26:45, pump on 10:30:11
  - HA logbook: all events showing no automation attribution (controller-side coordinator updates)
  - `sensor.pool_forecast_high` last_changed 10:24:41 with value 88.0 (rules out forecast-fallback as a cause; swimming_day stayed true throughout)
- ADR-011 (pool service mode) — being amended by this ADR
