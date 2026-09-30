package com.funcoesodm.javaservice.service;

import com.funcoesodm.javaservice.dto.*;
import com.funcoesodm.javaservice.exception.ResourceNotFoundException;
import com.funcoesodm.javaservice.model.*;
import com.funcoesodm.javaservice.repository.*;
import com.funcoesodm.javaservice.client.NodeODMClient;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.InputStreamResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.fasterxml.jackson.core.type.TypeReference;
import java.io.IOException;
import java.io.InputStream;
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
public class ChunkService {

    private static final Logger logger = LoggerFactory.getLogger(ChunkService.class);
    private static final ObjectMapper objectMapper = new ObjectMapper();

    private final ChunkRepository chunkRepository;
    private final ChunkImageRepository chunkImageRepository;
    private final ProjectRepository projectRepository;
    private final ProjectImageRepository projectImageRepository;
    private final ProcessingTaskRepository processingTaskRepository;
    private final NodeODMClient nodeodmClient;
    private final WebSocketService webSocketService;

    @Value("${app.upload.dir:/app/uploads}")
    private String uploadDir;

    @Autowired
    public ChunkService(ChunkRepository chunkRepository,
                       ChunkImageRepository chunkImageRepository,
                       ProjectRepository projectRepository,
                       ProjectImageRepository projectImageRepository,
                       ProcessingTaskRepository processingTaskRepository,
                       NodeODMClient nodeodmClient,
                       WebSocketService webSocketService) {
        this.chunkRepository = chunkRepository;
        this.chunkImageRepository = chunkImageRepository;
        this.projectRepository = projectRepository;
        this.projectImageRepository = projectImageRepository;
        this.processingTaskRepository = processingTaskRepository;
        this.nodeodmClient = nodeodmClient;
        this.webSocketService = webSocketService;
    }

    /**
     * Create a new chunk for a project
     */
    @Transactional
    public ChunkDto createChunk(Long projectId, ChunkCreateRequestDto request) {
        logger.info("Creating chunk '{}' for project {}", request.getName(), projectId);

        Project project = projectRepository.findById(projectId)
                .orElseThrow(() -> new ResourceNotFoundException("Projeto", "id", projectId));

        Chunk chunk = new Chunk();
        chunk.setProject(project);
        chunk.setTenantId(project.getTenantId()); // Fase 8.5: tenant herdado do projeto-pai
        chunk.setName(request.getName());
        chunk.setDescription(request.getDescription());
        chunk.setStatus(Chunk.ChunkStatus.EMPTY);
        chunk.setImageCount(0);
        chunk.setProgress(0);

        Chunk savedChunk = chunkRepository.save(chunk);
        logger.info("Created chunk {} for project {}", savedChunk.getId(), projectId);

        return ChunkDto.fromEntity(savedChunk);
    }

    /**
     * Get all chunks for a project
     */
    @Transactional(readOnly = true)
    public List<ChunkDto> getChunksByProject(Long projectId) {
        logger.debug("Fetching chunks for project {}", projectId);
        return chunkRepository.findByProjectId(projectId)
                .stream()
                .map(ChunkDto::fromEntity)
                .collect(Collectors.toList());
    }

    /**
     * Get a specific chunk
     */
    @Transactional(readOnly = true)
    public ChunkDto getChunk(Long projectId, Long chunkId) {
        Chunk chunk = chunkRepository.findByProjectIdAndChunkId(projectId, chunkId)
                .orElseThrow(() -> new ResourceNotFoundException("Chunk", "id", chunkId));
        return ChunkDto.fromEntity(chunk);
    }

    /**
     * Update a chunk
     */
    @Transactional
    public ChunkDto updateChunk(Long projectId, Long chunkId, ChunkUpdateRequestDto request) {
        logger.info("Updating chunk {} in project {}", chunkId, projectId);

        Chunk chunk = chunkRepository.findByProjectIdAndChunkId(projectId, chunkId)
                .orElseThrow(() -> new ResourceNotFoundException("Chunk", "id", chunkId));

        if (request.getName() != null) {
            chunk.setName(request.getName());
        }
        if (request.getDescription() != null) {
            chunk.setDescription(request.getDescription());
        }

        Chunk savedChunk = chunkRepository.save(chunk);
        return ChunkDto.fromEntity(savedChunk);
    }

    /**
     * Delete a chunk
     */
    @Transactional
    public void deleteChunk(Long projectId, Long chunkId) {
        logger.info("Deleting chunk {} from project {}", chunkId, projectId);

        Chunk chunk = chunkRepository.findByProjectIdAndChunkId(projectId, chunkId)
                .orElseThrow(() -> new ResourceNotFoundException("Chunk", "id", chunkId));

        // Delete all chunk-image associations
        chunkImageRepository.deleteByChunkId(chunkId);

        // Delete the chunk
        chunkRepository.delete(chunk);
        logger.info("Deleted chunk {} from project {}", chunkId, projectId);
    }

    /**
     * Add images to a chunk
     */
    @Transactional
    public ChunkDto addImagesToChunk(Long projectId, Long chunkId, ChunkAddImagesRequestDto request) {
        logger.info("Adding {} images to chunk {} in project {}", request.getImageIds().size(), chunkId, projectId);

        Chunk chunk = chunkRepository.findByProjectIdAndChunkId(projectId, chunkId)
                .orElseThrow(() -> new ResourceNotFoundException("Chunk", "id", chunkId));

        // Fase 8.5: só imagens do MESMO projeto podem ser anexadas — evita que um
        // imageId de outro projeto/tenant seja "emprestado" para este chunk.
        List<ProjectImage> images = projectImageRepository.findAllById(request.getImageIds())
                .stream()
                .filter(img -> img.getProject() != null
                        && img.getProject().getId().equals(chunk.getProject().getId()))
                .collect(Collectors.toList());

        if (images.size() != request.getImageIds().size()) {
            logger.warn("Algumas imagens não pertencem ao projeto {} ou não existem. Pedidas: {}, aceitas: {}",
                    projectId, request.getImageIds().size(), images.size());
        }

        int addedCount = 0;
        for (ProjectImage image : images) {
            // Check if image already exists in chunk
            ChunkImage existing = chunkImageRepository.findByChunkIdAndImageId(chunkId, image.getId());
            if (existing == null) {
                ChunkImage chunkImage = new ChunkImage();
                chunkImage.setChunk(chunk);
                chunkImage.setTenantId(chunk.getTenantId()); // Fase 8.5
                chunkImage.setImage(image);
                chunkImage.setSortOrder(chunk.getImageCount() + addedCount);
                chunkImageRepository.save(chunkImage);
                addedCount++;
            }
        }

        // Update image count
        chunk.setImageCount(chunk.getImageCount() + addedCount);
        
        // Update status if was empty
        if (chunk.getStatus() == Chunk.ChunkStatus.EMPTY && chunk.getImageCount() > 0) {
            chunk.setStatus(Chunk.ChunkStatus.READY);
        }

        Chunk savedChunk = chunkRepository.save(chunk);
        logger.info("Added {} images to chunk {}. Total images: {}", addedCount, chunkId, savedChunk.getImageCount());

        return ChunkDto.fromEntity(savedChunk);
    }

    /**
     * Remove images from a chunk
     */
    @Transactional
    public ChunkDto removeImagesFromChunk(Long projectId, Long chunkId, List<Long> imageIds) {
        logger.info("Removing {} images from chunk {} in project {}", imageIds.size(), chunkId, projectId);

        Chunk chunk = chunkRepository.findByProjectIdAndChunkId(projectId, chunkId)
                .orElseThrow(() -> new ResourceNotFoundException("Chunk", "id", chunkId));

        List<ChunkImage> chunkImages = chunkImageRepository.findByChunkIdAndImageIds(chunkId, imageIds);
        
        for (ChunkImage chunkImage : chunkImages) {
            chunkImageRepository.delete(chunkImage);
        }

        // Update image count
        long newCount = chunkImageRepository.countByChunkId(chunkId);
        chunk.setImageCount((int) newCount);
        
        // Update status if now empty
        if (newCount == 0) {
            chunk.setStatus(Chunk.ChunkStatus.EMPTY);
        }

        Chunk savedChunk = chunkRepository.save(chunk);
        logger.info("Removed {} images from chunk {}. Remaining images: {}", 
                chunkImages.size(), chunkId, savedChunk.getImageCount());

        return ChunkDto.fromEntity(savedChunk);
    }

    /**
     * Get images in a chunk
     */
    @Transactional(readOnly = true)
    public List<ProjectImageDto> getChunkImages(Long projectId, Long chunkId) {
        Chunk chunk = chunkRepository.findByProjectIdAndChunkId(projectId, chunkId)
                .orElseThrow(() -> new ResourceNotFoundException("Chunk", "id", chunkId));

        return chunkImageRepository.findByChunkId(chunkId)
                .stream()
                .map(ci -> ProjectImageDto.fromEntity(ci.getImage()))
                .collect(Collectors.toList());
    }

    /**
     * Update processing options for a chunk
     */
    @Transactional
    public ChunkDto updateProcessingOptions(Long projectId, Long chunkId, Map<String, Object> options) {
        logger.info("Updating processing options for chunk {} in project {}", chunkId, projectId);

        Chunk chunk = chunkRepository.findByProjectIdAndChunkId(projectId, chunkId)
                .orElseThrow(() -> new ResourceNotFoundException("Chunk", "id", chunkId));

        try {
            String optionsJson = objectMapper.writeValueAsString(options);
            chunk.setProcessingOptions(optionsJson);
        } catch (JsonProcessingException e) {
            logger.error("Failed to serialize processing options", e);
            throw new RuntimeException("Failed to serialize processing options", e);
        }

        Chunk savedChunk = chunkRepository.save(chunk);
        return ChunkDto.fromEntity(savedChunk);
    }

    /**
     * Update chunk status (internal use)
     */
    @Transactional
    public void updateChunkStatus(Long chunkId, Chunk.ChunkStatus status, Integer progress, String errorMessage) {
        Chunk chunk = chunkRepository.findById(chunkId)
                .orElseThrow(() -> new ResourceNotFoundException("Chunk", "id", chunkId));

        chunk.setStatus(status);
        if (progress != null) {
            chunk.setProgress(progress);
        }
        if (errorMessage != null) {
            chunk.setErrorMessage(errorMessage);
        }

        chunkRepository.save(chunk);
    }

    /**
     * Update chunk status (for REST API)
     */
    @Transactional
    public ChunkDto updateChunkStatus(Long projectId, Long chunkId, String statusStr, int progress, String message) {
        Chunk chunk = chunkRepository.findByProjectIdAndChunkId(projectId, chunkId)
                .orElseThrow(() -> new ResourceNotFoundException("Chunk", "id", chunkId));

        try {
            Chunk.ChunkStatus status = Chunk.ChunkStatus.valueOf(statusStr.toUpperCase());
            chunk.setStatus(status);
            chunk.setProgress(progress);
            if (status == Chunk.ChunkStatus.FAILED && message != null) {
                chunk.setErrorMessage(message);
            }
        } catch (IllegalArgumentException e) {
            throw new RuntimeException("Status inválido: " + statusStr);
        }

        Chunk saved = chunkRepository.save(chunk);
        return ChunkDto.fromEntity(saved);
    }

    /**
     * Find chunk by NodeODM task ID
     */
    @Transactional(readOnly = true)
    public Chunk findByNodeodmTaskId(String nodeodmTaskId) {
        return chunkRepository.findByNodeodmTaskId(nodeodmTaskId).orElse(null);
    }

    // ==================== PROCESSING METHODS ====================

    /**
     * Start processing a chunk with NodeODM
     */
    @Transactional
    public ChunkDto processChunk(Long projectId, Long chunkId, Map<String, Object> options, byte[] gcpContent) {
        logger.info("Starting processing for chunk {} in project {} with options: {}", chunkId, projectId, options);

        Chunk chunk = chunkRepository.findByProjectIdAndChunkId(projectId, chunkId)
                .orElseThrow(() -> new ResourceNotFoundException("Chunk", "id", chunkId));

        // Validate chunk has images
        if (chunk.getImageCount() < 3) {
            throw new RuntimeException("Chunk precisa de pelo menos 3 imagens para processar");
        }

        // Check if NodeODM is available
        if (!nodeodmClient.isHealthy()) {
            throw new RuntimeException("NodeODM não está disponível. Verifique se os containers estão rodando.");
        }

        // Update chunk status
        chunk.setStatus(Chunk.ChunkStatus.QUEUED);
        chunk.setProgress(0);
        chunk.setErrorMessage(null);

        // Store processing options
        if (options != null && !options.isEmpty()) {
            try {
                chunk.setProcessingOptions(objectMapper.writeValueAsString(options));
            } catch (JsonProcessingException e) {
                logger.warn("Failed to serialize options", e);
            }
        }

        Chunk savedChunk = chunkRepository.save(chunk);

        // Start async processing
        startChunkProcessingAsync(savedChunk.getId(), projectId, options, gcpContent);

        return ChunkDto.fromEntity(savedChunk);
    }

    /**
     * Start chunk processing asynchronously
     */
    private void startChunkProcessingAsync(Long chunkId, Long projectId, Map<String, Object> options, byte[] gcpContent) {
        CompletableFuture.runAsync(() -> {
            try {
                // Get chunk with images
                Chunk chunk = chunkRepository.findById(chunkId)
                        .orElseThrow(() -> new ResourceNotFoundException("Chunk", "id", chunkId));

                List<ChunkImage> chunkImages = chunkImageRepository.findByChunkId(chunkId);
                
                // Update to RUNNING
                updateChunkStatusInternal(chunkId, Chunk.ChunkStatus.RUNNING, 0, "Conectando ao NodeODM...");
                webSocketService.sendChunkProgress(projectId, chunkId, 0, "Conectando ao NodeODM...");

                // Step 1: Prepare images
                updateChunkStatusInternal(chunkId, Chunk.ChunkStatus.RUNNING, 5, 
                        "Preparando " + chunkImages.size() + " imagens...");
                webSocketService.sendChunkProgress(projectId, chunkId, 5, 
                        "Preparando " + chunkImages.size() + " imagens...");

                List<byte[]> imageDataList = new ArrayList<>();
                List<String> imageNames = new ArrayList<>();

                for (ChunkImage ci : chunkImages) {
                    ProjectImage img = ci.getImage();
                    try {
                        Path imagePath = Paths.get(img.getStoragePath());
                        byte[] imageData = Files.readAllBytes(imagePath);
                        imageDataList.add(imageData);
                        // Use original filename instead of UUID filename for NodeODM
                        // This preserves EXIF correlation needed for photogrammetry
                        String imageName = img.getOriginalFilename() != null ? 
                            img.getOriginalFilename() : img.getFilename();
                        imageNames.add(imageName);
                        logger.debug("Prepared image: {} (original: {})", img.getFilename(), imageName);
                    } catch (IOException e) {
                        logger.warn("Could not read image file: {}", img.getStoragePath());
                    }
                }

                if (imageDataList.isEmpty()) {
                    throw new RuntimeException("Nenhuma imagem válida encontrada para processamento");
                }

                // Step 2: Create task on NodeODM
                updateChunkStatusInternal(chunkId, Chunk.ChunkStatus.RUNNING, 10,
                        "Enviando " + imageDataList.size() + " imagens para NodeODM...");
                webSocketService.sendChunkProgress(projectId, chunkId, 10,
                        "Enviando " + imageDataList.size() + " imagens para NodeODM...");

                // Fix: Force SIFT instead of DSPSIFT due to known issues with DSPSIFT feature extraction
                Map<String, Object> adjustedOptions = new HashMap<>(options != null ? options : new HashMap<>());
                Object featureType = adjustedOptions.get("feature-type");
                if (featureType == null || "dspsift".equals(featureType)) {
                    logger.info("Changing feature-type from {} to 'sift' for better reliability", featureType);
                    adjustedOptions.put("feature-type", "sift");
                }

                JsonNode nodeodmTask = nodeodmClient.createTask(
                    imageDataList,
                    imageNames,
                    "Chunk_" + chunkId + "_" + System.currentTimeMillis(),
                    adjustedOptions,
                    gcpContent
                );

                String nodeodmTaskId = nodeodmTask.has("uuid") ?
                    nodeodmTask.get("uuid").asText() :
                    nodeodmTask.get("task_id").asText();

                logger.info("Created NodeODM task {} for chunk {}", nodeodmTaskId, chunkId);

                // Save NodeODM task ID
                saveNodeodmTaskId(chunkId, nodeodmTaskId);

                // Step 3: Poll for status
                updateChunkStatusInternal(chunkId, Chunk.ChunkStatus.RUNNING, 15, "Processamento iniciado no NodeODM...");
                webSocketService.sendChunkProgress(projectId, chunkId, 15, "Processamento iniciado no NodeODM...");

                pollChunkStatus(chunkId, projectId, nodeodmTaskId);

            } catch (Exception e) {
                logger.error("Chunk {} processing failed", chunkId, e);
                updateChunkStatusInternal(chunkId, Chunk.ChunkStatus.FAILED, 0, e.getMessage());
                webSocketService.sendChunkFailed(projectId, chunkId, e.getMessage());
            }
        });
    }

    /**
     * Poll NodeODM for chunk status updates
     */
    private void pollChunkStatus(Long chunkId, Long projectId, String nodeodmTaskId) throws InterruptedException {
        int maxAttempts = 720; // 2 hours at 10 second intervals
        int pollInterval = 10000;

        for (int attempt = 0; attempt < maxAttempts; attempt++) {
            try {
                JsonNode status = nodeodmClient.getTaskStatus(nodeodmTaskId);
                String taskStatus = status.get("status").asText();
                int progress = status.has("progress") ? status.get("progress").asInt() : 0;

                // Map progress to 20-100% range (first 20% is upload)
                int mappedProgress = 20 + (int)(progress * 0.8);
                String statusMessage = getStatusMessage(taskStatus, progress);

                updateChunkStatusInternal(chunkId, mapNodeODMStatus(taskStatus), mappedProgress, statusMessage);
                webSocketService.sendChunkProgress(projectId, chunkId, mappedProgress, statusMessage);

                if ("COMPLETED".equals(taskStatus)) {
                    // Get available assets
                    JsonNode assets = nodeodmClient.getAvailableAssets(nodeodmTaskId);
                    Map<String, String> outputs = buildOutputsMap(nodeodmTaskId, assets);

                    completeChunk(chunkId, projectId, outputs);
                    webSocketService.sendChunkCompleted(projectId, chunkId, "Processamento concluído!", outputs);
                    logger.info("Chunk {} completed successfully", chunkId);
                    return;

                } else if ("FAILED".equals(taskStatus)) {
                    String error = status.has("last_error") ? status.get("last_error").asText() : "Erro desconhecido";
                    updateChunkStatusInternal(chunkId, Chunk.ChunkStatus.FAILED, 0, error);
                    webSocketService.sendChunkFailed(projectId, chunkId, error);
                    return;
                }

                Thread.sleep(pollInterval);

            } catch (InterruptedException e) {
                throw e;
            } catch (Exception e) {
                logger.warn("Error polling status for chunk {}: {}", chunkId, e.getMessage());
                Thread.sleep(pollInterval);
            }
        }

        // Timeout
        updateChunkStatusInternal(chunkId, Chunk.ChunkStatus.FAILED, 0, "Timeout: processamento demorou muito");
        webSocketService.sendChunkFailed(projectId, chunkId, "Timeout: processamento demorou muito");
    }

    private void updateChunkStatusInternal(Long chunkId, Chunk.ChunkStatus status, int progress, String message) {
        try {
            Chunk chunk = chunkRepository.findById(chunkId).orElse(null);
            if (chunk != null) {
                chunk.setStatus(status);
                chunk.setProgress(progress);
                if (status == Chunk.ChunkStatus.FAILED) {
                    chunk.setErrorMessage(message);
                }
                chunkRepository.save(chunk);
            }
        } catch (Exception e) {
            logger.error("Failed to update chunk status", e);
        }
    }

    private void saveNodeodmTaskId(Long chunkId, String nodeodmTaskId) {
        try {
            Chunk chunk = chunkRepository.findById(chunkId).orElse(null);
            if (chunk != null) {
                chunk.setNodeodmTaskId(nodeodmTaskId);
                chunkRepository.save(chunk);
            }
        } catch (Exception e) {
            logger.error("Failed to save NodeODM task ID", e);
        }
    }

    private void completeChunk(Long chunkId, Long projectId, Map<String, String> outputs) {
        try {
            Chunk chunk = chunkRepository.findById(chunkId).orElse(null);
            if (chunk != null) {
                chunk.setStatus(Chunk.ChunkStatus.COMPLETED);
                chunk.setProgress(100);
                chunk.setOutputs(objectMapper.writeValueAsString(outputs));
                chunkRepository.save(chunk);
            }
        } catch (Exception e) {
            logger.error("Failed to complete chunk", e);
        }
    }

    private Chunk.ChunkStatus mapNodeODMStatus(String status) {
        return switch (status) {
            case "QUEUED" -> Chunk.ChunkStatus.QUEUED;
            case "RUNNING" -> Chunk.ChunkStatus.RUNNING;
            case "COMPLETED" -> Chunk.ChunkStatus.COMPLETED;
            case "FAILED" -> Chunk.ChunkStatus.FAILED;
            case "CANCELED" -> Chunk.ChunkStatus.CANCELED;
            default -> Chunk.ChunkStatus.RUNNING;
        };
    }

    private String getStatusMessage(String status, int progress) {
        return switch (status) {
            case "QUEUED" -> "Aguardando na fila...";
            case "RUNNING" -> progress < 30 ? "Alinhando imagens..." :
                             progress < 60 ? "Gerando nuvem de pontos..." :
                             progress < 80 ? "Criando modelo..." :
                             "Finalizando...";
            case "COMPLETED" -> "Processamento concluído!";
            case "FAILED" -> "Processamento falhou";
            default -> "Processando...";
        };
    }

    private Map<String, String> buildOutputsMap(String nodeodmTaskId, JsonNode assets) {
        Map<String, String> outputs = new HashMap<>();
        String baseUrl = "/api/v1/chunks/" + nodeodmTaskId + "/assets/";
        
        if (assets != null && assets.isArray()) {
            for (JsonNode asset : assets) {
                String assetName = asset.asText();
                if (assetName.contains("orthophoto")) {
                    outputs.put("orthophoto", baseUrl + "orthophoto.tif");
                } else if (assetName.contains("dsm")) {
                    outputs.put("dsm", baseUrl + "dsm.tif");
                } else if (assetName.contains("dtm")) {
                    outputs.put("dtm", baseUrl + "dtm.tif");
                } else if (assetName.contains("georeferenced_model") || assetName.contains("point_cloud")) {
                    outputs.put("pointCloud", baseUrl + "georeferenced_model.laz");
                } else if (assetName.contains("textured_model") || assetName.contains("3d")) {
                    outputs.put("model3d", baseUrl + "textured_model.zip");
                } else if (assetName.contains("report")) {
                    outputs.put("report", baseUrl + "report.pdf");
                }
            }
        }
        
        // Default outputs based on common NodeODM output structure
        if (outputs.isEmpty()) {
            outputs.put("orthophoto", baseUrl + "orthophoto.tif");
            outputs.put("dsm", baseUrl + "dsm.tif");
            outputs.put("pointCloud", baseUrl + "georeferenced_model.laz");
        }
        
        return outputs;
    }

    // ==================== RECOVERY & RETRY METHODS ====================

    /**
     * Retry a failed chunk: resets state and restarts processing with the same options.
     */
    @Transactional
    public ChunkDto retryChunk(Long projectId, Long chunkId) {
        Chunk chunk = chunkRepository.findByProjectIdAndChunkId(projectId, chunkId)
                .orElseThrow(() -> new ResourceNotFoundException("Chunk", "id", chunkId));

        if (chunk.getStatus() != Chunk.ChunkStatus.FAILED
                && chunk.getStatus() != Chunk.ChunkStatus.CANCELED) {
            throw new RuntimeException("Apenas chunks com falha ou cancelados podem ser reprocessados.");
        }

        if (chunk.getImageCount() < 3) {
            throw new RuntimeException("Chunk precisa de pelo menos 3 imagens para processar.");
        }

        Map<String, Object> options = new HashMap<>();
        if (chunk.getProcessingOptions() != null) {
            try {
                options = objectMapper.readValue(chunk.getProcessingOptions(),
                        new TypeReference<Map<String, Object>>() {});
            } catch (Exception e) {
                logger.warn("Nao foi possivel ler opcoes salvas do chunk {}. Usando padrao.", chunkId);
            }
        }

        chunk.setStatus(Chunk.ChunkStatus.QUEUED);
        chunk.setProgress(0);
        chunk.setErrorMessage(null);
        chunk.setNodeodmTaskId(null);

        Chunk saved = chunkRepository.save(chunk);
        startChunkProcessingAsync(saved.getId(), projectId, options, null);

        return ChunkDto.fromEntity(saved);
    }

    /**
     * Called by ChunkRecoveryService to resume polling for a chunk that was still RUNNING
     * in NodeODM when the server restarted.
     */
    public void resumePolling(Long chunkId, Long projectId, String nodeodmTaskId) {
        CompletableFuture.runAsync(() -> {
            try {
                logger.info("Retomando polling para chunk {} (nodeodmTaskId={})", chunkId, nodeodmTaskId);
                pollChunkStatus(chunkId, projectId, nodeodmTaskId);
            } catch (Exception e) {
                logger.error("Falha ao retomar polling do chunk {}", chunkId, e);
                updateChunkStatusInternal(chunkId, Chunk.ChunkStatus.FAILED, 0,
                        "Falha ao retomar monitoramento apos reinicio do servidor. Clique em 'Tentar Novamente'.");
                webSocketService.sendChunkFailed(projectId, chunkId,
                        "Falha ao retomar monitoramento apos reinicio.");
            }
        });
    }

    /**
     * Called by ChunkRecoveryService when NodeODM completed the task while the server was offline.
     */
    public void finalizeCompletedChunk(Long chunkId, Long projectId, String nodeodmTaskId) {
        CompletableFuture.runAsync(() -> {
            try {
                JsonNode assets = nodeodmClient.getAvailableAssets(nodeodmTaskId);
                Map<String, String> outputs = buildOutputsMap(nodeodmTaskId, assets);
                completeChunk(chunkId, projectId, outputs);
                webSocketService.sendChunkCompleted(projectId, chunkId, "Processamento concluido!", outputs);
                logger.info("Chunk {} finalizado com sucesso apos recuperacao.", chunkId);
            } catch (Exception e) {
                logger.error("Nao foi possivel finalizar chunk {} apos recuperacao", chunkId, e);
                updateChunkStatusInternal(chunkId, Chunk.ChunkStatus.FAILED, 0,
                        "Processamento concluido no ODM mas nao foi possivel recuperar os arquivos. Clique em 'Tentar Novamente'.");
                webSocketService.sendChunkFailed(projectId, chunkId,
                        "Nao foi possivel recuperar os arquivos apos reinicio.");
            }
        });
    }

    // ==================== MIGRATION METHODS ====================

    /**
     * Download asset from NodeODM via filesystem
     */
    public InputStreamResource downloadAssetFromNodeODM(String nodeodmTaskId, String filename) throws IOException {
        logger.info("Downloading asset from filesystem for task {} file {}", nodeodmTaskId, filename);
        
        // Read file directly from filesystem - much more efficient for large files
        InputStream inputStream = nodeodmClient.downloadAsset(nodeodmTaskId, filename);
        return new InputStreamResource(inputStream);
    }
    
    /**
     * Get the file size for an asset (for Content-Length header)
     */
    public long getAssetFileSize(String nodeodmTaskId, String filename) throws IOException {
        return nodeodmClient.getAssetFileSize(nodeodmTaskId, filename);
    }

    /**
     * Ensure project has at least one chunk. If not, create default chunk with all images.
     */
    @Transactional
    public void ensureProjectHasChunks(Long projectId) {
        List<Chunk> existingChunks = chunkRepository.findByProjectId(projectId);
        
        if (existingChunks.isEmpty()) {
            logger.info("Project {} has no chunks, creating default chunk", projectId);
            
            Project project = projectRepository.findById(projectId)
                    .orElseThrow(() -> new ResourceNotFoundException("Projeto", "id", projectId));

            // Create default chunk
            Chunk defaultChunk = new Chunk();
            defaultChunk.setProject(project);
            defaultChunk.setTenantId(project.getTenantId()); // Fase 8.5
            defaultChunk.setName("Chunk Principal");
            defaultChunk.setDescription("Chunk criado automaticamente");
            defaultChunk.setStatus(Chunk.ChunkStatus.EMPTY);
            defaultChunk.setImageCount(0);
            defaultChunk.setProgress(0);

            Chunk savedChunk = chunkRepository.save(defaultChunk);

            // Add all project images to this chunk
            List<ProjectImage> projectImages = projectImageRepository.findByProjectId(projectId);
            
            if (!projectImages.isEmpty()) {
                int count = 0;
                for (ProjectImage img : projectImages) {
                    ChunkImage chunkImage = new ChunkImage();
                    chunkImage.setChunk(savedChunk);
                    chunkImage.setTenantId(savedChunk.getTenantId()); // Fase 8.5
                    chunkImage.setImage(img);
                    chunkImage.setSortOrder(count++);
                    chunkImageRepository.save(chunkImage);
                }
                
                savedChunk.setImageCount(count);
                savedChunk.setStatus(count >= 3 ? Chunk.ChunkStatus.READY : Chunk.ChunkStatus.EMPTY);
                chunkRepository.save(savedChunk);
                
                logger.info("Added {} images to default chunk for project {}", count, projectId);
            }

            // Migrate existing ProcessingTask results to this chunk if available
            migrateProcessingTaskResults(savedChunk);
        }
    }

    /**
     * Migrate completed ProcessingTask results to a chunk
     */
    @Transactional
    protected void migrateProcessingTaskResults(Chunk chunk) {
        try {
            // Find the most recent completed task for this project
            List<ProcessingTask> completedTasks = processingTaskRepository
                    .findByProjectIdAndStatusOrderByCreatedAtDesc(
                            chunk.getProject().getId(),
                            ProcessingTask.Status.COMPLETED_WITH_WARNINGS
                    );

            if (completedTasks.isEmpty()) {
                completedTasks = processingTaskRepository
                        .findByProjectIdAndStatusOrderByCreatedAtDesc(
                                chunk.getProject().getId(),
                                ProcessingTask.Status.COMPLETED
                        );
            }

            if (!completedTasks.isEmpty()) {
                ProcessingTask task = completedTasks.get(0);
                chunk.setStatus(Chunk.ChunkStatus.COMPLETED);
                chunk.setProgress(100);
                chunk.setNodeodmTaskId(task.getNodeodmTaskId());
                chunk.setOutputs(task.getOutputs());
                chunkRepository.save(chunk);
                
                logger.info("Migrated ProcessingTask {} results to Chunk {}", task.getId(), chunk.getId());
            }
        } catch (Exception e) {
            logger.warn("Could not migrate ProcessingTask results to chunk {}: {}", chunk.getId(), e.getMessage());
        }
    }
}
