from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from time import perf_counter

from websockets.asyncio.server import ServerConnection, serve

from flycraft_brain.connectome import CodexMetadata
from flycraft_brain.motor import MotorDecoder
from flycraft_brain.runtime import BrainRuntime
from flycraft_brain.sensory import SensoryEncoder

from .protocol import (
    ErrorResponse,
    MotorResponse,
    ProtocolError,
    SensoryFrame,
    ServiceTelemetry,
)

LOGGER = logging.getLogger(__name__)


class BrainController:
    """Synchronous owner of one persistent encoder/brain/decoder pipeline."""

    def __init__(self, encoder, brain, decoder) -> None:
        self.encoder = encoder
        self.brain = brain
        self.decoder = decoder

    @classmethod
    def create(
        cls,
        data_dir: str | Path = "data/fly-brain",
        *,
        codegen_target: str = "cython",
        seed: int | None = 783,
    ) -> BrainController:
        metadata = CodexMetadata(data_dir)
        return cls(
            encoder=SensoryEncoder(metadata),
            brain=BrainRuntime(
                data_dir=data_dir,
                codegen_target=codegen_target,
                seed=seed,
            ),
            decoder=MotorDecoder(metadata),
        )

    def process(self, frame: SensoryFrame) -> MotorResponse:
        started = perf_counter()
        LOGGER.info("frame=%d rx sensors=%s", frame.request_id, frame.sensors)
        stimulus = self.encoder.encode(frame.sensors)
        stimulus.apply(self.brain)
        result = self.brain.step(frame.step_ms)
        command = self.decoder.decode(result)
        trace = self.decoder.last_trace
        response = MotorResponse(
            request_id=frame.request_id,
            command=command,
            telemetry=ServiceTelemetry(
                simulation_time_ms=result.simulation_time_ms,
                brain_wall_time_ms=result.wall_time_ms,
                round_trip_server_ms=(perf_counter() - started) * 1000.0,
                input_spikes=result.generated_input_spike_count,
                output_spikes=len(result.spikes),
                active_neurons=result.active_neuron_count,
                stimulated_neurons=len(stimulus),
                aggregate_stimulus_rate_hz=stimulus.total_rate_hz,
                descending_rate_hz=trace.descending_rate_hz,
                sensory_channel_rates_hz={
                    channel.channel: channel.total_rate_hz
                    for channel in stimulus.channels
                },
                motor_population_rates_hz=dict(trace.population_rates_hz),
                motor_side_rates_hz={
                    population: dict(side_rates)
                    for population, side_rates in trace.side_rates_hz.items()
                },
                unmapped_inputs=stimulus.unmapped_inputs,
            ),
        )
        LOGGER.info(
            "frame=%d tx stimulus=%s input_spikes=%d output_spikes=%d "
            "active_neurons=%d motor_rates=%s side_rates=%s command=%s wall_ms=%.1f",
            frame.request_id,
            response.telemetry.sensory_channel_rates_hz,
            response.telemetry.input_spikes,
            response.telemetry.output_spikes,
            response.telemetry.active_neurons,
            response.telemetry.motor_population_rates_hz,
            response.telemetry.motor_side_rates_hz,
            response.command,
            response.telemetry.round_trip_server_ms,
        )
        return response


class BrainWebSocketService:
    """Serializes clients onto the single stateful BrainController."""

    def __init__(self, controller: BrainController) -> None:
        self.controller = controller
        self._processing_lock: asyncio.Lock | None = None

    async def process_text(self, message: str) -> str:
        try:
            frame = SensoryFrame.from_json(message)
        except ProtocolError as error:
            return ErrorResponse(
                request_id=error.request_id,
                code=error.code,
                message=str(error),
            ).to_json()

        if self._processing_lock is None:
            self._processing_lock = asyncio.Lock()
        try:
            async with self._processing_lock:
                response = await asyncio.to_thread(self.controller.process, frame)
            return response.to_json()
        except Exception as error:
            LOGGER.exception("Brain frame processing failed")
            return ErrorResponse(
                request_id=frame.request_id,
                code="processing_error",
                message=str(error),
            ).to_json()

    async def handle_connection(self, websocket: ServerConnection) -> None:
        async for message in websocket:
            if not isinstance(message, str):
                await websocket.send(
                    ErrorResponse(
                        request_id=None,
                        code="binary_not_supported",
                        message="binary WebSocket messages are not supported",
                    ).to_json()
                )
                continue
            await websocket.send(await self.process_text(message))

    async def run(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self._processing_lock = asyncio.Lock()
        async with serve(
            self.handle_connection,
            host,
            port,
            max_size=64 * 1024,
            ping_interval=20,
            ping_timeout=20,
        ):
            LOGGER.info("Brain WebSocket service listening on ws://%s:%d", host, port)
            await asyncio.Future()
