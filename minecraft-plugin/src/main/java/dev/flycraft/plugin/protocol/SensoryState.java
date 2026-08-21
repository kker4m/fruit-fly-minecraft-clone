package dev.flycraft.plugin.protocol;

import com.google.gson.annotations.SerializedName;

public record SensoryState(
        double light,
        @SerializedName("food_distance") Double foodDistance,
        @SerializedName("food_angle") double foodAngle,
        @SerializedName("obstacle_front") Double obstacleFront,
        @SerializedName("obstacle_left") Double obstacleLeft,
        @SerializedName("obstacle_right") Double obstacleRight,
        boolean touch,
        boolean damage,
        @SerializedName("in_water") boolean inWater) {
}
