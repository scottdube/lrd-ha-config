# ADR-034 — Replace MyQ with DIY ratgdo garage door control (cross-site)

**Status:** Proposed
**Date:** 2026-06-26
**Supersedes:** N/A
**Related:**
- SLN ADR-020 — site reference + SLN-first implementation notes
- `sln-ha-config/docs/reference/ratgdo-diy-build.md` — BOM, ESP32 wiring, power, flashing
- network-docs — garage Wi-Fi path backup-power question (surface as request; not owned here)

---

## TL;DR

Replace the MyQ cloud dependency on the garage door openers with locally-controlled
ratgdo modules running the ESPHome ratgdo firmware, reporting into each site's HA. Build
DIY from the open-source [Kaldek rat-ratgdo](https://github.com/Kaldek/rat-ratgdo) PCB
rather than buying commercial boards: at ~5 units the commercial path is ~$470 (5×
ratgdo32 disco @ $94), the DIY path is under $100 all-in, and the build is well within
existing fabrication capability. Power each unit from the opener's battery-backup
terminals via an LM2596 so the controller survives a mains outage. Implement at **SLN
first**, prove it on one unit, then roll the same build to LRD. **First opener confirmed
(2026-06-26):** LiftMaster 45DCBL5 / FCC HBW7356, yellow-button Security+ 2.0 rail-drive
head — fully supported, not a jackshaft, so the 8500 exclusion does not apply. Remaining
gate: verify the other units match and confirm battery-backup presence per unit.

## Context

The openers are currently dependent on Chamberlain's MyQ. MyQ closed third-party API
access (the change that drove the broader ratgdo migration wave), and the cloud
dependency means no reliable local control, no trustworthy real-time state in HA, and
exposure to whatever Chamberlain decides to do with the service next. This is the same
vendor-lock-in failure mode being engineered out elsewhere in the stack.

ratgdo solves it: it taps the opener's Security+ serial bus and is mostly *listening*, so
HA reflects true door state including manual and wall-button operations — strictly better
than MyQ ever reported. On yellow-button Security+ 2.0 openers it also exposes obstruction
status, opener light, lock, and motion. The "and more" beyond MyQ is everything HA
automation adds on top (door-left-open alerting, geofence/schedule auto-close,
arrival/departure logic).

Two implementation realities shaped this decision:

- **Scale.** There are ~5 openers across both sites. That turns a per-unit price
  difference into a material number.
- **Power on outage.** Both sites' openers have battery backup; both HA NUCs are on UPS.
  Losing door visibility/control precisely when the power is out would be the wrong
  outcome, so the controller should ride the opener's existing battery backup.

## Decision

**1. Adopt ratgdo + ESPHome as the garage-door control layer at both sites**, replacing
MyQ. Each site's modules report into that site's HA install (no cross-site federation,
consistent with ADR-029).

**2. Build DIY from the rat-ratgdo open-source PCB**, not commercial boards. Rationale:

| Factor | DIY rat-ratgdo | Commercial (ratgdo32 disco ×5) |
|---|---|---|
| Cost, 5 units | < $100 all-in | ~$470 ($94 each) |
| Capability (Security+ 2.0) | Full: state, obstruction, light, lock, motion | Same + laser vehicle presence, beeper |
| Build effort | Solder + fab PCB + flash | Plug + flash |
| Supply independence | Full (recreatable from gerbers) | Vendor-dependent |

The disco's extras (vehicle-presence laser, beeper) are not required for MyQ parity. The
DIY board's payoff — recreatable, vendor-independent hardware — is the same reason MyQ is
being dropped. The build is trivial at this skill level. **This is the cost-conscious,
control-first choice; revisit per-unit only if a specific opener proves incompatible.**

**3. Standardize on ESP32** (Wemos D1 Mini ESP32) rather than ESP8266. ESP8266 is
sufficient for basic 2.0 control, but ESP32 leaves headroom for added sensors later
(e.g., a vehicle-presence ToF if wanted) without a board respin, and gives BLE-proxy
optionality. Pins: TX GPIO16 / RX GPIO21 / Obstruction GPIO23; install via the ESPHome
v2.0 ESP32 D1 Mini path. Full detail in the build guide.

**4. Power from the opener battery-backup terminals via LM2596 set to 5.0 V.** Keeps the
controller alive on mains loss for as long as the opener battery holds. Accept the small
continuous battery-drain cost (estimated ~40-75 mA from a 12 V backup) over adding a
dedicated mini-UPS per opener.

**5. Sequence SLN first.** Prove the full build on one SLN unit end-to-end before
ordering/fabbing the remaining units and before touching LRD.

## Consequences

**Positive:**
- Local control and trustworthy real-time state in HA; MyQ cloud dependency removed.
- Hardware is recreatable from open gerbers — no second vendor lock-in.
- ~$370 saved versus the commercial path at this unit count.
- Battery-backup power keeps door telemetry/control alive through mains outages (subject
  to the network-path caveat below).
- Exceeds MyQ functionality once HA automations (left-open alerts, geofence close) are built.

**Negative:**
- Build + per-unit bring-up labor (acceptable, this is in-wheelhouse).
- Continuous load on each opener's backup battery slightly reduces door-cycle reserve
  during outages.
- HA control during an outage still depends on the garage Wi-Fi path (AP/switch) being on
  backup power — a network-docs dependency, not solved by this ADR.
- Per-opener compatibility risk (Security+ 2.0 confirmation; 8500-series jackshaft caveat).

**Neutral:**
- No change to existing automations; new entities slot into the existing `garage.yaml`
  dashboard at SLN.
- Firmware/OTA follows the established ESPHome workflow (MacBook flash → adopt → NUC
  ESPHome Builder for OTA).

## Implementation

SLN-first. Tracked in `sln-ha-config/docs/current-state.md`. Build procedure, BOM, wiring,
and flashing: `sln-ha-config/docs/reference/ratgdo-diy-build.md`.

1. Confirm opener models / Security+ 2.0 / 8500 caveat at SLN.
2. Fab one PCB (or perfboard), populate, flash one ESP32, prove end-to-end on one SLN opener.
3. On success: fab/populate the remaining units; roll out across SLN, then LRD.
4. Build HA automations for MyQ-parity-plus (door-left-open notify, geofence/schedule close).
5. When LRD units are built, add an LRD-side note referencing this ADR.

## Open questions

- ~~**8500/8500C jackshaft exclusion**~~ — resolved for the first unit (2026-06-26): it's a
  45DCBL5 / HBW7356 rail-drive head, yellow-button Security+ 2.0. Re-check only if another
  opener turns out to be a different form factor.
- **Do all ~5 openers match** (yellow learn button each)? Confirm per unit before a parts run.
- **Battery-backup presence + measured voltage per unit.** 2012-era units predate the 2019
  mandate; the 45DCBL5 board ID doesn't confirm a battery. Units without it get a USB supply
  and won't ride through an outage.
- **LRD openers confirmed: LiftMaster 87504-267MC** (Secure View belt drive, Security+ 2.0,
  battery backup, integrated camera) ×2. Belt drive → not a jackshaft, ratgdo-compatible; same
  wiring + battery-backup power as SLN. (Sanity-check the 87504 against ratgdo's supported list
  as the newest model.)
  **Camera is NOT leverageable.** ratgdo controls the door only; the integrated myQ camera is
  cloud-locked with no local RTSP/ONVIF and no HA path, with or without a myQ Video
  subscription (the sub only unlocks cloud recording in the myQ app, nothing toward HA). For
  local, subscription-free garage video, add a **separate ONVIF/RTSP camera** — UniFi Protect
  preferred (matches the existing stack / SLN Protect), Reolink/Amcrest as cheaper alts.
- **Garage Wi-Fi path on backup power?** Surface to network-docs. Resolution criterion:
  if true outage-time control matters, the garage AP + its switch path must be on backup.
- **Dedicated mini-UPS vs battery-backup tap** — revisit only if backup-battery drain
  during outages proves to shorten door-cycle reserve unacceptably.
