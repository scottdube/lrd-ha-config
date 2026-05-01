# ADR-012: Vacation mode — cross-cutting `input_boolean.vacation` pattern, applied to pool first

**Status:** Accepted (pool implementation shipped in blueprint v1.10.0, 2026-05-02)
**Date:** 2026-05-02
**Decider:** Scott
**Related:** ADR-011 (pool service lockout — uses similar input_boolean pattern); future cross-cutting application to lighting / HVAC / etc.

---

## Context

Multi-day household absence has fundamentally different ideal automation behavior than normal occupancy:

- **Pool**: no swimming → no heating, no waterfall. But still need filtration to prevent algae bloom. Pool-light timing has security value (deters break-ins) so probably keep.
- **HVAC**: setback temps, less aggressive cycling. Carrier presence-aware setback (planned, separate backlog item).
- **Lighting**: presence-based lighting becomes either off (no security need beyond exterior) or scheduled "lived-in" simulation (security through random patterns).
- **Welcome-home logic**: must NOT fire while away (e.g., if door sensor briefly trips during a service visit).
- **Notifications**: maybe quieter / batched while away.

A single cross-cutting `input_boolean.vacation` toggle that any automation can check against gives a unified "we're away" signal without each automation needing its own gate.

## Decision

Define `input_boolean.vacation` as a **household-level mode toggle** that any automation can read. First implementation: pool blueprint v1.10.0 switches from swim-day logic to filter-only logic.

### Toggle mechanism

Manual via dashboard / mobile / voice. Future enhancement: geofence-based or calendar-based auto-set, but that has false-positive risk that's worse than just remembering to flip it. For now, manual.

Helper definition lives in `packages/pool/pool_modes.yaml` (alongside `input_boolean.pool_service_lockout`). It's not pool-specific by name or scope — pool just happens to be the first consumer.

### Pool-specific behavior when vacation is ON

| Aspect | Normal mode | Vacation mode |
|---|---|---|
| Heater | On per swim_day logic | Off (forced via `heater_needed = false`) |
| Pump | Variable schedule, possibly 24h on swim days | Runs `min_filter_hours` per day, configurable start time |
| Waterfall | Open during waterfall window on swim days | Always closed |
| Pool light | Lux/sunset triggers + fixed off time | **Same** (security value) |
| Chlorinator | Normal schedule | **Same** (still need sanitation) |
| Filter window | Tied to waterfall window + heat-time math | Independent: `vacation_filter_start_time` + `min_filter_hours` |

Default vacation filter window: 10:00 start, runs `min_filter_hours` (default 8h) → ends at 18:00. Configurable via blueprint input.

### How it integrates with the existing branches

Rather than adding a parallel set of "vacation branches" to the inner choose, vacation mode is implemented by **forcing variables and gating branches**:

- `heater_needed` returns `false` when `vacation_mode` (so HEATER+SPEED auto-disables heater)
- `heater_actively_delivering` returns `false` when `vacation_mode` (so pump speed selects normal)
- `should_filter` (new variable) = `swimming_day OR vacation_mode` (filtration always happens in vacation, not gated on weather)
- PUMP START's condition switches between "heat-time math" and "vacation filter window" based on `vacation_mode`
- WATERFALL ON gated on `not vacation_mode` (no waterfall during vacation)
- NOT-A-SWIM-DAY gated to fire end-of-vacation-filter-window when in vacation mode

Net effect: existing branches continue to work, just with vacation-aware variables and conditions. No code duplication.

### Service lockout interaction (with ADR-011)

Service work can happen during vacation (the tech still comes weekly). Both gates apply independently:
- `service_active` ON → equipment branches pause (regardless of vacation)
- `vacation_mode` ON → filter-only logic (regardless of service)
- Both ON → service pause wins (equipment paused, vacation filter logic doesn't override)

## Consequences

### Positive

- **Single toggle for "we're away."** Other automations (welcome-home, lighting, HVAC setback when built) can read the same boolean. Consistent semantics across the system.
- **Pool stays sanitary.** Filtration runs daily even when away — no green pool surprise after a 2-week trip.
- **Energy savings while away.** No heating, no waterfall, pump runs only the filter window (~8h vs. 24h). At ~$0.136/kWh, saving ~16h × pump-power per day = noticeable on multi-week absences.
- **Pool light keeps security value.** Lux/sunset triggers continue to work. Pool deck is lit at night even when nobody's home.
- **Future-extensible.** Adding HVAC setback, lighting simulation, etc. becomes "check input_boolean.vacation in a new branch/automation," no infrastructure changes.

### Negative

- **Manual toggle = manual error.** Forget to set it, all the above benefits are lost. Forget to clear it on return, pool stays in vacation mode. Future enhancement: calendar integration or arrival/departure detection.
- **Vacation pool light still draws power.** Could be considered wasteful. If Scott wants to disable pool light in vacation, add a separate `vacation_pool_light_off` toggle (out of scope for v1.10.0).
- **Filter window is single-block.** Doesn't support split filtration (e.g., 4h morning + 4h evening). Out of scope unless real use case emerges.
- **Doesn't auto-bump filter hours during high heat.** Florida summer might benefit from longer filter time. Could add a heat-aware multiplier in a future revision.

### Open questions

1. **Should vacation auto-set from calendar entries (Google Calendar / iCloud)?** Convenient but failure modes: missed flights, extended trips. Defer until manual mode validates the abstraction.
2. **Should "leaving the house overnight" (e.g., one-night trip) count as vacation?** Probably no — overnight isn't enough for pool to need different behavior. Threshold should be 2+ days, but that's policy, not blueprint logic. Defer until concrete use case.
3. **Should chlorinator boost on rain still happen during vacation?** Currently yes (chlorinator behavior unchanged). Probably correct — rain still happens whether we're home or not, and pool still needs chemical balance. Confirmed yes for v1.10.0; revisit if it causes over-chlorination problems.
4. **Should vacation_filter run overnight to capture SECO TOU super off-peak rates?** Analyzed 2026-05-02:
   - Scott is currently on SECO tiered rate (~13.3¢/kWh effective). Time of day doesn't affect cost.
   - SECO offers optional TOU: on-peak 23.7¢, off-peak 9.7¢, super off-peak 7.7¢. Super off-peak window appears to be 12am–6am (per SECO EV charging program; full residential tariff not retrieved).
   - For pool vacation pump alone: ~2 kWh/day × 5.6¢ TOU savings = ~$3.30/month during vacation periods. Small.
   - Decision: keep `vacation_filter_start_time` default at 10:00 for the current tiered plan. If Scott ever switches to TOU, change to 00:00 or 01:00. The input is already configurable; no blueprint change required when the rate plan changes.
   - Cross-reference: a separate household-level analysis should weigh switching to TOU based on full load profile (HVAC pre-shifting, EV charging if added). Defer until logger v2 + (eventual) whole-home power monitoring give us the data to decide.

## Implementation summary

**Files:**
- `packages/pool/pool_modes.yaml` — `input_boolean.vacation` helper definition (alongside `pool_service_lockout`)
- `blueprints/automation/LRD/pool_automation/pool_automation.yaml` — v1.10.0 with `vacation_mode`, `should_filter`, vacation-filter-window variables; branch conditions updated to handle both modes
- `automations.yaml` — Pool Automation v1.10.0 wires `vacation_boolean: input_boolean.vacation`
- `pool/scripts/state_logger.py` — new `vacation_mode` column
- `pool/docs/data-schema-v2.md` — column documented

**Verification plan:**
- Toggle `input_boolean.vacation` manually, observe blueprint behavior over 24-48 hours.
- Verify: heater stays off, waterfall stays closed, pump runs vacation_filter_start → +min_filter_hours, pool light still works at dusk.
- Once empirically validated, document expected behavior in a brief operational note for "next time we travel" reference.
