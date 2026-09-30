package com.funcoesodm.javaservice.config;

import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

import java.util.Map;

/**
 * Guarda o {@code Authorization} do pedido de upgrade do {@code /ws} na sessão
 * do WebSocket (fase 5 da remodelagem, BFF — acesso-e-permissoes.md §10.5).
 *
 * <p>O navegador não tem mais token para mandar no frame STOMP CONNECT: quem o
 * põe é o gateway, no próprio pedido de upgrade, depois de trocar o cookie da
 * sessão pelo access do drone. O {@link WebSocketAuthChannelInterceptor} o lê
 * daqui no CONNECT.
 */
@Component
public class BffHandshakeInterceptor implements HandshakeInterceptor {

    public static final String ATRIBUTO = "sgi.authorization";

    @Override
    public boolean beforeHandshake(ServerHttpRequest request, ServerHttpResponse response,
                                   WebSocketHandler wsHandler, Map<String, Object> attributes) {
        String authorization = request.getHeaders().getFirst("Authorization");
        if (authorization != null && !authorization.isBlank()) {
            attributes.put(ATRIBUTO, authorization);
        }
        return true;
    }

    @Override
    public void afterHandshake(ServerHttpRequest request, ServerHttpResponse response,
                               WebSocketHandler wsHandler, Exception exception) {
        // nada a fazer depois do handshake
    }
}
