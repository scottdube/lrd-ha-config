#!/usr/bin/env python3
"""
Offline analysis of a JSON stats dump from energy_pull_stats.py.

Prints daily totals, top consumers, HVAC system split, hour-of-day profile,
and overnight (03:00-04:00 EDT) decomposition. Designed for interactive
trend-spotting — the daily anomaly/opportunity checks live in
energy_audit.py.

Usage
-----
    python3 tools/energy_pull_stats.py \
        --token ~/.ha_token --days 14 --out /tmp/energy_stats.json
    python3 tools/energy_analyze.py --stats /tmp/energy_stats.json

Outputs only to stdout; safe to pipe / redirect.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

EDT = timezone(timedelta(hours=-4))

# Templates report in kWh; underlying ESPHome circuits in Wh.
KWH_NATIVE = {
    "sensor.whole_home_daily_energy",
    "sensor.hvac_daily_energy",
    "sensor.always_on_daily_energy",
    "sensor.pool_subpanel_daily_energy_kwh",
}

# Per-circuit names for shorter labels in reports.
CIRCUIT_LABEL_PREFIXES = (
    ("sensor.emporia_vue_panel_a_", "P-A "),
    ("sensor.emporia_vue_panel_b_", "P-B "),
    ("sensor.", ""),
)


def to_kwh(eid: str, value: float) -> float:
    return value if eid in KWH_NATIVE else value / 1000.0


def short_label(eid: str) -> str:
    for prefix, repl in CIRCUIT_LABEL_PREFIXES:
        if eid.startswith(prefix):
            return repl + eid[len(prefix):].replace("_daily_energy", "")
    return eid


def daily_totals(rows: list[dict], eid: str) -> tuple[dict, list[tuple]]:
    """Sum 'change' per local-day. Returns (by_day kWh, by_hour list)."""
    by_day: dict = {}
    by_hour: list = []
    for r in rows:
        t_utc = datetime.fromtimestamp(r["start"] / 1000, tz=timezone.utc)
        t = t_utc.astimezone(EDT)
        kwh = to_kwh(eid, r.get("change") or 0.0)
        by_day[t.date()] = by_day.get(t.date(), 0.0) + kwh
        by_hour.append((t, kwh))
    return by_day, by_hour


def hour_profile(by_hour: list[tuple]) -> dict[int, float]:
    buckets: dict[int, list[float]] = {h: [] for h in range(24)}
    for t, kwh in by_hour:
        buckets[t.hour].append(kwh)
    return {h: (sum(v) / len(v) if v else 0.0) for h, v in buckets.items()}


def report(stats: dict, electric_rate: float) -> None:
    results: dict = {}
    for eid, rows in stats.items():
        by_day, by_hour = daily_totals(rows, eid)
        results[eid] = {"by_day": by_day, "by_hour": by_hour}

    pa = "sensor.emporia_vue_panel_a_total_daily_energy"
    pb = "sensor.emporia_vue_panel_b_total_daily_energy"
    if pa not in results or pb not in results:
        print("ERROR: panel total entities missing from stats dump", file=sys.stderr)
        return

    days = sorted(set(results[pa]["by_day"].keys()) | set(results[pb]["by_day"].keys()))
    whole = {d: results[pa]["by_day"].get(d, 0) + results[pb]["by_day"].get(d, 0) for d in days}

    # --- Daily whole-home ---
    print("=" * 64)
    print("DAILY WHOLE-HOME ENERGY (kWh) — Panel A + Panel B, local-day EDT")
    print("=" * 64)
    for d in days:
        v = whole[d]
        if v < 1:
            continue
        bar = "█" * int(v / 3)
        print(f"  {d} {d.strftime('%a')}  {v:7.2f}  {bar}")

    complete = [whole[d] for d in days if whole[d] > 50]
    if complete:
        avg = sum(complete) / len(complete)
        print(f"\n  Complete days: {len(complete)}, avg {avg:.1f} kWh/day, "
              f"min {min(complete):.1f}, max {max(complete):.1f}")
        print(f"  Cost @ ${electric_rate:.3f}/kWh: avg ${avg * electric_rate:.2f}/day, "
              f"projected monthly ${avg * electric_rate * 30:.0f}")

    # --- Top consumers ---
    print("\n" + "=" * 64)
    print("TOP CONSUMERS — window totals (kWh), sorted")
    print("=" * 64)
    totals: dict = {}
    excluded = {pa, pb} | KWH_NATIVE | {
        "sensor.emporia_vue_panel_a_unmonitored_daily_energy",
        "sensor.emporia_vue_panel_b_unmonitored_daily_energy",
        "sensor.air_1_total_daily_energy",
        "sensor.air_2_total_daily_energy",
    }
    for eid, r in results.items():
        if eid in excluded:
            continue
        totals[eid] = sum(r["by_day"].values())
    wh_total = sum(complete) if complete else 1
    for eid, kwh in sorted(totals.items(), key=lambda x: -x[1])[:15]:
        pct = kwh / wh_total * 100
        print(f"  {kwh:7.1f} kWh  ({pct:4.1f}% of WH)  {short_label(eid)}")

    # --- HVAC split ---
    print("\n" + "=" * 64)
    print("HVAC SYSTEM SPLIT (Air 1 / Air 2 / Garage MS)")
    print("=" * 64)
    hvac = {
        "Air 1 condenser":   "sensor.emporia_vue_panel_a_circuit_9_air_1_condenser_daily_energy",
        "Air 1 handler":     "sensor.emporia_vue_panel_b_circuit_9_air_1_handler_daily_energy",
        "Air 2 condenser":   "sensor.emporia_vue_panel_b_circuit_10_air_2_condenser_daily_energy",
        "Air 2 handler":     "sensor.emporia_vue_panel_a_circuit_5_air_2_handler_daily_energy",
        "Garage mini split": "sensor.emporia_vue_panel_a_circuit_10_garage_mini_split_daily_energy",
    }
    for name, eid in hvac.items():
        if eid not in results:
            continue
        vals = [v for v in results[eid]["by_day"].values() if v > 0]
        if vals:
            print(f"  {name:22s}  {sum(vals):7.1f} kWh total, avg {sum(vals) / len(vals):5.2f}/day")

    # --- Hour-of-day shape ---
    print("\n" + "=" * 64)
    print("HOUR-OF-DAY PROFILE — Whole Home (avg kWh/hr by hour, local EDT)")
    print("=" * 64)
    hp_a = hour_profile(results[pa]["by_hour"])
    hp_b = hour_profile(results[pb]["by_hour"])
    combined = {h: hp_a[h] + hp_b[h] for h in range(24)}
    mx = max(combined.values()) or 1.0
    for h in range(24):
        v = combined[h]
        bar = "█" * int(v / mx * 40)
        print(f"  {h:02d}:00  {v:5.2f}  {bar}")
    bl = min(combined.values())
    print(f"\n  Implied baseload (min hour avg): {bl * 1000:.0f} W")
    print(f"  Implied baseload daily: {bl * 24:.1f} kWh "
          f"(${bl * 24 * electric_rate:.2f}/day)")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--stats", type=Path, required=True,
                   help="JSON dump from energy_pull_stats.py")
    p.add_argument("--rate", type=float, default=0.136,
                   help="$/kWh for cost projection (SECO Energy effective rate)")
    args = p.parse_args()
    stats = json.loads(args.stats.read_text())
    report(stats, args.rate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
