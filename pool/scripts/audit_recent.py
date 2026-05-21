#!/usr/bin/env python3
"""
Pool recent-state audit — runs every 3 hours.

Sits between the real-time watchers (packages/pool/pool_health_watcher.yaml)
and the nightly retrospective auditor (pool/scripts/auditor.py). Reads the
last 3 hours of state-log data, checks for sustained problem patterns, and
notifies via notify.scott_and_ha ONLY if problems are found. Silent on clean.

Designed for unattended cadence runs (launchd every 3 hours).

Five checks:

  1. Pump schedule mismatch — pump off >30 min during 08:30-20:00 EDT, OR
     pump on >30 min outside that window. Catches Hayward local-schedule
     drift, manual interventions that weren't restored, or controller
     state that doesn't match expectation.

  2. Pump on but power < 50W for >5 min (class-2 pattern). Re-checks what
     the real-time watcher might have missed via mode: single semantics.

  3. External water temp sensor freshness ratio < 80% over the 3h window.
     At 30-min deep-sleep cadence, expect ~6 fresh readings in 3 hours.
     Alert if more than ~1 sample missing — indicates WiFi flakiness or
     battery/firmware issue developing.

  4. Filter state unavailable >5 min cumulative in 3h — sub-threshold
     integration flapping. The 10-min class-1 watcher won't fire on a
     series of shorter blips that add up to instability.

  5. water_temp_authoritative outside 60-110°F. Out-of-range = sensor
     glitch or stuck reading. 60°F is conservative low for a Florida
     pool; 110°F is well above any normal operating temperature.

Setup
-----
  1. HA long-lived access token at ~/.ha_token (mode 600). Same token
     used by audit_yesterday.sh — share between the two.
  2. pool/analysis/pool_state_log_live.csv refreshed by the rsync mirror.
  3. notify.scott_and_ha group deployed in HA.

Usage
-----
    python3 audit_recent.py [--csv PATH] [--hours-back N]
                            [--no-notify] [--print-clean]

    --csv          override live CSV path
    --hours-back   override the 3h window (e.g., for debugging)
    --no-notify    don't send push notification even on problems
    --print-clean  print "all checks PASS" line on stdout even when silent
                   (useful for launchd log)

Exit code: 0 always (silent-on-clean expected; non-zero would noise the
launchd log every clean run).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, time, timezone, timedelta
from pathlib import Path
from typing import Optional

# Defaults (Mac mini paths)
LIVE_CSV_DEFAULT = (
    Path.home() / "code" / "home-assistant" / "pool" / "analysis" /
    "pool_state_log_live.csv"
)
TOKEN_FILE = Path.home() / ".ha_token"
HA_BASE = "http://192.168.50.11:8123"
NOTIFY_TARGET = "scott_and_ha"
HOURS_BACK_DEFAULT = 3

# Pump schedule (Hayward local schedule as of 2026-05-18 ops mode).
# If schedule changes, update these. Stored as decimal hours for easy
# comparison: 8.5 = 08:30.
PUMP_ON_HOUR_START = 8.5   # 08:30 EDT
PUMP_ON_HOUR_END = 20.0    # 20:00 EDT

# Thresholds
SCHEDULE_MISMATCH_MIN = 30
PUMP_NO_POWER_FAIL_MIN = 5
PUMP_NO_POWER_SKIP_SEC = 120  # Priming/spin-up grace
PUMP_POWER_MIN_W = 50.0
EXTERNAL_FRESH_RATIO_MIN = 0.80
UNAVAILABLE_CUMULATIVE_MIN = 5
WATER_TEMP_RANGE_LOW = 60.0
WATER_TEMP_RANGE_HIGH = 110.0

AUDIT_VERSION = "recent-1.0.0"


def parse_ts(s: str) -> Optional[datetime]:
    """Parse logger timestamp ('YYYY-MM-DD HH:MM:SS' in local time)."""
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def load_recent_rows(csv_path: Path, hours_back: int) -> tuple[list[str], list[dict]]:
    """Load rows from the last N hours. Returns (columns, rows)."""
    cutoff = datetime.now() - timedelta(hours=hours_back)
    with csv_path.open() as f:
        # Skip schema-version comment if present
        first = f.readline()
        if not first.startswith("#"):
            f.seek(0)
        reader = csv.DictReader(f)
        cols = list(reader.fieldnames or [])
        rows = []
        for row in reader:
            ts = parse_ts(row.get("timestamp", ""))
            if ts is None:
                continue
            if ts >= cutoff:
                rows.append(row)
    return cols, rows


def check_pump_schedule(rows: list[dict]) -> Optional[str]:
    """
    Returns a problem message if pump state contradicts schedule for >30 min
    in the window, else None.
    """
    if not rows:
        return None
    # Bin rows into expected-on vs expected-off based on time-of-day
    expected_on_off_minutes = 0  # Should be on, but off
    expected_off_on_minutes = 0  # Should be off, but on
    for a, b in zip(rows, rows[1:]):
        ta, tb = parse_ts(a["timestamp"]), parse_ts(b["timestamp"])
        if not (ta and tb):
            continue
        dur_min = (tb - ta).total_seconds() / 60.0
        hour_decimal = ta.hour + ta.minute / 60.0
        in_window = PUMP_ON_HOUR_START <= hour_decimal < PUMP_ON_HOUR_END
        state = (a.get("local_filter_state") or "").lower()
        if state == "unavailable":
            # Unavailable rows aren't conclusive; skip
            continue
        is_on = state == "on"
        if in_window and not is_on:
            expected_on_off_minutes += dur_min
        elif not in_window and is_on:
            expected_off_on_minutes += dur_min
    problems = []
    if expected_on_off_minutes > SCHEDULE_MISMATCH_MIN:
        problems.append(
            f"Pump OFF during scheduled on-window for "
            f"{expected_on_off_minutes:.0f} min (threshold {SCHEDULE_MISMATCH_MIN})"
        )
    if expected_off_on_minutes > SCHEDULE_MISMATCH_MIN:
        problems.append(
            f"Pump ON during scheduled off-window for "
            f"{expected_off_on_minutes:.0f} min (threshold {SCHEDULE_MISMATCH_MIN})"
        )
    return "; ".join(problems) if problems else None


def check_pump_no_power(rows: list[dict]) -> Optional[str]:
    """
    Returns a problem message if pump claimed on with sub-threshold power
    for sustained period (class-2 pattern). Mirrors auditor.py P5 logic.
    """
    if not rows:
        return None
    sub_threshold_min = 0.0
    run_start = None
    for a, b in zip(rows, rows[1:]):
        ta, tb = parse_ts(a["timestamp"]), parse_ts(b["timestamp"])
        if not (ta and tb):
            continue
        if (a.get("local_filter_state") or "").lower() != "on":
            run_start = None
            continue
        if run_start is None:
            run_start = ta
        # Skip priming window
        if (ta - run_start).total_seconds() < PUMP_NO_POWER_SKIP_SEC:
            continue
        power_raw = (a.get("local_filter_power") or "").lower()
        if power_raw in ("unavailable", "unknown", ""):
            continue
        power = to_float(power_raw)
        if power is None:
            continue
        if power < PUMP_POWER_MIN_W:
            sub_threshold_min += (tb - ta).total_seconds() / 60.0
    if sub_threshold_min > PUMP_NO_POWER_FAIL_MIN:
        return (
            f"Pump ON but power < {PUMP_POWER_MIN_W:.0f}W for "
            f"{sub_threshold_min:.1f} min (threshold {PUMP_NO_POWER_FAIL_MIN}). "
            "Check OmniLogic UI for MSP_DEV_COMM_LOSS alarms (ADR-019)."
        )
    return None


def check_external_freshness(rows: list[dict]) -> Optional[str]:
    """
    Returns a problem if external sensor freshness ratio is below threshold.
    """
    if not rows:
        return None
    eligible = 0  # Rows where the external sensor data is even parseable
    fresh_count = 0
    for row in rows:
        raw = (row.get("external_water_temp_fresh") or "").strip().lower()
        if raw not in ("true", "false"):
            continue
        eligible += 1
        if raw == "true":
            fresh_count += 1
    if eligible == 0:
        return None  # Phase 2 columns missing; skip check
    ratio = fresh_count / eligible
    if ratio < EXTERNAL_FRESH_RATIO_MIN:
        return (
            f"External temp sensor fresh ratio {ratio * 100:.0f}% "
            f"({fresh_count}/{eligible} rows) — below {EXTERNAL_FRESH_RATIO_MIN * 100:.0f}% "
            f"threshold. WiFi flakiness or sensor issue developing."
        )
    return None


def check_integration_flapping(rows: list[dict]) -> Optional[str]:
    """
    Returns a problem if integration entities were `unavailable` for
    > 5 cumulative minutes in the window.
    """
    if not rows:
        return None
    unavail_min = 0.0
    for a, b in zip(rows, rows[1:]):
        ta, tb = parse_ts(a["timestamp"]), parse_ts(b["timestamp"])
        if not (ta and tb):
            continue
        if (a.get("local_filter_state") or "").lower() == "unavailable":
            unavail_min += (tb - ta).total_seconds() / 60.0
    if unavail_min > UNAVAILABLE_CUMULATIVE_MIN:
        return (
            f"Integration flapping: filter_state=unavailable for "
            f"{unavail_min:.1f} cumulative min "
            f"(threshold {UNAVAILABLE_CUMULATIVE_MIN}). Sub-class-1, "
            "but worth investigating."
        )
    return None


def check_water_temp_range(rows: list[dict]) -> Optional[str]:
    """
    Returns a problem if water_temp_authoritative is outside safe range
    in the most recent row. Single-sample check on the latest data.
    """
    if not rows:
        return None
    latest = rows[-1]
    val = to_float(latest.get("water_temp_authoritative", ""))
    if val is None:
        return None  # Unavailable / missing — different problem class
    if val < WATER_TEMP_RANGE_LOW or val > WATER_TEMP_RANGE_HIGH:
        return (
            f"water_temp_authoritative={val:.1f}°F outside expected range "
            f"[{WATER_TEMP_RANGE_LOW}, {WATER_TEMP_RANGE_HIGH}]. Sensor "
            "glitch or stuck reading."
        )
    return None


def push_notify(title: str, message: str, token_file: Path) -> None:
    """Send notification via notify.scott_and_ha. Failure is non-fatal."""
    try:
        token = token_file.read_text().strip()
    except FileNotFoundError:
        print(
            f"WARN: token file {token_file} missing; skipping notify",
            file=sys.stderr,
        )
        return
    payload = json.dumps({"title": title, "message": message}).encode()
    req = urllib.request.Request(
        f"{HA_BASE}/api/services/notify/{NOTIFY_TARGET}",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        print(f"WARN: notify failed: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pool recent-state audit (silent on clean)"
    )
    parser.add_argument("--csv", type=Path, default=LIVE_CSV_DEFAULT)
    parser.add_argument("--hours-back", type=int, default=HOURS_BACK_DEFAULT)
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--print-clean", action="store_true")
    parser.add_argument(
        "--token-file", type=Path, default=TOKEN_FILE,
        help=f"HA long-lived token file (default {TOKEN_FILE})",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"ERROR: CSV not found at {args.csv}", file=sys.stderr)
        return 0  # Silent — log only

    cols, rows = load_recent_rows(args.csv, args.hours_back)
    if not rows:
        if args.print_clean:
            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] "
                f"audit-recent: no rows in last {args.hours_back}h window"
            )
        return 0

    checks = [
        ("schedule", check_pump_schedule),
        ("no_power", check_pump_no_power),
        ("external_fresh", check_external_freshness),
        ("integration_flap", check_integration_flapping),
        ("water_temp_range", check_water_temp_range),
    ]

    problems = []
    for name, fn in checks:
        try:
            msg = fn(rows)
        except Exception as e:
            msg = f"check {name} crashed: {e}"
        if msg:
            problems.append(f"[{name}] {msg}")

    if not problems:
        if args.print_clean:
            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] "
                f"audit-recent: {len(rows)} rows / {args.hours_back}h — "
                f"all {len(checks)} checks PASS"
            )
        return 0

    title = f"Pool: recent-audit found {len(problems)} issue(s)"
    body = "\n\n".join(problems)
    body += f"\n\nWindow: last {args.hours_back}h, {len(rows)} rows scanned."
    body += f"\nAudit version: {AUDIT_VERSION}"

    # Print to launchd log
    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] "
        f"audit-recent: {len(problems)} problem(s):"
    )
    print(body)

    if not args.no_notify:
        push_notify(title, body, args.token_file)

    return 0


if __name__ == "__main__":
    sys.exit(main())
