# Current State

Active working notes. Update as work progresses. This is the file Cowork should reference most often when answering "where are we on X?"

**Last updated:** 2026-05-01 (pool automation incident — uncovered blueprint design issue + observability gap; ADR-006, logger v2 spec, auditor spec drafted)

---

## In flight

### Pool automation
- **Blueprint version:** v1.8.0 (deployed); **v1.9.0 deployed 2026-05-02, post-deploy fix in repo** (per ADR-006). Initial v1.9.0 had a short-circuit bug — HEATER+SPEED branch was getting bypassed by WATERFALL ON's always-matching condition during 08:00–20:00. Maintenance moved out of the inner `choose:` so it runs every poll regardless. Pending push + restart to take effect.
- **Pump speed inputs tuned 2026-05-02:** `normal_pump_speed: 55`, `heater_pump_speed: 65` (down from defaults 65/77). Empirically validated values from Scott's prior tuning. ~17% additional reduction in pump consumption on top of v1.9.0 via cube-law. Bill analysis estimates ~$390/year savings vs. pre-v1.9.0 baseline at his SECO Energy rate ($0.136/kWh effective). Watch for HeatPro low-flow faults — if any appear during heating cycles, raise `heater_pump_speed` back toward 70-75.
- **April 2026 bill spike decomposed (2026-05-02 via Carrier app data):** Mar→Apr bill jumped +2025 kWh (2526→4551). HVAC actually *decreased* −245 kWh (Mar 1007 → Apr 762, sum of main + master mini-split). The +2025 kWh increase is dominated by pool: pump turning on 24/7 (~500 kWh) + heat-pump compressor running for water-temp recovery (~900–1100 kWh estimated; real measurement pending via `local_filter_power` once logger v2 captures a few days). HVAC is ~18% of total daily load (~25 kWh/day in April), pool is ~30%+, "everything else" is ~45%. Big "everything else" bucket (~65 kWh/day = ~$265/month) is the next investigation target — water heater, fridge, electronics, phantom loads. Whole-home power monitoring (Emporia Vue 2 or IotaWatt) is the natural next step for visibility into this bucket. Future ADR.
- **Heater logic:** set-and-hold — heater on if swim day, off if not. Heat pump owns cycling. **Open issue (ADR-006):** blueprint conflates heater-`on` (enabled/ready) with heater-actively-delivering. Result: pump runs 24/7 at 77% on swim-day stretches even when compressor is idle. Confirmed in 2026-04-28→05-01 CSV: 595 pump-on rows, 0 pump-off rows. Empirically validated 2026-05-01 via Hayward cloud activity log — heater compressor only ran 04:02–06:47 EDT (2h45m) yet pump ran 24h. **Signal source identified:** local `binary_sensor.<heater_equip>_heater_equipment_status` (compressor active boolean from `pyomnilogic_local.HeaterState`) plus cloud `water_heater` state as cross-validation. Blueprint v1.9.0 ready to implement.
- **Waterfall:** runs independently of pump_is_on (v1.6 change). **Orphan-entity confusion fully resolved 2026-05-02** — initial 2026-05-01 fix pointed everything at `valve.omnilogic_pool_waterfall_2`, but Developer Tools → States verification on 2026-05-02 showed the live entity is actually `valve.omnilogic_pool_waterfall` (no suffix). `_2` was/is the orphan. Reverted: blueprint waterfall_switch input, configuration.yaml shell_command, templates.yaml dashboard sensor, and state_logger.py all now point at the unsuffixed entity. **This is also why v1.9.0 didn't appear to do anything overnight** — the WATERFALL END branch's `is_state(waterfall_switch, 'open')` check was returning False against the orphan, so the pump-shutoff path never fired.
- **Integration:** OmniLogic Local on `1.0.4` (stable). Cloud retained for ORP/salt/pH monitoring only.
- **Network:** Temporary ethernet run to OmniLogic controller — confirmed reliable on 2026-04-30 evening (zero errors over 7 hours). Permanent run mostly done — waiting on Shepard Electric to route through exterior wall (currently dangling from soffit).
- **Open: midnight error burst on local integration** — discovered 2026-05-01 while diagnosing waterfall incident. ~18 `Failed to update data from OmniLogic` errors clustered 00:27–01:00 EDT, plus scattered isolated errors through 01:00–07:00. Evening hours zero errors. Cloud unaffected throughout. Pattern fits controller-side scheduled housekeeping rather than network instability. Needs multi-night confirmation. Full analysis: `scratch/omnilogic-local-midnight-burst-2026-05-01.md`.
- **Issue #173 resolved** in newer releases of `cryptk/haomnilogic-local`.

### Pool observability rebuild
Initiated 2026-05-01 after the waterfall incident exposed multiple blind spots in the existing logger (conditional on pump=on, captured wrong waterfall entity, no auditing). Three artifacts drafted, all awaiting review before implementation:

- **ADR-006** (`docs/decisions/006-actively-heating-vs-enabled.md`) — pump flow tied to compressor demand, not heater enabled state. Signal sources confirmed (local binary_sensor + cloud heater state). Includes additional v1.9.0 changes: swim_day guards on PUMP START + WATERFALL ON branches, poll-cadence shift (`:00→:05`) to dodge midnight burst. Amends ADR-002.
- **Logger v2 spec** (`pool/docs/logger-v2.md`) — always-on logging, captures local + cloud side-by-side for cross-validation, expected-state columns, transition events, action log, fixed entity references. ~60 columns, single CSV with `local_*`/`cloud_*` prefixes.
- **Auditor spec** (`pool/docs/auditor.md`) — nightly script that asserts daily-shape, pump, waterfall, heater, integration-health expectations against logger output. Failures push to mobile. Phase 1 catches the valve-stuck-open class of bug. Add new H4 (local-vs-cloud heater agreement) and H5/H6 (ADR-006 verification) once v1.9.0 ships.

**Sequencing:** Find heater_equip binary_sensor entity ID → logger v2 phase 1 (parallel, non-breaking) → blueprint v1.9.0 fix → logger v2 phase 2+ → auditor phase 1.

**Logger v2 phase 1 in flight (2026-05-02):** `pool/scripts/state_logger.py` written, `shell_command.pool_state_log` and `automation.pool_state_logger_v2` added. ~30 columns, local + environmental, always-on (no pump-on gate). Awaiting (a) long-lived access token saved to `/config/.state_logger_token` on the NUC, (b) commit/push, (c) HA restart. Cloud columns + state-change triggers + trusted-temp + rsync backup are phase 1.5/2/3.

### Voice assistant satellites (ESPHome)
- **First unit:** garage. Wired and flashed. Recovered 2026-04-28 from a stuck `voice_assistant.on_error` (pipeline pointed at a removed Ollama conversation entity — see ADR-003 for the canonical-vs-alternative pipeline policy).
- **Pipeline (LRD Voice Assistant):** HA Cloud STT, HA Cloud TTS (Davis voice, High quality), OpenAI Conversation as agent with "Prefer handling commands locally" ON (local first, OpenAI fallback). Per ADR-003 revised 2026-04-28. Ollama is supported as an alternative agent but not default.
- **Open issue:** Sporadic audio quality (clears up intermittently). Suspected I2S clock drift on ESP32-S3 with esp-idf driver. **Next step:** test fixed MCLK pin on MAX98357A.
- **Enclosure:** golf-ball-on-tee design in Fusion 360 for garage unit. Prototyping in alt-color PLA before final print. M3 heat-set inserts: 4.91mm OD, need 4.5mm holes.
- **Hardware on hand:** 6× ESP32-S3 N16R8, 5× MAX98357A, 5× INMP441. 5 more units to build.
- **ESPHome firmware location:** `esphome/` at repo root → maps to `/config/esphome/` on the NUC. The earlier `voice-satellites/esphome/` location was reverted because ESPHome dashboard's `rel_path()` validation is incompatible with directory-level symlinks.

### Nabu Casa subscription decision (URGENT)
- **Trial expires 2026-05-04** (~6 days). Decision required: subscribe or lapse.
- **What lapse breaks:** Cloud STT/TTS (voice satellites go red), Alexa Smart Home control of HA (18 entities), primary remote access (WireGuard not currently configured as alternative), stable `*.ui.nabu.casa` URL.
- **Cost:** annual subscription. See `integrations/nabu-casa.md` for full impact analysis.
- **Recommended:** subscribe given the cross-cutting dependencies. Local Whisper + Piper is a feasible long-term alternative for STT/TTS but isn't built; Alexa bridge has no local equivalent.

### Z-Wave fleet housekeeping
- **Toilet fan (ZEN75, node 256) is dead** after a strange firmware update. Needs reinclusion or recovery. `device-inventory.md` had this as `?` — now confirmed.
- **Kwikset 916 (node 038) battery at 30%** — replacement window opening. Other Kwikset (node 008) at 100%.

---

## Recently completed

- **HA config auto-pull from git wired.** Time-pattern automation (`HA Config Auto-Pull from Git`, every 15 min) calls `shell_command.git_pull_config` with `--ff-only`. Mobile push notifies on actual changes and on failures (e.g., divergent local edits blocking ff-only). Eliminates the manual NUC-pull step that caused state drift earlier today.
- **Temporary ethernet run to OmniLogic controller** in place and functioning perfectly. WiFi packet loss issue (~30-40%) eliminated. Permanent run mostly done — Shepard Electric to finish exterior wall pass-through.
- **OmniLogic Local upgraded to `1.0.4`** (stable, off beta).
- **GitHub issue #173 (cryptk/haomnilogic-local)** resolved by dev team in newer integration releases.
- **Switch→valve domain migration** for OmniLogic waterfall (blueprint v1.8.0).
- **Lanai lights blueprint v1.5** — door-activated with lux/sun fallback, skip-if-on guard. All 4 test paths verified. Live.
- **HA NUC migrated from IoT VLAN to LRD-Servers VLAN** (network-docs ADR-009, executed 2026-04-29). New primary IP: `192.168.50.11`. Pre-flight pcap missed broadcast/multicast traffic class — discovered post-cutover when WeatherFlow Tempest local integration silently stopped receiving data.
- **Dual-VLAN recovery via `eno1.4` sub-interface** (network-docs ADR-011, 2026-04-29). HA OS now trunked: native VLAN LRD-Servers on `eno1` (`192.168.50.11`, gateway `.50.1`), tagged VLAN IoT on `eno1.4` (`192.168.11.155`, no gateway, IPv6 disabled, passive listener only). Tempest local data flow restored within ~60 seconds. Persistence handled by HA Supervisor (`ha network vlan` command). Don't delete `eno1.4` — also load-bearing for any future broadcast/multicast-dependent local integrations.
- **HA `http.server_host` bound to LRD-Servers IP + localhost only** (ADR-005, 2026-04-30). Prevents IoT-side exposure of `:8123` web UI now that HA is dual-homed. Editor pitfall logged: HA File Editor add-on mangles YAML list form on save — use SCS or SSH+nano for list-valued config edits. (Recovery from this incident is what prompted the GitHub repo reconciliation; configuration.yaml committed as `3ba3983`.)
- **HS-WX300 fleet FW rollout: 15 devices upgraded v2.1.13 → v2.2.0** (2026-04-30). All 16 HS-WX300s now on FW v2.2.0 / SDK v7.18.8 (closes the divergence with node 034). Fixes Silabs SDK 7.18.1 bug where R2 800-Series WX300s "can stop responding to Z-Wave commands if not manually controlled for some time." Process logged in `scratch/wx300-fw-rollout.md`. Side outcomes: all 16 nodes now have friendly names set in Z-Wave JS UI (previously "NodeID_X" placeholders); node 029 renamed from "Toilet.  Light" to "Toilet Light" (typo fix); node 025 (Under Cabinet Lights) had Params 11+12 ramp rates set to 0 to fix perceived-dimming on non-dimmable load (pattern documented in `integrations/zwave-js.md`); `docs/device-inventory.md` back-filled with all 16 WX300 node IDs / locations / entity IDs.
- **Auto-pull persistent_notification.create added** (2026-04-30). Auto-pull automation now fires bell-icon persistent notifications alongside mobile push, so success/failure events are durable in HA UI even after iOS notification dismiss.
- **Durable SSH-key auth on NUC SSH shell** (2026-04-30). Generated ed25519 key, registered with GitHub, configured `pushInsteadOf` rewrite. Push uses SSH (no prompts), fetch/pull stays HTTPS so the auto-pull container's anonymous read path is unaffected.
- **Hubitat retired.** All Z-Wave devices migrated to Z-Wave JS. Last device was Fibaro Dimmer 2 on lamp post.
- **Studio Code Server clipboard issue** — workaround: open SCS in own tab (not iframe).
- **Midea AC LAN integration** added for `38MARBQ24AA3` mini split.
- **GitHub workflow established.** `lrd-ha-config` repo set up. Studio Code Server terminal handles git locally on the NUC.

---

## Backlog / not yet started

### Automations to build
- **Away mode** — single trigger: lights off, thermostat setback, security armed. Pieces exist; needs assembly.
- **Welcome home** — lights on, thermostat resume, recirc pump on (partial).
- **Vacation mode** — explicitly mentioned as wanted.
- **Kitchen + Great Room lux-based lighting** — site orientation darkens these rooms before sundown, so lux is the right trigger.
  - **Trigger / signal hierarchy** (designed so future indoor sensors slot in without a rewrite): future indoor lux sensors (when added) → Tempest local API illuminance (current primary) → sun elevation (fallback if Tempest stale/unavailable). Priority chain, not a vote.
  - **Presence gate:** `binary_sensor.household_occupied` — template sensor that ORs `person.*` entities, where each person is fed by HA Companion GPS *and* UniFi network device_tracker as a backup (handles GPS dropout / iOS background-location flake). Hysteresis on the OFF transition only (5–10 min) to prevent transient GPS loss from killing lights while we're home. Build this sensor as a reusable primitive — vacation automations and welcome-home will reuse it.
  - **Vacation guard:** honors cross-cutting `input_boolean.vacation` (see below).
  - **Resolved design decisions:**
    - **ON-only automation.** Other automations / wall switches / bedtime routines own OFF. Mirror lanai v1.5 skip-if-already-on guard so it never overrides a manual ON.
    - **Lights are a blueprint input** (selector for one or more `light` entities), not hardcoded — same blueprint can serve other rooms later.
  - **Pre-build verification:**
    - iOS Private Wi-Fi Address must be **Fixed** or **Off** on home SSID for both phones (NOT Rotating). Fixed = stable randomized MAC per-SSID, fine for tracking. Rotating = changes every 2 weeks, breaks tracking. WPA2+ networks default to Fixed, so usually no change needed.
    - In UniFi: rename the iPhone clients (`iPhone-Scott`, `iPhone-Wife`) so the picker isn't a guessing game; clean up stale "iPhone" entries from earlier Rotating-mode history.
    - Confirm UniFi Network integration is installed in HA and `device_tracker.iphone_*` entities report `home`/`not_home` correctly.
  - **Pattern reference:** lanai lights blueprint v1.5 (lux/sun fallback already proven), but trigger model differs — lanai is door-activated, this is lux-state-driven.
- **Carrier Infinity presence-aware setback** — Florida AC cost optimization. Reprioritized 2026-05-02: lower urgency than initially thought given HVAC was only ~18% of April daily load (vs. pool ~30%+). Best ROI is during winter heating months (main unit ran 878 kWh in March). Build after pool work stabilizes.
- **Camera motion alerts when away** — UniFi cameras already integrated.
- **Lanai fan presence + temp control** — fans on when occupied AND lanai temp above threshold X. Maybe staged speeds: e.g. low at 78–82°F, medium at 82–86°F, high at 86°F+. Uses the same `binary_sensor.household_occupied` primitive being designed for kitchen/great-room lux. Need: lanai temp sensor (Tempest OAT may be a reasonable proxy until a local one is added), fan speed control entities, presence gate. Decide whether to gate by HVAC state too (don't run lanai fans if AC is on doors-open).

### Cross-cutting automation patterns to add
- **`input_boolean.vacation` guard** — add a vacation helper and retrofit it as a condition on presence/lux/welcome-home style automations so they no-op while we're out of town. New automations (kitchen/great-room lux, welcome home, etc.) should include this guard from day one. Decide whether vacation mode itself should auto-set this, or keep it manual via dashboard toggle.

### Voice satellites
- 5 more units to build after garage proves out.
- Decide locations: kitchen, master bedroom, lanai, ?, ?

### Integrations to evaluate
- **ChefsTemp** — feature-request email drafted but not sent (waiting on Breezo support reply first). BLE proxy possible if API not granted.
- ~~WeatherFlow Local~~ — done. Both local and cloud integrations active; see `integrations/weatherflow.md`.

### Cleanup
- ~~Audit 573 entities exposed to Assist~~ — done. Now 45 exposed.
- ~~Turn off "Expose new entities" default~~ — done (Assist, Alexa, Google all OFF for new entities).
- Phantom entity on Fibaro Dimmer 2 (`light.dimmer_2_2`) — unexposed but worth final rename for clarity.
- **Periodic voice pipeline audit** — Settings → Voice Assistants → confirm each pipeline's conversation agent still exists. Stale agent references silently break devices. See ADR-003 operational notes.
- **Disable or finish Google Assistant cloud bridge** — currently enabled in HA Cloud but never linked to Google Home app. Either complete the smartphone setup or turn off the toggle to clean up.

---

## Known issues

### LRD: Fibaro FGD212 dual-channel exposure
- Device exposes both channels as light entities. Lamp post is wired to one. Other is real-but-unwired.
- **Fix applied:** unexposed phantom from Assist.
- **Optional:** rename `light.dimmer_2_2` → "Lamp Post - Unused Channel" for clarity in dashboards.

### OmniLogic dead nodes / orphan entities
- Periodic cleanup needed when devices fail/are replaced.
- Pattern: re-include creates `_2` suffix entity; original orphan must be deleted from registry first.

### "Hey Nabu" wake word — sometimes slow
- Server-side openWakeWord adds latency vs on-device.
- **Decision:** accept for now. On-device wake word is microWakeWord on ESP32-S3 (revisit later).

### `light.wall_dimmer_switch3` reference in automations.yaml (lines 16, 192)
- Stale reference from Hubitat migration, breaks no automation but fills logs with warnings.
- **TODO:** find owning automation, fix entity ID or delete if obsolete.

---

## Decision log (active references)

See `docs/decisions/` for full ADRs. Quick reference:

| ADR | Decision |
|---|---|
| 001 | OmniLogic Local for control, Cloud for monitoring only |
| 002 | Heater set-and-hold; heat pump owns cycling, HA owns pump speed |
| 003 | Voice pipeline: HA Cloud (Davis/High); OpenAI only experimental |
| 004 | Waterfall control: valve domain (post-1.0.0b5 of OmniLogic Local) |
| 005 | http.server_host bound to LRD-Servers IP + localhost only (post dual-VLAN) |
| 006 | (proposed) actively-heating vs enabled — pump flow tied to compressor demand, not heater enabled state |
