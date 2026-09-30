package com.funcoesodm.javaservice.controller;

import com.funcoesodm.javaservice.dto.AnnotationCreateRequestDto;
import com.funcoesodm.javaservice.dto.AnnotationDto;
import com.funcoesodm.javaservice.dto.AnnotationUpdateRequestDto;
import com.funcoesodm.javaservice.service.AnnotationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.security.Principal;
import java.util.List;

@RestController
public class AnnotationController {

    private static final Logger logger = LoggerFactory.getLogger(AnnotationController.class);

    private final AnnotationService annotationService;

    @Autowired
    public AnnotationController(AnnotationService annotationService) {
        this.annotationService = annotationService;
    }

    /** GET /api/v1/projects/{projectId}/annotations */
    @GetMapping("/api/v1/projects/{projectId}/annotations")
    public ResponseEntity<List<AnnotationDto>> getAnnotations(@PathVariable Long projectId) {
        logger.info("GET anotacoes do projeto={}", projectId);
        return ResponseEntity.ok(annotationService.getByProject(projectId));
    }

    /** POST /api/v1/projects/{projectId}/annotations */
    @PostMapping("/api/v1/projects/{projectId}/annotations")
    public ResponseEntity<AnnotationDto> createAnnotation(
            @PathVariable Long projectId,
            @RequestBody AnnotationCreateRequestDto request,
            Principal principal) {
        logger.info("POST anotacao no projeto={} pelo usuario={}", projectId, principal.getName());
        AnnotationDto created = annotationService.create(projectId, principal.getName(), request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    /** PATCH /api/v1/projects/{projectId}/annotations/{annotationId} */
    @PatchMapping("/api/v1/projects/{projectId}/annotations/{annotationId}")
    public ResponseEntity<AnnotationDto> updateAnnotation(
            @PathVariable Long projectId,
            @PathVariable Long annotationId,
            @RequestBody AnnotationUpdateRequestDto request,
            Principal principal) {
        logger.info("PATCH anotacao={} do projeto={} pelo usuario={}", annotationId, projectId, principal.getName());
        AnnotationDto updated = annotationService.update(projectId, annotationId, principal.getName(),
                request.getText(), request.getVisible());
        return ResponseEntity.ok(updated);
    }

    /** DELETE /api/v1/projects/{projectId}/annotations/{annotationId} */
    @DeleteMapping("/api/v1/projects/{projectId}/annotations/{annotationId}")
    public ResponseEntity<Void> deleteAnnotation(
            @PathVariable Long projectId,
            @PathVariable Long annotationId,
            Principal principal) {
        logger.info("DELETE anotacao={} do projeto={} pelo usuario={}", annotationId, projectId, principal.getName());
        annotationService.delete(projectId, annotationId, principal.getName());
        return ResponseEntity.noContent().build();
    }
}
