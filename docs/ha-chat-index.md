# Home Assistant — Chat Migration Index

Index of past Claude chats covering Home Assistant work. Links go directly to each chat in claude.ai.

**Note on scope:** Chats covering pure network infrastructure (firewall annotations, ADRs about VLANs, multi-site routing) are tracked in the separate `network-docs` project, not here. Where chats span both topics, they're listed here with a note.

---

## Z-Wave migration (Hubitat → HA)

Foundation chats — exclusion/inclusion, ghost nodes, mesh diagnostics.

| Chat | What's in it |
|---|---|
| [Hubitat exclude / Z-Wave include GE Jasco fan controllers](https://claude.ai/chat/a6c8d8d4-20d4-4eba-92ba-05c30024cbf8) | Exclusion procedures, ghost node cleanup, "No Security" inclusion for older GE devices, fan-as-light entity issue. Also contains initial UDM Pro WireGuard discussion. |
| [HS-WX300 "provisioned but not yet included"](https://claude.ai/chat/3f08c0cd-7472-4643-9cf7-bf7f42e55146) | Failed inclusion / placeholder ghost node fix. |
| [Minoston Z-Wave dimmer factory reset](https://claude.ai/chat/c1e2ed71-867f-489a-b52c-0d084390325a) | Reset procedures: 700 vs 800 series differences. |
| [Kwikset 916 lock — neighbors:[] / weak LWR](https://claude.ai/chat/2b21fccb-6801-41c7-997f-591bb949cee4) | Lock isolated on mesh; battery drain root cause = retry storm from no neighbors. |

## Pool automation (longest-running thread)

Spans ~5 chats and blueprint versions v1.0 → v1.8. Treat as one conceptual unit.

| Chat | What's in it |
|---|---|
| [Pool dashboard + OmniLogic Local install + GitHub repo setup](https://claude.ai/chat/d58fc251-96bd-4189-bc1a-ab96973ce4cb) | Dashboard YAML, local integration install, `lrd-ha-config` repo creation, initial git workflow. |
| [Pool automation troubleshooting v1.5 → v1.7](https://claude.ai/chat/e5d39631-0b1b-40af-853c-eeff836ac2c9) | Heater logic refactor (set-and-hold, heat pump owns cycling), pump start bug, waterfall independence, trace storage config. |
| [Pool waterfall ghost entity `_2` suffix](https://claude.ai/chat/e09111a8-bec9-45c4-833c-5291dc207a38) | Stale entity from migration; manual save force-resolves entity ID. |
| [OmniLogic comms errors + valve migration + Midea AC LAN + garage_ms rename](https://claude.ai/chat/e7c1005f-0537-4f25-bda3-7561b00be328) | Pydantic warning, switch→valve domain migration (blueprint v1.8), Midea CliMate mini-split integration, bulk entity rename via REST API. **Grab-bag — also covers Midea.** |
| [ChefsTemp BBQ probe HA integration request](https://claude.ai/chat/8897bbb5-a867-417c-8d3b-6a2fb35419fe) | Feature-request email drafted for ChefsTemp; tangential but HA-relevant. |

## HA infrastructure (host placement, integrations, cross-cutting)

| Chat | What's in it |
|---|---|
| [Eco Link tilt sensor + HA→IoT VLAN move + Fibaro Dimmer 2 + Tapo VLAN move + automation ideas](https://claude.ai/chat/d79c717a-5803-4cbb-bdbf-a78ef5b7905f) | **Largest single grab-bag.** HA migration to IoT VLAN, Fibaro Dimmer 2 inclusion, Hayward OmniLogic integration evaluation, voice assistant BOM, Tapo switch VLAN reassignment, Alexa skill cleanup, kitchen can sync automation, AS2005 add-on switch detective work, Fibaro dual-channel phantom entity. Worth a re-read before importing. |
| [Studio Code Server clipboard permissions](https://claude.ai/chat/4915b307-3ad0-4769-8f45-ed09f19aa177) | Iframe clipboard API limitation; fix = open SCS in own tab. Short, focused. |
| [ZEN75 toilet fan re-inclusion (also has network-docs content)](https://claude.ai/chat/83b94fbf-0547-45cb-9206-c62223ea11e4) | **Cross-project chat.** ZEN75 re-inclusion belongs here; firewall annotations / ADRs / multi-site VPN strategy belong in `network-docs` project. Same chat, two projects. |

## Lighting / door / presence automations

| Chat | What's in it |
|---|---|
| [ESPresense presence detection + garage bench light + outlet hunt for Mary's curling iron](https://claude.ai/chat/4a691cee-38f5-48f8-b654-b71eb76ebd57) | mqtt_room template, packages directory setup, ESPresense IRK, ZEN25 discontinuation / Minoston alternatives. |
| [Lanai lights after-dark blueprint v1.5](https://claude.ai/chat/279fa23d-3aae-48e3-b4f6-891acc623c2a) | Door-activated-lights blueprint extension: lux primary / sun elevation fallback, skip-if-on guard, all 4 test paths verified. |

## Voice assistant satellites (ESP32-S3)

| Chat | What's in it |
|---|---|
| [Voice assistant hardware assembly / ESPHome / golf-ball enclosure](https://claude.ai/chat/0e6dbfb1-10bb-48f8-b654-b71eb76ebd57) | Full build: INMP441 + MAX98357A wiring, ESPHome 2026.x config (use_wake_word, esp32_rmt_led_strip, openWakeWord), HA Cloud vs OpenAI pipeline testing, garage-unit golf-ball-on-tee enclosure design in Fusion 360. |

---

*Generated 2026-04-28. Update as new chats are added or old ones become irrelevant.*
