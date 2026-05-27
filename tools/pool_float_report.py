#!/usr/bin/env python3
"""
pool_float_report.py — Periodic performance report for the pool water-temp float.

Pulls the last N hours (default 24) of HA history for the pool float entities,
computes a fixed set of headline metrics + cross-validation vs the OmniLogic
in-line probe, renders charts, and emits a sharable PDF (and optional markdown
companion).

Designed to be:
  - Self-contained (stdlib + matplotlib + reportlab + requests)
  - Deterministic in structure (templated — same sections every run)
  - Schedule-friendly (no interactive prompts, exit codes used)

Typical schedule invocation:
    python3 pool_float_report.py
        --hours 24
        --token-file ~/.ha-token
        --out ~/Documents/Claude/Projects/home-assistant/scratch/pool-float-report-YYYY-MM-DD.pdf

Companion docs:
  - docs/decisions/025-pool-float-v2-hardware-revision.md (hardware context)
  - docs/reference/ha-rest-api-curl-cheatsheet.md (REST API patterns this mirrors)
  - tools/README.md (general tooling overview)
"""

import argparse
import io
import json
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak,
)


ENTITIES = {
    "temp_raw":     "sensor.pool_water_temp_external",
    "temp_filt":    "sensor.pool_water_temp_external_filtered",
    "temp_auth":    "sensor.pool_water_temp_authoritative",
    "battery":      "sensor.pool_water_temp_external_pool_float_battery_voltage",
    "wifi":         "sensor.pool_water_temp_external_pool_float_wifi_signal",
    "uptime":       "sensor.pool_water_temp_external_pool_float_uptime",
    "omni_temp":    "sensor.pool_pool_water_temperature",
    "ota_flag":     "input_boolean.pool_float_ota_mode",
}

WIFI_TARGET_LO = -70
WIFI_TARGET_HI = -66
TEMP_DELTA_WARN = 3.0
BATTERY_LOW_V = 3.05
TEMP_OUTLIER_LOW_F = 70.0
TEMP_OUTLIER_HIGH_F = 110.0


def parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def parse_num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def fetch_history(base: str, token: str, hours: int) -> dict:
    """Returns dict keyed by short-name (per ENTITIES), value = list of (ts, state_str)."""
    start = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    filter_ids = ",".join(ENTITIES.values())
    url = f"{base}/api/history/period/{start}?filter_entity_id={urllib.parse.quote(filter_ids, safe=',')}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = json.loads(resp.read())

    by_eid = {series[0]["entity_id"]: series for series in raw if series}
    result = {}
    for key, eid in ENTITIES.items():
        series = by_eid.get(eid, [])
        result[key] = [(parse_iso(r["last_updated"]), r["state"]) for r in series]
    return result


def numeric_series(rows, low=None, high=None):
    """Return [(ts, value)] dropping non-numeric and out-of-bounds entries."""
    out = []
    for ts, s in rows:
        v = parse_num(s)
        if v is None:
            continue
        if low is not None and v < low:
            continue
        if high is not None and v > high:
            continue
        out.append((ts, v))
    return out


def summary_stats(values):
    if not values:
        return None
    n = len(values)
    s = sorted(values)
    return {
        "n": n,
        "min": s[0],
        "max": s[-1],
        "mean": sum(s) / n,
        "p25": s[n // 4],
        "p50": s[n // 2],
        "p75": s[3 * n // 4],
    }


def aligned_pairs(a_series, b_series, max_skew_sec=120):
    """Match pairs by closest timestamp within max_skew_sec. Returns [(ts, a_val, b_val)]."""
    b_sorted = sorted(b_series, key=lambda t: t[0])
    pairs = []
    for ta, va in a_series:
        best = None
        best_dt = max_skew_sec + 1
        for tb, vb in b_sorted:
            dt = abs((ta - tb).total_seconds())
            if dt < best_dt:
                best_dt = dt
                best = (tb, vb)
        if best and best_dt <= max_skew_sec:
            pairs.append((ta, va, best[1]))
    return pairs


def gap_analysis(rows):
    """Return (count, gaps_sec_list) for consecutive uptime publishes."""
    if len(rows) < 2:
        return 0, []
    ts = [r[0] for r in rows]
    gaps = [(ts[i] - ts[i - 1]).total_seconds() for i in range(1, len(ts))]
    return len(ts), gaps


def _to_local(series):
    # Strip tzinfo after converting to local — matplotlib's default x-axis
    # renderer converts tz-aware datetimes back to UTC for display unless
    # rcParams['timezone'] is changed. Stripping makes matplotlib render the
    # local-time clock value literally.
    return [(t.astimezone().replace(tzinfo=None), v) for t, v in series]


def _xaxis_local(ax, tz_label):
    ax.set_xlabel(f"Local time ({tz_label})")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%m-%d"))


def chart_temp_timeline(temp_filt, omni, out_path, tz_label):
    temp_filt = _to_local(temp_filt)
    omni = _to_local(omni)
    fig, ax = plt.subplots(figsize=(8, 3.2))
    if temp_filt:
        xs = [t for t, _ in temp_filt]
        ys = [v for _, v in temp_filt]
        ax.plot(xs, ys, label="External (filtered)", linewidth=1.4, color="#2c7fb8")
    if omni:
        xs = [t for t, _ in omni]
        ys = [v for _, v in omni]
        ax.plot(xs, ys, label="OmniLogic in-line", linewidth=1.4, color="#d95f0e", linestyle="--")
    ax.set_title("Water temperature — external float vs OmniLogic")
    ax.set_ylabel("°F")
    ax.legend(loc="best", framealpha=0.9)
    ax.grid(True, alpha=0.3)
    _xaxis_local(ax, tz_label)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def chart_temp_delta(pairs, out_path, tz_label):
    pairs_local = [(t.astimezone().replace(tzinfo=None), a, b) for t, a, b in pairs]
    fig, ax = plt.subplots(figsize=(8, 2.8))
    if pairs_local:
        xs = [p[0] for p in pairs_local]
        ys = [p[2] - p[1] for p in pairs_local]
        ax.plot(xs, ys, color="#7a0177", linewidth=1.2, marker="o", markersize=3)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.axhline(TEMP_DELTA_WARN, color="red", linewidth=0.7, linestyle=":", label=f"watch threshold ({TEMP_DELTA_WARN}°F)")
        ax.legend(loc="best", framealpha=0.9)
    ax.set_title("Δ (OmniLogic − external) over time — calibration drift signal")
    ax.set_ylabel("Δ °F (positive = omni reads higher)")
    ax.grid(True, alpha=0.3)
    _xaxis_local(ax, tz_label)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def chart_battery(battery, out_path, tz_label):
    battery = _to_local(battery)
    fig, ax = plt.subplots(figsize=(8, 2.8))
    if battery:
        xs = [t for t, _ in battery]
        ys = [v for _, v in battery]
        ax.plot(xs, ys, color="#238b45", linewidth=1.2)
        ax.axhline(BATTERY_LOW_V, color="red", linewidth=0.7, linestyle=":", label=f"low-voltage watch ({BATTERY_LOW_V} V)")
        ax.legend(loc="best", framealpha=0.9)
    ax.set_title("Battery voltage over time")
    ax.set_ylabel("V")
    ax.grid(True, alpha=0.3)
    _xaxis_local(ax, tz_label)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def chart_wifi_timeline(wifi, out_path, tz_label):
    wifi = _to_local(wifi)
    fig, ax = plt.subplots(figsize=(8, 2.8))
    if wifi:
        xs = [t for t, _ in wifi]
        ys = [v for _, v in wifi]
        ax.plot(xs, ys, color="#0570b0", linewidth=0.7, alpha=0.6)
        ax.scatter(xs, ys, s=4, color="#0570b0", alpha=0.5)
        ax.axhspan(WIFI_TARGET_LO, WIFI_TARGET_HI, color="green", alpha=0.15, label=f"target band ({WIFI_TARGET_LO} to {WIFI_TARGET_HI} dBm)")
        ax.axhline(-80, color="orange", linewidth=0.7, linestyle=":", label="weak threshold (-80 dBm)")
        ax.legend(loc="lower right", framealpha=0.9)
    ax.set_title("WiFi RSSI over time")
    ax.set_ylabel("dBm")
    ax.grid(True, alpha=0.3)
    _xaxis_local(ax, tz_label)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def chart_wifi_histogram(wifi, out_path):
    fig, ax = plt.subplots(figsize=(8, 2.6))
    if wifi:
        ys = [v for _, v in wifi]
        bins = list(range(-100, -55, 5))
        ax.hist(ys, bins=bins, color="#0570b0", edgecolor="white")
        ax.axvspan(WIFI_TARGET_LO, WIFI_TARGET_HI, color="green", alpha=0.2, label="target band")
        ax.axvline(-80, color="orange", linewidth=0.7, linestyle=":", label="weak threshold")
        ax.legend(loc="best", framealpha=0.9)
    ax.set_title("WiFi RSSI distribution")
    ax.set_xlabel("dBm")
    ax.set_ylabel("count")
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def chart_cadence(gaps, out_path):
    fig, ax = plt.subplots(figsize=(8, 2.6))
    if gaps:
        clipped = [min(g, 600) for g in gaps]
        bins = [0, 30, 60, 90, 120, 180, 240, 300, 600]
        ax.hist(clipped, bins=bins, color="#54278f", edgecolor="white")
        ax.set_xticks(bins)
        ax.axvline(60, color="green", linewidth=1, linestyle="--", label="1-min target")
    ax.set_title("Publish-gap distribution (capped at 600s for display)")
    ax.set_xlabel("seconds between consecutive wakes")
    ax.set_ylabel("count")
    ax.grid(True, alpha=0.3, axis="y")
    ax.legend(loc="best", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def build_pdf(out_pdf, hours, generated_at, sections):
    doc = SimpleDocTemplate(
        str(out_pdf), pagesize=LETTER,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        title="Pool Float v2 — Performance Report",
        author="LRD HA tooling",
    )
    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]
    h2 = styles["Heading2"]
    body = styles["BodyText"]
    body.spaceAfter = 6
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.grey)
    story = []

    story.append(Paragraph("Pool Float v2 — Performance Report", h1))
    story.append(Paragraph(
        f"Generated {generated_at.strftime('%Y-%m-%d %H:%M %Z')} — window {hours}h ending now",
        small,
    ))
    story.append(Spacer(1, 0.15 * inch))

    for section in sections:
        kind = section[0]
        if kind == "h2":
            story.append(Paragraph(section[1], h2))
        elif kind == "p":
            story.append(Paragraph(section[1], body))
        elif kind == "table":
            data = section[1]
            tbl = Table(data, hAlign="LEFT")
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 0.1 * inch))
        elif kind == "image":
            story.append(Image(section[1], width=7 * inch, height=section[2] * inch))
            story.append(Spacer(1, 0.1 * inch))
        elif kind == "spacer":
            story.append(Spacer(1, section[1] * inch))
        elif kind == "pagebreak":
            story.append(PageBreak())

    doc.build(story)


def build_report(hours: int, base: str, token: str, out_pdf: Path, charts_dir: Path):
    generated_at = datetime.now().astimezone()
    data = fetch_history(base, token, hours)

    # Numeric series with sensible bounds
    temp_raw = numeric_series(data["temp_raw"], TEMP_OUTLIER_LOW_F, TEMP_OUTLIER_HIGH_F)
    temp_filt = numeric_series(data["temp_filt"], TEMP_OUTLIER_LOW_F, TEMP_OUTLIER_HIGH_F)
    temp_auth = numeric_series(data["temp_auth"], TEMP_OUTLIER_LOW_F, TEMP_OUTLIER_HIGH_F)
    battery = numeric_series(data["battery"], 2.0, 4.5)
    wifi = numeric_series(data["wifi"], -100, -40)
    uptime_rows = data["uptime"]
    omni = numeric_series(data["omni_temp"], 32, 110)
    ota_rows = data["ota_flag"]

    stats_temp = summary_stats([v for _, v in temp_filt])
    stats_batt = summary_stats([v for _, v in battery])
    stats_wifi = summary_stats([v for _, v in wifi])
    stats_omni = summary_stats([v for _, v in omni])
    pairs = aligned_pairs(temp_filt, omni, max_skew_sec=120)
    delta_stats = summary_stats([p[2] - p[1] for p in pairs])

    wake_count, gaps = gap_analysis(uptime_rows)
    if gaps:
        gap_mean = sum(gaps) / len(gaps)
        gap_median = sorted(gaps)[len(gaps) // 2]
        gap_max = max(gaps)
        long_gaps = [g for g in gaps if g > 120]
        # Success rate: actual wakes / theoretical (assumes 1-min cadence; degrade gracefully)
        span_min = max(1, (uptime_rows[-1][0] - uptime_rows[0][0]).total_seconds() / 60)
        cadence_pct = 100 * wake_count / span_min
    else:
        gap_mean = gap_median = gap_max = 0
        long_gaps = []
        span_min = cadence_pct = 0

    ota_toggles = sum(1 for _, s in ota_rows if s in ("on", "off")) - 1
    ota_now = ota_rows[-1][1] if ota_rows else "unknown"

    # Local timezone label (e.g. "EDT") for x-axes and tables
    tz_label = generated_at.strftime("%Z") or "local"

    # Render charts
    charts_dir.mkdir(parents=True, exist_ok=True)
    c_temp = charts_dir / "temp_timeline.png"
    c_delta = charts_dir / "temp_delta.png"
    c_batt = charts_dir / "battery.png"
    c_wifi = charts_dir / "wifi_timeline.png"
    c_wifi_h = charts_dir / "wifi_hist.png"
    c_gaps = charts_dir / "cadence.png"
    chart_temp_timeline(temp_filt, omni, c_temp, tz_label)
    chart_temp_delta(pairs, c_delta, tz_label)
    chart_battery(battery, c_batt, tz_label)
    chart_wifi_timeline(wifi, c_wifi, tz_label)
    chart_wifi_histogram(wifi, c_wifi_h)
    chart_cadence(gaps, c_gaps)

    def fmt(s, fmt_str="{:.2f}"):
        if s is None:
            return "—"
        if isinstance(s, dict):
            return s
        return fmt_str.format(s)

    headlines = [
        ["Metric", "Value", "Notes"],
        [
            "Wake cadence",
            f"{cadence_pct:.1f}% (over {span_min:.0f} min)" if span_min else "—",
            f"{wake_count} wakes, median gap {gap_median:.0f}s",
        ],
        [
            "WiFi RSSI",
            f"mean {fmt(stats_wifi['mean'] if stats_wifi else None, '{:.1f}')} dBm"
                if stats_wifi else "—",
            f"range {fmt(stats_wifi['min'] if stats_wifi else None, '{:.0f}')} to {fmt(stats_wifi['max'] if stats_wifi else None, '{:.0f}')} dBm; target band {WIFI_TARGET_LO} to {WIFI_TARGET_HI}",
        ],
        [
            "Battery voltage",
            f"mean {fmt(stats_batt['mean'] if stats_batt else None)} V" if stats_batt else "—",
            f"range {fmt(stats_batt['min'] if stats_batt else None)} to {fmt(stats_batt['max'] if stats_batt else None)} V; low-V watch {BATTERY_LOW_V}",
        ],
        [
            "Filtered water temp",
            f"mean {fmt(stats_temp['mean'] if stats_temp else None, '{:.1f}')} °F" if stats_temp else "—",
            f"range {fmt(stats_temp['min'] if stats_temp else None, '{:.1f}')} to {fmt(stats_temp['max'] if stats_temp else None, '{:.1f}')} °F",
        ],
        [
            "Δ vs OmniLogic",
            f"mean {fmt(delta_stats['mean'] if delta_stats else None, '{:+.2f}')} °F"
                if delta_stats else "—",
            f"{len(pairs)} matched pairs; watch threshold ±{TEMP_DELTA_WARN}°F sustained",
        ],
        [
            "OTA flag now",
            ota_now,
            f"{ota_toggles} toggle event(s) in window",
        ],
    ]

    watch_items = []
    if delta_stats and abs(delta_stats["mean"]) > TEMP_DELTA_WARN:
        watch_items.append(
            f"<b>Δ vs OmniLogic mean is {delta_stats['mean']:+.2f} °F</b> — over the ±{TEMP_DELTA_WARN}°F watch threshold. Likely calibration drift, real stratification, or OmniLogic pump-off staleness. Check pump state during this window before deciding."
        )
    if stats_batt and stats_batt["min"] < BATTERY_LOW_V:
        watch_items.append(
            f"<b>Battery dipped to {stats_batt['min']:.2f} V</b>, below the {BATTERY_LOW_V} V low-watch threshold. Plan a cell swap if this persists."
        )
    if stats_wifi and stats_wifi["mean"] < -80:
        watch_items.append(
            f"<b>WiFi mean RSSI is {stats_wifi['mean']:.1f} dBm</b>, weaker than the −80 dBm threshold. Check float position vs AP, antenna orientation, or AP-side RF."
        )
    if cadence_pct and cadence_pct < 85:
        watch_items.append(
            f"<b>Wake cadence {cadence_pct:.1f}% is below 85% per-minute success.</b> Investigate WiFi reliability or sleep-cycle issues."
        )
    if long_gaps:
        watch_items.append(
            f"<b>{len(long_gaps)} cadence gap(s) > 2 min</b> totalling {sum(long_gaps):.0f}s. Longest: {max(long_gaps):.0f}s."
        )
    if ota_toggles > 0:
        watch_items.append(
            f"OTA mode toggled {ota_toggles} time(s) in window — verify flag is OFF if you want sleep cycling active."
        )

    if not watch_items:
        watch_items.append(
            "No alerts. All headline metrics within normal bands and no cadence anomalies detected."
        )

    sources_data = [
        ["Entity", "Samples"],
    ]
    for key, eid in ENTITIES.items():
        sources_data.append([eid, str(len(data[key]))])

    # Per-section tables
    def stats_row(name, s, fmt_str="{:.2f}"):
        if not s:
            return [name, "—", "—", "—", "—", "—", "—"]
        return [
            name,
            str(s["n"]),
            fmt_str.format(s["min"]),
            fmt_str.format(s["max"]),
            fmt_str.format(s["mean"]),
            fmt_str.format(s["p50"]),
            f"{fmt_str.format(s['p25'])} / {fmt_str.format(s['p75'])}",
        ]

    temp_table = [
        ["Series", "n", "min", "max", "mean", "median (p50)", "p25 / p75"],
        stats_row("External filtered (°F)", stats_temp, "{:.2f}"),
        stats_row("OmniLogic in-line (°F)", stats_omni, "{:.2f}"),
    ]

    if pairs:
        delta_recent = pairs[-5:]
        delta_table = [
            ["Local time", "External (°F)", "OmniLogic (°F)", "Δ (°F)"],
        ] + [
            [
                p[0].astimezone().strftime(f"%Y-%m-%d %H:%M {tz_label}"),
                f"{p[1]:.2f}",
                f"{p[2]:.1f}",
                f"{p[2] - p[1]:+.2f}",
            ]
            for p in delta_recent
        ]
        delta_summary = [
            ["", "min", "max", "mean", "median"],
            [
                f"Δ stats ({len(pairs)} pairs)",
                f"{delta_stats['min']:+.2f}",
                f"{delta_stats['max']:+.2f}",
                f"{delta_stats['mean']:+.2f}",
                f"{delta_stats['p50']:+.2f}",
            ],
        ]
    else:
        delta_table = [["Local time", "External (°F)", "OmniLogic (°F)", "Δ (°F)"],
                       ["—", "—", "—", "no matched pairs in window"]]
        delta_summary = [["", "min", "max", "mean", "median"],
                         ["Δ stats", "—", "—", "—", "—"]]

    if battery:
        # First, middle, last samples for the trend table
        n_b = len(battery)
        picks = [0, n_b // 4, n_b // 2, 3 * n_b // 4, n_b - 1] if n_b >= 5 else list(range(n_b))
        battery_trend_table = [
            ["Local time", "Battery (V)"],
        ] + [
            [battery[i][0].astimezone().strftime(f"%Y-%m-%d %H:%M {tz_label}"),
             f"{battery[i][1]:.3f}"]
            for i in picks
        ]
    else:
        battery_trend_table = [["Local time", "Battery (V)"], ["—", "no samples in window"]]

    battery_stats_table = [
        ["", "n", "min", "max", "mean", "median"],
        stats_row("Battery (V)", stats_batt, "{:.3f}")[0:1] +
            stats_row("Battery (V)", stats_batt, "{:.3f}")[1:6],
    ]

    # WiFi distribution buckets
    wifi_buckets_def = [(-100, -85), (-85, -80), (-80, -75), (-75, -70), (-70, -65), (-65, -60)]
    wifi_table = [["RSSI bucket (dBm)", "count", "% of samples"]]
    wifi_total = len(wifi) if wifi else 0
    for lo, hi in wifi_buckets_def:
        count = sum(1 for _, v in wifi if lo <= v < hi)
        pct = (100.0 * count / wifi_total) if wifi_total else 0
        wifi_table.append([f"[{lo}, {hi})", str(count), f"{pct:.1f}%"])

    wifi_stats_table = [
        ["", "n", "min", "max", "mean", "median"],
        stats_row("WiFi RSSI (dBm)", stats_wifi, "{:.1f}")[0:1] +
            stats_row("WiFi RSSI (dBm)", stats_wifi, "{:.1f}")[1:6],
    ]

    # Cadence stats + longest gaps
    cadence_table = [
        ["Stat", "Value"],
        ["Wakes captured", str(wake_count)],
        ["Window span (min)", f"{span_min:.1f}"],
        ["Success rate vs 1-min cadence", f"{cadence_pct:.1f}%"],
        ["Median gap (s)", f"{gap_median:.0f}"],
        ["Mean gap (s)", f"{gap_mean:.0f}"],
        ["Max gap (s)", f"{gap_max:.0f}"],
        ["Gaps > 2 min", f"{len(long_gaps)} (total {sum(long_gaps):.0f}s)"],
    ]
    if gaps:
        longest = sorted(((g, i) for i, g in enumerate(gaps, 1)), reverse=True)[:5]
        longest_table = [["Rank", "Gap (s)", "Local time (gap ended)"]]
        for rank, (g, idx) in enumerate(longest, 1):
            longest_table.append([
                str(rank),
                f"{g:.0f}",
                uptime_rows[idx][0].astimezone().strftime(f"%Y-%m-%d %H:%M:%S {tz_label}"),
            ])
    else:
        longest_table = [["Rank", "Gap (s)", "Local time"], ["—", "—", "no gaps"]]

    sections = [
        ("h2", "Headlines"),
        ("table", headlines),
        ("spacer", 0.1),
        ("h2", "Water temperature"),
        ("p", "External float (filtered, 3-sample median) vs the OmniLogic in-line probe. The float reading feeds <i>sensor.pool_water_temp_authoritative</i> as Tier 1 of the fallback chain (per ADR-013/ADR-015)."),
        ("table", temp_table),
        ("image", str(c_temp), 2.5),
        ("p", "Delta = OmniLogic minus External. Positive values mean OmniLogic reads warmer (which is the steady-state expectation when the pump cycles). Last 5 matched pairs:"),
        ("table", delta_table),
        ("table", delta_summary),
        ("image", str(c_delta), 2.2),
        ("pagebreak",),
        ("h2", "Battery"),
        ("p", "L91 lithium AA stack feeding 3V3 direct (regulator bypassed per ADR-025). Working range 3.0–3.4 V across discharge curve; voltage-trap math accepts sleep current ~381 µA. Watch for sustained dips below the low-V line."),
        ("table", battery_stats_table),
        ("table", battery_trend_table),
        ("image", str(c_batt), 2.4),
        ("h2", "WiFi"),
        ("p", f"Target band is {WIFI_TARGET_LO} to {WIFI_TARGET_HI} dBm per ADR-025's combined RF improvements (powered RF switch + external U.FL antenna + Lanai U7 omni). The −80 dBm orange line is the practical weak-link threshold."),
        ("table", wifi_stats_table),
        ("table", wifi_table),
        ("image", str(c_wifi), 2.3),
        ("image", str(c_wifi_h), 2.2),
        ("pagebreak",),
        ("h2", "Cadence — wake reliability"),
        ("p", f"Wake count from the uptime sensor — most reliable signal of successful publishes. Target cadence is determined by ESPHome <i>sleep_duration</i> (currently 1 min for test, planned 30 min for production)."),
        ("table", cadence_table),
        ("table", longest_table),
        ("image", str(c_gaps), 2.2),
        ("h2", "Things to watch"),
    ]
    for w in watch_items:
        sections.append(("p", f"• {w}"))

    sections.extend([
        ("spacer", 0.15),
        ("h2", "Methodology + data sources"),
        ("p", f"Window: last {hours}h ending {generated_at.strftime('%Y-%m-%d %H:%M %Z')}. Source: HA REST <i>/api/history/period/</i> against the entities below, mirroring the curl patterns in <i>docs/reference/ha-rest-api-curl-cheatsheet.md</i>. Outlier guards: temperature clipped to 70–110 °F, battery to 2.0–4.5 V, WiFi to −100 to −40 dBm. Cross-validation pairs require timestamps within 120 s."),
        ("table", sources_data),
        ("spacer", 0.15),
        ("p", "<i>Generated by tools/pool_float_report.py. Pattern + ADRs in docs/decisions/{015,025}-*.md and docs/pool-float-* handoffs.</i>"),
    ])

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(out_pdf, hours, generated_at, sections)


def main():
    p = argparse.ArgumentParser(description="Generate the pool float performance PDF report.")
    p.add_argument("--hours", type=int, default=24, help="Look-back window in hours (default 24)")
    p.add_argument("--base", default="http://192.168.50.11:8123", help="HA Core base URL")
    p.add_argument("--token-file", type=Path, default=Path.home() / ".ha_token",
                   help="Path to file containing long-lived access token")
    p.add_argument("--out", type=Path, default=None,
                   help="Output PDF path. Default: ~/Documents/Claude/Projects/home-assistant/scratch/pool-float-report-YYYY-MM-DD.pdf")
    p.add_argument("--charts-dir", type=Path, default=None,
                   help="Where to write intermediate chart PNGs. Default: alongside the PDF, under charts/")
    args = p.parse_args()

    try:
        token = args.token_file.read_text().strip()
    except Exception as exc:
        sys.stderr.write(f"Cannot read token from {args.token_file}: {exc}\n")
        sys.exit(2)
    if not token:
        sys.stderr.write(f"Token file {args.token_file} is empty\n")
        sys.exit(2)

    today_local = datetime.now().astimezone().strftime("%Y-%m-%d")
    if args.out is None:
        args.out = Path.home() / "Documents" / "Claude" / "Projects" / "home-assistant" / "scratch" / f"pool-float-report-{today_local}.pdf"
    if args.charts_dir is None:
        args.charts_dir = args.out.parent / "charts" / f"pool-float-{today_local}"

    try:
        build_report(args.hours, args.base, token, args.out, args.charts_dir)
    except Exception as exc:
        sys.stderr.write(f"Report generation failed: {type(exc).__name__}: {exc}\n")
        sys.exit(3)

    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
