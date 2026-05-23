#!/usr/bin/env python3
"""
zwave_health_probe.py — One-shot probe of a Z-Wave node's lifeline health.

Connects to the zwave-js-server WebSocket exposed by the HA Z-Wave JS app,
runs `node.check_lifeline_health` against a target node, summarises the
result, and appends a structured row to a CSV. Designed to run on a
schedule (launchd, cron) to build a time-series for before/after
comparisons (e.g. before / after adding a closer repeater).

Endpoint defaults to ws://192.168.50.11:3000 (HA NUC, Trusted-LRD VLAN).
If the Z-Wave JS app is only bound to the IoT-VLAN address, pass
--uri ws://192.168.11.155:3000 and ensure UDM Pro firewall allows the hop.

Dependencies: websockets   (pip3 install --user websockets)

Usage:
    python3 zwave_health_probe.py
    python3 zwave_health_probe.py --node 55 --rounds 5 \\
        --csv ~/zw-baseline-node55.csv

Author: Scott Dube. Sister to pool/scripts/auditor.py — same shape of CSV
append + launchd schedule. Result schema follows zwave-js LifelineHealth
Check spec; raw_summary_json column preserves the full response for
re-parsing if the schema evolves.
"""

import argparse
import asyncio
import csv
import datetime
import json
import sys
import uuid
from pathlib import Path

try:
    import websockets
except ImportError:
    sys.stderr.write(
        "Missing dependency 'websockets'. Install with:\n"
        "    pip3 install --user websockets\n"
    )
    sys.exit(1)


DEFAULT_URI = "ws://192.168.50.11:3000"
DEFAULT_NODE = 55
DEFAULT_ROUNDS = 5
DEFAULT_CSV = Path.home() / "zw-baseline-node55.csv"
SCHEMA_VERSION = 34
WS_TIMEOUT_SEC = 180


CSV_FIELDS = [
    "timestamp_utc",
    "node",
    "rounds",
    "rating",
    "worst_round_rating",
    "worst_route_changes",
    "max_latency_ms",
    "total_failed_pings",
    "worst_min_powerlevel",
    "worst_snr_margin_db",
    "raw_summary_json",
]


async def _await_response(ws, msg_id: str, timeout: float = WS_TIMEOUT_SEC):
    """Drain messages until we see a result for the given messageId."""
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        msg = json.loads(raw)
        if msg.get("messageId") == msg_id:
            return msg


async def probe(uri: str, node: int, rounds: int) -> dict:
    async with websockets.connect(uri, max_size=2 ** 22) as ws:
        # Server announces version banner on connect; discard.
        await ws.recv()

        # Schema handshake — some commands require an agreed schema version.
        msg_id = str(uuid.uuid4())
        await ws.send(json.dumps({
            "messageId": msg_id,
            "command": "set_api_schema",
            "schemaVersion": SCHEMA_VERSION,
        }))
        resp = await _await_response(ws, msg_id, timeout=10)
        if not resp.get("success", True):
            raise RuntimeError(f"set_api_schema failed: {resp}")

        # Start listening — required before driver commands.
        msg_id = str(uuid.uuid4())
        await ws.send(json.dumps({
            "messageId": msg_id,
            "command": "start_listening",
        }))
        await _await_response(ws, msg_id, timeout=30)

        # The actual health check. Runs `rounds` rounds of NoOp pings,
        # measuring route changes, latency, failed pings, RSSI margin.
        msg_id = str(uuid.uuid4())
        await ws.send(json.dumps({
            "messageId": msg_id,
            "command": "node.check_lifeline_health",
            "nodeId": node,
            "rounds": rounds,
        }))
        resp = await _await_response(ws, msg_id, timeout=WS_TIMEOUT_SEC)
        if not resp.get("success"):
            raise RuntimeError(f"check_lifeline_health failed: {resp}")

        result = resp.get("result", {})
        # zwave-js-server has historically returned the summary either at
        # the top level or wrapped under a "summary" key. Handle both.
        return result.get("summary", result)


def summarize(result: dict) -> dict:
    rounds = result.get("results", []) or []
    if not rounds:
        return {
            "rating": result.get("rating"),
            "worst_round_rating": None,
            "worst_route_changes": None,
            "max_latency_ms": None,
            "total_failed_pings": None,
            "worst_min_powerlevel": None,
            "worst_snr_margin_db": None,
        }

    ratings = [r["rating"] for r in rounds if "rating" in r]
    route_changes = [r.get("routeChanges", 0) for r in rounds]
    latencies = [r.get("latency", 0) for r in rounds]
    failed = sum(r.get("failedPingsNode", 0) for r in rounds)
    powerlevels = [r["minPowerlevel"] for r in rounds if "minPowerlevel" in r]
    snrs = [r["snrMargin"] for r in rounds if "snrMargin" in r]

    return {
        "rating": result.get("rating"),
        "worst_round_rating": min(ratings) if ratings else None,
        "worst_route_changes": max(route_changes) if route_changes else None,
        "max_latency_ms": max(latencies) if latencies else None,
        "total_failed_pings": failed,
        "worst_min_powerlevel": min(powerlevels) if powerlevels else None,
        "worst_snr_margin_db": min(snrs) if snrs else None,
    }


def append_row(csv_path: Path, result: dict, node: int, rounds: int) -> dict:
    summary = summarize(result)
    row = {
        "timestamp_utc": datetime.datetime.utcnow()
            .replace(microsecond=0).isoformat() + "Z",
        "node": node,
        "rounds": rounds,
        **summary,
        "raw_summary_json": json.dumps(result, separators=(",", ":")),
    }
    new = not csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    return row


def main():
    p = argparse.ArgumentParser(
        description="Probe a Z-Wave node's lifeline health and append to CSV.",
    )
    p.add_argument("--uri", default=DEFAULT_URI,
                   help=f"zwave-js-server WebSocket URI (default {DEFAULT_URI})")
    p.add_argument("--node", type=int, default=DEFAULT_NODE,
                   help=f"Target node ID (default {DEFAULT_NODE})")
    p.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS,
                   help=f"Number of probe rounds (default {DEFAULT_ROUNDS})")
    p.add_argument("--csv", type=Path, default=DEFAULT_CSV,
                   help=f"CSV append path (default {DEFAULT_CSV})")
    args = p.parse_args()

    try:
        result = asyncio.run(probe(args.uri, args.node, args.rounds))
    except Exception as exc:
        sys.stderr.write(f"Probe failed: {type(exc).__name__}: {exc}\n")
        sys.exit(2)

    row = append_row(args.csv, result, args.node, args.rounds)
    print(
        f"node={row['node']} "
        f"rating={row['rating']} "
        f"worst_round={row['worst_round_rating']} "
        f"max_latency={row['max_latency_ms']}ms "
        f"failed_pings={row['total_failed_pings']} "
        f"snr={row['worst_snr_margin_db']}dB "
        f"-> {args.csv}"
    )


if __name__ == "__main__":
    main()
