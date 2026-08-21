from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from flycraft_brain.connectome import CodexMetadata, PopulationCatalog
from flycraft_brain.runtime import BrainStepResult

from .models import MotorCommand, MotorDecodeTrace


@dataclass(frozen=True, slots=True)
class MotorDecoderConfig:
    window_ms: float = 100.0
    rate_scale_hz: float = 100.0
    escape_threshold_hz: float = 20.0
    dna01_yaw_gain: float = 0.35
    dna02_yaw_gain: float = 0.65
    backward_gain: float = 1.0
    smoothing_alpha: float = 0.4
    deadzone: float = 0.03

    def __post_init__(self) -> None:
        for field_name in ("window_ms", "rate_scale_hz"):
            value = getattr(self, field_name)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} must be finite and positive")
        for field_name in (
            "escape_threshold_hz",
            "dna01_yaw_gain",
            "dna02_yaw_gain",
            "backward_gain",
            "deadzone",
        ):
            value = getattr(self, field_name)
            if not np.isfinite(value) or value < 0:
                raise ValueError(f"{field_name} must be finite and non-negative")
        if not 0 < self.smoothing_alpha <= 1:
            raise ValueError("smoothing_alpha must be within (0, 1]")
        if self.deadzone >= 1:
            raise ValueError("deadzone must be less than 1")


class MotorDecoder:
    """Persistent firing-rate decoder for metadata-backed descending neurons."""

    POPULATIONS = {
        "descending": "motor_descending_all",
        "turn_dna01": "motor_turning_dna01",
        "turn_dna02": "motor_turning_dna02",
        "forward_dnp09": "motor_forward_dnp09",
        "backward_mdn": "motor_backward_mdn",
        "escape_dnp01": "motor_escape_dnp01",
    }
    ASSUMPTIONS = (
        "DNp09/P9 activity is treated as an engineered forward-walking drive.",
        "MDN activity subtracts from forward drive as a backward-walking candidate.",
        "Positive yaw is right-minus-left DNa activity in Minecraft coordinates.",
        "DNa02 has higher steering gain than DNa01; gains are not behaviorally calibrated.",
        "DNp01/Giant Fiber activity triggers an engineered ground escape drive.",
    )

    def __init__(
        self,
        metadata: CodexMetadata,
        catalog: PopulationCatalog | None = None,
        *,
        config: MotorDecoderConfig | None = None,
    ) -> None:
        self.metadata = metadata
        self.catalog = catalog or PopulationCatalog.load()
        self.config = config or MotorDecoderConfig()
        self._population_rows = {
            key: self.catalog.resolve(metadata, catalog_name)
            for key, catalog_name in self.POPULATIONS.items()
        }
        empty = [key for key, rows in self._population_rows.items() if rows.empty]
        if empty:
            raise ValueError(f"Motor population(s) resolved empty: {', '.join(empty)}")
        self._population_ids = {
            key: rows["root_id"].to_numpy(dtype=np.int64)
            for key, rows in self._population_rows.items()
        }
        self._side_ids = {
            key: {side: self._ids_for_side(rows, side) for side in ("left", "right")}
            for key, rows in self._population_rows.items()
        }
        self._tracked_ids = self._population_ids["descending"]
        self._history_ids = np.empty(0, dtype=np.int64)
        self._history_times_ms = np.empty(0, dtype=np.float64)
        self._observation_start_ms: float | None = None
        self._last_end_ms: float | None = None
        self._smoothed = np.zeros(2, dtype=np.float64)
        self.last_trace: MotorDecodeTrace | None = None

    def decode(self, result: BrainStepResult) -> MotorCommand:
        step_end = float(result.simulation_time_ms)
        step_duration = float(result.duration_ms)
        step_start = step_end - step_duration
        self._validate_step(step_start, step_end, result)
        if self._observation_start_ms is None:
            self._observation_start_ms = step_start

        spike_ids = np.asarray(result.spikes.neuron_ids, dtype=np.int64)
        spike_times = np.clip(
            np.asarray(result.spikes.times_ms, dtype=np.float64), step_start, step_end
        )
        tracked = np.isin(spike_ids, self._tracked_ids)
        if np.any(tracked):
            self._history_ids = np.concatenate((self._history_ids, spike_ids[tracked]))
            self._history_times_ms = np.concatenate(
                (self._history_times_ms, spike_times[tracked])
            )

        window_start = max(
            self._observation_start_ms,
            step_end - self.config.window_ms,
        )
        in_window = self._history_times_ms >= window_start
        self._history_ids = self._history_ids[in_window]
        self._history_times_ms = self._history_times_ms[in_window]
        window_seconds = (step_end - window_start) / 1000.0

        population_rates = {
            key: self._rate(self._population_ids[key], window_seconds)
            for key in self.POPULATIONS
        }
        side_rates = {
            key: {side: self._rate(ids, window_seconds) for side, ids in sides.items()}
            for key, sides in self._side_ids.items()
        }

        raw_forward = np.clip(
            self._normalize(population_rates["forward_dnp09"])
            - self.config.backward_gain
            * self._normalize(population_rates["backward_mdn"]),
            -1.0,
            1.0,
        )
        dna01_delta = (
            side_rates["turn_dna01"]["right"] - side_rates["turn_dna01"]["left"]
        ) / self.config.rate_scale_hz
        dna02_delta = (
            side_rates["turn_dna02"]["right"] - side_rates["turn_dna02"]["left"]
        ) / self.config.rate_scale_hz
        raw_yaw = np.clip(
            self.config.dna01_yaw_gain * dna01_delta
            + self.config.dna02_yaw_gain * dna02_delta,
            -1.0,
            1.0,
        )
        escape_rate = max(side_rates["escape_dnp01"].values())
        escape = escape_rate >= self.config.escape_threshold_hz

        raw = np.array([raw_forward, raw_yaw], dtype=np.float64)
        alpha = self.config.smoothing_alpha
        self._smoothed = (1.0 - alpha) * self._smoothed + alpha * raw
        command_values = np.where(
            np.abs(self._smoothed) < self.config.deadzone,
            0.0,
            self._smoothed,
        )
        command_values = np.clip(command_values, -1.0, 1.0)
        command = MotorCommand(
            forward=float(command_values[0]),
            yaw=float(command_values[1]),
            escape=bool(escape),
        )
        self.last_trace = MotorDecodeTrace(
            window_start_ms=window_start,
            window_end_ms=step_end,
            population_rates_hz=population_rates,
            side_rates_hz=side_rates,
            raw_forward=float(raw_forward),
            raw_yaw=float(raw_yaw),
            descending_rate_hz=population_rates["descending"],
            assumptions=self.ASSUMPTIONS,
        )
        self._last_end_ms = step_end
        return command

    def reset(self) -> None:
        self._history_ids = np.empty(0, dtype=np.int64)
        self._history_times_ms = np.empty(0, dtype=np.float64)
        self._observation_start_ms = None
        self._last_end_ms = None
        self._smoothed.fill(0.0)
        self.last_trace = None

    def _validate_step(
        self,
        step_start: float,
        step_end: float,
        result: BrainStepResult,
    ) -> None:
        if (
            not np.isfinite(step_start)
            or not np.isfinite(step_end)
            or step_end <= step_start
        ):
            raise ValueError("Brain step must have a finite positive time interval")
        if self._last_end_ms is not None and not np.isclose(
            step_start, self._last_end_ms
        ):
            raise ValueError(
                "MotorDecoder requires contiguous, non-duplicated BrainStepResult windows"
            )
        times = np.asarray(result.spikes.times_ms, dtype=np.float64)
        boundary_tolerance_ms = 1e-9
        if (
            np.any(~np.isfinite(times))
            or np.any(times < step_start - boundary_tolerance_ms)
            or np.any(times > step_end + boundary_tolerance_ms)
        ):
            raise ValueError("Spike times must lie inside the decoded brain step")

    def _rate(self, neuron_ids: np.ndarray, window_seconds: float) -> float:
        if neuron_ids.size == 0 or window_seconds <= 0:
            return 0.0
        spike_count = np.count_nonzero(np.isin(self._history_ids, neuron_ids))
        return float(spike_count / (neuron_ids.size * window_seconds))

    def _normalize(self, rate_hz: float) -> float:
        return float(np.clip(rate_hz / self.config.rate_scale_hz, 0.0, 1.0))

    @staticmethod
    def _ids_for_side(rows: pd.DataFrame, side: str) -> np.ndarray:
        matches = rows["side"].astype("string").str.casefold().eq(side).fillna(False)
        return rows.loc[matches, "root_id"].to_numpy(dtype=np.int64)
