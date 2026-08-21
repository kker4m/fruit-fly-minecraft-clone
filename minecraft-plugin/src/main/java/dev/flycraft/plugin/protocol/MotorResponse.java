package dev.flycraft.plugin.protocol;

import com.google.gson.annotations.SerializedName;

public record MotorResponse(
        String type,
        @SerializedName("protocol_version") int protocolVersion,
        @SerializedName("request_id") long requestId,
        MotorCommand command,
        ServiceTelemetry telemetry) {

    public MotorResponse {
        if (!"motor_command".equals(type)) {
            throw new IllegalArgumentException("type must be motor_command");
        }
        if (protocolVersion != 1) {
            throw new IllegalArgumentException("unsupported protocol version: " + protocolVersion);
        }
        if (requestId < 0 || command == null || telemetry == null) {
            throw new IllegalArgumentException("invalid motor response");
        }
    }
}
