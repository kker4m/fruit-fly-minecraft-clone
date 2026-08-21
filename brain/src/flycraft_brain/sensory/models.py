from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Protocol, Sequence

import numpy as np


class StimulusTarget(Protocol):
    def stimulate(
        self, neuron_ids: Sequence[int], intensity: float | Sequence[float]
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class SensoryState:
    light: float = 0.0
    food_distance: float | None = None
    food_angle: float = 0.0
    obstacle_front: float | None = None
    obstacle_left: float | None = None
    obstacle_right: float | None = None
    touch: bool = False
    damage: bool = False
    in_water: bool = False

    def __post_init__(self) -> None:
        if not np.isfinite(self.light) or not 0.0 <= self.light <= 15.0:
            raise ValueError("light must be finite and within Minecraft's 0..15 range")
        if not np.isfinite(self.food_angle) or not -pi <= self.food_angle <= pi:
            raise ValueError("food_angle must be finite radians within [-pi, pi]")
        for field_name in (
            "food_distance",
            "obstacle_front",
            "obstacle_left",
            "obstacle_right",
        ):
            value = getattr(self, field_name)
            if value is not None and (not np.isfinite(value) or value < 0):
                raise ValueError(
                    f"{field_name} must be None or a finite non-negative distance"
                )


@dataclass(frozen=True, slots=True)
class ChannelEncoding:
    channel: str
    population: str
    neuron_ids: np.ndarray
    rates_hz: np.ndarray
    source_value: float | bool
    strength: float
    assumption: str

    def __post_init__(self) -> None:
        neuron_ids = np.asarray(self.neuron_ids, dtype=np.int64).copy()
        rates_hz = np.asarray(self.rates_hz, dtype=np.float64).copy()
        if neuron_ids.ndim != 1 or rates_hz.shape != neuron_ids.shape:
            raise ValueError("channel neuron_ids and rates_hz must be aligned vectors")
        if np.any(~np.isfinite(rates_hz)) or np.any(rates_hz < 0):
            raise ValueError("channel rates_hz must be finite and non-negative")
        neuron_ids.setflags(write=False)
        rates_hz.setflags(write=False)
        object.__setattr__(self, "neuron_ids", neuron_ids)
        object.__setattr__(self, "rates_hz", rates_hz)

    @property
    def total_rate_hz(self) -> float:
        return float(self.rates_hz.sum())


@dataclass(frozen=True, slots=True)
class NeuronStimulus:
    neuron_ids: np.ndarray
    rates_hz: np.ndarray
    channels: tuple[ChannelEncoding, ...] = ()
    unmapped_inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        neuron_ids = np.asarray(self.neuron_ids, dtype=np.int64).copy()
        rates_hz = np.asarray(self.rates_hz, dtype=np.float64).copy()
        if neuron_ids.ndim != 1 or rates_hz.shape != neuron_ids.shape:
            raise ValueError("neuron_ids and rates_hz must be aligned vectors")
        if np.unique(neuron_ids).size != neuron_ids.size:
            raise ValueError("neuron_ids must be unique after channel aggregation")
        if np.any(~np.isfinite(rates_hz)) or np.any(rates_hz < 0):
            raise ValueError("rates_hz must be finite and non-negative")
        neuron_ids.setflags(write=False)
        rates_hz.setflags(write=False)
        object.__setattr__(self, "neuron_ids", neuron_ids)
        object.__setattr__(self, "rates_hz", rates_hz)

    def __len__(self) -> int:
        return int(self.neuron_ids.size)

    @property
    def total_rate_hz(self) -> float:
        return float(self.rates_hz.sum())

    def apply(self, target: StimulusTarget) -> None:
        target.stimulate(self.neuron_ids, self.rates_hz)
