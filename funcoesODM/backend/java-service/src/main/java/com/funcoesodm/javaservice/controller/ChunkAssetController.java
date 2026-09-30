package com.funcoesodm.javaservice.controller;

import com.funcoesodm.javaservice.service.ChunkService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.io.InputStreamResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * Serves processed assets directly by NodeODM task UUID.
 * URL pattern matches the one stored in task/chunk outputs:
 *   GET /api/v1/chunks/{nodeodmTaskId}/assets/{filename}
 *
 * No auth required — permitted in SecurityConfig so that GeoTiffCacheService
 * (which uses raw fetch() without JWT) can stream large GeoTIFF files.
 */
@RestController
@RequestMapping("/api/v1/chunks")
public class ChunkAssetController {

    private static final Logger logger = LoggerFactory.getLogger(ChunkAssetController.class);

    private final ChunkService chunkService;

    @Autowired
    public ChunkAssetController(ChunkService chunkService) {
        this.chunkService = chunkService;
    }

    @GetMapping("/{nodeodmTaskId}/assets/{filename}")
    public ResponseEntity<Resource> downloadAsset(
            @PathVariable String nodeodmTaskId,
            @PathVariable String filename) {

        logger.info("UUID-based asset download: task={} file={}", nodeodmTaskId, filename);

        try {
            long fileSize;
            try {
                fileSize = chunkService.getAssetFileSize(nodeodmTaskId, filename);
            } catch (java.io.IOException e) {
                logger.warn("Asset not found on disk: task={} file={}: {}", nodeodmTaskId, filename, e.getMessage());
                return ResponseEntity.notFound().build();
            }

            InputStreamResource resource = chunkService.downloadAssetFromNodeODM(nodeodmTaskId, filename);

            String contentType = determineContentType(filename);

            return ResponseEntity.ok()
                    .contentType(MediaType.parseMediaType(contentType))
                    .contentLength(fileSize)
                    .header("Content-Disposition", "inline; filename=\"" + filename + "\"")
                    .body(resource);

        } catch (Exception e) {
            logger.error("Error serving asset task={} file={}: {}", nodeodmTaskId, filename, e.getMessage(), e);
            return ResponseEntity.internalServerError().build();
        }
    }

    private String determineContentType(String filename) {
        String lower = filename.toLowerCase();
        if (lower.endsWith(".tif") || lower.endsWith(".tiff")) return "image/tiff";
        if (lower.endsWith(".laz") || lower.endsWith(".las"))  return "application/octet-stream";
        if (lower.endsWith(".zip"))  return "application/zip";
        if (lower.endsWith(".pdf"))  return "application/pdf";
        if (lower.endsWith(".obj"))  return "model/obj";
        if (lower.endsWith(".json")) return "application/json";
        return "application/octet-stream";
    }
}
