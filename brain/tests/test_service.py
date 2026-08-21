from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import numpy as np
import pytest

from flycraft_brain import BrainStepResult, MotorCommand, NeuronStimulus, SpikeBatch
from flycraft_brain.service import (
    BrainController,
    BrainWebSocketService,
    MotorResponse,
    ProtocolError,
    SensoryFrame,
    ServiceTelemetry,
)


def valid_payload():
    return {
        "type": "sensory_frame",
        "protocol_version": 1,
        "request_id": 42,
        "sent_at_ms": 1_000,
        "step_ms": 50,
        "sensors": {
            "light": 12,
            "food_distance": 4.8,
            "food_angle": -0.31,
            "obstacle_front": 0.7,
            "obstacle_left": 3.1,
            "obstacle_right": 2.4,
            "touch": False,
            "damage": True,
            "in_water": False,
        },
    }


def test_sensory_frame_parses_strict_v1_message():
    frame = SensoryFrame.from_json(json.dumps(valid_payload()))

    assert frame.request_id == 42
    assert frame.step_ms == 50
    assert frame.sensors.damage is True
    assert frame.sensors.food_distance == pytest.approx(4.8)


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda payload: payload.update(protocol_version=2), "unsupported_version"),
        (lambda payload: payload.update(extra=True), "invalid_message"),
        (
            lambda payload: payload["sensors"].update(touch=1),
            "invalid_field",
        ),
        (lambda payload: payload.update(step_ms=250), "invalid_field"),
    ],
)
def test_sensory_frame_rejects_invalid_messages(mutate, code):
    payload = valid_payload()
    mutate(payload)

    with pytest.raises(ProtocolError) as error:
        SensoryFrame.from_json(json.dumps(payload))

    assert error.value.code == code


def test_motor_response_serializes_protocol_shape():
    response = MotorResponse(
        request_id=9,
        command=MotorCommand(forward=0.5, yaw=-0.2, escape=False),
        telemetry=ServiceTelemetry(
            simulation_time_ms=50,
            brain_wall_time_ms=200,
            round_trip_server_ms=205,
            input_spikes=10,
            output_spikes=20,
            active_neurons=7,
            stimulated_neurons=5,
            aggregate_stimulus_rate_hz=100,
            descending_rate_hz=2,
            sensory_channel_rates_hz={"light": 50.0},
            motor_population_rates_hz={"motor_forward_dnp09": 12.0},
            motor_side_rates_hz={"motor_turning_dna02": {"left": 1.0, "right": 3.0}},
            unmapped_inputs=(),
        ),
    )

    payload = json.loads(response.to_json())

    assert payload["type"] == "motor_command"
    assert payload["protocol_version"] == 1
    assert payload["request_id"] == 9
    assert payload["command"]["yaw"] == pytest.approx(-0.2)
    assert set(payload["command"]) == {"forward", "yaw", "escape"}
    assert payload["telemetry"]["sensory_channel_rates_hz"] == {"light": 50.0}
    assert payload["telemetry"]["motor_population_rates_hz"] == {
        "motor_forward_dnp09": 12.0
    }


class FakeEncoder:
    def encode(self, sensors):
        self.sensors = sensors
        return NeuronStimulus(
            neuron_ids=np.array([101], dtype=np.int64),
            rates_hz=np.array([20.0]),
            unmapped_inputs=("test-unmapped",),
        )


class FakeBrain:
    def __init__(self):
        self.stimulated = None

    def stimulate(self, neuron_ids, intensity):
        self.stimulated = (neuron_ids.copy(), intensity.copy())

    def step(self, duration_ms):
        return BrainStepResult(
            spikes=SpikeBatch(
                neuron_ids=np.array([201], dtype=np.int64),
                neuron_indices=np.array([0], dtype=np.int32),
                times_ms=np.array([10.0]),
            ),
            duration_ms=duration_ms,
            simulation_time_ms=duration_ms,
            wall_time_ms=123.0,
            stimulated_neuron_count=1,
            generated_input_spike_count=3,
        )


class FakeDecoder:
    def decode(self, result):
        self.result = result
        self.last_trace = SimpleNamespace(
            descending_rate_hz=7.5,
            population_rates_hz={"motor_forward_dnp09": 12.0},
            side_rates_hz={"motor_turning_dna02": {"left": 1.0, "right": 3.0}},
        )
        return MotorCommand(forward=0.4, yaw=0.1, escape=False)


def test_brain_controller_runs_end_to_end_pipeline():
    encoder = FakeEncoder()
    brain = FakeBrain()
    decoder = FakeDecoder()
    controller = BrainController(encoder, brain, decoder)
    frame = SensoryFrame.from_json(json.dumps(valid_payload()))

    response = controller.process(frame)

    assert response.request_id == 42
    assert response.command.forward == pytest.approx(0.4)
    assert brain.stimulated[0].tolist() == [101]
    assert response.telemetry.output_spikes == 1
    assert response.telemetry.input_spikes == 3
    assert response.telemetry.descending_rate_hz == pytest.approx(7.5)
    assert response.telemetry.motor_population_rates_hz == {"motor_forward_dnp09": 12.0}
    assert response.telemetry.motor_side_rates_hz == {
        "motor_turning_dna02": {"left": 1.0, "right": 3.0}
    }
    assert response.telemetry.unmapped_inputs == ("test-unmapped",)


def test_websocket_service_returns_structured_protocol_error():
    service = BrainWebSocketService(
        BrainController(FakeEncoder(), FakeBrain(), FakeDecoder())
    )

    response = json.loads(asyncio.run(service.process_text("not-json")))

    assert response["type"] == "error"
    assert response["code"] == "invalid_json"
    assert response["request_id"] is None


def test_websocket_service_returns_motor_response():
    service = BrainWebSocketService(
        BrainController(FakeEncoder(), FakeBrain(), FakeDecoder())
    )

    response = json.loads(
        asyncio.run(service.process_text(json.dumps(valid_payload())))
    )

    assert response["type"] == "motor_command"
    assert response["request_id"] == 42
    assert response["command"]["forward"] == pytest.approx(0.4)
