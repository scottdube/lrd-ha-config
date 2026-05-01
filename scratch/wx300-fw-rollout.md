# HS-WX300 Firmware Rollout: v2.1.13 → v2.2.0

**Started:** 2026-04-30
**Decision source:** `docs/current-state.md` "Z-Wave fleet housekeeping" in-flight item
**Target firmware:** `WX300-R2_2_2_0.gbl` (extracted from `https://homeseer.com/updates4/WX300-R2_2_2_0.zip`)
**Why:** SDK v7.18.1 → v7.18.8 + Silabs SDK bug fix where R2 (800 Series) WX300s "can stop responding to Z-Wave commands if not manually controlled for some time" (per HomeSeer changelog, verified 2026-04-28). Behaviorally identical otherwise — low-risk update fixing a real intermittent failure mode.

---

## Pre-flight checklist

- [ ] Z-Wave JS UI backup taken (Settings → Backup) — date/time:
- [ ] Firmware file downloaded and extracted to a known path on Mac: `WX300-R2_2_2_0.gbl`
- [ ] Fleet enumerated from Z-Wave JS UI Control Panel (filter by Manufacturer = HomeSeer Technologies)
- [ ] Pilot device selected (criteria: easy physical access, non-critical load, ideally somewhere a brief outage during update is fine)
- [ ] Current time / window confirmed (avoid times when scheduled automations or kids/Mary depending on these switches)

---

## Fleet roster

Status values: `pending` / `in-progress` / `done` / `failed` / `skipped`

| Node | Name | Area | FW before | FW after | Status | Updated at | Notes |
|---|---|---|---|---|---|---|---|
| 003 | Garage Lights | garage | 2.1.13 | 2.2.0 | done | 2026-04-30 | |
| 005 | Garage Cans | garage | 2.1.13 | 2.2.0 | done | 2026-04-30 | Smooth update. Verified post-update. |
| 016 | Lanai Cans | lanai | 2.1.13 | 2.2.0 | done | 2026-04-30 | |
| 018 | Master Bedroom Cans | master_suite | 2.1.13 | 2.2.0 | done | 2026-04-30 | |
| 019 | Garage Outdoor Lights | outside | 2.1.13 | 2.2.0 | done | 2026-04-30 | |
| 020 | Front Entryway Light | entry | 2.1.13 | 2.2.0 | done | 2026-04-30 | |
| 022 | Living Room Cans | living_room | 2.1.13 | 2.2.0 | done | 2026-04-30 | |
| 023 | Dining Room Light | dining_room | 2.1.13 | 2.2.0 | done | 2026-04-30 | Pilot. ~3–5 min update, no anomalies. HA + wall paddle both verified post-update. |
| 025 | Under Cabinet Lights | kitchen | 2.1.13 | 2.2.0 | done | 2026-04-30 | After update, set Param 11 + 12 ramp rates to 0 to fix perceived-dimming issue on non-dimmable load. See `integrations/zwave-js.md` known-patterns for the rationale. |
| 026 | Kitchen Cans | kitchen | 2.1.13 | 2.2.0 | done | 2026-04-30 | Group 2/3 associations to Kitchen 4 Cans preserved through FW update (verified). |
| 027 | Nook Lights | nook | 2.1.13 | 2.2.0 | done | 2026-04-30 | |
| 029 | Toilet Light | master_suite | 2.1.13 | 2.2.0 | done | 2026-04-30 | Name typo fixed 2026-04-30 (was "Toilet.  Light"). |
| 030 | Bathroom Light | master_suite | 2.1.13 | 2.2.0 | done | 2026-04-30 | |
| 031 | Vanity | master_suite | 2.1.13 | 2.2.0 | done | 2026-04-30 | |
| 033 | Master Suite Hall Light | master_suite | 2.1.13 | 2.2.0 | done | 2026-04-30 | |
| 034 | Kitchen 4 Cans | kitchen | 2.2.0 | 2.2.0 | already-current | — | Outlier already on target FW; the reason this rollout exists. |

(16 rows total: 1 outlier already on v2.2.0 + 15 to update.

Source for this enumeration: `/config/.storage/core.device_registry` extracted via Python on 2026-04-30. Entity IDs deliberately omitted — confirm at execution time when each device's HA card is open. HA's standard naming convention typically maps the device name to the entity ID with lowercase + underscores, e.g., "Garage Lights" → `light.garage_lights`.)

---

## Per-device procedure

1. Z-Wave JS UI → Control Panel → click the target node row to expand
2. Confirm "Firmware Version" reads `2.1.13` before starting
3. Click the **Firmware Update** action (icon in the node's action toolbar — typically a small "F" or upload icon)
4. Choose **Local File** and select the extracted `WX300-R2_2_2_0.gbl`
5. Initiate update — watch the progress dialog
6. Wait for **Update successful** confirmation (typically 3–5 min for 800 Series)
7. Re-check Firmware Version — should now read `2.2.0`
8. Functional test: toggle the load from HA (entity card) — confirm the switch physically actuates
9. Mark the row in the table above with status, timestamp, and any notes

Wall-clock target: ~5 min/device × 15 = ~75 min total. Mostly waiting; can bounce away between devices.

---

## Failure recovery

- **Update completes but device unresponsive.** Z-Wave JS UI → click the node → "Ping" action. If still unresponsive, may have lost mesh routes — wait a few minutes and retry. If still dead, may need an air-gap (kill the breaker) + re-include.
- **Update fails mid-flight (controller or device timeout).** Retry once. If still failing, leave that node on v2.1.13, mark as `failed` in the table, continue with the rest. Come back to that node later — likely a mesh/RF issue, not a firmware-image issue.
- **Worst case: device bricked.** Recovery = `Remove Failed Node` from the controller → physically air-gap the device → re-include via Z-Wave JS UI → rename in HA registry (drop any `_2` suffix per the ghost-node pattern in `integrations/zwave-js.md`) → re-establish any group associations (Group 2/3 to physical 3-way add-ons if applicable for that switch).

---

## Wall clock & observations

- Pre-flight start:
- Pilot start:
- Pilot end:
- Rollout start (devices 2 onward):
- Rollout end:
- Total elapsed:

### Observations / quirks

(Document anything surprising during the pilot — timing oddities, UI quirks, post-update behavior — so the rest of the rollout benefits.)

---

## Post-rollout closeout

- [x] All 16 WX300s confirmed on v2.2.0 / SDK v7.18.8 (verified 2026-04-30 in Z-Wave JS UI Control Panel; controller status "Ready")
- [x] `docs/device-inventory.md` back-filled with node numbers / locations / entity IDs from this rollout (12 entity IDs marked `(inferred)` — strip annotation as you confirm them in HA at your leisure)
- [x] `docs/current-state.md` updated: HS-WX300 FW divergence removed from "Z-Wave fleet housekeeping" in-flight; rollout summary added to Recently completed
- [x] All 16 WX300s now have friendly names set in Z-Wave JS UI (previously "NodeID_X" placeholders) — Scott did this during the rollout
- [x] Pattern captured in `integrations/zwave-js.md` known-issues: WX300 + non-dimmable load → set Params 11+12 ramp rates to 0 (verified on node 25)
- [x] Node 029 renamed from "Toilet.  Light" (typo) to "Toilet Light" in HA + Z-Wave JS UI
- [ ] No ADR warranted — operationally interesting but architecturally routine

**Side note for future hygiene:** the location string "Living Room Cans → Great Room" in Z-Wave JS UI doesn't match HA's `area_id` of `living_room`. Cosmetic only; align if/when you next touch Z-Wave JS UI names.
