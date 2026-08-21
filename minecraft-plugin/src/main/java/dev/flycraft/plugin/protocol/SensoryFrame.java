package dev.flycraft.plugin.protocol;

import com.google.gson.annotations.SerializedName;

public record SensoryFrame(
        String type,
        @SerializedName("protocol_version") int protocolVersion,
        @SerializedName("request_id") long requestId,
        @SerializedName("sent_at_ms") long sentAtMs,
        @SerializedName("step_ms") double stepMs,
        SensoryState sensors) {

    public SensoryFrame(long requestId, long sentAtMs, double stepMs, SensoryState sensors) {
        this("sensory_frame", 1, requestId, sentAtMs, stepMs, sensors);
    }
}
