package dev.flycraft.plugin.control;

import dev.flycraft.plugin.FlyCraftConfig;
import dev.flycraft.plugin.FlyCraftPlugin;
import dev.flycraft.plugin.net.BrainWebSocketClient;
import dev.flycraft.plugin.protocol.MotorResponse;
import dev.flycraft.plugin.protocol.SensoryFrame;
import dev.flycraft.plugin.protocol.SensoryState;
import java.time.Duration;
import net.kyori.adventure.text.Component;
import org.bukkit.Location;
import org.bukkit.entity.Spider;
import org.bukkit.event.entity.EntityDamageEvent;

public final class FlyCraftController implements Runnable, AutoCloseable {
    private static final String MANAGED_TAG = "flycraft-neural-spider";

    private final FlyCraftPlugin plugin;
    private final FlyCraftConfig config;
    private final SensorySampler sensorySampler;
    private final SpiderMovementController movementController;
    private final BrainWebSocketClient brainClient;

    private Spider spider;
    private long logicalTick;
    private long nextReconnectTick;
    private long nextRequestId;
    private Long inFlightRequestId;
    private SensoryState inFlightSensors;
    private long requestSentAtMs;
    private long lastCommandAtMs;
    private boolean damageSinceLastFrame;
    private boolean stoppedForStaleness;
    private volatile String connectionStatus = "disconnected";
    private MotorResponse lastResponse;

    public FlyCraftController(FlyCraftPlugin plugin, FlyCraftConfig config) {
        this.plugin = plugin;
        this.config = config;
        this.sensorySampler = new SensorySampler(
                config.obstacleRangeBlocks(),
                config.foodRangeBlocks(),
                config.foodScanPeriodTicks());
        this.movementController = new SpiderMovementController(config.movement());
        this.brainClient = new BrainWebSocketClient(
                config.brainServiceUri(),
                Duration.ofSeconds(5),
                this::receiveResponse,
                this::receiveProtocolError,
                this::receiveStatus);
    }

    public Spider spawn(Location location) {
        removeSpider();
        spider = location.getWorld().spawn(location, Spider.class, spawned -> {
            spawned.addScoreboardTag(MANAGED_TAG);
            spawned.customName(Component.text("FlyCraft • FAFB v783 Neural Spider"));
            spawned.setCustomNameVisible(true);
            spawned.setAI(false);
            spawned.setAware(false);
            spawned.setGravity(true);
            spawned.setPersistent(true);
            spawned.setRemoveWhenFarAway(false);
            spawned.setSilent(true);
        });
        stoppedForStaleness = true;
        return spider;
    }

    public boolean removeSpider() {
        if (spider == null) {
            return false;
        }
        if (spider.isValid()) {
            spider.remove();
        }
        spider = null;
        inFlightRequestId = null;
        inFlightSensors = null;
        lastResponse = null;
        return true;
    }

    public void recordDamage(EntityDamageEvent event) {
        if (spider != null && event.getEntity().getUniqueId().equals(spider.getUniqueId())) {
            damageSinceLastFrame = true;
        }
    }

    @Override
    public void run() {
        logicalTick += config.controlPeriodTicks();
        long now = System.currentTimeMillis();
        if (!brainClient.isConnected() && logicalTick >= nextReconnectTick) {
            nextReconnectTick = logicalTick + config.reconnectDelayTicks();
            brainClient.connect();
        }
        if (spider == null || !spider.isValid()) {
            spider = null;
            return;
        }
        if (lastCommandAtMs == 0 || now - lastCommandAtMs > config.staleCommandMs()) {
            if (!stoppedForStaleness) {
                movementController.stop(spider);
                stoppedForStaleness = true;
            }
        }
        if (inFlightRequestId != null) {
            if (now - requestSentAtMs > config.commandTimeoutMs()) {
                inFlightRequestId = null;
                inFlightSensors = null;
                plugin.getLogger().warning(
                        "Neural request timed out after " + (now - requestSentAtMs) + " ms");
                brainClient.close();
                connectionStatus = "request timed out";
            }
            return;
        }
        if (!brainClient.isConnected()) {
            return;
        }

        boolean damage = damageSinceLastFrame;
        damageSinceLastFrame = false;
        SensoryState sensors = sensorySampler.sample(spider, logicalTick, damage);
        long requestId = nextRequestId++;
        SensoryFrame frame = new SensoryFrame(
                requestId,
                now,
                config.brainStepMs(),
                sensors);
        inFlightRequestId = requestId;
        inFlightSensors = sensors;
        if (config.diagnosticLogging()) {
            plugin.getLogger().info(String.format(
                    "neural tx frame=%d light=%.0f food=%s angle=%.3f "
                            + "obstacles=[%s,%s,%s] touch=%s damage=%s water=%s",
                    requestId,
                    sensors.light(),
                    sensors.foodDistance(),
                    sensors.foodAngle(),
                    sensors.obstacleFront(),
                    sensors.obstacleLeft(),
                    sensors.obstacleRight(),
                    sensors.touch(),
                    sensors.damage(),
                    sensors.inWater()));
        }
        requestSentAtMs = now;
        brainClient.send(frame).whenComplete((ignored, error) -> {
            if (error != null) {
                plugin.getServer().getScheduler().runTask(
                        plugin,
                        () -> clearFailedRequest(requestId, error.getMessage()));
            }
        });
    }

    private void receiveResponse(MotorResponse response) {
        plugin.getServer().getScheduler().runTask(plugin, () -> applyResponse(response));
    }

    private void applyResponse(MotorResponse response) {
        if (inFlightRequestId == null || response.requestId() != inFlightRequestId) {
            if (config.diagnosticLogging()) {
                plugin.getLogger().warning(String.format(
                        "ignored neural rx frame=%d expected=%s",
                        response.requestId(), inFlightRequestId));
            }
            return;
        }
        inFlightRequestId = null;
        SensoryState sensors = inFlightSensors;
        inFlightSensors = null;
        lastResponse = response;
        if (spider == null || !spider.isValid()) {
            return;
        }
        MovementMath.DesiredMotion appliedMotion =
                movementController.apply(spider, response.command());
        lastCommandAtMs = System.currentTimeMillis();
        stoppedForStaleness = false;
        if (config.diagnosticLogging()) {
            plugin.getLogger().info(String.format(
                    "neural rx frame=%d sensors=%s stimulus_rates=%s "
                            + "spikes=[input=%d,output=%d,active=%d] "
                            + "motor_rates=%s side_rates=%s "
                            + "command=[forward=%.3f,yaw=%.3f,escape=%s] "
                            + "applied=[horizontal=%.3f,idle=%s] velocity=%s brain_ms=%.1f",
                    response.requestId(),
                    sensors,
                    response.telemetry().sensoryChannelRatesHz(),
                    response.telemetry().inputSpikes(),
                    response.telemetry().outputSpikes(),
                    response.telemetry().activeNeurons(),
                    response.telemetry().motorPopulationRatesHz(),
                    response.telemetry().motorSideRatesHz(),
                    response.command().forward(),
                    response.command().yaw(),
                    response.command().escape(),
                    appliedMotion.horizontalSpeed(),
                    appliedMotion.idleFallback(),
                    spider.getVelocity(),
                    response.telemetry().brainWallTimeMs()));
        }
    }

    private void receiveProtocolError(Long requestId, String message) {
        plugin.getServer().getScheduler().runTask(plugin, () -> {
            if (requestId != null && requestId.equals(inFlightRequestId)) {
                inFlightRequestId = null;
                inFlightSensors = null;
            }
            connectionStatus = "brain error: " + message;
            plugin.getLogger().warning(String.format(
                    "neural error frame=%s message=%s", requestId, message));
        });
    }

    private void receiveStatus(String status) {
        connectionStatus = status;
        plugin.getLogger().info(status);
    }

    private void clearFailedRequest(long requestId, String message) {
        if (inFlightRequestId != null && inFlightRequestId == requestId) {
            inFlightRequestId = null;
            inFlightSensors = null;
            connectionStatus = "send failed: " + message;
            plugin.getLogger().warning(String.format(
                    "neural send failed frame=%d message=%s", requestId, message));
        }
    }

    public String status() {
        String spiderStatus = spider == null || !spider.isValid()
                ? "none"
                : spider.getUniqueId().toString();
        String telemetry = lastResponse == null
                ? "no response"
                : String.format(
                        "brain %.1f ms, spikes %d, active %d",
                        lastResponse.telemetry().brainWallTimeMs(),
                        lastResponse.telemetry().outputSpikes(),
                        lastResponse.telemetry().activeNeurons());
        return "Spider: " + spiderStatus + "; service: " + connectionStatus + "; " + telemetry;
    }

    @Override
    public void close() {
        brainClient.close();
        removeSpider();
    }
}
