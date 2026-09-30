package com.funcoesodm.javaservice.config;

import com.funcoesodm.javaservice.repository.ProjectRepository;
import com.funcoesodm.javaservice.security.IamUserPrincipal;
import com.funcoesodm.javaservice.security.SecurityUtils;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Fase 8.5 — fronteira de tenant na borda para as entidades-filhas do drone.
 *
 * <p>Todo recurso-filho vive sob {@code /api/v1/projects/{projectId}/...} (chunks,
 * tasks, measurements, annotations, images, potree). Historicamente esses caminhos
 * eram escopados apenas por {@code projectId} — um usuário do tenant A que passasse
 * o {@code projectId} do tenant B lia/gravava os filhos daquele projeto, pois os
 * serviços carregavam o projeto por {@code findById} sem conferir o tenant.
 *
 * <p>Este interceptor fecha a classe inteira num único ponto: extrai o
 * {@code projectId} da URL e exige que ele pertença ao tenant do token da IAM.
 * Não pertencendo → <b>404</b> (não revela existência). Como roda para todo
 * {@code /api/v1/projects/**}, também endurece o próprio recurso {@code projects/{id}}
 * (update/delete antes só checavam o dono por username) e qualquer rota-filha
 * futura passa a nascer protegida — não há como esquecer.
 *
 * <p>Requisições sem identidade (rotas públicas de asset/thumbnail liberadas no
 * {@code SecurityConfig}, ou pré-flight) são deixadas passar: a autenticação já é
 * responsabilidade do filtro/So config, aqui só cuidamos do isolamento entre tenants.
 */
@Component
public class ProjectTenantInterceptor implements HandlerInterceptor {

    private static final Logger logger = LoggerFactory.getLogger(ProjectTenantInterceptor.class);

    /** Captura o projectId numérico logo após ".../projects/" (tolerante a prefixo do gateway). */
    private static final Pattern PROJECT_ID = Pattern.compile("/projects/(\\d+)(?:/|$)");

    private final ProjectRepository projectRepository;

    public ProjectTenantInterceptor(ProjectRepository projectRepository) {
        this.projectRepository = projectRepository;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        IamUserPrincipal principal = SecurityUtils.getCurrentPrincipal();
        // Sem identidade (rota pública) → nada a isolar; o SecurityConfig já decide o acesso.
        if (principal == null || principal.getTenantId() == null) {
            return true;
        }

        Matcher m = PROJECT_ID.matcher(request.getRequestURI());
        // Rota sem {projectId} concreto (ex.: POST /api/v1/projects, GET lista) → nada a conferir.
        if (!m.find()) {
            return true;
        }

        final Long projectId;
        try {
            projectId = Long.valueOf(m.group(1));
        } catch (NumberFormatException e) {
            return true; // id não numérico não referencia um projeto concreto
        }

        String tenantId = principal.getTenantId();
        if (projectRepository.existsByIdAndTenantId(projectId, tenantId)) {
            return true;
        }

        // Projeto inexistente OU de outro tenant: mesma resposta (não vaza existência).
        logger.warn("Bloqueio cross-tenant: usuário '{}' (tenant {}) tentou acessar o projeto {} em {} {}",
                principal.getUsername(), tenantId, projectId, request.getMethod(), request.getRequestURI());
        response.setStatus(HttpServletResponse.SC_NOT_FOUND);
        response.setContentType("application/json");
        response.getWriter().write("{\"error\":\"Projeto não encontrado\"}");
        return false;
    }
}
