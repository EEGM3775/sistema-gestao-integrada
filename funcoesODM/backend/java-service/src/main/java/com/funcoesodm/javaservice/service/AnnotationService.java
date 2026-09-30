package com.funcoesodm.javaservice.service;

import com.funcoesodm.javaservice.dto.AnnotationCreateRequestDto;
import com.funcoesodm.javaservice.dto.AnnotationDto;
import com.funcoesodm.javaservice.dto.AnnotationUpdateRequestDto;
import com.funcoesodm.javaservice.exception.ResourceNotFoundException;
import com.funcoesodm.javaservice.exception.UnauthorizedException;
import com.funcoesodm.javaservice.model.Annotation;
import com.funcoesodm.javaservice.model.Project;
import com.funcoesodm.javaservice.model.User;
import com.funcoesodm.javaservice.repository.AnnotationRepository;
import com.funcoesodm.javaservice.repository.ProjectRepository;
import com.funcoesodm.javaservice.repository.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Service
public class AnnotationService {

    private static final Logger logger = LoggerFactory.getLogger(AnnotationService.class);

    private final AnnotationRepository annotationRepository;
    private final ProjectRepository    projectRepository;
    private final UserRepository       userRepository;
    private final WebSocketService     webSocketService;

    @Autowired
    public AnnotationService(AnnotationRepository annotationRepository,
                             ProjectRepository projectRepository,
                             UserRepository userRepository,
                             WebSocketService webSocketService) {
        this.annotationRepository = annotationRepository;
        this.projectRepository    = projectRepository;
        this.userRepository       = userRepository;
        this.webSocketService     = webSocketService;
    }

    @Transactional(readOnly = true)
    public List<AnnotationDto> getByProject(Long projectId) {
        validateProject(projectId);
        return annotationRepository.findByProjectIdWithUser(projectId)
                .stream()
                .map(AnnotationDto::fromEntity)
                .collect(Collectors.toList());
    }

    @Transactional
    public AnnotationDto create(Long projectId, String username, AnnotationCreateRequestDto request) {
        logger.info("Criando anotacao tipo={} no projeto={} pelo usuario={}", request.getType(), projectId, username);

        Project project = validateProject(projectId);
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new ResourceNotFoundException("Usuario", "username", username));

        Annotation a = new Annotation();
        a.setProject(project);
        a.setTenantId(project.getTenantId()); // Fase 8.5: tenant herdado do projeto-pai
        a.setUser(user);
        a.setType(request.getType() != null ? request.getType() : "MARKER");
        a.setCoordinatesJson(request.getCoordinatesJson() != null ? request.getCoordinatesJson() : "[]");
        a.setText(request.getText());

        Annotation saved = annotationRepository.save(a);
        AnnotationDto dto = AnnotationDto.fromEntity(saved);

        webSocketService.sendAnnotationCreated(projectId, dto);
        logger.info("Anotacao {} criada com sucesso", saved.getId());
        return dto;
    }

    @Transactional
    public AnnotationDto update(Long projectId, Long annotationId, String username,
                                String text, Boolean visible) {
        logger.info("Atualizando anotacao={} do projeto={} pelo usuario={}", annotationId, projectId, username);

        Annotation a = annotationRepository.findByIdAndProjectId(annotationId, projectId)
                .orElseThrow(() -> new ResourceNotFoundException("Anotacao", "id", annotationId));

        if (!a.getUser().getUsername().equals(username)) {
            throw new UnauthorizedException("Apenas o autor pode editar esta anotacao");
        }

        if (text != null) a.setText(text.trim());
        if (visible != null) a.setVisible(visible);

        Annotation saved = annotationRepository.save(a);
        AnnotationDto dto = AnnotationDto.fromEntity(saved);

        webSocketService.sendAnnotationUpdated(projectId, dto);
        logger.info("Anotacao {} atualizada", saved.getId());
        return dto;
    }

    @Transactional
    public void delete(Long projectId, Long annotationId, String username) {
        logger.info("Deletando anotacao={} do projeto={} pelo usuario={}", annotationId, projectId, username);

        Annotation a = annotationRepository.findByIdAndProjectId(annotationId, projectId)
                .orElseThrow(() -> new ResourceNotFoundException("Anotacao", "id", annotationId));

        if (!a.getUser().getUsername().equals(username)) {
            throw new UnauthorizedException("Apenas o autor pode excluir esta anotacao");
        }

        annotationRepository.delete(a);
        webSocketService.sendAnnotationDeleted(projectId, annotationId);
        logger.info("Anotacao {} deletada", annotationId);
    }

    private Project validateProject(Long projectId) {
        return projectRepository.findById(projectId)
                .orElseThrow(() -> new ResourceNotFoundException("Projeto", "id", projectId));
    }
}
