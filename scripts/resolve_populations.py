#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flycraft_brain.connectome import CodexMetadata, PopulationCatalog


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve versioned biological candidate populations to FlyWire IDs"
    )
    parser.add_argument("names", nargs="*")
    parser.add_argument("--data-dir", type=Path, default=Path("data/fly-brain"))
    parser.add_argument("--include-unmodeled", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    metadata = CodexMetadata(args.data_dir)
    catalog = PopulationCatalog.load()
    names = args.names or None
    manifest = catalog.manifest(
        metadata,
        names,
        modeled_only=not args.include_unmodeled,
    )
    output = args.output or args.data_dir / "populations-v783.json"
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    for population in manifest["populations"]:
        print(f"{population['name']}: {population['count']}")


if __name__ == "__main__":
    main()
