# HA REST API curl cheat sheet

Quick-reference for the `curl` patterns used to inspect Home Assistant
state and history from the MacBook against the LRD HA NUC. All examples
assume `$HA_TOKEN` is exported (long-lived access token), and target the
NUC at `192.168.50.11:8123`.

For ad-hoc shell sessions on the MacBook, the user-accessible HA address
is always `192.168.50.11` — never `192.168.11.155` (that's the IoT VLAN
side and not routed from the workstation network).

---

## Setup

Persist the token in zsh so it survives new shell tabs. Replace the
placeholder with the actual long-lived access token created in HA UI →
Profile → Security → Long-Lived Access Tokens.

```
echo 'export HA_TOKEN="<paste-token-here>"' >> ~/.zshrc
source ~/.zshrc
```

Sanity-check the token is set in the current shell (prints token length,
not the value). Zero = not set.

```
echo ${#HA_TOKEN}
```

Sanity-check HA is reachable. `200` = OK + auth good. `401` = token bad
or unset. Anything else = network or HA Core problem.

```
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $HA_TOKEN" http://192.168.50.11:8123/api/
```

---

## Single entity state

State + last-update timestamp for one entity.

```
curl -s -H "Authorization: Bearer $HA_TOKEN" http://192.168.50.11:8123/api/states/sensor.pool_water_temp_external | jq -r '"\(.state)\t\(.last_updated)"'
```

Full state object (all attributes, friendly_name, etc.) — useful when
chasing entity_id mismatches or device_class oddities.

```
curl -s -H "Authorization: Bearer $HA_TOKEN" http://192.168.50.11:8123/api/states/sensor.pool_water_temp_external | jq '.'
```

---

## Multi-entity health check

Loop over a list of entities and dump state + timestamp for each.
`last_updated // .last_changed` handles entities that don't set
`last_updated` (e.g. some input_boolean states).

```
for e in sensor.pool_water_temp_external sensor.pool_water_temp_external_pool_float_battery_voltage sensor.pool_water_temp_external_pool_float_wifi_signal sensor.pool_water_temp_external_pool_float_uptime input_boolean.pool_float_ota_mode; do
  curl -s -H "Authorization: Bearer $HA_TOKEN" "http://192.168.50.11:8123/api/states/$e" | jq -r '"\(.entity_id)\t\(.state)\t\(.last_updated // .last_changed)"'
done
```

---

## Find entities by name pattern

Dump every entity whose entity_id contains a substring. Useful when
ESPHome's device-name prefixing creates unexpected entity_ids.

```
curl -s -H "Authorization: Bearer $HA_TOKEN" http://192.168.50.11:8123/api/states \
  | jq -r '.[] | select(.entity_id | test("pool")) | "\(.entity_id)\t\(.state)\t\(.last_updated)"'
```

Filter on multiple patterns with regex alternation.

```
curl -s -H "Authorization: Bearer $HA_TOKEN" http://192.168.50.11:8123/api/states \
  | jq -r '.[] | select(.entity_id | test("pool_water_temp|pool_float")) | "\(.entity_id)\t\(.state)"'
```

---

## History over a time window

Pull recorded history for one or more entities going back N hours. Uses
`date -u -v-NH` (BSD `date`, macOS-native) to compute the start timestamp.

Last 12 hours, multiple entities, raw JSON dump:

```
curl -s -H "Authorization: Bearer $HA_TOKEN" "http://192.168.50.11:8123/api/history/period/$(date -u -v-12H "+%Y-%m-%dT%H:%M:%SZ")?filter_entity_id=sensor.pool_water_temp_external_pool_float_battery_voltage,sensor.pool_water_temp_external_pool_float_wifi_signal,sensor.pool_water_temp_external_pool_float_uptime,sensor.pool_water_temp_external" | jq '.'
```

Last 1 hour, single entity, condensed `(timestamp, state)` rows:

```
curl -s -H "Authorization: Bearer $HA_TOKEN" "http://192.168.50.11:8123/api/history/period/$(date -u -v-1H "+%Y-%m-%dT%H:%M:%SZ")?filter_entity_id=sensor.pool_water_temp_external_pool_float_battery_voltage" | jq -r '.[][] | "\(.last_updated)\t\(.state)"'
```

Specific time range (start + end). Date format is ISO 8601 UTC.

```
curl -s -H "Authorization: Bearer $HA_TOKEN" "http://192.168.50.11:8123/api/history/period/2026-05-26T18:00:00Z?end_time=2026-05-26T22:00:00Z&filter_entity_id=sensor.pool_water_temp_external_pool_float_battery_voltage" | jq '.'
```

Count publishes per entity over a window (useful for cadence reliability —
how many wakes actually published vs the theoretical max):

```
curl -s -H "Authorization: Bearer $HA_TOKEN" "http://192.168.50.11:8123/api/history/period/$(date -u -v-12H "+%Y-%m-%dT%H:%M:%SZ")?filter_entity_id=sensor.pool_water_temp_external_pool_float_battery_voltage" | jq '.[0] | length'
```

Min/max/mean of a numeric sensor over a window:

```
curl -s -H "Authorization: Bearer $HA_TOKEN" "http://192.168.50.11:8123/api/history/period/$(date -u -v-12H "+%Y-%m-%dT%H:%M:%SZ")?filter_entity_id=sensor.pool_water_temp_external_pool_float_wifi_signal" | jq '[.[0][] | .state | tonumber? // empty] | {min: min, max: max, mean: (add/length)}'
```

---

## Service calls (write actions)

POST to `/api/services/<domain>/<service>` with a JSON body. Returns the
list of affected entities, or `[]` if the call hit nothing.

Turn an input_boolean off:

```
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" -d '{"entity_id":"input_boolean.pool_float_ota_mode"}' http://192.168.50.11:8123/api/services/input_boolean/turn_off
```

Turn an input_boolean on:

```
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" -d '{"entity_id":"input_boolean.pool_float_ota_mode"}' http://192.168.50.11:8123/api/services/input_boolean/turn_on
```

Generic pattern — call any service:

```
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" -d '{"entity_id":"<entity>", "<param>":"<value>"}' http://192.168.50.11:8123/api/services/<domain>/<service>
```

---

## Common gotchas

When `last_updated` matches across multiple sensors in a single device, it
proves they all published in the same wake cycle. Drift between
timestamps usually means HA deduped an identical value, not that the
device skipped publishing — particularly for diagnostic sensors that
don't set `state_class: measurement`.

`jq` errors with "Expected string key before ':'" mean the response body
isn't JSON. Common causes: token unset (HA returns plain-text 401), bad
entity_id (returns `404: Not Found`), or HA Core not responding. Drop
the `| jq` to see the raw response.

`null null null` from a state query means the entity_id doesn't exist.
Run the pattern-filter query (above) to find the real name — ESPHome's
device-prefix rule frequently produces longer entity_ids than expected
(e.g. `sensor.<device>_<sensor_name>` when the sensor name doesn't start
with the device name).

The history endpoint returns a list-of-lists: outer list is one element
per entity in the filter, each inner list is the state history. The `jq`
patterns above use `.[0][]` to flatten the first entity's history; for
multi-entity results iterate with `.[][]`.

`date -u -v-NH` is BSD `date` syntax (macOS native). On Linux, use
`date -u -d "N hours ago"` instead.

Always include the `Z` suffix on the timestamp passed to the history
endpoint. HA interprets a bare `2026-05-26T19:30:00` (no timezone marker)
as the HA server's local time — at LRD that's EDT, so the start time
ends up 4 hours in the future and the response is an empty `[]`. With
`Z` appended, HA parses it as explicit UTC and returns data correctly.

---

## Reference entities (LRD pool float v2)

ESPHome device `pool-water-temp-external`, HA-side entity_ids:

```
sensor.pool_water_temp_external
sensor.pool_water_temp_external_pool_float_battery_voltage
sensor.pool_water_temp_external_pool_float_wifi_signal
sensor.pool_water_temp_external_pool_float_uptime
input_boolean.pool_float_ota_mode
```

Additional derived sensors in HA (not directly from the float):

```
sensor.pool_water_temp_external_filtered
sensor.pool_water_temp_authoritative
```
