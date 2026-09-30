package com.funcoesodm.javaservice.controller;

import com.funcoesodm.javaservice.dto.CreateTaskRequestDto;
import com.funcoesodm.javaservice.dto.ProcessingTaskDto;
import com.funcoesodm.javaservice.service.ProcessingTaskService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@RestController
@RequestMapping("/api/v1/projects/{projectId}/tasks")
public class ProcessingTaskController {

    private static final Logger logger = LoggerFactory.getLogger(ProcessingTaskController.class);

    private final ProcessingTaskService taskService;

    public ProcessingTaskController(ProcessingTaskService taskService) {
        this.taskService = taskService;
    }

    /**
     * Get all tasks for a project
     * GET /api/v1/projects/{projectId}/tasks
     */
    @GetMapping
    public ResponseEntity<List<ProcessingTaskDto>> getProjectTasks(@PathVariable Long projectId) {
        List<ProcessingTaskDto> tasks = taskService.getProjectTasks(projectId);
        return ResponseEntity.ok(tasks);
    }

    /**
     * Get a specific task
     * GET /api/v1/projects/{projectId}/tasks/{taskId}
     */
    @GetMapping("/{taskId}")
    public ResponseEntity<ProcessingTaskDto> getTask(
            @PathVariable Long projectId,
            @PathVariable Long taskId) {
        return taskService.getTask(taskId)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    /**
     * Create a new processing task
     * POST /api/v1/projects/{projectId}/tasks
     */
    @PostMapping
    public ResponseEntity<?> createTask(
            @PathVariable Long projectId,
            @RequestBody(required = false) CreateTaskRequestDto request) {
        try {
            if (request == null) {
                request = new CreateTaskRequestDto();
                request.setName("Processamento ODM");
            }
            ProcessingTaskDto task = taskService.createTask(projectId, request);
            return ResponseEntity.ok(task);
        } catch (RuntimeException e) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", e.getMessage()
            ));
        }
    }

    /**
     * Cancel a task
     * POST /api/v1/projects/{projectId}/tasks/{taskId}/cancel
     */
    @PostMapping("/{taskId}/cancel")
    public ResponseEntity<Map<String, String>> cancelTask(
            @PathVariable Long projectId,
            @PathVariable Long taskId) {
        taskService.cancelTask(taskId);
        return ResponseEntity.ok(Map.of(
                "message", "Tarefa cancelada",
                "taskId", taskId.toString()
        ));
    }

    /**
     * Download a task asset
     * GET /api/v1/projects/{projectId}/tasks/{taskId}/download/{asset}
     */
    @GetMapping("/{taskId}/download/{asset}")
    public ResponseEntity<Resource> downloadTaskAsset(
            @PathVariable Long projectId,
            @PathVariable Long taskId,
            @PathVariable String asset) {
        
        logger.info("Download request for asset '{}' from project {} task {}", asset, projectId, taskId);
        
        Optional<com.funcoesodm.javaservice.client.NodeODMClient.ResolvedAsset> resolved =
                taskService.resolveAssetForDownload(projectId, taskId, asset);

        if (resolved.isEmpty()) {
            logger.warn("Asset '{}' not found for project {} task {}", asset, projectId, taskId);
            return ResponseEntity.notFound().build();
        }

        Path path = resolved.get().getPath();
        logger.info("Resolved asset path: {}", path);
        
        if (!Files.exists(path)) {
            logger.warn("Asset file does not exist: {}", path);
            return ResponseEntity.notFound().build();
        }
        
        Resource resource = new FileSystemResource(path);

        try {
            String contentType = Files.probeContentType(path);
            if (contentType == null || contentType.isBlank()) {
                contentType = MediaType.APPLICATION_OCTET_STREAM_VALUE;
            }

            return ResponseEntity.ok()
                    .contentType(MediaType.parseMediaType(contentType))
                    .contentLength(Files.size(path))
                    .header(HttpHeaders.CONTENT_DISPOSITION,
                            ContentDisposition.attachment()
                                    .filename(resolved.get().getFilename())
                                    .build()
                                    .toString())
                    .body(resource);
        } catch (IOException e) {
            return ResponseEntity.internalServerError().build();
        }
    }
}
