# UniFi Protect

Camera integration for the UniFi camera system. Provides motion events, snapshots, RTSP streams, and doorbell events to HA.

---

## Stack

- **HA integration:** built-in (`unifi_protect`)
- **Controller:** UDM SE (Lake Ridge Dr UDM SE — no separate UNVR / NVR Pro)
- **UniFi OS:** v5.0.16
- **Protect app:** v7.0.107
- **Controller IP from HA's VLAN:** `192.168.11.1` (the UDM's IP on the IoT VLAN where HA lives)
- **Controller IP from cameras' VLAN:** `192.168.0.1` (the UDM's IP on the camera/management VLAN)
- **Planned change:** when UDM moves to the server zone, the IP HA connects to becomes `192.168.50.1` (cross-project — `network-docs` ADR-008)
- **HA auth:** local user `admin` on the UDM SE (not a UI Account / cloud SSO)

---

## Cameras

All cameras on the dedicated camera VLAN at `192.168.4.x`. Continuous recording across the fleet. Smart Detections enabled on the G4-class indoor / doorbell cameras; **disabled on the G5 Pro front/side cameras** (worth reviewing — see Open issues).

| Friendly name | Model | IP | Smart Detections | FW | Notes |
|---|---|---|---|---|---|
| G4 Doorbell Pro | G4 Doorbell Pro | 192.168.4.143 | Enabled | 5.3.84 | Front door — see Doorbell section below |
| G4 Instant Family Room | G4 Instant | 192.168.4.244 | Enabled | 5.3.84 | Indoor |
| G5 Bullet | G5 Bullet | 192.168.4.119 | — | 5.3.84 | Smart Detections not configured |
| G5 Bullet Lanai East | G5 Bullet | 192.168.4.93 | — | 5.3.84 | Lanai exterior |
| G5 Bullet Lanai West | G5 Bullet | 192.168.4.98 | — | 5.3.84 | Lanai exterior |
| G5 Pro Front East | G5 Pro | 192.168.4.41 | **Disabled** | 5.3.84 | Front exterior |
| G5 Pro Front West | G5 Pro | 192.168.4.177 | **Disabled** | 5.3.84 | Front exterior |
| G5 Pro Left side | G5 Pro | 192.168.4.169 | **Disabled** | 5.3.84 | Side exterior |
| G5 Pro Right Side | G5 Pro | 192.168.4.77 | **Disabled** | 5.3.84 | Side exterior |
| Garage Right | G5 Bullet | 192.168.4.114 | — | 5.3.84 | Garage exterior |
| G4 Instant Master | G4 Instant | 192.168.0.116 | Enabled (was) | 5.1.219 | **OFFLINE** since 2026-01-04. "Click to Reconnect" in Protect. Note: on `192.168.0.x`, not the camera VLAN — possibly a leftover from prior network layout. Older FW (5.1.219). |

(IPs and FW captured 2026-04-28.)

---

## Doorbell

- **Model:** G4 Doorbell Pro
- **IP:** 192.168.4.143
- **Location:** Front door
- **HA wiring on ring event:** Protect mobile push notification fires (no custom HA flow yet — TTS / Echo Speaks / light flash all options worth wiring).
- **Live view in HA:** today only via the Protect app — no HA dashboard card configured.
- **Two-way audio:** **broken in HA** — surfaces only via the Protect app. Open issue.

---

## Storage

- **Where:** UDM SE internal HDD at LRD (8 TB drive, ~7.93 TB usable). No NAS, no separate NVR.
- **Current utilization:** 7.88 TB / 7.93 TB used (effectively full)
- **Storage Budgeting** (UniFi Labs feature): Balanced mode — 50% High Quality, 50% Low Quality
- **Storage breakdown** (snapshot 2026-04-28): HQ 3.43 TB · LQ 2.73 TB · Persistently Stored 3.22 GB · Scrubbing 34.4 GB · Unused 1.67 TB · System 68.7 GB
- **Retention** (estimated by UniFi Storage Budgeting):
  - High Quality recording: ~360 GB/day → ~11 days
  - Low Quality recording: ~41 GB/day → ~96 days
  - Oldest recording on disk: ~3 months ago
- **Recording trigger:** Continuous on every active camera
- **Storage health in HA:** UDM disk health surfaces as a sensor (verify entity name when wiring an alert)

---

## Setup

1. Create a local user with admin role on the UDM SE: **People → Create New → Create New User**.
2. Add the integration in HA, pointing at the UDM SE local IP from HA's VLAN (currently `192.168.11.1`) and the local user's credentials.
3. Verify cameras and doorbell appear under the new device.

---

## Known quirks

- **Local user account in HA, not UI Account.** HA uses the local UniFi user `admin` for the integration — not a unifi.ui.com SSO account.
- **RTSPS streams** are enabled per-camera at **Devices → click camera → Settings** in the Protect UI.
- **Two-way audio on the doorbell is broken in HA** — surfaces only in the Protect app.
- **Smart Detections** (person / vehicle / animal / package) — enable per-camera in Protect. Whether basic motion alone surfaces these object classes vs. requiring Smart Detections explicitly enabled is a per-camera-and-model behavior; verify rather than assume.

---

## Used by

- **Camera motion alerts when away** — planned (cleanup-plan / current-state backlog).
- **Doorbell ring → Protect mobile push** — live (no custom HA-side flow yet).
- TODO: as new automations are wired, list them here.

---

## Cross-project notes

- **UDM SE itself** — its firewall rules, VLAN assignments, and zone policy live in the `network-docs` project. This file documents only the Protect integration and how HA consumes it.
- **Planned UDM move to server zone** — when ADR-008 lands and the UDM ends up at `192.168.50.1`, update the Controller IP here and re-add the integration if needed.

---

## Open issues

- **G4 Instant Master offline since 2026-01-04.** On `192.168.0.116`, older FW. Decide: reconnect/repair, decommission, or replace.
- **G5 Pro front/side cameras have Smart Detections disabled.** Four cameras in arguably the most useful detection positions (front + sides) — worth enabling person/vehicle detection unless there's a specific reason it's off (false positives, license cost, etc.).
- **Doorbell two-way audio broken in HA.** Surfaces only in the Protect app.
- **Storage at 99% utilization.** Balanced mode auto-rotates oldest, but worth monitoring; drive replacement or storage tier change may be needed if retention requirements grow.
- **Per-camera recording trigger uniformity.** All cameras on Continuous today — confirm that's the intent vs. mixing motion-only / smart-event-only for the Smart-Detections-disabled cameras.
