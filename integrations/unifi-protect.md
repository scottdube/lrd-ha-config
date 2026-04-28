# UniFi Protect

Camera integration for the UniFi camera system. Provides motion events, snapshots, RTSP streams, and doorbell events to HA.

---

## Stack

- **HA integration:** built-in (`unifi_protect`)
- **Controller:** UDM Pro (the same unit handling network/firewall — see `network-docs` project for the network side)
- **Auth:** local UniFi user (NOT a UI Account / cloud user — local-only credentials are required)

---

## Cameras

- TODO: enumerate cameras with location, model, entity prefix
- Each camera typically exposes: motion sensor, person/vehicle/animal detection (G4-series and newer), snapshot, stream, light (if equipped)

---

## Setup

1. Create a **local-only** UniFi user with admin role on the UDM Pro (Settings → Admins & Users → Add). The HA integration cannot use UI Account credentials.
2. Add the integration in HA with the local IP of the UDM Pro and the local user's credentials.
3. Verify the cameras and doorbell appear under the new device.

---

## Known quirks

- **Local user required.** UI Account auth fails with cryptic errors. Create a separate local user just for HA.
- **Reauth loops** can occur after UniFi controller upgrades — usually resolved by reloading the integration.
- **RTSP streams** require RTSPS to be enabled per-camera in the Protect app.
- **Person/vehicle/animal detection** requires Smart Detections enabled per-camera.

---

## Used by

- TODO: link to camera motion alert automations (cleanup-plan backlog item — "Camera motion alerts when away")
- Doorbell: TODO confirm wiring to TTS / mobile notification flow

---

## Cross-project note

The UDM Pro itself, its firewall rules, VLAN assignments, and zone policy live in the `network-docs` project. This file documents only the Protect integration and how HA consumes it. Don't put network-side decisions here.
