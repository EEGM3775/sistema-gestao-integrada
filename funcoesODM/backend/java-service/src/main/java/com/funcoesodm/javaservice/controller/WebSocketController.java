package com.funcoesodm.javaservice.controller;

import com.funcoesodm.javaservice.dto.ProgressMessage;
import com.funcoesodm.javaservice.service.WebSocketService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

/**
 * WebSocket controller for handling real-time messages
 */
@Controller
public class WebSocketController {

    private static final Logger logger = LoggerFactory.getLogger(WebSocketController.class);

    private final WebSocketService webSocketService;

    public WebSocketController(WebSocketService webSocketService) {
        this.webSocketService = webSocketService;
    }

    /**
     * Handle messages sent to /app/project/{projectId}/subscribe
     * Clients can use this to confirm subscription
     */
    @MessageMapping("/project/{projectId}/subscribe")
    @SendTo("/topic/project/{projectId}/progress")
    public ProgressMessage subscribeToProject(@DestinationVariable Long projectId) {
        logger.info("Client subscribed to project {}", projectId);
        
        ProgressMessage message = new ProgressMessage();
        message.setProjectId(projectId);
        message.setType(ProgressMessage.ProgressType.PROCESSING_STATUS);
        message.setMessage("Subscribed to project " + projectId);
        message.setProgress(0);
        
        return message;
    }

    /**
     * Handle ping messages for connection health check
     */
    @MessageMapping("/ping")
    @SendTo("/topic/pong")
    public String ping() {
        logger.debug("Received ping");
        return "pong";
    }
}
