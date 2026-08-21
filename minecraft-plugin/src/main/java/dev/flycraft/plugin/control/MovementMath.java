package dev.flycraft.plugin.control;

import dev.flycraft.plugin.protocol.MotorCommand;

public final class MovementMath {
    private MovementMath() {
    }

    public static DesiredMotion compute(MotorCommand command, MovementConfig config) {
        boolean idleFallback = !command.escape()
                && command.forward() == 0.0
                && config.idleForwardDrive() > 0.0;
        double forward = command.escape()
                ? Math.max(command.forward(), config.escapeHorizontalDrive())
                : idleFallback ? config.idleForwardDrive() : command.forward();
        return new DesiredMotion(
                command.yaw() * config.maxYawDegreesPerCommand(),
                forward * config.maxHorizontalSpeed(),
                idleFallback);
    }

    public record MovementConfig(
            double maxHorizontalSpeed,
            double maxYawDegreesPerCommand,
            double escapeHorizontalDrive,
            double idleForwardDrive) {
        public MovementConfig {
            if (maxHorizontalSpeed <= 0 || maxYawDegreesPerCommand <= 0) {
                throw new IllegalArgumentException("movement limits must be positive");
            }
            requireUnit("escapeHorizontalDrive", escapeHorizontalDrive);
            requireUnit("idleForwardDrive", idleForwardDrive);
        }

        private static void requireUnit(String name, double value) {
            if (!Double.isFinite(value) || value < 0.0 || value > 1.0) {
                throw new IllegalArgumentException(name + " must be within [0, 1]");
            }
        }
    }

    public record DesiredMotion(
            double yawDeltaDegrees, double horizontalSpeed, boolean idleFallback) {
    }
}
