# Current State

Active working notes. Update as work progresses. This is the file Cowork should reference most often when answering "where are we on X?"

**Last updated:** 2026-05-03 (ADR-011 service mode end-to-end validated via panel-toggle test — detect→suppress→clear; ADR-016 deployed; **notify.scott_and_ha group live** — mobile + HA bell fan-out; **auditor v1.1.0 built and running** — Phase 1 + ADR-006 P-series; **rsync mirroring deployed** NUC→MacBook + NUC→Mac mini @ 5 min; **overnight audit launchd installed on Mac mini** scheduled 00:05 daily, FAIL-only push via scott_and_ha; logger v2 phase 1.5 deployed — schema rotation observed at 2026-05-02 12:10; ADR-015 firmware bench validation complete; HA NUC IP correction landed in memory — .50.11 user-accessible, .11.155 IoT-only)

---

## In flight

### Pool automation
- **Blueprint version:** v1.10.1 (deployed and validated). v1.10.2 also deployed (ADR-016 integration-recovery debounce in `packages/pool/pool_modes.yaml`). **ADR-011 panel-toggle service mode validated end-to-end 2026-05-03** via 8:53 OFF → 9:00 boundary check → 9:03 ON sequence: detection traces showed all 4 conditions passing both directions, blueprint trace at 9:00 confirmed `service_active=True` suppressed PUMP START despite all other preconditions (current_minutes=540 > pump_should_start=480, swimming_day=True, etc.) being satisfied. No false re-fires. Followed by a "wait through /10 boundary" cross-validation in the 8:53–9:00 window — confirmed lockout actually suppresses, not just that detection fires. **v1.10.1** content — single-line `current_water_temp` fallback fix per ADR-013, closes overnight pump-waste bug. **v1.10.2** content — input_boolean.pool_integration_recovering + 5-min watcher gate, closes the class of false-positive lockout engagements observed during the 2026-05-02 10:25–10:40 HA restart incident.
- **Pump speed inputs tuned 2026-05-02:** `normal_pump_speed: 55`, `heater_pump_speed: 65` (down from defaults 65/77). Empirically validated values from Scott's prior tuning. ~17% additional reduction in pump consumption on top of v1.9.0 via cube-law. Bill analysis estimates ~$390/year savings vs. pre-v1.9.0 baseline at his SECO Energy rate ($0.136/kWh effective). Watch for HeatPro low-flow faults — if any appear during heating cycles, raise `heater_pump_speed` back toward 70-75.
- **April 2026 bill spike decomposed (2026-05-02 via Carrier app data):** Mar→Apr bill jumped +2025 kWh (2526→4551). HVAC actually *decreased* −245 kWh (Mar 1007 → Apr 762, sum of main + master mini-split). The +2025 kWh increase is dominated by pool: pump turning on 24/7 (~500 kWh) + heat-pump compressor running for water-temp recovery (~900–1100 kWh estimated; real measurement pending via `local_filter_power` once logger v2 captures a few days). HVAC is ~18% of total daily load (~25 kWh/day in April), pool is ~30%+, "everything else" is ~45%. Big "everything else" bucket (~65 kWh/day = ~$265/month) is the next investigation target — water heater, fridge, electronics, phantom loads. Whole-home power monitoring (Emporia Vue 2 or IotaWatt) is the natural next step for visibility into this bucket. Future ADR.
- **Heater logic:** set-and-hold — heater on if swim day, off if not. Heat pump owns cycling. **Open issue (ADR-006):** blueprint conflates heater-`on` (enabled/ready) with heater-actively-delivering. Result: pump runs 24/7 at 77% on swim-day stretches even when compressor is idle. Confirmed in 2026-04-28→05-01 CSV: 595 pump-on rows, 0 pump-off rows. Empirically validated 2026-05-01 via Hayward cloud activity log — heater compressor only ran 04:02–06:47 EDT (2h45m) yet pump ran 24h. **Signal source identified:** local `binary_sensor.<heater_equip>_heater_equipment_status` (compressor active boolean from `pyomnilogic_local.HeaterState`) plus cloud `water_heater` state as cross-validation. Blueprint v1.9.0 ready to implement.
- **Waterfall:** runs independently of pump_is_on (v1.6 change). **Orphan-entity confusion fully resolved 2026-05-02** — initial 2026-05-01 fix pointed everything at `valve.omnilogic_pool_waterfall_2`, but Developer Tools → States verification on 2026-05-02 showed the live entity is actually `valve.omnilogic_pool_waterfall` (no suffix). `_2` was/is the orphan. Reverted: blueprint waterfall_switch input, configuration.yaml shell_command, templates.yaml dashboard sensor, and state_logger.py all now point at the unsuffixed entity. **This is also why v1.9.0 didn't appear to do anything overnight** — the WATERFALL END branch's `is_state(waterfall_switch, 'open')` check was returning False against the orphan, so the pump-shutoff path never fired.
- **Integration:** OmniLogic Local on `1.0.4` (stable). Cloud retained for ORP/salt/pH monitoring only.
- **Network:** Temporary ethernet run to OmniLogic controller — confirmed reliable on 2026-04-30 evening (zero errors over 7 hours). Permanent run mostly done — waiting on Shepard Electric to route through exterior wall (currently dangling from soffit).
- **Open: midnight error burst on local integration** — discovered 2026-05-01 while diagnosing waterfall incident. ~18 `Failed to update data from OmniLogic` errors clustered 00:27–01:00 EDT, plus scattered isolated errors through 01:00–07:00. Evening hours zero errors. Cloud unaffected throughout. Pattern fits controller-side scheduled housekeeping rather than network instability. Needs multi-night confirmation. Full analysis: `scratch/omnilogic-local-midnight-burst-2026-05-01.md`.
- **Issue #173 resolved** in newer releases of `cryptk/haomnilogic-local`.

### Pool observability rebuild
Largely complete as of 2026-05-03. Logger v2 phase 1.5 deployed (44 cols, schema rotation observed at 2026-05-02 12:10 cutover — old phase-1 file preserved as `pool_state_log.2.0-phase1.csv` per spec). Auditor v1.1.0 deployed and running nightly. Rsync mirroring deployed to MacBook (interactive use) and Mac mini (always-on for unattended overnight audit).

**Auditor (v1.1.0)** — `pool/scripts/auditor.py` implements Phase 1 daily-shape + waterfall + heater assertions plus ADR-006 P-series. Configurable HA token/base/notify-target via CLI args (--ha-base / --token-file / --notify-target). Default notify target = `scott_and_ha`. Five assertion-tuning fixes shipped 2026-05-03: D1 ignores 'unavailable' values; D3 exempts water_temp during pump-off (sensor only reliable with flow); W2/W3 skip if audit runs before respective windows; P3/P4 skip first time_pattern row of each heater-state-change run (closes the race where logger snapshots state at the same instant the blueprint fires its speed change command, before the change lands). Result: 11/0/4 against 2026-05-03 mid-day live data.

**Rsync mirroring** — pull-based via launchd on each Mac. Plist at `pool/scripts/launchd/com.scottdube.ha.pool-log-rsync.plist`, dedicated SSH key per machine on the NUC's Frenck SSH addon (port 22, user `sdube`). `pool/analysis/pool_state_log_live.csv` refreshed every 5 min. Both Mac mini and MacBook receive their own copies (mini for the unattended audit, MacBook for Cowork access). Setup walkthrough in `pool/docs/rsync-setup.md`.

**Overnight audit** — `pool/scripts/audit_yesterday.sh` + `pool/scripts/launchd/com.scottdube.ha.pool-audit-overnight.plist` on the Mac mini, fires daily at 00:05. Self-pulls latest auditor code via `git pull --ff-only` before each run, so any push to main is picked up the next night. Pushes only on FAIL via `notify.scott_and_ha` (mobile + bell); silent on PASS. HA long-lived token at `~/.ha_token` (mode 600). Logs to `~/Library/Logs/ha-pool-audit.{log,err.log}`.

**notify.scott_and_ha group** (`packages/notify/notify_groups.yaml`) — fan-out to mobile_app_iphone_sd + persistent_notification. Replaces the previous bare mobile push in all four pool service-lockout automations. Reused by the auditor's overnight FAIL pushes. Reusable for future battery-low alerts (ADR-014) and any other cross-cutting notification.

**Open auditor enhancements:**
- Schema-rotation-aware historical audits: auditor reads only `/config/pool_state_log.csv`, but the rotation on 2026-05-02 12:10 split data between two files. Audits of dates that straddle the rotation get false negatives for the missing half. Fix: `--csv-glob "/config/pool_state_log*.csv"` or similar. Not blocking — daily forward audits work fine because new data is always in the current file.
- Long-term snapshot retention strategy. Live mirror is gitignored and ephemeral; if Mac mini disk dies the file is recoverable from the NUC but historical audits aren't reproducible. Options: weekly daily-slice commit, periodic NAS dump, or accept ephemeral. Defer until 30+ days of data accumulate.

### External water temp sensor (ADR-015)
Requirements analysis complete and accepted 2026-05-02. Closes the structural blind spot ADR-013 patched tactically: the OmniLogic in-line probe reads `unknown` whenever pump is off (no flow), leaving the blueprint without real water temp during pump-off windows.

- **v1 hardware path: case-reuse + NTC-reuse.** Existing TX13-class floating thermometer case is mechanically intact (probe chamber, threaded gasket ring, battery compartment). Original PCB is corroded beyond repair (humid salt-air ingress through degraded gasket, NOT through wire pass-through). In-place NTC tested healthy at 41.4 kΩ at ~87°F lanai-ambient — consistent with 50 kΩ @ 25°C, Beta ≈ 3400–3500 class. Wire pass-through epoxy seal survived 20+ years and stays.
- **Build:** ESP32-C3/C6 + 47 kΩ 0.1% reference resistor + ESP32 ADC. ESPHome `resistance` + `ntc` platforms with declarative Steinhart-Hart calibration (3-point: ice bath, room temp, ~104°F warm water). Replaces threaded gasket O-ring, conformal coats new PCB.
- **Cascading fallback chain (replaces direct sensor read in blueprint):** Tier 1 `external_water_temp` fresh → Tier 2 `local_water_temp` reliable → Tier 3 `target_temp` (ADR-013).
- **Logger v2 columns to add (phase 2+):** `external_water_temp`, `external_water_temp_age_min`, `external_water_temp_fresh`, `water_temp_authoritative`, `water_temp_delta`. Auditor candidates W1/W2 follow.
- **Open build-phase decisions:** ~~MCU SKU~~ (C6, on hand, 2026-05-02), ~~power source~~ (2× lithium primary AA, no regulator, 2026-05-02), ~~calibration values~~ (done 2026-05-02), tether strategy, gasket material (EPDM vs silicone vs Viton), notification policy thresholds. Build-phase float buoyancy/trim test added — lithium primary cells are ~17 g lighter than alkaline; verify probe chamber vent slots stay submerged before final seal.
- **Deadline:** EOM 2026-05-31 for stage 1 (deployed + entity contract met + gates A/B/D/E/F). Stage 2 (gate C — 5-7 day soak data quality verification) lands 5–7 days after deploy.
- **Budget:** $100 ceiling; case-reuse path estimated $15–25 in parts.
- **Calibration complete 2026-05-02.** Three points captured (32.0°F/153kΩ, 73.7°F/52.6kΩ, 109.5°F/22.8kΩ), Steinhart-Hart coefficients fit, NTC characterized as 47 kΩ @ 25°C / Beta ≈ 3823. ESPHome multi-point calibration block ready. Full data + reference probe verification + in-service R sanity table in `pool/docs/external-water-temp-calibration.md`.
- **Thermal/condensation analysis added to ADR-015 2026-05-02.** Empirical observation during the calibration session — visible condensation formed inside the case within 15 min of submerging the lower body in 32°F ice bath, without solar gain or gasket leakage. Root cause: trapped humid air condenses out whenever interior surfaces drop below dew point, which happens daily in pool service from overnight cooling + solar gain on the clear dome. Required mitigations: hydrophobic vent membrane (top priority — addresses pressure-cycle pumping at root), indicating silica gel desiccant, **Boeshield T-9** for PCB + battery contacts + metal hardware (single-product replacement for conformal coating + dielectric grease), reflective dome treatment + LCD removal, **reuse existing silicone gasket with silicone grease**. Estimated BOM ~$60–80 (revised down from initial $80–110 after gasket-reuse and T-9 consolidation decisions). Full BOM in `pool/docs/external-water-temp-bom.md`.
- **Schematic generated 2026-05-02:** `pool/docs/external-water-temp-schematic.{png,svg}`. Top-down view of XIAO ESP32-C6 with all 14 pin pads labeled per silkscreen, BAT+/BAT− underside solder pads called out, used pads/pins highlighted (3V3, D0, BAT+, BAT−), 47kΩ + NTC voltage divider, U.FL antenna selection callout, and build notes including the bench-test "USB-only, no batteries" rule.
- **Bench validation completed 2026-05-02 (evening) — firmware end-to-end on actual XIAO ESP32-C6 hardware.**
  - **Toolchain:** Python 3.12 (Homebrew) + pipx + ESPHome 2026.4.3 on Mac. System Python 3.9 capped at ESPHome 2025.5.2 which still uses legacy ADC API (`adc2_channel_t`, `esp_adc_cal_*`) incompatible with C6 (which has only ADC1, no legacy calibration). Newer ESPHome (≥ 2025.6) requires Python ≥ 3.11. pipx with brew-installed Python 3.12 is the working install path; `pip3 install esphome` against system Python 3.9 will not work for C6.
  - **Board parameter for ESPHome:** `esp32-c6-devkitc-1` with `variant: esp32c6` (the `seeed_xiao_esp32c6` board name doesn't exist in PlatformIO's database yet; generic Espressif devkit compiles identically).
  - **Bootstrap flash via USB-C succeeded;** subsequent updates via WiFi OTA. Firmware location: `esphome/pool-water-temp-external.yaml`.
  - **Bench wiring (breadboard):** 47 kΩ standard-tolerance test resistor as divider reference, NTC accessed via clip leads on the existing TX13 daughterboard solder pads, all 4 connections to XIAO (BAT+ via USB, GND, 3V3, D0=GPIO0 ADC).
  - **End-to-end accuracy:** 74.7°F sensor read vs reference probe at 75.2°F (with AC airflow controlled). **±0.5°F gap — passes ADR-015 preferred accuracy spec.** Bench resistor tolerance accounts for most of the gap; 0.1% metal-film in production will close it further.
  - **Deep sleep cycle running** at 60 sec sleep / 30 sec run for bench verification (will switch to 30 min / 30 sec for production once stability confirmed). Wake/publish/sleep observed working in ~1 sec actual wake time.
  - **Power LED behavior:** the red LED on the XIAO C6 turns off when no battery is connected and USB is unplugged. Likely a charge-status indicator (not a hardwired power-on LED), meaning no LED disable surgery is needed for battery-only operation. To be confirmed once batteries are installed.
  - **Currently running unattended on NUC USB power** at the bench; will validate continuous overnight cycling.
- **WiFi gotcha (resolved):** ESP32-C6 cannot connect to "IoT" SSID (WPA2/WPA3 mixed transition mode) — fails with `Disconnected reason='Probe Request Unsuccessful'`, scan returns "No networks found" repeatedly. UDM Pro has a separate **"Legacy IoT"** SSID (WPA2-only, 2.4 GHz only, same IoT VLAN — 192.168.11.x) that the C6 connects to cleanly on first try. New secrets `legacy_iot_ssid` and `legacy_iot_password` added to local Mac's `esphome/secrets.yaml`. Voice-garage's ESP32-S3 happens to work on "IoT" but newer C6 WiFi 6 stack is stricter on transition-mode handshakes. Pattern: any future ESP32-C6 builds → use Legacy IoT.
- **OTA gotcha (resolved with workaround):** UDM Pro firewall blocks cross-VLAN port 3232 (ESPHome OTA) from management VLAN → IoT VLAN. Port 6053 (API) works fine cross-VLAN, so HA can still query the device. Workaround for OTA: connect Mac directly to "IoT" SSID during pushes (same VLAN as the C6 on Legacy IoT, no firewall hop), then switch back. Long-term fix: migrate config to NUC's `/config/esphome/` so the dashboard add-on does OTA from the NUC, which already has dual-VLAN attachment via `eno1.4` (per ADR-011) and is therefore on the IoT VLAN natively.
- **Open for next session:**
  - Overnight cycle stability check (HA should show continuous 1-min cycles by morning)
  - Deep sleep current measurement with multimeter inline on USB power (target ≤ 25 µA per ADR-015 power budget)
  - Switch `sleep_duration: 1min` → `30min` for production cadence once stability confirmed
  - Migrate YAML + secrets additions to NUC's `/config/esphome/` so dashboard add-on can OTA going forward (per voice-garage workflow)
  - Begin mechanical case integration per ADR-015 build sequence: clean case, remove dead LCD, install reflective dome treatment, fit ESP32-C6 + 47kΩ 0.1% on perfboard inside upper compartment, drill + seal vent membrane hole, install silica desiccant, T-9 application, reassemble with silicone grease on existing gasket
  - Buoyancy/trim test before final seal (lithium primary AA is ~17 g lighter than alkaline; chamber vent slots must stay submerged at rest)

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

- **Pool service mode (ADR-011) end-to-end validated 2026-05-03.** Morning panel-toggle test: 8:53 OFF → blueprint trace at 9:00 boundary confirmed `service_active=True` suppressed PUMP START → 9:03 ON cleared lockout. Three uploaded traces verified all conditions, both detection automations, and the suppression branch. Followed by post-restart re-test confirming the new notify group fires both mobile push and HA bell entry.
- **notify.scott_and_ha group deployed 2026-05-03.** New package `packages/notify/notify_groups.yaml`. All four pool service-lockout automations (engage, clear, manual-resume, midnight-autoclear) now route through it. Future battery + audit pushes will reuse.
- **Auditor v1.1.0 built and deployed 2026-05-03.** Phase 1 + ADR-006 P-series, configurable for non-NUC execution. Tuned via real data — 5 false-positive classes closed (D1 unavailable, D3 pump-off water_temp, W2/W3 pre-window, P3/P4 transition race).
- **Rsync mirroring deployed 2026-05-03.** NUC → MacBook + NUC → Mac mini, every 5 min via launchd, pull-based with dedicated SSH keys per machine. Mac mini hosts the always-on overnight audit at 00:05; MacBook copy gives Cowork instant fresh data.
- **HA NUC IP correction landed in memory.** `192.168.50.11` is the user-accessible address (LRD-Servers VLAN); `192.168.11.155` is IoT-VLAN-only and not reachable from Scott's workstations. All future setup docs/scripts default to .50.11.
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
- **Battery health tracking** (raised 2026-05-02 after Kwikset 916 long-beep at 20%). Two-layer approach per ADR-014: HACS Battery Notes for ops view (last-replaced, replacement reminders) + logger v2 extension for analytics (decay rate baselines, anomaly detection in auditor). Phase 1 (Battery Notes install) is immediate; Phase 2-4 build over time as data accumulates.
- **Pool maintenance day handling** — Phase 1 (panel-toggle detection) shipped and validated 2026-05-03 per ADR-011. Tech can pause the blueprint by toggling pump off at the Hayward panel; symmetric on for resume. Auto-clears at midnight. Solves the breaker-wear concern (no longer need breaker cycles for routine service). Phase 2 candidates (door switch on pool control box for "door opened but pump not toggled" cases) deferred — current detection covers the dominant case. Revisit if Scott observes pauses missed.

### Cross-cutting automation patterns to add
- **`input_boolean.vacation` guard** — add a vacation helper and retrofit it as a condition on presence/lux/welcome-home style automations so they no-op while we're out of town. New automations (kitchen/great-room lux, welcome home, etc.) should include this guard from day one. Decide whether vacation mode itself should auto-set this, or keep it manual via dashboard toggle.

### Voice satellites
- 5 more units to build after garage proves out.
- Decide locations: kitchen, master bedroom, lanai, ?, ?

### Whole-home power monitoring (planned)
- ADR-009 drafted 2026-05-02 covering Emporia Vue 2 vs IotaWatt trade-off.
- New sub-project at `energy/` with planning docs.
- Hardware not yet purchased; pre-purchase checklist in `energy/README.md`.
- Logger v2 will extend with `home_*` columns once installed.

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
| 009 | (proposed) whole-home power monitoring — 2× Vue 3 cloud-now-flash-later; install Sunday 2026-05-04. ESPHome 2026.4.0 issue resolved via emporia-vue-local @dev branch (per Discord 2026-05-02). |
| 011 | (deployed + validated 2026-05-03) pool service mode — input_boolean.pool_service_lockout via panel-toggle detection |
| 012 | (accepted) vacation mode — cross-cutting input_boolean.vacation, pool implementation first |
| 013 | (accepted) current_water_temp fallback uses target_temp instead of 75 — fixes PUMP START gate firing on every poll when sensor reads `unknown` |
| 014 | (proposed) battery health tracking — Battery Notes + logger v2 extension + auditor assertions |
| 015 | (accepted) independent water temp sensor — case-reuse + NTC-reuse v1 path; EOM 2026-05-31 deploy target; build-phase decisions deferred (MCU SKU, power source, tether, gasket spec, calibration values, notification thresholds) |
| 016 | (deployed) integration-recovery debounce — 5-min suppression of service-lockout detection after OmniLogic Local recovers from unavailable; closes false-positive class observed 2026-05-02 |
