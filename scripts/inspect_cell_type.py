#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from flycraft_brain.connectome import CodexMetadata


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect one exact primary/additional FlyWire cell type"
    )
    parser.add_argument("cell_type")
    parser.add_argument("--data-dir", type=Path, default=Path("data/fly-brain"))
    parser.add_argument("--include-unmodeled", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    metadata = CodexMetadata(args.data_dir)
    result = metadata.inspect_cell_type(
        args.cell_type, modeled_only=not args.include_unmodeled
    )
    columns = [
        "root_id",
        "primary_type",
        "additional_type(s)",
        "flow",
        "super_class",
        "class",
        "sub_class",
        "hemilineage",
        "side",
        "nerve",
        "nt_type",
        "modeled",
    ]
    if args.json:
        print(result[columns].to_json(orient="records", indent=2))
        return

    print(f"cell_type: {args.cell_type}")
    print(f"matches: {len(result)}")
    if result.empty:
        return
    print("side counts:")
    print(result["side"].value_counts(dropna=False).to_string())
    print("neurons:")
    print(result[columns].to_string(index=False))


if __name__ == "__main__":
    main()
