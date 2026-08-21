#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import urllib.request
from pathlib import Path

UPSTREAM_COMMIT = "680b7b3d8d1134bf3cbd289b892cf5d37f097d34"
BASE_URL = (
    f"https://raw.githubusercontent.com/eonsystemspbc/fly-brain/{UPSTREAM_COMMIT}/data"
)
FILES = {
    "2025_Completeness_783.csv": "52b0ac6094cd32c546f8d4c341e094376f48f4e791f8db9b166de5dff8199ea4",
    "2025_Connectivity_783.parquet": "efeb23fb99098e9c390f6869969b2a121a2ee92c833cfc45ecb2c1d8e1af0347",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(name: str, expected_digest: str, destination: Path) -> None:
    target = destination / name
    if target.is_file() and sha256(target) == expected_digest:
        print(f"verified {target}")
        return

    temporary = target.with_suffix(target.suffix + ".part")
    temporary.unlink(missing_ok=True)
    print(f"downloading {name}")
    try:
        with urllib.request.urlopen(f"{BASE_URL}/{name}") as response:
            with temporary.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
        actual_digest = sha256(temporary)
        if actual_digest != expected_digest:
            raise RuntimeError(
                f"Checksum mismatch for {name}: expected {expected_digest}, "
                f"received {actual_digest}"
            )
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch pinned FAFB v783 model data")
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("data/fly-brain"),
        help="output directory (default: data/fly-brain)",
    )
    args = parser.parse_args()
    destination = args.destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for name, digest in FILES.items():
        download(name, digest, destination)


if __name__ == "__main__":
    main()
