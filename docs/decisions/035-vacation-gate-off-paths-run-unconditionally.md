# LRD ADR-035 — Vacation gating: OFF/safety paths run unconditionally

**Status:** Accepted (authored 2026-07-07; pending NUC deploy)
**Date:** 2026-07-07
**Decider:** Scott
**Context repo:** home-assistant (LRD; canonical for cross-cutting pattern)
**Related:** ADR-012 (vacation cross-cutting pattern), SLN ADR-018
(sunset-lights dawn misfire — separate root cause, same debugging session).

## Context

On 2026-07-07 the LRD main-living cans (`light.living_wall_dimmer_switch`,
`light.kit_cans_wall_dimmer_switch`, `light.wall_dimmer_switch_under_cab`)
were found to have been ON continuously since 2026-06-30 20:38 EDT — six
days — while the house was in vacation mode (`input_boolean.vacation = on`,
both persons `not_home`).

Root cause: in `packages/lighting/main_living_areas.yaml`, the vacation +
presence gate sat at the **whole-automation** level of *Main Living: Lux
Cycling*, which bundled two opposite behaviors under one condition block:

- ON branch — `lux_low (<10000, 5 min) → lights on`
- OFF branch — `lux_high (>13000, 5 min) → lights off`

Gating the automation on `vacation off + person home` was aimed at the ON
behavior but disabled the OFF branch as collateral. With every auto-off
path gated out (cycling-off, dusk-hold) and the remaining ones inapplicable
while away (Everyone-Leaves already fired; Bed-Time needs a manual toggle),
nothing could clear a stray-on light. Something turned the cans on the
evening of 06/30 (most likely a physical paddle press during a service
visit — no vacation-gated automation could have) and they burned until
manually cleared.

## Decision

**Gate comfort/ON behaviors on presence/vacation; let safety/OFF behaviors
run unconditionally** (or gated only on their own safety-relevant
conditions).

This is already the ADR-012 principle applied to the pool: in vacation the
*comfort* behaviors change (heater off, waterfall closed) but the
*maintenance* behaviors keep running unconditionally (chlorinator "Same",
filtration "always happens in vacation, not gated on weather"). The
lighting bright-daylight off-sweep is the lighting equivalent of the
chlorinator and should likewise never be gated off.

### Implementation (`packages/lighting/main_living_areas.yaml`)

1. **Extract the OFF branch** out of *Main Living: Lux Cycling* into its own
   automation **`main_living_bright_daylight_off`** ("Main Living:
   Bright-Daylight Off"): trigger `lux > 13000 for 5 min`, **no conditions**,
   turn the three cans off. Runs whether home or away.
   - Home behavior is unchanged (bright-day off was already the accepted
     "option a" behavior).
   - *Main Living: Lux Cycling* keeps only the ON (`lux_low`) and 09:00
     `wake` branches, still gated on `vacation off + person home`.

2. **Add a night gap-filler** **`main_living_vacation_stray_light_sweep`**
   ("Main Living: Vacation Stray-Light Sweep"): `time_pattern every 30 min`,
   condition `vacation on` AND any of the three cans on, turn them off.
   Bright-Daylight Off only fires above 13000 lux, so a light switched on
   after dark while away would otherwise wait until the next bright period;
   this closes that gap. Chosen over an event-driven watchdog (which would
   shut a service tech's light off instantly) — the 30-min sweep is the
   gentler janitor. Safe because the sunset presence-simulation targets a
   different fixture set (porch, lamp post, plug dimmers), never these cans.

## Consequences

- Stray main-living lights are now swept even in vacation — within ~5 min
  during bright daylight, within ≤30 min after dark.
- No change to occupied-home behavior.
- Worth auditing other automations that adopt the ADR-012 vacation guard
  for the same ON/OFF conflation. The `input_boolean.vacation` guard
  backlog note is refined accordingly: apply the guard to ON/comfort paths
  only.
- Does not cover fixtures outside the three main-living cans (e.g.
  `light.lanai_u7_outdoor_led`, on since 06/20) — those need their own
  handling if desired.

## Files

- `packages/lighting/main_living_areas.yaml` (OFF branch split out + two new
  automations, 2026-07-07)
- `docs/decisions/035-vacation-gate-off-paths-run-unconditionally.md` (this)
