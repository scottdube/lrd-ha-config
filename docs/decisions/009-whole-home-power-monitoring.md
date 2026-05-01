# ADR-009: Whole-home power monitoring

**Status:** Proposed (hardware not yet purchased)
**Date:** 2026-05-02
**Decider:** Scott
**Related:** ADR-006 (pump flow tied to compressor activity — pool side); future ADR-010 (per-circuit allocation strategy, after data lands)

---

## Context

The 2026-04-08 SECO Energy bill jumped from 2526 kWh (March) to 4551 kWh (April) — +2025 kWh. Decomposition via the Carrier app and pool integration data:

| Source | Estimated April kWh | Share of +2025 increase |
|---|---|---|
| HVAC (both units, calendar April) | 762 | **−245** (decreased) |
| Pool pump (24/7 @ 77% pre-v1.9.0) | ~500 | ~25% |
| Pool heat-pump compressor (estimate) | ~900–1100 | ~45–55% |
| Pool other (chlorinator, light) | ~90 | ~4% |
| **"Everything else" — unknown decomposition** | **~2350** | **~50% of total monthly kWh** |

The "everything else" bucket — water heater, refrigerator, freezer, electronics, lighting, EV charging, phantom loads — represents roughly **$320/month** at the SECO effective rate ($0.136/kWh). This is the largest unmonitored target in the household energy budget. Without per-circuit visibility, we can't optimize what we can't measure.

Pool work (v1.9.0 + ADR-006) addresses the pool bucket. Carrier presence-aware setback (backlog) addresses the HVAC bucket. The "everything else" bucket has no instrumentation today.

## Decision

**Install whole-home circuit-level power monitoring**, integrated with Home Assistant, capturing per-circuit W readings into the existing `pool_state_log.csv` (extending logger v2 with `home_*` columns) for cross-domain analysis with the auditor.

Two viable hardware paths considered. **Choice deferred** until install logistics are evaluated — both work; trade-offs differ.

### Option A: Emporia Vue 2 (~$170–200)

- 16 × 50A current transformers + 2 × 200A mains CTs
- All CTs included in box
- HACS integration: [`emporia_vue`](https://github.com/magicalyak/emporia_vue) — cloud-based via Emporia's API
- Local-only operation possible but undocumented (community hack via `pyemvue`)
- Polling: ~1 second real-time data
- Install: ~1 hour for an experienced person; CTs are split-core (no rewiring, just clamp around each circuit's hot wire in the panel)

**Pros:**
- Cheapest fast-start.
- All hardware in one box, including CTs.
- HACS integration mature, well-documented.
- Native HA Energy Dashboard support.

**Cons:**
- **Cloud dependency.** Real-time data flows through Emporia's servers. Vendor outage = blind. Vendor sunset = brick.
- Data retention beyond what HA records is at vendor's discretion.
- Less maker-friendly (closed firmware).

### Option B: IotaWatt (~$230 base + $15–20/CT)

- 14 CT inputs; CTs sold separately, choose per-circuit amperage
- Fully local — web UI hosted on the device itself, no cloud
- HA integration via REST API or [`iotawatt`](https://www.home-assistant.io/integrations/iotawatt/) core integration
- Polling: 1-second resolution; on-device retention measured in years on internal SD card
- Open-source firmware
- Install: same as Emporia (split-core CTs around hot wires) but per-CT install requires picking the right amperage rating per circuit

**Pros:**
- **No cloud dependency.** Data lives on the device. Survives vendor sunset.
- Better long-term data retention (years on device).
- Open firmware — Scott's maker profile fits this well.
- Per-CT amperage selection means the tool is right-sized for each circuit (15A clamps for outlets, 50A clamps for HVAC, 100A for mains, etc.).

**Cons:**
- Higher upfront cost when fully kitted out (probably $400–500 for 14 circuits).
- Steeper learning curve — IotaWatt's web UI is functional but less polished than Emporia's app.
- CTs are an additional purchase decision (size by amperage).

### Option C (rejected): Per-circuit Shelly Pro modules

- Reliable, fully local, but $50–80/circuit. For 14 circuits: $700–1100. Doesn't scale economically vs. Option A or B.
- Adds significant panel real estate.
- Considered if granular control (not just monitoring) is ever needed; deferred for now.

### Option D (rejected): Sense (ML-based whole-home disaggregation)

- $300+. No per-circuit clamps; uses ML to identify appliances from a single mains CT signal.
- Cloud-locked, closed source.
- Identification accuracy is hit-or-miss. Doesn't fit maker profile or local-first preferences.

### Recommendation

Lean **Option B (IotaWatt)** for fit with maker profile and local-first principle, despite higher upfront cost. **Option A (Emporia Vue 2)** is acceptable as a fast-start if Scott values immediate deployment over local-first. Final choice deferred until panel install logistics are evaluated.

## Consequences

### Positive

- **Bill decomposition becomes data-driven.** No more cube-law estimates for the pump or rated-W estimates for the heater — actual measured W per circuit, integrated to kWh per day.
- **Predictive maintenance signals across the house.** Same pattern as `local_filter_power` for the pool pump: W-per-load drift on the water heater = element scaling; HVAC compressor power vs. temp delta = efficiency degradation; etc.
- **Auditor expands.** New assertions: appliance-X consuming kWh-Y/day within expected band; total household kWh matches sum of monitored circuits within 5% (catches missed circuits or miscalibrated CTs).
- **Investment-grade visibility into the "everything else" $320/month bucket.** Either we find expensive surprises (failing water heater element, EV charger drawing more than spec) or we confirm baseline is genuinely just "stuff."

### Negative

- **Hardware install requires panel access.** Means turning off main breaker, opening panel, clamping CTs around each monitored circuit. Not unsafe but requires basic comfort with electrical work or an electrician's hour.
- **Initial CT placement may need iteration.** Some circuits may turn out to be split between multiple CTs by accident; calibration and verification round will be needed.
- **Schema growth in logger v2.** Adds 14+ columns. Manageable; CSV doesn't care about width within reason. May want to revisit SQLite migration sooner.

### Open questions

1. **CT amperage selection (Option B only).** Need to know per-circuit amperage from the panel directory before ordering. Action item: photograph/document panel directory before purchase.
2. **Install timing.** Best done during a planned outage (battery backup might cover briefly, or schedule when household is OK with 10 min of no power).
3. **Mains placement.** Both options support 200A mains CTs. With both mains capture + per-circuit, total measured = sum of circuits, validating the install.
4. **Solar / battery future.** Neither Option A nor B precludes adding solar/battery monitoring later, but if solar is ≤2 years out, that may inform hardware choice (some monitors integrate solar/grid/battery natively).

## Implementation plan

1. **Pre-purchase:**
   - Photograph the panel directory; document each circuit's amperage and load.
   - Decide between A and B based on local-first preference vs. ROI urgency.
   - If B: identify required CT amperages from panel directory.
2. **Purchase & receive:**
   - Hardware procurement.
   - Verify HA-side prerequisites: HACS integration installed, no version conflicts.
3. **Install:**
   - Schedule a 1-hour window with main breaker off.
   - Install device + CTs around target circuits.
   - Bring device online, verify integration sees all CT inputs.
4. **Calibration:**
   - With known loads (toaster, hairdryer, etc.) plugged into specific circuits, verify the right CT registers the right wattage.
   - Document any CT-to-circuit mapping in `energy/docs/circuit-map.md`.
5. **Logger v2 integration:**
   - Add `home_<circuit_name>_w` columns to `state_logger.py`.
   - Add `home_total_w` column from mains CT.
   - Verify: `home_total_w ≈ Σ(home_*_w) ± 5%` as a sanity check on the install.
6. **Auditor assertions (later, ADR-010):**
   - Per-circuit budget assertions.
   - Drift detection for predictive maintenance.

## Cross-references

- `pool/scripts/state_logger.py` — extend with `home_*` columns once installed.
- `pool/docs/data-schema-v2.md` — document new columns.
- `pool/docs/auditor.md` — auditor extends to home-power assertions in a future phase.
- `energy/README.md` — project overview (this ADR's sibling).
- `docs/current-state.md` — track install + commissioning status.
