# ADR-004: Waterfall control via valve domain (post OmniLogic Local 1.0.0b5)

**Status:** Accepted
**Date:** 2026-04
**Decider:** Scott
**Blueprint version that implemented this:** v1.8.0

## Context

The `cryptk/haomnilogic-local` integration changed the entity domain for valve-controlled equipment in beta `1.0.0b5`. Pool waterfalls (and similar valve-controlled features) migrated from `switch.*` to `valve.*`.

Before:
- `switch.omnilogic_pool_waterfall`
- Service calls: `switch.turn_on` / `switch.turn_off`

After:
- `valve.omnilogic_pool_waterfall`
- Service calls: `valve.open_valve` / `valve.close_valve`

This is a **domain change**, not a rename. Service names are different. A blanket "switch" → "valve" find/replace fails because `switch.turn_on` ≠ `valve.open_valve`.

## Decision

Migrate the blueprint to `valve.*` entities and `valve.open_valve` / `valve.close_valve` service calls. Delete the stale `switch.omnilogic_pool_waterfall` entity from the registry.

Implemented in **blueprint v1.8.0**.

## Consequences

### Positive
- Aligned with current OmniLogic Local API.
- Valve domain is semantically correct — a waterfall is opened/closed, not switched on/off.

### Negative
- **Backward incompatibility.** Anyone deploying blueprint v1.7 or earlier against integration 1.0.0b5+ will get errors. Blueprint header now requires `OmniLogic Local 1.0.0b5+`.
- **Stale entity registry entries** require manual cleanup. The `switch.omnilogic_pool_waterfall` orphan must be deleted in Settings → Devices & Services → entities, otherwise it persists as `unavailable`.

### Lessons / pattern
This is the second time the OmniLogic Local integration has produced orphan entities during a version bump (first time was the `_2` suffix ghost on a re-included device). Pattern to remember:

1. Beta integrations create stale entities on schema/domain changes.
2. Blueprint references must be migrated explicitly.
3. Audit `Settings → Devices & Services → integration → entities` for `unavailable` rows after every beta upgrade.
