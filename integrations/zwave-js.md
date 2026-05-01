# Z-Wave JS

The Z-Wave network for LRD. Built-in HA integration backed by the Z-Wave JS app, with Z-Wave JS UI as the management front-end.

---

## Stack

- **Controller:** Zooz ZST39 LR 800 Series stick (USB on NUC)
- **Controller FW:** v1.70, SDK v7.24.2
- **Z-Wave JS app:** v1.3.0 (hostname `core-zwave-js`). Watchdog ON, auto-update intentionally OFF (manual upgrades only).
- **HA integration:** built-in (`zwave_js`)
- **Web UI:** Z-Wave JS UI (Daniel Lando's fork, accessed at `192.168.11.155` via the app's ingress). Used for Control Panel, Network Graph, inclusion/exclusion, FW updates, backups.

Network is fully migrated from Hubitat (retired). All Z-Wave devices currently live in this network.

### Network composition (35 nodes total: 1 controller + 34 devices)

| Manufacturer / Model | Count | FW |
|---|---|---|
| HomeSeer HS-WX300 wall dimmer/switch | 16 | mostly v2.1.13; node 034 on v2.2.0 (outlier) |
| Jasco 14314/ZW4002 in-wall fan speed | 5 | v5.24, all unsecured (No-Security inclusion path) |
| Zooz ZEN77 S2 dimmer | 3 | v4.70.0 |
| Minoston MP21ZD smart plug dimmer | 3 | v8.0.0 |
| Kwikset 916 door lock | 2 | v5.7 |
| Ecolink TILT-ZWAVE2.5-ECO tilt sensor | 2 | v10.1 (battery, FLiRS-style sleeping) |
| Zooz ZEN75 heavy-duty switch | 1 alive (node 032 — shower fan) + 1 dead (node 256 — toilet fan) | v1.30.0 |
| Fibaro FGD212 dimmer 2 | 1 | v3.5 |

**Z-Wave LR (Long Range):** controller is LR-capable but no devices currently use LR — all 34 devices are on classic Z-Wave Plus. LR is reserved for future-proofing. (Inference: based on protocol icons in Z-Wave JS UI Control Panel showing classic-only on every device row.)

---

## Known issues / patterns

- **Ghost nodes after failed inclusion.** Pattern: re-include a device, original orphan persists in registry, new entity ends up with `_2` suffix (e.g., `light.dimmer_2_2`). Fix: remove orphan from Z-Wave JS UI ("Remove Failed Node"), then optionally rename the survivor in HA registry to drop the suffix.
- **HS-WX300 fan controllers presenting as lights.** Older GE/Jasco devices and some HomeSeer fan switches expose a light entity rather than a fan entity. Workaround: treat as light or use device-specific config parameter to change.
- **No Security inclusion** required for some older GE/Jasco devices. S2 inclusion fails silently; fall back to "No Security" path in Z-Wave JS UI.
- **Mesh weakness around the lock.** Kwikset 916 has shown `neighbors:[]` / weak LWR — root cause of historic battery drain (retry storm). ZEN77 is acting as repeater for the lock; verify it's still reachable.
- **Provisioned-but-not-included** placeholder ghost nodes (HS-WX300 case). Resolution: remove via Z-Wave JS UI provisioning list.
- **HS-WX300 with non-dimmable loads** — set Parameter 11 (Ramp Rate Z-Wave) and Parameter 12 (Ramp Rate Manual) both to **0**. Instant on/off makes the paddle behave switch-like from the user's perspective; the slow default 3-sec ramp was causing users to hold the paddle waiting for fade-in, which produced the perceived "dimming." No need for hardware Switch Mode change (which requires exclusion + re-inclusion per HomeSeer R2 user guide) or HA template-switch wrapper. Verified on node 25 (Under Cabinet Lights) 2026-04-30. Apply to any WX300 driving a non-dimmable load (LED tape with non-dimmable driver, certain CFL/LED, etc.).

---

## Device inventory

Lives in `docs/device-inventory.md` (currently has gaps — see cleanup-plan 3.1).

---

## Useful commands / paths

When the network goes weird, in order of escalation:

1. **Z-Wave JS UI** → Control Panel → check node health (ping, neighbors, LWR)
2. **Heal network** — only after confirming a stable mesh; not a panacea
3. **Reload Z-Wave JS integration** in HA → Settings → Devices & Services
4. **Restart Z-Wave JS app** in Settings → Apps
5. **Restart HA Core** — reaches deeper state issues
6. **Pull stick + replug** — last resort; controller backup recommended first

Backups: Z-Wave JS UI → Settings → Backup. Take one before any controller firmware update or major mesh surgery.

---

## Past chat references

See `docs/ha-chat-index.md` Z-Wave migration section for the inclusion/exclusion battles, ghost node cleanups, and lock mesh diagnostics that produced the patterns above.
