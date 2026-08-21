#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flycraft_brain import BrainRuntime

UPSTREAM_SUGAR_GRNS = [
    720575940624963786,
    720575940630233916,
    720575940637568838,
    720575940638202345,
    720575940617000768,
    720575940630797113,
    720575940632889389,
    720575940621754367,
    720575940621502051,
    720575940640649691,
    720575940639332736,
    720575940616885538,
    720575940639198653,
    720575940639259967,
    720575940617937543,
    720575940632425919,
    720575940633143833,
    720575940612670570,
    720575940628853239,
    720575940629176663,
    720575940611875570,
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run two persistent 50 ms brain steps")
    parser.add_argument("--data-dir", type=Path, default=Path("data/fly-brain"))
    parser.add_argument(
        "--codegen-target", choices=("cython", "numpy"), default="cython"
    )
    args = parser.parse_args()

    brain = BrainRuntime(
        data_dir=args.data_dir,
        codegen_target=args.codegen_target,
        seed=783,
    )
    brain.stimulate(neuron_ids=UPSTREAM_SUGAR_GRNS, intensity=200.0)

    for step_number in (1, 2):
        result = brain.step(50)
        print(
            json.dumps(
                {
                    "step": step_number,
                    "simulation_time_ms": result.simulation_time_ms,
                    "wall_time_ms": round(result.wall_time_ms, 3),
                    "spikes": len(result.spikes),
                    "active_neurons": result.active_neuron_count,
                    "input_spikes": result.generated_input_spike_count,
                    "first_spike": (
                        {
                            "flywire_id": int(result.spikes.neuron_ids[0]),
                            "time_ms": float(result.spikes.times_ms[0]),
                        }
                        if len(result.spikes)
                        else None
                    ),
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
