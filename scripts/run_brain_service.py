#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from flycraft_brain.service import BrainController, BrainWebSocketService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the persistent FlyCraft brain service"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data/fly-brain"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--codegen-target", choices=("cython", "numpy"), default="cython"
    )
    parser.add_argument("--seed", type=int, default=783)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be within 1..65535")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.info("Loading FAFB v783 brain; WebSocket opens after initialization")
    controller = BrainController.create(
        args.data_dir,
        codegen_target=args.codegen_target,
        seed=args.seed,
    )
    service = BrainWebSocketService(controller)
    asyncio.run(service.run(args.host, args.port))


if __name__ == "__main__":
    main()
