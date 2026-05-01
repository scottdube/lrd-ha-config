# ADR-011: Pool service mode — pause equipment-control branches via lockout boolean

**Status:** Accepted (shipped in blueprint v1.10.0, 2026-05-02)
**Date:** 2026-05-02
**Decider:** Scott
**Related:** ADR-006 (pump flow tied to compressor activity), future ADR-013 (door switch as additional service-detection signal)

---

## Context

Pool service tech visits weekly (unpredictable day) to clean the filter and chlorinator. Sometimes she shuts down equipment to do this work. Two real safety problems with pre-v1.10.0 behavior:

1. **HA could re-energize equipment while disassembled.** Blueprint's PUMP START / WATERFALL ON branches don't know about service work in progress. If conditions for those branches were met during the service window, HA would attempt to start equipment that the tech might still have apart.

2. **Tech's workaround (cycling the breaker) wears the breaker.** 60A double-pole breakers handling pool pump motor inrush are not designed for routine weekly cycling. Pool tech raised this concern 2026-05-02 — she sees breakers fail prematurely from this pattern. Standard residential breakers are spec'd for ~10,000 mechanical operations on paper, but contact-arcing wear under motor load shortens lifespan well before that count, especially on the 60A class handling motor-start inrush.

Pre-v1.10.0 mitigations:
- v1.9.0 added an integration-health gate: when `pump_switch == 'unavailable'` (which happens when the breaker is off and the integration loses comms), MAIN POLL is skipped. This *does* respect physical lockout-tagout via breaker. But the breaker-cycling itself is the wear problem.

The tech doesn't change her workflow today — she **toggles the pump off via the Hayward control panel**, not via HA. That panel-toggle is the signal we want to capture.

## Decision

Add a **soft lockout via `input_boolean.pool_service_lockout`** that the blueprint checks in every equipment-control branch. The lockout is engaged automatically when external pump on/off transitions are detected (panel toggles), with no change to tech's existing workflow.

### Detection mechanism

State changes on `switch.omnilogic_pool_filter_pump` carry a Home Assistant context. When the change comes from HA-initiated actions (blueprint, UI, voice, automation), `context.user_id` and/or `context.parent_id` are populated. When the change comes from outside HA (the OmniLogic Local integration's coordinator polling and discovering the pump state changed at the controller), both fields are `None`. That's the fingerprint of an external action.

Two automations in `packages/pool/pool_modes.yaml`:

```yaml
# Engage on external OFF
trigger: state on→off
condition: context.user_id is none AND context.parent_id is none
action: input_boolean.turn_on pool_service_lockout

# Symmetric clear on external ON
trigger: state off→on
condition: context.user_id is none AND context.parent_id is none
action: input_boolean.turn_off pool_service_lockout
```

Plus a midnight auto-clear safety backstop and a mobile-notify "Resume Now" action button.

### Surgical scope of the lockout

Service mode is about pump/heater/waterfall, not unrelated functions. The lockout gates ONLY equipment-control branches:

| Branch | Gated? |
|---|---|
| PUMP START | Yes |
| WATERFALL ON | Yes |
| WATERFALL END (pump-off action) | Yes — valve close still fires (cleanup is safe) |
| NOT-A-SWIM-DAY (turn-everything-off) | Yes |
| HEATER+SPEED maintenance | Yes (skips entirely) |
| **POOL LIGHT ON (lux trigger)** | **No** — light still works during service |
| **POOL LIGHT ON (sunset trigger)** | **No** |
| **POOL LIGHT OFF (fixed time)** | **No** |
| MIDNIGHT RESET | No |

Pool light continues to work at dusk even during a service event. Service is about equipment, light is unrelated.

### Reset logic — symmetric with engage

When tech finishes and toggles pump back on via the panel, HA detects the external on (same context-fingerprint mechanism) and clears the lockout immediately. No Scott action required for the common case.

Three reset paths:
1. **External pump on detected** → clear immediately (most common).
2. **Manual "Resume Now" mobile notification action** → clear immediately (fallback).
3. **Midnight auto-clear** → safety backstop in case neither of the above happens.

## Consequences

### Positive

- **Tech's workflow unchanged.** She toggles the panel as she always has. HA detects automatically.
- **Breaker preserved.** No cycling for routine service work. Breaker reserved for actual disassembly LOTO (its design intent).
- **Pool light still works during service.** No collateral pause of unrelated functions.
- **Zero new hardware required.** Detection is software-only, leveraging existing HA context.
- **Future-compatible.** Door switch (planned ADR-013) and other detection signals can OR into the same lockout boolean.

### Negative

- **Depends on integration-coordinator updates.** If the OmniLogic Local integration's coordinator has high latency or misses the panel-toggle event, lockout engagement is delayed. The integration polls at single-digit-second cadence so this is usually <10s; rarely an issue.
- **External tools that toggle the pump (Hayward app, voice integrations) also engage the lockout.** Scott's wife or a voice assistant turning the pump off would trigger the lockout. Acceptable — the action looks like service either way; clearing it is one tap on the mobile push.
- **Doesn't catch tech opening the box without toggling the pump.** Service work that doesn't include pump-off (visual inspection, replacing a sensor) goes undetected. Door switch (future ADR-013) closes this gap.

### Open questions

1. **Does panel-toggle reliably arrive without HA context?** Empirical confirmation pending — the design assumes the integration's coordinator updates appear with `context.user_id is none and parent_id is none`. Logger v2 captures `pool_service_lockout` state, so the auditor can verify lockout engagement matches actual panel-toggle events over the next service window.
2. **Should mobile notify go to both Scott and (eventually) the tech?** Currently single-recipient. If tech ever gets HA Companion app installed for this house, she could get her own confirmation/dismissal flow. Out of scope for v1.

## Implementation summary

**Files:**
- `packages/pool/pool_modes.yaml` — input_boolean helper + 4 detection automations + mobile-notify action handler + midnight auto-clear
- `blueprints/automation/LRD/pool_automation/pool_automation.yaml` — v1.10.0 with `service_active` template variable + branch gates
- `automations.yaml` — Pool Automation alias updated to v1.10.0, new `service_lockout_boolean` input wired
- `pool/scripts/state_logger.py` — new `pool_service_lockout` column
- `pool/docs/data-schema-v2.md` — column documented

**Empirical validation pending:** first detection event after deployment will confirm the context-fingerprint mechanism. If it doesn't fire, fall back to the FilterState/FilterWhyOn enum-based detection (`omni_filter_state == WAITING_TURN_OFF_MANUAL` or `omni_why_on == MANUAL_ON`).
