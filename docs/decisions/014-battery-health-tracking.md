# ADR-014: Battery health tracking — Battery Notes + logger v2 extension + auditor assertions

**Status:** Proposed
**Date:** 2026-05-02
**Decider:** Scott
**Related:** logger v2 (`pool/docs/logger-v2.md`), auditor (`pool/docs/auditor.md`)

---

## Context

The household has multiple battery-powered devices that wear over time and eventually need replacement. Today the visibility is binary: HA's default behavior is "device works" until "battery is critically low" — by which point the device is already misbehaving (long beep on the Kwikset 916 today at 20% is the catalyst for this ADR).

Today's battery-powered inventory:
- 2× Kwikset 916 deadbolts (front door, lanai)
- ZEN75 toilet fan (Z-Wave)
- WeatherFlow Tempest hub
- Future: Zooz ZSE41 800LR door sensor (when it arrives)
- Future: additional door/window sensors as the home expands

Today's gaps:
- No long-term battery decay history → can't compute decay rate baselines per device
- No way to distinguish "battery wearing normally" from "battery failing prematurely" until the device complains
- No predictive replacement scheduling — replacements happen reactively (lock starts beeping)
- No audit signal for accelerated drain (which usually indicates a different problem — Z-Wave mesh issue, mechanical resistance, increased wake cycles, etc.)

## Decision

Two-layer approach. Both layers complement each other; either alone is incomplete.

### Layer 1: Battery Notes (HACS) — operational view

Install [HA-Battery-Notes](https://github.com/andrew-codechimp/HA-Battery-Notes) HACS integration. Provides:

- Per-device "last replaced" date tracking (manually entered when battery swapped)
- Battery type lookup (matches device model to expected battery type from a community library)
- Days-remaining estimates based on current decline rate
- Low-battery and replacement-reminder notifications
- Dashboard view tile

Strengths: zero custom code, works day-1, sufficient for routine operations ("which batteries do I need to swap on the next Costco run?").

Limitations: simple linear extrapolation, no anomaly detection beyond threshold alerts, no historical trend visualization beyond what HA's recorder already gives.

### Layer 2: Logger v2 extension — analytics + anomaly detection

Extend `pool_state_log.csv` (or future `home_state_log.csv`) with one column per battery device:

- `battery_<device_name>_pct` — integer percentage from the device's `battery_level` sensor

These columns capture once per `/10` poll alongside everything else. Over 30+ days of data, this enables:

- **Decay rate computation per device.** Slope of battery % over time. E.g., "front-door Kwikset: 0.4%/day baseline" — once a baseline is established, deviations are noticeable.
- **Anomaly detection assertions in the auditor:**
  - **Sudden drop**: battery dropped >X% in 24h → cell failure or hardware issue. Mobile notify.
  - **Accelerated decay**: 7-day average decay > 1.5× the 30-day baseline → something changed (mesh routing, mechanical resistance, environmental, etc.). Mobile notify.
  - **End-of-life chemistry plateau**: battery held steady for weeks then suddenly drops → typical alkaline/lithium end-of-life signature. Replacement window opening.
- **Replacement prediction** with statistical confidence rather than vendor estimate. "At current decay rate, replacement needed in ~32 days ± 5 days."
- **Comparative analysis** across devices of the same type. If one Kwikset drains 2× faster than another, that's a Z-Wave mesh signal, not a battery quality signal.

### Layer interaction

Battery Notes is the human-facing ops view: "what do I need to do this weekend?"

Logger v2 + auditor is the data-driven engineering view: "what's wearing faster than expected and why?"

Both useful; neither replaces the other.

## Consequences

### Positive

- **Predictive maintenance instead of reactive.** Lock won't start beeping unannounced — replacement cycles get planned.
- **Anomaly detection.** Mesh routing problems, mechanical strain, increased wake cycles all show up as accelerated decay before the user-visible failure.
- **Cross-device baselines.** Once 30+ days of data exists, replacing batteries on a unit that should have lasted longer is a signal, not a coincidence.
- **Auditor framework reuse.** Same assertion infrastructure already designed for pool extends to battery health with no new tooling.
- **Long-term trending.** Years of data → eventually distinguish "this brand of battery wears faster" from "this device is harder on batteries" — informs purchase decisions.

### Negative

- **Adds N columns to the logger.** Not a real cost; CSV doesn't care about width within reason.
- **Requires manual "last replaced" entry in Battery Notes.** Scott has to remember to record when he swaps batteries. Workaround: add an automation that detects sudden battery jump (e.g., 20% → 95% in <1h) and prompts Scott to confirm replacement date via mobile notify.
- **Anomaly thresholds are baseline-dependent.** Need 30+ days of data per device before assertions become useful. First month is data-collection only.

### Open questions

1. **Should the auditor try to detect "battery just replaced" automatically?** Sudden jump from low% to high% with timestamp is a strong signal. Could auto-update Battery Notes' "last replaced" via service call. Easy automation; deferred until logger has data.
2. **Combine or separate from `pool_state_log.csv`?** Pool logger is already wide. Battery levels are household-scope, not pool-scope. Probably belongs in the planned `home_state_log.csv` rename (per logger v2 spec long-term direction). For now, just append to the existing pool log; rename later.
3. **Notification cadence.** Daily summaries? Threshold-only? Defer to implementation phase.

## Implementation plan

### Phase 1: Battery Notes (immediate, ~30 min)

1. HACS → integrations → search "Battery Notes" → install.
2. Restart HA.
3. Settings → Devices & Services → Battery Notes → auto-discovers battery devices.
4. For each device, set "last replaced" date (best guess if unknown).
5. Add Battery Notes dashboard card to a relevant view.

### Phase 2: Logger extension (alongside next pool logger work, ~1 hour)

1. Identify all entities matching `*_battery_level` or `*_battery` in HA registry.
2. Add columns to `state_logger.py` `COLUMNS` list using the standard pattern:
   ```
   {"name": "battery_front_door_pct", "source": "state",
    "entity": "sensor.front_door_battery_level"},
   ```
3. Update `data-schema-v2.md` with new column section.
4. Wait 30+ days for baseline data.

### Phase 3: Auditor assertions (after baseline data exists, ~2 hours)

1. Add assertion `B1: sudden_drop` — flag any 24h delta >X%.
2. Add assertion `B2: accelerated_decay` — flag 7-day rate > 1.5× 30-day rate.
3. Add assertion `B3: replacement_predicted` — informational, projects replacement date.
4. Mobile notify on B1 (high severity), B2 (medium), B3 (low/digest).

### Phase 4: Auto-detection of replacement (optional, after Phase 3)

1. Automation triggers on battery_level state change with delta >50% upward in <1h.
2. Notification: "Detected battery replaced on <device>. Confirm to update Battery Notes' last_replaced date."
3. User taps "Confirm" → service call updates Battery Notes.

## Cross-references

- `pool/scripts/state_logger.py` — extend with battery columns
- `pool/docs/data-schema-v2.md` — document new columns
- `pool/docs/auditor.md` — add B1/B2/B3 assertions
- `docs/device-inventory.md` — battery-powered devices list (needs review for completeness)
- `docs/current-state.md` — track install + commissioning
