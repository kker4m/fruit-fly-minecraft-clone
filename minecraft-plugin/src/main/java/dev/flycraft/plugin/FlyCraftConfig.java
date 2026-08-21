package dev.flycraft.plugin;

import dev.flycraft.plugin.control.MovementMath.MovementConfig;
import java.net.URI;
import org.bukkit.configuration.file.FileConfiguration;

public record FlyCraftConfig(
        URI brainServiceUri,
        long controlPeriodTicks,
        double brainStepMs,
        long commandTimeoutMs,
        long staleCommandMs,
        long reconnectDelayTicks,
        double obstacleRangeBlocks,
        int foodRangeBlocks,
        long foodScanPeriodTicks,
        boolean diagnosticLogging,
        MovementConfig movement) {

    public static FlyCraftConfig load(FileConfiguration config) {
        FlyCraftConfig result = new FlyCraftConfig(
                URI.create(config.getString("brain-service-uri", "ws://127.0.0.1:8765")),
                config.getLong("control-period-ticks"),
                config.getDouble("brain-step-ms"),
                config.getLong("command-timeout-ms"),
                config.getLong("stale-command-ms"),
                config.getLong("reconnect-delay-ticks"),
                config.getDouble("obstacle-range-blocks"),
                config.getInt("food-range-blocks"),
                config.getLong("food-scan-period-ticks"),
                config.getBoolean("diagnostic-logging", true),
                new MovementConfig(
                        config.getDouble("max-horizontal-speed"),
                        config.getDouble("max-yaw-degrees-per-command"),
                        config.getDouble("escape-horizontal-drive"),
                        config.getDouble("idle-forward-drive", 0.15)));
        result.validate();
        return result;
    }

    private void validate() {
        String scheme = brainServiceUri.getScheme();
        if (!("ws".equals(scheme) || "wss".equals(scheme))) {
            throw new IllegalArgumentException("brain-service-uri must use ws or wss");
        }
        if (controlPeriodTicks <= 0 || brainStepMs <= 0 || brainStepMs > 200
                || commandTimeoutMs <= 0 || staleCommandMs <= 0
                || reconnectDelayTicks <= 0 || obstacleRangeBlocks <= 0
                || foodRangeBlocks <= 0 || foodScanPeriodTicks <= 0) {
            throw new IllegalArgumentException("FlyCraft timing and sensor settings must be positive");
        }
    }
}
