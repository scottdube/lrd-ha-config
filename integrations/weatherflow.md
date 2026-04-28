# WeatherFlow

Tempest weather station integration. Provides current conditions, forecasts, rain, illuminance, and lightning data used by pool automation and lighting.

---

## Cloud integration (current)

- **HA integration:** built-in (`weatherflow_cloud`) — TODO confirm exact integration name
- **Auth:** WeatherFlow personal access token
- **Hardware:** Tempest station (no separate hub)
- **Polling:** cloud-mediated; verify cadence in Settings → Devices & Services
- **Primary entity:** `weather.lake_ridge_dr`

## Local integration (planned, not yet active)

- **Status:** local UDP discovery should work now that HA is on the IoT VLAN with the Tempest. Backlog item in `docs/current-state.md`.
- **Why migrate:** lower latency, less cloud-dependent.

---

## Entities used by automations

| Entity | Used by | Notes |
|---|---|---|
| `weather.lake_ridge_dr` | Pool automation, weather card | Provides `temperature` attribute (current OAT) |
| `sensor.lake_ridge_dr_precipitation_today` | Pool chlorinator boost | Reports in **mm** — pool blueprint converts to inches (`/ 25.4`) |
| `sensor.lake_ridge_dr_precipitation_yesterday` | Pool chlorinator boost | Same mm-to-inch conversion |
| `sensor.st_00184974_illuminance` | Pool light + lanai lights | Tempest illuminance sensor — drives dusk detection |
| `sensor.pool_forecast_high` | Pool automation (swim-day decision) | Template sensor in `config/templates.yaml`, derived from WeatherFlow forecast |

---

## Known quirks

- **Rainfall in mm, not inches.** WeatherFlow's US units setting in the app does NOT convert sensor units — they remain mm in HA. Compensate at template-sensor or blueprint level.
- **Forecast sensor.** Forecast values not exposed directly as entities; pool automation depends on a template sensor in `config/templates.yaml` that extracts the day's high.

---

## Setup

- Tempest station ID: TODO (visible in Tempest app → Stations)
- Personal access token created at: https://tempestwx.com/settings/tokens
- Confirm station is on the IoT VLAN for local integration to work post-migration.
