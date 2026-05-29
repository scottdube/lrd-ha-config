#!/usr/bin/env python3
"""
Multi-zone occupancy logger.

Pulls yesterday's per-signal history from HA for each enabled zone in the
config files, classifies each hour as SUSTAINED / TRANSIENT / EMPTY using
the multi-signal classifier (ADR-028), appends one row per (zone, day) to
a per-zone CSV.

Designed for unattended daily cadence on the always-on Mac mini at LRD,
mirroring the pool auditor / energy auditor pattern. Will replicate to
the NH always-on host once NH HA is online — same script, different
config file.

Signal hierarchy (highest confidence first):
  Tier 1 — deterministic SUSTAINED short-circuit:
    - input_boolean.golfing on  (golf sim session, by user action)
  Tier 2 — strong SUSTAINED signals (any one):
    - bench mmWave presence >5 min in hour
    - bench-circuit power above (standby + delta) for >5 min
    - lights on >10 min AND any person-detect event
  Tier 3 — TRANSIENT:
    - person-detect event with no Tier 1/2 backing
    - overhead door open/close events
  Otherwise: EMPTY.

Trash-out trip pattern (Mon/Thu nights): walk-in door opens, motion event
for 60-90 sec, no lights >10min, no bench power, no golf-sim → classified
TRANSIENT. Does NOT contribute to "garage was used" hours.

Usage
-----
    python3 occupancy_log.py [--config tools/occupancy/lrd.yaml]
                             [--for-date YYYY-MM-DD]
                             [--csv-dir ~/occupancy-log]
                             [--token-file ~/.ha_token]
                             [--no-notify] [--print-clean]

Exit code: 0 always (silent-on-clean expected; mode mirrors pool auditor).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Any

import websockets
import yaml


HA_WS = "ws://192.168.50.11:8123/api/websocket"
HA_BASE = "http://192.168.50.11:8123"
NOTIFY_TARGET = "scott_and_ha"
TOKEN_FILE_DEFAULT = Path.home() / ".ha_token"
CSV_DIR_DEFAULT = Path.home() / "occupancy-log"
LOGGER_VERSION = "occupancy-log-1.0.0"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

@dataclass
class ZoneConfig:
    name: str
    property: str
    enabled: bool
    timezone_offset_hours: int
    description: str
    classifier: dict
    signals: dict

    @classmethod
    def from_dict(cls, d: dict) -> "ZoneConfig":
        return cls(
            name=d["name"],
            property=d["property"],
            enabled=d.get("enabled", False),
            timezone_offset_hours=d.get("timezone_offset_hours", -4),
            description=d.get("description", "").strip(),
            classifier=d.get("classifier", {}),
            signals=d.get("signals", {}),
        )


def load_zones(config_path: Path) -> list[ZoneConfig]:
    with config_path.open() as f:
        data = yaml.safe_load(f) or {}
    return [ZoneConfig.from_dict(z) for z in data.get("zones", [])]


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def local_midnight_utc(local_d: date, tz_offset_hours: int) -> datetime:
    """UTC datetime corresponding to 00:00 local on local_d."""
    return datetime(local_d.year, local_d.month, local_d.day,
                    -tz_offset_hours, 0, 0, tzinfo=timezone.utc)


def to_local(t_utc: datetime, tz_offset_hours: int) -> datetime:
    return t_utc.astimezone(timezone(timedelta(hours=tz_offset_hours)))


# ---------------------------------------------------------------------------
# HA history fetch
# ---------------------------------------------------------------------------

async def fetch_history_ws(
    token: str, entity_ids: list[str],
    start_utc: datetime, end_utc: datetime,
) -> dict[str, list[dict]]:
    """Use history/history_during_period — returns minimal state-change list."""
    if not entity_ids:
        return {}
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
            "entity_ids": entity_ids,
            "minimal_response": True,
            "no_attributes": True,
        }))
        resp = json.loads(await ws.recv())
        if not resp.get("success"):
            raise RuntimeError(f"history query failed: {resp}")
        return resp["result"]


def parse_entry_ts(entry: dict) -> Optional[datetime]:
    """history_during_period returns 'lu' (last_updated, seconds epoch float)."""
    if "lu" in entry:
        return datetime.fromtimestamp(entry["lu"], tz=timezone.utc)
    if "last_updated" in entry:
        s = entry["last_updated"]
        try:
            if s.endswith("Z"):
                return datetime.fromisoformat(s[:-1]).replace(tzinfo=timezone.utc)
            return datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


def entry_state(entry: dict) -> Optional[str]:
    return entry.get("s") or entry.get("state")


# ---------------------------------------------------------------------------
# Signal processing — per-hour aggregates
# ---------------------------------------------------------------------------

def on_minutes_per_hour(
    history: list[dict], day: date, tz_off: int,
    on_states: tuple[str, ...] = ("on",),
) -> list[float]:
    """Compute minutes the entity was in an 'on' state per local hour of the day.

    Walks state changes; integrates ON intervals across hour boundaries.
    Returns a 24-element list, one per hour (00-23 local).
    """
    by_hour = [0.0] * 24
    if not history:
        return by_hour
    # Sort by timestamp
    points: list[tuple[datetime, str]] = []
    for e in history:
        t = parse_entry_ts(e)
        s = entry_state(e)
        if t is not None and s is not None:
            points.append((t, s))
    points.sort(key=lambda p: p[0])

    day_start = local_midnight_utc(day, tz_off)
    day_end = day_start + timedelta(days=1)

    # If first point starts after day_start, prepend a synthetic "unknown" point
    # so we don't miss the leading interval. If state was "on" already at midnight,
    # the first point in the window will reflect that.
    # Walk interval-by-interval
    for i, (t, s) in enumerate(points):
        if s not in on_states:
            continue
        next_t = points[i + 1][0] if i + 1 < len(points) else day_end
        interval_start = max(t, day_start)
        interval_end = min(next_t, day_end)
        if interval_end <= interval_start:
            continue
        # Bucket into hourly local-time slots
        cursor = interval_start
        while cursor < interval_end:
            local = to_local(cursor, tz_off)
            hour = local.hour
            hour_end_local = local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            hour_end_utc = hour_end_local.astimezone(timezone.utc)
            chunk_end = min(interval_end, hour_end_utc)
            minutes = (chunk_end - cursor).total_seconds() / 60.0
            by_hour[hour] += minutes
            cursor = chunk_end
    return by_hour


def transitions_per_hour(
    history: list[dict], day: date, tz_off: int,
    to_state: str = "on", from_state: Optional[str] = "off",
) -> list[int]:
    """Count from→to state transitions per local hour."""
    counts = [0] * 24
    if not history:
        return counts
    points: list[tuple[datetime, str]] = []
    for e in history:
        t = parse_entry_ts(e)
        s = entry_state(e)
        if t is not None and s is not None:
            points.append((t, s))
    points.sort(key=lambda p: p[0])
    day_start = local_midnight_utc(day, tz_off)
    day_end = day_start + timedelta(days=1)
    prev_state = None
    for t, s in points:
        if t < day_start or t >= day_end:
            prev_state = s
            continue
        if s == to_state and (from_state is None or prev_state == from_state):
            local = to_local(t, tz_off)
            counts[local.hour] += 1
        prev_state = s
    return counts


def mean_above_threshold_minutes_per_hour(
    history: list[dict], day: date, tz_off: int, threshold: float,
) -> list[float]:
    """For a numeric sensor, minutes per hour the value exceeded threshold."""
    by_hour = [0.0] * 24
    if not history:
        return by_hour
    points: list[tuple[datetime, float]] = []
    for e in history:
        t = parse_entry_ts(e)
        s = entry_state(e)
        if t is None or s is None:
            continue
        try:
            v = float(s)
        except (TypeError, ValueError):
            continue
        points.append((t, v))
    points.sort(key=lambda p: p[0])
    day_start = local_midnight_utc(day, tz_off)
    day_end = day_start + timedelta(days=1)
    for i, (t, v) in enumerate(points):
        if v <= threshold:
            continue
        next_t = points[i + 1][0] if i + 1 < len(points) else day_end
        interval_start = max(t, day_start)
        interval_end = min(next_t, day_end)
        if interval_end <= interval_start:
            continue
        cursor = interval_start
        while cursor < interval_end:
            local = to_local(cursor, tz_off)
            hour_end_local = local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            hour_end_utc = hour_end_local.astimezone(timezone.utc)
            chunk_end = min(interval_end, hour_end_utc)
            minutes = (chunk_end - cursor).total_seconds() / 60.0
            by_hour[local.hour] += minutes
            cursor = chunk_end
    return by_hour


# ---------------------------------------------------------------------------
# Classifier — per-hour
# ---------------------------------------------------------------------------

@dataclass
class HourMetrics:
    hour: int
    golf_sim_min: float = 0.0
    bench_presence_min: float = 0.0
    bench_power_min: float = 0.0   # minutes above (standby + delta)
    lights_min: float = 0.0
    person_detect_events: int = 0
    door_events: int = 0
    walk_in_events: int = 0
    classification: str = "EMPTY"  # SUSTAINED-GOLF | SUSTAINED-BENCH | SUSTAINED-WORK | SUSTAINED-WORKSHOP | TRANSIENT | EMPTY


def classify_hour(m: HourMetrics, cls: dict) -> str:
    sustained_min = cls.get("sustained_min_minutes", 10)
    lights_sustained_min = cls.get("lights_sustained_min_minutes", 10)
    bench_power_min = cls.get("bench_power_sustained_min_minutes", 5)
    if m.golf_sim_min >= 1.0:
        return "SUSTAINED-GOLF"
    if m.bench_presence_min >= 5:
        return "SUSTAINED-BENCH"
    if m.bench_power_min >= bench_power_min:
        return "SUSTAINED-WORK"
    if m.lights_min >= lights_sustained_min and m.person_detect_events >= 1:
        return "SUSTAINED-WORKSHOP"
    if m.person_detect_events >= 1 or m.door_events >= 1 or m.walk_in_events >= 1:
        return "TRANSIENT"
    return "EMPTY"


# ---------------------------------------------------------------------------
# Per-zone run
# ---------------------------------------------------------------------------

@dataclass
class ZoneDayResult:
    zone: str
    audit_date: date
    sustained_hours: int = 0
    transient_hours: int = 0
    empty_hours: int = 0
    golf_sim_total_min: float = 0.0
    bench_power_total_min: float = 0.0
    lights_total_min: float = 0.0
    door_event_total: int = 0
    walk_in_event_total: int = 0
    person_detect_total: int = 0
    peak_sustained_hour: Optional[int] = None
    classifications_by_hour: list[str] = field(default_factory=lambda: ["EMPTY"] * 24)
    climate_avg_setpoint: Optional[float] = None
    climate_avg_humidity: Optional[float] = None


async def run_zone(
    token: str, zone: ZoneConfig, target_day: date,
) -> ZoneDayResult:
    sig = zone.signals
    tz = zone.timezone_offset_hours
    start_utc = local_midnight_utc(target_day, tz)
    end_utc = start_utc + timedelta(days=1)

    # Gather all entity IDs to query in one shot
    entities: list[str] = []
    if sig.get("golf_sim_flag"):
        entities.append(sig["golf_sim_flag"])
    if sig.get("bench_presence"):
        entities.append(sig["bench_presence"])
    bp = sig.get("bench_power")
    if bp and bp.get("entity"):
        entities.append(bp["entity"])
    entities.extend(sig.get("lights", []) or [])
    entities.extend(sig.get("person_detect", []) or [])
    entities.extend(sig.get("doors", []) or [])
    if sig.get("walk_in_door"):
        entities.append(sig["walk_in_door"])
    if sig.get("climate_entity"):
        entities.append(sig["climate_entity"])
    if sig.get("humidity_entity"):
        entities.append(sig["humidity_entity"])

    history = await fetch_history_ws(token, entities, start_utc, end_utc)

    # Build per-hour metrics
    hours = [HourMetrics(hour=h) for h in range(24)]

    if sig.get("golf_sim_flag"):
        per_h = on_minutes_per_hour(history.get(sig["golf_sim_flag"], []), target_day, tz)
        for h, v in enumerate(per_h):
            hours[h].golf_sim_min = v

    if sig.get("bench_presence"):
        per_h = on_minutes_per_hour(history.get(sig["bench_presence"], []), target_day, tz)
        for h, v in enumerate(per_h):
            hours[h].bench_presence_min = v

    if bp and bp.get("entity"):
        threshold = (bp.get("standby_w") or 0) + (bp.get("delta_threshold_w") or 50)
        per_h = mean_above_threshold_minutes_per_hour(
            history.get(bp["entity"], []), target_day, tz, threshold,
        )
        for h, v in enumerate(per_h):
            hours[h].bench_power_min = v

    # Lights: union across multiple entities — sum minutes any one was on
    # (overcounts overlaps but for "was someone here?" the question is binary)
    lights_per_h_union = [0.0] * 24
    for ent in sig.get("lights", []) or []:
        per_h = on_minutes_per_hour(history.get(ent, []), target_day, tz)
        for h, v in enumerate(per_h):
            lights_per_h_union[h] = max(lights_per_h_union[h], v)
    for h, v in enumerate(lights_per_h_union):
        hours[h].lights_min = v

    # Person detect events — sum across all camera entities
    for ent in sig.get("person_detect", []) or []:
        per_h = transitions_per_hour(history.get(ent, []), target_day, tz)
        for h, v in enumerate(per_h):
            hours[h].person_detect_events += v

    # Door events
    for ent in sig.get("doors", []) or []:
        per_h = transitions_per_hour(history.get(ent, []), target_day, tz)
        for h, v in enumerate(per_h):
            hours[h].door_events += v
    if sig.get("walk_in_door"):
        per_h = transitions_per_hour(history.get(sig["walk_in_door"], []), target_day, tz)
        for h, v in enumerate(per_h):
            hours[h].walk_in_events += v

    # Classify each hour
    cls = zone.classifier
    for hm in hours:
        hm.classification = classify_hour(hm, cls)

    # Aggregate
    res = ZoneDayResult(zone=zone.name, audit_date=target_day)
    sustained_minutes_by_hour = [0.0] * 24
    for hm in hours:
        c = hm.classification
        if c.startswith("SUSTAINED"):
            res.sustained_hours += 1
            # Compute sustained-minutes for peak-hour selection
            sustained_minutes_by_hour[hm.hour] = max(
                hm.golf_sim_min, hm.bench_presence_min,
                hm.bench_power_min, hm.lights_min,
            )
        elif c == "TRANSIENT":
            res.transient_hours += 1
        else:
            res.empty_hours += 1
        res.golf_sim_total_min += hm.golf_sim_min
        res.bench_power_total_min += hm.bench_power_min
        res.lights_total_min += hm.lights_min
        res.door_event_total += hm.door_events
        res.walk_in_event_total += hm.walk_in_events
        res.person_detect_total += hm.person_detect_events
    res.classifications_by_hour = [hm.classification for hm in hours]
    if any(v > 0 for v in sustained_minutes_by_hour):
        res.peak_sustained_hour = sustained_minutes_by_hour.index(max(sustained_minutes_by_hour))

    # Climate context (averages — purely informational, not in classifier)
    cl_ent = sig.get("climate_entity")
    if cl_ent and cl_ent in history:
        # set_attr won't be in minimal-response history; skip for now
        pass

    return res


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "audit_date", "zone", "sustained_hours", "transient_hours", "empty_hours",
    "golf_sim_total_min", "bench_power_total_min", "lights_total_min",
    "door_event_total", "walk_in_event_total", "person_detect_total",
    "peak_sustained_hour", "classifications_by_hour", "logger_version",
]


def append_zone_csv(csv_dir: Path, res: ZoneDayResult) -> Path:
    csv_dir.mkdir(parents=True, exist_ok=True)
    csv_path = csv_dir / f"{res.zone}_daily.csv"
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(CSV_COLUMNS)
        w.writerow([
            res.audit_date.isoformat(), res.zone,
            res.sustained_hours, res.transient_hours, res.empty_hours,
            f"{res.golf_sim_total_min:.0f}", f"{res.bench_power_total_min:.0f}",
            f"{res.lights_total_min:.0f}",
            res.door_event_total, res.walk_in_event_total, res.person_detect_total,
            "" if res.peak_sustained_hour is None else res.peak_sustained_hour,
            "|".join(res.classifications_by_hour),
            LOGGER_VERSION,
        ])
    return csv_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, action="append",
                        help="One or more zone config files. Repeat for multiple. "
                             "Default: tools/occupancy/lrd.yaml")
    parser.add_argument("--csv-dir", type=Path, default=CSV_DIR_DEFAULT)
    parser.add_argument("--token-file", type=Path, default=TOKEN_FILE_DEFAULT)
    parser.add_argument("--for-date", type=str, default=None)
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--print-clean", action="store_true")
    args = parser.parse_args()

    try:
        token = args.token_file.read_text().strip()
    except FileNotFoundError:
        print(f"ERROR: token file {args.token_file} missing", file=sys.stderr)
        return 0

    if not args.config:
        default = Path(__file__).parent / "occupancy" / "lrd.yaml"
        args.config = [default]

    zones: list[ZoneConfig] = []
    for cf in args.config:
        zones.extend(load_zones(cf))
    zones = [z for z in zones if z.enabled]

    if not zones:
        if args.print_clean:
            print(f"[{datetime.now().isoformat(timespec='seconds')}] "
                  f"occupancy-log: no enabled zones — nothing to do")
        return 0

    # Default target: yesterday in each zone's local tz. Use the FIRST zone's
    # tz for the default; if zones span timezones at boundary hours this could
    # be off by a day. Override with --for-date for backfill.
    if args.for_date:
        target_day = date.fromisoformat(args.for_date)
    else:
        now_utc = datetime.now(timezone.utc)
        first_tz = zones[0].timezone_offset_hours
        now_local = now_utc + timedelta(hours=first_tz)
        target_day = (now_local - timedelta(days=1)).date()

    now_iso = datetime.now().isoformat(timespec="seconds")
    results: list[ZoneDayResult] = []
    for zone in zones:
        try:
            res = asyncio.run(run_zone(token, zone, target_day))
            results.append(res)
            append_zone_csv(args.csv_dir, res)
        except Exception as e:
            print(f"[{now_iso}] occupancy-log {zone.name}: ERROR {e}", file=sys.stderr)

    if args.print_clean or any(r.sustained_hours > 0 for r in results):
        for res in results:
            print(
                f"[{now_iso}] occupancy-log {res.zone} {target_day}: "
                f"sustained {res.sustained_hours}h, transient {res.transient_hours}h, "
                f"empty {res.empty_hours}h, golf-sim {res.golf_sim_total_min:.0f}m, "
                f"bench-power {res.bench_power_total_min:.0f}m, "
                f"doors {res.door_event_total}, walk-in {res.walk_in_event_total}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
