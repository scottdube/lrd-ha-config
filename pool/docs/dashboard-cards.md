# Pool dashboard cards

Reference YAML for pool-related Lovelace cards. HA dashboards are configured
in storage mode (`.storage/lovelace`), which means the live card YAML is NOT
in this git repo. If `.storage` is ever rebuilt (HA reinstall, migration,
or just an accidental dashboard reset) the cards have to be re-added by hand.

This file is the source of truth for those cards. Each section below is a
copy-pasteable Lovelace card block. To add one to a dashboard:

1. Edit Dashboard → click `+ Add Card` → select **Manual** at the bottom
2. Paste the YAML from the relevant section
3. Save

Same pattern as the Photo Frame dashboard buttons preserved in ADR-018.

---

## Pool Controller Network Health

**Purpose:** at-a-glance assessment of OmniLogic controller network reachability.
Combines the binary_sensor (reachable y/n) with packet loss, RTT average, and
jitter into a single card with traffic-light coloring + 24h history graph.

**Dependencies:**

- Mushroom cards (HACS — `piitaya/lovelace-mushroom`)
- Ping (ICMP) integration configured for `192.168.11.19` (the OmniLogic
  controller) with device name `pool_controller_reachable`. See
  `integrations/omnilogic.md` → "Ping binary_sensor setup" section.
- All five ping diagnostic entities enabled (packet loss + jitter + RTT
  average/min/max). HA disables them by default; enable via Settings →
  Devices & Services → Ping → click the device → enable in the entity
  list. Card references the three primary ones: packet loss, RTT average,
  jitter.

**Threshold-color mapping (chip icons):**

| Chip | Green | Orange | Red |
|---|---|---|---|
| Packet loss | <1% | 1-10% | >10% |
| RTT average | <2ms | 2-10ms | >10ms |
| Jitter | <1ms | 1-5ms | >5ms |
| Reachable | on | — | off |

The 10% packet-loss threshold matches `automation.pool_alert_on_controller_network_degrading`'s
watcher fire condition — chip turns red right when the watcher fires.

**Suggested placement:** main overview dashboard, near other infrastructure-health
cards (network status, NUC health, etc.). Also useful on the pool dashboard
proper if you want it visible while looking at pool state.

**YAML:**

```yaml
type: vertical-stack
cards:
  - type: custom:mushroom-title-card
    title: Pool Controller Network
    subtitle: Hayward OmniLogic @ 192.168.11.19
  - type: custom:mushroom-chips-card
    alignment: center
    chips:
      - type: template
        icon: |
          {% if is_state('binary_sensor.pool_controller_reachable', 'on') %}mdi:lan-connect{% else %}mdi:lan-disconnect{% endif %}
        icon_color: |
          {% if is_state('binary_sensor.pool_controller_reachable', 'on') %}green{% else %}red{% endif %}
        content: |
          {% if is_state('binary_sensor.pool_controller_reachable', 'on') %}Online{% else %}Offline{% endif %}
      - type: template
        icon: mdi:percent
        icon_color: |
          {% set v = states('sensor.192_168_11_19_packet_loss') | float(0) %}
          {% if v < 1 %}green{% elif v < 10 %}orange{% else %}red{% endif %}
        content: "{{ states('sensor.192_168_11_19_packet_loss') }}% loss"
      - type: template
        icon: mdi:swap-horizontal-bold
        icon_color: |
          {% set v = states('sensor.192_168_11_19_round_trip_time_average') | float(0) %}
          {% if v < 2 %}green{% elif v < 10 %}orange{% else %}red{% endif %}
        content: "{{ states('sensor.192_168_11_19_round_trip_time_average') | round(2) }}ms"
      - type: template
        icon: mdi:sine-wave
        icon_color: |
          {% set v = states('sensor.192_168_11_19_jitter') | float(0) %}
          {% if v < 1 %}green{% elif v < 5 %}orange{% else %}red{% endif %}
        content: "{{ states('sensor.192_168_11_19_jitter') | round(2) }}ms jitter"
  - type: history-graph
    title: Last 24 hours
    hours_to_show: 24
    entities:
      - entity: sensor.192_168_11_19_packet_loss
        name: Packet loss (%)
      - entity: sensor.192_168_11_19_round_trip_time_average
        name: RTT avg (ms)
      - entity: sensor.192_168_11_19_jitter
        name: Jitter (ms)
```

**Entity ID caveat:** the ping integration's diagnostic sensors are named with
the host IP (`sensor.192_168_11_19_*`) rather than the device name. If the
OmniLogic controller's IP ever changes (DHCP reassignment, network reorg),
all five sensor entity IDs will be regenerated and this card will go blank.
DHCP reservation is in place per `integrations/omnilogic.md` so this should
be stable, but worth knowing for future debugging.

**Threshold tuning notes (2026-05-18 observation):** initial deployment showed
RTT chip at orange (2.68ms) and jitter chip at orange (1.81ms) in steady
state — these are in the warning band but well below the watchers' actual
alarm thresholds. If the orange-in-steady-state bothers you visually, relax
the chip thresholds (e.g., green up to 5ms RTT, 3ms jitter). The watchers
themselves (`automation.pool_alert_on_controller_network_degrading` etc.)
have wider thresholds and don't need to change.

---

## Future card slots

When new pool-related cards are added (pump status detail, blueprint state,
auditor results, etc.), each gets its own section here following the same
pattern: purpose, dependencies, threshold-color mapping (if any), placement,
YAML, caveats.
