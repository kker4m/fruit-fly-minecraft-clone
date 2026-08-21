#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flycraft_brain import BrainRuntime, SensoryEncoder, SensoryState
from flycraft_brain.connectome import CodexMetadata


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Encode one Minecraft-like sensory frame and optionally step the brain"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data/fly-brain"))
    parser.add_argument("--encode-only", action="store_true")
    parser.add_argument(
        "--codegen-target", choices=("cython", "numpy"), default="cython"
    )
    args = parser.parse_args()

    metadata = CodexMetadata(args.data_dir)
    encoder = SensoryEncoder(metadata)
    state = SensoryState(
        light=12,
        food_distance=4.8,
        food_angle=-0.31,
        obstacle_front=0.7,
        obstacle_left=3.1,
        obstacle_right=2.4,
        touch=False,
        damage=True,
        in_water=False,
    )
    stimulus = encoder.encode(state)
    print(
        json.dumps(
            {
                "stimulated_neurons": len(stimulus),
                "aggregate_rate_hz": round(stimulus.total_rate_hz, 3),
                "unmapped_inputs": stimulus.unmapped_inputs,
                "channels": [
                    {
                        "channel": channel.channel,
                        "population": channel.population,
                        "neurons": len(channel.neuron_ids),
                        "aggregate_rate_hz": round(channel.total_rate_hz, 3),
                        "strength": round(channel.strength, 4),
                    }
                    for channel in stimulus.channels
                ],
            },
            sort_keys=True,
        )
    )

    if args.encode_only:
        return
    brain = BrainRuntime(
        data_dir=args.data_dir,
        codegen_target=args.codegen_target,
        seed=783,
    )
    stimulus.apply(brain)
    result = brain.step(50)
    print(
        json.dumps(
            {
                "simulation_time_ms": result.simulation_time_ms,
                "wall_time_ms": round(result.wall_time_ms, 3),
                "input_spikes": result.generated_input_spike_count,
                "output_spikes": len(result.spikes),
                "active_neurons": result.active_neuron_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
