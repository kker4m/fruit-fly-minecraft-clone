#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import urllib.request
from pathlib import Path

CODEX_VERSION = "783"
BASE_URL = (
    f"https://storage.googleapis.com/flywire-data/codex/data/fafb/{CODEX_VERSION}"
)
FILES = {
    "classification.csv.gz": "e946b552f4056dfc977707be0674609832c3f64332a22d69dc0d9615e7aae663",
    "consolidated_cell_types.csv.gz": "8aba246d71dc40361677493629972ce3883048c3d02010adc42bda22962a1a2d",
    "neurons.csv.gz": "6a6b3759e635f0f35a677d169052362131ec61d95f55919298b55c43fce4e719",
    "labels.csv.gz": "bdd4eafab2bfe30540256c84ea1513e4b1877c0c4cf03f919204b4eafae5868e",
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
    parser = argparse.ArgumentParser(
        description="Fetch pinned FlyWire Codex FAFB v783 metadata"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/fly-brain"),
        help="model data root (default: data/fly-brain)",
    )
    args = parser.parse_args()
    destination = args.data_dir.expanduser().resolve() / f"codex-{CODEX_VERSION}"
    destination.mkdir(parents=True, exist_ok=True)
    for name, digest in FILES.items():
        download(name, digest, destination)
    print("source: FlyWire Codex FAFB v783")
    print("annotation license: CC-BY-NC 4.0 (https://flywire.ai/tos)")


if __name__ == "__main__":
    main()
