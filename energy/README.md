# Energy

Whole-home power monitoring — circuit-level visibility into the household energy budget.

This sub-project covers hardware install, integration with Home Assistant, per-circuit calibration, and ongoing analysis of the ~$320/month "everything else" bucket from the bill decomposition. Adjacent to but distinct from pool energy monitoring (which lives in `pool/` and is captured natively via the OmniLogic + Midea AC LAN integrations).

---

## Status

**Phase: Planning** (2026-05-02). Hardware not yet purchased. See `docs/decisions/009-whole-home-power-monitoring.md` for the decision context, hardware comparison, and pre-purchase checklist.

---

## Why this exists

The 2026-04-08 SECO Energy bill jumped +2025 kWh from March to April. Pool work (ADR-006) addresses ~50% of the increase. HVAC actually decreased. The remaining ~$320/month "everything else" bucket — water heater, refrigerator, freezer, lighting, electronics, EV (if applicable), phantom loads — has no instrumentation today.

Without per-circuit visibility, we can't:
- Identify which appliance is driving consumption
- Detect anomalies (failing water heater element, EV charger drawing more than spec)
- Build a predictive maintenance signal for major appliances
- Validate that pool / HVAC tuning is delivering its expected savings (because we have no whole-home denominator)

Whole-home power monitoring fixes that gap.

---

## Structure

```
energy/
├── README.md                ← this file
├── docs/
│   ├── circuit-map.md       ← per-CT mapping to breaker / load (post-install)
│   ├── install-notes.md     ← physical install record
│   └── calibration.md       ← per-circuit calibration verification
└── analysis/
    └── (notebooks, monthly trend exports — future)
```

---

## Hardware (decision pending — see ADR-009)

Two paths under consideration:

| | Emporia Vue 2 | IotaWatt |
|---|---|---|
| Cost (full kit) | ~$170–200 | ~$400–500 |
| Cloud-required? | Yes | No |
| HA integration | `emporia_vue` (HACS) | `iotawatt` (core HA) |
| Open source | No | Yes |
| Maker fit | Moderate | Strong |

Recommendation in ADR-009 leans IotaWatt for local-first principle. Final call deferred.

---

## Pre-purchase checklist

Before ordering anything:

- [ ] Photograph the SECO Energy panel directory (current breaker labels + amperages)
- [ ] Identify circuits to monitor (priority list — see below)
- [ ] If IotaWatt: tally required CT amperages
- [ ] Schedule a 1-hour install window with breaker access
- [ ] Confirm HACS integration availability for chosen device

---

## Priority circuits to monitor (proposed, refine before install)

Highest-ROI first:

1. **Mains** (both legs, 200A CTs) — total household consumption, validates install via `mains = Σ(circuits)`
2. **Water heater** — likely #1 hidden consumer
3. **Pool subpanel** (if separate) — cross-validate against `local_filter_power` + `local_heater_estimated_power_w`
4. **Main HVAC** — cross-validate against Carrier daily kWh
5. **Garage mini-split** — cross-validate against Midea AC LAN realtime power
6. **Refrigerator + freezer** (separate CTs if separate circuits)
7. **Kitchen general** (range, microwave, dishwasher — usually one or two circuits)
8. **Laundry** (dryer especially — second-biggest 240V load typically)
9. **EV charger** if installed
10. **Outdoor / pool equipment circuit** (chlorinator, lights, pumps not on pool integration)
11. **Master suite** (HVAC mini-split, electronics, etc.)
12. **Living room / great room** (TV, A/V)
13. **Office / electronics** (phantom load aggregation)
14. **Network equipment** (UDM Pro, switches, NUC, AP — for HA infrastructure cost tracking)

Reserve 1–2 spare CT slots for diagnostic work (move temporarily to investigate a suspect circuit).

---

## Integration with HA

Once installed, data flows into HA via the chosen integration's HACS or core component. Per-circuit W readings become entities like `sensor.<circuit_name>_power`.

`pool/scripts/state_logger.py` will be extended to capture each as a `home_*` column in `pool_state_log.csv` (eventually renamed to `home_state_log.csv` per the long-term plan in `pool/docs/logger-v2.md`).

---

## Cross-validation opportunities

Once installed, we can cross-check:

- **`home_pool_subpanel_w` vs. `local_filter_power + local_heater_estimated_power_w`** — should match within a few % during steady state. Discrepancy = something else on the pool subpanel (chlorinator, light) that's not yet captured.
- **`home_main_hvac_w` × time vs. Carrier `cooling_energy_yesterday`** — daily integration of measured W should match Carrier's reported daily kWh ± a few %. Discrepancy = either CT calibration error or Carrier reporting bug.
- **`home_garage_minisplit_w` vs. `garage_ms_power_w`** (already captured from Midea) — same value reported by two independent sources. Disagreement = wiring fault or one source is wrong.
- **`home_total_w` vs. SECO meter reading** (manual once-per-bill-cycle) — daily integration vs. utility-reported kWh. Validates the entire chain.

---

## Long-term direction

- ADR-009: hardware decision (this ADR).
- ADR-010 (later): per-circuit allocation strategy + budget categories.
- Auditor assertions extended to home-power baseline detection.
- If solar/battery ever enters scope, revisit the energy-monitoring choice — some platforms support production/import/export natively. Currently no solar/battery on horizon.

---

## Related

- `docs/decisions/009-whole-home-power-monitoring.md` — full ADR with hardware comparison
- `pool/scripts/state_logger.py` — logger to extend
- `pool/docs/data-schema-v2.md` — schema doc to extend
- `pool/docs/auditor.md` — auditor to extend (eventually)
- `docs/current-state.md` — track install + commissioning status
