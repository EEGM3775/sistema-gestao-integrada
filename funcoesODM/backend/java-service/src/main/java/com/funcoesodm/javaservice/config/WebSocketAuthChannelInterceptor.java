package com.funcoesodm.javaservice.config;

import com.funcoesodm.javaservice.security.AutorizacaoService;
import com.funcoesodm.javaservice.security.IamUserPrincipal;
import com.funcoesodm.javaservice.service.UserProvisioningService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/**
 * Autentica o handshake STOMP do {@code /ws} (Fase 10.8, pendência da Fase 1).
 *
 * <p>O endpoint HTTP {@code /ws} segue {@code permitAll} no {@link SecurityConfig}
 * (o {@code JwtAuthenticationFilter} valida o header {@code Authorization} das
 * requisições REST, mas o navegador não envia headers no <em>upgrade</em> do
 * WebSocket nativo). A identidade vem então do frame <strong>STOMP CONNECT</strong>:
 * o cliente manda o access token da IAM no header STOMP {@code Authorization}, e
 * aqui aplicamos o mesmo contrato do filtro REST — assinatura+{@code exp},
 * revogação imediata por época e o entitlement do módulo ({@code drone}),
 * perguntado ao {@link AutorizacaoService}. CONNECT
 * sem token válido / sem o módulo / de sessão revogada é <strong>recusado</strong>
 * (exceção → o cliente recebe um frame ERROR e a conexão não sobe).
 */
@Component
public class WebSocketAuthChannelInterceptor implements ChannelInterceptor {

    private static final Logger logger = LoggerFactory.getLogger(WebSocketAuthChannelInterceptor.class);

    private final JwtUtil jwtUtil;
    private final UserProvisioningService userProvisioningService;
    private final SessionRevocationService sessionRevocationService;
    private final AutorizacaoService autorizacaoService;

    /** Módulo (entitlement) exigido para conectar — mesmo do {@link SecurityConfig}. */
    @Value("${app.module.required:drone}")
    private String requiredModule;

    public WebSocketAuthChannelInterceptor(JwtUtil jwtUtil,
                                           UserProvisioningService userProvisioningService,
                                           SessionRevocationService sessionRevocationService,
                                           AutorizacaoService autorizacaoService) {
        this.jwtUtil = jwtUtil;
        this.userProvisioningService = userProvisioningService;
        this.sessionRevocationService = sessionRevocationService;
        this.autorizacaoService = autorizacaoService;
    }

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor =
                MessageHeaderAccessor.getAccessor(message, StompHeaderAccessor.class);

        // Só o CONNECT autentica; os frames seguintes reusam o principal da sessão.
        if (accessor == null || !StompCommand.CONNECT.equals(accessor.getCommand())) {
            return message;
        }

        // Fase 5 (BFF): o token vem do pedido de upgrade, posto pelo gateway
        // (BffHandshakeInterceptor). O header do frame fica só como caminho de
        // quem fala direto com o drone na rede interna, e nunca vence o do upgrade.
        String authHeader = null;
        Map<String, Object> atributos = accessor.getSessionAttributes();
        if (atributos != null && atributos.get(BffHandshakeInterceptor.ATRIBUTO) instanceof String doUpgrade) {
            authHeader = doUpgrade;
        }
        if (authHeader == null) {
            authHeader = accessor.getFirstNativeHeader("Authorization");
        }
        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            throw new MessagingException("WebSocket CONNECT sem token (header Authorization ausente).");
        }
        String jwt = authHeader.substring(7);

        if (!jwtUtil.isTokenValid(jwt)) {
            throw new MessagingException("WebSocket CONNECT com token inválido/expirado.");
        }
        if (jwtUtil.isServiceToken(jwt)) {
            throw new MessagingException("WebSocket CONNECT com token de serviço.");
        }

        // Revogação imediata (Fase 10.6.5): access emitido antes do carimbo da IAM
        // é rejeitado sem esperar o exp. Token de serviço (sem user_id) → no-op.
        String userId = jwtUtil.extractUserId(jwt);
        long iat = jwtUtil.extractIssuedAtSeconds(jwt);
        if (sessionRevocationService.isSessionRevoked(userId, iat)
                || sessionRevocationService.isSidRevoked(jwtUtil.extractSid(jwt))) {
            throw new MessagingException("WebSocket CONNECT de sessão revogada.");
        }

        String username = jwtUtil.extractUsername(jwt);
        String email = jwtUtil.extractEmail(jwt);
        String tenantId = jwtUtil.extractTenantId(jwt);
        String tenantSlug = jwtUtil.extractTenantSlug(jwt);

        // O mesmo "usa o módulo?" do filtro REST (D205): o PDP, ou a claim
        // enquanto o módulo não virou.
        if (!autorizacaoService.usaModulo(tenantId, userId, jwtUtil.extractModules(jwt),
                false, requiredModule)) {
            throw new MessagingException("WebSocket CONNECT sem o módulo '" + requiredModule + "'.");
        }
        List<String> modules = List.of(requiredModule);

        // Espelho local (JIT) — preserva FKs e grava o tenant, igual ao filtro REST.
        userProvisioningService.provision(username, email, tenantId);

        IamUserPrincipal principal =
                new IamUserPrincipal(username, email, tenantId, tenantSlug, modules);
        accessor.setUser(new UsernamePasswordAuthenticationToken(
                principal, null, principal.getAuthorities()));

        logger.debug("WebSocket autenticado '{}' (tenant {}, módulos {}).",
                username, tenantId, modules);
        return message;
    }
}
