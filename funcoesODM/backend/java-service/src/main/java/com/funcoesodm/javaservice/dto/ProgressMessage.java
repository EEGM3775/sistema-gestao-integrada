package com.funcoesodm.javaservice.dto;

/**
 * DTO for WebSocket progress messages
 */
public class ProgressMessage {

    public enum ProgressType {
        TASK_STARTED,
        TASK_PROGRESS,
        TASK_COMPLETED,
        TASK_FAILED,
        CHUNK_STARTED,
        CHUNK_PROGRESS,
        CHUNK_COMPLETED,
        CHUNK_FAILED,
        UPLOAD_PROGRESS,
        PROCESSING_STATUS,
        ANNOTATION_CREATED,
        ANNOTATION_DELETED,
        ANNOTATION_UPDATED
    }

    private Long projectId;
    private Long taskId;
    private Long chunkId;
    private ProgressType type;
    private int progress;         // 0-100
    private String message;
    private String status;
    private Object data;          // Additional data (e.g., outputs)

    public ProgressMessage() {}

    public ProgressMessage(Long projectId, ProgressType type, int progress, String message) {
        this.projectId = projectId;
        this.type = type;
        this.progress = progress;
        this.message = message;
    }

    public static ProgressMessage taskStarted(Long projectId, Long taskId, String message) {
        ProgressMessage msg = new ProgressMessage();
        msg.setProjectId(projectId);
        msg.setTaskId(taskId);
        msg.setType(ProgressType.TASK_STARTED);
        msg.setProgress(0);
        msg.setMessage(message);
        msg.setStatus("RUNNING");
        return msg;
    }

    public static ProgressMessage taskProgress(Long projectId, Long taskId, int progress, String message) {
        ProgressMessage msg = new ProgressMessage();
        msg.setProjectId(projectId);
        msg.setTaskId(taskId);
        msg.setType(ProgressType.TASK_PROGRESS);
        msg.setProgress(progress);
        msg.setMessage(message);
        msg.setStatus("RUNNING");
        return msg;
    }

    public static ProgressMessage taskCompleted(Long projectId, Long taskId, String message, Object data) {
        ProgressMessage msg = new ProgressMessage();
        msg.setProjectId(projectId);
        msg.setTaskId(taskId);
        msg.setType(ProgressType.TASK_COMPLETED);
        msg.setProgress(100);
        msg.setMessage(message);
        msg.setStatus("COMPLETED");
        msg.setData(data);
        return msg;
    }

    public static ProgressMessage taskFailed(Long projectId, Long taskId, String message) {
        ProgressMessage msg = new ProgressMessage();
        msg.setProjectId(projectId);
        msg.setTaskId(taskId);
        msg.setType(ProgressType.TASK_FAILED);
        msg.setProgress(0);
        msg.setMessage(message);
        msg.setStatus("FAILED");
        return msg;
    }

    // ==================== CHUNK FACTORY METHODS ====================

    public static ProgressMessage chunkProgress(Long projectId, Long chunkId, int progress, String message) {
        ProgressMessage msg = new ProgressMessage();
        msg.setProjectId(projectId);
        msg.setChunkId(chunkId);
        msg.setType(ProgressType.CHUNK_PROGRESS);
        msg.setProgress(progress);
        msg.setMessage(message);
        msg.setStatus("RUNNING");
        return msg;
    }

    public static ProgressMessage chunkCompleted(Long projectId, Long chunkId, String message, Object data) {
        ProgressMessage msg = new ProgressMessage();
        msg.setProjectId(projectId);
        msg.setChunkId(chunkId);
        msg.setType(ProgressType.CHUNK_COMPLETED);
        msg.setProgress(100);
        msg.setMessage(message);
        msg.setStatus("COMPLETED");
        msg.setData(data);
        return msg;
    }

    public static ProgressMessage chunkFailed(Long projectId, Long chunkId, String message) {
        ProgressMessage msg = new ProgressMessage();
        msg.setProjectId(projectId);
        msg.setChunkId(chunkId);
        msg.setType(ProgressType.CHUNK_FAILED);
        msg.setProgress(0);
        msg.setMessage(message);
        msg.setStatus("FAILED");
        return msg;
    }

    // Getters and Setters
    public Long getProjectId() {
        return projectId;
    }

    public void setProjectId(Long projectId) {
        this.projectId = projectId;
    }

    public Long getTaskId() {
        return taskId;
    }

    public void setTaskId(Long taskId) {
        this.taskId = taskId;
    }

    public ProgressType getType() {
        return type;
    }

    public void setType(ProgressType type) {
        this.type = type;
    }

    public int getProgress() {
        return progress;
    }

    public void setProgress(int progress) {
        this.progress = progress;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Object getData() {
        return data;
    }

    public void setData(Object data) {
        this.data = data;
    }

    public Long getChunkId() {
        return chunkId;
    }

    public void setChunkId(Long chunkId) {
        this.chunkId = chunkId;
    }
}
