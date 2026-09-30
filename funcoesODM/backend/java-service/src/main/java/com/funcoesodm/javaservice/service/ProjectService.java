package com.funcoesodm.javaservice.service;

import com.funcoesodm.javaservice.dto.ProjectCreateRequestDto;
import com.funcoesodm.javaservice.exception.ResourceNotFoundException;
import com.funcoesodm.javaservice.model.Project;
import com.funcoesodm.javaservice.model.User;
import com.funcoesodm.javaservice.repository.ChunkRepository;
import com.funcoesodm.javaservice.repository.ProcessingTaskRepository;
import com.funcoesodm.javaservice.repository.ProjectImageRepository;
import com.funcoesodm.javaservice.repository.ProjectRepository;
import com.funcoesodm.javaservice.repository.UserRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

@Service
public class ProjectService {
    private final ProjectRepository projectRepository;
    private final UserRepository userRepository;
    private final ProcessingTaskRepository processingTaskRepository;
    private final ProjectImageRepository projectImageRepository;
    private final ChunkRepository chunkRepository;

    @Autowired
    public ProjectService(ProjectRepository projectRepository,
                         UserRepository userRepository,
                         ProcessingTaskRepository processingTaskRepository,
                         ProjectImageRepository projectImageRepository,
                         ChunkRepository chunkRepository) {
        this.projectRepository = projectRepository;
        this.userRepository = userRepository;
        this.processingTaskRepository = processingTaskRepository;
        this.projectImageRepository = projectImageRepository;
        this.chunkRepository = chunkRepository;
    }

    @Transactional
    public Project createProject(ProjectCreateRequestDto projectDto, String username, String tenantId) {
        User owner = userRepository.findByUsername(username)
                .orElseThrow(() -> new ResourceNotFoundException("Usuário", "username", username));

        // NodeODM does not manage projects; create project locally

        // Create and save our internal project entity
        Project newProject = new Project();
        newProject.setName(projectDto.getName());
        newProject.setDescription(projectDto.getDescription());
        newProject.setOwner(owner);
        newProject.setTenantId(tenantId); // fronteira de tenant herdada do token da IAM
        // Vínculo com a obra/empreendimento de origem no ERP (cross-DB, sem FK).
        newProject.setEmpreendimentoId(projectDto.getEmpreendimentoId());
        newProject.setObraId(projectDto.getObraId());

        return projectRepository.save(newProject);
    }

    @Transactional(readOnly = true)
    public List<Project> getAllProjects(String tenantId) {
        return projectRepository.findAllWithOwnerByTenantId(tenantId);
    }

    @Transactional(readOnly = true)
    public Optional<Project> getProjectById(Long id, String tenantId) {
        return projectRepository.findByIdAndTenantIdWithOwner(id, tenantId);
    }

    @Transactional(readOnly = true)
    public List<Project> getProjectsByEmpreendimento(String tenantId, Long empreendimentoId) {
        return projectRepository.findAllWithOwnerByTenantIdAndEmpreendimentoId(tenantId, empreendimentoId);
    }

    @Transactional(readOnly = true)
    public List<Project> getProjectsByObra(String tenantId, Long obraId) {
        return projectRepository.findAllWithOwnerByTenantIdAndObraId(tenantId, obraId);
    }

    /** Reconciliação: ao excluir um empreendimento no ERP, desvincula (soft) os
     *  projetos de drone do tenant que apontavam para ele. Retorna quantos. */
    @Transactional
    public int unlinkEmpreendimento(String tenantId, Long empreendimentoId) {
        return projectRepository.unlinkEmpreendimento(tenantId, empreendimentoId);
    }

    /** Reconciliação: idem para exclusão de uma obra. */
    @Transactional
    public int unlinkObra(String tenantId, Long obraId) {
        return projectRepository.unlinkObra(tenantId, obraId);
    }

    @Transactional
    public Project updateProject(Long id, ProjectCreateRequestDto projectDto) {
        Project project = projectRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Projeto", "id", id));
        
        // Update only the fields that are provided
        if (projectDto.getName() != null && !projectDto.getName().trim().isEmpty()) {
            project.setName(projectDto.getName());
        }
        if (projectDto.getDescription() != null) {
            project.setDescription(projectDto.getDescription());
        }
        
        return projectRepository.save(project);
    }

    @Transactional
    public void deleteProject(Long id) {
        Project project = projectRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Projeto", "id", id));

        // Chunks nao possuem ON DELETE CASCADE no banco (criados pelo JPA sem cascade).
        // ChunkImages sao removidos em cascata pelo JPA ao deletar os Chunks.
        chunkRepository.deleteByProjectId(id);

        // processing_tasks e measurements possuem ON DELETE CASCADE no schema SQL,
        // mas deletar explicitamente garante consistencia independente do DDL.
        processingTaskRepository.deleteByProjectId(id);
        projectImageRepository.deleteByProjectId(id);

        projectRepository.delete(project);
    }
}
