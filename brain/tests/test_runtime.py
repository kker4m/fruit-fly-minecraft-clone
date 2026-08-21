from __future__ import annotations

import pandas as pd
import pytest

from flycraft_brain import BrainRuntime


@pytest.fixture()
def model_data(tmp_path):
    completeness = pd.DataFrame(
        {"Completed": [True, True, True]},
        index=pd.Index([101, 102, 103]),
    )
    completeness.to_csv(tmp_path / "2025_Completeness_783.csv")
    connectivity = pd.DataFrame(
        {
            "Presynaptic_Index": [0, 1],
            "Postsynaptic_Index": [1, 2],
            "Excitatory x Connectivity": [100, 100],
        }
    )
    connectivity.to_parquet(tmp_path / "2025_Connectivity_783.parquet")
    return tmp_path


def test_steps_preserve_network_and_return_only_new_spikes(model_data):
    brain = BrainRuntime(model_data, codegen_target="numpy", seed=7)
    network_identity = id(brain.network)
    brain.stimulate([101], intensity=10_000.0)

    first = brain.step(1.0)
    second = brain.step(1.0)

    assert id(brain.network) == network_identity
    assert first.simulation_time_ms == pytest.approx(1.0)
    assert second.simulation_time_ms == pytest.approx(2.0)
    assert len(first.spikes) > 0
    assert len(second.spikes) > 0
    assert first.spikes.times_ms.max() < 1.0
    assert second.spikes.times_ms.min() >= 1.0
    assert set(first.spikes.neuron_ids) == {101}


def test_stimulate_rejects_unknown_flywire_id(model_data):
    brain = BrainRuntime(model_data, codegen_target="numpy")

    with pytest.raises(KeyError, match="999"):
        brain.stimulate([999], intensity=200.0)


def test_empty_stimulus_clears_previous_population(model_data):
    brain = BrainRuntime(model_data, codegen_target="numpy", seed=7)
    brain.stimulate([101], intensity=10_000.0)
    brain.step(1.0)

    brain.stimulate([], intensity=0.0)
    result = brain.step(1.0)

    assert result.stimulated_neuron_count == 0
    assert result.generated_input_spike_count == 0
