package com.funcoesodm.javaservice.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.funcoesodm.javaservice.client.NodeODMClient;
import com.funcoesodm.javaservice.model.Chunk;
import com.funcoesodm.javaservice.repository.ChunkRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class ChunkRecoveryService {

    private static final Logger logger = LoggerFactory.getLogger(ChunkRecoveryService.class);

    private final ChunkRepository chunkRepository;
    private final NodeODMClient nodeodmClient;
    private final WebSocketService webSocketService;
    private final ChunkService chunkService;

    public ChunkRecoveryService(ChunkRepository chunkRepository,
                                NodeODMClient nodeodmClient,
                                WebSocketService webSocketService,
                                ChunkService chunkService) {
        this.chunkRepository = chunkRepository;
        this.nodeodmClient = nodeodmClient;
        this.webSocketService = webSocketService;
        this.chunkService = chunkService;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void recoverInterruptedChunks() {
        List<Chunk> stuck = chunkRepository.findByStatusIn(
            List.of(Chunk.ChunkStatus.RUNNING, Chunk.ChunkStatus.QUEUED)
        );

        if (stuck.isEmpty()) {
            return;
        }

        logger.info("Encontrados {} chunk(s) interrompidos pelo shutdown. Iniciando recuperacao.", stuck.size());

        for (Chunk chunk : stuck) {
            try {
                recoverChunk(chunk);
            } catch (Exception e) {
                logger.error("Falha ao recuperar chunk {}: {}", chunk.getId(), e.getMessage());
                markFailed(chunk, "Erro interno durante recuperacao do servidor.");
            }
        }
    }

    private void recoverChunk(Chunk chunk) {
        Long projectId = chunk.getProject().getId();
        Long chunkId = chunk.getId();

        if (chunk.getNodeodmTaskId() == null) {
            // Chunk nunca chegou ao NodeODM (estava QUEUED antes do shutdown)
            String msg = "Servidor desligado antes do inicio do processamento. "
                + "Clique em 'Tentar Novamente' para reprocessar.";
            markFailed(chunk, msg);
            logger.warn("Chunk {} (projeto {}) estava QUEUED sem tarefa ODM - marcado como FAILED.", chunkId, projectId);
            return;
        }

        // Chunk tinha uma tarefa no NodeODM — verificar o estado atual
        try {
            JsonNode status = nodeodmClient.getTaskStatus(chunk.getNodeodmTaskId());
            String odmStatus = status.has("status") ? status.get("status").asText() : "UNKNOWN";

            switch (odmStatus) {
                case "RUNNING", "QUEUED" -> {
                    // ODM ainda esta processando — retomar o polling
                    logger.info("Chunk {} ainda em execucao no NodeODM ({}%). Retomando polling.",
                        chunkId, status.has("progress") ? status.get("progress").asInt() : 0);
                    chunkService.resumePolling(chunkId, projectId, chunk.getNodeodmTaskId());
                }
                case "COMPLETED" -> {
                    // ODM terminou enquanto o servidor estava offline
                    logger.info("Chunk {} foi concluido no NodeODM durante o downtime. Finalizando.", chunkId);
                    chunkService.finalizeCompletedChunk(chunkId, projectId, chunk.getNodeodmTaskId());
                }
                case "FAILED" -> {
                    String odmError = status.has("last_error") ? status.get("last_error").asText() : null;
                    String msg = odmError != null
                        ? "Falha no processamento ODM: " + odmError + ". Clique em 'Tentar Novamente'."
                        : "Falha no processamento ODM. Clique em 'Tentar Novamente'.";
                    markFailed(chunk, msg);
                    logger.warn("Chunk {} falhou no ODM durante o downtime: {}", chunkId, odmError);
                }
                default -> {
                    String msg = "Servidor reiniciado durante o processamento (estava em "
                        + chunk.getProgress() + "%). Clique em 'Tentar Novamente'.";
                    markFailed(chunk, msg);
                }
            }
        } catch (Exception e) {
            // NodeODM nao retornou o status — provavelmente a tarefa foi perdida (restart completo do Docker)
            String msg = "Servidor reiniciado durante o processamento (estava em "
                + chunk.getProgress() + "%). Clique em 'Tentar Novamente'.";
            markFailed(chunk, msg);
            logger.warn("Chunk {} sem resposta do NodeODM apos restart. Marcado como FAILED.", chunkId);
        }
    }

    private void markFailed(Chunk chunk, String reason) {
        chunk.setStatus(Chunk.ChunkStatus.FAILED);
        chunk.setErrorMessage(reason);
        chunkRepository.save(chunk);

        Long projectId = chunk.getProject().getId();
        webSocketService.sendChunkFailed(projectId, chunk.getId(), reason);
    }
}
