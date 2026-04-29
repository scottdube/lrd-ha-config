# Current State

Active working notes. Update as work progresses. This is the file Cowork should reference most often when answering "where are we on X?"

**Last updated:** 2026-04-28

---

## In flight

### Pool automation
- **Blueprint version:** v1.8.0 (deployed)
- **Heater logic:** set-and-hold — heater on if swim day, off if not. Heat pump owns all cycling. HA controls pump speed only (77% when heater needed, 55% otherwise).
- **Waterfall:** runs independently of pump_is_on (v1.6 change).
- **Integration:** OmniLogic Local on `1.0.4` (stable). Cloud retained for ORP/salt/pH monitoring only.
- **Network:** Temporary ethernet run to OmniLogic controller is in place and functioning perfectly. Permanent run mostly done — waiting on Shepard Electric to route through exterior wall (currently dangling from soffit).
- **Issue #173 resolved** in newer releases of `cryptk/haomnilogic-local`.

### Voice assistant satellites (ESPHome)
- **First unit:** garage. Wired and flashed. Recovered 2026-04-28 from a stuck `voice_assistant.on_error` (pipeline pointed at a removed Ollama conversation entity — see ADR-003 for the canonical-vs-alternative pipeline policy).
- **Pipeline (LRD Voice Assistant):** HA Cloud STT, HA Cloud TTS (Davis voice, High quality), OpenAI Conversation as agent with "Prefer handling commands locally" ON (local first, OpenAI fallback). Per ADR-003 revised 2026-04-28. Ollama is supported as an alternative agent but not default.
- **Open issue:** Sporadic audio quality (clears up intermittently). Suspected I2S clock drift on ESP32-S3 with esp-idf driver. **Next step:** test fixed MCLK pin on MAX98357A.
- **Enclosure:** golf-ball-on-tee design in Fusion 360 for garage unit. Prototyping in alt-color PLA before final print. M3 heat-set inserts: 4.91mm OD, need 4.5mm holes.
- **Hardware on hand:** 6× ESP32-S3 N16R8, 5× MAX98357A, 5× INMP441. 5 more units to build.
- **ESPHome firmware location:** `esphome/` at repo root → maps to `/config/esphome/` on the NUC. The earlier `voice-satellites/esphome/` location was reverted because ESPHome dashboard's `rel_path()` validation is incompatible with directory-level symlinks.

### Nabu Casa subscription decision (URGENT)**
- **Trial expires 2026-05-04** (~6 days). Decision required: subscribe or lapse.
- **What lapse breaks:** Cloud STT/TTS (voice satellites go red), Alexa Smart Home control of HA (18 entities), primary remote access (WireGuard not currently configured as alternative), stable `*.ui.nabu.casa` URL.
- **Cost:** annual subscription. See `integrations/nabu-casa.md` for full impact analysis.
- **Recommended:** subscribe given the cross-cutting dependencies. Local Whisper + Piper is a feasible long-term alternative for STT/TTS but isn't built; Alexa bridge has no local equivalent.

### Network → HA boundary (cross-project)
- **ADR-008** (in network-docs project) — analysis underway for moving HA NUC from IoT VLAN to LRD-Servers VLAN.
- **Status:** pcap-based traffic characterization running. Initial findings suggest only 3-4 inbound rules needed if migrated.
- **Decision pending.** Don't move HA until ADR-008 is committed.

### Z-Wave fleet housekeeping
- **Toilet fan (ZEN75, node 256) is dead** after a strange firmware update. Needs reinclusion or recovery. `device-inventory.md` had this as `?` — now confirmed.
- **Kwikset 916 (node 038) battery at 30%** — replacement window opening. Other Kwikset (node 008) at 100%.
- **HS-WX300 fleet FW divergence** — node 034 is on v2.2.0 while the other 15 HS-WX300s are on v2.1.13. **Decision: roll the remaining 15 forward to v2.2.0.** Changelog (verified 2026-04-28 via HomeSeer docs) is SDK v7.18.1 → v7.18.8 plus a fix for a Silicon Labs SDK bug where R2 (800 Series) WX300s "can stop responding to Z-Wave commands if not manually controlled for some time." Low-risk update, behaviorally identical, fixes a real intermittent failure mode. Firmware file: `https://homeseer.com/updates4/WX300-R2_2_2_0.zip`. Update via Z-Wave JS UI → Node → Firmware Update. 15 devices × ~5 min each.

---

## Recently completed

- **HA config auto-pull from git wired.** Time-pattern automation (`HA Config Auto-Pull from Git`, every 15 min) calls `shell_command.git_pull_config` with `--ff-only`. Mobile push notifies on actual changes and on failures (e.g., divergent local edits blocking ff-only). Eliminates the manual NUC-pull step that caused state drift earlier today.
- **Temporary ethernet run to OmniLogic controller** in place and functioning perfectly. WiFi packet loss issue (~30-40%) eliminated. Permanent run mostly done — Shepard Electric to finish exterior wall pass-through.
- **OmniLogic Local upgraded to `1.0.4`** (stable, off beta).
- **GitHub issue #173 (cryptk/haomnilogic-local)** resolved by dev team in newer integration releases.
- **Switch→valve domain migration** for OmniLogic waterfall (blueprint v1.8.0).
- **Lanai lights blueprint v1.5** — door-activated with lux/sun fallback, skip-if-on guard. All 4 test paths verified. Live.
- **HA → IoT VLAN migration** done. NUC at 192.168.11.155.
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
- **Carrier Infinity presence-aware setback** — Florida AC cost optimization.
- **Camera motion alerts when away** — UniFi cameras already integrated.

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
