from __future__ import annotations

from dataclasses import dataclass
from math import sin

import numpy as np
import pandas as pd

from flycraft_brain.connectome import CodexMetadata, PopulationCatalog

from .models import ChannelEncoding, NeuronStimulus, SensoryState


@dataclass(frozen=True, slots=True)
class SensoryEncoderConfig:
    obstacle_range: float = 8.0
    food_range: float = 16.0
    gustatory_contact_range: float = 0.75
    light_budget_hz: float = 1_500.0
    looming_lplc2_budget_hz: float = 3_000.0
    looming_lc4_budget_hz: float = 2_000.0
    olfactory_budget_hz: float = 2_500.0
    gustatory_budget_hz: float = 1_500.0
    touch_budget_hz: float = 2_000.0
    damage_budget_hz: float = 5_000.0
    max_neuron_rate_hz: float = 500.0

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} must be finite and positive")


class SensoryEncoder:
    """Engineered Minecraft-to-FAFB optogenetic-rate encoder.

    Population membership comes from Codex annotations. Signal transforms,
    aggregate rate budgets, and hemisphere weighting are engineering choices.
    """

    POPULATIONS = (
        "sensory_visual_ocellar",
        "sensory_visual_looming_lplc2",
        "sensory_visual_looming_lc4",
        "sensory_olfactory",
        "sensory_gustatory_sugar_water",
        "sensory_mechanosensory",
    )

    def __init__(
        self,
        metadata: CodexMetadata,
        catalog: PopulationCatalog | None = None,
        *,
        config: SensoryEncoderConfig | None = None,
    ) -> None:
        self.metadata = metadata
        self.catalog = catalog or PopulationCatalog.load()
        self.config = config or SensoryEncoderConfig()
        self._populations = {
            name: self.catalog.resolve(metadata, name) for name in self.POPULATIONS
        }
        empty = [name for name, rows in self._populations.items() if rows.empty]
        if empty:
            raise ValueError(
                f"Encoder population(s) resolved empty: {', '.join(empty)}"
            )

    def encode(self, state: SensoryState) -> NeuronStimulus:
        channels: list[ChannelEncoding] = []

        light_strength = state.light / 15.0
        self._append_channel(
            channels,
            channel="light",
            population="sensory_visual_ocellar",
            source_value=state.light,
            strength=light_strength,
            budget_hz=self.config.light_budget_hz,
            assumption=(
                "Minecraft block light is normalized to an aggregate ocellar "
                "input budget; this is not a calibrated luminance response."
            ),
        )

        front = self._proximity(state.obstacle_front, self.config.obstacle_range)
        left = max(
            front, self._proximity(state.obstacle_left, self.config.obstacle_range)
        )
        right = max(
            front, self._proximity(state.obstacle_right, self.config.obstacle_range)
        )
        looming_strength = max(left, right)
        side_weights = self._normalized_side_weights(left, right)
        nearest_obstacle = self._nearest(
            state.obstacle_front, state.obstacle_left, state.obstacle_right
        )
        for population, budget_hz, cell_type in (
            (
                "sensory_visual_looming_lplc2",
                self.config.looming_lplc2_budget_hz,
                "LPLC2",
            ),
            (
                "sensory_visual_looming_lc4",
                self.config.looming_lc4_budget_hz,
                "LC4",
            ),
        ):
            self._append_channel(
                channels,
                channel=f"obstacle_{cell_type.lower()}",
                population=population,
                source_value=nearest_obstacle
                if nearest_obstacle is not None
                else False,
                strength=looming_strength,
                budget_hz=budget_hz,
                side_weights=side_weights,
                assumption=(
                    f"Static Minecraft obstacle proximity drives {cell_type} looming "
                    "candidates. Real looming selectivity depends on visual expansion "
                    "dynamics; annotation side is used as a hemisphere proxy."
                ),
            )

        food_strength = self._proximity(state.food_distance, self.config.food_range)
        lateral_signal = sin(state.food_angle)
        food_side_weights = ((1.0 - lateral_signal) / 2.0, (1.0 + lateral_signal) / 2.0)
        self._append_channel(
            channels,
            channel="food_olfactory",
            population="sensory_olfactory",
            source_value=state.food_distance
            if state.food_distance is not None
            else False,
            strength=food_strength,
            budget_hz=self.config.olfactory_budget_hz,
            side_weights=food_side_weights,
            assumption=(
                "Flower distance is an engineered odor-strength proxy with negative "
                "angles weighted left and positive angles right; no odor identity is modeled."
            ),
        )

        gustatory_strength = self._proximity(
            state.food_distance, self.config.gustatory_contact_range
        )
        self._append_channel(
            channels,
            channel="food_gustatory",
            population="sensory_gustatory_sugar_water",
            source_value=state.food_distance
            if state.food_distance is not None
            else False,
            strength=gustatory_strength,
            budget_hz=self.config.gustatory_budget_hz,
            side_weights=food_side_weights,
            assumption=(
                "Food within the configured contact range drives annotated sugar/water "
                "gustatory neurons; Minecraft flowers have no measured fly tastant concentration."
            ),
        )

        if state.touch:
            self._append_channel(
                channels,
                channel="touch",
                population="sensory_mechanosensory",
                source_value=True,
                strength=1.0,
                budget_hz=self.config.touch_budget_hz,
                assumption=(
                    "Minecraft collision is distributed over the broad mechanosensory class; "
                    "contact location and receptor subtype are unavailable."
                ),
            )
        if state.damage:
            self._append_channel(
                channels,
                channel="damage",
                population="sensory_mechanosensory",
                source_value=True,
                strength=1.0,
                budget_hz=self.config.damage_budget_hz,
                assumption=(
                    "No nociceptive population was identified in the pinned Codex taxonomy. "
                    "Damage therefore reuses mechanosensory neurons as an explicit proxy."
                ),
            )

        unmapped = ()
        if state.in_water:
            unmapped = (
                "in_water: no FAFB v783 water-immersion population is mapped; input omitted",
            )

        return self._aggregate(channels, unmapped)

    def _append_channel(
        self,
        channels: list[ChannelEncoding],
        *,
        channel: str,
        population: str,
        source_value: float | bool,
        strength: float,
        budget_hz: float,
        assumption: str,
        side_weights: tuple[float, float] | None = None,
    ) -> None:
        strength = float(np.clip(strength, 0.0, 1.0))
        if strength == 0:
            return
        rows = self._populations[population]
        weights = self._neuron_weights(rows, side_weights)
        if weights.sum() == 0:
            return
        rates_hz = budget_hz * strength * weights / weights.sum()
        channels.append(
            ChannelEncoding(
                channel=channel,
                population=population,
                neuron_ids=rows["root_id"].to_numpy(dtype=np.int64),
                rates_hz=rates_hz,
                source_value=source_value,
                strength=strength,
                assumption=assumption,
            )
        )

    @staticmethod
    def _neuron_weights(
        rows: pd.DataFrame, side_weights: tuple[float, float] | None
    ) -> np.ndarray:
        if side_weights is None:
            return np.ones(len(rows), dtype=np.float64)
        left_weight, right_weight = side_weights
        sides = rows["side"].astype("string").str.casefold()
        is_left = sides.eq("left").fillna(False).to_numpy(dtype=bool)
        is_right = sides.eq("right").fillna(False).to_numpy(dtype=bool)
        fallback = (left_weight + right_weight) / 2.0
        return np.where(
            is_left,
            left_weight,
            np.where(is_right, right_weight, fallback),
        ).astype(np.float64)

    def _aggregate(
        self,
        channels: list[ChannelEncoding],
        unmapped_inputs: tuple[str, ...],
    ) -> NeuronStimulus:
        if not channels:
            return NeuronStimulus(
                neuron_ids=np.empty(0, dtype=np.int64),
                rates_hz=np.empty(0, dtype=np.float64),
                channels=(),
                unmapped_inputs=unmapped_inputs,
            )
        all_ids = np.concatenate([channel.neuron_ids for channel in channels])
        all_rates = np.concatenate([channel.rates_hz for channel in channels])
        neuron_ids, inverse = np.unique(all_ids, return_inverse=True)
        rates_hz = np.zeros(neuron_ids.size, dtype=np.float64)
        np.add.at(rates_hz, inverse, all_rates)
        np.clip(rates_hz, 0.0, self.config.max_neuron_rate_hz, out=rates_hz)
        active = rates_hz > 0
        return NeuronStimulus(
            neuron_ids=neuron_ids[active],
            rates_hz=rates_hz[active],
            channels=tuple(channels),
            unmapped_inputs=unmapped_inputs,
        )

    @staticmethod
    def _proximity(distance: float | None, maximum_distance: float) -> float:
        if distance is None:
            return 0.0
        return float(np.clip(1.0 - distance / maximum_distance, 0.0, 1.0))

    @staticmethod
    def _normalized_side_weights(left: float, right: float) -> tuple[float, float]:
        maximum = max(left, right)
        if maximum == 0:
            return 0.0, 0.0
        return left / maximum, right / maximum

    @staticmethod
    def _nearest(*distances: float | None) -> float | None:
        present = [distance for distance in distances if distance is not None]
        return min(present) if present else None
