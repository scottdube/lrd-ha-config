# Panel B Install Checklist — Vue 3 + CTs

**Panel**: B (right panel — laundry / cooktop / master mini-split condenser / Air #1 handler)
**Vue 3 device**: TBD (record S/N during install: __________________)
**Install date**: __________________
**Status**: Planning — install AFTER Panel A is dialed in

---

## Pre-install

- [ ] Panel A install complete and verified (Panel B benefits from lessons learned on A)
- [ ] Second Vue 3 hardware on hand
- [ ] All 16× 50A branch CTs + 2× 200A mains CTs from bundle accounted for
- [ ] Antenna on hand
- [ ] DIN rail or mounting screws
- [ ] Spare double-pole 15A breaker for Vue's 240V supply
- [ ] Photo current panel state
- [ ] Notify household: brief power-off coming
- [ ] Phone on home WiFi for cloud setup

---

## Mains CT placement (200A CTs)

- [ ] Mains CT A — leg 1 of Panel B feed — polarity per arrow on CT facing source
- [ ] Mains CT B — leg 2 of Panel B feed — polarity per arrow on CT facing source

---

## Branch CT priority list (16 of 16 slots used)

| Slot | Circuit | Breaker | Panel side | Walk-flip test load | Expected W | Verified | Notes |
|------|---------|---------|------------|---------------------|------------|----------|-------|
| 1 | Dryer | 30A 2P | L | Run dryer 1 min on high | ~5000W | ☐ | 240V — heating element + drum motor |
| 2 | Cooktop | 40A 2P | L | Burner on high | ~2000–4000W | ☐ | 240V — single burner test |
| 3 | Air #1 Handler | 60A 2P | R | Run main HVAC, especially in heat strip mode | ~500W (fan) to ~10000W+ (strip heat) | ☐ | 240V — has electric resistance backup heat |
| 4 | Air #2 Condenser | 25A 2P | R | Master mini-split run | ~1500–3000W | ☐ | 240V — outdoor compressor |
| 5 | Washer + Laundry Rec | 20A | L | Run washer on heavy cycle | ~500W (motor) | ☐ | 120V — washer motor + incidental loads |
| 6 | Garbage Disposal | 20A | R | Run disposal 5s | ~500W | ☐ | 120V |
| 7 | Dishwasher | 20A | R | Start dishwasher cycle | ~1200W | ☐ | 120V — heating element when active |
| 8 | Master Bath GFI / Rec / Shower Term | 20A | R | Hairdryer in master bath | ~1500W | ☐ | 120V |
| 9 | Garage 20A Dedicated GFI | 20A | R | Plug in known load | varies | ☐ | 120V — confirm what's normally on this circuit |
| 10 | Garage GFI + W/PS (panel wall) | 20A | R | Plug in workshop tool | varies | ☐ | 120V |
| 11 | Summer Kitchen GFI #2 | 20A | R | Plug in outdoor load | ~100W+ | ☐ | 120V outdoor |
| 12 | Family Room / Lanai Fans / Sum Kitch Cans / Foyer / Entry | 15A AFCI | L | Lanai fans on high | ~200–400W aggregate | ☐ | 120V — flagged for Florida summer fan usage |
| 13 | Master Bed / Lanai Cans | 15A AFCI | L | Lanai cans on | ~50–100W | ☐ | 120V |
| 14 | General Loads (garage/chime/laundry/nook/kitch/master hall) | 15A AFCI | L | Hall lights | ~50W | ☐ | 120V — aggregated lighting across zones |
| 15 | Garage Counter Top + Under Cab Lighting | 20A | L | Plug in garage tool / under-cab lights on | varies | ☐ | 120V |
| 16 | Master Bath / Hall / Closets | 15A AFCI | L | Bathroom lights on | ~50W | ☐ | 120V |

---

## Skipped from Panel B (intentional)

- Whirlpool (20A) — never used per Scott
- Spare (15A) — empty slot

---

## Vue 3 device setup

- [ ] Vue physically mounted in panel
- [ ] 240V supply leads connected to spare double-pole 15A breaker
- [ ] All CTs connected per slot assignments above
- [ ] All CT leads physically separated from line-voltage conductors per NEC 725.136
- [ ] Antenna routed (knockout or old-work box per Panel A install pattern)
- [ ] Power restored
- [ ] Vue 3 LED indicates power + WiFi
- [ ] Emporia cloud: second device registered
- [ ] HA: second device visible via emporia_vue integration
- [ ] All 16 CT entities visible

---

## Walk-and-flip calibration

Same protocol as Panel A. Mark "Verified" column once each circuit confirmed.

---

## Post-install

- [ ] All 16 walk-flip tests verified
- [ ] CT-to-circuit map saved (this doc + `energy/docs/circuit-map.md`)
- [ ] Both Vue 3 entity IDs recorded for `state_logger.py` extension
- [ ] Update `device-inventory.md` with second device entry
- [ ] Sanity check: `mains_a_W + mains_b_W ≈ Σ(branch CTs)` within ±10%
  - If well off, indicates uncalibrated CT, missed circuit, or polarity inversion somewhere
  - Use the raw sum-of-branch as a validation tool

---

## Field notes (write here during install)

```
[Date / Time:]



[Issues encountered:]



[CT polarity flips needed:]



[WiFi RSSI from Vue (if visible in Emporia app):]



[Other observations:]



```
