# OmniLogic Local — Midnight Error Burst Investigation

**Date:** 2026-05-01
**Trigger:** Pool waterfall ran before scheduled 08:00 start. While diagnosing, identified pattern of `Failed to update data from OmniLogic` errors in HA log.
**Source data:** `home-assistant_2026-05-01T11-15-10.036Z.log` — 14-hour span 2026-04-30 17:00 EDT through 2026-05-01 07:14 EDT.

---

## Headline finding

The ethernet run is reliable. The midnight burst is **not** a network issue.

- **Evening (17:00–23:59):** 0 errors / 7 hours. Zero packet loss, zero coordinator failures.
- **Overnight (00:00–07:14):** 28 errors. **18 of those** clustered between **00:27:11 and 01:00:11** (a 33-minute burst).
- **No correlation** with WiFi, DHCP, gateway, or other integration errors during the burst window. Cloud OmniLogic integration polls successfully every 30 seconds throughout — so internet is up and the Hayward cloud relay is fine.

This means the local UDP coordinator is failing at a time when nothing else on the network is failing. The fault localizes to **either the controller's UDP listener or the local integration's interaction with it.**

---

## Raw numbers

### Hourly distribution

| Hour (EDT) | Errors |
|---|---|
| 17–23 (evening) | 0 |
| 00 | **18** |
| 01 | 1 |
| 02 | 1 |
| 03 | 1 |
| 04 | 2 |
| 05 | 1 |
| 06 | 3 |
| 07 | 1 |

### Timing pattern

- Error gaps: min 20s, median 140s, max 3990s (66 min), avg 894s.
- 4 back-to-back failures within 60s of each other — all inside the 00:27–01:00 burst.
- Burst window: 00:27:11 → 01:00:11 (29 minutes of clustered failures).
- After 01:00:11, gaps balloon to 60+ min between errors. Single isolated failures, not clusters.

### Co-occurrence

- FlightRadar24 403s and a single pychromecast SmartTV connect failure are present but uncorrelated with the OmniLogic burst (different times, different timeframes).
- No DHCP/WiFi/gateway/DNS log lines in the burst window.

---

## Hypothesis: controller-side scheduled job at midnight

The pattern fits a **controller-internal scheduled task running near midnight** that monopolizes the OmniLogic's network/processing stack temporarily. Candidates (none confirmed yet — need vendor-side info):

- Internal log rotation / event-history housekeeping.
- Scheduled cloud-sync job pushing daily telemetry to Hayward's servers (separate channel from local UDP, but could starve the local listener if the controller is single-threaded).
- Firmware/config self-check.
- A heartbeat or NTP-driven housekeeping that fires at the controller's local midnight.

**What's consistent with this hypothesis:**
- Burst is bounded (~30 min), not unbounded.
- Cloud integration is fine in the same window — points to controller workload, not network.
- The 06:00 mini-spike (3 errors) could be a second daily housekeeping job — needs more nights of data to confirm.

**What we'd need to confirm:**
- Multiple consecutive nights showing the same 00:27–01:00 burst pattern.
- Hayward documentation or community reports of midnight controller behavior.
- Hayward firmware changelog around scheduled tasks.

---

## What this is NOT

- **Not the ethernet run.** Evening 7 hours show zero errors. Network is solid.
- **Not the WiFi packet loss issue from earlier April.** That was random distribution, ~30-40% loss continuously. This is structurally different — bounded burst at a specific time of day, perfect reliability outside that window.
- **Not directly causing the early-morning waterfall issue** as a root cause — but the 00:30 burst did mask the blueprint's PUMP START call (entities went `unavailable` for that 30s service-call window, see `home-assistant_2026-05-01...log` lines 1157–1159). The pump command landed despite the warning, so the burst made the symptom visible but didn't change the outcome.

---

## Recommended next steps

1. **Collect more nights of log data.** Pull HA logs for 2026-05-02 through 2026-05-04. Confirm the 00:27–01:00 burst recurs nightly. If it does → confirmed pattern, controller-side. If it doesn't → one-off, ignore.
2. **Check Hayward / `cryptk/haomnilogic-local` GitHub issues for "midnight" or "scheduled" reliability reports.** If others see the same pattern, there's likely a known cause and possibly a fix.
3. **Tune integration retry/timeout** in `cryptk/haomnilogic-local`. If the integration retries aggressively during the burst, that may amplify load on the controller. A backoff during repeated failures might mask the burst entirely.
4. **Time-of-day filter on alerts.** Until resolved, the existing pool API watchdog (per `automations.yaml:483-505`) should suppress notifications for failures within the 00:27–01:00 window — those are now expected noise, not actionable.
5. **Capture controller firmware version.** Document in `integrations/omnilogic.md`. If a firmware update changes the burst pattern, we want a baseline.

---

## Decision pending

Whether the burst warrants:
- (a) Just-accept-and-ignore (suppression), once confirmed pattern.
- (b) Coordinate with Hayward / `cryptk` maintainer for fix.
- (c) Move blueprint poll cadence away from `:00`/`:10`/`:20`/`:30` so the 10-min poll doesn't land squarely inside the burst (currently 00:30 lands in the middle of it).

Lean (a) + (c) — small ops cost, no dependency on vendor.
