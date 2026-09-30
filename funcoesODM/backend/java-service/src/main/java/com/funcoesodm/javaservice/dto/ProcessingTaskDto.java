package com.funcoesodm.javaservice.dto;

import com.funcoesodm.javaservice.model.ProcessingTask;
import java.time.LocalDateTime;

public class ProcessingTaskDto {

    private Long id;
    private Long projectId;
    private String name;
    private String status;
    private Integer progress;
    private String statusMessage;
    private String nodeodmTaskId;
    private String options;
    private String outputs;
    private String errorMessage;
    private String warningMessage;  // Non-critical warnings during processing
    private LocalDateTime createdAt;
    private LocalDateTime startedAt;
    private LocalDateTime completedAt;

    public ProcessingTaskDto() {}

    public static ProcessingTaskDto fromEntity(ProcessingTask task) {
        ProcessingTaskDto dto = new ProcessingTaskDto();
        dto.setId(task.getId());
        dto.setProjectId(task.getProject() != null ? task.getProject().getId() : null);
        dto.setName(task.getName());
        dto.setStatus(task.getStatus() != null ? task.getStatus().name() : null);
        dto.setProgress(task.getProgress() != null ? task.getProgress() : 0);
        dto.setStatusMessage(task.getStatusMessage());
        dto.setNodeodmTaskId(task.getNodeodmTaskId());
        dto.setOptions(task.getOptions());
        dto.setOutputs(task.getOutputs());
        dto.setErrorMessage(task.getErrorMessage());
        dto.setWarningMessage(task.getWarningMessage());
        dto.setCreatedAt(task.getCreatedAt());
        dto.setStartedAt(task.getStartedAt());
        dto.setCompletedAt(task.getCompletedAt());
        
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

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Integer getProgress() {
        return progress;
    }

    public void setProgress(Integer progress) {
        this.progress = progress;
    }

    public String getStatusMessage() {
        return statusMessage;
    }

    public void setStatusMessage(String statusMessage) {
        this.statusMessage = statusMessage;
    }

    public String getNodeodmTaskId() {
        return nodeodmTaskId;
    }

    public void setNodeodmTaskId(String nodeodmTaskId) {
        this.nodeodmTaskId = nodeodmTaskId;
    }

    public String getOptions() {
        return options;
    }

    public void setOptions(String options) {
        this.options = options;
    }

    public String getOutputs() {
        return outputs;
    }

    public void setOutputs(String outputs) {
        this.outputs = outputs;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }

    public String getWarningMessage() {
        return warningMessage;
    }

    public void setWarningMessage(String warningMessage) {
        this.warningMessage = warningMessage;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
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
