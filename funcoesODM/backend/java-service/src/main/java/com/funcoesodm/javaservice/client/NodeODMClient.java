package com.funcoesodm.javaservice.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.*;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;

@Component
public class NodeODMClient {

    private static final Logger logger = LoggerFactory.getLogger(NodeODMClient.class);

        private static final Map<String, String> ASSET_ALIASES = Map.ofEntries(
            Map.entry("orthophoto", "orthophoto.tif"),
            Map.entry("orthophoto.tif", "orthophoto.tif"),
            Map.entry("dsm", "dsm.tif"),
            Map.entry("dsm.tif", "dsm.tif"),
            Map.entry("dtm", "dtm.tif"),
            Map.entry("dtm.tif", "dtm.tif"),
            Map.entry("pointcloud", "georeferenced_model.laz"),
            Map.entry("georeferenced_model", "georeferenced_model.laz"),
            Map.entry("georeferenced_model.laz", "georeferenced_model.laz"),
            Map.entry("mesh", "mesh.ply"),
            Map.entry("mesh.ply", "mesh.ply"),
            Map.entry("model3d", "textured_model.zip"),
            Map.entry("textured_model", "textured_model.zip"),
            Map.entry("textured_model.zip", "textured_model.zip"),
            Map.entry("report", "report.pdf"),
            Map.entry("report.pdf", "report.pdf"),
            Map.entry("all", "all.zip"),
            Map.entry("all.zip", "all.zip")
        );

    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;
    private final String nodeodmUrl;
    private final String nodeodmDataDir;

    public NodeODMClient(
            RestTemplate restTemplate,
            ObjectMapper objectMapper,
            @Value("${nodeodm.service.url:http://nodeodm:3000}") String nodeodmUrl,
            @Value("${nodeodm.data.dir:/nodeodm/data}") String nodeodmDataDir) {
        this.restTemplate = restTemplate;
        this.objectMapper = objectMapper;
        this.nodeodmUrl = nodeodmUrl;
        this.nodeodmDataDir = nodeodmDataDir;
        logger.info("NodeODMClient initialized with URL: {}", nodeodmUrl);
    }

    public boolean isHealthy() {
        try {
            ResponseEntity<JsonNode> response = restTemplate.getForEntity(nodeodmUrl + "/info", JsonNode.class);
            return response.getStatusCode().is2xxSuccessful();
        } catch (Exception e) {
            logger.warn("NodeODM health check failed: {}", e.getMessage());
            return false;
        }
    }

    public JsonNode createTask(List<byte[]> imageData, List<String> imageNames, String name, Map<String, Object> options, byte[] gcpContent) {
        try {
            String url = nodeodmUrl + "/task/new";

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);

            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();

            for (int i = 0; i < imageData.size(); i++) {
                byte[] data = imageData.get(i);
                String fileName = imageNames.get(i);

                ByteArrayResource resource = new ByteArrayResource(data) {
                    @Override
                    public String getFilename() {
                        return fileName;
                    }
                };
                body.add("images", resource);
            }

            if (name != null && !name.isBlank()) {
                body.add("name", name);
            }

            // Arquivo GCP: NodeODM espera o arquivo com nome "gcp_list.txt" no campo "images"
            if (gcpContent != null && gcpContent.length > 0) {
                ByteArrayResource gcpResource = new ByteArrayResource(gcpContent) {
                    @Override
                    public String getFilename() {
                        return "gcp_list.txt";
                    }
                };
                body.add("images", gcpResource);
                logger.info("GCP file (gcp_list.txt) adicionado ao task NodeODM ({} bytes)", gcpContent.length);
            }

            if (options != null && !options.isEmpty()) {
                ArrayNode optionsArray = objectMapper.createArrayNode();
                options.forEach((key, value) -> {
                    ObjectNode opt = objectMapper.createObjectNode();
                    opt.put("name", toKebabCase(key));
                    if (value instanceof Boolean) {
                        opt.put("value", ((Boolean) value) ? "true" : "false");
                    } else {
                        opt.put("value", String.valueOf(value));
                    }
                    optionsArray.add(opt);
                });
                body.add("options", optionsArray.toString());
            }

            HttpEntity<MultiValueMap<String, Object>> request = new HttpEntity<>(body, headers);
            ResponseEntity<JsonNode> response = restTemplate.postForEntity(url, request, JsonNode.class);

            if (response.getStatusCode().is2xxSuccessful() && response.getBody() != null) {
                logger.info("Created NodeODM task: {}", response.getBody().get("uuid"));
                return response.getBody();
            }
            throw new RuntimeException("Failed to create task: " + response.getStatusCode());
        } catch (Exception e) {
            logger.error("Error creating NodeODM task: {}", e.getMessage());
            throw new RuntimeException("Failed to create NodeODM task", e);
        }
    }

    public JsonNode getTaskStatus(String taskId) {
        try {
            String url = nodeodmUrl + "/task/" + taskId + "/info";
            ResponseEntity<JsonNode> response = restTemplate.getForEntity(url, JsonNode.class);
            JsonNode task = response.getBody();
            if (task == null) {
                throw new RuntimeException("Empty response from NodeODM");
            }

            int statusCode = task.path("status").path("code").asInt(10);
            String status = mapStatusCode(statusCode);
            int progress = task.path("progress").asInt(0);
            String lastError = task.path("status").path("errorMessage").asText(null);

            ObjectNode result = objectMapper.createObjectNode();
            result.put("task_id", taskId);
            result.put("status", status);
            result.put("status_code", statusCode);
            result.put("progress", progress);
            if (lastError != null) {
                result.put("last_error", lastError);
            }

            ArrayNode assets = objectMapper.createArrayNode();
            for (String asset : getAvailableAssetsList(taskId)) {
                assets.add(asset);
            }
            result.set("available_assets", assets);

            return result;
        } catch (Exception e) {
            logger.error("Error getting task status: {}", e.getMessage());
            throw new RuntimeException("Failed to get task status", e);
        }
    }

    public JsonNode getAvailableAssets(String taskId) {
        ObjectNode result = objectMapper.createObjectNode();
        ArrayNode assets = objectMapper.createArrayNode();
        for (String asset : getAvailableAssetsList(taskId)) {
            assets.add(asset);
        }
        result.set("available_assets", assets);
        return result;
    }

    public JsonNode validateAssets(String taskId) {
        List<AssetValidation> validations = validateAssetsInternal(taskId);

        ObjectNode result = objectMapper.createObjectNode();
        ArrayNode validAssets = objectMapper.createArrayNode();
        ArrayNode invalidAssets = objectMapper.createArrayNode();

        int validCount = 0;
        for (AssetValidation validation : validations) {
            if (validation.valid) {
                ObjectNode asset = objectMapper.createObjectNode();
                asset.put("name", validation.name);
                asset.put("size", validation.size);
                validAssets.add(asset);
                validCount++;
            } else {
                ObjectNode asset = objectMapper.createObjectNode();
                asset.put("name", validation.name);
                asset.put("error", validation.error);
                invalidAssets.add(asset);
            }
        }

        result.put("valid_count", validCount);
        result.put("all_valid", validCount == ASSET_FILE_PATHS.size());
        result.set("valid_assets", validAssets);
        result.set("invalid_assets", invalidAssets);

        return result;
    }

    public void cancelTask(String taskId) {
        try {
            String url = nodeodmUrl + "/task/cancel";
            MultiValueMap<String, String> body = new LinkedMultiValueMap<>();
            body.add("uuid", taskId);
            restTemplate.postForEntity(url, body, JsonNode.class);
            logger.info("Cancelled NodeODM task: {}", taskId);
        } catch (Exception e) {
            logger.error("Error cancelling task: {}", e.getMessage());
            throw new RuntimeException("Failed to cancel task", e);
        }
    }

    public void removeTask(String taskId) {
        try {
            String url = nodeodmUrl + "/task/remove";
            MultiValueMap<String, String> body = new LinkedMultiValueMap<>();
            body.add("uuid", taskId);
            restTemplate.postForEntity(url, body, JsonNode.class);
            logger.info("Removed NodeODM task: {}", taskId);
        } catch (Exception e) {
            logger.error("Error removing task: {}", e.getMessage());
            throw new RuntimeException("Failed to remove task", e);
        }
    }

    public Optional<ResolvedAsset> resolveAssetForDownload(String taskId, String assetName) {
        if (taskId == null || assetName == null || assetName.isBlank()) {
            return Optional.empty();
        }

        String canonicalName = normalizeAssetName(assetName);
        String relativePath = ASSET_FILE_PATHS.get(canonicalName);
        if (relativePath == null) {
            return Optional.empty();
        }

        Path path = resolveAssetPath(taskId, relativePath);
        if (path == null || !Files.isRegularFile(path)) {
            return Optional.empty();
        }

        return Optional.of(new ResolvedAsset(path, canonicalName));
    }

    private List<String> getAvailableAssetsList(String taskId) {
        List<String> assets = new ArrayList<>();
        for (String asset : ASSET_FILE_PATHS.keySet()) {
            if (assetExists(taskId, asset)) {
                assets.add(asset);
            }
        }
        return assets;
    }

    private List<AssetValidation> validateAssetsInternal(String taskId) {
        List<AssetValidation> validations = new ArrayList<>();
        for (Map.Entry<String, String> entry : ASSET_FILE_PATHS.entrySet()) {
            String name = entry.getKey();
            Path path = resolveAssetPath(taskId, entry.getValue());
            if (path != null && Files.isRegularFile(path)) {
                try {
                    validations.add(new AssetValidation(name, true, Files.size(path), null));
                } catch (Exception e) {
                    validations.add(new AssetValidation(name, false, 0, "size_error"));
                }
            } else {
                validations.add(new AssetValidation(name, false, 0, "not_found"));
            }
        }
        return validations;
    }

    private boolean assetExists(String taskId, String assetName) {
        Path path = resolveAssetPath(taskId, ASSET_FILE_PATHS.get(assetName));
        return path != null && Files.isRegularFile(path);
    }

    private Path resolveAssetPath(String taskId, String relativePath) {
        if (relativePath == null || taskId == null) {
            return null;
        }
        return Paths.get(nodeodmDataDir, taskId, relativePath);
    }

    private String normalizeAssetName(String assetName) {
        String normalized = assetName.trim().toLowerCase(Locale.ROOT);
        return ASSET_ALIASES.getOrDefault(normalized, normalized);
    }

    /**
     * Map of asset names to their actual file paths within the NodeODM task directory
     */
    private static final Map<String, String> ASSET_FILE_PATHS = Map.ofEntries(
            Map.entry("orthophoto.tif", "odm_orthophoto/odm_orthophoto.tif"),
            Map.entry("orthophoto", "odm_orthophoto/odm_orthophoto.tif"),
            Map.entry("dsm.tif", "odm_dem/dsm.tif"),
            Map.entry("dsm", "odm_dem/dsm.tif"),
            Map.entry("dtm.tif", "odm_dem/dtm.tif"),
            Map.entry("dtm", "odm_dem/dtm.tif"),
            Map.entry("georeferenced_model.laz", "odm_georeferencing/odm_georeferenced_model.laz"),
            Map.entry("pointcloud.laz", "odm_georeferencing/odm_georeferenced_model.laz"),
            Map.entry("pointcloud", "odm_georeferencing/odm_georeferenced_model.laz"),
            Map.entry("mesh.ply", "odm_meshing/odm_mesh.ply"),
            Map.entry("mesh", "odm_meshing/odm_mesh.ply"),
            Map.entry("textured_model.zip", "odm_texturing/odm_textured_model_geo.zip"),
            Map.entry("model3d.zip", "odm_texturing/odm_textured_model_geo.zip"),
            Map.entry("model3d", "odm_texturing/odm_textured_model_geo.zip"),
            Map.entry("report.pdf", "odm_report/report.pdf"),
            Map.entry("report", "odm_report/report.pdf"),
            Map.entry("all.zip", "all.zip")
    );

    /**
     * Download an asset from NodeODM by reading directly from the shared filesystem.
     * This is more efficient than HTTP for large files like orthophotos (700MB+).
     */
    public java.io.InputStream downloadAsset(String taskId, String filename) throws java.io.IOException {
        // Resolve the actual file path
        String relativePath = ASSET_FILE_PATHS.getOrDefault(filename.toLowerCase(), filename);
        Path filePath = Paths.get(nodeodmDataDir, taskId, relativePath);
        
        logger.info("Downloading asset from filesystem: {} (resolved to: {})", filename, filePath);
        
        if (!Files.exists(filePath)) {
            logger.error("Asset file not found: {}", filePath);
            throw new java.io.IOException("Asset file not found: " + filename);
        }
        
        // Return file input stream directly - much more efficient for large files
        return Files.newInputStream(filePath);
    }
    
    /**
     * Get the size of an asset file for Content-Length header
     */
    public long getAssetFileSize(String taskId, String filename) throws java.io.IOException {
        String relativePath = ASSET_FILE_PATHS.getOrDefault(filename.toLowerCase(), filename);
        Path filePath = Paths.get(nodeodmDataDir, taskId, relativePath);
        
        logger.debug("Checking asset size at path: {}", filePath);
        
        if (!Files.exists(filePath)) {
            logger.warn("Asset not found at path: {}", filePath);
            throw new java.io.IOException("Asset file not found: " + filename + " (path: " + filePath + ")");
        }
        
        return Files.size(filePath);
    }

    public static class ResolvedAsset {
        private final Path path;
        private final String filename;

        public ResolvedAsset(Path path, String filename) {
            this.path = path;
            this.filename = filename;
        }

        public Path getPath() {
            return path;
        }

        public String getFilename() {
            return filename;
        }
    }

    private String mapStatusCode(int code) {
        return switch (code) {
            case 10 -> "QUEUED";
            case 20 -> "RUNNING";
            case 30 -> "FAILED";
            case 40 -> "COMPLETED";
            case 50 -> "CANCELED";
            default -> "QUEUED";
        };
    }

    private String toKebabCase(String key) {
        if (key == null) return "";
        String withHyphens = key.replaceAll("([a-z])([A-Z])", "$1-$2");
        return withHyphens.replace('_', '-').toLowerCase(Locale.ROOT);
    }

    private static class AssetValidation {
        final String name;
        final boolean valid;
        final long size;
        final String error;

        AssetValidation(String name, boolean valid, long size, String error) {
            this.name = name;
            this.valid = valid;
            this.size = size;
            this.error = error;
        }
    }
}