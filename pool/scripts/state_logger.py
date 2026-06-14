#!/usr/bin/env python3
"""
Pool state logger v2.

Replaces v1's temp_logger.py. Always-on logging (no pump-on gate), captures
the full state surface of the OmniLogic Local integration plus environmental
context, in a single wide CSV row per call.

See pool/docs/logger-v2.md for design rationale and column inventory.
See pool/docs/data-schema-v2.md for the canonical column manifest.

Setup
-----
1. In HA: Profile (bottom left) → Security → Long-Lived Access Tokens
   → Create. Copy the token.
2. Save the token to /config/.state_logger_token (owned by the homeassistant
   user, mode 600). The .gitignore excludes this file.
3. configuration.yaml has shell_command.pool_state_log defined to invoke
   this script.
4. automations.yaml runs that shell_command on a 10-min time pattern.
   State-change triggers will be added in phase 1.5.

Usage
-----
    python3 state_logger.py [--row-type ROW_TYPE] [--trigger-entity ENTITY_ID]

    --row-type        time_pattern (default) or state_change
    --trigger-entity  for state_change rows: which entity transitioned

The script reads HA states via the REST API at http://localhost:8123,
appends one row to /config/pool_state_log.csv, and creates the file (with
header) if it doesn't exist.

Failure handling
----------------
Any single entity that returns an error or is unavailable is recorded as
the literal string "unavailable" — the row still gets written. The script
fails loud only on missing token or unrecoverable filesystem errors.

Phase scope
-----------
Phase 1: local OmniLogic + environmental + computed water_temp_reliable.
         ~35 columns. (shipped 2026-05-02)
Phase 1.5: state-change triggers + per-entity context capture
         (user_id, parent_id, last_changed) for pump, waterfall, heater.
         Adds 9 columns (44 total). Schema version 2.0-phase1.5.
         Schema rotation logic preserves phase 1 data side-by-side.
Phase 2: external water temp sensor integration per ADR-015. Added
         5 columns (49 total) — external_water_temp,
         external_water_temp_age_min, external_water_temp_fresh,
         water_temp_authoritative (cascading fallback), water_temp_delta.
         Pure observation in this phase — blueprint and auditor don't
         act on these yet. Schema version 2.0-phase2. Schema rotation
         preserves phase 1.5 data side-by-side.
Phase 2.1 (this version, 2026-05-22): external probe diagnostics.
         Adds 1 column (50 total) — external_wifi_rssi. Used to
         investigate the 5-19 → 5-21 freshness-degradation pattern
         (86% → 70% publish success). Distinguishes signal-attenuation
         cause from battery-sag cause. Schema version 2.0-phase2.1.
         Schema rotation preserves phase 2 data side-by-side.
Phase 3: cloud OmniLogic columns, expected_state computed columns,
         W1/W2 auditor assertions on external water temp data quality.
         Likely also: VBAT sensing for the external probe (requires
         hardware mod — external voltage divider on a free XIAO C6 GPIO).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = "/config/pool_state_log.csv"
TOKEN_FILE = "/config/.state_logger_token"
HA_BASE = "http://localhost:8123"
SCHEMA_VERSION = "2.0-phase2.1"

# External water temp sensor entity (ADR-015 deployment, 2026-05-18).
# Default ESPHome-composed entity_id was
# `sensor.pool_water_temp_external_pool_water_temp_external` (doubled because
# both the device name and the sensor name in ESPHome are "Pool Water Temp
# External"). Renamed in HA UI to the clean form below — the override is
# sticky in HA's entity registry and persists across ESPHome flashes.
EXTERNAL_WATER_TEMP_ENTITY = "sensor.pool_water_temp_external"

# Phase 2.1 (2026-05-22): WiFi signal sensor for the external probe.
# Already exposed by esphome/pool-water-temp-external.yaml as a
# `wifi_signal` sensor named "Pool Float WiFi Signal" — published once
# per wake by the on_boot script. The ESPHome-composed entity_id is
# typically `sensor.pool_water_temp_external_pool_float_wifi_signal`
# (device friendly_name + sensor name slugified). If renamed in HA UI,
# adjust this constant to match. Used to correlate publish-success with
# signal strength to diagnose the 2026-05-22 freshness-degradation
# pattern (declining from 86% on 5-19 to 70% on 5-21).
EXTERNAL_WIFI_RSSI_ENTITY = "sensor.pool_water_temp_external_pool_float_wifi_signal"

# Heartbeat entity for external-probe freshness. The float publishes uptime
# (seconds since boot) once per wake; that value is effectively unique every
# boot, so its last_changed advances on EVERY wake (verified 117/117 wakes,
# zero dedup). This is the ONLY reliable "the probe reported" signal on this
# device: the temp / wifi / battery values frequently repeat across wakes, and
# on this HA + ESPHome path an unchanged re-report advances NEITHER last_changed
# NOR last_reported (confirmed empirically 2026-06-14 — see ADR-031), so their
# timestamps stall 60-120 min even though the probe reported on schedule.
EXTERNAL_UPTIME_ENTITY = "sensor.pool_water_temp_external_pool_float_uptime"

# Freshness threshold for external water temp reading. ESP32-C6 deep-sleeps
# 30 min between samples (production cadence per ADR-015). Reading is
# considered fresh if the uptime heartbeat's last_changed is within 35 min of
# now (30 min sleep + 5 min grace for boot/wifi/publish lag). Bench-test cadence
# (1 min sleep) would want this set to ~2 min; production = 35 min.
FRESHNESS_THRESHOLD_MIN = 35

# Water-temp reliability threshold: pump must have been on for at least this
# many seconds before the OmniLogic water temp sensor is considered settled.
# Tunable; see pool/docs/logger-v2.md and ADR-008.
WATER_TEMP_SETTLING_SECONDS = 600  # 10 min

# Hayward HP31005T heat pump rated input power. Computed as V × A at the
# nominal 230V rating: 230 × 33.9A = 7797W. This is the estimated draw when
# the compressor is actively running. Real draw varies (lower in cooling
# mode, lower at partial heat-output, higher during defrost). Estimate is
# upper bound. Future ADR-009 (whole-home power monitoring) will replace
# this with measured data.
HEATER_RATED_POWER_W = 7800
HEATER_MODEL = "HP31005T"

# Column manifest. Each entry:
#   name        : CSV column name
#   source      : 'compute', 'state', or 'attr'
#   entity      : (state/attr) entity_id to read
#   attr        : (attr) attribute name on that entity
#   compute_fn  : (compute) function returning the value
#
# Order matters — it's the order columns appear in the CSV.
COLUMNS: list[dict] = [
    # ---------- Time ----------
    {"name": "timestamp", "source": "compute"},
    {"name": "row_type", "source": "compute"},
    {"name": "trigger_entity", "source": "compute"},

    # ---------- Environmental ----------
    {"name": "forecast_high", "source": "state",
     "entity": "sensor.pool_forecast_high"},
    {"name": "swim_day_raw", "source": "state",
     "entity": "sensor.pool_swimming_day"},
    {"name": "oat_weatherflow", "source": "attr",
     "entity": "weather.lake_ridge_dr", "attr": "temperature"},
    {"name": "illuminance_lux", "source": "state",
     "entity": "sensor.st_00184974_illuminance"},
    {"name": "precipitation_today", "source": "state",
     "entity": "sensor.lake_ridge_dr_precipitation_today"},
    {"name": "precipitation_yesterday", "source": "state",
     "entity": "sensor.lake_ridge_dr_precipitation_yesterday"},

    # ---------- Local: heater ----------
    {"name": "local_heater_state", "source": "state",
     "entity": "water_heater.omnilogic_pool_heater"},
    {"name": "local_heater_equip_status", "source": "state",
     "entity": "binary_sensor.omnilogic_pool_heater_heater_equipment_status"},
    {"name": "local_heater_equip_state", "source": "attr",
     "entity": "water_heater.omnilogic_pool_heater",
     "attr": "omni_heater_equip_Heater__state"},
    {"name": "local_heater_equip_enabled", "source": "attr",
     "entity": "water_heater.omnilogic_pool_heater",
     "attr": "omni_heater_equip_Heater__enabled"},
    {"name": "local_heater_target", "source": "attr",
     "entity": "water_heater.omnilogic_pool_heater",
     "attr": "temperature"},
    {"name": "local_heater_solar_set_point", "source": "attr",
     "entity": "water_heater.omnilogic_pool_heater",
     "attr": "omni_solar_set_point"},
    {"name": "local_heater_why_on", "source": "attr",
     "entity": "water_heater.omnilogic_pool_heater",
     "attr": "omni_why_on"},

    # ---------- Local: filter pump ----------
    {"name": "local_filter_state", "source": "state",
     "entity": "switch.omnilogic_pool_filter_pump"},
    {"name": "local_filter_state_enum", "source": "attr",
     "entity": "switch.omnilogic_pool_filter_pump", "attr": "omni_filter_state"},
    {"name": "local_filter_why_on", "source": "attr",
     "entity": "switch.omnilogic_pool_filter_pump", "attr": "omni_why_on"},
    {"name": "local_filter_speed", "source": "state",
     "entity": "number.omnilogic_pool_filter_pump_speed"},
    # Filter power (W) — exposed by integration as a sensor on filter.
    # Entity ID guess based on naming pattern; verify after first poll.
    # Critical for: (a) energy/cost analysis vs. cube-law estimates,
    # (b) predictive maintenance — anomalous power-vs-speed ratio
    # signals impeller wear, blockage, or bearing degradation.
    {"name": "local_filter_power", "source": "state",
     "entity": "sensor.omnilogic_pool_filter_pump_power"},

    # ---------- Local: waterfall ----------
    {"name": "local_waterfall_state", "source": "state",
     "entity": "valve.omnilogic_pool_waterfall"},
    {"name": "local_waterfall_function", "source": "attr",
     "entity": "valve.omnilogic_pool_waterfall", "attr": "omni_function"},
    {"name": "local_waterfall_why_on", "source": "attr",
     "entity": "valve.omnilogic_pool_waterfall", "attr": "omni_why_on"},

    # ---------- Local: chlorinator ----------
    {"name": "local_chlorinator_state", "source": "state",
     "entity": "switch.omnilogic_pool_chlorinator"},
    {"name": "local_chlorinator_percent", "source": "state",
     "entity": "number.omnilogic_pool_chlorinator_timed_percent"},

    # ---------- Local: water + air ----------
    {"name": "local_water_temp", "source": "state",
     "entity": "sensor.omnilogic_pool_watersensor"},
    {"name": "local_water_temp_reliable", "source": "compute"},

    # ---------- Phase 2: external water temp + cascading fallback (ADR-015) ----------
    # External sensor on XIAO ESP32-C6 in the pool. 30-min deep-sleep cadence.
    # See EXTERNAL_WATER_TEMP_ENTITY constant near top of file for the entity
    # ID and the renaming history. The five columns here form the
    # data-collection scaffold for ADR-015 stage 2 (gate C — 5-7 day soak
    # verification). Blueprint and auditor do not act on these yet; that's
    # Phase 3 work.
    {"name": "external_water_temp", "source": "state",
     "entity": EXTERNAL_WATER_TEMP_ENTITY},
    {"name": "external_water_temp_age_min", "source": "compute"},
    {"name": "external_water_temp_fresh", "source": "compute"},
    {"name": "water_temp_authoritative", "source": "compute"},
    {"name": "water_temp_delta", "source": "compute"},

    # ---------- Phase 2.1: external probe diagnostics (2026-05-22) ----------
    # WiFi RSSI for the floating external temp probe. Published by the
    # XIAO ESP32-C6 once per 30-min wake cycle. Used to investigate the
    # freshness-degradation pattern observed 5-19 → 5-21 (86% → 70%
    # successful publish rate). If declining publish success correlates
    # with declining RSSI, the cause is signal/distance/water-attenuation;
    # if RSSI is stable but publishes still fail, cause is more likely
    # battery sag under TX load or AP-side intermittent behavior.
    {"name": "external_wifi_rssi", "source": "state",
     "entity": EXTERNAL_WIFI_RSSI_ENTITY},

    # Heater estimated power: HEATER_RATED_POWER_W when compressor binary
    # sensor reports 'on', else 0. Per HP31005T nameplate (33.9A @ 230V).
    # Estimate only — see HEATER_RATED_POWER_W comment.
    {"name": "local_heater_estimated_power_w", "source": "compute"},

    # ---------- Local: pool light ----------
    {"name": "local_pool_light_state", "source": "state",
     "entity": "switch.omnilogic_pool_light"},

    # ---------- Pool modes (ADR-011, ADR-012) ----------
    # Helper booleans driving the v1.10.0 service_active and vacation_mode
    # gates in the blueprint. Captured here so the auditor can verify
    # that pump/heater/waterfall behavior actually changed when these
    # modes were active.
    {"name": "pool_service_lockout", "source": "state",
     "entity": "input_boolean.pool_service_lockout"},
    {"name": "vacation_mode", "source": "state",
     "entity": "input_boolean.vacation"},

    # ---------- HVAC: garage mini-split (Carrier 38MARBQ24AA3 via Midea AC LAN)
    # First non-pool domain captured. Real-time power (W) is unique here —
    # the Carrier Infinity integration only gives daily kWh aggregates;
    # Midea AC LAN exposes instantaneous draw. Useful for cross-checking
    # the household total and for the eventual presence-aware setback.
    {"name": "garage_ms_power_w", "source": "state",
     "entity": "sensor.garage_ms_power_realtime"},
    {"name": "garage_ms_kwh_total", "source": "state",
     "entity": "sensor.garage_ms_energy_total"},
    {"name": "garage_ms_kwh_current", "source": "state",
     "entity": "sensor.garage_ms_energy_current"},

    # ---------- Phase 1.5: context capture for state-change attribution ----
    # Per logger v2 phase 1.5 spec. For each of the three primary control
    # entities (pump, waterfall, heater), capture:
    #   - context.user_id   : non-null when a HA user initiated the change
    #   - context.parent_id : non-null when an automation/script initiated
    #   - last_changed      : timestamp of last state transition
    # Both null means the change came through the integration's coordinator
    # update (external / autonomous controller behavior). Same signal the
    # service-lockout detection automations use; capturing it here lets the
    # auditor flag the same class of events from CSV alone.

    {"name": "pump_state_context_user_id", "source": "context",
     "entity": "switch.omnilogic_pool_filter_pump", "ctx_field": "user_id"},
    {"name": "pump_state_context_parent_id", "source": "context",
     "entity": "switch.omnilogic_pool_filter_pump", "ctx_field": "parent_id"},
    {"name": "pump_state_last_changed", "source": "last_changed",
     "entity": "switch.omnilogic_pool_filter_pump"},

    {"name": "waterfall_state_context_user_id", "source": "context",
     "entity": "valve.omnilogic_pool_waterfall", "ctx_field": "user_id"},
    {"name": "waterfall_state_context_parent_id", "source": "context",
     "entity": "valve.omnilogic_pool_waterfall", "ctx_field": "parent_id"},
    {"name": "waterfall_state_last_changed", "source": "last_changed",
     "entity": "valve.omnilogic_pool_waterfall"},

    {"name": "heater_state_context_user_id", "source": "context",
     "entity": "water_heater.omnilogic_pool_heater", "ctx_field": "user_id"},
    {"name": "heater_state_context_parent_id", "source": "context",
     "entity": "water_heater.omnilogic_pool_heater", "ctx_field": "parent_id"},
    {"name": "heater_state_last_changed", "source": "last_changed",
     "entity": "water_heater.omnilogic_pool_heater"},
]


def get_token() -> str:
    """Read long-lived access token from disk. Fail loud if missing."""
    try:
        token = Path(TOKEN_FILE).read_text().strip()
    except FileNotFoundError:
        sys.exit(
            f"ERROR: missing token file at {TOKEN_FILE}. "
            "See pool/scripts/state_logger.py module docstring for setup."
        )
    if not token:
        sys.exit(f"ERROR: token file at {TOKEN_FILE} is empty.")
    return token


def fetch_entity(
    entity_id: str, token: str
) -> tuple[str, dict, str | None, dict]:
    """
    Fetch one entity's state, attributes, last_changed, and context from HA.

    Returns (state, attributes, last_changed_iso, context) or
    ('unavailable', {}, None, {}) on any failure.

    The context dict contains 'id', 'user_id', 'parent_id'. user_id and
    parent_id are None for coordinator-originated state updates. This is
    the same signal used by the service-lockout detection automations
    to distinguish HA-initiated changes from external/coordinator updates.
    Phase 1.5 captures it directly so the auditor can flag the same class
    of events without depending on Activity log scraping.
    """
    req = urllib.request.Request(
        f"{HA_BASE}/api/states/{entity_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return (
                data.get("state", "unavailable"),
                data.get("attributes", {}) or {},
                data.get("last_changed"),
                data.get("context", {}) or {},
            )
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return "unavailable", {}, None, {}


def parse_iso_utc(iso_str: str | None) -> datetime | None:
    """Parse HA's ISO timestamp (e.g. '2026-05-01T13:07:42.123456+00:00')."""
    if not iso_str:
        return None
    try:
        # Python's fromisoformat handles +00:00 cleanly from 3.11+
        return datetime.fromisoformat(iso_str)
    except ValueError:
        return None


def compute_heater_estimated_power_w(heater_equip_status: str) -> str:
    """
    Estimated heat pump input power (W) based on compressor binary sensor.

    Returns HEATER_RATED_POWER_W when compressor is active ('on'), else '0'.
    Returns 'unavailable' if the upstream binary sensor itself is unavailable
    (rather than guessing).
    """
    if heater_equip_status == "on":
        return str(HEATER_RATED_POWER_W)
    if heater_equip_status == "off":
        return "0"
    return "unavailable"


def compute_water_temp_reliable(
    pump_state: str, pump_last_changed: str | None
) -> str:
    """
    True iff the OmniLogic water temp sensor reading is trustworthy.

    The sensor sits in the pump return path and needs flow to settle.
    Reliable when: pump is currently 'on' AND has been on for at least
    WATER_TEMP_SETTLING_SECONDS.

    Returns 'true' / 'false' string for CSV. False during pump-off intervals
    and during the settling window after pump just started.
    """
    if pump_state != "on":
        return "false"
    last_changed = parse_iso_utc(pump_last_changed)
    if last_changed is None:
        return "false"
    on_for = (datetime.now(timezone.utc) - last_changed).total_seconds()
    return "true" if on_for >= WATER_TEMP_SETTLING_SECONDS else "false"


def compute_external_water_temp_age_min(heartbeat_ts_iso: str | None) -> str:
    """
    Minutes since the external probe last completed a wake (heartbeat).

    Takes the uptime heartbeat entity's last_changed (EXTERNAL_UPTIME_ENTITY),
    which advances every wake — NOT the temp sensor's own timestamp, which
    stalls when the median-filtered/rounded value repeats. last_reported was
    tried first (ADR-031) and empirically does NOT advance on an unchanged
    ESPHome re-report on this system, so the uptime heartbeat is used instead.

    Returns 'unavailable' if the timestamp is missing or unparseable. Otherwise
    a string-formatted float with 1 decimal place (e.g., '4.7').
    """
    heartbeat = parse_iso_utc(heartbeat_ts_iso)
    if heartbeat is None:
        return "unavailable"
    age_sec = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    return f"{age_sec / 60.0:.1f}"


def compute_external_water_temp_fresh(heartbeat_ts_iso: str | None) -> str:
    """
    True iff the external probe completed a wake within the freshness threshold
    (FRESHNESS_THRESHOLD_MIN). Per ADR-015 + 2026-05-18 production cadence:
    35 min (30 min deep-sleep + 5 min grace for boot/wifi/publish).

    Keyed off the uptime heartbeat's last_changed (advances every wake), NOT
    the temp sensor's timestamp (stalls on repeated values) and NOT last_reported
    (does not advance on unchanged ESPHome re-reports here) — see ADR-031.

    Returns 'true' / 'false' string for CSV. Returns 'false' if the timestamp
    is unparseable — treat unknown freshness as not-fresh, conservative
    default for the cascading fallback in compute_water_temp_authoritative.
    """
    heartbeat = parse_iso_utc(heartbeat_ts_iso)
    if heartbeat is None:
        return "false"
    age_sec = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    return "true" if age_sec / 60.0 <= FRESHNESS_THRESHOLD_MIN else "false"


def compute_water_temp_authoritative(
    external_temp: str, external_fresh: str,
    local_temp: str, local_reliable: str,
    target_temp: str,
) -> str:
    """
    Cascading fallback for the canonical water temp value, per ADR-015.

    Tier 1: external_water_temp if fresh and numeric — preferred because it
            works during pump-off intervals where the local sensor reads
            'unknown' (no flow through the in-line probe).
    Tier 2: local_water_temp if reliable per ADR-013 — settled, pump-on for
            WATER_TEMP_SETTLING_SECONDS or more.
    Tier 3: target_temp from the heater — ADR-013 tactical fallback when
            local sensor reads 'unknown' and no fresh external sensor.

    Returns the chosen value formatted to 1 decimal place, or 'unavailable'
    if all three tiers fail to provide a usable number.
    """
    # Tier 1: external if fresh
    if external_fresh == "true":
        try:
            return f"{float(external_temp):.1f}"
        except (ValueError, TypeError):
            pass
    # Tier 2: local if reliable
    if local_reliable == "true":
        try:
            return f"{float(local_temp):.1f}"
        except (ValueError, TypeError):
            pass
    # Tier 3: heater target temp
    try:
        return f"{float(target_temp):.1f}"
    except (ValueError, TypeError):
        return "unavailable"


def compute_water_temp_delta(
    external_temp: str, local_temp: str, pump_on: bool,
) -> str:
    """
    Difference between external and local water temp readings, in °F
    (external minus local). Only meaningful when pump is on — local sensor
    needs flow to read at all. Returns empty string when pump is off or
    either reading is non-numeric.

    Useful signal for future auditor assertion W2: sustained large delta
    during pump-on suggests one sensor is miscalibrated or the external
    probe is positioned somewhere with materially different water than
    the in-line return-path probe. Format: '+/-X.XX' with two decimals.
    """
    if not pump_on:
        return ""
    try:
        e = float(external_temp)
        l = float(local_temp)
        return f"{e - l:+.2f}"
    except (ValueError, TypeError):
        return ""


def build_row(args: argparse.Namespace, token: str) -> list[str]:
    """Walk the COLUMNS manifest and produce one CSV row."""
    # Cache of fetched entities so multiple columns reading the same entity
    # only hit the REST API once. Pre-populate the pump entity because
    # compute_water_temp_reliable needs its last_changed below — and any
    # later attribute reads of the same entity must see the real attrs,
    # not an empty dict.
    cache: dict[str, tuple[str, dict, str | None, dict]] = {
        "switch.omnilogic_pool_filter_pump": fetch_entity(
            "switch.omnilogic_pool_filter_pump", token
        ),
    }
    pump_state, _, pump_last_changed, _ = cache[
        "switch.omnilogic_pool_filter_pump"
    ]

    def get(entity_id: str) -> tuple[str, dict, str | None, dict]:
        if entity_id not in cache:
            cache[entity_id] = fetch_entity(entity_id, token)
        return cache[entity_id]

    # External-probe freshness keys off the uptime heartbeat's last_changed,
    # which advances every wake — temp/wifi/battery timestamps stall on repeated
    # values, and last_reported does not advance on unchanged re-reports here
    # (ADR-031). Fetched once and shared by the age / fresh / authoritative
    # columns below.
    _, _, ext_heartbeat_ts, _ = get(EXTERNAL_UPTIME_ENTITY)

    row: list[str] = []
    for col in COLUMNS:
        name = col["name"]
        src = col["source"]

        if src == "compute":
            if name == "timestamp":
                row.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            elif name == "row_type":
                row.append(args.row_type)
            elif name == "trigger_entity":
                row.append(args.trigger_entity or "")
            elif name == "local_water_temp_reliable":
                row.append(
                    compute_water_temp_reliable(pump_state, pump_last_changed)
                )
            elif name == "external_water_temp_age_min":
                row.append(
                    compute_external_water_temp_age_min(ext_heartbeat_ts)
                )
            elif name == "external_water_temp_fresh":
                row.append(
                    compute_external_water_temp_fresh(ext_heartbeat_ts)
                )
            elif name == "water_temp_authoritative":
                ext_state, _, _, _ = get(EXTERNAL_WATER_TEMP_ENTITY)
                local_state, _, _, _ = get("sensor.omnilogic_pool_watersensor")
                _, heater_attrs, _, _ = get(
                    "water_heater.omnilogic_pool_heater"
                )
                target_temp = str(heater_attrs.get("temperature", ""))
                fresh = compute_external_water_temp_fresh(ext_heartbeat_ts)
                local_reliable = compute_water_temp_reliable(
                    pump_state, pump_last_changed
                )
                row.append(compute_water_temp_authoritative(
                    ext_state, fresh, local_state, local_reliable, target_temp
                ))
            elif name == "water_temp_delta":
                ext_state, _, _, _ = get(EXTERNAL_WATER_TEMP_ENTITY)
                local_state, _, _, _ = get("sensor.omnilogic_pool_watersensor")
                row.append(compute_water_temp_delta(
                    ext_state, local_state, pump_state == "on"
                ))
            elif name == "local_heater_estimated_power_w":
                heater_equip_state, _, _, _ = get(
                    "binary_sensor.omnilogic_pool_heater_heater_equipment_status"
                )
                row.append(compute_heater_estimated_power_w(heater_equip_state))
            else:
                # Unknown computed column — record as empty
                row.append("")

        elif src == "state":
            state, _, _, _ = get(col["entity"])
            row.append(state)

        elif src == "attr":
            _, attrs, _, _ = get(col["entity"])
            value = attrs.get(col["attr"], "unavailable")
            # Render dicts/lists as JSON for CSV-safety
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            row.append(str(value) if value is not None else "")

        elif src == "last_changed":
            # Phase 1.5: capture the entity's last_changed timestamp.
            # Useful for correlating row events with state-transition events.
            _, _, last_changed, _ = get(col["entity"])
            row.append(last_changed or "")

        elif src == "context":
            # Phase 1.5: capture the HA context for the entity's current state.
            # ctx_field is one of 'user_id', 'parent_id', 'id'.
            # user_id=None and parent_id=None means coordinator-originated
            # update (i.e., external/integration-side change, not HA action).
            # Auditor uses these to distinguish blueprint-initiated from
            # autonomous-controller events without scraping the Activity log.
            _, _, _, context = get(col["entity"])
            value = context.get(col["ctx_field"])
            row.append(str(value) if value is not None else "")

        else:
            row.append("")

    return row


def maybe_rotate_csv(log_path: Path) -> None:
    """
    Rotate the CSV if its first-line schema_version comment doesn't match
    the current SCHEMA_VERSION. Renames the existing file to include the
    old schema version in the filename so historical data is preserved
    side-by-side. The next write_row call will then create a fresh file
    with the current schema header.

    Why this exists: when phase 1.5 added context columns, the new schema
    has 44 columns vs phase 1's 35. Appending new rows to the old file
    would produce ragged CSV that breaks pandas / csv parsers. Rotating
    is the simplest safe migration — historical rows stay readable in
    their original format, new rows go in a fresh file.

    No-op if the file doesn't exist or the version already matches.
    """
    if not log_path.exists():
        return
    with log_path.open() as f:
        first_line = f.readline().strip()
    expected = f"# schema_version={SCHEMA_VERSION}"
    if first_line == expected:
        return
    if first_line.startswith("# schema_version="):
        old_version = first_line.split("=", 1)[1]
    else:
        old_version = "unknown"
    rotated = log_path.with_name(
        f"{log_path.stem}.{old_version}{log_path.suffix}"
    )
    log_path.rename(rotated)


def write_row(row: list[str]) -> None:
    """Append row to CSV. Create file with header if missing."""
    log_path = Path(LOG_FILE)
    maybe_rotate_csv(log_path)
    file_exists = log_path.exists()

    with log_path.open("a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            # Schema version comment row + header
            f.write(f"# schema_version={SCHEMA_VERSION}\n")
            writer.writerow([col["name"] for col in COLUMNS])
        writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pool state logger v2 — phase 1")
    parser.add_argument(
        "--row-type",
        default="time_pattern",
        choices=["time_pattern", "state_change"],
        help="Type of row being written (default: time_pattern)",
    )
    parser.add_argument(
        "--trigger-entity",
        default="",
        help="For state_change rows: which entity triggered this row",
    )
    args = parser.parse_args()

    token = get_token()
    row = build_row(args, token)
    write_row(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
