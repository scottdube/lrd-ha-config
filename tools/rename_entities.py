#!/usr/bin/env python3
"""Bulk rename HA entity_ids by substring substitution.

Renames any entity_id containing OLD_STEM by replacing OLD_STEM with NEW_STEM.
Default behavior is preview-only; use --execute to apply changes.

Optionally filter to a single device with --device-id or --device-name. This
avoids the substring-overlap footgun when multiple devices share a stem
(e.g., 'foo_500s' and 'foo_500s_2' — running with --old-stem foo_500s would
match both without a device filter).

Required environment variables:
    HA_URL    - HA WebSocket URL (e.g., ws://192.168.50.11:8123/api/websocket)
    HA_TOKEN  - Long-lived access token from HA Profile -> Security

Examples:
    # Rename all entities containing 'fan_toilet':
    ./rename_entities.py --old-stem fan_toilet --new-stem toilet_fan

    # Rename only entities of a specific device (by device_id):
    ./rename_entities.py --device-id abc123... \\
        --old-stem in_wall_fan_speed_control_500s --new-stem lanai_left

    # Or by device name_by_user (resolved internally):
    ./rename_entities.py --device-name "Lanai Fan Left" \\
        --old-stem in_wall_fan_speed_control_500s --new-stem lanai_left

    # Review the preview, then re-run with --execute to apply.
"""
import argparse
import asyncio
import json
import os
import sys

import websockets


async def main():
    parser = argparse.ArgumentParser(
        description="Bulk rename HA entity_ids by substring substitution"
    )
    parser.add_argument("--old-stem", required=True,
                        help="Substring in entity_id to replace")
    parser.add_argument("--new-stem", required=True,
                        help="Replacement substring")
    parser.add_argument("--execute", action="store_true",
                        help="Apply changes (default is preview only)")
    filter_group = parser.add_mutually_exclusive_group()
    filter_group.add_argument(
        "--device-id",
        help="Limit renames to entities of this device_id (UUID hash)",
    )
    filter_group.add_argument(
        "--device-name",
        help="Limit renames to entities of the device with this name_by_user "
             "(resolved internally to device_id)",
    )
    args = parser.parse_args()

    ha_url = os.environ.get("HA_URL")
    ha_token = os.environ.get("HA_TOKEN")
    if not ha_url or not ha_token:
        sys.exit("HA_URL and HA_TOKEN environment variables required")

    async with websockets.connect(ha_url, max_size=10 * 1024 * 1024) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": ha_token}))
        auth_result = json.loads(await ws.recv())
        if auth_result.get("type") != "auth_ok":
            sys.exit(f"Auth failed: {auth_result}")

        msg_id = 1

        device_filter = args.device_id
        if args.device_name:
            await ws.send(json.dumps({
                "id": msg_id,
                "type": "config/device_registry/list",
            }))
            msg_id += 1
            dev_response = json.loads(await ws.recv())
            devices = dev_response["result"]
            matches = [d for d in devices
                       if d.get("name_by_user") == args.device_name]
            if not matches:
                sys.exit(
                    f"No device found with name_by_user='{args.device_name}'"
                )
            if len(matches) > 1:
                ids = [d["id"] for d in matches]
                sys.exit(
                    f"Multiple devices match name_by_user='{args.device_name}': "
                    f"{ids}. Use --device-id to disambiguate."
                )
            device_filter = matches[0]["id"]
            print(f"Resolved --device-name '{args.device_name}' -> "
                  f"device_id {device_filter}")

        await ws.send(json.dumps({
            "id": msg_id,
            "type": "config/entity_registry/list",
        }))
        msg_id += 1
        response = json.loads(await ws.recv())
        entities = response["result"]

        renames = []
        for entity in entities:
            old_id = entity["entity_id"]
            if device_filter and entity.get("device_id") != device_filter:
                continue
            if args.old_stem not in old_id:
                continue
            new_id = old_id.replace(args.old_stem, args.new_stem)
            if old_id == new_id:
                continue
            renames.append((old_id, new_id))

        if not renames:
            print(f"No entities to rename "
                  f"(no entity_id contains '{args.old_stem}')")
            return

        mode = "EXECUTE" if args.execute else "PREVIEW"
        print(f"[{mode}] {len(renames)} entity_id rename(s):")
        print()
        success = 0
        failed = 0
        for old_id, new_id in renames:
            print(f"  {old_id}")
            print(f"  -> {new_id}")
            if args.execute:
                await ws.send(json.dumps({
                    "id": msg_id,
                    "type": "config/entity_registry/update",
                    "entity_id": old_id,
                    "new_entity_id": new_id,
                }))
                msg_id += 1
                result = json.loads(await ws.recv())
                if result.get("success"):
                    print("     [OK]")
                    success += 1
                else:
                    err = result.get("error", "unknown")
                    print(f"     [FAIL] {err}")
                    failed += 1
            print()

        if args.execute:
            print(f"Done. {success} renamed, {failed} failed.")
        else:
            print("Preview only. Re-run with --execute to apply.")


if __name__ == "__main__":
    asyncio.run(main())
