# ADR-030: Alerting posture — management-by-exception with negative-space monitoring

**Status:** Accepted
**Date:** 2026-06-11
**Decider:** Scott
**Related:** ADR-011 (pool service mode), ADR-016 (integration-recovery debounce), ADR-013 (water-temp fallback — and the "door switch as service signal" hook first noted in ADR-011), ADR-021 (Z-Wave node health monitoring), the pool auditor (`pool/scripts/auditor.py`, `pool/docs/auditor.md`). Supersedes the implicit "notify on confirmation" posture baked into the early pool automations.

---

## Context

The monitoring stack started as **confirmation monitoring**: notify on every event so we could watch the system work and build trust that it did what we thought it would. That was the right call for a young, unproven setup — the lockout engaged/cleared pushes, the swim-day-lock push, and the pool auditor's per-night posture were all built to say "yes, the thing fired."

The stack has matured. Confirmations are now noise, and worse, confirmation monitoring has a structural blind spot that bit us directly:

**The 12-day auditor silence (2026-05-29 → 2026-06-10).** The overnight pool auditor stopped pushing results after its 05-29 run. The root cause was a `set -euo pipefail` interaction — `auditor.py` exits 1 whenever an audit FAILs, which aborted `audit_yesterday.sh` before its commit/push step (see the auditor push-bug thread). But the deeper lesson is the one that matters here: **a FAIL-push system is confirmation monitoring wearing an exception costume.** When it stopped, the absence of a FAIL was indistinguishable from "everything passed." Nothing was wrong on the surface precisely because nothing could surface. The pool was effectively unmonitored for 12 days and no signal said so.

Separately, the health watchers (`pool/health_watcher`) have already evolved past confirmation monitoring — "pump-on but no power," "flow loss with pump on," "salt out of band," "controller unreachable," "MSP IP drift," "cloud salt feed stale," "blueprint + schedule conflict." Every one fires on the **presence** of a bad signal. That is the mature posture for one half of "exception."

What is missing is the other half: **the absence of an expected good event.** "The pump was supposed to circulate N minutes and didn't." "The waterfall was commanded open and never moved." "It's a swim day and the pump never started." "The auditor was supposed to push a result and didn't." Non-events are silent by nature, which is exactly what makes them the valuable and the hard class.

## Decision

Adopt **management-by-exception** as the system-wide alerting posture, with negative-space (expected-but-absent) monitoring as a first-class, mandatory leg. This is a cross-cutting principle and applies to all monitoring surfaces — pool, Z-Wave health (ADR-021), energy, the auditor itself — not just the pool.

### The three-bucket notification taxonomy

Every notification source classifies into exactly one bucket, and the bucket dictates the channel:

| Bucket | Meaning | Channel |
|---|---|---|
| **Confirmation** | It did what we expected | Dashboard / log only — **no push** |
| **Unexpected happened** | Reality diverged from intent (bad state is present) | **Push** |
| **Expected didn't happen** | A commanded/scheduled event did not occur by its deadline | **Push** |

### Negative-space monitoring requires two things deviation alerts do not

1. **An explicitly encoded expectation** — *what* should happen and *by when*. A deviation alert reacts to a bad value that is sitting right there; a negative-space alert has nothing to react to, so the expectation and its deadline must be written down as the thing being checked.
2. **A timer/heartbeat that fires on the deadline passing** with nothing observed.

### The heartbeat rule: monitor the monitor

Any monitor whose value is in catching absence **must itself have a heartbeat**, or the silent-failure problem just relocates one level up — which is precisely what the 12-day auditor silence was. Concretely: the auditor gets a liveness check ("no fresh audit result landed by the daily deadline → alert") that is independent of the auditor's own success/failure path.

### Reclassification of current surfaces

- **Pool auditor** → its FAIL findings stay as push (unexpected happened), but it gains (a) a heartbeat per the rule above, and (b) the negative-space "expected didn't happen" checks via the commanded-vs-actual rework and the pump-timing floor (separate ADR).
- **Health watchers** → already "unexpected happened." Keep as-is.
- **Lockout engaged/cleared pushes** (`pool/modes`) → confirmations. Demote to dashboard. (They are also currently firing on false positives — see the service-signal correction below — which must be fixed regardless.)
- **Swim-day-lock push** → confirmation. Demote to dashboard.

### Service-signal correction: pump-off ≠ "tech was here"

ADR-011 hung pool-service detection on external pump on/off transitions and treated an external pump-off as "tech is servicing." Two empirical findings retire that as the primary signal:

1. **Schedule masquerade.** The Hayward panel's own daily schedule turns the pump off at 16:00 and on at ~09:00 with no HA context — byte-for-byte indistinguishable, at the off-event, from a manual panel toggle (`why_on` collapses to `Off` on any turn-off; only the turn-*on* distinguishes `Timed Event` vs `Manual On`). This is what produced the daily false "Lockout Engaged" (16:00) + "Auto-Cleared" (00:01) pushes, and — more importantly — gated all four health watchers for ~8 hours nightly.

2. **The pump-off means something narrower than we thought.** Scott confirmed (2026-06-11) that the service tech does **not** shut the pump off on every visit — only when she **cleans the filter**. So an external pump-off is, at best, a *"filter likely cleaned"* signal. It is the **wrong signal** to hang "pool service tech was present" on: it misses every visit that doesn't include a filter clean (visual inspection, sensor swap, chemical check), and it fires on schedule events that aren't visits at all.

**Decision:** "Pool service happening" is rebuilt as a sensor-fusion signal — **camera + lanai door sensor + pump-as-weak-corroborator** — which is the precise realization of the "other detection signals can OR into the lockout boolean" hook ADR-011 left open. The pump-off transition is demoted to at most a corroborating *"filter likely cleaned"* event, never the primary presence signal. The pump-transition auto-detection is **not removed until the fusion detector is live**, because removing it without a replacement reintroduces the exact safety gap ADR-011 was built for (HA re-energizing equipment mid-service).

## Consequences

### Positive

- **Silence becomes loud.** The failure mode that hid for 12 days is structurally caught by the heartbeat rule.
- **Push channel regains signal.** Only genuine deviations and genuine missed-expectations reach the phone; confirmations move to a dashboard you look at when you choose to.
- **Nightly monitoring hole closes.** Demoting the lockout pushes is paired with stopping the phantom engagement, so the health watchers stop being gated for 8 hours every night.
- **Service detection gets honest.** Presence is detected by signals that actually correlate with presence, not by a pump-off that only sometimes happens.

### Negative / costs (accepted)

- **Discipline cost.** Negative-space alerts require enumerating every expectation and assigning a deadline. A *forgotten* expectation is an invisible gap — nothing spams you into noticing it's missing. That is simultaneously the point and the danger; it trades the old failure mode (false-positive noise) for a new one (false-negative silence) that must be guarded by the heartbeat rule and by periodic review of the expectation set.
- **More moving parts.** Heartbeats and deadline timers are themselves things that can break; they are kept deliberately simple and independent of the systems they watch.
- **Tuning.** Deadlines and floors (e.g., the pump-timing turnover minimum) need real-data calibration, not guessed constants — the same anti-pattern (hardcoded constants standing in for intent) this posture exists to remove.

## Follow-ups (separate threads / ADRs)

1. **Auditor push-bug fix + heartbeat** — decouple the `auditor.py` exit from `set -e`; add the liveness check. (Immediate.)
2. **Auditor rework ADR** — rebase W2/P1/P3/P4 onto commanded-vs-actual; add the pump-timing floor as the negative-space safety net; keep presence-independent checks (chlorine, cadence, availability, heater interlocks) unchanged.
3. **Lockout demotion + phantom-engage gate** — move engage/clear pushes to dashboard; gate detection on `why_on`/`from_state` so schedule transitions stop toggling the lockout.
4. **Tech-presence fusion ADR** — camera + lanai door + pump corroborator; realizes the ADR-011/ADR-013 hook; pump-off reclassified to a "filter likely cleaned" corroborating event.

## Sources

- 12-day auditor silence: `pool/audit/` (last result 2026-05-29), `pool/scripts/audit_yesterday.sh` (the `set -euo pipefail` + bare `auditor.py` call), `pool/scripts/auditor.py` lines 763/778/783 (exit_code on FAIL).
- Health-watcher deviation aliases: `packages/pool/pool_health_watcher.yaml`.
- Lockout daily choreography + health-watcher gating: `packages/pool/pool_modes.yaml` (detection automations lines 57–160, midnight auto-clear ~227–250), `packages/pool/pool_health_watcher.yaml` (watcher gating on `input_boolean.pool_service_lockout`).
- `why_on` discriminator (`Timed Event` vs `Manual On`, and the turn-off collapse to `Off`): `state_change` rows in `pool/analysis/pool_state_log_live.csv`.
- Service-signal correction: Scott, 2026-06-11 — tech shuts pump off only when cleaning the filter.
