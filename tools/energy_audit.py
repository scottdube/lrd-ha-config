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
AUDIT_VERSION = "energy-audit-1.0.0"

# Threshold knobs. Tune as the 14-day baseline evolves.
THR_DAILY_HIGH_MULT = 1.25      # A1: daily total > 1.25 × 7d rolling avg
THR_DAILY_LOW_MULT  = 0.60      # A2: daily total < 0.6 × 7d rolling avg (data loss)
THR_BASELOAD_W      = 2500      # A3: 02:00-04:00 EDT mean > 2500 W
THR_ALWAYS_ON_MULT  = 1.50      # A4: always-on > 1.5 × 7d median
THR_HVAC_PER_DAY    = 40.0      # A5: any one HVAC system > 40 kWh/day
THR_POOL_PER_DAY    = 30.0      # A6: pool subpanel > 30 kWh/day
THR_WH_PER_DAY      = 30.0      # A7: water heater > 30 kWh/day
THR_GARAGE_PER_DAY  = 25.0      # A8: garage mini split > 25 kWh/day
THR_PANEL_A_UNMON   = 0.02      # A9: Panel A unmonitored > 2%
THR_PANEL_B_UNMON   = 0.08      # A9: Panel B unmonitored > 8%
THR_POOL_CROSSVAL_PCT = 0.15    # A11: Vue vs OmniLogic daily delta > 15%

# Opportunity (Monday-summary) tunables
WEEKLY_OPP_DELTA = 0.20         # O1: circuit grew >20% WoW

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
    "network_rack":    "sensor.emporia_vue_panel_a_circuit_14_network_rack_daily_energy",
    "dryer":           "sensor.emporia_vue_panel_b_circuit_1_dryer_daily_energy",
    "family_lanai":    "sensor.emporia_vue_panel_b_circuit_4_family_rm_lanai_daily_energy",
    "master_lanai":    "sensor.emporia_vue_panel_b_circuit_5_master_bed_lanai_daily_energy",
    "air_1_handler":   "sensor.emporia_vue_panel_b_circuit_9_air_1_handler_daily_energy",
    "air_2_condenser": "sensor.emporia_vue_panel_b_circuit_10_air_2_condenser_daily_energy",
}

# Power sensors for the 02:00-04:00 EDT baseload check
ENT_POWER_BASELOAD = "sensor.whole_home_power"
ENT_POWER_ALWAYSON = "sensor.always_on_power"

# OmniLogic pool cross-validation
ENT_OMNI_PUMP_POWER = "sensor.omnilogic_pool_filter_pump_power"
ENT_POOL_POWER = "sensor.emporia_vue_panel_a_circuit_1_pool_subpanel_power"

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
    rolling_avg_kwh: float = 0.0
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
    "audit_date", "whole_home_kwh", "hvac_kwh", "pool_kwh", "water_heater_kwh",
    "garage_ms_kwh", "air_1_kwh", "air_2_kwh", "always_on_kwh",
    "panel_a_kwh", "panel_b_kwh", "panel_a_unmon_pct", "panel_b_unmon_pct",
    "baseload_w_overnight", "always_on_w_overnight", "rolling_avg_kwh",
    "pool_vue_kwh", "pool_omni_kwh_est", "finding_count", "findings",
    "audit_version",
]


def append_csv(csv_dir: Path, m: DayMetrics) -> Path:
    csv_dir.mkdir(parents=True, exist_ok=True)
    csv_path = csv_dir / "energy_audit.csv"
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(CSV_COLUMNS)
        w.writerow([
            m.audit_date.isoformat(),
            f"{m.whole_home_kwh:.2f}", f"{m.hvac_kwh:.2f}", f"{m.pool_kwh:.2f}",
            f"{m.water_heater_kwh:.2f}", f"{m.garage_ms_kwh:.2f}",
            f"{m.air_1_kwh:.2f}", f"{m.air_2_kwh:.2f}", f"{m.always_on_kwh:.2f}",
            f"{m.panel_a_kwh:.2f}", f"{m.panel_b_kwh:.2f}",
            f"{m.panel_a_unmon_pct:.4f}", f"{m.panel_b_unmon_pct:.4f}",
            f"{m.baseload_w_overnight:.0f}", f"{m.always_on_w_overnight:.0f}",
            f"{m.rolling_avg_kwh:.2f}",
            f"{m.pool_vue_kwh:.2f}", f"{m.pool_omni_kwh_est:.2f}",
            m.finding_count, " | ".join(m.findings),
            AUDIT_VERSION,
        ])
    return csv_path


def load_prior_audit_rows(csv_dir: Path, days_window: int) -> list[dict]:
    """Load the last N days of audit rows for rolling comparisons."""
    csv_path = csv_dir / "energy_audit.csv"
    if not csv_path.exists():
        return []
    with csv_path.open() as f:
        rdr = csv.DictReader(f)
        return list(rdr)[-days_window:]


# ----------------------------------------------------------------------------
# Audit logic
# ----------------------------------------------------------------------------

def run_audit(
    token: str,
    target_day: date,
    days_window: int,
    csv_dir: Path,
    rate: float,
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
    power_ents = [ENT_POWER_BASELOAD, ENT_POWER_ALWAYSON,
                  ENT_OMNI_PUMP_POWER, ENT_POOL_POWER]
    power_stats = asyncio.run(fetch_stats(
        token, power_ents, start_utc, end_utc, period="hour",
        types=["mean"],
    ))

    m = DayMetrics(audit_date=target_day)

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

    panel_a_unmon = get_day_kwh("sensor.emporia_vue_panel_a_unmonitored_daily_energy")
    panel_b_unmon = get_day_kwh("sensor.emporia_vue_panel_b_unmonitored_daily_energy")
    m.panel_a_unmon_pct = panel_a_unmon / m.panel_a_kwh if m.panel_a_kwh else 0
    m.panel_b_unmon_pct = panel_b_unmon / m.panel_b_kwh if m.panel_b_kwh else 0

    # ---- Overnight power means (02:00-04:00 EDT) ----
    wh_pwr = power_stats.get(ENT_POWER_BASELOAD, [])
    ao_pwr = power_stats.get(ENT_POWER_ALWAYSON, [])
    bl = mean_in_hour_window(wh_pwr, target_day, (2, 4))
    ao = mean_in_hour_window(ao_pwr, target_day, (2, 4))
    m.baseload_w_overnight = bl or 0.0
    m.always_on_w_overnight = ao or 0.0

    # ---- OmniLogic cross-val (estimate kWh as mean_power_W × 24h / 1000) ----
    omni_pwr_rows = filter_local_day(power_stats.get(ENT_OMNI_PUMP_POWER, []), target_day)
    omni_means = [r.get("mean") for r in omni_pwr_rows if r.get("mean") is not None]
    omni_avg_w = statistics.mean(omni_means) if omni_means else 0.0
    m.pool_omni_kwh_est = omni_avg_w * 24 / 1000.0

    # ---- Rolling 7-day avg of whole_home_kwh from prior audit rows ----
    prior_rows = load_prior_audit_rows(csv_dir, days_window=7)
    prior_whs = [float(r["whole_home_kwh"]) for r in prior_rows
                 if float(r["whole_home_kwh"]) > 50]
    m.rolling_avg_kwh = statistics.mean(prior_whs) if prior_whs else 0.0

    # ---- Findings ----
    findings = []

    # A1 — daily total high
    if m.rolling_avg_kwh > 0 and m.whole_home_kwh > m.rolling_avg_kwh * THR_DAILY_HIGH_MULT:
        findings.append(
            f"[A1] daily total {m.whole_home_kwh:.1f} kWh > "
            f"{THR_DAILY_HIGH_MULT}× 7d avg ({m.rolling_avg_kwh:.1f} kWh) — "
            f"${(m.whole_home_kwh - m.rolling_avg_kwh) * rate:.2f} above baseline"
        )

    # A2 — daily total low (data loss / device offline)
    if m.rolling_avg_kwh > 0 and m.whole_home_kwh < m.rolling_avg_kwh * THR_DAILY_LOW_MULT:
        findings.append(
            f"[A2] daily total {m.whole_home_kwh:.1f} kWh < "
            f"{THR_DAILY_LOW_MULT}× 7d avg ({m.rolling_avg_kwh:.1f} kWh) — "
            f"likely Vue panel offline or recorder gap"
        )

    # A3 — overnight baseload spike
    if m.baseload_w_overnight > THR_BASELOAD_W:
        findings.append(
            f"[A3] overnight baseload {m.baseload_w_overnight:.0f} W "
            f"(02:00-04:00 EDT mean) > {THR_BASELOAD_W} W threshold"
        )

    # A4 — always-on creep
    prior_ao = [float(r["always_on_w_overnight"]) for r in prior_rows
                if float(r["always_on_w_overnight"]) > 50]
    if prior_ao:
        med_ao = statistics.median(prior_ao)
        if m.always_on_w_overnight > med_ao * THR_ALWAYS_ON_MULT:
            findings.append(
                f"[A4] always-on baseload {m.always_on_w_overnight:.0f} W > "
                f"{THR_ALWAYS_ON_MULT}× 7d median ({med_ao:.0f} W) — possible new standby load"
            )

    # A5 — HVAC system runaway (each system)
    for label, kwh in [("Air 1", m.air_1_kwh), ("Air 2", m.air_2_kwh),
                       ("Garage MS", m.garage_ms_kwh)]:
        limit = THR_HVAC_PER_DAY if label != "Garage MS" else THR_GARAGE_PER_DAY
        if kwh > limit:
            findings.append(
                f"[A5/A8] {label} {kwh:.1f} kWh > {limit:.0f} kWh/day threshold"
            )

    # A6 — pool subpanel high
    if m.pool_kwh > THR_POOL_PER_DAY:
        findings.append(
            f"[A6] pool subpanel {m.pool_kwh:.1f} kWh > {THR_POOL_PER_DAY:.0f} kWh — "
            f"heater runaway or pump stuck at high speed?"
        )

    # A7 — water heater high
    if m.water_heater_kwh > THR_WH_PER_DAY:
        findings.append(
            f"[A7] water heater {m.water_heater_kwh:.1f} kWh > {THR_WH_PER_DAY:.0f} kWh — "
            f"element stuck on / thermostat drift / recirc fault?"
        )

    # A9 — unmonitored % out of range
    if m.panel_a_unmon_pct > THR_PANEL_A_UNMON:
        findings.append(
            f"[A9] Panel A unmonitored {m.panel_a_unmon_pct * 100:.1f}% > "
            f"{THR_PANEL_A_UNMON * 100:.0f}% — CT slip or new load not yet CT'd"
        )
    if m.panel_b_unmon_pct > THR_PANEL_B_UNMON:
        findings.append(
            f"[A9] Panel B unmonitored {m.panel_b_unmon_pct * 100:.1f}% > "
            f"{THR_PANEL_B_UNMON * 100:.0f}% — CT slip or new load not yet CT'd"
        )

    # A10 — data freshness: any aggregate or circuit at 0 kWh on a non-vacation day
    # is suspicious (only flag the panel totals + Vue circuits we expect to move daily)
    if m.panel_a_kwh < 20:
        findings.append(
            f"[A10] Panel A total {m.panel_a_kwh:.1f} kWh — Vue Panel A may be offline"
        )
    if m.panel_b_kwh < 5:
        findings.append(
            f"[A10] Panel B total {m.panel_b_kwh:.1f} kWh — Vue Panel B may be offline"
        )

    # A11 — pool Vue vs OmniLogic cross-val
    if m.pool_omni_kwh_est > 1.0 and m.pool_vue_kwh > 1.0:
        # OmniLogic only measures the filter pump; Vue measures the whole subpanel
        # (pump + heater + lights + booster). Vue >= OmniLogic always. Flag if Vue
        # is *less* than OmniLogic (sensor problem) or if pump-on-only delta is
        # extreme. Use a soft threshold: if OmniLogic > Vue, that's a bug.
        if m.pool_omni_kwh_est > m.pool_vue_kwh * (1 + THR_POOL_CROSSVAL_PCT):
            findings.append(
                f"[A11] OmniLogic pump est ({m.pool_omni_kwh_est:.1f} kWh) > "
                f"Vue pool subpanel ({m.pool_vue_kwh:.1f} kWh) — CT polarity or Vue offline?"
            )

    # ---- Monday opportunity scan (weekly summary) ----
    if target_day.weekday() == 0:  # Monday — review prior 7 vs prior 14
        opp = scan_opportunities(prior_rows, m, rate)
        if opp:
            findings.extend(opp)

    m.findings = findings
    m.finding_count = len(findings)
    return m


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

    try:
        m = run_audit(token, target_day, args.days_window, args.csv_dir, args.rate)
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
    if not m.findings:
        if args.print_clean:
            print(
                f"[{now_iso}] energy-audit {target_day}: "
                f"WH {m.whole_home_kwh:.1f} kWh (${m.whole_home_kwh * args.rate:.2f}), "
                f"baseload {m.baseload_w_overnight:.0f} W — all checks PASS"
            )
        return 0

    # Findings — log to stdout (launchd captures), notify push
    title = f"Energy audit {target_day}: {m.finding_count} finding(s)"
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
