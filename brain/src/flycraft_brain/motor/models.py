from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np


@dataclass(frozen=True, slots=True)
class MotorCommand:
    forward: float
    yaw: float
    escape: bool

    def __post_init__(self) -> None:
        for field_name in ("forward", "yaw"):
            value = getattr(self, field_name)
            if not np.isfinite(value) or not -1.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be finite and within [-1, 1]")


@dataclass(frozen=True, slots=True)
class MotorDecodeTrace:
    window_start_ms: float
    window_end_ms: float
    population_rates_hz: Mapping[str, float]
    side_rates_hz: Mapping[str, Mapping[str, float]]
    raw_forward: float
    raw_yaw: float
    descending_rate_hz: float
    assumptions: tuple[str, ...]
