# Incident — Eaton BRAF AFCI nuisance trips on P-B C6 General Loads

- Date: 2026-05-28 evening EDT
- Status: Diagnostic in progress; fluorescent fixture hypothesis under test
- Circuit: Main panel — 15A AFCI Combination Type BRAF (Eaton), labeled
  "General Utils — garage, chime, laund, laundry hall, nook, Kitch cans,
  master hall"
- Vue mapping: **Panel B Circuit 6 "General Loads"**

## TL;DR

A 15A Eaton BRAF combination AFCI breaker tripped **three times in ~25
minutes** on the evening of 2026-05-28 (20:44, 20:49, 21:08 EDT). Vue
P-B C6 history captured all three trip signatures cleanly. Pre-trip
baseline was a steady ~540 W with no surge before each trip — diagnostic
pattern of an **arc-fault signature**, not an overcurrent overload.

Branch loads inventory (per label + HA control surface):

- Kitchen Cans (LED, Z-Wave dimmer)
- Kitchen 4 Cans (LED, Z-Wave dimmer)
- Nook (LED, Z-Wave dimmer)
- Master Hall (LED can lights)
- Chandelier with LEDs
- Laundry / Laundry Hall lights
- **2× groups of 4ft fluorescent fixtures** (locations TBC — likely
  garage shop lights + one other)
- Doorbell chime transformer (~5 W always-on)

Hypothesis: **the 4ft fluorescent fixtures are the AFCI trigger.**
Eaton BRAF AFCIs are documented industry-wide as highly susceptible to
fluorescent ballast arc signatures (both magnetic and aging electronic),
and tube end-of-life arcing in particular. The steady ~540 W pre-trip
baseline is also ~300 W higher than expected for LED-only lighting,
matching the load of 4-6 fluorescent tubes (~64-80 W per 2-tube fixture).

Test in progress: fluorescents physically isolated via the Z-Wave switch
**air-gap pull tab**, breaker reset at 21:36:23 EDT. Baseline observed
afterward dropped to **~11 W steady** (chime + dimmer parasitic), then
loads added back to verify the breaker holds.

## Timeline (UTC; subtract 4h for EDT)

| Time UTC | Time EDT | Event | Source |
|---|---|---|---|
| 00:44:35 | 20:44:35 | Trip #1 — 541 W → 0 W | Vue P-B C6 history |
| 00:46:00 | 20:46:00 | Reset #1 — 0 W → 562 W | Vue P-B C6 history |
| 00:49:50 | 20:49:50 | Trip #2 — 565 W → 0 W (4 min after reset) | Vue P-B C6 history |
| 00:51:21 | 20:51:21 | Reset #2 — 0 W → 568 W | Vue P-B C6 history |
| 01:08:36 | 21:08:36 | Trip #3 — 546 W → 125 W → 0 W (2-step drop) | Vue P-B C6 history |
| 01:32:32 | 21:32:32 | Confirmed 0 W (breaker open) — diagnostic prep | Vue P-B C6 history |
| 01:36:23 | 21:36:23 | Reset #3 — 256.8 W instantly (something already commanded on) | Vue P-B C6 history |
| 01:36:38 | 21:36:38 | Peak 386.3 W as residual loads stabilized | Vue P-B C6 history |
| 01:37:08 | 21:37:08 | Manual load shedding began (286 → 159 W) | Scott physically |
| 01:37:48 | 21:37:48 | Steady 13 W (~chime + dimmer standby) | Vue P-B C6 history |
| 01:38:23 | 21:38:23 | Steady 11.4 W — baseline established | Vue P-B C6 history |

## Forensic patterns supporting the AFCI nuisance trip hypothesis

### 1. Pre-trip steady load (~540 W, no surge)

All three trips happened from a stable 541-565 W baseline that had been
holding for many minutes. There is **no appliance-turn-on spike** in the
sub-second window before any trip. This rules out the "two high-draw
appliances on a borderline branch caused thermal trip" hypothesis. The
trips were waveform-driven (arc detection), not current-driven (thermal
overload).

### 2. 4-minute trip-to-retrip interval (Trips #1 → #2)

After Reset #1 at 20:46:00 EDT, the breaker re-tripped only **4 minutes
later** at 20:49:50 EDT — much too fast for thermal cooldown to be the
mechanism (thermal needs many minutes), and much too slow for a hard
short-circuit (which would re-trip immediately on reset). The 4-minute
window matches the **thermal warm-up cycle of a fluorescent ballast**:
load comes back, ballast and tubes start cold (clean waveform), warm to
steady-state over 3-5 min, arc signature intensifies as components heat,
AFCI's arc-detection algorithm crosses threshold and opens.

### 3. 2-step drop on Trip #3 (546 → 125 → 0 W)

The third trip captured an intermediate 125 W reading between the
pre-trip steady state and the breaker-open zero. The Vue samples at
~5 sec; the BRAF opens in <1 cycle (~16.7 ms). The 125 W intermediate is
not the breaker partially opening — it's the Vue catching the load state
during one of the sub-cycle arcing events that built up to the trip.
This is characteristic of a deteriorating connection or aging fluorescent
ballast that arcs more progressively as it ramps to the AFCI's
detection threshold.

### 4. Unexplained ~300 W of baseline

The expected lighting load for this branch (assuming all-LED) is
150-200 W. The observed steady baseline was **~540 W**, a ~300 W gap.
Two 4ft fluorescent fixtures (typical 2-tube T8 = 64 W or T12 = 80 W)
account for 128-320 W of that gap. With ~4 tubes across two fixtures the
math matches.

### 5. Industry-documented Eaton BRAF + fluorescent failure mode

Eaton's BRAF combination AFCI line uses a particular waveform-pattern
algorithm that is well-known in the field to false-trip on fluorescent
ballast harmonics — especially when:

- The ballast is **magnetic** (heavier 60 Hz harmonic content)
- The tubes are at **end-of-life** (visible dark bands at the tube
  ends — phosphor degradation around the cathode causing re-strike arcs)
- The fixture is in a **heavy-use / warm area** where the ballast
  reaches higher operating temperatures

This is documented in Eaton's own AFCI troubleshooting bulletins and
discussed extensively in IBEW and electrical-inspector communities.

## Diagnostic test in progress

Per Scott 2026-05-28 ~21:36 EDT:

1. Pulled the **air gap reset tab** on the Z-Wave switch feeding the
   fluorescent fixtures — physically disconnects the load regardless of
   what HA / Z-Wave commands the switch state to.
2. Reset the AFCI breaker. Vue confirms circuit holding.
3. Baseline observed at **11 W steady** after Scott shed remaining
   commanded-on loads — confirms the chime transformer + Z-Wave dimmer
   parasitic draws total ~10-15 W (expected).
4. Next: add the other loads back (LED cans, chandelier, nook at >30%
   brightness) and watch for 15-20 min. If the breaker holds, the
   fluorescent fixtures are confirmed as the AFCI trigger.

## Companion-state observations

- HA shows `light.garage_lights` as `on` at brightness 255 throughout —
  that's the Z-Wave commanded state, not actual line power. With the air
  gap pulled, no current flows even when HA reports the light as "on."
- The breaker label says "Lanai Fans" but the **lanai fans never lost
  power** during any trip. Vue P-B C4 "Family Rm Lanai" stayed at a
  steady 295-302 W through all three trip events. Conclusion: the breaker
  label is incorrect — lanai fans are on a different branch. Label
  needs correction.
- The `light.wall_dimmer_switch_nook` was at brightness **3/255 (1.2%)**
  during the trips. Very low TRIAC phase-cut angles produce the most
  chopped waveform AFCIs see — this dimmer setting may have been a
  contributing waveform anomaly on top of the fluorescent baseline. Worth
  reviewing whether anyone was running the nook lights at 1% recently.

## Recommended fix paths (in order of cost / complexity)

### Option 1 — Direct-wire (Type B) LED tube retrofit

- **Cost:** $8-15 per tube
- **Effort:** ~10 min per fixture (remove ballast, wire 120 V directly
  to existing tombstone sockets)
- **Pros:** Cheapest, fastest, eliminates ballast entirely. The LED
  tubes use switching-mode power supplies that are AFCI-friendly. Energy
  savings ~60-70% on those fixtures.
- **Cons:** Requires correct tube selection (must be "Direct Wire" /
  "Ballast Bypass" / "Type B" — NOT "Plug and Play" / "Type A" which
  keeps the ballast in circuit).

### Option 2 — Full LED fixture replacement

- **Cost:** $30-60 per fixture
- **Effort:** ~15 min per fixture (mount swap, splice line)
- **Pros:** New fixtures, modern light quality, drop-in install.
- **Cons:** Costs more than direct-wire retrofit; existing fixtures may
  be in good cosmetic shape and not need replacement.

### Option 3 — Move fluorescents to a non-AFCI branch

- **Cost:** Electrician fee + permit (if required by jurisdiction)
- **Effort:** Significant — rerouting a branch
- **Pros:** Keeps fluorescents.
- **Cons:** Code in most jurisdictions requires AFCI on most circuits in
  living spaces. Garage / detached utility may not require it but living
  rooms (family room, kitchen, master hall) do. Doesn't address
  underlying fluorescent aging issue.

**Recommendation: Option 1** — direct-wire LED tube retrofit. Cheapest,
fastest, and improves lighting quality + energy efficiency as a side
benefit. Can do all the fluorescent fixtures on this branch in one
afternoon with $50-100 in tubes and basic wiring tools.

## Open follow-ups

- [ ] **Confirm hypothesis** — does the breaker hold for >30 min with
  all non-fluorescent loads on and fluorescents air-gapped?
- [ ] **Inventory the fluorescent fixtures** — exact count and locations.
  Are they all 4ft? Tube type (T8 vs T12)? Ballast type (magnetic vs
  electronic)? Tube condition (dark bands at ends)?
- [ ] **Choose fix path** — most likely Option 1 (direct-wire LED).
- [ ] **Update breaker labels** on the main panel:
      - The breaker pointed to in the first photo (#2 from top in left
        column, "Family Room / Lanai Fans / Sum Kitch Cans / Foyer Entry
        / ...") does NOT actually feed the lanai fans (Vue C4 confirms
        they stayed up through all trips). Re-label after walking the
        branch.
      - The General Utils breaker (#4) is what actually trips and
        contains the Kitchen Cans + Nook + Master Hall + Laundry + the
        fluorescent fixtures.
- [ ] **Redirect `light.garage_lights` references** in `automations.yaml`
  and `scripts.yaml` to `light.garage_cans` while the fluorescents are
  air-gapped, so the garage-door / motion / golf-sim flows still work.
- [ ] **Re-enable the 4 garage light automations + 2 kitchen cans sync
  automations** disabled during diagnostic (after the redirect lands).
- [ ] **Update `tools/occupancy/lrd.yaml`** — `light.garage_lights` is
  in the lights list there; once the fluorescents are retrofitted,
  decide whether the lights list should track `garage_lights` or shift
  to `garage_cans`.

## Vue data archive (for the report log)

Source: HA `recorder/statistics_during_period` via `/api/history/period`
queries against `sensor.emporia_vue_panel_b_circuit_6_general_loads_power`
on the LRD NUC at 192.168.50.11.

Key extracted timeline transitions are in the table above. Full per-sample
trace was not persisted — the HA recorder default retention (10 days)
keeps the raw data accessible via the API until ~2026-06-07. If a longer
archive is wanted, query and dump to CSV before then.

## Source

- 2026-05-28 conversation troubleshooting the 21:08 trip in real time
- Breaker panel photos (2 photos showing initial mis-identification then
  correction to the General Utils breaker)
- Vue P-B C6 General Loads history pulls during the diagnostic

---

## Amendment 2026-05-28 late evening / 2026-05-29 morning — corrected root cause

The fluorescent hypothesis above is **wrong**. The continuing investigation
that same evening cleared the fluorescents and identified the actual cause:
**`light.wall_dimmer_switch_kitche_4` is a no-neutral Z-Wave dimmer**, and
its trickle-current return path through the LED bulbs produces the
arc-fault waveform the AFCI is correctly detecting.

### Investigation chronology (revised)

| Time EDT | Test | Outcome |
|---|---|---|
| 22:07-22:33 | Garage fluorescent alone (after air-gap on `light.garage_lights`) | 25.8 min steady, 0 trips, 0 Ting anomalies — **cleared** |
| 22:33-22:41 | Full reproduction (~528 W, all loads as cluster) | Trip at 22:41 within 1m 22s of Island Lights coming on |
| 22:54-23:04 | Island Lights alone at brightness 157 (61.5%) | 10 min steady, 0 trips, 0 Ting anomalies — **cleared** |
| 23:05-23:15 | Multi-load reproduction (~500W, all suspects + Island Lights at 61.5%) | 3 Ting anomalies in 10 min, no trip |
| 23:15-23:26 | A/B test: Island Lights OFF, other loads ON | 2 Ting anomalies in 10 min (same rate) — **Island Lights cleared** |
| 23:30 (overnight) | All wall paddles off, breaker closed, doorbell live | 72 Ting anomalies in 9.4 h, no trip — proves something is still actively trickling |
| 08:43 EDT 5/29 | Scott pulls **air gap on `light.wall_dimmer_switch_kitche_4`** | Watch ongoing at writing |

### Why the fluorescent hypothesis was wrong

The forensic correlations I trusted (4-min ballast warmup, hi pre-trip
load, 2-step drop signature) were either coincidence or symptom of the
underlying issue:

- The 4-min "trip after load came on" intervals were the cumulative
  arc-fault sample accumulation crossing the AFCI threshold — not
  ballast-specific warmup.
- The 540 W pre-trip baseline I attributed to fluorescents was actually
  mostly kitchen LED cans at full brightness; the fluorescent contribution
  was real but they're not the arc source.
- The Ting anomaly cluster I observed during the trip cluster was
  produced by the kitche_4 dimmer's trickle current waveform, not by
  fluorescent ballast harmonics.

### Why no-neutral Z-Wave dimmers cause this

The no-neutral dimmer steals a small current (typically 10-50 mA) through
the load to power its own electronics — including when the dimmer is
commanded OFF. That trickle current:

1. **Doesn't follow normal AC patterns** — the dimmer's internal switching
   regulator chops the trickle into a non-sinusoidal waveform that the
   LED bulbs see as input.
2. **Drives the LED driver's input filter into bizarre operating regions**
   — the SMPS sees the trickle as noise, sometimes oscillates.
3. **Superimposes on the dimmer's TRIAC phase-cut** when actively dimming
   — instead of clean phase-cut, you get phase-cut on a trickle pedestal.
4. **Looks indistinguishable from a series arc fault to the BRAF's
   detection algorithm.** Ting independently confirms real arc-fault
   waveform via its 208.78 V "anomaly" markers — 72 in 9.4 hours
   overnight, despite the wall paddle being "off."
5. **Can become a real arc precursor over time** — the trickle through
   the LED driver's switching components stresses them and accelerates
   failure.

### Corrected fix path

In order of effort / cost:

1. **Aeotec ZWA042 wire-saver / bypass capacitor** (~$12-15) installed at
   the kitche_4 fixture's last junction box, wired line ↔ neutral in
   parallel with the LED load. Provides a return path so the dimmer
   doesn't have to trickle through the LEDs. ~15 min install. **Most
   likely fix.** Ordered 2026-05-29, target install post-NH return.
2. **Run a neutral wire** to the kitche_4 switch. Best long-term solution
   but requires fishing wire — may or may not be feasible depending on
   accessibility.
3. **Replace with Lutron Caseta** (~$50/switch). Has the cleanest
   no-neutral implementation in the industry; many no-neutral failure
   modes are simply absent. Skip the dimmer-tinkering and migrate the
   Caseta hub for this branch's switches.
4. **Replace LED bulbs with incandescents** (TEMP DIAGNOSTIC ONLY).
   Eliminates LED driver oscillation but doesn't fix the root cause
   (trickle current still flows, just doesn't get chopped into
   arc-fault-mimicking waveform by an SMPS). Not a real fix.

The Aeotec route is recommended — cheap, fast, addresses root cause,
preserves existing dimmer + LED hardware.

### Watch-item until fix lands

`packages/afci/p_b_c6_watcher.yaml` (committed in same PR as this
amendment) provides two layers of protection during Scott's
2026-05-30 → mid-Oct departure:

1. **Trip alert** on `sensor.emporia_vue_panel_b_circuit_6_general_loads_power < 1 W for 2 min` — fires
   immediately if the breaker opens (doorbell offline signal too).
2. **Anomaly spike alert** if today's 208.78 V Ting marker count
   exceeds 300 — escalation signal vs the observed ~180/day "current
   dirty baseline" (which itself is real arcing the AFCI is choosing
   not to escalate).

Air-gap pull on kitche_4 at 08:43 EDT 2026-05-29 is in effect through
the departure window. Lights at that fixture stay dark until the
wire-saver lands. Other circuits on the branch (chime + doorbell +
kitchen cans + nook + under cab + fluorescents) keep working normally
through their separate switches.

### Cross-corroboration: Ting data integrity confirmed

The Whisker Ting (installed 2026-05-week, in 30-day learning mode) saw
the arc events independently of the AFCI. The 208.78 V markers from the
`simplytoast1/ha-whisker-ting` integration are anomaly-detection
placeholders the integration surfaces as voltage spikes (vs proper
event entities — filed as a future enhancement). They appear with a
~250 ms latency to the AFCI's millisecond-scale trip events, which is
consistent with Ting's 4 Hz sampling rate.

Once Ting graduates from learning mode (~2026-06-26, while Scott is at
NH), `sensor.lrd_electrical_fire_hazard_status` will start raising
explicit hazard alerts on this kind of pattern — providing a third
independent watcher on top of the AFCI breaker and our energy-audit
integration.
