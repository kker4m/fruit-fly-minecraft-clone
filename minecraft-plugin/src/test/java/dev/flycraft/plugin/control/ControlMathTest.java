package dev.flycraft.plugin.control;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import dev.flycraft.plugin.control.MovementMath.DesiredMotion;
import dev.flycraft.plugin.control.MovementMath.MovementConfig;
import dev.flycraft.plugin.protocol.MotorCommand;
import org.bukkit.Location;
import org.bukkit.util.Vector;
import org.junit.jupiter.api.Test;

class ControlMathTest {
    private static final MovementConfig CONFIG =
            new MovementConfig(0.32, 18.0, 0.8, 0.15);

    @Test
    void mapsContinuousCommandOntoBoundedVelocityAndYaw() {
        DesiredMotion motion = MovementMath.compute(
                new MotorCommand(0.5, -0.25, false), CONFIG);

        assertEquals(0.16, motion.horizontalSpeed(), 1e-12);
        assertEquals(-4.5, motion.yawDeltaDegrees(), 1e-12);
        assertEquals(false, motion.idleFallback());
    }

    @Test
    void escapeOverridesWeakOrReverseDrive() {
        DesiredMotion motion = MovementMath.compute(
                new MotorCommand(-0.4, 0.0, true), CONFIG);

        assertEquals(0.256, motion.horizontalSpeed(), 1e-12);
        assertEquals(false, motion.idleFallback());
    }

    @Test
    void appliesExplicitEngineeredIdleDriveWhenNeuralForwardIsZero() {
        DesiredMotion motion = MovementMath.compute(
                new MotorCommand(0.0, 0.0, false), CONFIG);

        assertEquals(0.048, motion.horizontalSpeed(), 1e-12);
        assertEquals(true, motion.idleFallback());
    }

    @Test
    void motorCommandRejectsOutOfRangeValues() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new MotorCommand(1.1, 0.0, false));
    }

    @Test
    void minecraftYawProducesExpectedHorizontalDirections() {
        assertVector(SensorySampler.horizontalDirection(new Location(null, 0, 0, 0, 0, 0)), 0, 1);
        assertVector(SensorySampler.horizontalDirection(new Location(null, 0, 0, 0, 90, 0)), -1, 0);
    }

    @Test
    void foodAngleUsesNegativeForLeftAndPositiveForRight() {
        Vector south = new Vector(0, 0, 1);

        assertEquals(-Math.PI / 2, SensorySampler.signedHorizontalAngle(south, new Vector(1, 0, 0)), 1e-12);
        assertEquals(Math.PI / 2, SensorySampler.signedHorizontalAngle(south, new Vector(-1, 0, 0)), 1e-12);
    }

    @Test
    void normalizesYawAcrossWrapBoundary() {
        assertEquals(-170.0f, SpiderMovementController.normalizeYaw(190.0f));
        assertEquals(170.0f, SpiderMovementController.normalizeYaw(-190.0f));
    }

    private static void assertVector(Vector value, double x, double z) {
        assertEquals(x, value.getX(), 1e-12);
        assertEquals(z, value.getZ(), 1e-12);
    }
}
