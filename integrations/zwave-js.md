# Z-Wave JS

The Z-Wave network for LRD. Built-in HA integration backed by the Z-Wave JS server (HA add-on), with Z-Wave JS UI as the management front-end.

---

## Stack

- **Controller:** Zooz ZST39 LR 800 Series stick (USB on NUC)
- **Controller FW:** v1.70 (per device-inventory.md)
- **Add-on:** Z-Wave JS server (core add-on)
- **Manager UI:** Z-Wave JS UI (HACS / community add-on)
- **HA integration:** built-in (`zwave_js`)

Network is fully migrated from Hubitat (retired). All Z-Wave devices currently live in this network.

---

## Known issues / patterns

- **Ghost nodes after failed inclusion.** Pattern: re-include a device, original orphan persists in registry, new entity ends up with `_2` suffix (e.g., `light.dimmer_2_2`). Fix: remove orphan from Z-Wave JS UI ("Remove Failed Node"), then optionally rename the survivor in HA registry to drop the suffix.
- **HS-WX300 fan controllers presenting as lights.** Older GE/Jasco devices and some HomeSeer fan switches expose a light entity rather than a fan entity. Workaround: treat as light or use device-specific config parameter to change.
- **No Security inclusion** required for some older GE/Jasco devices. S2 inclusion fails silently; fall back to "No Security" path in Z-Wave JS UI.
- **Mesh weakness around the lock.** Kwikset 916 has shown `neighbors:[]` / weak LWR — root cause of historic battery drain (retry storm). ZEN77 is acting as repeater for the lock; verify it's still reachable.
- **Provisioned-but-not-included** placeholder ghost nodes (HS-WX300 case). Resolution: remove via Z-Wave JS UI provisioning list.

---

## Device inventory

Lives in `docs/device-inventory.md` (currently has gaps — see cleanup-plan 3.1).

---

## Useful commands / paths

When the network goes weird, in order of escalation:

1. **Z-Wave JS UI** → Control Panel → check node health (ping, neighbors, LWR)
2. **Heal network** — only after confirming a stable mesh; not a panacea
3. **Reload Z-Wave JS integration** in HA → Settings → Devices & Services
4. **Restart Z-Wave JS add-on** in Settings → Add-ons
5. **Restart HA Core** — reaches deeper state issues
6. **Pull stick + replug** — last resort; controller backup recommended first

Backups: Z-Wave JS UI → Settings → Backup. Take one before any controller firmware update or major mesh surgery.

---

## Past chat references

See `docs/ha-chat-index.md` Z-Wave migration section for the inclusion/exclusion battles, ghost node cleanups, and lock mesh diagnostics that produced the patterns above.
