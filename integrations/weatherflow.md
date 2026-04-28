# WeatherFlow

Tempest weather station integrations. Two HA integrations run side-by-side — local for on-network real-time data, cloud for forecast and the second (off-network) Shore station.

---

## Integrations

### WeatherFlow (local)

- **HA integration:** built-in (`weatherflow`) — local UDP discovery
- **Status:** Active
- **Devices:** 2 (1 hub + 1 station, 32 entities total)
- **Hub:** `HB-00183756` — Tempest hub on the IoT VLAN (4 entities)
- **Station:** `ST-00184974` — Tempest "Outside" at Lake Ridge Dr (28 entities)
- **Why we use it:** real-time updates, low latency, no cloud dependency for current conditions and illuminance

### WeatherflowCloud (cloud)

- **HA integration:** built-in (`weatherflow_cloud`)
- **Status:** Active
- **Auth:** WeatherFlow personal access token (https://tempestwx.com/settings/tokens)
- **Locations:** 2 hubs / 62 entities total
  - **Lake Ridge Dr** — 31 entities (same physical Tempest as the local integration; cloud exposes additional derived/forecast entities)
  - **Shore In** — 31 entities (off-network station, only reachable via cloud)
- **Why we use it:** forecast data (not exposed by local integration), the Shore In station which is at a different location, historical / aggregated values

---

## Stations

Two physical Tempest stations across Scott's two residences (~6 months each).

| Station ID | Name | Location | Source | Notes |
|---|---|---|---|---|
| `ST-00184974` (hub `HB-00183756`) | Outside | Lake Ridge Dr (FL) | Local + Cloud | Pool automation, door automations, lighting. Local works because HA lives at LRD on the IoT VLAN. |
| `ST-XXXXXXXX` (TODO fill in — drill into the "Shore In" hub in WeatherflowCloud integration to see) | Shore In | Shore property (SLN) | Cloud only | No HA install at SLN yet, so no local integration possible from there. Currently monitor-only — no automations consume Shore In data (yet). |

(All WeatherFlow stations follow `ST-XXXXXXXX` IDs; hubs follow `HB-XXXXXXXX`.)

If HA ever moves or duplicates to the SLN property, the local integration would also become available there.

---

## Entities used by automations

| Entity | Source | Used by | Notes |
|---|---|---|---|
| `weather.lake_ridge_dr` | Cloud | Pool automation, weather card | `temperature` attribute = current OAT |
| `sensor.lake_ridge_dr_precipitation_today` | Cloud | Pool chlorinator boost | Reports in **mm** — pool blueprint converts to inches (`/ 25.4`) |
| `sensor.lake_ridge_dr_precipitation_yesterday` | Cloud | Pool chlorinator boost | Same mm-to-inch conversion |
| `sensor.st_00184974_illuminance` | Local | Pool light, lanai lights, door automations | Drives dusk detection (lux-based primary path) |
| `sensor.pool_forecast_high` | Template (derived from Cloud) | Pool automation (swim-day decision) | Defined in `config/templates.yaml` from WeatherFlow forecast |

(TODO: enumerate which other entities each automation reads.)

---

## Available but unused entities

The Tempest exposes ~28-32 entities per station. Below is the catalog of what's available but NOT currently consumed by any automation. Use this as a menu when adding new automations.

### Likely-useful candidates (priority for review)

| Entity / sensor | Source | Possible automation use |
|---|---|---|
| `sensor.<station>_lightning_strikes_today` | Local + Cloud | Pool cover close, BBQ shutdown alert, "lightning detected" notification while outside |
| `sensor.<station>_lightning_last_distance` | Local + Cloud | Same — gated by distance threshold |
| `sensor.<station>_lightning_last_time` | Local + Cloud | Suppress repeat alerts within X minutes |
| `sensor.<station>_wind_speed` | Local + Cloud | Awning/umbrella retract, lanai close, deck cushion stow alert |
| `sensor.<station>_wind_gust` | Local + Cloud | Same — typically a higher threshold than steady wind |
| `sensor.<station>_uv_index` | Local + Cloud | Pool umbrella deploy reminder, kid sun-exposure alerts |
| `sensor.<station>_solar_radiation` | Local + Cloud | Better than UV for solar production proxy |
| `sensor.<station>_humidity` | Local + Cloud | Dehumidifier control, BBQ moisture awareness |
| `sensor.<station>_dew_point` | Local + Cloud | AC efficiency / muggy-day flag for Carrier setback |
| `sensor.<station>_feels_like` | Local + Cloud | Outdoor comfort flag, presence-aware AC setpoints |
| `sensor.<station>_pressure_trend` | Cloud | Storm-incoming heuristic for pool cover / awning automation |

### Lower priority

| Entity / sensor | Notes |
|---|---|
| `sensor.<station>_wind_direction` | Useful only paired with awning orientation |
| `sensor.<station>_wind_lull` | Niche — base of gust calculation |
| `sensor.<station>_pressure_*` | Sea-level + station pressure |
| `sensor.<station>_battery_voltage` | Tempest is solar; battery voltage as health-check |
| `sensor.<station>_signal_strength` | Hub RF signal — diagnostics only |
| `sensor.<station>_precipitation_intensity` | Already covered by today/yesterday sensors |
| `sensor.<station>_precipitation_type` | Niche — "rain vs none" |

(Inference: entity ID patterns above use `<station>` as a placeholder. Actual IDs follow `sensor.st_00184974_<measure>` for local, `sensor.lake_ridge_dr_<measure>` for cloud. Confirm exact names in Settings → Devices & Services when wiring.)

---

## Known quirks

- **Some values come through in metric even when the Tempest app is set to imperial.** Scott specifically remembers needing to convert some Tempest data; the pool blueprint divides precipitation values by 25.4 (mm → inches), suggesting precipitation is the affected channel. Other channels may also be affected — verify when wiring new automations. The Tempest app's US-units setting does not appear to propagate to all HA-exposed sensor values.
- **Two integrations, overlapping entities.** The Lake Ridge Tempest appears in BOTH local and cloud integrations with similar but not identical entity sets. Don't assume an entity update in one source means the other has the latest value. Use local for real-time-critical reads, cloud for forecast and Shore In.
- **Forecast not exposed directly.** Forecast values come through the cloud integration but typically as attributes of the weather entity; pool automation depends on a template sensor that extracts the day's high.

---

## Setup

- **Lake Ridge station ID:** `ST-00184974`
- **Lake Ridge hub:** `HB-00183756`
- **Personal access token:** created at https://tempestwx.com/settings/tokens
- **Local discovery:** Tempest hub must be on the same VLAN as HA (currently IoT VLAN — works).
- **Shore In:** TODO capture station ID and any setup notes for the off-network deployment.

---

## Polling cadence

- **Local:** continuous UDP broadcast from hub (sub-minute updates).
- **Cloud:** TODO confirm cadence in HA Settings → Devices & Services → WeatherflowCloud. Typical for cloud weather integrations is 1-min current, less frequent forecast.
