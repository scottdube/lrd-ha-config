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
| ? | HS-WX300 | HomeSeer | ? | ? | Multiple of these — list each |
| ? | HS-WX300 (kitchen cans) | HomeSeer | Kitchen | `light.kitchen_cans` | Group 2/3 association to Kitchen 4 Cans |
| ? | HS-WX300 (kitchen 4 cans) | HomeSeer | Kitchen | `light.kitchen_4_cans` | |
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
| Heat pump | Hayward HeatPro | via OmniLogic | `water_heater.omnilogic_pool_heater` |
| Filter pump | (variable speed) | via OmniLogic | `switch.omnilogic_pool_filter_pump` |
| Waterfall | (valve) | via OmniLogic | `valve.omnilogic_pool_waterfall` |
| Chlorinator | salt | via OmniLogic | `switch.omnilogic_pool_chlorinator` |
| Pool light | — | via OmniLogic | `light.?` |

**Network:** OmniLogic controller on WiFi, IoT VLAN. **Packet loss issue — ethernet run pending.**

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

## Other

- **Eco Link tilt sensor** — garage door (model? confirm)
- **Tapo WiFi switches** — moved to IoT VLAN. List specific switches and locations.
- **Echo Speaks (TTS via Alexa)** — list Echo devices receiving TTS

---

## Entity exposure to Assist

**Currently:** 573 entities exposed (too many — audit needed)
**Default behavior:** "Expose new entities" is ON (turn off, expose manually going forward)
