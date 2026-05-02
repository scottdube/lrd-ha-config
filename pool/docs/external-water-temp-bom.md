# External water temp sensor — BOM and sourcing

**Build target:** v1 per ADR-015 (case-reuse + NTC-reuse, ESP32-C6, 2× lithium primary AA, no regulator)
**Budget ceiling per ADR-015:** $100
**Last updated:** 2026-05-02

This BOM reflects the build *as of* the 2026-05-02 condensation analysis (ADR-015 "Thermal and condensation analysis" section). Moisture mitigation chemicals dominate the spend — confirmed prediction that "the money is in chemicals."

---

## Electronics — modest, mostly on hand

| Item | Qty | Unit cost | Subtotal | On hand? | Notes |
|---|---|---|---|---|---|
| Seeed XIAO ESP32-C6 dev board | 1 | $5–8 | — | **Yes** | Already in inventory per 2026-05-02 conversation |
| 47 kΩ 0.1% metal-film resistor (Yageo MFR series or similar) | 1 | $0.10 | $0.10 | Likely | Bought as 10-pack ~$1.50 if needed |
| Perfboard / small protoboard (~25 mm × 35 mm) | 1 | $0.50 | $0.50 | Likely | Cut to fit upper compartment |
| 22–26 AWG silicone-jacketed hookup wire | ~30 cm | trivial | — | Yes | |
| Solder, flux, heat-shrink | misc | trivial | — | Yes | |
| **Electronics subtotal** | | | **~$0.60 incremental** | | |

---

## Power — modest

| Item | Qty | Unit cost | Subtotal | Notes |
|---|---|---|---|---|
| Energizer Ultimate Lithium AA (or equivalent lithium primary) | 2 | $2.50–3.00 | $5–6 | Buy 4-pack to keep one set as spare. Avoid alkalines per ADR-015 chemistry decision. |
| **Power subtotal** | | | **~$5–6** | |

---

## Moisture mitigation — the dominant cost

Per ADR-015 "Thermal and condensation analysis" — these are required, not optional.

| Item | Qty / size | Unit cost | Notes |
|---|---|---|---|
| **Boeshield T-9** — 12 oz spray can | 1 | $13–15 | Single-product solution for PCB protection + battery contacts + internal metal hardware. Active moisture displacement, leaves thin waxy film. Reapply at each battery swap (already an existing maintenance touch point). **Test on scrap ABS first** — 24h soak of a drop on the case material to verify no plastic crazing before applying broadly. Replaces both conformal coating and dielectric grease line items from the prior BOM. |
| **Indicating silica gel desiccant** (color-changing beads, ~3 mm) | small jar (50–100 g) | $8–12 | 1–2 g per build; jar lasts dozens. Use indicating type so saturation is visible at battery swap. |
| **Silicone grease** — Super Lube silicone grease or equivalent | 1 oz tube | $5–7 | Gasket lubrication only — silicone-on-silicone compatibility with the original silicone gasket. Prevents bunching during threaded-ring tightening, fills groove micro-imperfections, gives even compression around perimeter. **Do not use T-9 here** — its hydrocarbon solvents aren't appropriate for the silicone gasket interface. |
| **Hydrophobic vent membrane** — choose ONE: | | | |
|  • Bud Industries IPV-1119 threaded breather (or equivalent M5/M6 ePTFE) | 1 | $10–15 | Engineered for the application; threads into a tapped hole. Cleanest install. |
|  • DIY: ePTFE membrane sheet from McMaster (P/N 5239K11 or similar Goretex equivalent) | small piece | $15–25 (sheet) | Cut a ~10 mm circle, glue over a 3–5 mm hole with marine silicone. Sheet provides enough material for many builds. |
| **Marine silicone sealant** — 3M 4200 Fast Cure or Permatex Marine Silicone | 3 oz tube | $8–10 | For vent perimeter, any new wire pass-through. |
| **Marine 2-part epoxy** — West System G/flex 650 or J-B Marine Weld | 2 × 1 oz tubes | $10–15 | For permanent re-seals if any are needed. Optional but cheap insurance. |
| ~~Replacement gasket material~~ | — | $0 | **Resolved 2026-05-02:** reuse existing silicone gasket per ADR-015. Inspect for compression resilience + visible damage before reuse; clean with IPA before re-greasing. Viton replacement remains as fallback only if inspection fails. |
| **Moisture mitigation subtotal** (lower bound — single vent option) | | **~$54–74** | |

---

## Total estimated BOM

| Category | Cost range |
|---|---|
| Electronics (incremental) | ~$0.60 |
| Power | $5–6 |
| Moisture mitigation | $54–74 |
| **Total v1 build** | **~$60–80** |

**Comfortably under the $100 ADR-015 budget ceiling.** Notes on the simplification from the prior BOM revision:

- Boeshield T-9 replaces both the conformal coating ($18–22) and dielectric grease ($5–7) line items — one product covers PCB protection, battery contacts, and metal hardware
- Reusing the existing silicone gasket (ADR-015 resolution) eliminates the gasket-sourcing line item ($15–25) and removes the longest-lead-time / highest-uncertainty piece of the BOM
- Most chemicals (T-9, silica gel, silicone grease, marine silicone, marine epoxy) come in quantities much larger than this single build needs. **Per-build incremental cost amortized over future builds drops to ~$25–35** once the consumable inventory exists
- The vent membrane choice remains the biggest cost lever: a $10 threaded breather vs. $20 for membrane sheet that supplies many builds
- T-9 introduces a maintenance reapplication cadence (every battery swap, ~12+ months) — acceptable because the swap is already an open-the-case touch point

---

## Sourcing recommendations

**Single-stop vendors (most efficient):**

- **McMaster-Carr** — gasket cord, ePTFE membrane, marine silicone, dielectric grease. Next-day shipping, no minimum.
- **Amazon** — lithium primary cells, conformal coating spray, indicating silica gel, marine epoxy, generic dielectric grease. Prime delivery.
- **DigiKey / Mouser** — XIAO C6 (if not on hand), 0.1% reference resistor, IPV-1119 vent breather. 2-day shipping.

**Pre-purchase verification needed:**

- Measure existing gasket: ID, OD, cross-section thickness (use calipers, photograph for sourcing reference)
- Measure existing wire pass-through hole diameter (for cable gland decision)
- Confirm XIAO ESP32-C6 model number on hand — some XIAO variants differ in pinout / antenna connector

---

## Tools (assumed on hand per Scott's maker profile)

- Soldering iron, multimeter, calipers
- Drill press + small bits (drill the vent membrane hole, possibly enlarge wire pass-through if needed)
- Hobby knife / razor for trimming
- Tap (M5 or M6) if going threaded-breather route — likely on hand from existing inventory

No new tool purchases anticipated.

---

## Sources

- ADR-015 (`docs/decisions/015-external-water-temp-sensor.md`) — requirements, decisions, and the thermal/condensation analysis driving moisture mitigation requirements
- 2026-05-02 conversation — empirical condensation observation during NTC calibration drove promotion of moisture-mitigation items from "optional" to "required"
- Calibration data (`pool/docs/external-water-temp-calibration.md`) — NTC characterization for the voltage divider design
