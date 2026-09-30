package com.funcoesodm.javaservice.service;

import com.funcoesodm.javaservice.dto.AnnotationDto;
import com.funcoesodm.javaservice.dto.ProgressMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

/**
 * Service for sending WebSocket messages to clients
 */
@Service
public class WebSocketService {

    private static final Logger logger = LoggerFactory.getLogger(WebSocketService.class);

    private final SimpMessagingTemplate messagingTemplate;

    public WebSocketService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    /**
     * Send progress update to all subscribers of a project
     */
    public void sendProjectProgress(Long projectId, ProgressMessage message) {
        String destination = "/topic/project/" + projectId + "/progress";
        logger.debug("Sending progress to {}: {}%", destination, message.getProgress());
        messagingTemplate.convertAndSend(destination, message);
    }

    /**
     * Send task progress update
     */
    public void sendTaskProgress(Long projectId, Long taskId, int progress, String statusMessage) {
        ProgressMessage message = ProgressMessage.taskProgress(projectId, taskId, progress, statusMessage);
        sendProjectProgress(projectId, message);
    }

    /**
     * Send task started notification
     */
    public void sendTaskStarted(Long projectId, Long taskId, String message) {
        ProgressMessage progressMessage = ProgressMessage.taskStarted(projectId, taskId, message);
        sendProjectProgress(projectId, progressMessage);
    }

    /**
     * Send task completed notification
     */
    public void sendTaskCompleted(Long projectId, Long taskId, String message, Object outputs) {
        ProgressMessage progressMessage = ProgressMessage.taskCompleted(projectId, taskId, message, outputs);
        sendProjectProgress(projectId, progressMessage);
    }

    /**
     * Send task failed notification
     */
    public void sendTaskFailed(Long projectId, Long taskId, String errorMessage) {
        ProgressMessage progressMessage = ProgressMessage.taskFailed(projectId, taskId, errorMessage);
        sendProjectProgress(projectId, progressMessage);
    }

    /**
     * Send a general notification to all connected clients
     */
    public void sendGlobalNotification(String message) {
        logger.info("Sending global notification: {}", message);
        messagingTemplate.convertAndSend("/topic/notifications", message);
    }

    /**
     * Send a message to a specific user
     */
    public void sendToUser(String username, String destination, Object message) {
        logger.debug("Sending message to user {}: {}", username, destination);
        messagingTemplate.convertAndSendToUser(username, destination, message);
    }

    // ==================== CHUNK METHODS ====================

    /**
     * Send chunk progress update
     */
    public void sendChunkProgress(Long projectId, Long chunkId, int progress, String statusMessage) {
        ProgressMessage message = ProgressMessage.chunkProgress(projectId, chunkId, progress, statusMessage);
        String destination = "/topic/project/" + projectId + "/chunk/" + chunkId + "/progress";
        logger.debug("Sending chunk progress to {}: {}%", destination, progress);
        messagingTemplate.convertAndSend(destination, message);
        // Also send to project topic for dashboard
        sendProjectProgress(projectId, message);
    }

    /**
     * Send chunk completed notification
     */
    public void sendChunkCompleted(Long projectId, Long chunkId, String message, Object outputs) {
        ProgressMessage progressMessage = ProgressMessage.chunkCompleted(projectId, chunkId, message, outputs);
        String destination = "/topic/project/" + projectId + "/chunk/" + chunkId + "/progress";
        logger.info("Chunk {} completed", chunkId);
        messagingTemplate.convertAndSend(destination, progressMessage);
        sendProjectProgress(projectId, progressMessage);
    }

    // ==================== ANNOTATION METHODS ====================

    public void sendAnnotationCreated(Long projectId, AnnotationDto annotation) {
        ProgressMessage msg = new ProgressMessage();
        msg.setType(ProgressMessage.ProgressType.ANNOTATION_CREATED);
        msg.setProjectId(projectId);
        msg.setData(annotation);
        sendProjectProgress(projectId, msg);
    }

    public void sendAnnotationDeleted(Long projectId, Long annotationId) {
        ProgressMessage msg = new ProgressMessage();
        msg.setType(ProgressMessage.ProgressType.ANNOTATION_DELETED);
        msg.setProjectId(projectId);
        msg.setData(annotationId);
        sendProjectProgress(projectId, msg);
    }

    public void sendAnnotationUpdated(Long projectId, AnnotationDto annotation) {
        ProgressMessage msg = new ProgressMessage();
        msg.setType(ProgressMessage.ProgressType.ANNOTATION_UPDATED);
        msg.setProjectId(projectId);
        msg.setData(annotation);
        sendProjectProgress(projectId, msg);
    }

    /**
     * Send chunk failed notification
     */
    public void sendChunkFailed(Long projectId, Long chunkId, String errorMessage) {
        ProgressMessage progressMessage = ProgressMessage.chunkFailed(projectId, chunkId, errorMessage);
        String destination = "/topic/project/" + projectId + "/chunk/" + chunkId + "/progress";
        logger.error("Chunk {} failed: {}", chunkId, errorMessage);
        messagingTemplate.convertAndSend(destination, progressMessage);
        sendProjectProgress(projectId, progressMessage);
    }
}
