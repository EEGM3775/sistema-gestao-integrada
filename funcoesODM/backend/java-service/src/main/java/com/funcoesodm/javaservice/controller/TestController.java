package com.funcoesodm.javaservice.controller;

import com.funcoesodm.javaservice.service.WebSocketService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.concurrent.CompletableFuture;

/**
 * Controller for testing and simulating processing tasks
 */
@RestController
@RequestMapping("/api/v1/test")
public class TestController {

    private final WebSocketService webSocketService;

    public TestController(WebSocketService webSocketService) {
        this.webSocketService = webSocketService;
    }

    /**
     * Simulate a processing task with progress updates
     * POST /api/v1/test/simulate-processing/{projectId}
     */
    @PostMapping("/simulate-processing/{projectId}")
    public ResponseEntity<Map<String, String>> simulateProcessing(
            @PathVariable Long projectId,
            @RequestParam(defaultValue = "10") int durationSeconds) {
        
        Long taskId = System.currentTimeMillis(); // Simulated task ID
        
        // Run simulation in background
        CompletableFuture.runAsync(() -> {
            try {
                // Task started
                webSocketService.sendTaskStarted(projectId, taskId, "Iniciando processamento...");
                Thread.sleep(1000);

                // Progress updates
                String[] stages = {
                    "Carregando imagens...",
                    "Detectando pontos de interesse...",
                    "Alinhando fotos...",
                    "Construindo nuvem de pontos densa...",
                    "Gerando malha 3D...",
                    "Texturizando modelo...",
                    "Gerando ortofoto...",
                    "Exportando resultados...",
                    "Finalizando..."
                };

                int stepsPerStage = durationSeconds * 1000 / stages.length;
                
                for (int i = 0; i < stages.length; i++) {
                    int progress = (int) ((i + 1) * 100.0 / stages.length);
                    webSocketService.sendTaskProgress(projectId, taskId, progress, stages[i]);
                    Thread.sleep(stepsPerStage);
                }

                // Task completed
                Map<String, String> outputs = Map.of(
                    "orthophoto", "/outputs/orthophoto.tif",
                    "dsm", "/outputs/dsm.tif",
                    "pointCloud", "/outputs/pointcloud.las"
                );
                webSocketService.sendTaskCompleted(projectId, taskId, "Processamento concluído!", outputs);
                
            } catch (InterruptedException e) {
                webSocketService.sendTaskFailed(projectId, taskId, "Processamento cancelado");
                Thread.currentThread().interrupt();
            } catch (Exception e) {
                webSocketService.sendTaskFailed(projectId, taskId, "Erro: " + e.getMessage());
            }
        });

        return ResponseEntity.ok(Map.of(
            "message", "Simulação de processamento iniciada",
            "projectId", projectId.toString(),
            "taskId", taskId.toString(),
            "durationSeconds", String.valueOf(durationSeconds)
        ));
    }

    /**
     * Send a test progress message
     * POST /api/v1/test/send-progress/{projectId}
     */
    @PostMapping("/send-progress/{projectId}")
    public ResponseEntity<Map<String, String>> sendTestProgress(
            @PathVariable Long projectId,
            @RequestParam(defaultValue = "50") int progress,
            @RequestParam(defaultValue = "Processando...") String message) {
        
        webSocketService.sendTaskProgress(projectId, 1L, progress, message);
        
        return ResponseEntity.ok(Map.of(
            "status", "sent",
            "projectId", projectId.toString(),
            "progress", String.valueOf(progress),
            "message", message
        ));
    }
}
