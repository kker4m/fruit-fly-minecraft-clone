package dev.flycraft.plugin.net;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.google.gson.JsonObject;
import dev.flycraft.plugin.protocol.SensoryFrame;
import dev.flycraft.plugin.protocol.SensoryState;
import org.junit.jupiter.api.Test;

class BrainWebSocketClientTest {
    @Test
    void serializesAbsentSensorReadingsAsExplicitNulls() {
        SensoryState sensors = new SensoryState(
                15.0, null, 0.0, null, null, null, false, false, false);

        String json = BrainWebSocketClient.createProtocolGson()
                .toJson(new SensoryFrame(7, 1000, 50, sensors));
        JsonObject encodedSensors = BrainWebSocketClient.createProtocolGson()
                .fromJson(json, JsonObject.class)
                .getAsJsonObject("sensors");

        assertEquals(9, encodedSensors.size());
        assertEquals(true, encodedSensors.get("food_distance").isJsonNull());
        assertEquals(true, encodedSensors.get("obstacle_front").isJsonNull());
        assertEquals(true, encodedSensors.get("obstacle_left").isJsonNull());
        assertEquals(true, encodedSensors.get("obstacle_right").isJsonNull());
    }
}
