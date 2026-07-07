# LRD ADR-036 — Pool auditor publishes to a dedicated `audit` branch, not `main`

**Status:** Accepted (authored 2026-07-07; pending branch bootstrap + Mac mini deploy)
**Date:** 2026-07-07
**Decider:** Scott
**Context repo:** home-assistant (LRD; `scottdube/lrd-ha-config`)
**Related:** ADR-019 (auditor / recovery playbook), ADR-030 (alerting posture,
silent-failure fix + heartbeat), gitignore note 2026-05-21 (audit output
un-ignored to enable raw-URL read).

## Context

`pool/scripts/audit_yesterday.sh` runs nightly on the Mac mini (00:05 EDT),
writes `pool/audit/pool_audit_<date>.json`, and — per the 2026-05-21
decision to expose audit output over a GitHub raw URL for the
`daily-pool-audit-review` scheduled task — committed and **pushed that JSON
to `main`** every night.

Side effect: `main` accrued one machine commit per day (`audit: <date>
result`). Any human working in `~/code/home-assistant` falls behind origin
between sessions, so a normal `git push` is rejected non-fast-forward until
they `git pull --rebase`. On 2026-07-07 this bit a routine lighting-config
push (13 audit commits behind). Machine bookkeeping was blocking human work
on the shared branch.

There was also a latent failure mode: the old flow did `git add` + `commit`
on the working-tree's `main`, then `git push`. If the push failed, `main`
kept an unpushed local commit, and the next run's `git pull --ff-only` (top
of the script) would fail non-ff — silently degrading the auditor.

## Decision

**The auditor publishes audit JSON to a dedicated `audit` branch, never to
`main`.** GitHub raw URLs work on any branch, so the only consumer (the
review task) keeps working with a one-word URL change (`/main/` → `/audit/`).

`main` becomes human-only: no machine commits, no forced rebases, no race
between the nightly job and human pushes.

### Implementation

1. **Bootstrap once** (any machine): `git branch audit main && git push
   origin audit`. Seeds `audit` with the current tree (incl. the 53 JSONs
   already on main); it thereafter only accumulates audit additions.

2. **`audit_yesterday.sh`** — replaced the `git add`/`commit`/`push origin
   main` block with a plumbing publish that never touches the working tree
   or its current branch:
   - `git fetch origin audit`
   - dedupe: skip if the JSON blob already matches
     `origin/audit:<path>`
   - build a commit against `origin/audit` with a temp `GIT_INDEX_FILE`
     (`read-tree` → `update-index --add --cacheinfo` → `write-tree` →
     `commit-tree -p origin/audit`)
   - `git push origin <commit>:refs/heads/audit`
   - `stamp_heartbeat` on success (ADR-030 heartbeat unchanged)

   Because nothing commits to the working-tree `main`, the script's opening
   `git pull --ff-only` can never face an unpushed local commit — the latent
   failure mode is closed too.

3. **`daily-pool-audit-review` scheduled task** — raw URL repointed from
   `/main/pool/audit/...` to `/audit/pool/audit/...`. ADR links in that task
   stay on `/main/` (docs live on main).

4. **`.gitignore`** — `pool/audit/` re-ignored so the Mac mini's `main`
   working tree stays clean (the nightly JSON is still written to disk for
   local trend analysis; it just isn't tracked on main). The 53 historical
   JSONs remain in main's history; optional `git rm --cached pool/audit/*.json`
   fully relocates them.

## Consequences

- `main` no longer accumulates daily machine commits; human pushes stop
  getting rejected. No "pull --rebase before every session" ritual.
- Audit history is still fully versioned and raw-URL-readable, on `audit`.
- The auditor's own `git pull --ff-only` is now robust to prior push
  failures.
- Minor: `audit` and `main` diverge indefinitely (never merged) — expected;
  `audit` is an append-only data branch, not a config branch.
- Deploy touchpoints: bootstrap the branch, deploy the updated script to the
  Mac mini, and the task URL (already updated). Until the branch exists the
  nightly push logs a WARN and retries — non-fatal.

## Files

- `pool/scripts/audit_yesterday.sh` (git block rewritten, 2026-07-07)
- `.gitignore` (`pool/audit/` re-ignored)
- `daily-pool-audit-review` scheduled task (raw URL → `audit` branch)
- `docs/decisions/036-audit-results-on-dedicated-branch.md` (this)
