package dev.flycraft.plugin;

import dev.flycraft.plugin.control.FlyCraftController;
import java.util.List;
import org.bukkit.Location;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.PluginCommand;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.plugin.java.JavaPlugin;

public final class FlyCraftPlugin extends JavaPlugin
        implements Listener, CommandExecutor, TabCompleter {
    private FlyCraftController controller;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        try {
            FlyCraftConfig config = FlyCraftConfig.load(getConfig());
            controller = new FlyCraftController(this, config);
            getServer().getPluginManager().registerEvents(this, this);
            PluginCommand command = getCommand("flycraft");
            if (command == null) {
                throw new IllegalStateException("flycraft command is missing from plugin.yml");
            }
            command.setExecutor(this);
            command.setTabCompleter(this);
            getServer().getScheduler().runTaskTimer(
                    this,
                    controller,
                    1L,
                    config.controlPeriodTicks());
            getLogger().info("FlyCraft enabled; use /flycraft spawn to create the neural Spider");
        } catch (RuntimeException error) {
            getLogger().severe("Invalid FlyCraft configuration: " + error.getMessage());
            getServer().getPluginManager().disablePlugin(this);
        }
    }

    @Override
    public void onDisable() {
        if (controller != null) {
            controller.close();
            controller = null;
        }
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onSpiderDamage(EntityDamageEvent event) {
        if (controller != null) {
            controller.recordDamage(event);
        }
    }

    @Override
    public boolean onCommand(
            CommandSender sender, Command command, String label, String[] args) {
        if (controller == null || args.length != 1) {
            return false;
        }
        return switch (args[0].toLowerCase()) {
            case "spawn" -> spawn(sender);
            case "remove" -> remove(sender);
            case "status" -> status(sender);
            default -> false;
        };
    }

    private boolean spawn(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage("FlyCraft: spawn must be run by a player");
            return true;
        }
        Location spawn = player.getEyeLocation()
                .add(player.getLocation().getDirection().normalize().multiply(2.0));
        controller.spawn(spawn);
        sender.sendMessage("FlyCraft: neural Spider spawned");
        return true;
    }

    private boolean remove(CommandSender sender) {
        sender.sendMessage(controller.removeSpider()
                ? "FlyCraft: neural Spider removed"
                : "FlyCraft: no managed Spider exists");
        return true;
    }

    private boolean status(CommandSender sender) {
        sender.sendMessage("FlyCraft: " + controller.status());
        return true;
    }

    @Override
    public List<String> onTabComplete(
            CommandSender sender, Command command, String alias, String[] args) {
        if (args.length != 1) {
            return List.of();
        }
        String prefix = args[0].toLowerCase();
        return List.of("spawn", "remove", "status").stream()
                .filter(value -> value.startsWith(prefix))
                .toList();
    }
}
