# ADR-029 — Adopt dual-site HA, SLN bootstrap

**Status:** Accepted
**Date:** 2026-05-29
**Supersedes:** N/A
**Related:** ADR-024 (pre-departure freeze + summer update policy — applies per-site once SLN is live)

---

## Context

Home Assistant has been a single-site project since the Hubitat migration completed in May 2026: one HA install at LRD (FL vacation house), one canonical repo (`scottdube/lrd-ha-config`), 28 ADRs, ~35 Z-Wave nodes, deep integration stack (OmniLogic pool, Carrier/Midea HVAC, photo-frame, Vue Gen 3 energy monitoring, voice satellites).

Scott is now expanding HA to the NH primary residence (SLN) for the first time. The drivers:

- HA at LRD has matured to the point where Scott is fully committed to the platform — the original hesitation that kept SLN on Hubitat C6 is resolved.
- SLN has been running a Hubitat C6 hub from the basement network rack with proven Z-Wave mesh coverage at that location.
- The dual-site network already exists (UniFi mesh VPN between SLN UDM Pro and LRD), so the marginal complexity of adding a second HA site is low.
- Hardware ordered 2026-05-29: used Intel NUC10i5FNH (i5-10210U / 16GB / 512GB, $272 delivered) from eBay seller `waterweed88`, and Nabu Casa Connect ZWA-2 (refurb, $63.95) as the Z-Wave controller. Arriving Jun 1–5.

This ADR captures the cross-cutting decisions about scope, naming, and repo structure. Site-specific build details (network config, integrations, install plan) live in the new SLN repo's `docs/decisions/001-sln-ha-site-bootstrap.md`.

---

## Decision

**1. HA scope expands from single-site (LRD) to dual-site (LRD + SLN).** Each site has an independent HA install — no shared HA Core instance, no cross-site entity federation. Cross-site coordination (if ever needed) flows through external pub/sub or REST, not native HA.

**2. Adopt the `network-docs` site code convention in HA.** Site codes are:
- **LRD** = Lake Ridge Drive (FL vacation house) — this repo, existing install.
- **SLN** = NH primary residence — new repo, install in flight.

Convention: HA artifacts referenced across sites use the site code prefix (e.g., "the SLN ZWA-2", "LRD's `input_boolean.vacation`"). Single-site artifacts stay unprefixed within their own repo.

**3. Dual-repo, not monorepo.** Each site gets its own canonical config repo paralleling the network-docs/HA repo split:
- `scottdube/lrd-ha-config` (this repo — existing)
- `scottdube/sln-ha-config` (new — bootstrap when SLN hardware arrives)

ADRs are site-scoped to their respective repo's `docs/decisions/`. This cross-cutting ADR (the one you're reading) lives at LRD because LRD is the established canonical project; the SLN repo references it as Related.

**4. Clean HA OS install on SLN.** No backup restore from LRD. LRD's config is ~80% physically tied to LRD-only hardware (OmniLogic pool, Carrier zones, Midea garage MS, photo-frame TVs, 35-node Z-Wave network) — restoring would force a delete-most pass that's higher cognitive load than fresh install + selective convention copy. What gets copied from LRD as scaffold:

- Repo structure (README / `docs/` / `integrations/` / `packages/` / `tools/` layout)
- ADR template
- `notify` group pattern (`notify.scott_and_ha` shape for the SLN mobile target)
- `input_boolean.vacation` per ADR-012 (same pattern applies)
- Studio Code Server + git-pull deploy workflow
- Reusable tooling templates (`tools/rename_entities.py`, audit harness pattern)
- Pre-departure freeze + summer update policy (ADR-024)

What does NOT carry over: any package referencing physical entities, any integration tied to LRD hardware, any blueprint reference that hasn't been generalized.

**5. Cowork project structure stays single-project, dual-folder.** The existing `home-assistant` Cowork project continues to span both sites — it's a domain (HA), not a deployment target. Both repo folders mount into the same project. Memory and project instructions stay unified. The `network-docs` project also gets mounted as a read-only working folder so HA work can consume current network facts without round-tripping through Scott.

---

## Consequences

**Positive:**

- LRD's existing knowledge base (28 ADRs, integration notes, tooling) is fully available for SLN bootstrap, accelerating the second-site build dramatically.
- ADR-024 update policy already covers vacation freezes — the same pattern applies at SLN, no new policy work.
- Site-code convention from network-docs extends consistently into HA — no naming drift between projects.
- Dual-repo structure keeps each NUC's Studio Code Server / git-pull workflow independent — no risk of accidentally pushing LRD config to SLN or vice versa.

**Negative:**

- Pattern drift between sites is now possible. Mitigation: when porting a pattern from LRD → SLN, port it as-is and only customize when SLN actually needs to deviate. Any deviation gets an ADR in the SLN repo.
- Two ADR numbering sequences now exist (LRD continues 029, 030, … ; SLN starts at 001). When referencing across repos, always qualify (e.g., "LRD ADR-029" not "ADR-029").
- Site ambiguity in conversation. Mitigated by the convention in #2 above and the Cowork project instructions update.
- Tooling duplication risk. If `tools/` scripts get materially valuable at both sites, factor them into a third `scottdube/ha-tools` repo as git submodules. Defer until duplication actually hurts.

**Neutral:**

- LRD-side automations and integrations are unchanged by this ADR. Nothing in `packages/`, `automations.yaml`, or any integration note needs editing.
- Memory file `MEMORY.md` already updated to reflect dual-site scope (entry `user_property_lrd_is_florida.md`).

---

## Implementation checklist

Tracked separately in `docs/current-state.md`. High-level:

1. README.md updated with Sites section and SLN repo pointer (this commit).
2. This ADR (029) lands in LRD repo.
3. Cowork project instructions updated with site-code convention + network-docs read-only mount policy.
4. When SLN hardware lands (Jun 1–5):
   - Create `scottdube/sln-ha-config` with scaffold structure.
   - Write SLN ADR-001 (site bootstrap — hardware, network plan, install procedure).
   - HA OS USB install on NUC.
   - Studio Code Server app, wire to SLN repo.
   - ZWA-2 plug-in, Z-Wave JS install, network creation.
   - SLN device inventory + inclusion plan.

---

## Open questions

- **SLN VLAN / IP plan.** Pending — should mirror LRD's pattern (servers VLAN for HA NUC, IoT VLAN sub-interface for broadcast/multicast adjacency) but the actual subnet numbers come from network-docs. Resolve when network-docs is mounted into the project.
- **Blueprints repo.** Currently `scottdube/lrd-ha-blueprints` is LRD-named. If SLN builds materially divergent blueprints, decide: rename to `scottdube/ha-blueprints` (drop site prefix, accept shared scope) or fork to `scottdube/sln-ha-blueprints`. Defer.
- **Nabu Casa subscription.** One Nabu Casa account; can a single subscription cover two HA instances? Verify before SLN's first remote-access need. Pricing/policy check needed.
