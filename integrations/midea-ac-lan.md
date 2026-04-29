# Midea AC LAN

LAN-based control of Midea-protocol mini split. Comprehensive control surface (HVAC modes, fan, swing, aux heat, frost protect, eco/sleep/comfort, smart eye, dust filter status, energy metering).

---

## Stack

- **HACS repo:** [`wuwentao/midea_ac_lan`](https://github.com/wuwentao/midea_ac_lan) — currently the actively maintained fork (v0.6.11 at time of writing, regular commits).
- **Custom component path:** `custom_components/midea_ac_lan/`
- **Communication:** LAN (no cloud dependency for ongoing operation)
- **Protocol:** Midea M-Smart proprietary

---

## Device

- **Friendly name:** Garage Mini Split (in HA: "Garage Mini Split")
- **Location:** Garage (LRD)
- **Brand on HA device card:** Midea (the integration shows OEM identity)
- **Brand on the unit:** Carrier — model `38MARBQ24AA3` (the Carrier-branded version of a Midea-OEM unit)
- **Network manufacturer string:** "Springer Midea AC" (Springer is Carrier's South American brand, also Midea-OEM — same firmware family. UniFi reports the network manufacturer this way.)
- **Midea internal identifier:** Air Conditioner 00000Q18 (44204)
- **MAC:** 80:76:c2:3c:db:d2
- **Hostname:** `net_ac_DBD2`

---

## Network

- **IP:** `192.168.11.228` (IoT VLAN, VLAN ID 4)
- **AP:** Garage U7 Pro
- **WiFi:** 2.4 GHz, Ch 1, 20 MHz, WiFi 4 (the unit's radio is WiFi 4 only — typical for HVAC controllers)
- **Signal:** ~-46 dBm (strong, consistent)
- **DHCP reservation in UniFi:** in place — IP is stable

---

## Entities

Primary climate entity:

- `climate.garage_mini_split` — main control surface (HVAC mode, target temp, fan speed, swing). Currently set to Auto, target 76°F.

Sensors:

- `sensor.garage_mini_split_indoor_temperature` — 77°F observed
- `sensor.garage_mini_split_indoor_humidity` — 48% observed
- `sensor.garage_mini_split_outdoor_temperature` — 76.1°F observed (reading from the outdoor unit's sensor)
- `sensor.garage_mini_split_realtime_power` — 0 W (when idle)
- `sensor.garage_mini_split_current_energy_consumption` — kWh
- `sensor.garage_mini_split_total_energy_consumption` — kWh (lifetime)
- `binary_sensor.garage_mini_split_full_of_dust` — filter cleaning reminder

Switches / toggles (per unit feature):

- Aux Heating, Boost Mode, Breezeless, Comfort Mode, Dry, ECO Mode, Fresh Air, Frost Protect, Indirect Wind, Natural Wind, Power, Prompt Tone, Screen Display, Screen Display Alternate, Sleep Mode, Smart Eye, Swing Horizontal, Swing Vertical

Other:

- Airflow Horizontal / Vertical (select)
- Fan Speed Percent (number / slider)

Most of these toggles will go untouched in normal operation. The ones likely to matter for automations: `climate.garage_mini_split`, the temp/humidity sensors, the power sensor, and possibly Aux Heating + Frost Protect for cold-weather logic.

---

## Setup

- **Discovery:** integration discovers Midea devices on local subnet
- **Auth:** requires Midea cloud account credentials on first add to retrieve device key/token. Ongoing operation is local-only.
- **Network:** device on IoT VLAN, IP `192.168.11.228`. DHCP reservation in UniFi is in place.
- **Specific pairing flow used:** not recalled. If re-pairing becomes necessary, expect to need Midea cloud credentials again to retrieve the device token.

---

## Known quirks

- None observed in production yet — unit has been integrated but not heavily exercised by automations.
- Reasonable patterns to watch for (from the broader Midea-LAN ecosystem):
  - Occasional connection drops requiring HA integration reload (pattern not yet seen here)
  - Fan-mode label mismatches between HA and the unit's IR remote
  - Mode coordination — setting mode + fan + temp in rapid succession can be lossy; some users prefer climate.set_temperature alone

---

## Used by

- Currently no automations consuming this device.
- **Not** the unit referenced by the "Carrier Infinity presence-aware setback" backlog item — that's a different Carrier system (likely the central HVAC). Don't conflate them.

---

## Why local instead of cloud

The official Carrier app uses Midea cloud relay. Local integration eliminates cloud dependency, reduces latency, and survives WAN outages. Per the broader pattern of preferring local over cloud where possible (cf. ADR-001 OmniLogic Local).

---

## Service / mounting (none captured — unit is uncomplicated)

No special service or mounting notes worth capturing here. Filter access, drainage, and physical service are conventional for a standard wall-mounted mini split.
