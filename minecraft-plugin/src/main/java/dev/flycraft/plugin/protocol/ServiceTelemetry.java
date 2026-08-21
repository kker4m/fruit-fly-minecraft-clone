package dev.flycraft.plugin.protocol;

import com.google.gson.annotations.SerializedName;
import java.util.List;
import java.util.Map;

public record ServiceTelemetry(
        @SerializedName("simulation_time_ms") double simulationTimeMs,
        @SerializedName("brain_wall_time_ms") double brainWallTimeMs,
        @SerializedName("round_trip_server_ms") double roundTripServerMs,
        @SerializedName("input_spikes") int inputSpikes,
        @SerializedName("output_spikes") int outputSpikes,
        @SerializedName("active_neurons") int activeNeurons,
        @SerializedName("stimulated_neurons") int stimulatedNeurons,
        @SerializedName("aggregate_stimulus_rate_hz") double aggregateStimulusRateHz,
        @SerializedName("descending_rate_hz") double descendingRateHz,
        @SerializedName("sensory_channel_rates_hz") Map<String, Double> sensoryChannelRatesHz,
        @SerializedName("motor_population_rates_hz") Map<String, Double> motorPopulationRatesHz,
        @SerializedName("motor_side_rates_hz") Map<String, Map<String, Double>> motorSideRatesHz,
        @SerializedName("unmapped_inputs") List<String> unmappedInputs) {
}
