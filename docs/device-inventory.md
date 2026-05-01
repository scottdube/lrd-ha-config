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
| 32 | ZEN75 | Zooz | Master Suite — shower fan | `switch.heavy_duty_switch_shower` | FW v1.30.0 |
| ? | ZEN75 | Zooz | Master Suite — toilet fan | `switch.heavy_duty_switch_toilet` | Re-included after failed FW update |
| ? | Fibaro FGD212 | Fibaro | Outside / lamp post | `light.dimmer_2` | Dual-channel; second channel unused, unexposed from Assist |
| ? | Kwikset 916 | Kwikset | Lanai door | `lock.?` | Battery drain issue — neighbors:[] on mesh |
| ? | ZEN77 | Zooz | ? | ? | 700-series beaming repeater for lock |
| ? | GE/Jasco fan controller | GE | ? | ? | Older device, may show as light not fan |
| ? | ZEN25 (or Minoston MP26Z) | Zooz/Minoston | Bathroom — Mary's curling iron | ? | Per-outlet control for Away automation |
| Dead 24 | (dead ghost node) | — | — | — | **Cleanup pending:** Remove Failed Node in Z-Wave JS |
| 256 | (Z-Wave LR device) | ? | ? | ? | LR node — identify which device |

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
| UniFi G5 Bullet | Garage exterior | UniFi Protect | `binary_sensor.g5_bullet_person_detected` |
| UniFi G5 Bullet (2nd) | Garage exterior | UniFi Protect | `binary_sensor.g5_bullet_person_detected_2` — combined into `binary_sensor.garage_person_detected` template helper |
| (more?) | ? | ? | List others |

---

## WeatherFlow

| Device | Notes |
|---|---|
| Tempest hub | On IoT VLAN. Cloud + Local integrations both available. |

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

**Currently:** 573 entities exposed (too many — audit needed)
**Default behavior:** "Expose new entities" is ON (turn off, expose manually going forward)
