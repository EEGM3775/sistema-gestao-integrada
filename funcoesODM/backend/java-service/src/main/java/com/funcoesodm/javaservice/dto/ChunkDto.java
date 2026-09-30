package com.funcoesodm.javaservice.dto;

import com.funcoesodm.javaservice.model.Chunk;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;

public class ChunkDto {
    private Long id;
    private Long projectId;
    private String name;
    private String description;
    private Integer imageCount;
    private String status;
    private String nodeodmTaskId;
    private Integer progress;
    private Map<String, Object> outputs;
    private Map<String, Object> processingOptions;
    private String errorMessage;
    private Long processingTime;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    private LocalDateTime startedAt;
    private LocalDateTime completedAt;

    private static final ObjectMapper objectMapper = new ObjectMapper();

    public ChunkDto() {}

    public static ChunkDto fromEntity(Chunk chunk) {
        ChunkDto dto = new ChunkDto();
        dto.setId(chunk.getId());
        dto.setProjectId(chunk.getProject().getId());
        dto.setName(chunk.getName());
        dto.setDescription(chunk.getDescription());
        dto.setImageCount(chunk.getImageCount());
        dto.setStatus(chunk.getStatus().name());
        dto.setNodeodmTaskId(chunk.getNodeodmTaskId());
        dto.setProgress(chunk.getProgress());
        dto.setErrorMessage(chunk.getErrorMessage());
        dto.setProcessingTime(chunk.getProcessingTime());
        dto.setCreatedAt(chunk.getCreatedAt());
        dto.setUpdatedAt(chunk.getUpdatedAt());
        dto.setStartedAt(chunk.getStartedAt());
        dto.setCompletedAt(chunk.getCompletedAt());

        // Parse outputs JSON
        if (chunk.getOutputs() != null && !chunk.getOutputs().isEmpty()) {
            try {
                dto.setOutputs(objectMapper.readValue(chunk.getOutputs(), new TypeReference<Map<String, Object>>() {}));
            } catch (JsonProcessingException e) {
                dto.setOutputs(new HashMap<>());
            }
        }

        // Parse processing options JSON
        if (chunk.getProcessingOptions() != null && !chunk.getProcessingOptions().isEmpty()) {
            try {
                dto.setProcessingOptions(objectMapper.readValue(chunk.getProcessingOptions(), new TypeReference<Map<String, Object>>() {}));
            } catch (JsonProcessingException e) {
                dto.setProcessingOptions(new HashMap<>());
            }
        }

        return dto;
    }

    // Getters and Setters
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public Long getProjectId() {
        return projectId;
    }

    public void setProjectId(Long projectId) {
        this.projectId = projectId;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public Integer getImageCount() {
        return imageCount;
    }

    public void setImageCount(Integer imageCount) {
        this.imageCount = imageCount;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getNodeodmTaskId() {
        return nodeodmTaskId;
    }

    public void setNodeodmTaskId(String nodeodmTaskId) {
        this.nodeodmTaskId = nodeodmTaskId;
    }

    public Integer getProgress() {
        return progress;
    }

    public void setProgress(Integer progress) {
        this.progress = progress;
    }

    public Map<String, Object> getOutputs() {
        return outputs;
    }

    public void setOutputs(Map<String, Object> outputs) {
        this.outputs = outputs;
    }

    public Map<String, Object> getProcessingOptions() {
        return processingOptions;
    }

    public void setProcessingOptions(Map<String, Object> processingOptions) {
        this.processingOptions = processingOptions;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }

    public Long getProcessingTime() {
        return processingTime;
    }

    public void setProcessingTime(Long processingTime) {
        this.processingTime = processingTime;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(LocalDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }

    public LocalDateTime getStartedAt() {
        return startedAt;
    }

    public void setStartedAt(LocalDateTime startedAt) {
        this.startedAt = startedAt;
    }

    public LocalDateTime getCompletedAt() {
        return completedAt;
    }

    public void setCompletedAt(LocalDateTime completedAt) {
        this.completedAt = completedAt;
    }
}
