package com.funcoesodm.javaservice.controller;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.funcoesodm.javaservice.dto.*;
import com.funcoesodm.javaservice.service.ChunkService;
import jakarta.validation.Valid;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.io.InputStreamResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/projects/{projectId}/chunks")
public class ChunkController {

    private static final Logger logger = LoggerFactory.getLogger(ChunkController.class);

    private final ChunkService chunkService;
    private final ObjectMapper objectMapper;

    @Autowired
    public ChunkController(ChunkService chunkService, ObjectMapper objectMapper) {
        this.chunkService = chunkService;
        this.objectMapper = objectMapper;
    }

    /**
     * Get all chunks for a project
     */
    @GetMapping
    public ResponseEntity<List<ChunkDto>> getChunks(@PathVariable Long projectId) {
        List<ChunkDto> chunks = chunkService.getChunksByProject(projectId);
        return ResponseEntity.ok(chunks);
    }

    /**
     * Create a new chunk
     */
    @PostMapping
    public ResponseEntity<ChunkDto> createChunk(
            @PathVariable Long projectId,
            @Valid @RequestBody ChunkCreateRequestDto request) {
        
        logger.info("Creating chunk for project {}: {}", projectId, request.getName());
        
        ChunkDto chunk = chunkService.createChunk(projectId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(chunk);
    }

    /**
     * Get a specific chunk
     */
    @GetMapping("/{chunkId}")
    public ResponseEntity<ChunkDto> getChunk(
            @PathVariable Long projectId,
            @PathVariable Long chunkId) {
        
        ChunkDto chunk = chunkService.getChunk(projectId, chunkId);
        return ResponseEntity.ok(chunk);
    }

    /**
     * Update a chunk
     */
    @PutMapping("/{chunkId}")
    public ResponseEntity<ChunkDto> updateChunk(
            @PathVariable Long projectId,
            @PathVariable Long chunkId,
            @Valid @RequestBody ChunkUpdateRequestDto request) {
        
        logger.info("Updating chunk {} in project {}", chunkId, projectId);
        
        ChunkDto chunk = chunkService.updateChunk(projectId, chunkId, request);
        return ResponseEntity.ok(chunk);
    }

    /**
     * Delete a chunk
     */
    @DeleteMapping("/{chunkId}")
    public ResponseEntity<Void> deleteChunk(
            @PathVariable Long projectId,
            @PathVariable Long chunkId) {
        
        logger.info("Deleting chunk {} from project {}", chunkId, projectId);
        
        chunkService.deleteChunk(projectId, chunkId);
        return ResponseEntity.noContent().build();
    }

    /**
     * Add images to a chunk
     */
    @PostMapping("/{chunkId}/images")
    public ResponseEntity<ChunkDto> addImagesToChunk(
            @PathVariable Long projectId,
            @PathVariable Long chunkId,
            @Valid @RequestBody ChunkAddImagesRequestDto request) {
        
        logger.info("Adding {} images to chunk {} in project {}", 
                request.getImageIds().size(), chunkId, projectId);
        
        ChunkDto chunk = chunkService.addImagesToChunk(projectId, chunkId, request);
        return ResponseEntity.ok(chunk);
    }

    /**
     * Remove images from a chunk
     */
    @DeleteMapping("/{chunkId}/images")
    public ResponseEntity<ChunkDto> removeImagesFromChunk(
            @PathVariable Long projectId,
            @PathVariable Long chunkId,
            @RequestBody List<Long> imageIds) {
        
        logger.info("Removing {} images from chunk {} in project {}", 
                imageIds.size(), chunkId, projectId);
        
        ChunkDto chunk = chunkService.removeImagesFromChunk(projectId, chunkId, imageIds);
        return ResponseEntity.ok(chunk);
    }

    /**
     * Get images in a chunk
     */
    @GetMapping("/{chunkId}/images")
    public ResponseEntity<List<ProjectImageDto>> getChunkImages(
            @PathVariable Long projectId,
            @PathVariable Long chunkId) {
        
        List<ProjectImageDto> images = chunkService.getChunkImages(projectId, chunkId);
        return ResponseEntity.ok(images);
    }

    /**
     * Update processing options for a chunk
     */
    @PutMapping("/{chunkId}/options")
    public ResponseEntity<ChunkDto> updateProcessingOptions(
            @PathVariable Long projectId,
            @PathVariable Long chunkId,
            @RequestBody Map<String, Object> options) {
        
        logger.info("Updating processing options for chunk {} in project {}", chunkId, projectId);
        
        ChunkDto chunk = chunkService.updateProcessingOptions(projectId, chunkId, options);
        return ResponseEntity.ok(chunk);
    }

    /**
     * Start processing a chunk (JSON options, sem GCP)
     */
    @PostMapping(value = "/{chunkId}/process", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ChunkDto> processChunk(
            @PathVariable Long projectId,
            @PathVariable Long chunkId,
            @RequestBody(required = false) Map<String, Object> options) {
        
        logger.info("Starting processing for chunk {} in project {} with options: {}", 
                chunkId, projectId, options);
        
        ChunkDto chunk = chunkService.processChunk(projectId, chunkId, options != null ? options : Map.of(), null);
        return ResponseEntity.accepted().body(chunk);
    }

    /**
     * Start processing a chunk com arquivo GCP (multipart/form-data)
     */
    @PostMapping(value = "/{chunkId}/process", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ChunkDto> processChunkWithGcp(
            @PathVariable Long projectId,
            @PathVariable Long chunkId,
            @RequestParam(value = "options", required = false) String optionsJson,
            @RequestParam(value = "gcpFile", required = false) MultipartFile gcpFile) {

        logger.info("Starting processing with GCP for chunk {} in project {}", chunkId, projectId);

        Map<String, Object> options = Map.of();
        if (optionsJson != null && !optionsJson.isBlank()) {
            try {
                options = objectMapper.readValue(optionsJson, new TypeReference<>() {});
            } catch (IOException e) {
                logger.warn("Failed to parse options JSON: {}", e.getMessage());
            }
        }

        byte[] gcpContent = null;
        if (gcpFile != null && !gcpFile.isEmpty()) {
            try {
                gcpContent = gcpFile.getBytes();
                logger.info("GCP file received: {} ({} bytes)", gcpFile.getOriginalFilename(), gcpContent.length);
            } catch (IOException e) {
                logger.warn("Failed to read GCP file: {}", e.getMessage());
            }
        }

        ChunkDto chunk = chunkService.processChunk(projectId, chunkId, options, gcpContent);
        return ResponseEntity.accepted().body(chunk);
    }

    /**
     * Update chunk status (internal use)
     */
    @PatchMapping("/{chunkId}/status")
    public ResponseEntity<ChunkDto> updateChunkStatus(
            @PathVariable Long projectId,
            @PathVariable Long chunkId,
            @RequestParam String status,
            @RequestParam(required = false) Integer progress,
            @RequestParam(required = false) String message) {
        
        logger.info("Updating status for chunk {} to {}", chunkId, status);
        
        ChunkDto chunk = chunkService.updateChunkStatus(projectId, chunkId, status, 
                progress != null ? progress : 0, message);
        return ResponseEntity.ok(chunk);
    }

    /**
     * Ensure project has chunks (migration endpoint)
     */
    @PostMapping("/ensure")
    public ResponseEntity<List<ChunkDto>> ensureProjectHasChunks(@PathVariable Long projectId) {
        
        logger.info("Ensuring project {} has chunks", projectId);
        
        chunkService.ensureProjectHasChunks(projectId);
        List<ChunkDto> chunks = chunkService.getChunksByProject(projectId);
        return ResponseEntity.ok(chunks);
    }

    /**
     * Download asset from NodeODM via filesystem (streaming for large files)
     */
    @GetMapping("/{chunkId}/assets/{filename}")
    public ResponseEntity<Resource> downloadAsset(
            @PathVariable Long projectId,
            @PathVariable Long chunkId,
            @PathVariable String filename) {
        
        logger.info("Downloading asset {} for chunk {} in project {}", filename, chunkId, projectId);
        
        try {
            ChunkDto chunk = chunkService.getChunk(projectId, chunkId);
            
            if (chunk.getNodeodmTaskId() == null || chunk.getNodeodmTaskId().isEmpty()) {
                logger.warn("Chunk {} has no NodeODM task ID", chunkId);
                return ResponseEntity.notFound().build();
            }

            long fileSize;
            try {
                fileSize = chunkService.getAssetFileSize(chunk.getNodeodmTaskId(), filename);
            } catch (java.io.IOException e) {
                logger.warn("Asset file not found on disk for task {} file {}: {}",
                        chunk.getNodeodmTaskId(), filename, e.getMessage());
                return ResponseEntity.notFound().build();
            }

            logger.info("Asset {} has size {} bytes ({} MB)", filename, fileSize, fileSize / 1024 / 1024);
            
            InputStreamResource resource = chunkService.downloadAssetFromNodeODM(
                    chunk.getNodeodmTaskId(), filename);
            
            // Determine content type based on file extension
            String contentType = determineContentType(filename);
            
            return ResponseEntity.ok()
                    .contentType(MediaType.parseMediaType(contentType))
                    .contentLength(fileSize)
                    .header("Content-Disposition", "attachment; filename=\"" + filename + "\"")
                    .body(resource);
                    
        } catch (Exception e) {
            logger.error("Error downloading asset {} (chunk={}, project={}): {}",
                    filename, chunkId, projectId, e.getMessage(), e);
            return ResponseEntity.internalServerError().build();
        }
    }
    
    /**
     * Retry a failed chunk: resets state and restarts processing with the saved options.
     * POST /api/v1/projects/{projectId}/chunks/{chunkId}/retry
     */
    @PostMapping("/{chunkId}/retry")
    public ResponseEntity<?> retryChunk(
            @PathVariable Long projectId,
            @PathVariable Long chunkId) {
        try {
            ChunkDto chunk = chunkService.retryChunk(projectId, chunkId);
            return ResponseEntity.ok(chunk);
        } catch (RuntimeException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    private String determineContentType(String filename) {
        String lower = filename.toLowerCase();
        if (lower.endsWith(".tif") || lower.endsWith(".tiff")) {
            return "image/tiff";
        } else if (lower.endsWith(".las") || lower.endsWith(".laz")) {
            return "application/octet-stream";
        } else if (lower.endsWith(".obj")) {
            return "model/obj";
        } else if (lower.endsWith(".zip")) {
            return "application/zip";
        } else if (lower.endsWith(".json")) {
            return "application/json";
        } else if (lower.endsWith(".txt")) {
            return "text/plain";
        }
        return "application/octet-stream";
    }
}
