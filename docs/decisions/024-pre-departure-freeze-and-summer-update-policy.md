# ADR-024: Pre-departure freeze + summer update policy

**Date:** 2026-05-25
**Status:** Accepted
**Related:** ADR-012 (vacation mode), ADR-019 (OmniLogic recovery playbook), `docs/current-state.md`

## Context

Scott departs LRD on 2026-05-30 for the summer, returning approximately mid-October (3rd week, ~2026-10-17). Roughly 5 months unattended at LRD with the HA installation managing critical pool automation (Blueprint v1.12.0, ADR-022 PUMP RECONCILE), voice satellites, energy monitoring, photo frame, Z-Wave fleet, and the in-shakedown ESP32-C6 pool float.

Remote access during the absence is via Nabu Casa subscription (ADR documented in `integrations/nabu-casa.md`) plus Studio Code Server for repository edits. Physical access to the NUC, MSP controller, AP, switches, and individual ESP devices is essentially impossible without a $700+ flight.

The question is: how to handle the steady stream of HA Core, HA OS, ESPHome, and HACS integration updates that will accumulate over the summer, given that:

- An untested update applied remotely could break automation that controls the physical pool equipment (pump, heater, waterfall) and create real maintenance or safety issues
- Recovery from a broken update is technically possible via SCS terminal + Nabu Casa but slow and stressful from 1500 miles away
- Skipping ALL updates for 5 months accumulates significant version drift and exposes the system to known-patched vulnerabilities

Neither extreme (apply everything immediately, defer everything until home) is right. The system needs a discipline that balances stability with security.

## Decision

Two-phase policy:

### Phase 1 — Pre-departure freeze (final 7 days before any extended absence)

In the 7 days leading up to departure, **do not apply any update** unless an explicit CVE / security fix is documented in the release notes AND the affected component is in active use. Treat the pre-departure window as a freeze where the goal is "leave with a known-working system," even at the cost of a known-pending update sitting unapplied.

Rationale: 7 days is not enough time to recover from a broken update before leaving. The risk of leaving with a broken system far exceeds the risk of leaving with a 7-day-stale system.

### Phase 2 — Summer selective-update discipline (during the absence)

Weekly check (Monday morning EDT) of HA's Update screen and release notes. Apply updates by tier:

| Update type | Action |
|---|---|
| HA Core **patch** (e.g. 2026.5.4 → 2026.5.5) | Apply ~1 week after release. Wait for community to surface regressions. |
| HA Core **minor** (e.g. 2026.5.x → 2026.6.x) | **Defer until home.** Break only for documented CVE. |
| HA OS update | Apply ~1 week after release. Usually low-risk Alpine + supervisor patches. |
| ESPHome add-on update | **Defer until home.** Updating invalidates cached SDK builds — every ESP device needs a flash on next OTA, too much risk away from home. |
| HACS integration update | **Defer until home** unless explicitly security-flagged. |
| Any update with explicit **CVE** or **Security** label | Apply within a day or two of release, regardless of other rules. Verify backup completed before applying. |

Always require automatic backup before update — already enabled in HA Core update flow; verify before leaving. Confirm the backup is being made to a location that survives a failed update (NUC local + ideally pushed to Mac mini or Backblaze).

Have a rollback procedure documented and practiced before leaving:

```
Settings → System → Backups → select pre-update backup → Restore
```

If the rollback path itself breaks, fall back to SCS terminal: `ha core stop && ha core check-config && ha core start`, then if that fails, restore from backup via supervisor CLI.

### Exceptions that warrant breaking the policy

Apply immediately, regardless of tier rules:

- Documented CVE affecting Nabu Casa remote access (would lock out remote management)
- Documented bug in ESPHome that specifically affects deep_sleep on ESP32-C6 (would break the deployed float)
- HA Core security-flagged bug in a component you actually use externally (e.g. an HTTP endpoint with auth bypass)

Apply nothing for:

- Feature additions, however appealing
- Minor version jumps that aren't security-driven
- New integrations / add-ons that look interesting
- Cosmetic UI changes
- Anything you'd "like to try" — that's an October project

### Watch-items / process

A weekly automated review task summarizes pending updates with recommended actions per the tier policy. Scott reviews and applies/defers manually. The task does not auto-apply anything — apply remains a human decision because the consequence of a broken update is real.

If a recovery scenario emerges (HA unreachable, automation failing, device offline), DO NOT update as a triage step. Update only after the immediate problem is resolved and the system is stable.

## Consequences

The system will fall behind on minor-version updates over the summer. That's intentional. The "Updates available" badge on the HA UI will be a normal sight, not an emergency.

ESPHome will probably accumulate 2-4 versions of skipped updates. That's fine — the pool float and voice satellites work; we'll catch up in October.

Security posture is acceptable: the LRD network is behind UDM Pro with no inbound port forwards (other than what Nabu Casa tunnels, which is the encrypted Cloud relay). Most ESP devices live entirely on the IoT VLAN with no external attack surface. The actual remote-attack risk over the summer is dominated by Nabu Casa's tunneling code, which is what we prioritize via the CVE exception clause.

## Pattern reuse

This policy applies to any future extended absence (snowbird transitions, extended trips, etc.). The 7-day pre-freeze + weekly selective-update pattern is reusable. Document any departure timeline and return date in `docs/current-state.md` so the policy has a clear end date.
