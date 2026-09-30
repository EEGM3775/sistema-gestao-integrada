package com.funcoesodm.javaservice.config;

import com.funcoesodm.javaservice.security.AutorizacaoService;
import com.funcoesodm.javaservice.security.IamUserPrincipal;
import com.funcoesodm.javaservice.service.UserProvisioningService;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.lang.NonNull;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;

/**
 * Valida o JWT da IAM em cada requisição e popula o contexto de segurança.
 *
 * <p>Fluxo (resource server): valida assinatura + expiração → extrai
 * {@code sub}/{@code tenant_id} → faz JIT provisioning do usuário local →
 * pergunta "usa o módulo?" ao {@link AutorizacaoService} (o PDP, ou a claim
 * {@code modules} enquanto o módulo não virou) → autentica com um
 * {@link IamUserPrincipal} que só tem {@code MODULE_<código>} se a resposta foi
 * sim. O enforcement do entitlement fica no {@code SecurityConfig}.
 */
@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final Logger logger = LoggerFactory.getLogger(JwtAuthenticationFilter.class);

    private final JwtUtil jwtUtil;
    private final UserProvisioningService userProvisioningService;
    private final SessionRevocationService sessionRevocationService;
    private final AutorizacaoService autorizacaoService;

    /** Módulo (entitlement) exigido para acessar este produto — o do {@code SecurityConfig}. */
    @Value("${app.module.required:drone}")
    private String requiredModule;

    /**
     * Fase 5 (§10.6): o token de serviço só entra onde o serviço tem o que fazer —
     * o desvínculo de projetos que o backend pede ao excluir obra ou
     * empreendimento — e só com o escopo dele. Em qualquer outra rota, não autentica.
     */
    static final String ESCOPO_DESVINCULAR = "drone.projetos.desvincular";
    static final String ROTA_DESVINCULAR = "/api/v1/projects/links/";

    static boolean servicoPodeAqui(String metodo, String caminho, String escopo) {
        return "DELETE".equals(metodo)
                && caminho != null && caminho.startsWith(ROTA_DESVINCULAR)
                && ESCOPO_DESVINCULAR.equals(escopo);
    }

    public JwtAuthenticationFilter(JwtUtil jwtUtil,
                                   UserProvisioningService userProvisioningService,
                                   SessionRevocationService sessionRevocationService,
                                   AutorizacaoService autorizacaoService) {
        this.jwtUtil = jwtUtil;
        this.userProvisioningService = userProvisioningService;
        this.sessionRevocationService = sessionRevocationService;
        this.autorizacaoService = autorizacaoService;
    }

    @Override
    protected void doFilterInternal(
            @NonNull HttpServletRequest request,
            @NonNull HttpServletResponse response,
            @NonNull FilterChain filterChain
    ) throws ServletException, IOException {
        final String authHeader = request.getHeader("Authorization");

        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            filterChain.doFilter(request, response);
            return;
        }

        final String jwt = authHeader.substring(7);

        try {
            if (jwtUtil.isTokenValid(jwt)
                    && SecurityContextHolder.getContext().getAuthentication() == null) {

                String username = jwtUtil.extractUsername(jwt);
                String email = jwtUtil.extractEmail(jwt);
                String tenantId = jwtUtil.extractTenantId(jwt);
                String tenantSlug = jwtUtil.extractTenantSlug(jwt);
                List<String> modules = jwtUtil.extractModules(jwt);

                // Revogação imediata (Fase 10.6.5): troca/reset de senha ou
                // desativação na IAM carimba `sess:revoked_after:<user_id>` no
                // Redis; access token emitido antes disso é rejeitado aqui, sem
                // esperar o `exp`. Sessão revogada → não autentica (o
                // SecurityConfig responde 401 nas rotas protegidas).
                String userId = jwtUtil.extractUserId(jwt);
                long iat = jwtUtil.extractIssuedAtSeconds(jwt);
                boolean servico = jwtUtil.isServiceToken(jwt);
                if (servico) {
                    if (servicoPodeAqui(request.getMethod(), request.getRequestURI(), jwtUtil.extractScope(jwt))) {
                        userProvisioningService.provision(username, null, tenantId);
                        IamUserPrincipal principal = new IamUserPrincipal(
                                username, null, tenantId, null, List.of(requiredModule));
                        UsernamePasswordAuthenticationToken authToken =
                                new UsernamePasswordAuthenticationToken(principal, null, principal.getAuthorities());
                        authToken.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));
                        SecurityContextHolder.getContext().setAuthentication(authToken);
                    } else {
                        logger.info("Token de serviço fora da rota do escopo dele ({} {}); não autentica.",
                                request.getMethod(), request.getRequestURI());
                    }
                } else if (sessionRevocationService.isSessionRevoked(userId, iat)) {
                    logger.info("Sessão revogada na IAM (user_id={}); acesso negado.", userId);
                } else if (sessionRevocationService.isSidRevoked(jwtUtil.extractSid(jwt))) {
                    logger.info("Sessão encerrada na IAM (user_id={}); acesso negado.", userId);
                } else if (username != null) {
                    // Espelho local (JIT) — preserva FKs e grava o tenant.
                    userProvisioningService.provision(username, email, tenantId);

                    boolean usa = autorizacaoService.usaModulo(
                            tenantId, userId, modules, false, requiredModule);
                    IamUserPrincipal principal = new IamUserPrincipal(
                            username, email, tenantId, tenantSlug, usa ? List.of(requiredModule) : List.of());

                    UsernamePasswordAuthenticationToken authToken =
                            new UsernamePasswordAuthenticationToken(
                                    principal, null, principal.getAuthorities());
                    authToken.setDetails(
                            new WebAuthenticationDetailsSource().buildDetails(request));
                    SecurityContextHolder.getContext().setAuthentication(authToken);
                    logger.debug("Autenticado '{}' (tenant {}, módulos {})",
                            username, tenantId, modules);
                }
            }
        } catch (Exception e) {
            logger.error("Erro ao processar JWT da IAM: {}", e.getMessage());
        }

        filterChain.doFilter(request, response);
    }
}
