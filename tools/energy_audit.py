#!/usr/bin/env python3
"""
LRD whole-home energy daily audit.

Runs once per day after midnight rollover. Pulls yesterday's local-day
energy from HA's long-term statistics, compares against a rolling 14-day
window, and flags anomalies (unusual daily totals, baseload spikes, runaway
circuits) and opportunities (creep, persistent overnight loads, template
under-coverage).

Silent on clean. Push-notifies via notify.scott_and_ha on findings. Always
appends one CSV row per run so we build a durable trend record.

Designed to run unattended on the Mac mini at LRD via launchd, mirroring
the pool auditor pattern (see pool/scripts/audit_recent.py + ADR-021 /
ADR-006 for the broader audit architecture).

Setup
-----
  1. HA long-lived access token at ~/.ha_token (mode 600). Shared with
     pool/scripts/audit_*.sh.
  2. Mac mini Python venv: ~/.venv/zwave-health (reused — already has
     websockets installed for the Z-Wave probes).
  3. notify.scott_and_ha group deployed in HA.
  4. CSV directory: ~/energy-audit/ (created on first run).

Usage
-----
    python3 energy_audit.py [--token-file PATH]
                            [--csv-dir PATH]
                            [--days-window N]
                            [--for-date YYYY-MM-DD]
                            [--no-notify]
                            [--print-clean]
                            [--rate 0.136]

    --for-date     audit a specific local-day (default = yesterday)
    --days-window  rolling-window length for comparison (default 14)
    --print-clean  emit "all checks PASS" line for launchd log

Exit code: 0 always (silent-on-clean expected).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import statistics
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import websockets


HA_WS = "ws://192.168.50.11:8123/api/websocket"
HA_BASE = "http://192.168.50.11:8123"
NOTIFY_TARGET = "scott_and_ha"
TOKEN_FILE_DEFAULT = Path.home() / ".ha_token"
CSV_DIR_DEFAULT = Path.home() / "energy-audit"
LRD_LOCAL_OFFSET_HOURS = -4
AUDIT_VERSION = "energy-audit-1.1.0"

# Threshold knobs. Tune as the 14-day baseline evolves.
#
# Two profiles: occupied (default) and vacation (entered when
# input_boolean.vacation is on per ADR-012). Vacation thresholds reflect
# LRD summer policy: water heater off, hot-water recirc off, HVAC setpoints
# raised but humidity cycling continues, garage MS dehumidify-only, pool
# on Hayward filter-only schedule.
#
# A1/A2/A4 are rolling-average-relative; the rolling window filters to
# same-mode rows so vacation transitions don't fire false-positives.

class Thresholds:
    """Per-mode threshold set."""
    def __init__(self, **kw):
        self.daily_high_mult   = kw.get("daily_high_mult", 1.25)   # A1
        self.daily_low_mult    = kw.get("daily_low_mult", 0.60)    # A2
        self.baseload_w        = kw.get("baseload_w", 2500)        # A3
        self.always_on_mult    = kw.get("always_on_mult", 1.50)    # A4
        self.air_per_day       = kw.get("air_per_day", 40.0)       # A5
        self.pool_per_day      = kw.get("pool_per_day", 30.0)      # A6
        self.wh_per_day        = kw.get("wh_per_day", 30.0)        # A7
        self.garage_per_day    = kw.get("garage_per_day", 25.0)    # A8
        self.panel_a_unmon     = kw.get("panel_a_unmon", 0.02)     # A9
        self.panel_b_unmon     = kw.get("panel_b_unmon", 0.08)     # A9
        self.panel_a_low_kwh   = kw.get("panel_a_low_kwh", 20.0)   # A10
        self.panel_b_low_kwh   = kw.get("panel_b_low_kwh", 5.0)    # A10
        self.pool_crossval_pct = kw.get("pool_crossval_pct", 0.15) # A11
        self.enable_a10        = kw.get("enable_a10", True)
        # Vacation-only checks (None = disabled in this profile)
        self.v_wh_per_day      = kw.get("v_wh_per_day", None)      # V1
        self.v_garage_per_day  = kw.get("v_garage_per_day", None)  # V2
        self.v_whole_home_cap  = kw.get("v_whole_home_cap", None)  # V3
        self.v_pool_floor      = kw.get("v_pool_floor", None)      # V4
        self.v_cooktop_per_day = kw.get("v_cooktop_per_day", None) # V5a
        self.v_oven_per_day    = kw.get("v_oven_per_day", None)    # V5b
        self.v_stove_per_day   = kw.get("v_stove_per_day", None)   # V5c
        self.v_dryer_per_day   = kw.get("v_dryer_per_day", None)   # V6
        self.v_recirc_w_avg    = kw.get("v_recirc_w_avg", None)    # V7

# Occupied profile — current tuning from May 13-26 baseline
THR_OCCUPIED = Thresholds()

# Vacation profile — calibrated to the policy Scott confirmed 2026-05-27:
#   water heater OFF, recirc OFF, garage MS dehumidify-only,
#   pool Hayward filter-only, HVAC setpoints raised.
THR_VACATION = Thresholds(
    # Rolling-relative thresholds stay the same but operate on vacation-only rows
    daily_high_mult=1.25,
    daily_low_mult=0.60,
    # Absolute thresholds tightened or relaxed for the new baseline
    baseload_w=1200,            # A3 — overnight AC running unexpectedly
    air_per_day=15.0,           # A5 — HVAC should cycle far less
    pool_per_day=30.0,          # A6 — unchanged (pump still runs)
    wh_per_day=30.0,            # A7 — fallback; the real signal is V1
    garage_per_day=25.0,        # A8 — fallback; the real signal is V2
    enable_a10=False,           # A10 — disabled (vacation panel totals are legitimately low)
    # Vacation-only checks
    v_wh_per_day=1.0,           # V1 water heater should be off
    v_garage_per_day=8.0,       # V2 garage MS dehumidify-only ceiling
    v_whole_home_cap=80.0,      # V3 overall vacation-mode ceiling
    v_pool_floor=1.0,           # V4 stagnant-pool detector (pump unexpectedly off)
    v_cooktop_per_day=0.3,      # V5a cooktop left on
    v_oven_per_day=0.3,         # V5b wall oven left on
    v_stove_per_day=2.0,        # V5c kitchen stove has ~0.5 kWh/day standby clock; 2.0 catches cooking
    v_dryer_per_day=0.3,        # V6 dryer left running
    v_recirc_w_avg=10.0,        # V7 recirc pump mean power > 10 W (should be off)
)

# Opportunity (Monday-summary) tunables
WEEKLY_OPP_DELTA = 0.20         # O1: circuit grew >20% WoW
WEEKLY_SUPPRESS_DAYS = 14       # Suppress O1 for N days after a mode flip

# Entity sets ----------------------------------------------------------------

# Aggregate / cross-cutting (Panel totals + unmonitored + ADR-020 templates).
#
# NOTE 2026-05-27: the Carrier per-system templates `air_1_total_daily_energy`
# and `air_2_total_daily_energy` cannot be used for per-day `change` via
# `recorder/statistics_during_period` — they double-count. Each underlying
# component (condenser + handler) resets at local midnight, and HA's stats
# engine sees each underlying reset as a template reset, recording the
# pre-reset accumulated value into the change column for the period. The
# live state value is fine for real-time dashboards; only the stats-engine
# per-period change is broken. Audit sums the underlying circuits instead.
ENT_AGGREGATES = [
    "sensor.emporia_vue_panel_a_total_daily_energy",
    "sensor.emporia_vue_panel_b_total_daily_energy",
    "sensor.emporia_vue_panel_a_unmonitored_daily_energy",
    "sensor.emporia_vue_panel_b_unmonitored_daily_energy",
    "sensor.always_on_daily_energy",
]

# Top consumer circuits — these drive most of the audit checks
ENT_CIRCUITS = {
    "pool_subpanel":   "sensor.emporia_vue_panel_a_circuit_1_pool_subpanel_daily_energy",
    "refrigerator":    "sensor.emporia_vue_panel_a_circuit_2_refrigerator_daily_energy",
    "water_heater":    "sensor.emporia_vue_panel_a_circuit_3_water_heater_daily_energy",
    "air_2_handler":   "sensor.emporia_vue_panel_a_circuit_5_air_2_handler_daily_energy",
    "air_1_condenser": "sensor.emporia_vue_panel_a_circuit_9_air_1_condenser_daily_energy",
    "garage_ms":       "sensor.emporia_vue_panel_a_circuit_10_garage_mini_split_daily_energy",
    "wall_oven":       "sensor.emporia_vue_panel_a_circuit_12_wall_oven_daily_energy",
    "kitchen_stove":   "sensor.emporia_vue_panel_a_circuit_13_kitchen_stove_daily_energy",
    "network_rack":    "sensor.emporia_vue_panel_a_circuit_14_network_rack_daily_energy",
    "dryer":           "sensor.emporia_vue_panel_b_circuit_1_dryer_daily_energy",
    "cooktop":         "sensor.emporia_vue_panel_b_circuit_2_cooktop_daily_energy",
    "family_lanai":    "sensor.emporia_vue_panel_b_circuit_4_family_rm_lanai_daily_energy",
    "master_lanai":    "sensor.emporia_vue_panel_b_circuit_5_master_bed_lanai_daily_energy",
    "air_1_handler":   "sensor.emporia_vue_panel_b_circuit_9_air_1_handler_daily_energy",
    "air_2_condenser": "sensor.emporia_vue_panel_b_circuit_10_air_2_condenser_daily_energy",
}

# Power sensors for the 02:00-04:00 EDT baseload check + recirc pump (V7)
ENT_POWER_BASELOAD = "sensor.whole_home_power"
ENT_POWER_ALWAYSON = "sensor.always_on_power"
ENT_POWER_RECIRC   = "sensor.hot_water_recirc_pump_power"

# OmniLogic pool cross-validation
ENT_OMNI_PUMP_POWER = "sensor.omnilogic_pool_filter_pump_power"
ENT_POOL_POWER = "sensor.emporia_vue_panel_a_circuit_1_pool_subpanel_power"

# HA state for mode detection
ENT_VACATION_FLAG = "input_boolean.vacation"

KWH_NATIVE = {
    "sensor.whole_home_daily_energy",
    "sensor.hvac_daily_energy",
    "sensor.always_on_daily_energy",
    "sensor.pool_subpanel_daily_energy_kwh",
}


# ----------------------------------------------------------------------------
# Data classes
# ----------------------------------------------------------------------------

@dataclass
class DayMetrics:
    """One day of derived metrics, written as one CSV row."""
    audit_date: date
    vacation: int = 0                  # 0 = occupied, 1 = vacation
    whole_home_kwh: float = 0.0
    hvac_kwh: float = 0.0
    pool_kwh: float = 0.0
    water_heater_kwh: float = 0.0
    garage_ms_kwh: float = 0.0
    air_1_kwh: float = 0.0
    air_2_kwh: float = 0.0
    always_on_kwh: float = 0.0
    panel_a_kwh: float = 0.0
    panel_b_kwh: float = 0.0
    panel_a_unmon_pct: float = 0.0
    panel_b_unmon_pct: float = 0.0
    baseload_w_overnight: float = 0.0  # 02:00-04:00 EDT mean of whole_home_power
    always_on_w_overnight: float = 0.0
    recirc_w_avg: float = 0.0          # full-day mean of recirc pump power
    cooktop_kwh: float = 0.0
    wall_oven_kwh: float = 0.0
    kitchen_stove_kwh: float = 0.0
    dryer_kwh: float = 0.0
    rolling_avg_kwh: float = 0.0       # 7d avg over same-mode rows
    pool_vue_kwh: float = 0.0
    pool_omni_kwh_est: float = 0.0
    finding_count: int = 0
    findings: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def to_kwh(eid: str, value: float) -> float:
    return value if eid in KWH_NATIVE else value / 1000.0


def local_midnight_utc(local_d: date) -> datetime:
    """Return the UTC datetime corresponding to 00:00 local at LRD."""
    return datetime(local_d.year, local_d.month, local_d.day,
                    -LRD_LOCAL_OFFSET_HOURS, 0, 0, tzinfo=timezone.utc)


async def fetch_stats(
    token: str,
    entities: list[str],
    start_utc: datetime,
    end_utc: datetime,
    period: str = "hour",
    types: list[str] | None = None,
) -> dict:
    if types is None:
        types = ["sum", "state", "change", "mean"]
    async with websockets.connect(HA_WS, max_size=50_000_000) as ws:
        await ws.recv()
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


def sum_change(rows: list[dict], eid: str) -> float:
    """Sum 'change' across rows, converted to kWh."""
    return sum(to_kwh(eid, r.get("change") or 0.0) for r in rows)


def filter_local_day(rows: list[dict], target_day: date) -> list[dict]:
    """Filter hourly rows to a specific local-day at LRD."""
    out = []
    for r in rows:
        t_local = datetime.fromtimestamp(r["start"] / 1000, tz=timezone.utc) \
                    .astimezone(timezone(timedelta(hours=LRD_LOCAL_OFFSET_HOURS)))
        if t_local.date() == target_day:
            out.append(r)
    return out


def mean_in_hour_window(
    rows: list[dict], target_day: date, hours: tuple[int, int],
) -> Optional[float]:
    """Mean of 'mean' field across rows whose local hour is in [h_lo, h_hi)."""
    h_lo, h_hi = hours
    vals = []
    for r in rows:
        t_local = datetime.fromtimestamp(r["start"] / 1000, tz=timezone.utc) \
                    .astimezone(timezone(timedelta(hours=LRD_LOCAL_OFFSET_HOURS)))
        if t_local.date() == target_day and h_lo <= t_local.hour < h_hi:
            m = r.get("mean")
            if m is not None:
                vals.append(m)
    return statistics.mean(vals) if vals else None


# ----------------------------------------------------------------------------
# Notify
# ----------------------------------------------------------------------------

def push_notify(title: str, message: str, token_file: Path) -> None:
    try:
        token = token_file.read_text().strip()
    except FileNotFoundError:
        print(f"WARN: token file {token_file} missing; skipping notify",
              file=sys.stderr)
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


# ----------------------------------------------------------------------------
# CSV history
# ----------------------------------------------------------------------------

CSV_COLUMNS = [
    "audit_date", "vacation", "whole_home_kwh", "hvac_kwh", "pool_kwh",
    "water_heater_kwh", "garage_ms_kwh", "air_1_kwh", "air_2_kwh",
    "always_on_kwh", "panel_a_kwh", "panel_b_kwh", "panel_a_unmon_pct",
    "panel_b_unmon_pct", "baseload_w_overnight", "always_on_w_overnight",
    "recirc_w_avg", "cooktop_kwh", "wall_oven_kwh", "kitchen_stove_kwh",
    "dryer_kwh", "rolling_avg_kwh", "pool_vue_kwh", "pool_omni_kwh_est",
    "finding_count", "findings", "audit_version",
]


def migrate_csv_schema(csv_path: Path) -> None:
    """Add missing columns to an older-schema CSV in place.

    v1.0.0 → v1.1.0 added: vacation, recirc_w_avg, cooktop_kwh, wall_oven_kwh,
    kitchen_stove_kwh, dryer_kwh. Old rows fill the new columns with 0/0.0.

    Detection: read the header row. If it doesn't match CSV_COLUMNS, migrate.
    """
    if not csv_path.exists():
        return
    with csv_path.open() as f:
        rdr = csv.reader(f)
        try:
            header = next(rdr)
        except StopIteration:
            return
        if header == CSV_COLUMNS:
            return
        old_rows = list(csv.DictReader(open(csv_path)))
    # Backup the old file before rewriting
    backup = csv_path.with_suffix(csv_path.suffix + ".pre-v1.1.0.bak")
    if not backup.exists():
        backup.write_text(csv_path.read_text())
    # Defaults for new columns
    defaults = {c: "0" for c in CSV_COLUMNS}
    defaults["audit_date"] = ""
    defaults["findings"] = ""
    defaults["audit_version"] = "energy-audit-1.0.0-migrated"
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for row in old_rows:
            out = []
            for col in CSV_COLUMNS:
                out.append(row.get(col, defaults[col]))
            w.writerow(out)


def append_csv(csv_dir: Path, m: DayMetrics) -> Path:
    csv_dir.mkdir(parents=True, exist_ok=True)
    csv_path = csv_dir / "energy_audit.csv"
    migrate_csv_schema(csv_path)
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(CSV_COLUMNS)
        w.writerow([
            m.audit_date.isoformat(), m.vacation,
            f"{m.whole_home_kwh:.2f}", f"{m.hvac_kwh:.2f}", f"{m.pool_kwh:.2f}",
            f"{m.water_heater_kwh:.2f}", f"{m.garage_ms_kwh:.2f}",
            f"{m.air_1_kwh:.2f}", f"{m.air_2_kwh:.2f}", f"{m.always_on_kwh:.2f}",
            f"{m.panel_a_kwh:.2f}", f"{m.panel_b_kwh:.2f}",
            f"{m.panel_a_unmon_pct:.4f}", f"{m.panel_b_unmon_pct:.4f}",
            f"{m.baseload_w_overnight:.0f}", f"{m.always_on_w_overnight:.0f}",
            f"{m.recirc_w_avg:.0f}",
            f"{m.cooktop_kwh:.2f}", f"{m.wall_oven_kwh:.2f}",
            f"{m.kitchen_stove_kwh:.2f}", f"{m.dryer_kwh:.2f}",
            f"{m.rolling_avg_kwh:.2f}",
            f"{m.pool_vue_kwh:.2f}", f"{m.pool_omni_kwh_est:.2f}",
            m.finding_count, " | ".join(m.findings),
            AUDIT_VERSION,
        ])
    return csv_path


def load_prior_audit_rows(
    csv_dir: Path, days_window: int, vacation_filter: int | None = None,
) -> list[dict]:
    """Load the last N days of audit rows for rolling comparisons.

    If vacation_filter is set (0 or 1), only return rows matching that mode.
    Returns the most recent N matching rows.
    """
    csv_path = csv_dir / "energy_audit.csv"
    if not csv_path.exists():
        return []
    with csv_path.open() as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
    if vacation_filter is not None:
        # Tolerate older rows without the vacation column (treat as occupied).
        rows = [r for r in rows if int(r.get("vacation", 0) or 0) == vacation_filter]
    return rows[-days_window:]


def fetch_state(entity_id: str, token_file: Path) -> Optional[str]:
    """Read a single entity state via /api/states. None on failure."""
    try:
        token = token_file.read_text().strip()
    except FileNotFoundError:
        return None
    req = urllib.request.Request(
        f"{HA_BASE}/api/states/{entity_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read()).get("state")
    except (urllib.error.HTTPError, urllib.error.URLError,
            TimeoutError, json.JSONDecodeError):
        return None


# ----------------------------------------------------------------------------
# Audit logic
# ----------------------------------------------------------------------------

def run_audit(
    token: str,
    target_day: date,
    days_window: int,
    csv_dir: Path,
    rate: float,
    vacation: int,
    token_file: Path,
    notify_mode_flip: bool = True,
) -> DayMetrics:
    """Pull stats and compute metrics + findings for target_day."""

    # Window: target_day - days_window through target_day inclusive (hourly).
    start_local = target_day - timedelta(days=days_window)
    end_local = target_day + timedelta(days=1)
    start_utc = local_midnight_utc(start_local)
    end_utc = local_midnight_utc(end_local)

    # Energy entities (need 'change')
    energy_ents = list(ENT_AGGREGATES) + list(ENT_CIRCUITS.values())
    energy_stats = asyncio.run(fetch_stats(
        token, energy_ents, start_utc, end_utc, period="hour",
        types=["change"],
    ))

    # Power entities (need 'mean') — separate query, smaller payload
    power_ents = [ENT_POWER_BASELOAD, ENT_POWER_ALWAYSON, ENT_POWER_RECIRC,
                  ENT_OMNI_PUMP_POWER, ENT_POOL_POWER]
    power_stats = asyncio.run(fetch_stats(
        token, power_ents, start_utc, end_utc, period="hour",
        types=["mean"],
    ))

    m = DayMetrics(audit_date=target_day, vacation=vacation)
    thr = THR_VACATION if vacation else THR_OCCUPIED

    # ---- Daily kWh per circuit / aggregate ----
    def get_day_kwh(eid: str) -> float:
        rows = energy_stats.get(eid, [])
        rows_today = filter_local_day(rows, target_day)
        return sum_change(rows_today, eid)

    m.panel_a_kwh = get_day_kwh("sensor.emporia_vue_panel_a_total_daily_energy")
    m.panel_b_kwh = get_day_kwh("sensor.emporia_vue_panel_b_total_daily_energy")
    m.whole_home_kwh = m.panel_a_kwh + m.panel_b_kwh

    # Sum the underlying Vue circuits — do NOT use the air_X_total_daily_energy
    # templates here (see NOTE on ENT_AGGREGATES above; they double-count via
    # recorder/statistics_during_period).
    m.air_1_kwh = (
        get_day_kwh(ENT_CIRCUITS["air_1_condenser"])
        + get_day_kwh(ENT_CIRCUITS["air_1_handler"])
    )
    m.air_2_kwh = (
        get_day_kwh(ENT_CIRCUITS["air_2_condenser"])
        + get_day_kwh(ENT_CIRCUITS["air_2_handler"])
    )
    m.garage_ms_kwh = get_day_kwh(ENT_CIRCUITS["garage_ms"])
    m.hvac_kwh = m.air_1_kwh + m.air_2_kwh + m.garage_ms_kwh

    m.pool_kwh = get_day_kwh(ENT_CIRCUITS["pool_subpanel"])
    m.water_heater_kwh = get_day_kwh(ENT_CIRCUITS["water_heater"])
    m.always_on_kwh = get_day_kwh("sensor.always_on_daily_energy")
    m.pool_vue_kwh = m.pool_kwh  # alias for cross-val column

    # Cooking + dryer circuits (used by V5/V6 in vacation mode)
    m.cooktop_kwh = get_day_kwh(ENT_CIRCUITS["cooktop"])
    m.wall_oven_kwh = get_day_kwh(ENT_CIRCUITS["wall_oven"])
    m.kitchen_stove_kwh = get_day_kwh(ENT_CIRCUITS["kitchen_stove"])
    m.dryer_kwh = get_day_kwh(ENT_CIRCUITS["dryer"])

    panel_a_unmon = get_day_kwh("sensor.emporia_vue_panel_a_unmonitored_daily_energy")
    panel_b_unmon = get_day_kwh("sensor.emporia_vue_panel_b_unmonitored_daily_energy")
    m.panel_a_unmon_pct = panel_a_unmon / m.panel_a_kwh if m.panel_a_kwh else 0
    m.panel_b_unmon_pct = panel_b_unmon / m.panel_b_kwh if m.panel_b_kwh else 0

    # ---- Overnight power means (02:00-04:00 EDT) + recirc full-day mean ----
    wh_pwr = power_stats.get(ENT_POWER_BASELOAD, [])
    ao_pwr = power_stats.get(ENT_POWER_ALWAYSON, [])
    bl = mean_in_hour_window(wh_pwr, target_day, (2, 4))
    ao = mean_in_hour_window(ao_pwr, target_day, (2, 4))
    m.baseload_w_overnight = bl or 0.0
    m.always_on_w_overnight = ao or 0.0

    # Recirc pump: full-day mean (no hour window, V7 catches any sustained draw)
    recirc_rows = filter_local_day(power_stats.get(ENT_POWER_RECIRC, []), target_day)
    recirc_means = [r.get("mean") for r in recirc_rows if r.get("mean") is not None]
    m.recirc_w_avg = statistics.mean(recirc_means) if recirc_means else 0.0

    # ---- OmniLogic cross-val (estimate kWh as mean_power_W × 24h / 1000) ----
    omni_pwr_rows = filter_local_day(power_stats.get(ENT_OMNI_PUMP_POWER, []), target_day)
    omni_means = [r.get("mean") for r in omni_pwr_rows if r.get("mean") is not None]
    omni_avg_w = statistics.mean(omni_means) if omni_means else 0.0
    m.pool_omni_kwh_est = omni_avg_w * 24 / 1000.0

    # ---- Rolling 7-day avg over same-mode rows only ----
    # This filters out the noisy transition week when vacation mode flips:
    # an occupied-mode day's baseline doesn't include vacation-mode rows,
    # and vice versa.
    prior_rows = load_prior_audit_rows(csv_dir, days_window=7, vacation_filter=vacation)
    prior_whs = [float(r["whole_home_kwh"]) for r in prior_rows
                 if float(r["whole_home_kwh"]) > 1.0]
    m.rolling_avg_kwh = statistics.mean(prior_whs) if prior_whs else 0.0

    # ---- Findings ----
    findings = []

    # Mode-flip detection (any-mode prior row, not filtered)
    last_any = load_prior_audit_rows(csv_dir, days_window=1, vacation_filter=None)
    if last_any:
        prev_vac = int(last_any[-1].get("vacation", 0) or 0)
        if prev_vac != vacation:
            label = "ON (away)" if vacation else "OFF (home)"
            findings.append(
                f"[MODE] vacation flipped {prev_vac}→{vacation} ({label}). "
                f"Switching to {'vacation' if vacation else 'occupied'} threshold profile. "
                f"Rolling baselines reset to same-mode rows only."
            )

    # A1 — daily total high (skip if fewer than 3 same-mode baseline rows)
    if m.rolling_avg_kwh > 0 and len(prior_whs) >= 3 \
       and m.whole_home_kwh > m.rolling_avg_kwh * thr.daily_high_mult:
        findings.append(
            f"[A1] daily total {m.whole_home_kwh:.1f} kWh > "
            f"{thr.daily_high_mult}× 7d avg ({m.rolling_avg_kwh:.1f} kWh) — "
            f"${(m.whole_home_kwh - m.rolling_avg_kwh) * rate:.2f} above baseline"
        )

    # A2 — daily total low (data loss / device offline)
    if m.rolling_avg_kwh > 0 and len(prior_whs) >= 3 \
       and m.whole_home_kwh < m.rolling_avg_kwh * thr.daily_low_mult:
        findings.append(
            f"[A2] daily total {m.whole_home_kwh:.1f} kWh < "
            f"{thr.daily_low_mult}× 7d avg ({m.rolling_avg_kwh:.1f} kWh) — "
            f"likely Vue panel offline or recorder gap"
        )

    # A3 — overnight baseload spike
    if m.baseload_w_overnight > thr.baseload_w:
        findings.append(
            f"[A3] overnight baseload {m.baseload_w_overnight:.0f} W "
            f"(02:00-04:00 EDT mean) > {thr.baseload_w} W threshold"
        )

    # A4 — always-on creep (same-mode median; skip if <5 rows)
    prior_ao = [float(r["always_on_w_overnight"]) for r in prior_rows
                if float(r["always_on_w_overnight"]) > 50]
    if len(prior_ao) >= 5:
        med_ao = statistics.median(prior_ao)
        if m.always_on_w_overnight > med_ao * thr.always_on_mult:
            findings.append(
                f"[A4] always-on baseload {m.always_on_w_overnight:.0f} W > "
                f"{thr.always_on_mult}× 7d median ({med_ao:.0f} W) — possible new standby load"
            )

    # A5/A8 — HVAC system runaway (each system)
    for label, kwh, limit in [
        ("Air 1", m.air_1_kwh, thr.air_per_day),
        ("Air 2", m.air_2_kwh, thr.air_per_day),
        ("Garage MS", m.garage_ms_kwh, thr.garage_per_day),
    ]:
        if kwh > limit:
            findings.append(
                f"[A5/A8] {label} {kwh:.1f} kWh > {limit:.0f} kWh/day threshold"
            )

    # A6 — pool subpanel high
    if m.pool_kwh > thr.pool_per_day:
        findings.append(
            f"[A6] pool subpanel {m.pool_kwh:.1f} kWh > {thr.pool_per_day:.0f} kWh — "
            f"heater runaway or pump stuck at high speed?"
        )

    # A7 — water heater high (occupied-mode signal; V1 covers vacation)
    if m.water_heater_kwh > thr.wh_per_day:
        findings.append(
            f"[A7] water heater {m.water_heater_kwh:.1f} kWh > {thr.wh_per_day:.0f} kWh — "
            f"element stuck on / thermostat drift / recirc fault?"
        )

    # A9 — unmonitored % out of range
    if m.panel_a_unmon_pct > thr.panel_a_unmon:
        findings.append(
            f"[A9] Panel A unmonitored {m.panel_a_unmon_pct * 100:.1f}% > "
            f"{thr.panel_a_unmon * 100:.0f}% — CT slip or new load not yet CT'd"
        )
    if m.panel_b_unmon_pct > thr.panel_b_unmon:
        findings.append(
            f"[A9] Panel B unmonitored {m.panel_b_unmon_pct * 100:.1f}% > "
            f"{thr.panel_b_unmon * 100:.0f}% — CT slip or new load not yet CT'd"
        )

    # A10 — panel total suspiciously low (disabled in vacation profile —
    # vacation panel totals can legitimately drop into the teens)
    if thr.enable_a10:
        if m.panel_a_kwh < thr.panel_a_low_kwh:
            findings.append(
                f"[A10] Panel A total {m.panel_a_kwh:.1f} kWh — Vue Panel A may be offline"
            )
        if m.panel_b_kwh < thr.panel_b_low_kwh:
            findings.append(
                f"[A10] Panel B total {m.panel_b_kwh:.1f} kWh — Vue Panel B may be offline"
            )

    # A11 — pool Vue vs OmniLogic cross-val
    if m.pool_omni_kwh_est > 1.0 and m.pool_vue_kwh > 1.0:
        if m.pool_omni_kwh_est > m.pool_vue_kwh * (1 + thr.pool_crossval_pct):
            findings.append(
                f"[A11] OmniLogic pump est ({m.pool_omni_kwh_est:.1f} kWh) > "
                f"Vue pool subpanel ({m.pool_vue_kwh:.1f} kWh) — CT polarity or Vue offline?"
            )

    # ---- Vacation-only checks (V1-V7) ----
    if vacation:
        if thr.v_wh_per_day is not None and m.water_heater_kwh > thr.v_wh_per_day:
            findings.append(
                f"[V1] water heater {m.water_heater_kwh:.2f} kWh — should be off in vacation "
                f"(threshold {thr.v_wh_per_day:.1f} kWh)"
            )
        if thr.v_garage_per_day is not None and m.garage_ms_kwh > thr.v_garage_per_day:
            findings.append(
                f"[V2] garage MS {m.garage_ms_kwh:.1f} kWh > {thr.v_garage_per_day:.1f} kWh — "
                f"running above dehumidify-only expectation"
            )
        if thr.v_whole_home_cap is not None and m.whole_home_kwh > thr.v_whole_home_cap:
            findings.append(
                f"[V3] whole-home {m.whole_home_kwh:.1f} kWh > {thr.v_whole_home_cap:.1f} kWh "
                f"vacation ceiling — vacation mode may not be fully engaged"
            )
        if thr.v_pool_floor is not None and m.pool_kwh < thr.v_pool_floor:
            findings.append(
                f"[V4] pool subpanel only {m.pool_kwh:.2f} kWh — filter pump may be off, "
                f"stagnant-pool risk (Hayward filter-only schedule expected)"
            )
        if thr.v_cooktop_per_day is not None and m.cooktop_kwh > thr.v_cooktop_per_day:
            findings.append(
                f"[V5] cooktop {m.cooktop_kwh:.2f} kWh — burner left on?"
            )
        if thr.v_oven_per_day is not None and m.wall_oven_kwh > thr.v_oven_per_day:
            findings.append(
                f"[V5] wall oven {m.wall_oven_kwh:.2f} kWh — oven left on?"
            )
        if thr.v_stove_per_day is not None and m.kitchen_stove_kwh > thr.v_stove_per_day:
            findings.append(
                f"[V5] kitchen stove {m.kitchen_stove_kwh:.2f} kWh > "
                f"{thr.v_stove_per_day:.1f} kWh (excludes ~0.5 kWh/day clock standby)"
            )
        if thr.v_dryer_per_day is not None and m.dryer_kwh > thr.v_dryer_per_day:
            findings.append(
                f"[V6] dryer {m.dryer_kwh:.2f} kWh — dryer ran in vacation?"
            )
        if thr.v_recirc_w_avg is not None and m.recirc_w_avg > thr.v_recirc_w_avg:
            findings.append(
                f"[V7] hot water recirc pump avg {m.recirc_w_avg:.0f} W — should be off"
            )

    # ---- Monday opportunity scan (weekly summary) ----
    # Suppress for WEEKLY_SUPPRESS_DAYS days after a mode flip — WoW deltas
    # across modes are meaningless.
    days_since_flip = days_since_mode_flip(csv_dir, vacation)
    if target_day.weekday() == 0 and days_since_flip >= WEEKLY_SUPPRESS_DAYS:
        opp = scan_opportunities(prior_rows, m, rate)
        if opp:
            findings.extend(opp)

    m.findings = findings
    m.finding_count = len(findings)
    return m


def days_since_mode_flip(csv_dir: Path, current_vacation: int) -> int:
    """Count consecutive prior days with the same vacation flag as today.

    Returns 999 if no prior rows, OR if the entire history is in the same
    mode as today (no flip has occurred — treat as long-stable).
    Otherwise returns the run length since the most recent flip.
    """
    csv_path = csv_dir / "energy_audit.csv"
    if not csv_path.exists():
        return 999
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return 999
    n = 0
    saw_other_mode = False
    for r in reversed(rows):
        if int(r.get("vacation", 0) or 0) == current_vacation:
            if saw_other_mode:
                break
            n += 1
        else:
            saw_other_mode = True
            break
    return n if saw_other_mode else 999


def scan_opportunities(prior_rows: list[dict], today: DayMetrics, rate: float) -> list[str]:
    """Monday: scan for week-over-week creep + persistent patterns."""
    out = []
    if len(prior_rows) < 7:
        return out

    # Most recent 7 vs prior 7 for whole-home, garage MS, water heater
    def avg(rows, col):
        vals = [float(r[col]) for r in rows if float(r[col]) > 0.1]
        return statistics.mean(vals) if vals else 0.0

    last7 = prior_rows[-7:]
    prev7 = prior_rows[-14:-7] if len(prior_rows) >= 14 else []

    for col, label, threshold_pct in [
        ("whole_home_kwh", "Whole home", WEEKLY_OPP_DELTA),
        ("garage_ms_kwh", "Garage mini split", WEEKLY_OPP_DELTA),
        ("water_heater_kwh", "Water heater", WEEKLY_OPP_DELTA),
        ("pool_kwh", "Pool subpanel", WEEKLY_OPP_DELTA),
        ("hvac_kwh", "HVAC total", WEEKLY_OPP_DELTA),
    ]:
        a = avg(last7, col)
        b = avg(prev7, col)
        if b > 1.0:
            delta = (a - b) / b
            if abs(delta) > threshold_pct:
                arrow = "↑" if delta > 0 else "↓"
                cost = (a - b) * 7 * rate
                out.append(
                    f"[O1] {label} {arrow} {delta * 100:+.0f}% WoW "
                    f"({b:.1f} → {a:.1f} kWh/day, ${cost:+.2f}/week)"
                )

    # O3: always-on template under-coverage
    if today.baseload_w_overnight > 0 and today.always_on_w_overnight > 0:
        non_hvac_baseload = today.baseload_w_overnight - today.always_on_w_overnight
        # If the gap is >800 W and that gap isn't HVAC (rough check via today's pool kWh)
        if non_hvac_baseload > 800:
            out.append(
                f"[O3] non-HVAC, non-template baseload ~{non_hvac_baseload:.0f} W — "
                f"always-on template likely under-counts; review packages/energy/templates.yaml"
            )

    return out


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--token-file", type=Path, default=TOKEN_FILE_DEFAULT)
    parser.add_argument("--csv-dir", type=Path, default=CSV_DIR_DEFAULT)
    parser.add_argument("--days-window", type=int, default=14)
    parser.add_argument("--for-date", type=str, default=None,
                        help="YYYY-MM-DD local-day (default = yesterday LRD-EDT)")
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--print-clean", action="store_true")
    parser.add_argument("--rate", type=float, default=0.136)
    parser.add_argument(
        "--vacation-override", choices=["on", "off"], default=None,
        help=(
            "Force a specific mode (e.g. for backfill or what-if). Default reads "
            "input_boolean.vacation from HA. Backfill historical days that were "
            "occupied with --vacation-override=off."
        ),
    )
    args = parser.parse_args()

    try:
        token = args.token_file.read_text().strip()
    except FileNotFoundError:
        print(f"ERROR: token file {args.token_file} missing", file=sys.stderr)
        return 0  # silent

    # Default target = yesterday in LRD-local
    if args.for_date:
        target_day = date.fromisoformat(args.for_date)
    else:
        now_local = datetime.now(timezone.utc) + timedelta(hours=LRD_LOCAL_OFFSET_HOURS)
        target_day = (now_local - timedelta(days=1)).date()

    # Vacation flag — CLI override wins; otherwise read live HA state. Failure
    # to fetch is treated as 'occupied' (conservative — we'd rather notify
    # spuriously than silently use vacation-mode tighter thresholds).
    if args.vacation_override is not None:
        vacation = 1 if args.vacation_override == "on" else 0
    else:
        state = fetch_state(ENT_VACATION_FLAG, args.token_file)
        vacation = 1 if state == "on" else 0

    try:
        m = run_audit(token, target_day, args.days_window, args.csv_dir,
                      args.rate, vacation, args.token_file)
    except Exception as e:
        print(f"ERROR: audit failed: {e}", file=sys.stderr)
        # Still notify on hard failures — this is a meta-audit signal
        if not args.no_notify:
            push_notify(
                "Energy audit: hard error",
                f"Audit run for {target_day} crashed: {e}\nCheck launchd log on Mac mini.",
                args.token_file,
            )
        return 0

    csv_path = append_csv(args.csv_dir, m)

    # --- Stdout report ---
    now_iso = datetime.now().isoformat(timespec="seconds")
    mode = "vacation" if vacation else "occupied"
    if not m.findings:
        if args.print_clean:
            print(
                f"[{now_iso}] energy-audit {target_day} [{mode}]: "
                f"WH {m.whole_home_kwh:.1f} kWh (${m.whole_home_kwh * args.rate:.2f}), "
                f"baseload {m.baseload_w_overnight:.0f} W — all checks PASS"
            )
        return 0

    # Findings — log to stdout (launchd captures), notify push
    title = f"Energy audit {target_day} [{mode}]: {m.finding_count} finding(s)"
    summary_line = (
        f"WH {m.whole_home_kwh:.1f} kWh (${m.whole_home_kwh * args.rate:.2f}), "
        f"7d avg {m.rolling_avg_kwh:.1f}, baseload {m.baseload_w_overnight:.0f} W"
    )
    body = summary_line + "\n\n" + "\n\n".join(m.findings)
    body += f"\n\nCSV: {csv_path}\nVersion: {AUDIT_VERSION}"

    print(f"[{now_iso}] {title}")
    print(body)

    if not args.no_notify:
        push_notify(title, body, args.token_file)

    return 0


if __name__ == "__main__":
    sys.exit(main())
