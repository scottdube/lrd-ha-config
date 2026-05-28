#!/usr/bin/env python3
"""
Pull long-term statistics for energy entities from HA.

Ad-hoc analysis helper — companion to energy_analyze.py. Use this to
materialize a JSON file you can re-analyze offline (cheap to iterate on
analysis logic without re-querying HA).

Defaults to 14 days, local-midnight-aligned at LRD (EDT = UTC-4), and the
canonical Vue 3 circuit set + ADR-020 subtotal templates.

Usage
-----
    python3 tools/energy_pull_stats.py \
        --token ~/Documents/Claude/Projects/home-assistant/.ha-token \
        --days 14 \
        --out energy_stats.json

The output JSON is the raw `recorder/statistics_during_period` response
keyed by entity_id; downstream scripts (energy_analyze.py, energy_audit.py)
consume it directly.

Notes
-----
- ESPHome `total_daily_energy` sensors reset at local midnight (resets are
  handled correctly by HA's total_increasing state class; the per-period
  `change` field is the kWh delta for that period).
- Underlying Vue circuit sensors are in Wh. The ADR-020 subtotal templates
  (whole_home_daily_energy, hvac_daily_energy, etc.) are in kWh.
- HA parses bare ISO timestamps as server-local time. Always pass an
  explicit offset (`+00:00` or `Z`) — see docs/reference/ha-rest-api-curl-cheatsheet.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import websockets


HA_WS = "ws://192.168.50.11:8123/api/websocket"

# Canonical energy entity set. Underlying Vue circuits + ADR-020 templates +
# Carrier per-system templates. Keep aligned with packages/energy/templates.yaml.
ENTITIES_DEFAULT = [
    # Subtotal templates (kWh, post-2026-05-18)
    "sensor.whole_home_daily_energy",
    "sensor.hvac_daily_energy",
    "sensor.always_on_daily_energy",
    "sensor.pool_subpanel_daily_energy_kwh",
    # Panel totals + unmonitored (Wh)
    "sensor.emporia_vue_panel_a_total_daily_energy",
    "sensor.emporia_vue_panel_b_total_daily_energy",
    "sensor.emporia_vue_panel_a_unmonitored_daily_energy",
    "sensor.emporia_vue_panel_b_unmonitored_daily_energy",
    # Carrier per-system templates (Wh)
    "sensor.air_1_total_daily_energy",
    "sensor.air_2_total_daily_energy",
    # Major individual circuits (Wh) — top consumers + always-on
    "sensor.emporia_vue_panel_a_circuit_1_pool_subpanel_daily_energy",
    "sensor.emporia_vue_panel_a_circuit_2_refrigerator_daily_energy",
    "sensor.emporia_vue_panel_a_circuit_3_water_heater_daily_energy",
    "sensor.emporia_vue_panel_a_circuit_5_air_2_handler_daily_energy",
    "sensor.emporia_vue_panel_a_circuit_9_air_1_condenser_daily_energy",
    "sensor.emporia_vue_panel_a_circuit_10_garage_mini_split_daily_energy",
    "sensor.emporia_vue_panel_a_circuit_14_network_rack_daily_energy",
    "sensor.emporia_vue_panel_b_circuit_1_dryer_daily_energy",
    "sensor.emporia_vue_panel_b_circuit_4_family_rm_lanai_daily_energy",
    "sensor.emporia_vue_panel_b_circuit_5_master_bed_lanai_daily_energy",
    "sensor.emporia_vue_panel_b_circuit_6_general_loads_daily_energy",
    "sensor.emporia_vue_panel_b_circuit_9_air_1_handler_daily_energy",
    "sensor.emporia_vue_panel_b_circuit_10_air_2_condenser_daily_energy",
    "sensor.emporia_vue_panel_b_circuit_12_dishwasher_daily_energy",
    "sensor.emporia_vue_panel_b_circuit_15_garage_gfi_panel_wall_daily_energy",
]

# LRD is EDT = UTC-4 year-round (Florida doesn't change for this analysis;
# revisit if the pool ever moves to AZ).
LRD_LOCAL_OFFSET_HOURS = -4


async def fetch_stats(
    token: str,
    entities: list[str],
    start_utc: datetime,
    end_utc: datetime,
    period: str = "hour",
    types: list[str] | None = None,
) -> dict:
    """Call recorder/statistics_during_period via WebSocket."""
    if types is None:
        types = ["sum", "state", "change", "mean"]
    async with websockets.connect(HA_WS, max_size=50_000_000) as ws:
        await ws.recv()  # auth_required
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        ack = json.loads(await ws.recv())
        if ack.get("type") != "auth_ok":
            raise RuntimeError(f"auth failed: {ack}")
        msg = {
            "id": 1,
            "type": "recorder/statistics_during_period",
            "start_time": start_utc.isoformat(),
            "end_time": end_utc.isoformat(),
            "statistic_ids": entities,
            "period": period,
            "types": types,
        }
        await ws.send(json.dumps(msg))
        resp = json.loads(await ws.recv())
        if not resp.get("success"):
            raise RuntimeError(f"stats query failed: {resp}")
        return resp["result"]


def local_midnight_window(days: int) -> tuple[datetime, datetime]:
    """Return (start_utc, end_utc) for the last N complete local-midnight days."""
    now_utc = datetime.now(timezone.utc)
    local_now = now_utc + timedelta(hours=LRD_LOCAL_OFFSET_HOURS)
    local_today_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = local_today_midnight
    start_local = end_local - timedelta(days=days)
    # Convert back to UTC
    start_utc = (start_local - timedelta(hours=LRD_LOCAL_OFFSET_HOURS)).replace(tzinfo=timezone.utc)
    end_utc = (end_local - timedelta(hours=LRD_LOCAL_OFFSET_HOURS)).replace(tzinfo=timezone.utc)
    return start_utc, end_utc


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--token", type=Path, required=True, help="HA long-lived token file")
    p.add_argument("--days", type=int, default=14, help="Days back (default 14)")
    p.add_argument("--period", choices=["hour", "day"], default="hour")
    p.add_argument("--out", type=Path, default=Path("energy_stats.json"))
    p.add_argument(
        "--entities", type=Path, default=None,
        help="Optional file with one entity_id per line, overrides defaults",
    )
    args = p.parse_args()

    token = args.token.expanduser().read_text().strip()
    if args.entities:
        entities = [
            line.strip() for line in args.entities.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
    else:
        entities = ENTITIES_DEFAULT

    start_utc, end_utc = local_midnight_window(args.days)
    print(f"Pulling {len(entities)} entities, {args.days}d, "
          f"{start_utc.isoformat()} → {end_utc.isoformat()}", file=sys.stderr)

    result = asyncio.run(fetch_stats(token, entities, start_utc, end_utc, period=args.period))

    args.out.write_text(json.dumps(result, indent=2, default=str))
    print(f"Wrote {args.out} ({sum(len(v) for v in result.values())} rows, "
          f"{len(result)} entities)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
