from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Mapping

from flycraft_brain.motor import MotorCommand
from flycraft_brain.sensory import SensoryState

PROTOCOL_VERSION = 1


class ProtocolError(ValueError):
    def __init__(
        self, code: str, message: str, *, request_id: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id


@dataclass(frozen=True, slots=True)
class SensoryFrame:
    request_id: int
    sent_at_ms: int
    step_ms: float
    sensors: SensoryState

    @classmethod
    def from_json(cls, message: str) -> SensoryFrame:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError as error:
            raise ProtocolError("invalid_json", str(error)) from error
        if not isinstance(payload, dict):
            raise ProtocolError("invalid_message", "message must be a JSON object")
        request_id = payload.get("request_id")
        request_id_for_error = request_id if type(request_id) is int else None
        cls._require_exact_keys(
            payload,
            {
                "type",
                "protocol_version",
                "request_id",
                "sent_at_ms",
                "step_ms",
                "sensors",
            },
            request_id_for_error,
        )
        if payload["type"] != "sensory_frame":
            raise ProtocolError(
                "unsupported_type",
                "type must be 'sensory_frame'",
                request_id=request_id_for_error,
            )
        if payload["protocol_version"] != PROTOCOL_VERSION:
            raise ProtocolError(
                "unsupported_version",
                f"protocol_version must be {PROTOCOL_VERSION}",
                request_id=request_id_for_error,
            )
        cls._require_non_negative_int("request_id", request_id)
        cls._require_non_negative_int("sent_at_ms", payload["sent_at_ms"])
        step_ms = cls._require_number("step_ms", payload["step_ms"])
        if not 0 < step_ms <= 200:
            raise ProtocolError(
                "invalid_field",
                "step_ms must be within (0, 200]",
                request_id=request_id,
            )
        sensors = cls._parse_sensors(payload["sensors"], request_id)
        return cls(
            request_id=request_id,
            sent_at_ms=payload["sent_at_ms"],
            step_ms=step_ms,
            sensors=sensors,
        )

    @staticmethod
    def _parse_sensors(payload: Any, request_id: int) -> SensoryState:
        if not isinstance(payload, dict):
            raise ProtocolError(
                "invalid_field", "sensors must be an object", request_id=request_id
            )
        expected = {
            "light",
            "food_distance",
            "food_angle",
            "obstacle_front",
            "obstacle_left",
            "obstacle_right",
            "touch",
            "damage",
            "in_water",
        }
        SensoryFrame._require_exact_keys(payload, expected, request_id)
        for field_name in ("touch", "damage", "in_water"):
            if type(payload[field_name]) is not bool:
                raise ProtocolError(
                    "invalid_field",
                    f"{field_name} must be boolean",
                    request_id=request_id,
                )
        try:
            return SensoryState(
                light=SensoryFrame._require_number("light", payload["light"]),
                food_distance=SensoryFrame._optional_number(
                    "food_distance", payload["food_distance"]
                ),
                food_angle=SensoryFrame._require_number(
                    "food_angle", payload["food_angle"]
                ),
                obstacle_front=SensoryFrame._optional_number(
                    "obstacle_front", payload["obstacle_front"]
                ),
                obstacle_left=SensoryFrame._optional_number(
                    "obstacle_left", payload["obstacle_left"]
                ),
                obstacle_right=SensoryFrame._optional_number(
                    "obstacle_right", payload["obstacle_right"]
                ),
                touch=payload["touch"],
                damage=payload["damage"],
                in_water=payload["in_water"],
            )
        except ValueError as error:
            raise ProtocolError(
                "invalid_field", str(error), request_id=request_id
            ) from error

    @staticmethod
    def _require_exact_keys(
        payload: dict[str, Any], expected: set[str], request_id: int | None
    ) -> None:
        actual = set(payload)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ProtocolError(
                "invalid_message",
                f"message keys mismatch; missing={missing}, extra={extra}",
                request_id=request_id,
            )

    @staticmethod
    def _require_non_negative_int(field_name: str, value: Any) -> None:
        if type(value) is not int or value < 0:
            raise ProtocolError(
                "invalid_field", f"{field_name} must be a non-negative integer"
            )

    @staticmethod
    def _require_number(field_name: str, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ProtocolError("invalid_field", f"{field_name} must be numeric")
        value = float(value)
        if not isfinite(value):
            raise ProtocolError("invalid_field", f"{field_name} must be finite")
        return value

    @staticmethod
    def _optional_number(field_name: str, value: Any) -> float | None:
        if value is None:
            return None
        return SensoryFrame._require_number(field_name, value)


@dataclass(frozen=True, slots=True)
class ServiceTelemetry:
    simulation_time_ms: float
    brain_wall_time_ms: float
    round_trip_server_ms: float
    input_spikes: int
    output_spikes: int
    active_neurons: int
    stimulated_neurons: int
    aggregate_stimulus_rate_hz: float
    descending_rate_hz: float
    sensory_channel_rates_hz: Mapping[str, float]
    motor_population_rates_hz: Mapping[str, float]
    motor_side_rates_hz: Mapping[str, Mapping[str, float]]
    unmapped_inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MotorResponse:
    request_id: int
    command: MotorCommand
    telemetry: ServiceTelemetry

    def to_json(self) -> str:
        return json.dumps(
            {
                "type": "motor_command",
                "protocol_version": PROTOCOL_VERSION,
                "request_id": self.request_id,
                "command": asdict(self.command),
                "telemetry": asdict(self.telemetry),
            },
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class ErrorResponse:
    request_id: int | None
    code: str
    message: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "type": "error",
                "protocol_version": PROTOCOL_VERSION,
                "request_id": self.request_id,
                "code": self.code,
                "message": self.message,
            },
            separators=(",", ":"),
        )
