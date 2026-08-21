from __future__ import annotations

import gc
import os
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Sequence

import numpy as np
import pandas as pd
from brian2 import (
    Clock,
    Network,
    NeuronGroup,
    SpikeGeneratorGroup,
    SpikeMonitor,
    Synapses,
    ms,
    mV,
    prefs,
)


@dataclass(frozen=True, slots=True)
class SpikeBatch:
    """Spikes emitted during one call to :meth:`BrainRuntime.step`."""

    neuron_ids: np.ndarray
    neuron_indices: np.ndarray
    times_ms: np.ndarray

    def __len__(self) -> int:
        return int(self.neuron_ids.size)


@dataclass(frozen=True, slots=True)
class BrainStepResult:
    spikes: SpikeBatch
    duration_ms: float
    simulation_time_ms: float
    wall_time_ms: float
    stimulated_neuron_count: int
    generated_input_spike_count: int

    @property
    def active_neuron_count(self) -> int:
        return int(np.unique(self.spikes.neuron_ids).size)


class BrainRuntime:
    """Persistent Brian2 runtime for the Eon Systems FAFB v783 LIF model.

    ``neuron_ids`` are FlyWire root IDs, not Brian2's contiguous array indices.
    Stimulation follows the upstream model's optogenetic abstraction: each input
    spike adds ``f_poi * w_syn`` to the target neuron's membrane voltage. The
    requested intensity is the Bernoulli/Poisson input rate in Hz.
    """

    _CONNECTIVITY_COLUMNS = (
        "Presynaptic_Index",
        "Postsynaptic_Index",
        "Excitatory x Connectivity",
    )

    def __init__(
        self,
        data_dir: str | Path | None = None,
        *,
        codegen_target: str = "cython",
        seed: int | None = None,
        dt_ms: float = 0.1,
    ) -> None:
        self.data_dir = self._resolve_data_dir(data_dir)
        self.completeness_path = self.data_dir / "2025_Completeness_783.csv"
        self.connectivity_path = self.data_dir / "2025_Connectivity_783.parquet"
        self._validate_data_files()

        if dt_ms <= 0:
            raise ValueError("dt_ms must be positive")
        if codegen_target not in {"cython", "numpy"}:
            raise ValueError("codegen_target must be 'cython' or 'numpy'")

        prefs.codegen.target = codegen_target
        self.dt_ms = float(dt_ms)
        self._rng = np.random.default_rng(seed)
        self._stimulus_indices = np.empty(0, dtype=np.int32)
        self._stimulus_rates_hz = np.empty(0, dtype=np.float64)
        self._recorded_spike_count = 0

        self._load_neuron_ids()
        self._build_network()

    @staticmethod
    def _resolve_data_dir(data_dir: str | Path | None) -> Path:
        configured = data_dir or os.environ.get("FLY_BRAIN_DATA_DIR")
        return Path(configured or "data/fly-brain").expanduser().resolve()

    def _validate_data_files(self) -> None:
        missing = [
            path.name
            for path in (self.completeness_path, self.connectivity_path)
            if not path.is_file()
        ]
        if missing:
            raise FileNotFoundError(
                f"Missing fly-brain data in {self.data_dir}: {', '.join(missing)}. "
                "Run scripts/fetch_fly_brain_data.py first."
            )

    def _load_neuron_ids(self) -> None:
        completeness = pd.read_csv(self.completeness_path, index_col=0)
        self.index_to_id = completeness.index.to_numpy(dtype=np.int64, copy=True)
        self.id_to_index = {
            int(flywire_id): index for index, flywire_id in enumerate(self.index_to_id)
        }
        del completeness

    def _build_network(self) -> None:
        self.clock = Clock(dt=self.dt_ms * ms, name="flycraft_clock*")
        equations = """
            dv/dt = (v_0 - v + g) / t_mbr : volt (unless refractory)
            dg/dt = -g / tau : volt (unless refractory)
            rfc : second
        """
        namespace = {
            "v_0": -52 * mV,
            "v_rst": -52 * mV,
            "v_th": -45 * mV,
            "t_mbr": 20 * ms,
            "tau": 5 * ms,
        }
        self.neurons = NeuronGroup(
            len(self.index_to_id),
            model=equations,
            method="linear",
            threshold="v > v_th",
            reset="v = v_rst; g = 0 * mV",
            refractory="rfc",
            namespace=namespace,
            clock=self.clock,
            name="flycraft_neurons*",
        )
        self.neurons.v = namespace["v_0"]
        self.neurons.g = 0 * mV
        self.neurons.rfc = 2.2 * ms

        connectivity = pd.read_parquet(
            self.connectivity_path,
            columns=list(self._CONNECTIVITY_COLUMNS),
        )
        self.recurrent_synapses = Synapses(
            self.neurons,
            self.neurons,
            model="w : volt",
            on_pre="g_post += w",
            delay=1.8 * ms,
            clock=self.clock,
            name="flycraft_recurrent*",
        )
        self.recurrent_synapses.connect(
            i=connectivity["Presynaptic_Index"].to_numpy(),
            j=connectivity["Postsynaptic_Index"].to_numpy(),
        )
        self.recurrent_synapses.w = (
            connectivity["Excitatory x Connectivity"].to_numpy() * 0.275 * mV
        )
        del connectivity
        gc.collect()

        self.stimulus_source = SpikeGeneratorGroup(
            len(self.index_to_id),
            indices=np.empty(0, dtype=np.int32),
            times=np.empty(0) * ms,
            clock=self.clock,
            name="flycraft_stimulus_source*",
        )
        self.stimulus_synapses = Synapses(
            self.stimulus_source,
            self.neurons,
            on_pre="v_post += 68.75 * mV",
            clock=self.clock,
            name="flycraft_stimulus_synapses*",
        )
        self.stimulus_synapses.connect(j="i")

        self.spike_monitor = SpikeMonitor(
            self.neurons,
            name="flycraft_spike_monitor*",
        )
        self.network = Network(
            self.neurons,
            self.recurrent_synapses,
            self.stimulus_source,
            self.stimulus_synapses,
            self.spike_monitor,
        )

    def stimulate(
        self,
        neuron_ids: Sequence[int],
        intensity: float | Sequence[float],
    ) -> None:
        """Replace the active stimulus set.

        ``intensity`` is one rate in Hz for every ID, or one rate per ID. Calling
        this with an empty ID sequence clears stimulation for subsequent steps.
        """

        ids = np.asarray(neuron_ids, dtype=np.int64)
        if ids.ndim != 1:
            raise ValueError("neuron_ids must be one-dimensional")
        if np.unique(ids).size != ids.size:
            raise ValueError("neuron_ids must not contain duplicates")

        rates = np.asarray(intensity, dtype=np.float64)
        if rates.ndim == 0:
            rates = np.full(ids.size, float(rates), dtype=np.float64)
        elif rates.shape != ids.shape:
            raise ValueError("intensity must be scalar or match neuron_ids")

        maximum_rate_hz = 1000.0 / self.dt_ms
        if np.any(~np.isfinite(rates)) or np.any(rates < 0):
            raise ValueError("intensity rates must be finite and non-negative")
        if np.any(rates > maximum_rate_hz):
            raise ValueError(
                f"intensity cannot exceed {maximum_rate_hz:g} Hz at "
                f"dt={self.dt_ms:g} ms"
            )

        missing = [
            int(flywire_id)
            for flywire_id in ids
            if int(flywire_id) not in self.id_to_index
        ]
        if missing:
            preview = ", ".join(str(value) for value in missing[:5])
            raise KeyError(f"Unknown FlyWire neuron ID(s): {preview}")

        nonzero = rates > 0
        previous_indices = self._stimulus_indices
        self._stimulus_indices = np.fromiter(
            (self.id_to_index[int(value)] for value in ids[nonzero]),
            dtype=np.int32,
            count=int(nonzero.sum()),
        )
        self._stimulus_rates_hz = rates[nonzero].copy()
        self.neurons.rfc[previous_indices] = 2.2 * ms
        self.neurons.rfc[self._stimulus_indices] = 0 * ms

    def step(self, duration_ms: float) -> BrainStepResult:
        """Advance the existing network and return only newly emitted spikes."""

        duration_ms = float(duration_ms)
        n_steps = int(round(duration_ms / self.dt_ms))
        if duration_ms <= 0 or not np.isclose(n_steps * self.dt_ms, duration_ms):
            raise ValueError(
                f"duration_ms must be a positive multiple of dt={self.dt_ms:g} ms"
            )

        generated_indices, generated_times = self._generate_stimulus_spikes(n_steps)
        self.stimulus_source.set_spikes(generated_indices, generated_times * ms)

        wall_start = perf_counter()
        self.network.run(duration_ms * ms)
        wall_time_ms = (perf_counter() - wall_start) * 1000.0

        spike_start = self._recorded_spike_count
        spike_end = int(self.spike_monitor.num_spikes)
        neuron_indices = np.asarray(
            self.spike_monitor.i[spike_start:spike_end], dtype=np.int32
        )
        times_ms = np.asarray(
            self.spike_monitor.t[spike_start:spike_end] / ms, dtype=np.float64
        )
        neuron_ids = self.index_to_id[neuron_indices]
        self._recorded_spike_count = spike_end

        return BrainStepResult(
            spikes=SpikeBatch(
                neuron_ids=neuron_ids,
                neuron_indices=neuron_indices,
                times_ms=times_ms,
            ),
            duration_ms=duration_ms,
            simulation_time_ms=float(self.network.t / ms),
            wall_time_ms=wall_time_ms,
            stimulated_neuron_count=int(self._stimulus_indices.size),
            generated_input_spike_count=int(generated_indices.size),
        )

    def _generate_stimulus_spikes(self, n_steps: int) -> tuple[np.ndarray, np.ndarray]:
        if self._stimulus_indices.size == 0:
            return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.float64)

        probability = self._stimulus_rates_hz * (self.dt_ms / 1000.0)
        draws = self._rng.random((self._stimulus_indices.size, n_steps))
        source_rows, time_bins = np.nonzero(draws < probability[:, None])
        indices = self._stimulus_indices[source_rows]
        start_ms = float(self.network.t / ms)
        times_ms = start_ms + time_bins.astype(np.float64) * self.dt_ms
        order = np.lexsort((times_ms, indices))
        return indices[order], times_ms[order]
