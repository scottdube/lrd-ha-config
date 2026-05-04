# External water temp sensor — custom battery holder design log

**Project:** ADR-015 v1 build (case-reuse path)
**Reason for custom holder:** The purchased AA holder bottomed-out against the case interior walls before reaching its design depth (case ID transitions from 30 mm at the upper zone to a narrower bottom). A drop-in commodity holder won't fit. Custom 3-piece holder designed in Fusion 360 to nest inside the case.
**Last updated:** 2026-05-03 (v6 base exported)

---

## Architecture

Three printed parts stack vertically inside the case:

| Part | OD | Height | Role |
|---|---|---|---|
| Battery_Cap | 32.5 mm | 5 mm + 2 mm pegs = 7 mm | Top of stack. Sits in the wider 33 mm upper zone. Has cell-pocket through-holes, alignment pegs, wire slot |
| ESP32_Deck | 32.5 mm | 4 mm | Above cap. Carries the XIAO ESP32-C6 in a recessed pocket. Peg holes register it laterally to the cap |
| Battery_Base | 29.5 mm | 3.5 mm (disc 2.5 + lips 1.0) | Bottom of stack. Sits in the 30 mm zone. Locates two AA cells, contains the contact slots and wire pass-through |

Cells: 2× AA lithium primary, head-to-tail series, side-by-side along the X axis at (±7.25, 0).

Wire pass-through: at (0, −12) on both base and cap, perimeter-open rectangular slot 4 × 10 mm (open to disc OD so wires can be installed when both ends are already terminated).

Pegs: at (±7, +11) on cap (2 mm dia × 2 mm tall); peg holes 2.2 mm dia on deck.

---

## Battery_Base iteration history

| Version | Change | Outcome |
|---|---|---|
| v1–v2 | Initial sketches | Print failures around thin-wall regions |
| v3 | First fully-printed version. Lips at (0, ±7.5) — Y axis. Full annular ring lips, 16 mm OD, extending past disc OR | Printed and fitted. Cells seat correctly. **But:** lips extended ~0.5–0.75 mm past the 29.5 mm disc OD, catching on case wall during insertion and preventing the base from settling to design depth |
| v4 | Lips removed entirely. Flat disc with contact slots only | Cleared the case-fit issue but eliminated cell positioning |
| v5 | Lips added back, clipped at disc OD via boolean intersection with disc face. Still at (0, ±7.5) | Lip overhang past disc OD eliminated. **But:** discovered the lips were 90° clocked from the existing contact slots (which are at (±7.25, 0) on the X axis — verified via sketch profile centroids). Also: where the two annular rings overlapped at the cell-cell midline, an X-shaped ridge remained that would interfere with cell seating |
| **v6** | Lips re-clocked to (±7.25, 0) matching contact slots. Annular profiles now naturally split into outboard arcs and overlap pieces; filter selects only the outboard arcs (4 total — one upper + one lower per cell). No X intersection between cells | **Current.** Disc-OD-clipped on the outboard sides, midline-clipped on the inboard sides, cells locate against each other across the inboard gap |

---

## v6 final geometry

**Base disc**
- 29.5 mm OD × 2.5 mm thick
- Wire slot at (0, −12), 4 × 10 mm, perimeter-open at −Y

**Contact slots (carried forward unchanged)**
- 6 × 6 mm × 1.5 mm deep recesses at (±7.25, 0)
- ⚠️ These were sized for hypothetical small button contacts. The selected commercial replacement contacts are 29 × 12 mm — slot redesign or surface-mount path needed before final assembly. Decision pending.

**Cell positioning lips**
- 4 partial annular arcs (one upper + one lower per cell)
- 15 mm ID / 16 mm OD × 1 mm tall
- Inboard side open: cells locate against each other across the 0.5 mm gap at x=0
- Outboard side clipped at disc OD: no portion exceeds 29.5 mm
- Each arc spans roughly 90° of its cell's annulus, in the upper/lower-outboard quadrants

**Print orientation:** disc-down (flat side on bed, lips facing up). Bottom is fully flat — no support needed anywhere.

**STL location:** `/Users/scottdube/Documents/Claude/Projects/home-assistant/Battery_Base_v6.stl`

---

## Open items before final assembly

1. **Contact selection.** Generic 29 × 12 mm AA spring/plate replacement set (e.g., uxcell or SQXBK 12-pair) recommended over Keystone 209 single-cell springs. Decision: surface-mount the contacts on a flat disc (delete contact slots, route lugs through wire slot) OR redesign base with 29 × 13 × 1 mm recesses to seat them flush. Surface-mount is the smaller CAD change.
2. **Base end jumper.** Series configuration needs a jumper bridging cell-A − to cell-B + at the bottom. Easiest implementation: one flat plate + one spring soldered to a short wire bridge. Alternative: cut a single nickel strip with a flat at one end and spring at the other.
3. **Cap end contacts.** Two separate contacts at the top — one + spring, one − flat plate. Both terminate to wires that route through the cap wire slot up to the ESP32 deck.
4. **Print + fit verification.** Battery_Base_v6 needs to be printed and inserted into the case to confirm it now reaches design depth.
5. **Stack-up height check after fit.** Cells (50.5 mm) + base (3.5 mm) + cap (7 mm) + deck (4 mm) = 65 mm. Verify against available case depth (60 mm of 30 mm-ID zone + cap nests in 33 mm zone). Cells partially occupy the 30 mm zone; cap+deck nest in the 33 mm zone above.

---

## Sources

- ADR-015 (`docs/decisions/015-external-water-temp-sensor.md`)
- BOM: `pool/docs/external-water-temp-bom.md`
- Calibration: `pool/docs/external-water-temp-calibration.md`
- Fusion 360 design: "Pool Temp Sensor Battery holder" (in user's Fusion projects)
