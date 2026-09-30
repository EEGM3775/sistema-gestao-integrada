package com.funcoesodm.javaservice.controller;

import com.funcoesodm.javaservice.dto.MeasurementCreateRequestDto;
import com.funcoesodm.javaservice.dto.MeasurementDto;
import com.funcoesodm.javaservice.service.GeoPackageExportService;
import com.funcoesodm.javaservice.service.MeasurementService;
import jakarta.validation.Valid;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Endpoints REST para medições (distância, área, volume, altura) associadas
 * a um projeto e a um chunk (tarefa de processamento) específico.
 *
 * Base URL: /api/v1/projects/{projectId}/chunks/{chunkId}/measurements
 *
 * Também expõe listagem de todas as medições do projeto:
 *   GET /api/v1/projects/{projectId}/measurements
 */
@RestController
public class MeasurementController {

    private static final Logger logger = LoggerFactory.getLogger(MeasurementController.class);

    private final MeasurementService       measurementService;
    private final GeoPackageExportService  geoPackageExportService;

    @Autowired
    public MeasurementController(MeasurementService measurementService,
                                 GeoPackageExportService geoPackageExportService) {
        this.measurementService      = measurementService;
        this.geoPackageExportService = geoPackageExportService;
    }

    // ─── Exportação GeoPackage ───────────────────────────────────────────────────

    /**
     * Gera e retorna arquivo GeoPackage (.gpkg) com todas as medições do projeto.
     * Processado inteiramente no servidor Java (sem WASM no browser).
     *
     * GET /api/v1/projects/{projectId}/measurements/export/gpkg
     *   ?coordFormat=wgs84|utm   (padrão: wgs84)
     *   &epsg=32724              (opcional — EPSG do fuso UTM de saída)
     */
    @GetMapping("/api/v1/projects/{projectId}/measurements/export/gpkg")
    public ResponseEntity<byte[]> exportGeoPackage(
            @PathVariable Long projectId,
            @RequestParam(defaultValue = "wgs84") String coordFormat,
            @RequestParam(required = false) Integer epsg) {

        logger.info("GET export/gpkg projeto={} coordFormat={} epsg={}", projectId, coordFormat, epsg);
        byte[] data = geoPackageExportService.generateForProject(projectId, coordFormat, epsg);

        String filename = "medicoes_projeto_" + projectId + ".gpkg";
        return ResponseEntity.ok()
                .header("Content-Disposition", "attachment; filename=\"" + filename + "\"")
                .header("Content-Type", "application/geopackage+sqlite3")
                .body(data);
    }

    // ─── Listagem por projeto ────────────────────────────────────────────────────

    /**
     * Retorna todas as medições de um projeto (todos os chunks).
     * GET /api/v1/projects/{projectId}/measurements
     */
    @GetMapping("/api/v1/projects/{projectId}/measurements")
    public ResponseEntity<List<MeasurementDto>> getMeasurementsByProject(
            @PathVariable Long projectId) {
        List<MeasurementDto> measurements = measurementService.getMeasurementsByProject(projectId);
        return ResponseEntity.ok(measurements);
    }

    // ─── Operações por chunk ─────────────────────────────────────────────────────

    /**
     * Retorna medições de um chunk específico.
     * GET /api/v1/projects/{projectId}/chunks/{chunkId}/measurements
     */
    @GetMapping("/api/v1/projects/{projectId}/chunks/{chunkId}/measurements")
    public ResponseEntity<List<MeasurementDto>> getMeasurementsByChunk(
            @PathVariable Long projectId,
            @PathVariable Long chunkId) {
        List<MeasurementDto> measurements = measurementService.getMeasurementsByChunk(projectId, chunkId);
        return ResponseEntity.ok(measurements);
    }

    /**
     * Cria uma nova medição vinculada ao chunk.
     * POST /api/v1/projects/{projectId}/chunks/{chunkId}/measurements
     */
    @PostMapping("/api/v1/projects/{projectId}/chunks/{chunkId}/measurements")
    public ResponseEntity<MeasurementDto> createMeasurement(
            @PathVariable Long projectId,
            @PathVariable Long chunkId,
            @Valid @RequestBody MeasurementCreateRequestDto request) {

        logger.info("POST medição '{}' para projeto={} chunk={}", request.getName(), projectId, chunkId);
        MeasurementDto created = measurementService.createMeasurement(projectId, chunkId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    // ─── Deleção ─────────────────────────────────────────────────────────────────

    /**
     * Remove uma medição.
     * DELETE /api/v1/projects/{projectId}/measurements/{measurementId}
     */
    @DeleteMapping("/api/v1/projects/{projectId}/measurements/{measurementId}")
    public ResponseEntity<Void> deleteMeasurement(
            @PathVariable Long projectId,
            @PathVariable Long measurementId) {

        logger.info("DELETE medição={} do projeto={}", measurementId, projectId);
        measurementService.deleteMeasurement(projectId, measurementId);
        return ResponseEntity.noContent().build();
    }

    // ─── Visibilidade ────────────────────────────────────────────────────────────

    /**
     * Altera visibilidade de uma medição.
     * PATCH /api/v1/projects/{projectId}/measurements/{measurementId}/visibility
     */
    @PatchMapping("/api/v1/projects/{projectId}/measurements/{measurementId}/visibility")
    public ResponseEntity<MeasurementDto> updateVisibility(
            @PathVariable Long projectId,
            @PathVariable Long measurementId,
            @RequestBody java.util.Map<String, Boolean> body) {

        boolean visible = body.getOrDefault("visible", true);
        logger.info("PATCH visibilidade da medição={} -> {}", measurementId, visible);
        MeasurementDto updated = measurementService.updateVisibility(projectId, measurementId, visible);
        return ResponseEntity.ok(updated);
    }

    // ─── Renomeação ───────────────────────────────────────────────────────────────

    /**
     * Renomeia uma medição.
     * PATCH /api/v1/projects/{projectId}/measurements/{measurementId}/name
     */
    @PatchMapping("/api/v1/projects/{projectId}/measurements/{measurementId}/name")
    public ResponseEntity<MeasurementDto> renameMeasurement(
            @PathVariable Long projectId,
            @PathVariable Long measurementId,
            @RequestBody java.util.Map<String, String> body) {

        String newName = body.getOrDefault("name", "");
        logger.info("PATCH nome da medição={} para '{}'", measurementId, newName);
        MeasurementDto updated = measurementService.renameMeasurement(projectId, measurementId, newName);
        return ResponseEntity.ok(updated);
    }
}
