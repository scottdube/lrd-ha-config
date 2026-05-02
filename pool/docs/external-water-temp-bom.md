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
| **Conformal coating** — MG Chemicals 419D acrylic, 12 oz spray can | 1 | $18–22 | Reuse for many future builds. Mask connectors before applying. |
| **Indicating silica gel desiccant** (color-changing beads, ~3 mm) | small jar (50–100 g) | $8–12 | 1–2 g per build; jar lasts dozens. Use indicating type so saturation is visible at battery swap. |
| **Dielectric grease** — Permatex 22058 or equivalent | 0.33 oz tube | $5–7 | Apply to battery contacts and any electrical connection inside the case. |
| **Hydrophobic vent membrane** — choose ONE: | | | |
|  • Bud Industries IPV-1119 threaded breather (or equivalent M5/M6 ePTFE) | 1 | $10–15 | Engineered for the application; threads into a tapped hole. Cleanest install. |
|  • DIY: ePTFE membrane sheet from McMaster (P/N 5239K11 or similar Goretex equivalent) | small piece | $15–25 (sheet) | Cut a ~10 mm circle, glue over a 3–5 mm hole with marine silicone. Sheet provides enough material for many builds. |
| **Marine silicone sealant** — 3M 4200 Fast Cure or Permatex Marine Silicone | 3 oz tube | $8–10 | For vent perimeter, gasket backup, any new wire pass-through. |
| **Marine 2-part epoxy** — West System G/flex 650 or J-B Marine Weld | 2 × 1 oz tubes | $10–15 | For permanent re-seals if any are needed. Optional but cheap insurance. |
| **Replacement gasket material** — choose ONE based on existing dimensions: | | | |
|  • Viton (FKM) square-section profile cord from McMaster | ~1 ft | $15–25 | Best chlorine + salt + UV resistance. Cut to length, glue ends with cyanoacrylate to close the loop. |
|  • Viton O-ring assortment kit | 1 | $20–30 | Fallback if exact square-section dimensions are obsolete. May need groove modification for ideal compression. |
|  • EPDM square-section cord | ~1 ft | $8–15 | Cheaper alternative if Viton unavailable. Shorter service life in pool chemistry. |
| **Moisture mitigation subtotal** (lower bound — single vent option, single gasket option) | | **~$74–100** | |

---

## Total estimated BOM

| Category | Cost range |
|---|---|
| Electronics (incremental) | ~$0.60 |
| Power | $5–6 |
| Moisture mitigation | $74–100 |
| **Total v1 build** | **~$80–110** |

**At or near the $100 ADR-015 budget ceiling.** A few notes on this:

- The "money in chemicals" prediction held — moisture mitigation is ~85% of the spend
- Most chemicals (conformal coating, dielectric grease, silicone, epoxy, desiccant) come in quantities much larger than this single build needs. **Per-build incremental cost amortized over future builds is much lower** — closer to $30–40 once the consumable inventory exists
- The vent membrane choice has the biggest cost lever: a $10 threaded breather vs. $20 for membrane sheet that supplies many builds
- Replacement gasket sourcing is the highest-uncertainty cost — depends on what dimensions are needed and what's available

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
