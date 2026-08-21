#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from flycraft_brain.connectome import CodexMetadata, ConnectivityStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect local FAFB v783 inputs and outputs for a FlyWire root ID"
    )
    parser.add_argument("root_id", type=int)
    parser.add_argument("--data-dir", type=Path, default=Path("data/fly-brain"))
    parser.add_argument(
        "--direction", choices=("inputs", "outputs", "both"), default="both"
    )
    parser.add_argument("--min-synapses", type=int, default=5)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--no-metadata", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")

    store = ConnectivityStore(args.data_dir)
    result = store.neighbors(
        args.root_id,
        direction=args.direction,
        min_synapses=args.min_synapses,
    )
    if not args.no_metadata and not result.empty:
        metadata = CodexMetadata(args.data_dir)
        partner_metadata = metadata.table[
            ["root_id", "primary_type", "super_class", "side", "nt_type", "modeled"]
        ].rename(columns={"root_id": "partner_id"})
        result = result.merge(partner_metadata, on="partner_id", how="left")

    shown = result.head(args.limit)
    if args.json:
        print(shown.to_json(orient="records", indent=2))
    else:
        print(f"connections: {len(result)}; showing: {len(shown)}")
        if len(shown):
            print(shown.to_string(index=False))


if __name__ == "__main__":
    main()
