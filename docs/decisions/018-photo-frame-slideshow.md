# ADR-018: Photo-frame slideshow (multi-TV)

**Status:** Extended 2026-05-16 (same day, third revision) — bedroom Hisense Google TV added as a dev/test surface alongside the living room Fire TV. See "Addition 2026-05-16: bedroom Google TV (dev/test surface)" at the end. Prior: Revised 2026-05-16 — original 4-automation + helper design simplified to script-as-primitive + 2 thin time triggers (see "Revision 2026-05-16" section). The original sections below are preserved for history.

**Date:** 2026-05-16 (original) / Revised 2026-05-16 / Extended 2026-05-16 (bedroom added)
**Decider:** Scott
**Implementation:** `packages/photo-frame/photo_frame.yaml`
**Upstream source of truth:** `scottdube/photo-frame` repo at `ha/photo-frame-automations.yaml` *(bedroom script propagated upstream same day per 2026-05-16 hand-off; the upstream's original 4-automation + helper structure for the living room remains drifted vs. this file's simplified design)*

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

---

## Revision 2026-05-16

### Why the change

The original design assumed a real-world scenario where the Fire TV would sit on `com.amazon.tv.launcher` for 10+ continuous minutes — long enough that an automatic relaunch into FKB was useful, but recent enough to a manual exit that a 2 h cooldown was needed to keep the slideshow from fighting the user. After deploying the design and walking the empirical test plan, that scenario turned out to be too thin to justify the machinery:

- In practice the living room TV is either showing something (an app foreground, FKB, Netflix) or off. The launcher-idle state is a *transient* state someone passes through while navigating, not a *steady* state the device sits in.
- Most Fire TVs auto-sleep after 20 min of inactivity by default. The launcher-idle window self-terminates well before the slideshow relaunch math even matters in many cases.
- The state-attribute `for: "00:10:00"` trigger is fragile against Amazon's screensaver / ad-rotation behavior — `current_app` can flip mid-window to a non-launcher app id, resetting the timer, even if the user isn't actively using the TV.

The original design's action chain (power-on + ADB launch) was empirically verified to work. The trigger/condition machinery around it was solving a problem that wasn't really there.

### Revised decision

Strip the package to three primitives:

| Primitive | Role |
|---|---|
| **`script.photo_frame_start`** | Reusable action: power on Fire TV, wait 10 s for boot, ADB-launch FKB. Callable from automations, dashboards, Alexa routines (via HA Cloud Smart Home), or any HA service call. |
| **`automation.photo_frame_morning_wake`** | One-line wrapper. At 09:00 daily, call `script.photo_frame_start`. Same effect as the original morning wake but now the action lives in a reusable place. |
| **`automation.photo_frame_end_of_day_shutdown`** | At **23:00** (moved from 21:00 per Scott's call — gives the slideshow a longer evening run while you're around), power Fire TV off only if FKB is foreground. Foreground-gate preserved from original. |

Removed: `automation.photo_frame_track_user_exit`, `automation.photo_frame_relaunch_after_idle`, `input_datetime.fire_tv_living_room_last_exit`. No external references existed; clean removal.

### Why script-as-primitive

The same action sequence is needed from at least three eventual entry points:

1. The 09:00 schedule (handled by the morning-wake automation).
2. An on-demand HA dashboard button (a Lovelace tile firing `script.photo_frame_start`). **Deployed 2026-05-16** on the LRD-Test dashboard in the living room area. Interim placement; will migrate during the planned dashboard revamp.
3. Voice via an Echo device, routed through HA Cloud's Alexa Smart Home skill. `script.photo_frame_start` exposed to Alexa with friendly name "Photo Frame" → "Alexa, turn on photo frame" works from any Echo in the house. Not yet deployed; defer unless the dashboard button proves insufficient.

The Fire TV remote's mic button is NOT a viable entry point: Fire TV's Alexa is content-search-biased, routes "open Fully Kiosk Browser" to Prime Video catalog search instead of the installed app. Confirmed empirically 2026-05-16.

A script as the reusable primitive means each entry point is a one-call invocation rather than a copy-paste of the action sequence.

### Time-window simplification

Original window: 09:00–21:00. Revised: 09:00 wake, 23:00 shutdown. The 21:00 → 23:00 move is Scott's preference for "while there" — the slideshow is welcome later in the evening when winding down. There is no longer an active "relaunch window" because relaunch is gone, so the 09:00–21:00 range was structurally meaningless under the new design.

### Consequences

Positive: dramatically simpler. Three entities (script + 2 automations) instead of five (helper + 4 automations). No state-attribute `for:` trigger to debug against Amazon's idle quirks. Same wake + shutdown behavior; on-demand starts via dashboard / Echo cover the cases the relaunch automation was attempting to.

Negative / open: no automatic recovery if the slideshow gets exited mid-day and the user doesn't manually restart it. Acceptable given that the original behavior (auto-relaunch under conditions) was either rarely useful or actively unwanted in most exit scenarios.

Reversal cost: very low. The script's action body is exactly the original wake action — reinstating the relaunch automation later would just call the script with a different trigger + conditions.

### Migration notes

- `input_datetime.fire_tv_living_room_last_exit` registry entry: YAML-defined helpers disappear on the next HA restart after removal from YAML. A full `ha core restart` (not just `automation.reload`) is needed for clean entity-registry cleanup. Reload alone leaves the old entity behind as orphaned.
- `automation.photo_frame_end_of_window_shutdown` → renamed `automation.photo_frame_end_of_day_shutdown`. Entity ID change. No external references to update in this repo (verified via grep).
- Upstream `scottdube/photo-frame` `ha/photo-frame-automations.yaml` is now drifted from the deployed implementation. Propagate this simplification upstream when ready, or accept the drift and treat this file as the live source of truth.

### Dashboard button YAML (preserved for future re-add)

Dashboards are in storage mode (no Lovelace YAML in `lrd-ha-config`), so the button itself isn't version-controlled. If the LRD-Test dashboard ever loses the card, re-add via Edit Dashboard → "+ Add Card" → "Manual" with one of:

Built-in button card:

```yaml
type: button
entity: script.photo_frame_start
name: Photo Frame
icon: mdi:image-frame
show_state: false
tap_action:
  action: perform-action
  perform_action: script.photo_frame_start
```

Mushroom template card (depends on `lovelace-mushroom` HACS being present):

```yaml
type: custom:mushroom-template-card
primary: Photo Frame
secondary: Tap to start
icon: mdi:image-frame
icon_color: indigo
tap_action:
  action: perform-action
  perform_action: script.photo_frame_start
```

---

## Addition 2026-05-16: bedroom Google TV (dev/test surface)

### Why

A second TV — Hisense Google TV in the bedroom, HA entity `media_player.android_tv_192_168_11_108` — came online with FKB installed (via `adb install`) and verified rendering against the same `http://192.168.50.10:8000/slideshow` URL the living room TV uses. The bedroom TV is intentionally a **dev/test surface**, not a second production slideshow:

- Slideshow development (changes to `slideshow.html`, new transition behaviors, new library views) needs verification on a second platform — Chrome on Google TV vs Silk on Fire TV — to catch platform-specific rendering issues before they hit the living room.
- The bedroom TV is also useful when the living room TV is monopolized for normal viewing (Mary watching a show) and Scott still wants to exercise the slideshow stack.
- The bedroom isn't meant to be an always-on family slideshow space, so the morning-wake / end-of-day-shutdown pattern doesn't apply.

### Decision

Add **only** a sibling start script — `script.photo_frame_start_bedroom` — targeting the bedroom entity. Same action chain as `script.photo_frame_start` with the entity ID swapped: `media_player.turn_on`, 10 s delay, `androidtv.adb_command "am start -n de.ozerov.fully/de.ozerov.fully.MainActivity"`. The FKB activity name is identical on both Fire TV and Google TV — empirically verified.

**Not added (intentional):**

- No `photo_frame_morning_wake_bedroom` automation. Bedroom is manual-start-only.
- No `photo_frame_end_of_day_shutdown_bedroom` automation. Same reason.
- No script generalization (single script with a `fields:` target parameter). With two TVs the duplication is trivial; the generalization lift isn't justified yet. **Revisit when a third TV lands** — see open follow-ups.

For symmetry and to match what was already in use on the live HA instance, both scripts use the short `Photo Frame: <Room>` alias pattern:

- `script.photo_frame_start` → alias `Photo Frame: Living Room`
- `script.photo_frame_start_bedroom` → alias `Photo Frame: Bedroom`

Service names are unchanged so existing dashboard button and morning-wake automation references don't break. Both scripts also carry parallel `description:` blocks in the YAML so the package file is the source of truth for their UI metadata (previously the deployed living-room script had a friendlier alias and a description that lived only on the NUC and never made it back to git — that drift is now closed).

### Bedroom dashboard button (storage-mode dashboard, manual re-add YAML)

Dashboards are in storage mode (no Lovelace YAML in this repo), same situation as the living room button. Preserved here for future re-add. Place adjacent to the living room button on the LRD-Test dashboard.

Mushroom template card (matches the living room button's style):

```yaml
type: custom:mushroom-template-card
primary: Start bedroom slideshow
secondary: Hisense Google TV
icon: mdi:image-multiple
icon_color: blue
tap_action:
  action: perform-action
  perform_action: script.photo_frame_start_bedroom
```

Built-in button card alternative (no HACS dependency):

```yaml
type: button
entity: script.photo_frame_start_bedroom
name: Bedroom Photo Frame
icon: mdi:image-multiple
show_state: false
tap_action:
  action: perform-action
  perform_action: script.photo_frame_start_bedroom
```

### Verification after deploy

1. `script.reload` service call (or HA restart) so the new script is picked up.
2. Developer Tools → Services → confirm `script.photo_frame_start_bedroom` is selectable.
3. Tap the new dashboard button on LRD-Test → bedroom TV should power on (or stay on if already on), wait ~10 s, launch FKB; photos cycle.

### Consequences

Positive: trivially small change (~12 lines of YAML); same proven action chain; symmetric naming; second platform now exercised, which reduces the risk of slideshow regressions reaching the production living room TV unnoticed.

Negative / open: a third TV would push duplication past the worthwhile threshold. The follow-up below tracks when generalization becomes the right move.

Reversal cost: trivially low. Delete the script block and the dashboard button.

### Open follow-ups (specific to this addition)

- **Generalize the start script when a 3rd TV is added.** Refactor `photo_frame_start` into a single script that takes a target entity parameter (HA scripts support `fields`). Living room + bedroom can stay duplicated for two TVs.
- **If bedroom becomes a production slideshow surface** (i.e. an always-on family display, not a dev/test surface), copy the living room's `photo_frame_morning_wake` + `photo_frame_end_of_day_shutdown` automations with the entity ID swapped. ~5 min of work — don't preemptively add the schedule.
- **Per-TV library selection** (e.g. living room shows "Family", bedroom shows "Travel" when manually started) is blocked on the photo-frame hub's library/bucket model. Hub-side roadmap item; nothing to do on the HA side until the `?library=` query parameter exists on the hub.
