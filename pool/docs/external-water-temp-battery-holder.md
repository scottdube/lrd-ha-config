# External water temp sensor — custom battery holder design log

**Project:** ADR-015 v1 build (case-reuse path)
**Reason for custom holder:** The purchased AA holder bottomed-out against the case interior walls before reaching its design depth (case ID transitions from 30 mm at the upper zone to a narrower bottom). A drop-in commodity holder won't fit. Custom 3-piece holder designed in Fusion 360 to nest inside the case.
**Last updated:** 2026-05-04 (v8 base / v5 cap / v4 deck — tether post relocated from cap to base for easier insertion handling and more printable geometry)

---

## Architecture

Three printed parts stack vertically inside the case:

| Part | OD | Height | Role |
|---|---|---|---|
| Battery_Cap (v5) | 32.5 mm | 5 mm disc + 2 mm pegs = 7 mm | Top of stack. Sits in the wider 33 mm upper zone. Has cell-pocket through-holes, alignment pegs to deck, wire slot, and a 5.5 mm-dia tether through-hole at (0, +12) that slides over the base's tether post |
| ESP32_Deck (v4) | 32.5 mm | 4 mm | Above cap. Carries the XIAO ESP32-C6 in a 2.5 mm-deep recessed pocket (1.5 mm floor remaining). 2.5 mm dia peg holes register it laterally to the cap |
| Battery_Base (v8) | 29.5 mm | 5.5 mm (disc 2.5 + lips 3.0) + 55 mm tether post = 57.5 mm overall | Bottom of stack. Sits in the 30 mm zone. Locates two AA cells with 3 mm-tall positioning lips, contains the contact slots and wire pass-through, and carries the 5 mm-dia × 55 mm tall tether post extending up from the disc top at (0, +12). Post is the insertion handle — Scott grabs it to lower the base in, then assembles cells/cap/deck around it |

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
| v6 | Lips re-clocked to (±7.25, 0) matching contact slots. Annular profiles split into outboard arcs and overlap pieces; filter selects only the outboard arcs (4 total — one upper + one lower per cell). No X intersection between cells | Disc-OD-clipped on the outboard sides, midline-clipped on the inboard sides, cells locate against each other across the inboard gap. **First-print feedback 2026-05-04:** base now reaches design depth (case-fit issue resolved) and OD is good. Insertion difficulty noted — fingers can't reach down far enough, base flips during placement. Cell lateral guidance also needs more height. Cap-deck peg fit too tight to assemble |
| v7 (base) / v4 (cap, deck) | Lip height 1 mm → 3 mm (3× taller) for more lateral cell guidance. Cap gets 5 mm dia × 50 mm tether post on its underside at (0, +12); base gets matching 5.5 mm dia through-hole at same coords. Deck peg holes 2.2 mm → 2.5 mm dia. Deck ESP32 pocket 1 mm → 2.5 mm deep | Post-on-cap orientation: cap becomes handle, base hangs from cap during insertion. Cap part total height 57 mm (later 62 mm at 55 mm post length). Not yet printed |
| **v8 (base) / v5 (cap, deck unchanged)** | **Tether post relocated from cap to base.** Base post extends 55 mm UP from disc top at (0, +12); cap gets a 5.5 mm through-hole at the same position. Same fit (5 mm post + 5.5 mm hole = 0.5 mm diametral clearance) | **Current.** Two improvements vs. cap-mounted post: (1) post prints much better attached to the smaller, simpler base than to the cap with its cell pockets and other features; (2) the post sticking up from the base is a natural insertion handle — grab the post above the case opening, lower base in, leave post in place, drop cells around it, slide cap down over post (post passes through 5.5 mm cap hole), then deck on cap. Post tip ends inside cap thickness (z=57.5 of 58 mm cap top) — does not interfere with deck |

---

## v8 / v5 / v4 final geometry

**Battery_Base v8**
- 29.5 mm OD × 2.5 mm disc + 3 mm lips = 5.5 mm disc-and-lips region; total part height 57.5 mm with the 55 mm tether post
- Wire slot at (0, −12), 4 × 10 mm, perimeter-open at −Y
- Cell positioning lips: 4 partial annular arcs (15 mm ID / 16 mm OD × 3 mm tall) at (±7.25, 0). Inboard-open, outboard disc-OD-clipped
- **Tether post: 5 mm dia × 55 mm tall at (0, +12)** extending up from the disc top. Functions as the insertion handle (grab above case rim, lower base in) and the cap-base alignment feature (post passes through cap during stack-up). Length sized so post tip ends within cap thickness when fully assembled (z=57.5 of cap-top z=58 mm) — does not protrude up into the deck region. Printable concern: 11:1 aspect ratio. Print post-up (disc on bed, post vertical), PETG over PLA recommended, solid infill in the post region. A small chamfer/sand on the post tip helps it pass through the cap's 5.5 mm hole.
- Contact slots (carried forward unchanged): 6 × 6 mm × 1.5 mm deep recesses at (±7.25, 0). ⚠️ Still sized for button contacts — see Open items
- **Print orientation:** disc-down, post vertical.

**Battery_Cap v5**
- 32.5 mm OD × 5 mm disc + 2 mm pegs = 7 mm overall
- Cell pocket through-holes: 14.5 mm dia at (±7.25, 0)
- Wire slot: at (0, −12), 4 × 10 mm
- Alignment pegs (up to deck): 2 mm dia × 2 mm tall at (±7, +11)
- **Tether through-hole at (0, +12): 5.5 mm dia × through cap thickness** — receives the base post. 0.5 mm diametral clearance over 5 mm post.
- **Print orientation:** disc-down (pegs facing up). Simple flat print.

**ESP32_Deck v4**
- 32.5 mm OD × 4 mm thick
- Wire slot: at (0, −12), 4 × 10 mm
- Peg holes (receive cap pegs): 2.5 mm dia at (±7, +11) — 0.5 mm diametral clearance over 2 mm cap pegs
- ESP32 pocket: 21.5 × 18 mm × 2.5 mm deep recess centered at origin. Floor: 1.5 mm
- **Print orientation:** disc-down (pocket facing up). Peg holes shallow, no support needed.

**STL locations:** `/Users/scottdube/Documents/Claude/Projects/home-assistant/{Battery_Base_v8,Battery_Cap_v5,ESP32_Deck_v4}.stl`

---

## Open items before final assembly

1. **Contact selection.** Generic 29 × 12 mm AA spring/plate replacement set (e.g., uxcell or SQXBK 12-pair) recommended over Keystone 209 single-cell springs. Decision: surface-mount the contacts on a flat disc (delete contact slots, route lugs through wire slot) OR redesign base with 29 × 13 × 1 mm recesses to seat them flush. Surface-mount is the smaller CAD change.
2. **Base end jumper.** Series configuration needs a jumper bridging cell-A − to cell-B + at the bottom. Easiest implementation: one flat plate + one spring soldered to a short wire bridge. Alternative: cut a single nickel strip with a flat at one end and spring at the other.
3. **Cap end contacts.** Two separate contacts at the top — one + spring, one − flat plate. Both terminate to wires that route through the cap wire slot up to the ESP32 deck.
4. **Print + fit verification.** Battery_Base_v8 + Battery_Cap_v5 + ESP32_Deck_v4 — print all three, confirm cap slides over the base post smoothly, peg-fit deck-to-cap, and base+post insertion handling.
5. **Stack-up height check after fit.** Cells (50.5 mm) + base (3.5 mm) + cap (7 mm) + deck (4 mm) = 65 mm. Verify against available case depth (60 mm of 30 mm-ID zone + cap nests in 33 mm zone). Cells partially occupy the 30 mm zone; cap+deck nest in the 33 mm zone above.

---

## Sources

- ADR-015 (`docs/decisions/015-external-water-temp-sensor.md`)
- BOM: `pool/docs/external-water-temp-bom.md`
- Calibration: `pool/docs/external-water-temp-calibration.md`
- Fusion 360 design: "Pool Temp Sensor Battery holder" (in user's Fusion projects)
