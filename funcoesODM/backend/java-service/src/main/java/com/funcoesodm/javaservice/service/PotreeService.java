package com.funcoesodm.javaservice.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.funcoesodm.javaservice.model.ProcessingTask;
import com.funcoesodm.javaservice.repository.ProcessingTaskRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.Map;
import java.util.Optional;

/**
 * Gerencia conversao de point clouds LAZ para tiles Potree.
 *
 * Fluxo:
 *  1. Frontend solicita status de conversao para uma task
 *  2. Se nao iniciada, backend chama POST /convert no potree-converter-service
 *  3. Frontend faz polling em GET /status ate status=ready
 *  4. Quando ready, tilesUrl aponta para /potree-tiles/{nodeodm_task_uuid}/
 */
@Service
public class PotreeService {

    private static final Logger logger = LoggerFactory.getLogger(PotreeService.class);

    private final ProcessingTaskRepository taskRepository;
    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;

    @Value("${potree.converter.url:http://potree-converter:5001}")
    private String converterUrl;

    public PotreeService(ProcessingTaskRepository taskRepository,
                         RestTemplate restTemplate,
                         ObjectMapper objectMapper) {
        this.taskRepository = taskRepository;
        this.restTemplate = restTemplate;
        this.objectMapper = objectMapper;
    }

    public record PotreeStatusResponse(
            String status,        // not_started | converting | ready | failed
            String tilesUrl,      // preenchido quando ready
            String error,         // preenchido quando failed
            String startedAt,
            String completedAt
    ) {}

    /**
     * Retorna o status atual da conversao Potree para a task.
     * Se nao iniciada, inicia automaticamente.
     */
    public PotreeStatusResponse getOrStartConversion(Long projectId, Long taskId) {
        Optional<ProcessingTask> taskOpt = taskRepository.findByIdWithProject(taskId);
        if (taskOpt.isEmpty()) {
            return new PotreeStatusResponse("not_found", null, "Task nao encontrada", null, null);
        }

        ProcessingTask task = taskOpt.get();
        if (task.getProject() == null || !task.getProject().getId().equals(projectId)) {
            return new PotreeStatusResponse("not_found", null, "Task nao pertence ao projeto", null, null);
        }

        String nodeodmUuid = task.getNodeodmTaskId();
        if (nodeodmUuid == null || nodeodmUuid.isBlank()) {
            return new PotreeStatusResponse("not_started", null, "Task sem UUID NodeODM", null, null);
        }

        // Consulta status no converter service
        PotreeStatusResponse current = fetchConverterStatus(nodeodmUuid);

        if ("not_started".equals(current.status())) {
            triggerConversion(nodeodmUuid);
            return new PotreeStatusResponse("converting", null, null, null, null);
        }

        if ("ready".equals(current.status())) {
            String tilesUrl = "/potree-tiles/" + nodeodmUuid + "/";
            return new PotreeStatusResponse("ready", tilesUrl, null, current.startedAt(), current.completedAt());
        }

        return current;
    }

    private PotreeStatusResponse fetchConverterStatus(String nodeodmUuid) {
        try {
            String url = converterUrl + "/status/" + nodeodmUuid;
            ResponseEntity<JsonNode> resp = restTemplate.getForEntity(url, JsonNode.class);
            if (resp.getBody() != null) {
                JsonNode body = resp.getBody();
                return new PotreeStatusResponse(
                        body.path("status").asText("not_started"),
                        null,
                        body.has("error") ? body.get("error").asText() : null,
                        body.has("startedAt") ? body.get("startedAt").asText() : null,
                        body.has("completedAt") ? body.get("completedAt").asText() : null
                );
            }
        } catch (Exception e) {
            logger.warn("[Potree] Erro ao consultar status do converter: {}", e.getMessage());
        }
        return new PotreeStatusResponse("not_started", null, null, null, null);
    }

    private void triggerConversion(String nodeodmUuid) {
        try {
            String url = converterUrl + "/convert";
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            HttpEntity<Map<String, String>> request = new HttpEntity<>(
                    Map.of("taskUuid", nodeodmUuid), headers);
            restTemplate.postForEntity(url, request, JsonNode.class);
            logger.info("[Potree] Conversao iniciada para task {}", nodeodmUuid);
        } catch (Exception e) {
            logger.error("[Potree] Erro ao disparar conversao: {}", e.getMessage());
        }
    }
}
