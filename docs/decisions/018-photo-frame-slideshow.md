# ADR-018: Living room Fire TV photo-frame slideshow

**Status:** Accepted (deployed pending first-run verification)
**Date:** 2026-05-16
**Decider:** Scott
**Implementation:** `packages/photo-frame/photo_frame.yaml`
**Upstream source of truth:** `scottdube/photo-frame` repo at `ha/photo-frame-automations.yaml`

## Context

The living room Fire TV is idle most of the day. Photo-library work has produced a slideshow web page served from the LRD Mac Mini (`http://192.168.50.10:8000/slideshow`, behind a UDM Pro firewall rule allowing IoT VLAN → 192.168.50.10:8000). Fully Kiosk Browser (FKB, `de.ozerov.fully`) installed on the Fire TV renders that page full-screen with no chrome.

The HA piece needs to:

1. Start the slideshow each morning so the TV "becomes a photo frame" without manual effort.
2. Get out of the way when the user wants to watch TV — no auto-resume that fights the remote.
3. Auto-resume the slideshow if the TV is left idle on the launcher (typical pattern: someone presses Home but never goes to an app).
4. Power the TV off at night if the slideshow is still running — but never interrupt active viewing.

The TV is integrated via the Android Debug Bridge (`androidtv`) integration as `media_player.fire_tv_192_168_11_82` over IoT-VLAN ADB-over-TCP.

## Decision

Four time- and state-driven automations + one `input_datetime` helper, packaged together as `packages/photo-frame/photo_frame.yaml`. Policy parameters:

| Knob | Value | Rationale |
|---|---|---|
| Active window | **09:00 – 21:00** | Mirror typical waking hours at LRD; matches the "ambient" use case (not before coffee, not after winding down). |
| Morning wake | **09:00** | Same boundary as the active window; one trigger, one source of truth. |
| Idle-relaunch threshold | **10 min** continuous on `com.amazon.tv.launcher` | Long enough that someone walking past the TV and pressing Home accidentally doesn't get the slideshow yanked back instantly; short enough that genuinely-idle launcher state reverts to the frame within a coffee refill. |
| Post-exit cooldown | **2 h** since last FKB exit | Covers a typical viewing session (a movie, a couple of shows). Short enough that idle launcher *later* still reverts to the frame; long enough that pressing Home then opening Netflix doesn't trigger a relaunch while Netflix is loading. |
| Evening shutdown | **21:00**, only if FKB is foreground | Saves power if the TV was photo-framing all day; refuses to interrupt an active show. |

### Exit signal: Home-button → launcher state

User exit from the slideshow is detected by `media_player.fire_tv_192_168_11_82` `current_app` attribute transitioning *from* `de.ozerov.fully` (any destination). The Home button on the Fire TV remote is the natural way to leave FKB; it lands on `com.amazon.tv.launcher`. No FKB-side configuration or custom intent needed.

**Prerequisite:** FKB must not be configured as the Fire TV's home launcher. If it ever is, pressing Home re-enters FKB and the exit edge never fires. Verification step: with FKB foreground, press Home; expect to land on the Amazon launcher, not back in FKB.

### Cooldown via `input_datetime`, not blueprint state

`input_datetime.fire_tv_living_room_last_exit` stores the timestamp of the user's last exit. The relaunch automation gates on `(now() - last_exit) > 7200 s`. Template handles unknown/unavailable/null with a permissive fallback (treat as "cooldown expired") so the first relaunch after a HA restart isn't held off forever waiting for an exit that never happened.

### `androidtv.adb_command` vs Fully Kiosk integration

FKB has its own HA integration (`fully_kiosk`) over MQTT/REST that can launch the app. We use raw `androidtv.adb_command` (`am start -n de.ozerov.fully/de.ozerov.fully.MainActivity`) instead because the Fire TV is already wired up via Android Debug Bridge for state introspection (`current_app`), so adding the `fully_kiosk` integration would be a second dependency for what is, in net, one extra command path. Single integration = single failure mode.

### Package organization

One file: `packages/photo-frame/photo_frame.yaml` carries the helper + all four automations. Matches every other domain in this repo (`packages/pool/`, `packages/lanai/`, etc. are all subdirs containing one or more YAML files). Self-contained, trivially revertible.

## Consequences

### Positive

- Each policy knob is a literal in one file; tuning is a one-line edit.
- Manual override path is the Home button on the remote — no app, no dashboard, no voice command needed.
- The 21:00 shutdown is conservative (foreground-gated): a movie that runs past 21:00 finishes without HA interference.

### Negative / open

- **Time-based active window only.** Doesn't know about presence. Slideshow will start at 09:00 even if no one is home. Acceptable for now (Fire TV idle on a webpage is cheap); revisit if energy data shows otherwise once Vue Panel A circuits 13 (Garage Mini Split) / etc. land enough data to identify the living-room outlet draw.
- **No "stop for tonight" gesture.** If the user wants the TV completely off but the slideshow is foreground, they have to either wait until 21:00 or use the remote to power-off (and the next launcher-idle window between 09:00–21:00 will relaunch unless the cooldown is active). Not a real problem at the policy level; flag if it becomes one.
- **Cross-VLAN reliance.** FKB needs to reach 192.168.50.10:8000 from IoT VLAN. Firewall rule in `network-docs` is the load-bearing piece — if it's changed/removed, slideshow goes blank but the automations keep "succeeding" (FKB launches, just to a connection-refused page). Worth a follow-up template sensor that pings the slideshow URL and exposes status.

### Reversal cost

Low. Remove the `packages/photo-frame/` directory, restart HA, delete the helper from the registry. No external dependencies in other automations or scripts.

## Open follow-ups

- Verify FKB launch component (`de.ozerov.fully/de.ozerov.fully.MainActivity`) on the actual installed FKB version. If `am start` errors, run `adb shell dumpsys package de.ozerov.fully | grep -A1 -E "Activity|filter"` on the device.
- Confirm `androidtv.adb_command` service is registered in Dev Tools → Services after package load. (Known HA quirk: the service can disappear if the integration's only device is offline at HA start — GitHub home-assistant/core #125579. Fire TVs typically stay on the network when off, so this shouldn't bite, but worth confirming on the first 09:00 cold-start.)
- Once first 09:00 wake fires successfully, mark this ADR Implemented and move the in-flight section in `current-state.md` to Recently completed.
- Future extensions (per hand-off, not part of this ADR):
  - Per-TV library selection on the hub (Family / Kids / etc.) — needs the library/bucket model on the photo-frame hub, which doesn't exist yet.
  - Context-sensitive library switching (visitor presence → their album) — depends on per-TV libraries + HA presence triggers.
  - Motion-based wake — alternative to schedule-only wake; would replace or augment the 09:00 trigger with a lanai/living-room occupancy sensor.
