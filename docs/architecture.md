# FlyCraft architecture

## Scope and status

Stages 1–5 are implemented: persistent runtime, metadata-backed candidate populations, engineered sensory encoding, engineered motor decoding, a versioned WebSocket service, and a Paper Spider controller. Stage 6 visualization is not implemented.

## Connectome and model boundary

The pinned upstream source is `eonsystemspbc/fly-brain` commit `680b7b3d8d1134bf3cbd289b892cf5d37f097d34`.

The FAFB v783 model files contain:

- 138,639 modeled neurons in `2025_Completeness_783.csv`;
- 15,091,983 directed, neuron-pair connectivity rows;
- 54,492,922 underlying synapses (sum of the `Connectivity` column).

The runtime copies Eon's Brian2 LIF dynamics and parameters: resting/reset potential -52 mV, threshold -45 mV, 20 ms membrane time constant, 5 ms synaptic decay, 2.2 ms refractory period, 1.8 ms recurrent delay, and 0.275 mV per signed connectivity unit.

`BrainRuntime.stimulate` is not a natural Minecraft sensory transduction model. It reproduces the upstream optogenetic abstraction: a requested rate generates Bernoulli/Poisson input events; each event adds `250 × 0.275 mV` to the selected neuron's membrane potential, and selected neurons have a zero refractory period while stimulated. FlyWire root IDs are translated to the contiguous indices used by Brian2. Later sensory mappings must state which populations come from FlyWire annotations and which transforms are engineered.

A spike means that the LIF model crossed its threshold. It does not by itself establish intent, a behavioral decision, or a motor command. Later decoders will be explicitly engineered readouts of metadata-backed descending populations.

## Backend decision

Stage 1 uses Brian2 CPU.

- Brian2CUDA, NEST GPU, GeNN, and Brian2GeNN in the upstream repository require NVIDIA CUDA.
- The upstream PyTorch environment also resolves CUDA wheels and its runner is CUDA-oriented.
- RX 6700 XT does not provide CUDA. Porting these implementations to ROCm is a separate compatibility and numerical-parity project.
- Brian2 CPU is the upstream ground-truth implementation and runs on the target Ryzen/Linux system without a GPU-specific toolchain.

The upstream benchmark uses C++ standalone for a one-shot CPU trial. That path builds and runs a closed standalone program and is unsuitable for an interactive controller that changes stimulation every 50 ms. FlyCraft instead uses Brian2 runtime mode with the Cython code-generation target. The network is created once; `Network.run` advances the same membrane, conductance, refractory, delay-queue, and simulation-clock state on every `step` call.

## Persistent stimulation

A full-size `SpikeGeneratorGroup` is connected one-to-one to the modeled neurons. It has one lightweight stimulus synapse per neuron, not a second copy of the connectome. Before each step, only currently stimulated neurons receive generated input events. `set_spikes` changes future input schedules without rebuilding the 15-million-edge recurrent network.

The public Stage 1 API is:

```python
brain = BrainRuntime(data_dir="data/fly-brain", seed=783)
brain.stimulate(neuron_ids=[720575940624963786], intensity=200.0)
result = brain.step(50)
print(result.spikes)
```

`result.spikes` contains parallel NumPy arrays for FlyWire IDs, Brian2 indices, and absolute simulation times in milliseconds. Returning arrays avoids allocating one Python object per spike.

## Timing implication

Minecraft advances at 20 TPS, but CPU execution of the whole connectome is not assumed to be real-time. The controller service must eventually decouple Minecraft ticks from neural simulation steps and expose measured `wall_time_ms`. No claim of 10–20 Hz closed-loop operation is valid until it is measured on the target Ryzen 5 5500 with the final stimulus and recording populations.

## Data provenance and reproducibility

`scripts/fetch_fly_brain_data.py` downloads the two model files from the pinned upstream commit and verifies SHA-256 checksums before replacing local files. Model data stays outside Git under `data/fly-brain/`.

## Stage 2 metadata source

FlyCraft uses the public Codex FAFB v783 static tables from
`storage.googleapis.com/flywire-data/codex/data/fafb/783/`. Codex declares v783
as its current FAFB snapshot in
[`codex/data/versions.py`](https://github.com/murthylab/codex/blob/main/codex/data/versions.py).
The downloader pins SHA-256 digests for `classification.csv.gz`,
`consolidated_cell_types.csv.gz`, `neurons.csv.gz`, and `labels.csv.gz`.

Codex has 139,255 root IDs. Eon's completeness table has 138,639; every Eon ID
exists in Codex, while 616 Codex IDs are outside this model. Metadata queries
therefore default to `modeled_only=True`. This prevents a valid Codex annotation
from silently becoming an invalid `BrainRuntime` stimulus ID.

Codex software is Apache-2.0. FlyWire's terms state that cell annotations are
made available under CC-BY-NC 4.0. Bulk metadata and resolved root-ID manifests
remain local under `data/fly-brain/`; the committed population catalog stores
filters, evidence, and attribution rather than redistributing the bulk tables.

## Candidate population policy

`populations.json` distinguishes broad anatomical classes from
literature-backed canonical cell types:

- visual input: photoreceptors and ocellar sensory classes;
- looming candidates: canonical LPLC2 and LC4 primary types;
- chemical input: olfactory and sugar/water gustatory sensory classes;
- contact candidates: the mechanosensory class;
- output pool: all modeled descending neurons;
- turning candidates: canonical DNa01 and DNa02;
- forward-walking candidate: canonical DNp09/P9;
- backward-walking candidate: canonical MDN;
- escape candidate: canonical DNp01/Giant Fiber.

Canonical population filters use `primary_type`, not fuzzy text or substring
matching. `inspect_cell_type.py` intentionally searches both primary and exact
comma-separated additional aliases for annotation investigation. In particular,
`P9` does not match unrelated labels such as `aSP9`.

The resolved modeled counts for the pinned snapshot are:

| Population | Count |
|---|---:|
| visual photoreceptors | 10,616 |
| visual ocellar | 273 |
| LPLC2 | 210 |
| LC4 | 104 |
| olfactory sensory | 2,279 |
| sugar/water gustatory | 129 |
| mechanosensory | 2,662 |
| all descending | 1,301 |
| DNa01 | 2 |
| DNa02 | 2 |
| DNp09/P9 | 2 |
| MDN | 4 |
| DNp01/Giant Fiber | 2 |

These are candidate channels, not finished encoders or decoders. Minecraft
obstacle distance is not equivalent to a looming stimulus, and a DNp01 spike is
not automatically an `escape=true` command. Stage 3 defines the sensory
transforms as explicit engineering policy; Stage 4 must still define and
calibrate the engineered spike readouts.

## Stage 3 sensory encoding

`SensoryEncoder` resolves six versioned metadata populations once at startup and
converts each `SensoryState` frame into one aggregated `NeuronStimulus`.
`NeuronStimulus.rates_hz` is the rate parameter consumed by Eon's optogenetic
input abstraction. It is not injected physical current and is not a measured
sensory-neuron transfer function.

Distance channels use:

$$
p(d; D) = \operatorname{clip}(1 - d/D, 0, 1)
$$

where absent observations have zero strength. Light uses
$p_{light}=light/15$. A channel with aggregate budget $B$, strength $s$, and
per-neuron laterality weights $w_i$ assigns:

$$
r_i = B s \frac{w_i}{\sum_j w_j}
$$

This population-budget invariant is deliberate: adding annotation-complete
neurons does not multiply total external drive. Rates from overlapping channels
are summed by root ID and capped at 500 Hz per neuron.

Default engineered budgets:

| Channel | Metadata population | Aggregate max rate |
|---|---|---:|
| light | ocellar visual sensory | 1,500 Hz |
| obstacle size candidate | LPLC2 | 3,000 Hz |
| obstacle expansion candidate | LC4 | 2,000 Hz |
| food odor proxy | olfactory sensory | 2,500 Hz |
| food contact proxy | sugar/water gustatory | 1,500 Hz |
| touch proxy | mechanosensory | 2,000 Hz |
| damage proxy | mechanosensory | 5,000 Hz |

Obstacle range defaults to 8 blocks. Front proximity drives both annotated
sides; left/right observations weight their corresponding side. Food range
defaults to 16 blocks and its side weights are
$(1-\sin\theta)/2$ left and $(1+\sin\theta)/2$ right, with negative angles
defined as left. Sugar/water gustatory drive is limited to a 0.75-block contact
range.

The side transform uses Codex annotation side as a hemisphere proxy. It is not
a receptive-field map. Static Minecraft distance also lacks the expansion
velocity needed to call the LPLC2/LC4 input a biological looming stimulus.

No explicit nociceptive population was found in the pinned classification or
label search. `damage` therefore adds a stronger drive to the same broad
mechanosensory population as `touch`, and its trace records that proxy.
`in_water` is deliberately omitted rather than assigned to an invented neuron
group; the omission appears in `NeuronStimulus.unmapped_inputs`.

Each channel retains population name, source value, strength, member IDs,
distributed rates, and its scientific assumption. This trace is intended for
the later live visualization and prevents the aggregate stimulus from hiding
engineered mappings.

## Stage 4 motor decoding

`MotorDecoder` is stateful. It accepts contiguous, non-duplicated
`BrainStepResult` objects, retains only modeled descending-neuron spikes, and
computes population firing rates over a 100 ms rolling window:

$$
R_P = \frac{N_{spikes,P}}{N_{neurons,P}\,T_{window}}
$$

The first window uses only elapsed observed time, rather than pretending that
unobserved history contained zero spikes. A gap or duplicate result is rejected
because either would bias rate estimates.

With $n(r)=\operatorname{clip}(r/100\text{ Hz},0,1)$, default raw readouts are:

$$
forward = \operatorname{clip}(n(R_{DNp09}) - n(R_{MDN}), -1, 1)
$$

$$
yaw = \operatorname{clip}\left(
0.35\frac{R_{DNa01,R}-R_{DNa01,L}}{100\text{ Hz}} +
0.65\frac{R_{DNa02,R}-R_{DNa02,L}}{100\text{ Hz}},
-1,1\right)
$$

`escape` becomes true immediately when either DNp01 side reaches 20 Hz.
`forward` and `yaw` use exponential smoothing
$x_t=0.6x_{t-1}+0.4x_{raw}$ followed by a 0.03 dead zone. Their ranges are
`[-1, 1]`; positive yaw is defined as right in Minecraft coordinates.

The selected biological candidates and engineered interpretations are:

| Population | Decoder role | Boundary |
|---|---|---|
| DNp09/P9 | positive forward | walking candidate |
| MDN | subtractive/backward drive | walking direction candidate |
| DNa01 | low-gain yaw | sign uses annotation side as a proxy |
| DNa02 | high-gain yaw | gain is not behaviorally calibrated |
| DNp01/Giant Fiber | ground escape flag | Paper converts it to a minimum forward burst |
| all descending | diagnostic average rate | not mixed directly into commands |

The ground-only protocol intentionally has no vertical command. The decoder
does not compute or serialize an unused altitude/takeoff value.

The full-connectome motor smoke test directly optogenetically activates the
candidate output populations in three consecutive 50 ms windows. This verifies
rate extraction, rolling history, smoothing, and command production. It does
not demonstrate that natural sensory propagation would cause the same behavior.

## Stage 5 transport and service

The Python process owns one persistent `BrainController` composed of
`SensoryEncoder`, `BrainRuntime`, and `MotorDecoder`. WebSocket handlers parse a
strict v1 sensory frame, then serialize work through one asynchronous lock and
run the CPU-bound controller step off the asyncio event loop. Multiple clients
therefore cannot concurrently mutate Brian2 or decoder state.

WebSocket was selected over UDP and raw TCP. It provides persistent full-duplex
transport, message framing, request correlation, ping/close behavior, and Java
21/Python standard ecosystem support. Its framing overhead is negligible beside
the measured full-connectome CPU step. UDP would require loss, ordering,
duplication, and fragmentation policy; raw TCP would require custom framing.
The default service binds only `127.0.0.1`. The v1 protocol has no
authentication or TLS and must not be exposed externally as configured.

`protocol/flycraft-v1.schema.json` defines three messages:

- `sensory_frame`: protocol version, monotonically increasing request ID,
  sender timestamp, neural step duration, and one `SensoryState`;
- `motor_command`: the correlated `MotorCommand` and simulation telemetry;
- `error`: correlated where possible, with a stable machine-readable code.

The Paper client permits one in-flight frame. This is deliberate backpressure:
Minecraft ticks are never queued into an already slower neural simulation.
Request timeout closes the socket; reconnect attempts are rate-limited. A
response must match the in-flight request ID. Missing commands stop the Spider's
horizontal movement after the configured 750 ms stale interval.

## Stage 5 Minecraft mappings

The controller targets Paper 1.21.11 on Java 21. `/flycraft spawn` creates one
Spider with AI and awareness disabled while leaving gravity enabled. Every
Bukkit world/entity access and velocity update runs on the server thread; Java
`HttpClient` callbacks only schedule results back onto that thread.

| Minecraft observation | Wire field | Extraction policy |
|---|---|---|
| local block light | `light` | Bukkit block light level, 0–15 |
| nearest loaded flower | `food_distance`, `food_angle` | `Tag.FLOWERS`, 16-block radius, cached 20 ticks |
| front/left/right solidity | obstacle distances | block raycasts at 0° and ±45°, maximum 8 blocks |
| near-front collision | `touch` | front hit within 0.35 blocks |
| effective damage event | `damage` | latched until the next transmitted frame |
| Bukkit water state | `in_water` | direct entity state |

Negative food angle means left and positive means right, matching the sensory
encoder convention. Missing flower or obstacle observations are JSON `null`,
not invented maximum-distance measurements. Flower scans skip unloaded chunks
instead of loading world data from a control tick.

The movement actuator maps decoder commands as:

$$
\Delta yaw = 18^\\circ \\cdot yaw
$$

$$
v_h = 0.32 \cdot forward
$$

Positive yaw turns right in Minecraft coordinates. During `escape`, forward
drive is at least 0.8 before the horizontal velocity scale is applied. When the
neural forward command is exactly zero after its dead zone, Paper applies a
configurable `idle-forward-drive` of 0.15, producing 0.048 horizontal velocity.
This is an explicitly engineered gameplay policy, is logged as `idle=true`, and
must not be presented as a connectome decision. Existing vertical velocity is
preserved so Minecraft gravity and collision physics own the ground axis. The
plugin does not restore vanilla pathfinding while under neural control.

## Stage 5 measured limit

A real loopback WebSocket smoke frame traversed the encoder, full FAFB v783 LIF
network, decoder, and JSON response in 434.5 ms server time; the Brian2 step was
418.9 ms for 50 ms simulated time. That sample emitted 11,606 output spikes
across 6,261 active neurons. It is one workstation measurement, not a stable
benchmark, but it proves the current CPU path cannot sustain 10–20 Hz. The
single-in-flight policy therefore yields roughly 2 Hz rather than accumulating
latency. A returned `escape=true` remains an engineered threshold crossing of
the selected descending population, not evidence that a biological fly
\"decided\" to escape.
