package com.funcoesodm.javaservice.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.funcoesodm.javaservice.client.NodeODMClient;
import com.funcoesodm.javaservice.dto.CreateTaskRequestDto;
import com.funcoesodm.javaservice.dto.ProcessingTaskDto;
import com.funcoesodm.javaservice.model.ProcessingTask;
import com.funcoesodm.javaservice.model.Project;
import com.funcoesodm.javaservice.model.ProjectImage;
import com.funcoesodm.javaservice.repository.ProcessingTaskRepository;
import com.funcoesodm.javaservice.repository.ProjectImageRepository;
import com.funcoesodm.javaservice.repository.ProjectRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.stream.Collectors;

@Service
public class ProcessingTaskService {

    private static final Logger logger = LoggerFactory.getLogger(ProcessingTaskService.class);

    private final ProcessingTaskRepository taskRepository;
    private final ProjectRepository projectRepository;
    private final ProjectImageRepository imageRepository;
    private final WebSocketService webSocketService;
    private final ObjectMapper objectMapper;
    private final NodeODMClient nodeodmClient;
    
    @Value("${app.upload.dir:/app/uploads}")
    private String uploadDir;

    public ProcessingTaskService(
            ProcessingTaskRepository taskRepository,
            ProjectRepository projectRepository,
            ProjectImageRepository imageRepository,
            WebSocketService webSocketService,
            ObjectMapper objectMapper,
            NodeODMClient nodeodmClient) {
        this.taskRepository = taskRepository;
        this.projectRepository = projectRepository;
        this.imageRepository = imageRepository;
        this.webSocketService = webSocketService;
        this.objectMapper = objectMapper;
        this.nodeodmClient = nodeodmClient;
    }

    /**
     * Get all tasks for a project
     */
    @Transactional(readOnly = true)
    public List<ProcessingTaskDto> getProjectTasks(Long projectId) {
        return taskRepository.findByProjectId(projectId)
                .stream()
                .map(ProcessingTaskDto::fromEntity)
                .collect(Collectors.toList());
    }

    /**
     * Get a specific task
     */
    @Transactional(readOnly = true)
    public Optional<ProcessingTaskDto> getTask(Long taskId) {
        return taskRepository.findById(taskId)
                .map(ProcessingTaskDto::fromEntity);
    }

    /**
     * Resolve a task asset file for download
     */
    @Transactional(readOnly = true)
    public Optional<NodeODMClient.ResolvedAsset> resolveAssetForDownload(Long projectId, Long taskId, String assetName) {
        return taskRepository.findByIdWithProject(taskId)
                .filter(task -> task.getProject() != null && task.getProject().getId().equals(projectId))
                .map(ProcessingTask::getNodeodmTaskId)
                .flatMap(nodeodmTaskId -> nodeodmClient.resolveAssetForDownload(nodeodmTaskId, assetName));
    }

    /**
     * Create a new processing task for a project
     */
    @Transactional
    public ProcessingTaskDto createTask(Long projectId, CreateTaskRequestDto request) {
        logger.info("Creating processing task for project {}", projectId);

        Project project = projectRepository.findById(projectId)
                .orElseThrow(() -> new RuntimeException("Project not found: " + projectId));

        // Check if project has images
        List<ProjectImage> images = imageRepository.findByProjectId(projectId);
        if (images.isEmpty()) {
            throw new RuntimeException("Project has no images to process");
        }

        // Create task
        ProcessingTask task = new ProcessingTask();
        task.setProject(project);
        task.setTenantId(project.getTenantId()); // Fase 8.5: tenant herdado do projeto-pai
        task.setName(request.getName() != null ? request.getName() : "Processamento ODM");
        task.setStatus(ProcessingTask.Status.QUEUED);
        task.setProgress(0);
        task.setStatusMessage("Aguardando na fila...");

        // Convert options to JSON
        if (request.getOptions() != null) {
            try {
                String optionsJson = objectMapper.writeValueAsString(request.getOptions());
                task.setOptions(optionsJson);
            } catch (Exception e) {
                logger.warn("Failed to serialize options", e);
            }
        }

        ProcessingTask savedTask = taskRepository.save(task);
        logger.info("Created task {} for project {}", savedTask.getId(), projectId);

        // Update project status
        project.setStatus("PROCESSING");
        projectRepository.save(project);

        // Start processing asynchronously - use NodeODM directly
        if (!nodeodmClient.isHealthy()) {
            logger.error("NodeODM service is not available for task {}", savedTask.getId());
            // Update task status to failed
            savedTask.setStatus(ProcessingTask.Status.FAILED);
            savedTask.setStatusMessage("Erro: NodeODM não está disponível. Verifique se os containers estão rodando.");
            taskRepository.save(savedTask);
            throw new RuntimeException("NodeODM service is not available. Please ensure NodeODM is running.");
        }
        
        logger.info("Starting NodeODM processing for task {}", savedTask.getId());
        startNodeODMProcessingAsync(savedTask.getId(), projectId, images, request.getOptions());

        return ProcessingTaskDto.fromEntity(savedTask);
    }

    /**
    * Start NodeODM processing asynchronously
     */
    private void startNodeODMProcessingAsync(Long taskId, Long projectId, List<ProjectImage> images, 
                                    Map<String, Object> options) {
        CompletableFuture.runAsync(() -> {
            try {
                // Update task to RUNNING
                updateTaskStatus(taskId, ProcessingTask.Status.RUNNING, 0, "Conectando ao NodeODM...");
                webSocketService.sendTaskStarted(projectId, taskId, "Processamento iniciado");

                // Step 1: Prepare images
                updateTaskStatus(taskId, ProcessingTask.Status.RUNNING, 5, "Preparando " + images.size() + " imagens...");
                webSocketService.sendTaskProgress(projectId, taskId, 5, "Preparando " + images.size() + " imagens...");
                
                List<byte[]> imageDataList = new ArrayList<>();
                List<String> imageNames = new ArrayList<>();
                
                for (ProjectImage img : images) {
                    try {
                        Path imagePath = Paths.get(img.getStoragePath());
                        byte[] imageData = Files.readAllBytes(imagePath);
                        imageDataList.add(imageData);
                        imageNames.add(img.getFilename());
                        logger.debug("Prepared image: {}", img.getFilename());
                    } catch (IOException e) {
                        logger.warn("Could not read image file: {}", img.getStoragePath());
                    }
                }
                
                if (imageDataList.isEmpty()) {
                    throw new RuntimeException("Nenhuma imagem válida encontrada para processamento");
                }

                // Step 2: Create task with images directly on NodeODM
                updateTaskStatus(taskId, ProcessingTask.Status.RUNNING, 10, 
                                "Enviando " + imageDataList.size() + " imagens para NodeODM...");
                webSocketService.sendTaskProgress(projectId, taskId, 10, 
                                                 "Enviando " + imageDataList.size() + " imagens para NodeODM...");
                
                // Use project ID 0 for NodeODM direct - it doesn't use project concept
                JsonNode nodeodmTask = nodeodmClient.createTask(
                    imageDataList,
                    imageNames,
                    "FuncoesODM_Task_" + taskId,
                    options,
                    null
                );
                
                // NodeODM returns "uuid" instead of "id"
                String nodeodmTaskId = nodeodmTask.has("uuid") ? 
                    nodeodmTask.get("uuid").asText() : 
                    nodeodmTask.get("task_id").asText();
                    
                logger.info("Created NodeODM task: {}", nodeodmTaskId);
                
                // Save NodeODM task ID (project ID is 0 for NodeODM)
                saveNodeODMIds(taskId, nodeodmTaskId);

                // Step 3: Poll for status updates
                updateTaskStatus(taskId, ProcessingTask.Status.RUNNING, 15, "Processamento iniciado no NodeODM...");
                webSocketService.sendTaskProgress(projectId, taskId, 15, "Processamento iniciado no NodeODM...");
                
                pollTaskStatus(taskId, projectId, nodeodmTaskId);

            } catch (Exception e) {
                logger.error("NodeODM task {} failed", taskId, e);
                failTask(taskId, projectId, "Erro no NodeODM: " + e.getMessage());
                webSocketService.sendTaskFailed(projectId, taskId, e.getMessage());
            }
        });
    }

    /**
     * Poll NodeODM for task status updates
     */
    private void pollTaskStatus(Long taskId, Long projectId, String nodeodmTaskId) 
            throws InterruptedException {
        
        int maxAttempts = 360; // 1 hour at 10 second intervals
        int pollInterval = 10000; // 10 seconds
        
        for (int attempt = 0; attempt < maxAttempts; attempt++) {
            try {
                JsonNode status = nodeodmClient.getTaskStatus(nodeodmTaskId);
                String taskStatus = status.get("status").asText();
                int progress = status.has("progress") ? status.get("progress").asInt() : 0;
                
                // Map progress to 20-100% range (first 20% is upload)
                int mappedProgress = 20 + (int)(progress * 0.8);
                
                String statusMessage = getStatusMessage(taskStatus, progress);
                
                updateTaskStatus(taskId,
                               mapNodeODMStatus(taskStatus),
                               mappedProgress,
                               statusMessage);
                webSocketService.sendTaskProgress(projectId, taskId, mappedProgress, statusMessage);
                
                if ("COMPLETED".equals(taskStatus)) {
                    // Validate that assets are actually accessible
                    JsonNode validation = nodeodmClient.validateAssets(nodeodmTaskId);
                    boolean allValid = validation.has("all_valid") && validation.get("all_valid").asBoolean();
                    
                    if (allValid) {
                        // All assets valid - complete success
                        JsonNode assets = nodeodmClient.getAvailableAssets(nodeodmTaskId);
                        Map<String, String> outputs = buildOutputsMap(nodeodmTaskId, assets);
                        
                        completeTask(taskId, projectId, outputs);
                        webSocketService.sendTaskCompleted(projectId, taskId, "Processamento concluído!", outputs);
                        logger.info("NodeODM task {} completed successfully with all assets valid", taskId);
                    } else {
                        // Some assets failed validation - complete with warnings
                        JsonNode validAssets = validation.get("valid_assets");
                        JsonNode invalidAssets = validation.get("invalid_assets");
                        
                        Map<String, String> outputs = buildOutputsMapFromValidation(nodeodmTaskId, validAssets);
                        String warning = buildWarningMessage(invalidAssets);
                        
                        completeTaskWithWarnings(taskId, projectId, outputs, warning);
                        webSocketService.sendTaskCompleted(projectId, taskId, 
                            "Processamento concluído com avisos: alguns arquivos não estão disponíveis", outputs);
                        logger.warn("NodeODM task {} completed but some assets invalid: {}", taskId, warning);
                    }
                    return;
                    
                } else if ("FAILED".equals(taskStatus)) {
                    // Validate if any main assets are actually accessible despite failure
                    JsonNode validation = nodeodmClient.validateAssets(nodeodmTaskId);
                    int validCount = validation.has("valid_count") ? validation.get("valid_count").asInt() : 0;
                    
                    if (validCount > 0) {
                        // Some assets are accessible - complete with warnings
                        JsonNode validAssets = validation.get("valid_assets");
                        String odmError = status.has("last_error") ? status.get("last_error").asText() : "Unknown ODM error";
                        
                        Map<String, String> outputs = buildOutputsMapFromValidation(nodeodmTaskId, validAssets);
                        String warning = "Processamento ODM reportou erro mas " + validCount + " arquivo(s) foram gerados. Erro ODM: " + odmError;
                        
                        completeTaskWithWarnings(taskId, projectId, outputs, warning);
                        webSocketService.sendTaskCompleted(projectId, taskId, 
                            "Processamento concluído parcialmente - " + validCount + " arquivo(s) disponíveis", outputs);
                        logger.warn("Task {} marked as FAILED in ODM but has {} valid assets. Error: {}", 
                                   taskId, validCount, odmError);
                        return;
                    }
                    
                    // No valid assets - real failure
                    String error = status.has("last_error") ? status.get("last_error").asText() : "Unknown error";
                    failTask(taskId, projectId, error);
                    webSocketService.sendTaskFailed(projectId, taskId, error);
                    return;
                    
                } else if ("CANCELED".equals(taskStatus)) {
                    failTask(taskId, projectId, "Tarefa cancelada no NodeODM");
                    webSocketService.sendTaskFailed(projectId, taskId, "Tarefa cancelada");
                    return;
                }
                
                Thread.sleep(pollInterval);
                
            } catch (Exception e) {
                logger.warn("Error polling task status, retrying...: {}", e.getMessage());
                Thread.sleep(pollInterval);
            }
        }
        
        // Timeout
        failTask(taskId, projectId, "Timeout: processamento excedeu o tempo limite");
        webSocketService.sendTaskFailed(projectId, taskId, "Timeout no processamento");
    }

    /**
     * Map NodeODM status to internal status
     */
    private ProcessingTask.Status mapNodeODMStatus(String nodeodmStatus) {
        return switch (nodeodmStatus) {
            case "QUEUED" -> ProcessingTask.Status.QUEUED;
            case "RUNNING" -> ProcessingTask.Status.RUNNING;
            case "COMPLETED" -> ProcessingTask.Status.COMPLETED;
            case "FAILED" -> ProcessingTask.Status.FAILED;
            case "CANCELED" -> ProcessingTask.Status.CANCELED;
            default -> ProcessingTask.Status.RUNNING;
        };
    }

    /**
     * Get human-readable status message
     */
    private String getStatusMessage(String status, int progress) {
        return switch (status) {
            case "QUEUED" -> "Aguardando na fila do NodeODM...";
            case "RUNNING" -> {
                if (progress < 10) yield "Analisando imagens...";
                else if (progress < 30) yield "Detectando pontos de interesse...";
                else if (progress < 50) yield "Alinhando fotos...";
                else if (progress < 60) yield "Construindo nuvem de pontos...";
                else if (progress < 70) yield "Gerando malha 3D...";
                else if (progress < 80) yield "Texturizando modelo...";
                else if (progress < 90) yield "Gerando ortofoto...";
                else yield "Finalizando processamento...";
            }
            case "COMPLETED" -> "Processamento concluído";
            case "FAILED" -> "Processamento falhou";
            case "CANCELED" -> "Processamento cancelado";
            default -> "Processando...";
        };
    }

    /**
     * Build outputs map from available assets
     * URL pattern: /api/v1/projects/{projectId}/tasks/{taskId}/download/{asset}
     */
    private Map<String, String> buildOutputsMap(String nodeodmTaskId, JsonNode assets) {
        Map<String, String> outputs = new HashMap<>();
        // Legacy: store only asset names as keys; URL is built dynamically by the controller
        // Store friendly key -> assetFilename for UI display
        Map<String, String> assetKeyMap = Map.of(
            "orthophoto.tif", "orthophoto",
            "dsm.tif", "dsm",
            "dtm.tif", "dtm",
            "georeferenced_model.laz", "pointCloud",
            "georeferenced_model.ply", "model3d"
        );
        
        if (assets.has("available_assets") && assets.get("available_assets").isArray()) {
            for (JsonNode asset : assets.get("available_assets")) {
                String assetName = asset.asText();
                // Map to friendly key if known, else use filename as key
                String outputKey = assetKeyMap.getOrDefault(assetName, assetName);
                outputs.put(outputKey, assetName); // store just filename; URL built at request time
            }
        }
        
        return outputs;
    }

    /**
     * Build outputs map from validated assets (uses validation response format)
     */
    private Map<String, String> buildOutputsMapFromValidation(String nodeodmTaskId, JsonNode validAssets) {
        Map<String, String> outputs = new HashMap<>();
        Map<String, String> assetKeyMap = Map.of(
            "orthophoto.tif", "orthophoto",
            "dsm.tif", "dsm",
            "dtm.tif", "dtm",
            "georeferenced_model.laz", "pointCloud",
            "georeferenced_model.ply", "model3d"
        );
        
        if (validAssets != null && validAssets.isArray()) {
            for (JsonNode asset : validAssets) {
                String assetName = asset.has("name") ? asset.get("name").asText() : asset.asText();
                long size = asset.has("size") ? asset.get("size").asLong() : 0;
                String outputKey = assetKeyMap.getOrDefault(assetName, assetName);
                outputs.put(outputKey, assetName);
                outputs.put(outputKey + "_size", String.valueOf(size));
            }
        }
        
        return outputs;
    }

    /**
     * Build warning message from invalid assets
     */
    private String buildWarningMessage(JsonNode invalidAssets) {
        if (invalidAssets == null || !invalidAssets.isArray() || invalidAssets.isEmpty()) {
            return "Alguns assets não puderam ser validados";
        }
        
        StringBuilder sb = new StringBuilder("Assets não disponíveis: ");
        for (int i = 0; i < invalidAssets.size(); i++) {
            JsonNode asset = invalidAssets.get(i);
            String name = asset.has("name") ? asset.get("name").asText() : "unknown";
            String error = asset.has("error") ? asset.get("error").asText() : "unknown error";
            if (i > 0) sb.append(", ");
            sb.append(name).append(" (").append(error).append(")");
        }
        return sb.toString();
    }

    /**
     * Check if a specific asset is available
     */
    private boolean hasAsset(JsonNode assets, String assetName) {
        if (assets.has("available_assets") && assets.get("available_assets").isArray()) {
            for (JsonNode asset : assets.get("available_assets")) {
                if (assetName.equals(asset.asText())) {
                    return true;
                }
            }
        }
        return false;
    }

    /**
     * Save NodeODM IDs to task
     */
    @Transactional
    public void saveNodeODMIds(Long taskId, String nodeodmTaskId) {
        taskRepository.findById(taskId).ifPresent(task -> {
            task.setNodeodmTaskId(nodeodmTaskId);
            taskRepository.save(task);
        });
    }

    /**
     * Update task status and progress
     */
    @Transactional
    public void updateTaskStatus(Long taskId, ProcessingTask.Status status, Integer progress, String message) {
        taskRepository.findById(taskId).ifPresent(task -> {
            task.setStatus(status);
            task.setProgress(progress);
            task.setStatusMessage(message);
            if (status == ProcessingTask.Status.RUNNING && task.getStartedAt() == null) {
                task.setStartedAt(LocalDateTime.now());
            }
            taskRepository.save(task);
        });
    }

    /**
     * Complete a task successfully
     */
    @Transactional
    public void completeTask(Long taskId, Long projectId, Map<String, String> outputs) {
        taskRepository.findById(taskId).ifPresent(task -> {
            task.setStatus(ProcessingTask.Status.COMPLETED);
            task.setProgress(100);
            task.setStatusMessage("Processamento concluído");
            task.setCompletedAt(LocalDateTime.now());
            try {
                String outputsJson = objectMapper.writeValueAsString(outputs);
                task.setOutputs(outputsJson);
            } catch (Exception e) {
                logger.warn("Failed to serialize outputs", e);
            }
            taskRepository.save(task);
        });

        // Update project status
        projectRepository.findById(projectId).ifPresent(project -> {
            project.setStatus("COMPLETED");
            projectRepository.save(project);
        });
    }

    /**
     * Complete a task with warnings (partial success)
     */
    @Transactional
    public void completeTaskWithWarnings(Long taskId, Long projectId, Map<String, String> outputs, String warning) {
        taskRepository.findById(taskId).ifPresent(task -> {
            task.setStatus(ProcessingTask.Status.COMPLETED_WITH_WARNINGS);
            task.setProgress(100);
            task.setStatusMessage("Processamento concluído com avisos");
            task.setWarningMessage(warning);
            task.setCompletedAt(LocalDateTime.now());
            try {
                String outputsJson = objectMapper.writeValueAsString(outputs);
                task.setOutputs(outputsJson);
            } catch (Exception e) {
                logger.warn("Failed to serialize outputs", e);
            }
            taskRepository.save(task);
            logger.info("Task {} completed with warnings: {}", taskId, warning);
        });

        // Update project status - still mark as completed since we have outputs
        projectRepository.findById(projectId).ifPresent(project -> {
            project.setStatus("COMPLETED_WITH_WARNINGS");
            projectRepository.save(project);
        });
    }

    /**
     * Fail a task
     */
    @Transactional
    public void failTask(Long taskId, Long projectId, String errorMessage) {
        taskRepository.findById(taskId).ifPresent(task -> {
            task.setStatus(ProcessingTask.Status.FAILED);
            task.setStatusMessage("Falha no processamento");
            task.setErrorMessage(errorMessage);
            task.setCompletedAt(LocalDateTime.now());
            taskRepository.save(task);
        });

        // Update project status
        projectRepository.findById(projectId).ifPresent(project -> {
            project.setStatus("ERROR");
            projectRepository.save(project);
        });
    }

    /**
     * Cancel a running task
     */
    @Transactional
    public void cancelTask(Long taskId) {
        taskRepository.findById(taskId).ifPresent(task -> {
            if (task.getStatus() == ProcessingTask.Status.RUNNING ||
                    task.getStatus() == ProcessingTask.Status.QUEUED) {
                
                // If task has NodeODM ID, cancel in NodeODM too
                if (task.getNodeodmTaskId() != null) {
                    try {
                        nodeodmClient.cancelTask(task.getNodeodmTaskId());
                    } catch (Exception e) {
                        logger.warn("Failed to cancel task in NodeODM: {}", e.getMessage());
                    }
                }
                
                task.setStatus(ProcessingTask.Status.CANCELED);
                task.setCompletedAt(LocalDateTime.now());
                taskRepository.save(task);
                
                // Notify via WebSocket
                webSocketService.sendTaskFailed(
                        task.getProject().getId(),
                        taskId,
                        "Tarefa cancelada pelo usuário"
                );
            }
        });
    }
}
