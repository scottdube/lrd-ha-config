# Panel A Install Checklist — Vue 3 + CTs

**Panel**: A (left panel — pool side / main HVAC condenser / water heater)
**Vue 3 device**: Unit #2 (S/N TBD — record during reflash: __________________)
**Status**: Initial cloud install complete 2026-05-11; ESPHome reflash + post-remap reassembly pending 2026-05-12.

**Vue 3 orientation in Panel A: rotated 180° from Panel B.** Verified 2026-05-12:
- Antenna SMA jack on LEFT side of device
- Wiring harness (L1/L2/N/L3 green Phoenix) on RIGHT side
- "emporia" logo upside down
- Silkscreen "1" on FAR RIGHT end of top edge; silkscreen "16" on FAR LEFT
- **Locality rule (inverted from Panel B): RIGHT-side panel breakers → slots 1–8; LEFT-side breakers → slots 9–16.** Panel A has 8 LEFT + 8 RIGHT breakers — clean locality, no crossover.

See `panel-a-slot-remap.pdf` for the old→new slot mapping used during plug labeling.

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

## Branch CT priority list (16 of 16 slots used — post-remap 2026-05-12)

Slot ordering follows the inverted locality rule (RIGHT-side panel breakers in slots 1–8, LEFT-side in slots 9–16) chosen to minimize CT wire crossing at the Vue. See `panel-a-slot-remap.pdf` for old→new mapping during plug labeling.

For 240V circuits (slots 1, 3, 7, 9, 10, 12): single CT on either leg + `multiply: 2` filter in the ESPHome YAML — same pattern proven on Panel B. The phase_id (phase_a / phase_b) for each slot will be set per the multimeter mapping recorded during reassembly.

Walk-flip test plan: turn on the listed load, watch the matching `sensor.emporiavue_panel_a_circuit_N_*_power` entity in HA. If reads 0 W under load with the *neg filter, swap `phase_id` in YAML (most common fix). If reads ~half the expected value, the `multiply: 2` filter wasn't applied.

| Slot | Circuit | Breaker | Panel side | Walk-flip test load | Expected W | Verified | Notes |
|------|---------|---------|------------|---------------------|------------|----------|-------|
| 1 | Pool Subpanel | 60A 2P | R | Pool pump + heater both running | ~700–8000W | ☐ | 240V, ×2. Backsolves heater power per ADR-006. (was old slot 1 — no change) |
| 2 | Refrigerator | 20A | R | Compressor cycle (or trigger door alarm) | ~150–250W | ☐ | 120V continuous. (was old slot 5) |
| 3 | Water Heater | 30A 2P | R | Hot tap for 30s | ~4500W | ☐ | 240V, ×2 — confirm draw at heating element. (was old slot 6) |
| 4 | Kitchen GFI + recs (sink wall) | 20A | R | Coffee maker | ~1000W | ☐ | 120V. (was old slot 9) |
| 5 | Air #2 Handler | 30A 2P | R | Run Air #2 (Carrier Infinity) fan high | ~200–500W | ☐ | 240V, ×2 — indoor blower. Air #2 is a Carrier Infinity central system, NOT a mini split. (was old slot 3 — moved here from new slot 8 due to cable length) |
| 6 | Summer Kitchen GFI #1 | 20A | R | Plug in load on summer kitchen outlet | ~100W+ | ☐ | 120V outdoor. (was old slot 11) |
| 7 | Garage GFI + W/PS (side wall) | 20A | R | Plug in tool / known load | varies | ☐ | 120V workshop. (was old slot 12) |
| 8 | Guest / Pool Bath GFIs | 20A | R | Hairdryer in guest bath | ~1500W | ☐ | 120V. (was old slot 15) |
| 9 | Air #1 Condenser | 40A 2P | L | Run AC at low temp setpoint | ~3000–5000W | ☐ | 240V, ×2 — main HVAC outdoor unit (Carrier Infinity). (was old slot 2) |
| 10 | Garage Mini Split (Carrier 38MARBQ24AA3) | 35A 2P | L | Mini-split run high cool | ~500–2500W | ☐ | 240V, ×2 — single CT on either leg. Cross-validates against `sensor.garage_ms_power_realtime` (Midea LAN). (was old slot 13) |
| 11 | Microwave | 20A | L | Microwave 60s on high | ~1100W | ☐ | 120V. (was old slot 4) |
| 12 | Wall Oven | 30A 2P | L | Bake preheat 350°F | ~3000W | ☐ | 240V, ×2 — measure one leg. (was old slot 7) |
| 13 | Kitchen GFI + recs (stove wall, island) | 20A | L | Toaster on island | ~1000W | ☐ | 120V. (was old slot 8) |
| 14 | Irrigation / Post Light / Attic / Ceiling recs / Network Rack | 15A | L | Irrigation cycle OR check network rack baseline ~250W | ~50–250W | ☐ | 120V — outdoor + always-on lights + UDM Pro / NUC / switches. Network rack is the dominant always-on load. (was old slot 10) |
| 15 | Guest Room 3 | 15A AFCI | L | Plug-in lamp test | varies | ☐ | 120V. (was old slot 14) |
| 16 | Guest Room 2 | 15A AFCI | L | Plug-in lamp test | varies | ☐ | 120V. (was old slot 16 — no change) |

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
- [ ] ESPHome dashboard shows `emporiavue-panel-a` Online (post-reflash)
- [ ] HA → Settings → Devices & Services → ESPHome device auto-discovered + configured
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
