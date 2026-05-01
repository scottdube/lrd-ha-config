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
Phase 1 (this version): local OmniLogic + environmental + computed
                        water_temp_reliable. ~30 columns.
Phase 1.5: add state-change triggers, more local attributes (filter
           power, why_on enums).
Phase 2: cloud OmniLogic columns, expected_state computed columns, trusted
         water temp via input_number helper.
Phase 3: rsync backup to Mac mini.
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
SCHEMA_VERSION = "2.0-phase1"

# Water-temp reliability threshold: pump must have been on for at least this
# many seconds before the OmniLogic water temp sensor is considered settled.
# Tunable; see pool/docs/logger-v2.md and ADR-008.
WATER_TEMP_SETTLING_SECONDS = 600  # 10 min

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

    # ---------- Local: waterfall ----------
    {"name": "local_waterfall_state", "source": "state",
     "entity": "valve.omnilogic_pool_waterfall_2"},
    {"name": "local_waterfall_function", "source": "attr",
     "entity": "valve.omnilogic_pool_waterfall_2", "attr": "omni_function"},
    {"name": "local_waterfall_why_on", "source": "attr",
     "entity": "valve.omnilogic_pool_waterfall_2", "attr": "omni_why_on"},

    # ---------- Local: chlorinator ----------
    {"name": "local_chlorinator_state", "source": "state",
     "entity": "switch.omnilogic_pool_chlorinator"},
    {"name": "local_chlorinator_percent", "source": "state",
     "entity": "number.omnilogic_pool_chlorinator_timed_percent"},

    # ---------- Local: water + air ----------
    {"name": "local_water_temp", "source": "state",
     "entity": "sensor.omnilogic_pool_watersensor"},
    {"name": "local_water_temp_reliable", "source": "compute"},
    # Trusted water temp (forward-fill of last reliable read) — Phase 2.
    # local_water_temp_trusted column placeholder added in v2 of this script.

    # ---------- Local: pool light ----------
    {"name": "local_pool_light_state", "source": "state",
     "entity": "switch.omnilogic_pool_light"},
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


def fetch_entity(entity_id: str, token: str) -> tuple[str, dict, str | None]:
    """
    Fetch one entity's state and attributes from HA REST API.

    Returns (state, attributes, last_changed_iso) or
    ('unavailable', {}, None) on any failure.
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
            )
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return "unavailable", {}, None


def parse_iso_utc(iso_str: str | None) -> datetime | None:
    """Parse HA's ISO timestamp (e.g. '2026-05-01T13:07:42.123456+00:00')."""
    if not iso_str:
        return None
    try:
        # Python's fromisoformat handles +00:00 cleanly from 3.11+
        return datetime.fromisoformat(iso_str)
    except ValueError:
        return None


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


def build_row(args: argparse.Namespace, token: str) -> list[str]:
    """Walk the COLUMNS manifest and produce one CSV row."""
    # Pre-fetch entities we'll need in compute columns
    pump_state, _, pump_last_changed = fetch_entity(
        "switch.omnilogic_pool_filter_pump", token
    )

    # Cache of fetched entities so multiple columns reading the same entity
    # only hit the REST API once.
    cache: dict[str, tuple[str, dict, str | None]] = {
        "switch.omnilogic_pool_filter_pump": (pump_state, {}, pump_last_changed),
    }

    def get(entity_id: str) -> tuple[str, dict, str | None]:
        if entity_id not in cache:
            cache[entity_id] = fetch_entity(entity_id, token)
        return cache[entity_id]

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
            else:
                # Unknown computed column — record as empty
                row.append("")

        elif src == "state":
            state, _, _ = get(col["entity"])
            row.append(state)

        elif src == "attr":
            _, attrs, _ = get(col["entity"])
            value = attrs.get(col["attr"], "unavailable")
            # Render dicts/lists as JSON for CSV-safety
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            row.append(str(value) if value is not None else "")

        else:
            row.append("")

    return row


def write_row(row: list[str]) -> None:
    """Append row to CSV. Create file with header if missing."""
    log_path = Path(LOG_FILE)
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
