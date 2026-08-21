#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time

from websockets.sync.client import connect


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send one sensory frame to a running brain service"
    )
    parser.add_argument("--uri", default="ws://127.0.0.1:8765")
    args = parser.parse_args()
    payload = {
        "type": "sensory_frame",
        "protocol_version": 1,
        "request_id": 1,
        "sent_at_ms": int(time.time() * 1000),
        "step_ms": 50,
        "sensors": {
            "light": 12,
            "food_distance": 4.8,
            "food_angle": -0.31,
            "obstacle_front": 0.7,
            "obstacle_left": 3.1,
            "obstacle_right": 2.4,
            "touch": False,
            "damage": False,
            "in_water": False,
        },
    }
    with connect(args.uri, open_timeout=10, close_timeout=10) as websocket:
        websocket.send(json.dumps(payload))
        response = json.loads(websocket.recv(timeout=30))
    if response.get("type") != "motor_command" or response.get("request_id") != 1:
        raise RuntimeError(f"unexpected response: {response}")
    print(json.dumps(response, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
