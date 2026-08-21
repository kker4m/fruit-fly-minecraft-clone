from __future__ import annotations

import pandas as pd
import pytest

from flycraft_brain.sensory import SensoryEncoder, SensoryEncoderConfig, SensoryState


class FakeCatalog:
    POPULATIONS = {
        "sensory_visual_ocellar": [(1, "left"), (2, "right")],
        "sensory_visual_looming_lplc2": [(3, "left"), (4, "right")],
        "sensory_visual_looming_lc4": [(5, "left"), (6, "right")],
        "sensory_olfactory": [(7, "left"), (8, "right")],
        "sensory_gustatory_sugar_water": [(9, "left"), (10, "right")],
        "sensory_mechanosensory": [(11, "left"), (12, "right")],
    }

    def resolve(self, metadata, name):
        return pd.DataFrame(self.POPULATIONS[name], columns=["root_id", "side"])


@pytest.fixture()
def encoder():
    return SensoryEncoder(
        metadata=object(),
        catalog=FakeCatalog(),
        config=SensoryEncoderConfig(max_neuron_rate_hz=10_000.0),
    )


def test_zero_state_produces_no_stimulation_and_reports_unmapped_water(encoder):
    quiet = encoder.encode(SensoryState())
    water = encoder.encode(SensoryState(in_water=True))

    assert len(quiet) == 0
    assert quiet.channels == ()
    assert len(water) == 0
    assert water.unmapped_inputs == (
        "in_water: no FAFB v783 water-immersion population is mapped; input omitted",
    )


def test_light_uses_ocellar_population_and_aggregate_budget(encoder):
    stimulus = encoder.encode(SensoryState(light=15))

    assert stimulus.neuron_ids.tolist() == [1, 2]
    assert stimulus.total_rate_hz == pytest.approx(1_500.0)
    assert [channel.channel for channel in stimulus.channels] == ["light"]


def test_left_obstacle_lateralizes_both_looming_populations(encoder):
    stimulus = encoder.encode(SensoryState(obstacle_left=0.0))

    assert stimulus.neuron_ids.tolist() == [3, 5]
    assert stimulus.total_rate_hz == pytest.approx(5_000.0)
    assert {channel.population for channel in stimulus.channels} == {
        "sensory_visual_looming_lplc2",
        "sensory_visual_looming_lc4",
    }


def test_food_distance_and_angle_drive_olfactory_and_contact_gustatory(encoder):
    stimulus = encoder.encode(SensoryState(food_distance=0.0, food_angle=-1.5707963268))

    assert stimulus.neuron_ids.tolist() == [7, 9]
    assert stimulus.total_rate_hz == pytest.approx(4_000.0)
    assert [channel.channel for channel in stimulus.channels] == [
        "food_olfactory",
        "food_gustatory",
    ]


def test_touch_and_damage_share_proxy_population_and_sum_rates(encoder):
    stimulus = encoder.encode(SensoryState(touch=True, damage=True))

    assert stimulus.neuron_ids.tolist() == [11, 12]
    assert stimulus.rates_hz.tolist() == pytest.approx([3_500.0, 3_500.0])
    assert [channel.channel for channel in stimulus.channels] == ["touch", "damage"]
    assert "No nociceptive population" in stimulus.channels[1].assumption


def test_stimulus_applies_rates_to_runtime_compatible_target(encoder):
    stimulus = encoder.encode(SensoryState(light=15))

    class Target:
        def stimulate(self, neuron_ids, intensity):
            self.neuron_ids = neuron_ids
            self.intensity = intensity

    target = Target()
    stimulus.apply(target)

    assert target.neuron_ids.tolist() == [1, 2]
    assert target.intensity.tolist() == pytest.approx([750.0, 750.0])


def test_missing_side_uses_bilateral_fallback_weight():
    rows = pd.DataFrame({"side": ["left", "right", pd.NA]})

    weights = SensoryEncoder._neuron_weights(rows, (1.0, 0.0))

    assert weights.tolist() == pytest.approx([1.0, 0.0, 0.5])


@pytest.mark.parametrize(
    "state",
    [
        SensoryState(light=0),
        SensoryState(food_angle=0),
    ],
)
def test_valid_boundary_states_construct(state):
    assert isinstance(state, SensoryState)


def test_invalid_sensor_ranges_are_rejected():
    with pytest.raises(ValueError, match="light"):
        SensoryState(light=16)
    with pytest.raises(ValueError, match="obstacle_front"):
        SensoryState(obstacle_front=-1)
