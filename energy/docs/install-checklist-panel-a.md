# Panel A Install Checklist — Vue 3 + CTs

**Panel**: A (left panel — pool side / main HVAC condenser / water heater)
**Vue 3 device**: TBD (record S/N during install: __________________)
**Install date**: __________________
**Status**: Planning

---

## Pre-install

- [ ] Vue 3 hardware on hand
- [ ] All 16× 50A branch CTs + 2× 200A mains CTs from bundle accounted for
- [ ] Antenna (included) on hand
- [ ] DIN rail or mounting screws ready
- [ ] Spare double-pole 15A breaker for Vue's 240V supply
- [ ] Photo current panel state (before-shot for reference)
- [ ] Notify household: brief power-off coming
- [ ] Phone connected to home WiFi (for Vue cloud setup)

---

## Mains CT placement (200A CTs)

Both Vue 3 mains CTs go around Panel A's incoming feed conductors — one per leg, ABOVE the 150A main breaker if accessible, or on the lugs if not.

- [ ] Mains CT A — leg 1 of Panel A feed — polarity per arrow on CT facing source
- [ ] Mains CT B — leg 2 of Panel A feed — polarity per arrow on CT facing source

---

## Branch CT priority list (16 of 16 slots used)

Walk-flip test plan: with each CT installed and Vue online, turn on a known load on that circuit and verify the Vue dashboard shows wattage on the expected CT slot. If wattage shows negative, flip CT polarity in software (Emporia app has this option).

| Slot | Circuit | Breaker | Panel side | Walk-flip test load | Expected W | Verified | Notes |
|------|---------|---------|------------|---------------------|------------|----------|-------|
| 1 | Pool Subpanel | 60A 2P | R | Pool pump + heater both running | ~700–8000W | ☐ | 240V — backsolves heater power per ADR-006. Slot reassigned from 7→1 during 2026-05-11 install (physical wiring already done at slot 1). |
| 2 | Air #1 Condenser | 40A 2P | L | Run AC at low temp setpoint | ~3000–5000W | ☐ | 240V — main HVAC outdoor unit |
| 3 | Air #2 Handler | 30A 2P | L | Master mini-split fan high | ~200–500W | ☐ | 240V — indoor blower |
| 4 | Microwave | 20A | L | Microwave 60s on high | ~1100W | ☐ | 120V |
| 5 | Refrigerator | 20A | R | Compressor cycle (or trigger door alarm) | ~150–250W | ☐ | 120V continuous |
| 6 | Water Heater | 30A 2P | R | Hot tap for 30s | ~4500W | ☐ | 240V — confirm draw at heating element |
| 7 | Wall Oven | 30A 2P | L | Bake preheat 350°F | ~3000W | ☐ | 240V circuit — measure one leg. Slot reassigned from 1→7 during 2026-05-11 install. |
| 8 | Kitchen GFI + recs (stove wall, island) | 20A | L | Toaster on island | ~1000W | ☐ | 120V |
| 9 | Kitchen GFI + recs (sink wall) | 20A | R | Coffee maker | ~1000W | ☐ | 120V |
| 10 | Irrigation / Post Light / Attic / Ceiling recs | 15A | L | Irrigation cycle | ~50–200W | ☐ | 120V — outdoor + always-on lights |
| 11 | Summer Kitchen GFI #1 | 20A | R | Plug in load on summer kitchen outlet | ~100W+ | ☐ | 120V outdoor |
| 12 | Garage GFI + W/PS (side wall) | 20A | R | Plug in tool / known load | varies | ☐ | 120V workshop |
| 13 | Garage Mini Split (Carrier 38MARBQ24AA3) | 35A 2P | R | Mini-split run high cool | ~500–2500W | ☐ | 240V — single CT on either leg, set "240V" / ×2 tag in Emporia app. Cross-validates against `sensor.garage_ms_power_realtime` (Midea LAN). Reassigned from Nook Recs on 2026-05-11 per accuracy discussion. |
| 14 | Guest Room 3 | 15A AFCI | L | Plug-in lamp test | varies | ☐ | 120V — reassigned from Dining Room Recs on 2026-05-11. Emporia app label still reads "Dining Room Recs" — rename to "Guest Room 3" in app config. |
| 15 | Guest / Pool Bath GFIs | 20A | R | Hairdryer in guest bath | ~1500W | ☐ | 120V |
| 16 | Guest Room 2 | 15A AFCI | L | Plug-in lamp test | varies | ☐ | 120V — reassigned from "Bedroom 2 OR Bedroom 3 (pick one)" on 2026-05-11. Emporia app label currently "Bedroom 2" (same physical room) — optional rename to "Guest Room 2" for consistency. |

---

## Skipped from Panel A (intentional)

- Smokes — few watts, not worth a CT slot
- Nook Recs (20A AFCI) — displaced 2026-05-11 by Garage Mini Split cross-validation on slot 13
- Dining Room Recs (20A AFCI) — displaced 2026-05-11 by Guest Room 3 on slot 14. Reason: dining room is essentially never used; both guest bedrooms now monitored instead

**Note on Garage Mini Split (slot 13, not skipped):** Originally listed as skipped because the unit reports `sensor.garage_ms_power_realtime` via Midea AC LAN. Promoted to slot 13 on 2026-05-11 to cross-validate the Midea-reported power against an independent CT measurement. Midea's `realtime_power` is inferred to be inverter-derived (DC-bus shunt × estimated efficiency) rather than a true-RMS AC measurement, which is typically ±10–20% vs the Vue CT's ±1–2%. The CT also surfaces standby draw that the Midea sensor floors to 0 W. Reference: ADR-009 cross-validation table.

---

## Vue 3 device setup

- [ ] Vue physically mounted in panel
- [ ] 240V supply leads connected to spare double-pole 15A breaker
- [ ] All CTs connected to Vue branch ports per slot assignments above
- [ ] All CT leads physically separated from line-voltage conductors per NEC 725.136
- [ ] Antenna routed out bottom knockout (testing) OR through prepared old-work box (permanent)
- [ ] Power restored to panel
- [ ] Vue 3 LED indicates power + WiFi connection
- [ ] Emporia cloud account: device registered
- [ ] HA → HACS → emporia_vue integration → device visible
- [ ] All 16 CT entities visible in HA Developer Tools → States

---

## Walk-and-flip calibration

For each CT slot 1-16, run the walk-flip test. Mark "Verified" column once:

- ✅ The right Vue CT slot shows wattage (not zero, not negative)
- ✅ Approximate value matches expected (within 20%)
- ✅ Polarity correct (positive when load is drawing)

If polarity is wrong → Emporia app → CT setting → flip polarity. No physical re-clamp needed.

---

## Post-install

- [ ] All 16 walk-flip tests verified
- [ ] CT-to-circuit map saved permanently (this doc, plus copy in `energy/docs/circuit-map.md`)
- [ ] Vue 3 entity IDs recorded for `state_logger.py` extension
- [ ] Vue 3 firmware version recorded (in case rollback needed when ESPHome flash work begins)
- [ ] Photo final panel state with CTs in place
- [ ] Update `device-inventory.md` with new device entry

---

## Field notes (write here during install)

```
[Date / Time:]



[Issues encountered:]



[CT polarity flips needed:]



[WiFi RSSI from Vue (if visible in Emporia app):]



[Other observations:]



```
