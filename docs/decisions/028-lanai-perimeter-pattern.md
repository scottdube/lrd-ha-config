# ADR-028: Lanai perimeter pattern (and reusable notify shape)

- Status: Accepted
- Date: 2026-05-28
- Related: ADR-012 (cross-cutting `input_boolean.vacation`), the existing
  `Lanai Door Activated Lights with Motion Keep-Alive` blueprint instance.

## Context

Two new Z-Wave contact sensors went on the east and west lanai screen-room
doors — the two exterior egress points from the pool deck and yard into
the screened lanai. Scott wanted a "watch these doors, alert with picture,
bring the lanai lights to full bright, treat vacation differently" pattern,
with the new sensors hot before 2026-05-30 (8-month-ish summer departure).
The departure date falls inside the ADR-024 7-day pre-departure freeze
window; Scott explicitly opted to violate the freeze for this work because
the security value materially exceeds the deploy risk.

A handful of design questions only became real once the first incidents
fired on hardware. This ADR captures the decisions so they don't get
re-derived next time we add a perimeter sensor or wire up the front door
the same way.

## Activation window

**Decision**: at-home gate is local midnight → sunrise, not sunset →
sunrise. Vacation gate is anytime.

The first iteration used `sun.sun: below_horizon` as the at-home gate.
First night of live observation surfaced two problems:

1. **`sun.sun` state change lags geometric sunset.** HA's astral
   scheduler flips state on the calculated event, not on continuous
   elevation evaluation, and atmospheric-refraction conventions push the
   "horizon crossing" out to about elevation -0.83°. A 20:11 EDT test at
   elevation +0.29° looked dark to a human but read `above_horizon` to
   HA, so the condition was false by less than half a degree and the
   automation didn't fire. This is HA-canonical behavior, not a bug, but
   it surprises users who think "sun is down" and "below_horizon" are
   the same instant.
2. **Sunset → midnight is when legitimate lanai activity happens.** TV on
   the porch, hot tub, late guests, etc. Treating any sunset-to-midnight
   door open as a security event generates nuisance push notifications
   that train you to ignore the alert.

Tightening the at-home gate to `now().hour < 12 AND sun.sun =
below_horizon` floors at local midnight and ceilings at sunrise, both
tracked dynamically. Real "late night unauthorized entry" is the
remaining signal class. The hour gate is template-based (not a
time-range condition) so it composes cleanly with the sun state in a
single `and` block.

Vacation gate stays anytime — daytime opens during vacation matter (pool
service, deliveries, intrusion), and Scott isn't on the property to
generate false positives.

## `input_boolean.bed_time_active` is kept as no-op infrastructure

**Decision**: define and wire the latch, even though the perimeter no
longer reads it.

The first design used an `input_boolean.bed_time_active` latch (mirrored
from the existing `input_boolean.bed_time` pulse, cleared at sunrise) as
the at-home gate. The midnight-sunrise simplification dropped that
dependency. Rather than deleting the helper + its two latch/clear
automations, we keep them as cross-cutting infrastructure per the
ADR-012 philosophy (one flag, many consumers, defined once). Likely next
consumers: HVAC night setback, motion-suppression in master bedroom,
"don't announce on speakers after this time" gates.

## Cameras are named by mount, not view direction

**Decision**: document the camera-vs-door mapping inline in the variables
block where it bites.

The G5 Bullet Lanai East and G5 Bullet Lanai West cameras are named for
where they're physically mounted on the lanai roof. The east-mounted
camera looks west across the lanai (covering the West door). The
west-mounted camera looks east (covering the East door). The first
deploy assumed name = view direction and produced snapshots of empty
doorways behind the person; the swap was made same-night.

Both the lanai perimeter package and any future consumer of these
cameras for door-triggered snapshots needs the same swap. The comment
in `packages/lanai/exterior_perimeter.yaml` is the canonical source.

## Notification shape: split mobile + persistent for image in HA bell

**Decision**: invoke `notify.mobile_app_iphone_sd` and
`persistent_notification.create` directly, rather than calling
`notify.scott_and_ha`. The group still exists for simpler use cases.

The shared `notify.scott_and_ha` group fans the same payload to
`mobile_app_iphone_sd` and `notify.persistent_notification`. That works
for text-only alerts. For image attachments it doesn't: the
`notify.persistent_notification` service ignores `data.attachment`, so
the HA bell carried text but no image. Splitting the call lets each
target receive a payload tailored to what it can render:

- Mobile gets `attachment.url` (snapshot), `data.url` (default tap),
  `data.actions[]` (long-press menu), `data.push.interruption-level`,
  and the vacation-only `sound.critical` / `volume` block.
- Persistent gets the image embedded as markdown
  (`![snapshot]({{ snapshot_url }})`) in `message:`. HA's frontend
  renders that inline in the bell entry.

The two-call pattern is now used by the lanai perimeter and the front
door doorbell alert. When other notification flows need rich content,
they should mirror this shape.

## iOS Companion URL handling: action URIs go to system Safari

**Decision**: use external `https://` URLs (not `entityId:` scheme) for
both default tap and per-action URIs.

The HA Companion iOS docs list `entityId:<entity_id>` as a URL scheme
that opens the entity's more-info dialog in the app. It works as
documented when set as the notification's top-level `url:` field. It
**silently falls back to opening the app shell** when used in an
`actions[].uri` field — observed empirically on the current iOS
Companion build, and discussed in
[home-assistant/iOS issue #749](https://github.com/home-assistant/iOS/issues/749)
which notes that per-action URIs always launch in system Safari
regardless of the General → Open Links In preference.

Since per-action URIs always go to system Safari, an external `https://`
URL is the most reliable destination — Safari maintains a persistent
session for whatever site you land on. That makes the UniFi Protect
cloud URL strictly better than `entityId:` for the View Live action:
single behavior across vacation and at-home contexts, no Companion
setting required, works on cellular.

## UniFi Protect cloud URL for live view

**Decision**: link to
`https://unifi.ui.com/physical-security/devices/<camera-uuid>` rather
than the local UDM URL or the (undocumented) Protect iOS app scheme.

Three options were considered:

1. **Local UDM URL** (`https://192.168.0.1/protect/dashboard?camera=<id>`).
   Works on LRD WiFi. When Scott is at SLN or on cellular, `192.168.0.1`
   routes to the SLN UDM Pro — wrong device, won't load.
2. **UniFi Protect iOS app deep link** (`unifiprotect://...` or similar).
   Native app stays logged in, no auth ever. Ubiquiti doesn't publicly
   document the URL scheme; community-derived recipes (e.g. the
   "Figured out the URL Scheme for Protect deep linking" thread) live on
   JavaScript-rendered forum pages we couldn't fetch directly. Could be
   recovered later via the Shortcuts app or a browser session.
3. **UniFi cloud URL** (`https://unifi.ui.com/physical-security/devices/<id>`).
   Routes via Scott's UI account to whichever console the camera is on,
   works from any network. Opens the device detail page rather than a
   pure live-only view; live preview is embedded in that page along with
   alarms and device info. Reuses Safari's persistent unifi.ui.com
   session, no re-login.

(3) wins on portability and login-free reuse, with the only tradeoff
being that you land on the device page rather than a fullscreen live
tile. Ubiquiti doesn't expose a pure live-view URL today, so (3) is
also strictly what's available.

Camera UUIDs are stable per the integration and were pulled from the HA
device registry. The mapping (door-to-cloud-URL) lives in the variables
block of the perimeter automation, swap-aware per the camera-naming
note above.

## Existing interior-door automation interaction

**Decision**: the perimeter automation cancels
`timer.lanai_lights_timer` on every trip; it never restarts it. The
existing interior-door blueprint instance is unmodified.

`Lanai Door Activated Lights with Motion Keep-Alive` (automations.yaml
id 1775916297031) owns `timer.lanai_lights_timer` and runs the
interior-door pattern at 58% / 10 min. If a perimeter trip fires while
that timer is mid-run, the timer would expire and turn the lanai cans
off in the middle of the incident. Canceling it as the first action of
the perimeter trip prevents that race. The blueprint's own
`skip_if_lights_on: true` keeps it from re-firing at 58% while the
perimeter has lights at 100%.

The perimeter starts its own `timer.lanai_perimeter_incident` (10-min,
restart-on-retrigger) for the auto-off. The two timers are kept distinct
because they serve different concerns and have different durations
philosophically (interior is "lights for movement", perimeter is
"lights for incident response").

## Front door follow-on

The front door doorbell alert (automations.yaml id 1775854571098) was
extended to match the perimeter shape: 3s delayed snapshot from
`camera.g4_doorbell_pro_high_resolution_channel`, iOS push with
attachment + Protect URL + action buttons, persistent_notification with
image embedded as markdown. Trigger and 5-min suppression logic
unchanged. Same UniFi Protect cloud URL pattern, doorbell UUID
`6630eba101ffcb03e400a468`.

Activation differs by design: the front door has no time/sun gate.
Doorbell person/animal detection is itself the gate, and the existing
5-min `input_boolean.front_door_notification_suppression` window
(driven by physical front-door open events) is the entire false-positive
defense.

## Snapshot retention

`/config/www/snapshots/` is the shared snapshot directory for both
automations. A daily 03:30 launchd-equivalent (HA `shell_command` +
time-triggered automation, defined in `packages/snapshots/purge.yaml`)
purges files older than 30 days. Silent on a clean run; notifies via
`notify.scott_and_ha` with a count + first-five preview when files were
deleted, so unexpected growth or unexpected purges surface.

## Open follow-ups

- **Critical alerts permission.** The vacation branch sets `critical: 1`
  + `volume: 1.0` on the iOS push. iOS only honors that when Critical
  Alerts permission is granted in iOS Settings → Notifications → Home
  Assistant. Verify before 2026-05-30 departure.
- **Person-detection cross-check.** UniFi Protect exposes
  `binary_sensor.g5_bullet_lanai_<side>_person_detected`. A follow-up
  notification with "person confirmed" reduces false positives from
  wind / animals / pool service. Defer until we have data on
  false-positive rate over the summer.
- **Perimeter scope extension.** Other exterior egress (garage interior
  door, front door contact, anything else) deserves the same shape.
  Worth either parameterizing into a blueprint or fanning out via
  additional package files. The activation gate is the only piece
  likely to differ per door.
- **Protect iOS app deep link.** Optional polish if Safari session ever
  proves annoying during vacation. Recover the URL scheme via Shortcuts
  app or browser-driven inspection of the community threads.
