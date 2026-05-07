# ADR-005: Bind HA Core http.server_host to LRD-Servers IP only (post dual-VLAN)

**Status:** Accepted
**Date:** 2026-04-30
**Decider:** Scott
**Cross-references:** network-docs ADR-009 (NUC migration to LRD-Servers VLAN), network-docs ADR-011 (HA NUC trunked to IoT VLAN for broadcast/multicast adjacency)

## Context

ADR-009 (network-docs) migrated the HA NUC from the IoT VLAN to the LRD-Servers VLAN on 2026-04-29. Pre-flight pcap-based traffic characterization (the work that had been "in flight" in current-state.md) missed an entire traffic class: broadcast/multicast. Broadcasts arrive natively on the source's L2 segment without being routed, so a unicast-focused capture wouldn't surface them.

Once the NUC moved off the IoT VLAN, the WeatherFlow Tempest **local** integration silently broke. It relies on UDP broadcast on `192.168.11.255:50222` from the Tempest hub, which sits on the IoT VLAN.

ADR-011 (network-docs) was the response: rather than roll back ADR-009, add a tagged VLAN sub-interface (`eno1.4` / `192.168.11.155/24`) on HA OS so the NUC has L2 adjacency to the IoT VLAN for broadcast reception only. Default route stays on `eno1` (LRD-Servers, `.50.1`). `eno1.4` has no gateway, no DNS, IPv6 disabled — passive listener.

This creates a security gap: with `eno1.4` up, HA Core's web UI (default bind `0.0.0.0:8123`) would be reachable on `http://192.168.11.155:8123` from any IoT device. The IoT VLAN is the lowest-trust zone — any compromised IoT device could probe `:8123`, attempt brute-force login, or hit known HA CVE surface. ADR-009's whole point was to put HA in a higher-trust zone; failing to restrict the bind would undo the security posture while keeping the operational benefit.

## Decision

Add explicit `http.server_host` restriction to `/config/configuration.yaml`:

```yaml
http:
  server_host:
    - 192.168.50.11
    - 127.0.0.1
    - 172.30.32.1
```

HA Core's web server binds to the LRD-Servers IP, localhost, and the hassio Docker bridge interface. Even though the host has an interface at `192.168.11.155`, the web UI does not listen there.

The `172.30.32.1` entry is the **hassio Docker bridge IP** that Core uses to talk to the Supervisor. Without this entry, Supervisor's WebSocket connection to Core fails — see Revision 2026-05-06 below.

Mobile app, browser access from trusted clients, and Nabu Casa cloud relay all reach HA via `192.168.50.11:8123` (or via Nabu Casa's outbound tunnel, which is unaffected). The IoT-side `192.168.11.155` IP is reserved for inbound broadcast/multicast reception only.

## Consequences

### Positive
- Web UI not reachable from the IoT VLAN. ADR-009's security gain is preserved.
- WeatherFlow Tempest local integration continues to receive broadcasts via `eno1.4`.
- Pattern is reusable: any future broadcast-dependent local integration (TP-Link Tapo, SSDP-discovered IoT devices) can rely on `eno1.4` adjacency without exposing more web surface.

### Negative
- Future host migration (different IP) requires updating `server_host`. Removing this block without replacement reopens the IoT-side exposure.
- Reverse-proxy or new HA bind requirements need to compose with this list, not replace it.

### Operational note — File Editor add-on YAML mangling
During the recovery, the HA File Editor add-on silently mangled the YAML list form on save: it dropped the `-` list dashes and produced invalid YAML. HA Core failed to restart. Recovery required SSH to HA OS and `nano` direct edit.

**Rule:** for any list-valued key in `configuration.yaml` (or other root config files), use **Studio Code Server** or **SSH + nano**. Do **not** use the File Editor add-on for list edits. (See current-state.md "Recently completed" for the SCS-in-own-tab clipboard workaround if SCS itself misbehaves.)

### Tripwires for future HA work
- Don't remove `http.server_host` without a replacement that preserves the bind restriction.
- **`server_host` MUST include the hassio Docker bridge IP (`172.30.32.1`)** in addition to user-facing IPs and localhost. Without it, Supervisor cannot connect to Core's WebSocket from its own container, and every Supervisor↔Core operation that requires WebSocket coordination silently fails (backups most visibly). The original ADR-005 deployment omitted this and broke Supervisor↔Core for ~6 days before the symptom became severe enough to surface. See Revision 2026-05-06.
- Don't delete the `eno1.4` sub-interface on HA OS — local integration that depends on IoT-VLAN broadcasts will silently break. Persistence is handled by HA Supervisor (`ha network vlan` command) — no `.nmconnection` edits needed.
- If networking is re-architected, broadcast/multicast adjacency is the constraint to design around. ADR-011 (network-docs) explains the trade-offs.

## Revision 2026-05-06 — Supervisor bridge IP added to server_host

**Symptom observed today:** Manual backups failed with "Failed to inform HA Core: Can't connect to Home Assistant Core WebSocket, the API is not reachable." Daily automatic backups had been silently failing since 2026-04-30 (the last successful backup). Google Drive Backup app's 3-hour scheduled runs each failed and progressively wedged Supervisor's job-group state, surfacing today as "backup already in progress" UI errors that blocked Core restart and the ESPHome Device Builder app update.

**Root cause:** ADR-005's original `server_host` list (`192.168.50.11` + `127.0.0.1`) excluded the hassio Docker bridge IP `172.30.32.1`, which is the address Supervisor uses to reach Core's HTTP/WebSocket endpoint from its own container. Core's HTTP server bound only to user-facing IPs and the container's loopback — the bridge interface had no listener. Supervisor's WebSocket connection attempts were refused at the TCP level, and every Supervisor-mediated operation that needed Core (backups, service calls, hardware events propagated to Core, etc.) failed silently.

**Why it took 6 days to surface:** HA Core's HTTP/UI continued to work (Scott uses 192.168.50.11), Studio Code Server worked (uses localhost), and direct API calls from Scott's browser worked. The break was confined to the internal Supervisor↔Core control channel, which is invisible from the user's normal interaction pattern until a Supervisor-mediated operation fails. With Core watchdog also disabled (separately), nothing auto-recovered. The Google Drive Backup app's 3-hour cadence accumulated failures that eventually wedged enough state to make the failure visible.

**Fix applied:** Added `172.30.32.1` to the `server_host` list. Verified by clearing job-group locks (`ha jobs reset`), restarting Core, and confirming WebSocket warnings no longer appear in supervisor logs.

**Lesson:** When restricting `http.server_host` on HA OS / Supervised installs, always include the supervisor-facing bridge IP. Default Docker bridge for hassio is `172.30.32.0/24` with Core at `.32.1`. The `ha core info` command's `ip_address` field reports the current bridge IP — this is the value to include.
