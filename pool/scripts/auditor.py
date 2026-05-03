#!/usr/bin/env python3
"""
Pool auditor — Phase 1 + Phase 2 (P-series).

Reads pool_state_log.csv, runs assertions per pool/docs/auditor.md, writes
JSON results, optionally pushes mobile notification on FAIL.

Usage
-----
    python3 auditor.py --date YYYY-MM-DD [--csv PATH] [--out DIR]
                       [--no-notify] [--success-summary]
    python3 auditor.py --date-range YYYY-MM-DD YYYY-MM-DD [--no-notify]

Defaults
--------
    --csv  /config/pool_state_log.csv
    --out  /config/pool/audit/

Schema
------
Tolerant of phase-1 (35 col) and phase-1.5 (44 col) schemas. Skips
assertions whose required columns are missing.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Optional

CSV_DEFAULT = "/config/pool_state_log.csv"
OUT_DEFAULT = "/config/pool/audit/"
TOKEN_FILE = "/config/.state_logger_token"
HA_BASE = "http://localhost:8123"
NOTIFY_TARGET = "scott_and_ha"
AUDITOR_VERSION = "1.1.0"

WATERFALL_START_DEFAULT = time(8, 0)
WATERFALL_END_DEFAULT = time(20, 0)
WATERFALL_TRANSITION_TOL_MIN = 15
WATERFALL_WINDOW_TOL_MIN = 5
PUMP_TRANSITION_TOL_MIN = 10
LOG_CADENCE_TARGET_MIN = 10
LOG_CADENCE_TOL_MIN = 2
LOG_CADENCE_GAP_FAIL_MIN = 12
SENSOR_UNAVAIL_FAIL_MIN = 30
HEATER_PUMP_SPEED_MIN = 65
IDLE_PUMP_SPEED_MAX = 55
HEATER_TRANSITION_GRACE_ROWS = 1
HEATER_TEMP_DELTA_MIN_F = 0.3
HEATER_TEMP_WINDOW_MIN = 60
INTEGRATION_FAIL_PCT_MAX = 3.0
MIDNIGHT_BURST_END = time(1, 30)


@dataclass
class Result:
    id: str
    name: str
    status: str
    expected: str = ""
    observed: str = ""
    severity: str = "med"
    violating_rows: list = field(default_factory=list)
    reason: str = ""


def parse_ts(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def to_bool(v) -> Optional[bool]:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("true", "on", "open", "yes", "1"):
        return True
    if s in ("false", "off", "closed", "no", "0"):
        return False
    return None


def to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def load_csv(path: str) -> tuple[list[str], list[dict]]:
    with open(path, "r", newline="") as f:
        first = f.readline()
        if not first.startswith("# schema_version"):
            f.seek(0)
        reader = csv.DictReader(f)
        rows = list(reader)
        return reader.fieldnames or [], rows


def filter_date(rows: list[dict], target: date) -> list[dict]:
    out = []
    for r in rows:
        ts = parse_ts(r.get("timestamp", ""))
        if ts and ts.date() == target:
            out.append(r)
    return out


def transitions(rows: list[dict], col: str, want_truthy_first: bool):
    """Yield (ts, prev_val, cur_val) when col changes between adjacent rows."""
    prev = None
    prev_ts = None
    for r in rows:
        ts = parse_ts(r.get("timestamp", ""))
        cur = r.get(col)
        if prev is not None and cur != prev:
            yield ts, prev, cur
        prev = cur
        prev_ts = ts


def push_notify(title: str, message: str, ha_base: str, token_file: str,
                notify_target: str) -> bool:
    try:
        token = Path(token_file).read_text().strip()
    except OSError:
        return False
    req = urllib.request.Request(
        f"{ha_base}/api/services/notify/{notify_target}",
        data=json.dumps({"title": title, "message": message}).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True
    except urllib.error.URLError:
        return False


def assert_d1(rows, cols) -> Result:
    r = Result("D1", "swim_day_consistency", "PASS",
               expected="swim_day_raw constant across day (ignoring transient unavailable)",
               severity="low")
    if "swim_day_raw" not in cols:
        r.status = "SKIP"; r.reason = "swim_day_raw column missing"; return r
    vals = {row.get("swim_day_raw") for row in rows
            if row.get("swim_day_raw")
            and row.get("swim_day_raw").lower() not in ("unavailable", "unknown")}
    if len(vals) > 1:
        r.status = "FAIL"
        r.observed = f"swim_day_raw took multiple values: {sorted(vals)}"
    else:
        r.observed = f"swim_day_raw={next(iter(vals)) if vals else 'none'}"
    return r


def assert_d2(rows, cols) -> Result:
    r = Result("D2", "log_cadence", "PASS",
               expected=f"time_pattern rows every {LOG_CADENCE_TARGET_MIN}±{LOG_CADENCE_TOL_MIN} min",
               severity="low")
    tp = [row for row in rows if row.get("row_type") == "time_pattern"]
    if len(tp) < 2:
        r.status = "SKIP"; r.reason = "<2 time_pattern rows"; return r
    gaps = []
    for a, b in zip(tp, tp[1:]):
        ta, tb = parse_ts(a["timestamp"]), parse_ts(b["timestamp"])
        if ta and tb:
            gaps.append((tb - ta).total_seconds() / 60.0)
    out_of_spec = [g for g in gaps
                   if abs(g - LOG_CADENCE_TARGET_MIN) > LOG_CADENCE_TOL_MIN]
    big = [g for g in gaps if g > LOG_CADENCE_GAP_FAIL_MIN]
    pct = 100.0 * len(out_of_spec) / max(len(gaps), 1)
    r.observed = (f"{len(gaps)} gaps, mean {sum(gaps)/len(gaps):.1f} min, "
                  f"out-of-spec {pct:.1f}% ({len(out_of_spec)}), "
                  f"max gap {max(gaps):.1f} min")
    if pct > 5.0 or big:
        r.status = "FAIL"
    return r


def assert_d3(rows, cols) -> Result:
    r = Result("D3", "sensor_availability", "PASS",
               expected=f"no critical sensor unavailable >{SENSOR_UNAVAIL_FAIL_MIN} cumulative min "
                        f"(water_temp exempt while pump is off — sensor settles only with flow)",
               severity="med")
    critical = ["local_water_temp", "oat_weatherflow",
                "local_filter_state", "local_waterfall_state"]
    have = [c for c in critical if c in cols]
    if not have:
        r.status = "SKIP"; r.reason = "no critical columns present"; return r
    bad_minutes = defaultdict(float)
    for a, b in zip(rows, rows[1:]):
        ta, tb = parse_ts(a["timestamp"]), parse_ts(b["timestamp"])
        if not (ta and tb):
            continue
        dur = (tb - ta).total_seconds() / 60.0
        for c in have:
            v = (a.get(c) or "").lower()
            if v in ("unavailable", "unknown", ""):
                if c == "local_water_temp" and pump_on(a) is not True:
                    continue
                bad_minutes[c] += dur
    bad = {k: v for k, v in bad_minutes.items() if v > SENSOR_UNAVAIL_FAIL_MIN}
    if bad:
        r.status = "FAIL"
        r.observed = "; ".join(f"{k}={v:.0f} min" for k, v in bad.items())
    else:
        r.observed = "all critical sensors within tolerance"
    return r


def is_swim_day(rows) -> Optional[bool]:
    for row in rows:
        v = (row.get("swim_day_raw") or "").strip().lower()
        if v in ("yes", "true", "on", "1"):
            return True
        if v in ("no", "false", "off", "0"):
            return False
    return None


def assert_w1(rows, cols) -> Result:
    r = Result("W1", "waterfall_window_only",
               status="PASS",
               expected=f"waterfall open only between {WATERFALL_START_DEFAULT} and {WATERFALL_END_DEFAULT}",
               severity="high")
    if "local_waterfall_state" not in cols:
        r.status = "SKIP"; r.reason = "local_waterfall_state missing"; return r
    tol = timedelta(minutes=WATERFALL_WINDOW_TOL_MIN)
    violations = []
    for row in rows:
        ts = parse_ts(row["timestamp"])
        if not ts:
            continue
        is_open = to_bool(row.get("local_waterfall_state"))
        if not is_open:
            continue
        start_dt = datetime.combine(ts.date(), WATERFALL_START_DEFAULT) - tol
        end_dt = datetime.combine(ts.date(), WATERFALL_END_DEFAULT) + tol
        if not (start_dt <= ts <= end_dt):
            violations.append({"timestamp": row["timestamp"],
                               "local_waterfall_state": row.get("local_waterfall_state")})
    if violations:
        r.status = "FAIL"
        r.observed = f"{len(violations)} off-window open rows"
        r.violating_rows = violations[:10]
    else:
        r.observed = "no off-window opens"
    return r


def assert_w2(rows, cols, swim) -> Result:
    r = Result("W2", "waterfall_opens_at_start", status="PASS",
               expected="closed→open transition near 08:00 on swim days",
               severity="med")
    if "local_waterfall_state" not in cols:
        r.status = "SKIP"; r.reason = "column missing"; return r
    if swim is False:
        r.status = "SKIP"; r.reason = "non-swim day"; return r
    target = datetime.combine(rows[0] and parse_ts(rows[0]["timestamp"]).date()
                              or date.today(), WATERFALL_START_DEFAULT)
    tol = timedelta(minutes=WATERFALL_TRANSITION_TOL_MIN)
    if datetime.now() < target + tol:
        r.status = "SKIP"
        r.reason = f"audit run before open-window deadline ({(target+tol).strftime('%H:%M')})"
        return r
    found = None
    for ts, prev, cur in transitions(rows, "local_waterfall_state", True):
        if to_bool(prev) is False and to_bool(cur) is True:
            if abs((ts - target).total_seconds()) <= tol.total_seconds():
                found = ts
                break
    if not found:
        r.status = "FAIL"
        r.observed = f"no closed→open transition within ±{WATERFALL_TRANSITION_TOL_MIN} min of {WATERFALL_START_DEFAULT}"
    else:
        r.observed = f"opened at {found.time()}"
    return r


def assert_w3(rows, cols) -> Result:
    r = Result("W3", "waterfall_closes_at_end", status="PASS",
               expected="open→closed transition near 20:00 if waterfall opened today",
               severity="high")
    if "local_waterfall_state" not in cols:
        r.status = "SKIP"; r.reason = "column missing"; return r
    target_date = parse_ts(rows[0]["timestamp"]).date()
    target = datetime.combine(target_date, WATERFALL_END_DEFAULT)
    tol = timedelta(minutes=WATERFALL_TRANSITION_TOL_MIN)
    if datetime.now() < target + tol:
        r.status = "SKIP"
        r.reason = f"audit run before close-window deadline ({(target+tol).strftime('%H:%M')})"
        return r
    ever_open = any(to_bool(row.get("local_waterfall_state")) is True for row in rows)
    if not ever_open:
        r.status = "SKIP"; r.reason = "waterfall never opened today"; return r
    found = None
    for ts, prev, cur in transitions(rows, "local_waterfall_state", False):
        if to_bool(prev) is True and to_bool(cur) is False:
            if abs((ts - target).total_seconds()) <= tol.total_seconds():
                found = ts
                break
    if not found:
        r.status = "FAIL"
        r.observed = (f"no open→closed transition within ±{WATERFALL_TRANSITION_TOL_MIN} min of {WATERFALL_END_DEFAULT}; "
                      f"this is the assertion that catches the late-April class of bug")
        last = next((row for row in reversed(rows)
                     if row.get("local_waterfall_state")), None)
        if last:
            r.violating_rows = [{"timestamp": last["timestamp"],
                                 "local_waterfall_state": last.get("local_waterfall_state")}]
    else:
        r.observed = f"closed at {found.time()}"
    return r


def pump_on(row) -> Optional[bool]:
    return to_bool(row.get("local_filter_state"))


def heater_active(row) -> Optional[bool]:
    v = row.get("local_heater_equip_status")
    if v is None:
        return None
    return to_bool(v)


def assert_p1(rows, cols, swim) -> Result:
    r = Result("P1", "swim_day_pump_window", status="PASS",
               expected="pump on through swim-day filtration window",
               severity="med")
    if "local_filter_state" not in cols:
        r.status = "SKIP"; r.reason = "column missing"; return r
    if swim is not True:
        r.status = "SKIP"; r.reason = "non-swim day"; return r
    target_date = parse_ts(rows[0]["timestamp"]).date()
    start = datetime.combine(target_date, WATERFALL_START_DEFAULT)
    end = datetime.combine(target_date, WATERFALL_END_DEFAULT)
    tol = timedelta(minutes=PUMP_TRANSITION_TOL_MIN)
    in_window = [row for row in rows
                 if (ts := parse_ts(row["timestamp"]))
                 and start + tol <= ts <= end - tol]
    if not in_window:
        r.status = "SKIP"; r.reason = "no rows in interior window"; return r
    off_count = sum(1 for row in in_window if pump_on(row) is False)
    pct = 100.0 * off_count / len(in_window)
    r.observed = f"{off_count}/{len(in_window)} interior rows pump=off ({pct:.1f}%)"
    if pct > 10.0:
        r.status = "FAIL"
    return r


def assert_p2(rows, cols, swim) -> Result:
    r = Result("P2", "nonswim_day_pump_off", status="PASS",
               expected="pump off ≥95% of day on non-swim days",
               severity="med")
    if "local_filter_state" not in cols:
        r.status = "SKIP"; r.reason = "column missing"; return r
    if swim is not False:
        r.status = "SKIP"; r.reason = "swim day"; return r
    on_count = sum(1 for row in rows if pump_on(row) is True)
    pct = 100.0 * on_count / max(len(rows), 1)
    r.observed = f"{on_count}/{len(rows)} rows pump=on ({pct:.1f}%)"
    if pct > 5.0:
        r.status = "FAIL"
    return r


def assert_p3(rows, cols) -> Result:
    r = Result("P3", "pump_speed_when_heating", status="PASS",
               expected=f"pump_speed ≥ {HEATER_PUMP_SPEED_MIN}% on heater-active time_pattern rows; "
                        f"first heater-active row of each run skipped (race: logger snapshot at same "
                        f"instant blueprint fires, before pump-speed command lands)",
               severity="high")
    needed = ["local_filter_speed", "local_heater_equip_status"]
    if any(c not in cols for c in needed):
        r.status = "SKIP"; r.reason = "required columns missing"; return r
    violations = []
    prev_tp_heater_active = False
    for row in rows:
        if row.get("row_type") != "time_pattern":
            continue
        cur = heater_active(row) is True
        if cur and not prev_tp_heater_active:
            prev_tp_heater_active = cur
            continue
        prev_tp_heater_active = cur
        if cur:
            spd = to_float(row.get("local_filter_speed"))
            if spd is not None and spd < HEATER_PUMP_SPEED_MIN:
                violations.append({"timestamp": row["timestamp"],
                                   "local_filter_speed": row.get("local_filter_speed")})
    if violations:
        r.status = "FAIL"
        r.observed = f"{len(violations)} time_pattern rows heater-active with pump_speed < {HEATER_PUMP_SPEED_MIN}%"
        r.violating_rows = violations[:10]
    else:
        r.observed = "all heater-active time_pattern rows had pump at heater speed (post-first)"
    return r


def assert_p4(rows, cols) -> Result:
    r = Result("P4", "pump_speed_when_idle", status="PASS",
               expected=f"pump_speed ≤ {IDLE_PUMP_SPEED_MAX}% on idle time_pattern rows; first idle "
                        f"row after each heater run skipped (race: pump-speed-down command lands "
                        f"after the time_pattern snapshot at the same instant)",
               severity="med")
    needed = ["local_filter_speed", "local_heater_equip_status", "local_filter_state"]
    if any(c not in cols for c in needed):
        r.status = "SKIP"; r.reason = "required columns missing"; return r
    violations = []
    prev_tp_heater_active = False
    for row in rows:
        if row.get("row_type") != "time_pattern":
            continue
        cur = heater_active(row) is True
        if not cur and prev_tp_heater_active:
            prev_tp_heater_active = cur
            continue
        prev_tp_heater_active = cur
        if cur:
            continue
        if pump_on(row) is True:
            spd = to_float(row.get("local_filter_speed"))
            if spd is not None and spd > IDLE_PUMP_SPEED_MAX:
                violations.append({"timestamp": row["timestamp"],
                                   "local_filter_speed": row.get("local_filter_speed")})
    if violations:
        r.status = "FAIL"
        r.observed = f"{len(violations)} idle-pump time_pattern rows with speed > {IDLE_PUMP_SPEED_MAX}%"
        r.violating_rows = violations[:10]
    else:
        r.observed = "idle pump always within speed limit on time_pattern checks (post-first)"
    return r


def assert_h1(rows, cols, swim) -> Result:
    r = Result("H1", "heater_state_matches_swim_day", status="PASS",
               expected="heater on iff swimming_day; allow 1 mismatch in first 10 min",
               severity="med")
    if "local_heater_state" not in cols:
        r.status = "SKIP"; r.reason = "column missing"; return r
    if swim is None:
        r.status = "SKIP"; r.reason = "swim_day undetermined"; return r
    expect_on = swim
    target_date = parse_ts(rows[0]["timestamp"]).date()
    grace_end = datetime.combine(target_date, time(0, 10))
    violations = []
    for row in rows:
        ts = parse_ts(row["timestamp"])
        if ts and ts <= grace_end:
            continue
        actual = to_bool(row.get("local_heater_state"))
        if actual is None:
            continue
        if actual != expect_on:
            violations.append({"timestamp": row["timestamp"],
                               "local_heater_state": row.get("local_heater_state")})
    if violations:
        r.status = "FAIL"
        r.observed = f"{len(violations)} mismatch rows after grace"
        r.violating_rows = violations[:10]
    else:
        r.observed = f"heater state matches swim_day ({swim}) all day"
    return r


def assert_h2(rows, cols) -> Result:
    r = Result("H2", "heater_active_implies_pump_on", status="PASS",
               expected="when heater actively delivering, pump must be on",
               severity="high")
    needed = ["local_heater_equip_status", "local_filter_state"]
    if any(c not in cols for c in needed):
        r.status = "SKIP"; r.reason = "required columns missing"; return r
    violations = []
    for row in rows:
        if heater_active(row) is True and pump_on(row) is False:
            violations.append({"timestamp": row["timestamp"],
                               "local_filter_state": row.get("local_filter_state"),
                               "local_heater_equip_status": row.get("local_heater_equip_status")})
    if violations:
        r.status = "FAIL"
        r.observed = f"{len(violations)} SAFETY rows: heater active with pump off"
        r.violating_rows = violations[:10]
    else:
        r.observed = "no heater-on/pump-off violations"
    return r


def assert_h3(rows, cols) -> Result:
    r = Result("H3", "water_temp_rising_when_heating", status="PASS",
               expected=f"≥ +{HEATER_TEMP_DELTA_MIN_F}°F over {HEATER_TEMP_WINDOW_MIN} min when heating",
               severity="low")
    needed = ["local_water_temp", "local_heater_equip_status",
              "local_water_temp_reliable"]
    if any(c not in cols for c in needed):
        r.status = "SKIP"; r.reason = "required columns missing"; return r
    runs = []
    cur_run = []
    for row in rows:
        if heater_active(row) is True and to_bool(row.get("local_water_temp_reliable")):
            cur_run.append(row)
        else:
            if len(cur_run) >= 2:
                runs.append(cur_run)
            cur_run = []
    if cur_run:
        runs.append(cur_run)
    if not runs:
        r.status = "SKIP"; r.reason = "no qualifying heating window with reliable temp"; return r
    failures = []
    for run in runs:
        first_ts = parse_ts(run[0]["timestamp"])
        anchor_temp = to_float(run[0].get("local_water_temp"))
        if anchor_temp is None:
            continue
        for row in run[1:]:
            ts = parse_ts(row["timestamp"])
            t = to_float(row.get("local_water_temp"))
            if not (ts and t is not None):
                continue
            if (ts - first_ts).total_seconds() >= HEATER_TEMP_WINDOW_MIN * 60:
                if t - anchor_temp < HEATER_TEMP_DELTA_MIN_F:
                    failures.append({"window_start": run[0]["timestamp"],
                                     "window_end": row["timestamp"],
                                     "delta_f": round(t - anchor_temp, 2)})
                break
    if failures:
        r.status = "FAIL"
        r.observed = f"{len(failures)} heating windows with inadequate temp rise"
        r.violating_rows = failures[:5]
    else:
        r.observed = f"{len(runs)} heating runs all rose ≥ {HEATER_TEMP_DELTA_MIN_F}°F"
    return r


def assert_i1(rows, cols) -> Result:
    r = Result("I1", "omnilogic_local_uptime", status="SKIP",
               expected=f"OmniLogic Local available ≥{100-INTEGRATION_FAIL_PCT_MAX}% of rows",
               severity="low",
               reason="needs omnilogic_local_last_update_success column (not in phase 1 schema)")
    return r


def assert_i2(rows, cols) -> Result:
    r = Result("I2", "midnight_burst_bounded", status="SKIP",
               expected=f"any sensor-error cluster ends by {MIDNIGHT_BURST_END}",
               severity="low",
               reason="needs error log integration; deferred")
    return r


def run_audit(rows: list[dict], cols: list[str]) -> dict:
    if not rows:
        return {"date": None, "auditor_version": AUDITOR_VERSION,
                "summary": {"passed": 0, "failed": 0, "skipped": 0},
                "assertions": [],
                "error": "no rows for date"}
    swim = is_swim_day(rows)
    results = [
        assert_d1(rows, cols),
        assert_d2(rows, cols),
        assert_d3(rows, cols),
        assert_w1(rows, cols),
        assert_w2(rows, cols, swim),
        assert_w3(rows, cols),
        assert_p1(rows, cols, swim),
        assert_p2(rows, cols, swim),
        assert_p3(rows, cols),
        assert_p4(rows, cols),
        assert_h1(rows, cols, swim),
        assert_h2(rows, cols),
        assert_h3(rows, cols),
        assert_i1(rows, cols),
        assert_i2(rows, cols),
    ]
    summary = {"passed": sum(1 for r in results if r.status == "PASS"),
               "failed": sum(1 for r in results if r.status == "FAIL"),
               "skipped": sum(1 for r in results if r.status == "SKIP")}
    return {
        "date": parse_ts(rows[0]["timestamp"]).date().isoformat(),
        "auditor_version": AUDITOR_VERSION,
        "swim_day": swim,
        "row_count": len(rows),
        "schema_columns": len(cols),
        "summary": summary,
        "assertions": [asdict(r) for r in results],
    }


def write_json(result: dict, out_dir: str, target_date: date) -> str:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = Path(out_dir) / f"pool_audit_{target_date.isoformat()}.json"
    path.write_text(json.dumps(result, indent=2, default=str))
    return str(path)


def fail_message(result: dict) -> str:
    fails = [a for a in result["assertions"] if a["status"] == "FAIL"]
    head = f"Pool Audit FAIL — {result['date']}\n{len(fails)} of {len(result['assertions'])} assertions failed:"
    body = "\n".join(f"- {a['id']} {a['name']}: {a['observed']}" for a in fails)
    return f"{head}\n{body}"


def success_message(result: dict) -> str:
    s = result["summary"]
    return (f"Pool Audit OK — {result['date']}: "
            f"{s['passed']} pass / {s['failed']} fail / {s['skipped']} skip "
            f"({result['row_count']} rows)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="YYYY-MM-DD")
    p.add_argument("--date-range", nargs=2, metavar=("START", "END"))
    p.add_argument("--csv", default=CSV_DEFAULT)
    p.add_argument("--out", default=OUT_DEFAULT)
    p.add_argument("--no-notify", action="store_true")
    p.add_argument("--success-summary", action="store_true",
                   help="push notification on PASS too")
    p.add_argument("--print", action="store_true", help="print summary to stdout")
    p.add_argument("--ha-base", default=HA_BASE,
                   help=f"HA base URL for notify pushes (default {HA_BASE})")
    p.add_argument("--token-file", default=TOKEN_FILE,
                   help=f"path to file containing HA long-lived token (default {TOKEN_FILE})")
    p.add_argument("--notify-target", default=NOTIFY_TARGET,
                   help=f"HA notify service name (default {NOTIFY_TARGET})")
    args = p.parse_args()

    if not args.date and not args.date_range:
        p.error("--date or --date-range required")

    cols, rows = load_csv(args.csv)
    targets = []
    if args.date:
        targets = [date.fromisoformat(args.date)]
    else:
        d0 = date.fromisoformat(args.date_range[0])
        d1 = date.fromisoformat(args.date_range[1])
        targets = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]

    exit_code = 0
    for d in targets:
        day_rows = filter_date(rows, d)
        result = run_audit(day_rows, cols)
        out = write_json(result, args.out, d)
        if args.print or args.no_notify:
            print(f"[{d}] {out}")
            print(json.dumps(result["summary"]), file=sys.stderr)
            for a in result["assertions"]:
                tag = {"PASS": "✓", "FAIL": "✗", "SKIP": "·"}.get(a["status"], "?")
                detail = a.get("observed") or a.get("reason") or ""
                print(f"  {tag} {a['id']} {a['name']}: {detail}")
        if not args.no_notify and result["summary"]["failed"] > 0:
            push_notify(f"Pool Audit FAIL {d}", fail_message(result),
                        args.ha_base, args.token_file, args.notify_target)
            exit_code = 1
        elif not args.no_notify and args.success_summary:
            push_notify(f"Pool Audit OK {d}", success_message(result),
                        args.ha_base, args.token_file, args.notify_target)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
