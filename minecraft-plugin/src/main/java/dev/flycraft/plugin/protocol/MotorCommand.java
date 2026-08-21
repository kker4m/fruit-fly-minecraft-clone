package dev.flycraft.plugin.protocol;

public record MotorCommand(double forward, double yaw, boolean escape) {
    public MotorCommand {
        requireUnitRange("forward", forward);
        requireUnitRange("yaw", yaw);
    }

    private static void requireUnitRange(String name, double value) {
        if (!Double.isFinite(value) || value < -1.0 || value > 1.0) {
            throw new IllegalArgumentException(name + " must be finite and within [-1, 1]");
        }
    }
}
