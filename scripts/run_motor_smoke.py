#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flycraft_brain import BrainRuntime, MotorDecoder
from flycraft_brain.connectome import CodexMetadata, PopulationCatalog


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Optogenetically exercise forward, turn, and escape decoder channels"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data/fly-brain"))
    parser.add_argument(
        "--codegen-target", choices=("cython", "numpy"), default="cython"
    )
    args = parser.parse_args()

    metadata = CodexMetadata(args.data_dir)
    catalog = PopulationCatalog.load()
    decoder = MotorDecoder(metadata, catalog)
    brain = BrainRuntime(
        data_dir=args.data_dir,
        codegen_target=args.codegen_target,
        seed=783,
    )

    forward_ids = catalog.resolve(metadata, "motor_forward_dnp09")["root_id"].tolist()
    right_turn_ids = (
        catalog.resolve(metadata, "motor_turning_dna02")
        .loc[lambda rows: rows["side"].eq("right"), "root_id"]
        .tolist()
    )
    escape_ids = catalog.resolve(metadata, "motor_escape_dnp01")["root_id"].tolist()
    scenarios = (
        ("forward_dnp09", forward_ids),
        ("right_turn_dna02", right_turn_ids),
        ("escape_dnp01", escape_ids),
    )

    for name, neuron_ids in scenarios:
        brain.stimulate(neuron_ids, intensity=200.0)
        result = brain.step(50)
        command = decoder.decode(result)
        trace = decoder.last_trace
        print(
            json.dumps(
                {
                    "scenario": name,
                    "stimulated_ids": neuron_ids,
                    "brain": {
                        "simulation_time_ms": result.simulation_time_ms,
                        "wall_time_ms": round(result.wall_time_ms, 3),
                        "spikes": len(result.spikes),
                        "active_neurons": result.active_neuron_count,
                    },
                    "command": {
                        "forward": round(command.forward, 4),
                        "yaw": round(command.yaw, 4),
                        "escape": command.escape,
                    },
                    "rates_hz": {
                        key: round(trace.population_rates_hz[key], 3)
                        for key in (
                            "forward_dnp09",
                            "backward_mdn",
                            "turn_dna02",
                            "escape_dnp01",
                        )
                    },
                    "mode": "optogenetic_readout_smoke_not_natural_behavior",
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
