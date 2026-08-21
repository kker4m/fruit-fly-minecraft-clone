package dev.flycraft.plugin.control;

import dev.flycraft.plugin.protocol.SensoryState;
import org.bukkit.FluidCollisionMode;
import org.bukkit.Location;
import org.bukkit.Tag;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.entity.Spider;
import org.bukkit.util.RayTraceResult;
import org.bukkit.util.Vector;

public final class SensorySampler {
    private static final double TOUCH_DISTANCE = 0.35;
    private static final double SIDE_RAY_ANGLE = Math.toRadians(45.0);

    private final double obstacleRange;
    private final int foodRange;
    private final long foodScanPeriodTicks;
    private Location cachedFlower;
    private long nextFoodScanTick;

    public SensorySampler(double obstacleRange, int foodRange, long foodScanPeriodTicks) {
        if (obstacleRange <= 0 || foodRange <= 0 || foodScanPeriodTicks <= 0) {
            throw new IllegalArgumentException("sensor ranges and scan period must be positive");
        }
        this.obstacleRange = obstacleRange;
        this.foodRange = foodRange;
        this.foodScanPeriodTicks = foodScanPeriodTicks;
    }

    public SensoryState sample(Spider spider, long tick, boolean damage) {
        Location origin = spider.getEyeLocation();
        Vector forward = horizontalDirection(origin);
        Double obstacleFront = rayDistance(origin, forward);
        Double obstacleLeft = rayDistance(origin, forward.clone().rotateAroundY(SIDE_RAY_ANGLE));
        Double obstacleRight = rayDistance(origin, forward.clone().rotateAroundY(-SIDE_RAY_ANGLE));

        Location flower = nearestFlower(spider.getLocation(), tick);
        Double foodDistance = flower == null ? null : spider.getLocation().distance(flower);
        double foodAngle = flower == null
                ? 0.0
                : signedHorizontalAngle(forward, flower.toVector().subtract(origin.toVector()));

        return new SensoryState(
                spider.getLocation().getBlock().getLightLevel(),
                foodDistance,
                foodAngle,
                obstacleFront,
                obstacleLeft,
                obstacleRight,
                obstacleFront != null && obstacleFront <= TOUCH_DISTANCE,
                damage,
                spider.isInWater());
    }

    private Double rayDistance(Location origin, Vector direction) {
        RayTraceResult hit = origin.getWorld().rayTraceBlocks(
                origin,
                direction,
                obstacleRange,
                FluidCollisionMode.NEVER,
                true);
        return hit == null ? null : hit.getHitPosition().distance(origin.toVector());
    }

    private Location nearestFlower(Location origin, long tick) {
        if (tick < nextFoodScanTick && isUsableCachedFlower(origin)) {
            return cachedFlower;
        }
        nextFoodScanTick = tick + foodScanPeriodTicks;
        cachedFlower = scanNearestFlower(origin);
        return cachedFlower;
    }

    private boolean isUsableCachedFlower(Location origin) {
        return cachedFlower != null
                && cachedFlower.getWorld().equals(origin.getWorld())
                && cachedFlower.distanceSquared(origin) <= foodRange * foodRange
                && Tag.FLOWERS.isTagged(cachedFlower.getBlock().getType());
    }

    private Location scanNearestFlower(Location origin) {
        World world = origin.getWorld();
        int centerX = origin.getBlockX();
        int centerY = origin.getBlockY();
        int centerZ = origin.getBlockZ();
        double bestDistanceSquared = Double.POSITIVE_INFINITY;
        Location best = null;
        int verticalRange = Math.min(foodRange, 8);

        for (int x = centerX - foodRange; x <= centerX + foodRange; x++) {
            for (int z = centerZ - foodRange; z <= centerZ + foodRange; z++) {
                if (!world.isChunkLoaded(x >> 4, z >> 4)) {
                    continue;
                }
                for (int y = centerY - verticalRange; y <= centerY + verticalRange; y++) {
                    double dx = x + 0.5 - origin.getX();
                    double dy = y + 0.5 - origin.getY();
                    double dz = z + 0.5 - origin.getZ();
                    double distanceSquared = dx * dx + dy * dy + dz * dz;
                    if (distanceSquared >= bestDistanceSquared
                            || distanceSquared > foodRange * foodRange) {
                        continue;
                    }
                    Block block = world.getBlockAt(x, y, z);
                    if (Tag.FLOWERS.isTagged(block.getType())) {
                        bestDistanceSquared = distanceSquared;
                        best = block.getLocation().add(0.5, 0.5, 0.5);
                    }
                }
            }
        }
        return best;
    }

    static Vector horizontalDirection(Location location) {
        double radians = Math.toRadians(location.getYaw());
        return new Vector(-Math.sin(radians), 0.0, Math.cos(radians));
    }

    static double signedHorizontalAngle(Vector forward, Vector target) {
        Vector horizontalTarget = target.clone().setY(0.0);
        if (horizontalTarget.lengthSquared() == 0.0) {
            return 0.0;
        }
        horizontalTarget.normalize();
        double crossY = forward.getX() * horizontalTarget.getZ()
                - forward.getZ() * horizontalTarget.getX();
        return Math.atan2(crossY, forward.dot(horizontalTarget));
    }
}
