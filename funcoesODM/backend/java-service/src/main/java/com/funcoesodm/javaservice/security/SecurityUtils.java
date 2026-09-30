package com.funcoesodm.javaservice.security;

import com.funcoesodm.javaservice.exception.UnauthorizedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

/**
 * Acesso utilitário à identidade da IAM no contexto de segurança da request.
 *
 * <p>Centraliza a leitura do {@link IamUserPrincipal} para que os controllers e
 * serviços obtenham o {@code tenantId} corrente de forma uniforme, garantindo o
 * isolamento multi-tenant em todas as queries.
 */
public final class SecurityUtils {

    private SecurityUtils() {
    }

    public static IamUserPrincipal getCurrentPrincipal() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.getPrincipal() instanceof IamUserPrincipal principal) {
            return principal;
        }
        return null;
    }

    /** Tenant da request; lança 401 se não houver identidade (token ausente/ inválido). */
    public static String requireTenantId() {
        IamUserPrincipal principal = getCurrentPrincipal();
        if (principal == null || principal.getTenantId() == null) {
            throw new UnauthorizedException("Requisição sem tenant (token da IAM ausente ou inválido).");
        }
        return principal.getTenantId();
    }

    public static String getCurrentUsername() {
        IamUserPrincipal principal = getCurrentPrincipal();
        return principal != null ? principal.getUsername() : null;
    }
}
