package com.funcoesodm.javaservice.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    private final WebSocketAuthChannelInterceptor authChannelInterceptor;
    private final BffHandshakeInterceptor bffHandshakeInterceptor;

    /**
     * As mesmas origens do CORS. Era {@code *}: com a sessão num cookie (fase 5),
     * aceitar o handshake de qualquer origem abriria o canal a uma página de
     * outro site (CSWSH). O gateway também confere o Origin antes (identity/bff.py).
     */
    @Value("${app.cors.allowed-origins:http://localhost:4200,http://localhost:8088,http://nginx:80,http://localhost:8090}")
    private String allowedOrigins;

    public WebSocketConfig(WebSocketAuthChannelInterceptor authChannelInterceptor,
                           BffHandshakeInterceptor bffHandshakeInterceptor) {
        this.authChannelInterceptor = authChannelInterceptor;
        this.bffHandshakeInterceptor = bffHandshakeInterceptor;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry config) {
        // Enable a simple in-memory message broker
        // Clients subscribe to /topic/* to receive messages
        config.enableSimpleBroker("/topic", "/queue");
        
        // Application destination prefix for messages from clients
        config.setApplicationDestinationPrefixes("/app");
        
        // User destination prefix for private messages
        config.setUserDestinationPrefix("/user");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        // Register the WebSocket endpoint that clients will connect to
        String[] origens = java.util.Arrays.stream(allowedOrigins.split(","))
                .map(String::trim).filter(o -> !o.isEmpty()).toArray(String[]::new);
        registry.addEndpoint("/ws")
                .setAllowedOrigins(origens)
                .addInterceptors(bffHandshakeInterceptor)
                .withSockJS();

        // Also allow native WebSocket without SockJS
        registry.addEndpoint("/ws")
                .setAllowedOrigins(origens)
                .addInterceptors(bffHandshakeInterceptor);
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        // Fase 10.8: autentica o frame STOMP CONNECT (o handshake HTTP do /ws é
        // permitAll). Desde a fase 5 o token vem do upgrade, posto pelo gateway.
        registration.interceptors(authChannelInterceptor);
    }
}
