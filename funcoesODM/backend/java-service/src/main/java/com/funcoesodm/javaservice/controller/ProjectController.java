package com.funcoesodm.javaservice.controller;

import com.funcoesodm.javaservice.dto.ImageUploadResponseDto;
import com.funcoesodm.javaservice.dto.ProjectCreateRequestDto;
import com.funcoesodm.javaservice.dto.ProjectImageDto;
import com.funcoesodm.javaservice.dto.ProjectResponseDto;
import com.funcoesodm.javaservice.exception.ResourceNotFoundException;
import com.funcoesodm.javaservice.exception.UnauthorizedException;
import com.funcoesodm.javaservice.model.Project;
import com.funcoesodm.javaservice.security.ProjectSecurityService;
import com.funcoesodm.javaservice.security.SecurityUtils;
import com.funcoesodm.javaservice.service.ProjectImageService;
import com.funcoesodm.javaservice.service.ProjectService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.security.Principal;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@RestController
@RequestMapping("/api/v1/projects")
public class ProjectController {

    private final ProjectService projectService;
    private final ProjectImageService imageService;
    private final ProjectSecurityService projectSecurity;

    @Autowired
    public ProjectController(ProjectService projectService, 
                            ProjectImageService imageService,
                            ProjectSecurityService projectSecurity) {
        this.projectService = projectService;
        this.imageService = imageService;
        this.projectSecurity = projectSecurity;
    }

    @GetMapping
    public ResponseEntity<List<ProjectResponseDto>> getAllProjects(
            @RequestParam(required = false) Long empreendimentoId,
            @RequestParam(required = false) Long obraId,
            Principal principal) {
        // Isolamento multi-tenant: lista apenas projetos do tenant do token.
        // Filtros opcionais por empreendimento/obra (vínculo com o ERP, Fase 3) —
        // ex.: o ERP lista os projetos de drone de uma obra via ?obraId=.
        String tenantId = SecurityUtils.requireTenantId();
        final List<Project> projects;
        if (obraId != null) {
            projects = projectService.getProjectsByObra(tenantId, obraId);
        } else if (empreendimentoId != null) {
            projects = projectService.getProjectsByEmpreendimento(tenantId, empreendimentoId);
        } else {
            projects = projectService.getAllProjects(tenantId);
        }
        List<ProjectResponseDto> response = projects.stream()
                .map(ProjectResponseDto::fromEntity)
                .collect(Collectors.toList());
        return ResponseEntity.ok(response);
    }

    // ===== Reconciliação cross-DB (Fase 3) =====
    // O ERP chama estes endpoints ao excluir uma obra/empreendimento, para
    // desvincular (soft) os projetos de drone órfãos do tenant. Exige o módulo
    // 'drone' (SecurityConfig) e é escopado ao tenant do token.

    @DeleteMapping("/links/empreendimento/{empreendimentoId}")
    public ResponseEntity<Map<String, Object>> unlinkEmpreendimento(
            @PathVariable Long empreendimentoId, Principal principal) {
        String tenantId = SecurityUtils.requireTenantId();
        int afetados = projectService.unlinkEmpreendimento(tenantId, empreendimentoId);
        return ResponseEntity.ok(Map.of("unlinked", afetados, "empreendimentoId", empreendimentoId));
    }

    @DeleteMapping("/links/obra/{obraId}")
    public ResponseEntity<Map<String, Object>> unlinkObra(
            @PathVariable Long obraId, Principal principal) {
        String tenantId = SecurityUtils.requireTenantId();
        int afetados = projectService.unlinkObra(tenantId, obraId);
        return ResponseEntity.ok(Map.of("unlinked", afetados, "obraId", obraId));
    }

    @PostMapping
    public ResponseEntity<ProjectResponseDto> createProject(@RequestBody ProjectCreateRequestDto projectDto, Principal principal) {
        if (principal == null) {
            throw new UsernameNotFoundException("Cannot create a project without a logged-in user.");
        }

        String tenantId = SecurityUtils.requireTenantId();
        Project createdProject = projectService.createProject(projectDto, principal.getName(), tenantId);
        return ResponseEntity.ok(ProjectResponseDto.fromEntity(createdProject));
    }

    @GetMapping("/{id}")
    public ResponseEntity<ProjectResponseDto> getProjectById(@PathVariable Long id, Principal principal) {
        // Só retorna o projeto se pertencer ao tenant do token (404 caso contrário).
        String tenantId = SecurityUtils.requireTenantId();
        return projectService.getProjectById(id, tenantId)
                .map(project -> ResponseEntity.ok(ProjectResponseDto.fromEntity(project)))
                .orElseThrow(() -> new ResourceNotFoundException("Projeto", "id", id));
    }

    @PutMapping("/{id}")
    public ResponseEntity<ProjectResponseDto> updateProject(
            @PathVariable Long id, 
            @RequestBody ProjectCreateRequestDto projectDto,
            Principal principal) {
        if (principal == null) {
            throw new UnauthorizedException("Usuário não autenticado");
        }
        
        // Verificar se o usuário pode modificar o projeto
        if (!projectSecurity.canModify(id, principal.getName())) {
            throw new UnauthorizedException("modificar", "projeto");
        }
        
        Project updatedProject = projectService.updateProject(id, projectDto);
        return ResponseEntity.ok(ProjectResponseDto.fromEntity(updatedProject));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> deleteProject(@PathVariable Long id, Principal principal) {
        if (principal == null) {
            throw new UnauthorizedException("Usuário não autenticado");
        }
        
        // Verificar se o usuário pode deletar o projeto
        if (!projectSecurity.canDelete(id, principal.getName())) {
            throw new UnauthorizedException("deletar", "projeto");
        }
        
        projectService.deleteProject(id);
        return ResponseEntity.noContent().build();
    }

    // ============== Image Endpoints ==============

    @PostMapping(value = "/{id}/images", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ImageUploadResponseDto> uploadImages(
            @PathVariable Long id,
            @RequestParam("files") List<MultipartFile> files,
            Principal principal) {
        if (principal == null) {
            throw new UnauthorizedException("Usuário não autenticado");
        }
        
        // Verificar se o usuário pode modificar o projeto
        if (!projectSecurity.canModify(id, principal.getName())) {
            throw new UnauthorizedException("modificar", "projeto");
        }
        
        ImageUploadResponseDto response = imageService.uploadImages(id, files, principal.getName());
        return ResponseEntity.ok(response);
    }

    @GetMapping("/{id}/images")
    public ResponseEntity<List<ProjectImageDto>> getProjectImages(@PathVariable Long id) {
        List<ProjectImageDto> images = imageService.getProjectImages(id);
        return ResponseEntity.ok(images);
    }

    @DeleteMapping("/{projectId}/images/{imageId}")
    public ResponseEntity<Void> deleteImage(
            @PathVariable Long projectId,
            @PathVariable Long imageId,
            Principal principal) {
        if (principal == null) {
            throw new UnauthorizedException("Usuário não autenticado");
        }
        
        if (!projectSecurity.canModify(projectId, principal.getName())) {
            throw new UnauthorizedException("modificar", "projeto");
        }
        
        imageService.deleteImage(imageId);
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/{id}/images")
    public ResponseEntity<Void> deleteAllImages(@PathVariable Long id, Principal principal) {
        if (principal == null) {
            throw new UnauthorizedException("Usuário não autenticado");
        }
        
        if (!projectSecurity.canModify(id, principal.getName())) {
            throw new UnauthorizedException("modificar", "projeto");
        }
        
        imageService.deleteAllProjectImages(id);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/{projectId}/images/{imageId}/thumbnail")
    public ResponseEntity<Resource> getImageThumbnail(
            @PathVariable Long projectId,
            @PathVariable Long imageId) {
        
        try {
            Resource thumbnail = imageService.getImageThumbnail(imageId);
            if (thumbnail != null && thumbnail.exists()) {
                return ResponseEntity.ok()
                        .contentType(MediaType.IMAGE_JPEG)
                        .body(thumbnail);
            }
        } catch (Exception e) {
            // Log error but return 404 instead of 500
            org.slf4j.LoggerFactory.getLogger(ProjectController.class)
                .warn("Thumbnail not found for image {}: {}", imageId, e.getMessage());
        }
        return ResponseEntity.notFound().build();
    }
}
