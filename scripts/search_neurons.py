#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from flycraft_brain.connectome import CodexMetadata

DISPLAY_COLUMNS = [
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search local FlyWire Codex FAFB v783 metadata"
    )
    parser.add_argument("query", nargs="?", help="literal text search")
    parser.add_argument("--data-dir", type=Path, default=Path("data/fly-brain"))
    parser.add_argument("--root-id", type=int, action="append", dest="root_ids")
    parser.add_argument("--flow")
    parser.add_argument("--super-class")
    parser.add_argument("--class", dest="cell_class")
    parser.add_argument("--sub-class")
    parser.add_argument("--hemilineage")
    parser.add_argument("--side")
    parser.add_argument("--nerve")
    parser.add_argument("--cell-type")
    parser.add_argument("--primary-type")
    parser.add_argument("--include-unmodeled", action="store_true")
    parser.add_argument("--labels", action="store_true", help="load label text")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")

    filters = {
        field: value
        for field, value in {
            "flow": args.flow,
            "super_class": args.super_class,
            "class": args.cell_class,
            "sub_class": args.sub_class,
            "hemilineage": args.hemilineage,
            "side": args.side,
            "nerve": args.nerve,
            "cell_type": args.cell_type,
            "primary_type": args.primary_type,
        }.items()
        if value is not None
    }
    metadata = CodexMetadata(args.data_dir, load_labels=args.labels)
    result = metadata.search(
        text=args.query,
        filters=filters,
        root_ids=args.root_ids,
        modeled_only=not args.include_unmodeled,
    )
    shown = result.head(args.limit)
    columns = DISPLAY_COLUMNS.copy()
    if args.labels:
        columns.append("labels")
    if args.json:
        print(shown[columns].to_json(orient="records", indent=2))
    else:
        print(f"matches: {len(result)}; showing: {len(shown)}")
        if len(shown):
            print(shown[columns].to_string(index=False))


if __name__ == "__main__":
    main()
