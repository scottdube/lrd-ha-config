#!/usr/bin/env python3
"""
Garage motion-pattern report.

Pulls 14 days of motion + occupancy + climate state from HA's history and
prints day-of-week / hour-of-day heat maps so Scott can refine the
Active-mode schedule (currently 09:00-13:00 daily) with real data.

Designed to be re-run weekly (or on demand) — no CSV state, just a
snapshot from HA's recorder.

Usage
-----
    python3 tools/garage_motion_report.py \
        --token ~/Documents/Claude/Projects/home-assistant/.ha-token \
        --days 14

Default token path is the same as energy_pull_stats.py / energy_audit.py.

Caveats
-------
- HA's recorder default purge is 10 days. If --days exceeds that, the
  recorder won't have data for the older period. Check
  configuration.yaml → recorder: → days_to_keep if you want longer
  windows.
- Motion sensors return on/off state changes. A "30-min occupied" window
  with continuous motion may show as 1-2 state transitions, not 30.
  Treat the per-hour count as "any motion in this hour", not duration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict

import websockets

HA_WS = "ws://192.168.50.11:8123/api/websocket"
LRD_LOCAL_OFFSET_HOURS = -4

# Motion / occupancy / climate entities to sample
ENTITIES = [
    "binary_sensor.garage_occupied",           # broader occupancy (BLE + motion combined)
    "binary_sensor.garage_person_detected",    # tighter person-detected
    "binary_sensor.garage_door",               # walk-in
    "binary_sensor.z_wave_plus_gold_plated_reliability_garage_door_tilt_sensor",   # Big overhead
    "binary_sensor.z_wave_plus_gold_plated_reliability_garage_door_tilt_sensor_2", # Golf-cart overhead
    "climate.garage_ms",                       # hvac state changes
]

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


async def fetch_history(
    token: str, entities: list[str], start_utc: datetime, end_utc: datetime,
) -> dict[str, list[dict]]:
    """Pull /history/period equivalent via WebSocket history/history_during_period."""
    async with websockets.connect(HA_WS, max_size=50_000_000) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        ack = json.loads(await ws.recv())
        if ack.get("type") != "auth_ok":
            raise RuntimeError(f"auth failed: {ack}")
        await ws.send(json.dumps({
            "id": 1,
            "type": "history/history_during_period",
            "start_time": start_utc.isoformat(),
            "end_time": end_utc.isoformat(),
            "entity_ids": entities,
            "minimal_response": True,
            "no_attributes": True,
        }))
        resp = json.loads(await ws.recv())
        if not resp.get("success"):
            raise RuntimeError(f"history query failed: {resp}")
        return resp["result"]


def to_local(t_utc: datetime) -> datetime:
    return t_utc.astimezone(timezone(timedelta(hours=LRD_LOCAL_OFFSET_HOURS)))


def parse_history_dt(entry: dict) -> datetime | None:
    """Each history entry has 'lu' (last_updated ms) or 's' state. Returns UTC dt."""
    if "lu" in entry:
        return datetime.fromtimestamp(entry["lu"], tz=timezone.utc)
    if "last_updated" in entry:
        s = entry["last_updated"].rstrip("Z")
        try:
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc) \
                   if "+" not in s else datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


def count_on_transitions_by_hour(history: list[dict]) -> dict[tuple[int, int], int]:
    """Return {(dow, hour): count_of_off→on_transitions}."""
    grid: dict[tuple[int, int], int] = defaultdict(int)
    prev = None
    for entry in history:
        state = entry.get("s") or entry.get("state")
        t = parse_history_dt(entry)
        if state is None or t is None:
            continue
        if prev == "off" and state == "on":
            local = to_local(t)
            grid[(local.weekday(), local.hour)] += 1
        prev = state
    return grid


def count_total_on_minutes_by_hour(history: list[dict]) -> dict[tuple[int, int], float]:
    """Return {(dow, hour): minutes the entity was 'on' in that hour-of-week bucket}.

    Walks the history series, integrating ON intervals across the bucket
    boundaries. Approximation — close enough for pattern-spotting.
    """
    grid: dict[tuple[int, int], float] = defaultdict(float)
    if not history:
        return grid
    # Build (timestamp, state) tuples in chronological order
    points: list[tuple[datetime, str]] = []
    for entry in history:
        state = entry.get("s") or entry.get("state")
        t = parse_history_dt(entry)
        if t is not None and state is not None:
            points.append((t, state))
    points.sort(key=lambda p: p[0])
    for i, (t, state) in enumerate(points):
        if state != "on":
            continue
        # Find when this 'on' interval ends — next non-'on' state or window end
        end = points[i + 1][0] if i + 1 < len(points) else points[-1][0]
        if end <= t:
            continue
        # Walk the interval hour-by-hour
        cursor = t
        while cursor < end:
            local = to_local(cursor)
            hour_end_local = local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            hour_end_utc = hour_end_local.astimezone(timezone.utc)
            chunk_end = min(end, hour_end_utc)
            minutes = (chunk_end - cursor).total_seconds() / 60.0
            grid[(local.weekday(), local.hour)] += minutes
            cursor = chunk_end
    return grid


def render_heatmap(
    title: str, grid: dict[tuple[int, int], float], unit: str = "min",
) -> None:
    """Print a 7-row × 24-col day-of-week × hour-of-day heat map."""
    print(title)
    print("       " + "".join(f"{h:>4d}" for h in range(24)))
    mx = max(grid.values()) if grid else 1.0
    for dow in range(7):
        row = [f"{DAY_NAMES[dow]:>5s} |"]
        for hour in range(24):
            v = grid.get((dow, hour), 0)
            if v == 0:
                row.append("   .")
            elif v < mx * 0.05:
                row.append("   ·")
            elif v < mx * 0.25:
                row.append("   ▁")
            elif v < mx * 0.5:
                row.append("   ▃")
            elif v < mx * 0.75:
                row.append("   ▅")
            else:
                row.append("   █")
        print("".join(row))
    print(f"       (max in any cell: {mx:.0f} {unit})\n")


def summary_table(grid: dict[tuple[int, int], float], top_n: int = 10) -> list[tuple]:
    """Top N (dow, hour) cells by value."""
    items = sorted(grid.items(), key=lambda x: -x[1])[:top_n]
    return [(DAY_NAMES[dow], hour, val) for (dow, hour), val in items]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--token", type=Path, required=True)
    p.add_argument("--days", type=int, default=14)
    args = p.parse_args()

    token = args.token.expanduser().read_text().strip()

    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(days=args.days)

    print(f"Garage motion report — {args.days} days "
          f"({to_local(start_utc).strftime('%Y-%m-%d')} → "
          f"{to_local(end_utc).strftime('%Y-%m-%d')} LRD-EDT)\n")

    history = asyncio.run(fetch_history(token, ENTITIES, start_utc, end_utc))

    # Person detected — tightest signal of "Scott in the garage"
    person = history.get("binary_sensor.garage_person_detected", [])
    if person:
        grid = count_total_on_minutes_by_hour(person)
        render_heatmap(
            "PERSON-DETECTED — minutes/hour, by day-of-week × hour-of-day:",
            grid, unit="min",
        )
        top = summary_table(grid)
        if top:
            print("Top 10 most-occupied (dow, hour, minutes):")
            for dow_name, h, m in top:
                print(f"  {dow_name} {h:02d}:00  {m:5.0f} min")
            print()

    # Garage occupied — broader (includes BLE presence)
    occ = history.get("binary_sensor.garage_occupied", [])
    if occ:
        grid = count_total_on_minutes_by_hour(occ)
        render_heatmap(
            "OCCUPANCY (combined) — minutes/hour, by day-of-week × hour-of-day:",
            grid, unit="min",
        )

    # Overhead doors — open events
    for label, ent in [
        ("Big overhead door", "binary_sensor.z_wave_plus_gold_plated_reliability_garage_door_tilt_sensor"),
        ("Golf cart overhead", "binary_sensor.z_wave_plus_gold_plated_reliability_garage_door_tilt_sensor_2"),
    ]:
        h = history.get(ent, [])
        if h:
            grid = count_on_transitions_by_hour(h)
            total = sum(grid.values())
            if total > 0:
                print(f"{label} — open events ({total} total in window)")
                render_heatmap(f"  events/hour:", grid, unit="opens")

    # Climate state summary
    cl = history.get("climate.garage_ms", [])
    if cl:
        state_counts: dict[str, int] = defaultdict(int)
        for entry in cl:
            state_counts[entry.get("s") or entry.get("state") or "unknown"] += 1
        print("Climate state transitions in window:")
        for s, n in sorted(state_counts.items(), key=lambda x: -x[1]):
            print(f"  {s:10s}  {n} transitions")

    return 0


if __name__ == "__main__":
    sys.exit(main())
