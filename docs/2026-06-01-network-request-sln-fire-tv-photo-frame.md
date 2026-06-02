# Network request — SLN Fire TV access to LRD slideshow hub

**Date:** 2026-06-01
**From:** `home-assistant` project (LRD photo-frame package extension to SLN)
**To:** `network-docs` project
**Status:** Request — not yet applied

## What we need

A firewall rule that allows the SLN-side Fire TV stick (to be deployed
on the SLN smart-display / IoT VLAN, exact VLAN TBD per SLN network
plan) to reach the LRD-resident photo-frame slideshow web server over
the existing UniFi mesh VPN.

## Connection details

| Field            | Value                                             |
|------------------|---------------------------------------------------|
| Source site      | SLN (NH)                                          |
| Source VLAN      | TBD — whichever VLAN SLN places display/IoT devices on |
| Source device    | Fire TV Stick HD (new, not yet purchased)         |
| Destination site | LRD (FL)                                          |
| Destination VLAN | LRD-Servers (where the Mac Mini lives)            |
| Destination host | `192.168.50.10` (Mac Mini M4)                     |
| Destination port | TCP `8000`                                        |
| Protocol         | HTTP                                              |
| Direction        | SLN → LRD (Fire TV originates the connection)     |
| Transport        | UniFi mesh VPN, UDM Pro at LRD                    |

## Symmetric reference

LRD already has the analogous in-site rule for the LR Fire TV:
`LRD IoT VLAN → 192.168.50.10:8000`. This request is the cross-site
equivalent for the SLN Fire TV.

## Justification

The Fire TV at SLN will run Fully Kiosk Browser pointed at
`http://192.168.50.10:8000/slideshow`, identical to the LRD living
room production setup defined in `lrd-ha-config` ADR-018
(`docs/decisions/018-photo-frame-slideshow.md`). The slideshow hub
stays single-sourced on the LRD Mac Mini; we do not plan to stand up
a second hub instance at SLN at this stage. That decision can be
revisited later — see "Open follow-ups" in
`photo-frame-briefing-2026-05-16.md` item 4 (Florida property
replication, applied here in the SLN direction).

## Scope decisions for network-docs to make

1. **Source scoping** — narrow rule to a DHCP-reserved IP for the new
   Fire TV, or broad rule for the whole SLN IoT/display VLAN. Broader
   is simpler; narrower is the security-hygiene default. Either works.
2. **VLAN assignment** — confirm which SLN VLAN the Fire TV lands on.
   If SLN is using the same `IoT` naming as LRD, the cross-site rule
   becomes: `SLN IoT → LRD LRD-Servers:192.168.50.10/32 tcp 8000`.
3. **Logging** — recommend ALLOW with logging at first so we can verify
   actual traffic shape; drop logging once stable.
4. **DNS** — Fire TV will be pointed at the bare IP `192.168.50.10`,
   not a hostname. No DNS changes required.

## Validation

After the rule is in place and the Fire TV is on the network at SLN,
the success test is one of:

- From the Fire TV's network settings: open the FKB browser, enter
  `http://192.168.50.10:8000/slideshow`, confirm the slideshow renders.
- Or `curl -I http://192.168.50.10:8000/slideshow` from any other
  device on the same SLN VLAN as the Fire TV. Expect HTTP 200.

## Out of scope

- Any reverse direction (LRD → SLN) — not needed for this workload.
- ADB-over-TCP access from LRD HA to the SLN Fire TV. Will be a
  separate request when SLN HA comes online and we want LRD HA to
  drive the SLN Fire TV; until then, FKB's own auto-launch covers
  the boot path and no HA-side control is needed.
- Future slideshow hub `/health` endpoint mentioned in the briefing
  (item 1) — separate request when that endpoint exists.
