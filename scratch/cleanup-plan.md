# Cleanup Plan

Bring-up tasks left over from the move from one-off Claude chats to the Cowork project. Knock these off as time permits. Delete this file when Phases 1-4 are done.

**Created:** 2026-04-28
**Status legend:** `[ ]` not started · `[~]` in progress · `[x]` done

---

## Phase 1 — Foundation (~60 min total, any order)

### 1.1 Reconcile `README.md` to actual structure ✅
Completed 2026-04-28.

- [x] Add `custom_components/`, `tts/`, `www/`, `esphome/`, `config/` to the structure block
- [x] Change `automations/` → `automations.yaml`
- [x] Document dashboards: HA UI/storage-based (not YAML in repo)
- [x] Add `pool/`
- [x] Bonus: noted runtime gitignored files inline; clarified Mac/NUC clone relationship at top

**Done when:** README structure block is a true map of the repo. ✅

### 1.2 Voice-satellites becomes the home for voice work (Option A) ✅
Completed 2026-04-28.

- [x] Move `esphome/voice-garage.yaml` → `voice-satellites/esphome/voice-garage.yaml`
- [x] Decide fate of root-level `esphome/` folder — deleted (only contained voice-garage.yaml + ESPHome's stock .gitignore, which moved with it)
- [x] Create `voice-satellites/enclosures/README.md` (Fusion CAD location flagged as TODO for Scott to fill in)
- [x] Drop a stub `voice-satellites/README.md` summarizing current state, hardware on hand, planned locations
- [x] Update root README.md structure block

**Done when:** voice-satellites/ has real content; esphome/voice-garage.yaml no longer at root. ✅

**Follow-up for Scott:** fill in the Fusion CAD location in `voice-satellites/enclosures/README.md` (currently TODO).

#### 1.2 partial revert (2026-04-28 evening)
The `voice-satellites/esphome/` location turned out to be incompatible with ESPHome's dashboard. Its `rel_path()` security check captures `absolute_config_dir` un-resolved but resolves submitted paths through symlinks; with `/config/esphome -> /config/voice-satellites/esphome`, the resolved path is no longer a subpath of the un-resolved root, and validate / compile silently fail with `ValueError`. Tried both directory-level and file-level symlink workarounds; the directory-level one breaks compile, the file-level secrets symlink works fine.

Outcome: ESPHome configs moved BACK to repo root `esphome/` (which maps to `/config/esphome/` on the NUC, where the dashboard expects them). `voice-satellites/` retains `docs/`, `enclosures/`, and `README.md` for non-firmware artifacts. Voice satellite work still owns the surrounding context, just not the YAML location.

- [x] Move `voice-satellites/esphome/voice-garage.yaml` → `esphome/voice-garage.yaml` (git mv)
- [x] Move `voice-satellites/esphome/.gitignore` → `esphome/.gitignore` (git mv)
- [x] Remove now-empty `voice-satellites/esphome/`
- [x] Update `voice-satellites/README.md` to drop the broken symlink workaround and document the new structure
- [x] Update root `README.md` structure block

### 1.3 Relocate pool_temp_logger.py to a `pool/` domain ✅
Decision: pool gets its own root-level domain folder to host current logger plus future predictive-heating analysis.

Completed 2026-04-28. New path live, automation cycle verified, CSV gitignored.

- [x] Create folder structure:
  ```
  pool/
  ├── README.md            — what's here, data location, schema, ML plans
  ├── scripts/
  │   └── temp_logger.py   — moved + renamed (drop "pool_" prefix)
  ├── docs/
  │   └── data-schema.md   — CSV columns, units, "unknown"/"unavailable" semantics
  └── analysis/
      └── .gitkeep         — future notebooks/models
  ```
- [x] Move `pool_temp_logger.py` → `pool/scripts/temp_logger.py`
- [x] Update `configuration.yaml` `shell_command.pool_log` path: `python3 /config/pool/scripts/temp_logger.py`
- [x] LOG_FILE kept at `/config/pool_temp_log.csv` (runtime data location unchanged)
- [x] Add `pool_temp_log.csv` to `.gitignore`
- [x] Clean known-bad rows from existing CSV: dropped `water_temp=unknown` (39 rows, 2026-04-08 → 2026-04-10, attributable to mix of WiFi packet loss and a separately-fixed integration bug) and `pump_speed=unavailable` (2 rows, 2026-04-15). One-liner on the NUC:
  ```bash
  cd /config && cp pool_temp_log.csv pool_temp_log.csv.bak && \
    awk -F',' 'NR==1 || ($2!="unknown" && $6!="unavailable")' pool_temp_log.csv > pool_temp_log.csv.tmp && \
    mv pool_temp_log.csv.tmp pool_temp_log.csv
  ```
- [x] Restart HA, confirm next 10-min poll writes a fresh row (verified 2026-04-28 12:40:13 row from new path)
- [x] `git status` should NOT show pool_temp_log.csv as modified after the next pump cycle (verified)

**Done when:** new row appears in CSV after restart AND the CSV is no longer tracked by git. ✅

### 1.4 Resolve `scratch/setup-instructions.md` ✅
Deleted 2026-04-28. Cleanup-plan.md supersedes as the bring-up tracker.

- [x] **A.** Delete it. This cleanup-plan.md replaces it as the bring-up tracker.

**Done when:** the file's status is unambiguous. ✅

---

## Phase 2 — Integration notes scaffolding (~45 min)

### 2.1 Stub the missing integration notes ✅
Completed 2026-04-28. Stubs ended up beefier than 5-line minimums; Z-Wave JS in particular got real content.

- [x] `integrations/zwave-js.md` — fleshed (controller, known patterns, escalation steps)
- [x] `integrations/weatherflow.md` — fleshed (cloud + local plan, entity table, mm/inch quirk)
- [x] `integrations/midea-ac-lan.md` — stub with TODOs for entity ID and quirks
- [x] `integrations/unifi-protect.md` — stub with TODOs for camera enumeration and motion alert wiring
- [x] `integrations/nabu-casa.md` — stub with TODOs for entity audit and renewal date

**Done when:** `integrations/` has 6 files (omnilogic + 5 new). ✅

**Follow-up TODOs embedded in the new files** (review when you next touch each integration):
- ~~weatherflow: capture Tempest station ID; verify exact integration name~~ — done (ST-00184974, weatherflow + weatherflow_cloud both active)
- ~~midea-ac-lan: verify HACS fork; capture climate.* entity ID~~ — done (wuwentao fork, climate.garage_mini_split, 192.168.11.228)
- ~~unifi-protect: enumerate cameras with locations + entities~~ — done (11 cameras catalogued); motion alerts wiring still backlog
- ~~nabu-casa: subscription renewal date; audit 573 exposed-to-Assist entities~~ — done (trial expires 2026-05-04 ⚠️ urgent; exposure now 45 entities)

**Phase 2 complete 2026-04-28.**

### 2.2 Per-integration detail fill (ongoing, no deadline)
Treat each `integrations/<name>.md` as a target of opportunity. When you touch the integration in real work, fill in what you learn. Not a single task — a habit.

---

## Phase 3 — Device inventory (~45-60 min, single sitting)

### 3.1 Fill `docs/device-inventory.md` gaps
Open Z-Wave JS UI side-by-side. For each `?` row: node ID, FW version, location, entity ID. Add rows for any device not currently listed.

- [ ] Z-Wave devices: zero `?` markers remaining
- [ ] Remove the "Inference flag" warning at the top once complete
- [ ] Verify: pick 3 random rows, confirm against actual device

**Done when:** zero `?` markers in the Z-Wave table.

This is the single highest-payoff cleanup item. It's the file you'll grep at 11pm when something breaks.

---

## Phase 4 — Stale entity cleanup (~45 min total)

### 4.1 Fix `light.wall_dimmer_switch3` references
- [ ] Find owning automation (lines 16, 192 of `automations.yaml`)
- [ ] Decide: rename to current entity OR delete if obsolete (Hubitat-era ghost)
- [ ] Verify: `grep wall_dimmer_switch3 automations.yaml` returns nothing

**Done when:** grep is empty.

### 4.5 HS-WX300 fleet FW rollout v2.1.13 → v2.2.0 (~90 min, 15 devices × ~5 min)

Verdict from comparing release notes 2026-04-28: worth doing. v2.2.0 is SDK v7.18.1 → v7.18.8 + a fix for a Silicon Labs SDK bug where R2 (800 Series) WX300s "stop responding to Z-Wave commands if not manually controlled for some time." Low-risk update, no behavioral changes.

**Important:** the Z-Wave JS UI per-device "firmware up to date" indicator may show **all 15 as current** even though they're on v2.1.13 and v2.2.0 exists. This is a known Z-Wave ecosystem quirk: the indicator compares against the OpenSmartHouse / Z-Wave JS device DB, which may not have v2.2.0 indexed yet (HomeSeer's release was relatively recent). The actual fix is a manual flash:

1. Download the firmware file from HomeSeer: `https://homeseer.com/updates4/WX300-R2_2_2_0.zip` — unzip to `.gbl`.
2. In Z-Wave JS UI → Control Panel, click each HS-WX300 node.
3. In the node detail pane, find the "Firmware Update" section.
4. Choose "Update Firmware via File" (not the built-in OTA list, which is what shows "up to date").
5. Upload the `.gbl` file, start, wait.
6. After flash, verify FW reads `v2.2.0` in the Control Panel row.

Sequence the flash from controller-nearest nodes outward. Take a Z-Wave JS controller backup before starting (Settings → Backup).

- [ ] Download `WX300-R2_2_2_0.gbl` to NUC
- [ ] Z-Wave JS controller backup
- [ ] Flash 15 nodes: 003, 005, 016, 018, 019, 020, 022, 023, 025, 026, 027, 029, 030, 031, 033
- [ ] Verify all show v2.2.0 in Control Panel after completion

**Done when:** all 16 HS-WX300 nodes (including 034 already on v2.2.0) report v2.2.0.

### 4.2 Rename `light.dimmer_2_2` (cosmetic)
- [ ] Settings → Devices & Services → Fibaro FGD212 → entity rename → "Lamp Post - Unused Channel"

**Done when:** entity registry shows the friendly name.

### 4.3 Resolve `valve.omnilogic_pool_waterfall_2` ghost
Discovered 2026-04-28. Active blueprint instance in `automations.yaml` line 532 references `valve.omnilogic_pool_waterfall_2` (ghost suffix), while the canonical entity is `valve.omnilogic_pool_waterfall`.

- [ ] Determine which entity is "real" (check Settings → Devices & Services → OmniLogic Local)
- [ ] Delete the orphan in registry; rename the survivor to canonical name if needed
- [ ] Update the blueprint instance to point at the canonical entity

**Done when:** only one waterfall valve entity exists; blueprint instance points at it.

### 4.4 Verify Pool Automation blueprint version
Discovered 2026-04-28. The active automation alias is `Pool Automation v1.7.0` but the blueprint file on disk is v1.8.0. Almost certainly the alias is just stale text and HA is using v1.8 (blueprint files are loaded by path, not version). Verify and refresh the alias.

- [ ] Open the automation in HA UI, confirm it's referencing `LRD/pool_automation/pool_automation.yaml` (latest on disk)
- [ ] Re-save the automation so its alias regenerates as `Pool Automation v1.8.0`
- [ ] Spot-check one v1.8-only behavior (waterfall as `valve.*`, not `switch.*`)

**Done when:** alias matches the blueprint version on disk.

---

## Phase 5 — ADR backfill (~15 min)

### 5.1 ADR-005: OmniLogic transport (WiFi → ethernet)
- [ ] Write 1-page ADR: context (~30-40% packet loss), decision (ethernet), state (temp run live, Shepard pending exterior wall pass-through), consequences (UDP fragment timeouts gone)

**Done when:** `docs/decisions/005-omnilogic-transport-ethernet.md` exists.

### ~~5.2 ADR-006 Hubitat retirement~~
Skipping. Chat index already captures it; ADR adds no value.

### 5.3 Backlog: pool predictive-heating data foundation
**Not a Phase 5 task — a backlog seed.** Logger currently only runs when pump is on, blinding the dataset to overnight water-temp decay vs. OAT. That's the most predictively valuable window for "what time should pump start tomorrow to hit 89°F by 11:00."

- [ ] Add a second `Pool Temp Logger (Idle)` automation: every 30 min while pump is OFF, log water_temp + OAT + outdoor humidity to a separate CSV (or same CSV with a `mode` column)
- [ ] In `pool/docs/data-schema.md`, document the known-bad event (2026-04-08 → 2026-04-10) where 39 rows had `water_temp=unknown` due to mixed WiFi/integration-bug causes. Note this was cleaned out of the CSV at the time of the cleanup-plan execution; future analysts won't see those rows but should be aware they existed.
- [ ] Plan: ~6 months of data before meaningful modeling

Move to `current-state.md` backlog when you're ready to scope it.

---

## Tracking

Update checkboxes inline as items complete. No need to maintain a parallel list in `current-state.md` — that file stays focused on real in-flight work (pool, voice satellites, network move). Once Phases 1-4 are all `[x]`, delete this file. Phase 5.1 can land any time after that.

## When to delete this file

When Phases 1-4 are complete. Phase 5.3 graduates to `current-state.md` backlog before then.
