# Midea AC LAN

LAN-based control of Midea-protocol mini split. Recently added (per `docs/current-state.md`).

---

## Stack

- **HACS repo:** [`georgezhao2010/midea_ac_lan`](https://github.com/georgezhao2010/midea_ac_lan) — TODO verify exact fork in use
- **Custom component path:** `custom_components/midea_ac_lan/`
- **Communication:** LAN (no cloud dependency)
- **Device:** Carrier `38MARBQ24AA3` mini split (Midea-OEM internals)

---

## Entity

- TODO: capture exact entity ID (`climate.<...>`)
- Climate platform — supports HVAC modes, fan speed, target temp, swing

---

## Setup

- **Discovery:** integration discovers Midea devices on local subnet
- **Auth:** requires Midea cloud account credentials on first add to retrieve device key/token, but ongoing operation is local-only
- **Network:** device must be reachable from HA's VLAN (IoT). Confirm DHCP reservation in UniFi.

---

## Known quirks

- TODO: capture as encountered. Common Midea-LAN patterns include occasional connection drops requiring HA integration reload, and fan-mode mappings that don't match the unit's remote-control labels.

---

## Why local instead of cloud

The official Carrier app uses Midea cloud relay. Local integration eliminates cloud dependency, reduces latency, and survives WAN outages. Per the broader pattern of preferring local over cloud where possible (cf. ADR-001 OmniLogic Local).
