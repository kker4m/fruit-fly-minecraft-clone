from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from flycraft_brain import (
    BrainStepResult,
    MotorCommand,
    MotorDecoder,
    MotorDecoderConfig,
    SpikeBatch,
)


class FakeCatalog:
    POPULATIONS = {
        "motor_descending_all": [
            (1, "left"),
            (2, "right"),
            (3, "left"),
            (4, "right"),
            (5, "left"),
            (6, "right"),
            (7, "left"),
            (8, "left"),
            (9, "right"),
            (10, "right"),
            (11, "left"),
            (12, "right"),
        ],
        "motor_turning_dna01": [(1, "left"), (2, "right")],
        "motor_turning_dna02": [(3, "left"), (4, "right")],
        "motor_forward_dnp09": [(5, "left"), (6, "right")],
        "motor_backward_mdn": [
            (7, "left"),
            (8, "left"),
            (9, "right"),
            (10, "right"),
        ],
        "motor_escape_dnp01": [(11, "left"), (12, "right")],
    }

    def resolve(self, metadata, name):
        return pd.DataFrame(self.POPULATIONS[name], columns=["root_id", "side"])


@pytest.fixture()
def config():
    return MotorDecoderConfig(
        window_ms=100.0,
        rate_scale_hz=40.0,
        escape_threshold_hz=20.0,
        smoothing_alpha=1.0,
        deadzone=0.0,
    )


@pytest.fixture()
def decoder(config):
    return MotorDecoder(metadata=object(), catalog=FakeCatalog(), config=config)


def make_step(start_ms, duration_ms, spikes):
    neuron_ids = np.asarray([neuron_id for neuron_id, _ in spikes], dtype=np.int64)
    times_ms = np.asarray([time_ms for _, time_ms in spikes], dtype=np.float64)
    return BrainStepResult(
        spikes=SpikeBatch(
            neuron_ids=neuron_ids,
            neuron_indices=np.arange(len(spikes), dtype=np.int32),
            times_ms=times_ms,
        ),
        duration_ms=duration_ms,
        simulation_time_ms=start_ms + duration_ms,
        wall_time_ms=0.0,
        stimulated_neuron_count=0,
        generated_input_spike_count=0,
    )


def test_dnp09_activity_drives_forward(decoder):
    result = make_step(0, 50, [(5, 10), (5, 20), (6, 15), (6, 25)])

    command = decoder.decode(result)

    assert command == MotorCommand(forward=1.0, yaw=0.0, escape=False)
    assert decoder.last_trace.population_rates_hz["forward_dnp09"] == pytest.approx(
        40.0
    )


def test_right_minus_left_dna_activity_controls_yaw(config):
    right_decoder = MotorDecoder(object(), FakeCatalog(), config=config)
    left_decoder = MotorDecoder(object(), FakeCatalog(), config=config)

    right = right_decoder.decode(make_step(0, 50, [(4, 10), (4, 20)]))
    left = left_decoder.decode(make_step(0, 50, [(3, 10), (3, 20)]))

    assert right.yaw == pytest.approx(0.65)
    assert left.yaw == pytest.approx(-0.65)


def test_mdn_activity_subtracts_forward_drive(decoder):
    spikes = [
        (5, 10),
        (5, 20),
        (6, 15),
        (6, 25),
        (7, 10),
        (7, 20),
        (8, 10),
        (8, 20),
        (9, 10),
        (9, 20),
        (10, 10),
        (10, 20),
    ]

    command = decoder.decode(make_step(0, 50, spikes))

    assert command.forward == pytest.approx(0.0)


def test_giant_fiber_activity_triggers_escape(decoder):
    command = decoder.decode(make_step(0, 50, [(12, 10)]))

    assert command.escape is True
    assert command.forward == 0.0


def test_rolling_window_retains_then_expires_spikes(decoder):
    first = decoder.decode(make_step(0, 50, [(5, 10), (5, 20), (6, 15), (6, 25)]))
    second = decoder.decode(make_step(50, 50, []))
    third = decoder.decode(make_step(100, 50, []))

    assert first.forward == pytest.approx(1.0)
    assert second.forward == pytest.approx(0.5)
    assert third.forward == pytest.approx(0.0)


def test_non_contiguous_or_duplicate_steps_are_rejected(decoder):
    decoder.decode(make_step(0, 50, []))

    with pytest.raises(ValueError, match="contiguous"):
        decoder.decode(make_step(60, 50, []))


def test_floating_point_noise_at_step_boundaries_is_accepted(decoder):
    start_ms = 100.0
    end_ms = 150.0
    result = make_step(
        start_ms,
        end_ms - start_ms,
        [
            (5, np.nextafter(start_ms, -np.inf)),
            (6, np.nextafter(end_ms, np.inf)),
        ],
    )

    command = decoder.decode(result)

    assert command.forward == pytest.approx(0.5)


def test_reset_discards_history_and_smoothing(decoder):
    decoder.decode(make_step(0, 50, [(5, 10), (6, 15)]))

    decoder.reset()
    command = decoder.decode(make_step(0, 50, []))

    assert command == MotorCommand(forward=0.0, yaw=0.0, escape=False)
    assert decoder.last_trace is not None


def test_motor_command_rejects_out_of_range_values():
    with pytest.raises(ValueError, match="yaw"):
        MotorCommand(forward=0.0, yaw=1.1, escape=False)
