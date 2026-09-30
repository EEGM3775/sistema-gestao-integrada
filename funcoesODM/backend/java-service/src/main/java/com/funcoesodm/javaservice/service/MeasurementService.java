package com.funcoesodm.javaservice.service;

import com.funcoesodm.javaservice.dto.MeasurementCreateRequestDto;
import com.funcoesodm.javaservice.dto.MeasurementDto;
import com.funcoesodm.javaservice.exception.ResourceNotFoundException;
import com.funcoesodm.javaservice.model.Measurement;
import com.funcoesodm.javaservice.model.Project;
import com.funcoesodm.javaservice.repository.MeasurementRepository;
import com.funcoesodm.javaservice.repository.ProjectRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class MeasurementService {

    private static final Logger logger = LoggerFactory.getLogger(MeasurementService.class);
    private static final ObjectMapper objectMapper = new ObjectMapper();

    private final MeasurementRepository measurementRepository;
    private final ProjectRepository projectRepository;

    @Autowired
    public MeasurementService(MeasurementRepository measurementRepository,
                               ProjectRepository projectRepository) {
        this.measurementRepository = measurementRepository;
        this.projectRepository = projectRepository;
    }

    // ─── Leitura ────────────────────────────────────────────────────────────────

    /**
     * Retorna todas as medições de um projeto.
     */
    @Transactional(readOnly = true)
    public List<MeasurementDto> getMeasurementsByProject(Long projectId) {
        logger.debug("Buscando medições do projeto {}", projectId);
        validateProject(projectId);
        return measurementRepository.findByProjectIdOrderByCreatedAtDesc(projectId)
                .stream()
                .map(MeasurementDto::fromEntity)
                .collect(Collectors.toList());
    }

    /**
     * Retorna medições de um chunk específico dentro de um projeto.
     */
    @Transactional(readOnly = true)
    public List<MeasurementDto> getMeasurementsByChunk(Long projectId, Long chunkId) {
        logger.debug("Buscando medições do chunk {} no projeto {}", chunkId, projectId);
        validateProject(projectId);
        return measurementRepository.findByProjectIdAndChunkIdOrderByCreatedAtDesc(projectId, chunkId)
                .stream()
                .map(MeasurementDto::fromEntity)
                .collect(Collectors.toList());
    }

    // ─── Criação ────────────────────────────────────────────────────────────────

    /**
     * Cria uma nova medição para um chunk de um projeto.
     */
    @Transactional
    public MeasurementDto createMeasurement(Long projectId, Long chunkId,
                                            MeasurementCreateRequestDto request) {
        logger.info("Criando medição '{}' (tipo={}) para projeto={} chunk={}",
                request.getName(), request.getType(), projectId, chunkId);

        Project project = validateProject(projectId);

        Measurement m = new Measurement();
        m.setProject(project);
        m.setTenantId(project.getTenantId()); // Fase 8.5: tenant herdado do projeto-pai
        m.setChunkId(chunkId);
        m.setName(request.getName());
        m.setType(request.getType());
        m.setValue(request.getValue());
        m.setUnit(request.getUnit());
        m.setDataSource(request.getDataSource());

        // Serializa coordenadas para JSON
        if (request.getCoordinates() != null && !request.getCoordinates().isEmpty()) {
            try {
                m.setCoordinatesJson(objectMapper.writeValueAsString(request.getCoordinates()));
            } catch (JsonProcessingException e) {
                logger.warn("Falha ao serializar coordenadas: {}", e.getMessage());
                m.setCoordinatesJson("[]");
            }
        } else {
            m.setCoordinatesJson("[]");
        }

        Measurement saved = measurementRepository.save(m);
        logger.info("Medição {} criada com sucesso", saved.getId());
        return MeasurementDto.fromEntity(saved);
    }

    // ─── Deleção ────────────────────────────────────────────────────────────────

    /**
     * Remove uma medição garantindo que ela pertence ao projeto informado.
     */
    @Transactional
    public void deleteMeasurement(Long projectId, Long measurementId) {
        logger.info("Deletando medição {} do projeto {}", measurementId, projectId);

        Measurement m = measurementRepository.findByIdAndProjectId(measurementId, projectId)
                .orElseThrow(() -> new ResourceNotFoundException("Medição", "id", measurementId));

        measurementRepository.delete(m);
        logger.info("Medição {} deletada", measurementId);
    }

    // ─── Renomeação ──────────────────────────────────────────────────────────────

    /**
     * Atualiza o nome de uma medição.
     */
    @Transactional
    public MeasurementDto renameMeasurement(Long projectId, Long measurementId, String newName) {
        logger.info("Renomeando medição {} do projeto {} para '{}'", measurementId, projectId, newName);

        Measurement m = measurementRepository.findByIdAndProjectId(measurementId, projectId)
                .orElseThrow(() -> new ResourceNotFoundException("Medição", "id", measurementId));

        m.setName(newName != null ? newName.trim() : "");
        Measurement saved = measurementRepository.save(m);
        logger.info("Medição {} renomeada com sucesso", saved.getId());
        return MeasurementDto.fromEntity(saved);
    }

    // ─── Visibilidade ────────────────────────────────────────────────────────────

    /**
     * Altera a visibilidade de uma medição (visível/oculta no mapa).
     */
    @Transactional
    public MeasurementDto updateVisibility(Long projectId, Long measurementId, boolean visible) {
        logger.info("Visibilidade da medição {} -> {}", measurementId, visible);

        Measurement m = measurementRepository.findByIdAndProjectId(measurementId, projectId)
                .orElseThrow(() -> new ResourceNotFoundException("Medição", "id", measurementId));

        m.setVisible(visible);
        return MeasurementDto.fromEntity(measurementRepository.save(m));
    }

    // ─── Helpers ────────────────────────────────────────────────────────────────

    private Project validateProject(Long projectId) {
        return projectRepository.findById(projectId)
                .orElseThrow(() -> new ResourceNotFoundException("Projeto", "id", projectId));
    }
}
