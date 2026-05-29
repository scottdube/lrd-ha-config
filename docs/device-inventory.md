# Device Inventory

What hardware exists, where it lives, what it's paired to, what state it's in.

**Inference flag:** Most of this skeleton is populated from chat history fragments. **Verify and complete the gaps before relying on it.** Items I'm uncertain about are marked `?`.

---

## Z-Wave network

**Controller:** Zooz ZST39 LR 800 Series, FW v1.70 (USB stick on NUC)
**Network:** Z-Wave JS via HA add-on
**Manager UI:** Z-Wave JS UI (HACS add-on)

### Devices (verify and complete)

| Node | Device | Model | Location | Entity ID | Notes |
|---|---|---|---|---|---|
| 003 | HS-WX300 | HomeSeer | Garage | `light.garage_lights` | |
| 005 | HS-WX300 | HomeSeer | Garage | `light.garage_cans` | |
| 016 | HS-WX300 | HomeSeer | Lanai | `light.lanai_cans` (inferred) | |
| 018 | HS-WX300 | HomeSeer | Master Suite | `light.master_bedroom_cans` (inferred) | |
| 019 | HS-WX300 | HomeSeer | Outside | `light.garage_outdoor_lights` (inferred) | |
| 020 | HS-WX300 | HomeSeer | Entry | `light.front_entryway_light` (inferred) | |
| 022 | HS-WX300 | HomeSeer | Living Room | `light.living_room_cans` (inferred) | |
| 023 | HS-WX300 | HomeSeer | Dining Room | `light.dining_room_light` (inferred) | |
| 025 | HS-WX300 | HomeSeer | Kitchen | `light.under_cabinet_lights` (inferred) | |
| 026 | HS-WX300 | HomeSeer | Kitchen | `light.kitchen_cans` | Group 2/3 association to Kitchen 4 Cans (node 034). Verify still working post-FW-rollout. |
| 027 | HS-WX300 | HomeSeer | Nook | `light.nook_lights` (inferred) | |
| 029 | HS-WX300 | HomeSeer | Master Suite | `light.toilet_light` (inferred) | Renamed 2026-04-30: previously "Toilet.  Light" (typo), now "Toilet Light". |
| 030 | HS-WX300 | HomeSeer | Master Suite | `light.bathroom_light` (inferred) | |
| 031 | HS-WX300 | HomeSeer | Master Suite | `light.vanity` (inferred) | |
| 033 | HS-WX300 | HomeSeer | Master Suite | `light.master_suite_hall_light` (inferred) | |
| 034 | HS-WX300 | HomeSeer | Kitchen | `light.kitchen_4_cans` | FW outlier — already on v2.2.0; group source for node 026's associations. |
| ? | Jasco AS2005 | Jasco | Kitchen (over bar) | none | Add-on switch, associated to kitchen cans at Z-Wave level |
| 32 | ZEN75 | Zooz | Master Suite — shower fan | `switch.shower_fan` | FW v1.30.0; renamed from `switch.heavy_duty_switch_shower` 2026-05-20 |
| 51 | ZEN75 | Zooz | Master Suite — toilet fan | `switch.toilet_fan` | Re-included 2026-05-20 as Z-Wave Classic. Previously node 256 on Z-Wave LR — single-link failures in bathroom RF environment; Classic re-include gave 29 mesh neighbors, health check 10/10. FW v1.30.0 |
| 55 | Fibaro FGD212 | Fibaro | Outside / lamp post | `light.lamp_post_dimmer` | FW v3.5. Re-included 2026-05-23 (previously node 43 as `light.dimmer_2`). Sunrise/sunset automations verified end-to-end same day. Signal marginal post-reinclusion but functional — heal + repeater work pending if it stays weak. Dual-channel; second channel `light.lamp_post_dimmer_2` renamed to "Lamp Post - Unused Channel", unexposed from Assist. |
| 47 | Zooz ZSE41 | Zooz | Lanai — East exterior screen door | `binary_sensor.east_ext_door` | CR2032, last replaced 2026-05-18 (100% at install). Wired into ADR-028 lanai perimeter. Entity stems renamed 2026-05-28 from auto-generated `open_close_xs_sensor` to `east_ext_door` via tools/rename_entities.py for parity with West. |
| 49 | Zooz ZSE41 | Zooz | Lanai — West exterior screen door | `binary_sensor.west_ext_door` | CR2032, last replaced 2026-05-18 (100% at install). Wired into ADR-028 lanai perimeter. Stem already clean at inclusion. |
| ? | Kwikset 916 | Kwikset | Lanai door | `lock.?` | Battery drain issue — neighbors:[] on mesh |
| ? | ZEN77 | Zooz | ? | ? | 700-series beaming repeater for lock |
| ? | 14314 / ZW4002 ×6 | Jasco | Lanai L/R, Living Room, Master Bedroom, Guest Bedroom 1+2 | `fan.<area>_ceiling[_<position>]` | 6× in-wall fan speed controllers; entity_ids renamed from auto-generated stems to location-first + `_ceiling` type marker 2026-05-20 via tools/rename_entities.py |
| 53 | ZEN77 | Zooz | Guest Room 1 — cans | `light.s2_dimmer_4` (legacy) | Added 2026-05-20. name_by_user = "Guest Room 1 Cans". 50 entities still on legacy `s2_dimmer_*` stem (mixed `_2`/`_4` suffixes from earlier S2 Dimmer pairings) — entity_id rename deferred to ADR-021; needs script `--regex` enhancement to handle suffix cleanup. |
| (pending) | ZEN77 | Zooz | Guest Room 2 — cans | (none yet) | Added via SmartStart 2026-05-20 — provisioning entry exists (`provision_14244-44678-...`) but device hasn't completed inclusion. Power-cycle the dimmer or check Z-Wave JS UI → Provisioning to trigger inclusion. Once included: same entity_id rename treatment as GR1 Cans. |
| ? | ZEN25 (or Minoston MP26Z) | Zooz/Minoston | Bathroom — Mary's curling iron | ? | Per-outlet control for Away automation |
| Dead 24 | (dead ghost node) | — | — | — | **Cleanup pending:** Remove Failed Node in Z-Wave JS |

---

## ESPHome devices

| Hostname | Hardware | Location | Status | Notes |
|---|---|---|---|---|
| `voice-garage` | ESP32-S3 N16R8 + INMP441 + MAX98357A | Garage | Active, wired | Sporadic audio clarity issue |
| (planned) | ESP32-S3 N16R8 + INMP441 + MAX98357A | ? | Planned | 5 more units |
| (planned) | ESP32-S3 N16R8 + INMP441 + MAX98357A | ? | Planned | |
| (planned) | ESP32-S3 N16R8 + INMP441 + MAX98357A | ? | Planned | |
| (planned) | ESP32-S3 N16R8 + INMP441 + MAX98357A | ? | Planned | |

**Spare hardware:**
- 1× ESP32-S3 N16R8 (spare beyond 5 satellites)
- 0× MAX98357A (5 used or earmarked for 5 satellites)
- 0× INMP441 (5 used or earmarked for 5 satellites)

---

## Pool equipment

| Device | Make/Model | Integration | Entity (key) |
|---|---|---|---|
| Controller | Hayward OmniLogic / OmniPL | OmniLogic Local (control) + OmniLogic Cloud (monitor only) | various |
| Heat pump | Hayward HP31005T (heat AND cool) | via OmniLogic | `water_heater.omnilogic_pool_heater` |
| Filter pump | (variable speed) | via OmniLogic | `switch.omnilogic_pool_filter_pump` |
| Waterfall | (valve) | via OmniLogic | `valve.omnilogic_pool_waterfall` |
| Chlorinator | salt | via OmniLogic | `switch.omnilogic_pool_chlorinator` |
| Pool light | — | via OmniLogic | `light.?` |

**Network:** OmniLogic controller on WiFi, IoT VLAN. **Packet loss issue — ethernet run pending.**

**Heat pump nameplate (HP31005T, manufactured 11/07/2024):**
- Total Load: 33.9A @ 208/230V → ~7.0–7.8 kW input at full load
- Compressor: 32.3A; Fan: 1.6A; Locked Rotor: 139A
- Min Circuit Ampacity: 42A; Max Fuse: 70A
- Heating water-temp range: 48.2–104°F
- Cooling water-temp range: 48.2–86°F (heat pump can't cool above 86°F)
- Recommended water flow: **42.7 gpm** (binding constraint for `heater_pump_speed` blueprint input)
- Refrigerant: R410A, 3500g (7.72 lb)

---

## HVAC

| Device | Make/Model | Integration | Notes |
|---|---|---|---|
| Mini split (?) | Carrier 38MARBQ24AA3 | Midea AC LAN (wuwentao fork) | Local control via port 6444. CliMate WiFi module on IoT VLAN. |
| Main HVAC | Carrier Infinity | Carrier Infinity (HA built-in?) | Used for presence-aware setback (planned) |

---

## Cameras

| Camera | Location | Integration | Notes |
|---|---|---|---|
| UniFi G5 Bullet | Garage interior (Left) | UniFi Protect | `binary_sensor.g5_bullet_person_detected`. Covers main bay + bench area. Person detection is motion-gated bursts, not continuous presence — see `packages/presence/garage_occupied.yaml`. |
| UniFi G5 Bullet (2nd) | Garage interior (Right) | UniFi Protect | `binary_sensor.g5_bullet_person_detected_2` — combined into `binary_sensor.garage_person_detected` template helper |
| UniFi G5 Bullet | Lanai East (mounted east, looks west) | UniFi Protect | `camera.g5_bullet_lanai_east_high_resolution_channel`. Protect UUID `67c4e2a100f9da03e4003b71`. Covers West door view per the mount-vs-view convention in ADR-028. `binary_sensor.g5_bullet_lanai_east_person_detected` exposed for future cross-check. |
| UniFi G5 Bullet | Lanai West (mounted west, looks east) | UniFi Protect | `camera.g5_bullet_lanai_west_high_resolution_channel`. Protect UUID `67c4c93c0284da03e40032cd`. Covers East door view per the mount-vs-view convention in ADR-028. `binary_sensor.g5_bullet_lanai_west_person_detected` exposed for future cross-check. |
| UniFi G4 Doorbell Pro | Front door | UniFi Protect | `camera.g4_doorbell_pro_high_resolution_channel` (main) + `.._package_camera` (lower angle). Protect UUID `6630eba101ffcb03e400a468`. Drives the Front Door doorbell person/animal alert in automations.yaml (id 1775854571098). |
| (more?) | ? | ? | Front-east/west, side, doorbell extras — list as added |

---

## TVs / display clients (photo-frame slideshow)

| Device | Location | IP | Entity | FKB | Role |
|---|---|---|---|---|---|
| Amazon Fire TV | Living room | `192.168.11.82` (IoT VLAN) | `media_player.fire_tv_192_168_11_82` | Installed (Silk-based) | **Production.** Scheduled 09:00 wake + 23:00 foreground-gated shutdown. Dashboard button on LRD-Test. |
| Hisense Google TV | Bedroom | `192.168.11.108` (IoT VLAN) | `media_player.android_tv_192_168_11_108` | Installed via `adb install` (Chrome-based) | **Dev/test surface.** Manual-only — no automation wired. Used to verify `slideshow.html` changes on a second platform without interrupting the living room. Dashboard button pending (Mushroom card YAML in ADR-018). |

Both integrated via the **Android Debug Bridge (`androidtv`)** integration over IoT VLAN ADB-over-TCP. FKB launch component `de.ozerov.fully/de.ozerov.fully.MainActivity` is identical and confirmed working on both. Both render `http://192.168.50.10:8000/slideshow` from the LRD Mac Mini; the UDM Pro firewall rule for IoT → 192.168.50.10:8000 is the load-bearing cross-VLAN piece. Reference: ADR-018, `packages/photo-frame/photo_frame.yaml`.

Known HA quirk: `androidtv.adb_command` service can vanish from HA if the integration's only device is unreachable at HA startup ([home-assistant/core #125579](https://github.com/home-assistant/core/issues/125579)). With two devices on the integration the all-unreachable failure surface is slightly smaller than with one, but watch for it on first 09:00 cold-start after HA restart.

---

## WeatherFlow

| Device | MAC | Notes |
|---|---|---|
| Tempest hub | `6c:2a:df:e1:95:00` | On IoT VLAN. Cloud + Local integrations both available. UDP broadcast on port 50222 must reach HA NUC's `eno1.4` sub-interface for Local feed. Recorded after 2026-05-04 outage where hub disappeared from UniFi client list briefly post-reboot. |
| Tempest station | TBD | Outdoor solar-powered unit. Reports to hub via RF. Captures last-seen via the WeatherFlow mobile app. |

---

## Servers / always-on hosts

| Host | Hardware | IP | VLAN | Role |
|---|---|---|---|---|
| HA NUC | Intel NUC | `192.168.50.11` (`eno1`) + `192.168.11.155` (`eno1.4` IoT) | LRD-Servers (native) + IoT (tagged) | Home Assistant OS + Z-Wave JS USB stick. Dual-VLAN per network-docs ADR-011. |
| Mac mini | Apple Mac mini | `192.168.50.10` | LRD-Servers | Backup target for HA runtime data (pool state log, etc.). SSH reachable from NUC (ed25519 key already exists per 2026-04-30 SSH-key auth work — verify the same key is authorized on the mini). |

---

## Other

- **Eco Link tilt sensor** — garage door (model? confirm)
- **Tapo WiFi switches** — moved to IoT VLAN. List specific switches and locations.
- **Echo Speaks (TTS via Alexa)** — list Echo devices receiving TTS

---

## Entity exposure to Assist

**Currently:** 45 entities exposed (audit completed — see current-state.md Done section).
**Default behavior:** "Expose new entities" is OFF for Assist, Alexa, and Google.
**MCP note:** The Claude MCP Server integration shares this allowlist. Exposing an entity to Assist also exposes it to Claude (and to Alexa/Google to the extent they're enabled). Audit before exposing new entities.
