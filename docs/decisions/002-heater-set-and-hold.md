# ADR-002: Heater set-and-hold; heat pump owns cycling, HA owns pump speed

**Status:** Accepted
**Date:** 2026-04
**Decider:** Scott
**Blueprint version that implemented this:** v1.7.0

## Context

Earlier blueprint versions tried to manage heater on/off cycling directly in HA — turning the heater on when temperature dropped below target and off when it reached target. This created two problems:

1. **Missed heater starts due to pump-start timing.** The pump had to be running for at least N seconds before the heater could safely engage (for flow). Race conditions in HA polling caused the heater to be commanded "on" before the pump had spooled up, resulting in either an error from the controller or a missed start that wasn't retried.
2. **Redundant cycling.** The HeatPro heat pump has its own thermostat with hysteresis. Layering HA's logic on top of the heat pump's logic produced inconsistent behavior — sometimes HA would override the heat pump's natural cycle.

## Decision

Treat the **heat pump as the temperature controller.** It already has a thermostat, hysteresis, and flow-safety logic.

HA's role narrows to:
- **Set heater state once per swim day:** ON if today is a swim day, OFF if not.
- **Set pump speed based on heater intent:** `heater_pump_speed` (77%) when heater is on / needed, `normal_pump_speed` (55%) otherwise.

The heat pump cycles itself based on water temperature. HA does not poll for "should heater be on right now?" decisions.

## Consequences

### Positive
- No more missed heater starts from pump timing race conditions.
- Heat pump cycles smoothly per its own thermostat — no conflicting commands.
- Simpler blueprint logic. Fewer states to track. Fewer traces.
- HA enforces heater state every 10 minutes regardless — drift-resistant.

### Negative
- **Setpoint lives on the heat pump, not in HA.** To change target temperature, you have to walk to the unit and press buttons, not edit a number helper. Acceptable trade-off for simplicity.
- **Loses some flexibility.** If you wanted to do something clever like "preheat aggressively before guests arrive," HA can't directly drive that. Workaround: temporarily change pump speed up while heat pump still gates the heater.

### Implementation note
This decision deprecated the `heater_idle` trigger that v1.2 added. v1.7+ no longer needs it — heat pump handles the case where heater stops on its own.
