# LRD ADR-033 — Sunset lights on lux (primary) with sun fallback — PROPOSED, NOT APPLIED

**Status:** Proposed — documented only, **not implemented** (Scott's call,
2026-06-24). LRD's "Lights on at Sunset" automation remains on its `sun`
`sunset` trigger. This ADR captures the design so it can be applied later
as a drop-in.
**Date:** 2026-06-24
**Context repo:** lrd-ha-config
**Related:** SLN ADR-018 (same pattern, **implemented** at SLN on
`sln_sunset_lights`).

## Context

SLN moved its sunset cascade from the `sun sunset` event to a lux-primary
trigger (SLN ADR-018) so the lights follow actual darkness and come on
earlier on overcast evenings. LRD's exterior evening lights — "Lights on
at Sunset", `automations.yaml` id `1775132170002` (front wall, garage
outdoor, lamp post, smart-plug dimmers, funky lamp) — currently use the
`sun sunset` event and could adopt the same pattern.

Scott opted to **document the change for LRD but not apply it yet** — LRD's
exterior lighting is working and stable, and there's no pressing reason to
change it. This ADR exists so the work is a known, ready-to-execute change
rather than a re-derivation later.

## Threshold — measured

Read LRD station illuminance (`sensor.st_00184974_illuminance`) 15 min
before sunset on recent clear evenings (lux):

| Evening | LRD T-15 |
|---|---|
| 06/18 | 1616 |
| 06/20 | 1605 |
| 06/21 | 1470 |
| 06/22 | 2097 |
| 06/23 | 2091 |
| 06/19 | 406 (cloud at sunset — excluded) |

Clear-evening T-15 clusters ~1500–2100 lx (clearest day 2097) — higher
than SLN's ~700–1300 lx because LRD is ~16° lower latitude (sun higher at
a given offset from sunset), has clearer Gulf-side skies, and less tree
horizon. Proposed threshold: **2000 lx** (≈ clearest-day value, so lights
never come on late on a clear evening; earlier when cloudy).

## Proposed change (when applied)

Replace the single `sun sunset` trigger on automation `1775132170002`
with:

- **Primary:** `numeric_state sensor.st_00184974_illuminance below: 2000
  for: 00:02:00`, gated by `sun.sun` elevation `< 10°` (blocks a dark
  midday storm from tripping the exterior cascade; the dusk crossing at
  sun ~+4° still passes).
- **Fallback:** `sun sunset` event, allowed **only** when
  `sensor.st_00184974_illuminance` is `unavailable`/`unknown`.

Use trigger ids (`lux` / `sun_fallback`) and an `or` of two `and` blocks
to route the two paths, exactly as SLN ADR-018's
`packages/lighting/sunset_lights.yaml`. Actions/brightness levels
unchanged.

## Consequences (when applied)

- Clear evenings: lights ~15 min before sunset; overcast: earlier.
- New dependency on the LRD Tempest, mitigated by the sun fallback.
- HA-restart-after-dusk gap (same as SLN): numeric_state crossing won't
  re-fire; acceptable, add a `homeassistant` start re-eval if needed.

## To apply later

Edit automation id `1775132170002` in `automations.yaml` per the above,
config-check, reload automations, then flip this ADR to **Accepted**.
No live change is made by this document.
