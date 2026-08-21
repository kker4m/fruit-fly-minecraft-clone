package dev.flycraft.plugin.control;

import dev.flycraft.plugin.control.MovementMath.DesiredMotion;
import dev.flycraft.plugin.control.MovementMath.MovementConfig;
import dev.flycraft.plugin.protocol.MotorCommand;
import org.bukkit.Location;
import org.bukkit.entity.Spider;
import org.bukkit.util.Vector;

public final class SpiderMovementController {
    private final MovementConfig config;

    public SpiderMovementController(MovementConfig config) {
        this.config = config;
    }

    public DesiredMotion apply(Spider spider, MotorCommand command) {
        DesiredMotion motion = MovementMath.compute(command, config);
        Location location = spider.getLocation();
        float yaw = normalizeYaw((float) (location.getYaw() + motion.yawDeltaDegrees()));
        spider.setRotation(yaw, 0.0f);

        double radians = Math.toRadians(yaw);
        Vector velocity = new Vector(-Math.sin(radians), 0.0, Math.cos(radians))
                .multiply(motion.horizontalSpeed())
                .setY(spider.getVelocity().getY());
        spider.setVelocity(velocity);
        return motion;
    }

    public void stop(Spider spider) {
        spider.setVelocity(new Vector(0.0, spider.getVelocity().getY(), 0.0));
    }

    static float normalizeYaw(float yaw) {
        float normalized = yaw % 360.0f;
        if (normalized <= -180.0f) {
            normalized += 360.0f;
        } else if (normalized > 180.0f) {
            normalized -= 360.0f;
        }
        return normalized;
    }
}
