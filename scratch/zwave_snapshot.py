#!/usr/bin/env python3
"""Read-only Z-Wave JS snapshot of one or more nodes.

Does NOT call check_lifeline_health (which burns beam-wake energy on FLiRS
battery nodes). Reads the driver's start_listening state, which already
contains per-node statistics + last-seen telemetry, and prints the fields
that matter for trend / mesh-health work as JSON.

Usage:
    python3 zwave_snapshot.py            # snapshot of default node set
    python3 zwave_snapshot.py 55 8 38    # explicit node IDs

Companion to tools/zwave_health_probe.py. Cheap and FLiRS-safe — use when
you want a "right now" view without paying the lock-battery cost of a
formal lifeline health check.
"""

import asyncio
import json
import sys
import uuid

import websockets

URI = "ws://192.168.50.11:3000"
SCHEMA_VERSION = 34
DEFAULT_NODES = {55, 8, 38}


async def _await_response(ws, msg_id, timeout=30):
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        msg = json.loads(raw)
        if msg.get("messageId") == msg_id:
            return msg


async def fetch_state():
    async with websockets.connect(URI, max_size=2 ** 24) as ws:
        await ws.recv()  # version banner

        msg_id = str(uuid.uuid4())
        await ws.send(json.dumps({
            "messageId": msg_id,
            "command": "set_api_schema",
            "schemaVersion": SCHEMA_VERSION,
        }))
        await _await_response(ws, msg_id, timeout=10)

        msg_id = str(uuid.uuid4())
        await ws.send(json.dumps({
            "messageId": msg_id,
            "command": "start_listening",
        }))
        resp = await _await_response(ws, msg_id, timeout=60)
        return resp.get("result", {}).get("state", {})


def summarize_node(node):
    nid = node.get("nodeId")
    stats = node.get("statistics", {}) or {}
    lwr = stats.get("lwr") or {}
    rssi = lwr.get("rssi")
    neighbors = node.get("neighbors") or []

    battery = None
    for v in node.get("values", []) or []:
        if v.get("commandClassName") == "Battery" and v.get("propertyName") == "level":
            battery = v.get("value")

    return {
        "nodeId": nid,
        "name": node.get("name") or node.get("label"),
        "status": node.get("status"),
        "ready": node.get("ready"),
        "interviewStage": node.get("interviewStage"),
        "lastSeen": node.get("lastSeen") or stats.get("lastSeen"),
        "battery": battery,
        "numNeighbors": len(neighbors),
        "neighbors": neighbors,
        "commandsTX": stats.get("commandsTX"),
        "commandsRX": stats.get("commandsRX"),
        "commandsDroppedRX": stats.get("commandsDroppedRX"),
        "commandsDroppedTX": stats.get("commandsDroppedTX"),
        "timeoutResponse": stats.get("timeoutResponse"),
        "rtt": stats.get("rtt"),
        "rssi": rssi,
        "lwr": {
            "rssi": rssi,
            "repeaters": lwr.get("repeaters"),
            "protocolDataRate": lwr.get("protocolDataRate"),
            "routeFailedBetween": lwr.get("routeFailedBetween"),
        },
        "nlwr": stats.get("nlwr"),
    }


async def main():
    targets = DEFAULT_NODES
    if len(sys.argv) > 1:
        targets = {int(a) for a in sys.argv[1:]}

    state = await fetch_state()
    nodes = state.get("nodes", []) or []
    hits = [n for n in nodes if n.get("nodeId") in targets]
    out = {summarize_node(n)["nodeId"]: summarize_node(n) for n in hits}
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        sys.stderr.write(f"Snapshot failed: {type(e).__name__}: {e}\n")
        sys.exit(2)
