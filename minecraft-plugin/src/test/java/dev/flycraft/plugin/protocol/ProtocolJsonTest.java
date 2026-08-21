package dev.flycraft.plugin.protocol;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.google.gson.Gson;
import org.junit.jupiter.api.Test;

class ProtocolJsonTest {
    private final Gson gson = new Gson();

    @Test
    void serializesSensoryFrameWithVersionedSnakeCaseContract() {
        SensoryState sensors = new SensoryState(
                12, 4.8, -0.31, 0.7, 3.1, 2.4, false, true, false);

        String json = gson.toJson(new SensoryFrame(7, 1000, 50, sensors));

        assertTrue(json.contains("\"type\":\"sensory_frame\""));
        assertTrue(json.contains("\"protocol_version\":1"));
        assertTrue(json.contains("\"request_id\":7"));
        assertTrue(json.contains("\"food_distance\":4.8"));
        assertTrue(json.contains("\"in_water\":false"));
    }

    @Test
    void parsesValidMotorResponse() {
        String json = """
                {"type":"motor_command","protocol_version":1,"request_id":7,
                 "command":{"forward":0.4,"yaw":-0.2,"escape":false},
                 "telemetry":{"simulation_time_ms":50,"brain_wall_time_ms":123,
                  "round_trip_server_ms":125,"input_spikes":3,"output_spikes":8,
                  "active_neurons":5,"stimulated_neurons":4,
                  "aggregate_stimulus_rate_hz":100,"descending_rate_hz":2,
                  "sensory_channel_rates_hz":{"light":50},
                  "motor_population_rates_hz":{"motor_forward_dnp09":12},
                  "motor_side_rates_hz":{"motor_turning_dna02":{"left":1,"right":3}},
                  "unmapped_inputs":[]}}
                """;

        MotorResponse response = gson.fromJson(json, MotorResponse.class);

        assertEquals(7, response.requestId());
        assertEquals(-0.2, response.command().yaw(), 1e-12);
        assertEquals(8, response.telemetry().outputSpikes());
        assertEquals(50.0, response.telemetry().sensoryChannelRatesHz().get("light"));
        assertEquals(
                12.0,
                response.telemetry().motorPopulationRatesHz().get("motor_forward_dnp09"));
        assertEquals(
                3.0,
                response.telemetry()
                        .motorSideRatesHz()
                        .get("motor_turning_dna02")
                        .get("right"));
    }

    @Test
    void rejectsUnsupportedResponseVersion() {
        String json = """
                {"type":"motor_command","protocol_version":2,"request_id":7,
                 "command":{"forward":0,"yaw":0,"escape":false},
                 "telemetry":{}}
                """;

        assertThrows(RuntimeException.class, () -> gson.fromJson(json, MotorResponse.class));
    }
}
