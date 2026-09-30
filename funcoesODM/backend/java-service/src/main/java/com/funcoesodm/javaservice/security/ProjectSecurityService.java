package com.funcoesodm.javaservice.security;

import com.funcoesodm.javaservice.model.Project;
import com.funcoesodm.javaservice.repository.ProjectRepository;
import org.springframework.stereotype.Component;

@Component("projectSecurity")
public class ProjectSecurityService {
    
    private final ProjectRepository projectRepository;
    
    public ProjectSecurityService(ProjectRepository projectRepository) {
        this.projectRepository = projectRepository;
    }
    
    /**
     * Verifica se o usuário é o dono do projeto
     */
    public boolean isOwner(Long projectId, String username) {
        return projectRepository.findByIdWithOwner(projectId)
                .map(project -> project.getOwner().getUsername().equals(username))
                .orElse(false);
    }
    
    /**
     * Verifica se o usuário pode acessar o projeto (por enquanto, qualquer usuário autenticado)
     * No futuro, pode incluir lógica de compartilhamento
     */
    public boolean canAccess(Long projectId, String username) {
        return isOwner(projectId, username);
        // TODO: Adicionar lógica de compartilhamento se necessário
    }
    
    /**
     * Verifica se o usuário pode modificar o projeto
     */
    public boolean canModify(Long projectId, String username) {
        return isOwner(projectId, username);
    }
    
    /**
     * Verifica se o usuário pode deletar o projeto
     */
    public boolean canDelete(Long projectId, String username) {
        return true;
    }
}
