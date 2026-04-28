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
- **First unit:** garage. Wired and flashed. Pipeline configured.
- **Pipeline:** HA Cloud STT/TTS (Davis voice, High quality). OpenAI tested but billing/quality issues — reverted to HA Cloud.
- **Open issue:** Sporadic audio quality (clears up intermittently). Suspected I2S clock drift on ESP32-S3 with esp-idf driver. **Next step:** test fixed MCLK pin on MAX98357A.
- **Enclosure:** golf-ball-on-tee design in Fusion 360 for garage unit. Prototyping in alt-color PLA before final print. M3 heat-set inserts: 4.91mm OD, need 4.5mm holes.
- **Hardware on hand:** 6× ESP32-S3 N16R8, 5× MAX98357A, 5× INMP441. 5 more units to build.

### Network → HA boundary (cross-project)
- **ADR-008** (in network-docs project) — analysis underway for moving HA NUC from IoT VLAN to LRD-Servers VLAN.
- **Status:** pcap-based traffic characterization running. Initial findings suggest only 3-4 inbound rules needed if migrated.
- **Decision pending.** Don't move HA until ADR-008 is committed.

---

## Recently completed

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
- **WeatherFlow Local** — discovery should work now that HA is on IoT VLAN with Tempest.

### Cleanup
- Audit 573 entities exposed to Assist — too many.
- Turn off "Expose new entities" default.
- Phantom entity on Fibaro Dimmer 2 (`light.dimmer_2_2`) — unexposed but worth final rename for clarity.

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
