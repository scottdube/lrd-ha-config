# OmniLogic

Hayward pool controller. Two integrations running side-by-side. See ADR-001 for the why.

---

## Local integration (control)

- **HACS repo:** [`cryptk/haomnilogic-local`](https://github.com/cryptk/haomnilogic-local)
- **Status:** Beta
- **Current version:** `1.0.0b7`
- **Communication:** UDP, direct LAN to controller
- **Controller IP:** `192.168.11.19` (DHCP reservation in UniFi)
- **Network:** IoT VLAN

### What it controls
- Pump (variable speed via `number.set_value` on speed entity)
- Heater (`water_heater.omnilogic_pool_heater`)
- Waterfall (`valve.omnilogic_pool_waterfall` — see ADR-004)
- Chlorinator (`number.set_value` on timed percent entity)
- Pool light
- Water temperature
- Air temperature

### Entity naming convention
`*.omnilogic_pool_*` (vs cloud's `*.pool_pool_*`). Easy to confuse. Always grep for `omnilogic_pool_` when wiring blueprints.

### Known issues
- **WiFi packet loss to controller (~30-40% per ping test).** Causes UDP fragment timeouts during HA restart. Workaround: HA recovers on its own after retries. Real fix: ethernet run to controller (pending).
- **Beta version churn.** Schema/domain changes occur between beta releases. Check release notes; audit blueprint for entity references after every upgrade. Audit unavailable entities in registry.
- **Stale entities post-rename.** When devices are re-included or domains change, ghost entities persist with `_2` suffix. Manual cleanup required.

### Open dialogue
GitHub issue #173 with maintainer. Maintainer has confirmed diagnostics are correct and the integration logic works against simulated data — environmental factors (WiFi packet loss) suspected for state-update issues.

---

## Cloud integration (monitoring only)

- **HACS repo:** [`djtimca/haomnilogic`](https://github.com/djtimca/haomnilogic)
- **Status:** Stable
- **Communication:** Cloud relay through Hayward servers
- **Authentication:** Hayward app credentials
- **Used for:** ORP, salt level, pH (sensors not exposed by local integration)

### Entity naming convention
`*.pool_pool_*` (note the doubled "pool"). Not used in blueprint service calls — sensors only.

### Known issues
- Internet-dependent. State updates pause during outages.
- Polling interval — confirm against current docs. Roughly minutes.

---

## Cross-integration notes

- **Both integrations create separate entity sets** for the same physical equipment. Don't delete one assuming the other will pick it up.
- **Dashboards reference both.** Cloud row shows ORP/salt/pH. Local row shows everything else.
- **Watchdog dashboard** monitors cloud availability. Confirmed: when cloud is firewalled, watchdog fires after a delay (cloud uses persistent connection that takes time to drop).

---

## Setup quirks

- **Temperature sensor naming.** If renamed in the Hayward app, the cloud integration won't find them. Defaults are `airTemp` and `waterTemp`.
- **Static IP for controller.** DHCP reservation in UniFi. Critical for local integration to reach it reliably.
- **Heat pump in AUTO mode.** Per ADR-002, the heat pump owns cycling. Confirm AUTO is set on the unit itself, not just in HA.

---

## Useful commands

When the integration goes weird, in order of escalation:

1. **Reload integration** — Settings → Devices & Services → OmniLogic Local → Reload
2. **Restart HA** — handles deeper state issues
3. **Audit registry** — Settings → Devices & Services → entities, filter `omnilogic`, look for `unavailable`
4. **Check controller WiFi** — UniFi → Client Devices → packet loss / signal strength
5. **Diagnostic dump** — for #173 or new issues, integration → ⋮ menu → Download diagnostics
