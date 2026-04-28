# ADR-001: OmniLogic Local for control, Cloud for monitoring only

**Status:** Accepted
**Date:** 2026-04 (approximate — backfilled)
**Decider:** Scott

## Context

The Hayward OmniLogic pool controller has multiple integration paths in Home Assistant:

1. **Built-in HA integration** (cloud) — basic, polls Hayward's servers
2. **`djtimca/haomnilogic` HACS** (cloud) — more features, more equipment supported, but still cloud-dependent
3. **`cryptk/haomnilogic-local` HACS** (local UDP) — direct communication with the controller on the LAN

Cloud integrations are subject to Hayward server availability and impose latency on every action. Local integration is faster, works during internet outages, and has no third-party dependency.

However, the local integration is on beta (`1.0.0b7` at time of writing) and doesn't expose every sensor — notably ORP, salt level, and pH come through cleanly on cloud but are missing or unreliable on local.

## Decision

Run **both integrations side by side**:

- **Local (`cryptk/haomnilogic-local`)** is the source of truth for all *control actions* (pump, heater, waterfall, chlorinator, light) and for water/air temperature sensors.
- **Cloud (`djtimca/haomnilogic`)** is retained for *monitoring only* — ORP, salt, pH. No control actions go through cloud.

The blueprint (`pool_automation.yaml`) explicitly uses local entities for all `service:` calls. Cloud entities feed dashboards and notifications only.

## Consequences

### Positive
- Pool automation continues to work during internet outages.
- Faster response on commands — UDP local vs cloud round-trip.
- ORP/salt/pH data preserved.
- Beta integration testing happens against a controlled blast radius.

### Negative
- Two integrations to maintain and update.
- Naming convention split: cloud uses `switch.pool_pool_filter_pump` style, local uses `switch.omnilogic_pool_filter_pump` style. Easy to confuse.
- Beta integration occasionally hits issues (Pydantic warnings, valve domain migrations, fragment timeouts) — track via GitHub issues.

### Cleanup needed periodically
- When local integration replaces an entity (e.g., switch→valve domain change in 1.0.0b5+), audit blueprint references and delete stale entities from registry.
