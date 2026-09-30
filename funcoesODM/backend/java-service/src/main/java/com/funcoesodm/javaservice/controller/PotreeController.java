package com.funcoesodm.javaservice.controller;

import com.funcoesodm.javaservice.service.PotreeService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * Endpoints para conversao e status Potree.
 *
 * GET /api/v1/projects/{projectId}/tasks/{taskId}/potree
 *   Retorna status da conversao. Se nao iniciada, inicia automaticamente.
 *   Response: { status, tilesUrl?, error?, startedAt?, completedAt? }
 *
 * Polling recomendado: 3s enquanto status = "converting"
 */
@RestController
@RequestMapping("/api/v1/projects/{projectId}/tasks/{taskId}/potree")
public class PotreeController {

    private final PotreeService potreeService;

    public PotreeController(PotreeService potreeService) {
        this.potreeService = potreeService;
    }

    @GetMapping
    public ResponseEntity<PotreeService.PotreeStatusResponse> getPotreeStatus(
            @PathVariable Long projectId,
            @PathVariable Long taskId) {

        PotreeService.PotreeStatusResponse status = potreeService.getOrStartConversion(projectId, taskId);

        if ("not_found".equals(status.status())) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok(status);
    }
}
