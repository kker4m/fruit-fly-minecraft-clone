package dev.flycraft.plugin.net;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import dev.flycraft.plugin.protocol.MotorResponse;
import dev.flycraft.plugin.protocol.SensoryFrame;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.BiConsumer;
import java.util.function.Consumer;

public final class BrainWebSocketClient implements WebSocket.Listener, AutoCloseable {
    private final URI uri;
    private final HttpClient httpClient;
    private final Gson gson = createProtocolGson();
    private final Consumer<MotorResponse> responseHandler;
    private final BiConsumer<Long, String> errorHandler;
    private final Consumer<String> statusHandler;
    private final AtomicBoolean connecting = new AtomicBoolean();
    private final StringBuilder incomingText = new StringBuilder();
    private volatile WebSocket socket;

    public BrainWebSocketClient(
            URI uri,
            Duration connectTimeout,
            Consumer<MotorResponse> responseHandler,
            BiConsumer<Long, String> errorHandler,
            Consumer<String> statusHandler) {
        this.uri = Objects.requireNonNull(uri);
        this.responseHandler = Objects.requireNonNull(responseHandler);
        this.errorHandler = Objects.requireNonNull(errorHandler);
        this.statusHandler = Objects.requireNonNull(statusHandler);
        this.httpClient = HttpClient.newBuilder().connectTimeout(connectTimeout).build();
    }

    static Gson createProtocolGson() {
        return new GsonBuilder().serializeNulls().create();
    }

    public void connect() {
        if (socket != null || !connecting.compareAndSet(false, true)) {
            return;
        }
        statusHandler.accept("connecting to " + uri);
        httpClient.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .buildAsync(uri, this)
                .whenComplete((webSocket, error) -> {
                    connecting.set(false);
                    if (error != null) {
                        statusHandler.accept("connection failed: " + error.getMessage());
                    }
                });
    }

    public boolean isConnected() {
        return socket != null;
    }

    public CompletableFuture<WebSocket> send(SensoryFrame frame) {
        WebSocket current = socket;
        if (current == null) {
            return CompletableFuture.failedFuture(
                    new IllegalStateException("brain service is disconnected"));
        }
        return current.sendText(gson.toJson(frame), true);
    }

    @Override
    public void onOpen(WebSocket webSocket) {
        socket = webSocket;
        statusHandler.accept("connected to " + uri);
        webSocket.request(1);
    }

    @Override
    public CompletionStage<?> onText(WebSocket webSocket, CharSequence data, boolean last) {
        incomingText.append(data);
        if (last) {
            String message = incomingText.toString();
            incomingText.setLength(0);
            handleMessage(message);
        }
        webSocket.request(1);
        return null;
    }

    private void handleMessage(String message) {
        try {
            JsonObject envelope = gson.fromJson(message, JsonObject.class);
            if (envelope == null || !envelope.has("type")) {
                throw new JsonParseException("response has no type");
            }
            String type = envelope.get("type").getAsString();
            if ("motor_command".equals(type)) {
                responseHandler.accept(gson.fromJson(envelope, MotorResponse.class));
                return;
            }
            if ("error".equals(type)) {
                Long requestId = envelope.get("request_id").isJsonNull()
                        ? null
                        : envelope.get("request_id").getAsLong();
                errorHandler.accept(requestId, envelope.get("message").getAsString());
                return;
            }
            throw new JsonParseException("unsupported response type: " + type);
        } catch (RuntimeException error) {
            statusHandler.accept("invalid brain response: " + error.getMessage());
        }
    }

    @Override
    public CompletionStage<?> onClose(WebSocket webSocket, int statusCode, String reason) {
        if (socket == webSocket) {
            socket = null;
        }
        statusHandler.accept("connection closed: " + statusCode + " " + reason);
        return null;
    }

    @Override
    public void onError(WebSocket webSocket, Throwable error) {
        if (socket == webSocket) {
            socket = null;
        }
        statusHandler.accept("connection error: " + error.getMessage());
    }

    @Override
    public void close() {
        WebSocket current = socket;
        socket = null;
        if (current != null) {
            current.sendClose(WebSocket.NORMAL_CLOSURE, "plugin shutdown");
        }
    }
}
