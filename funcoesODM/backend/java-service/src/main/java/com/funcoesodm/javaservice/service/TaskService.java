package com.funcoesodm.javaservice.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.funcoesodm.javaservice.client.NodeODMClient;
import com.funcoesodm.javaservice.model.ProcessingTask;
import com.funcoesodm.javaservice.model.Project;
import com.funcoesodm.javaservice.repository.ProcessingTaskRepository;
import com.funcoesodm.javaservice.repository.ProjectRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Service
public class TaskService {

    private final NodeODMClient nodeodmClient;
    private final ProjectRepository projectRepository;
    private final ProcessingTaskRepository processingTaskRepository;

    @Autowired
    public TaskService(NodeODMClient nodeodmClient, ProjectRepository projectRepository, ProcessingTaskRepository processingTaskRepository) {
        this.nodeodmClient = nodeodmClient;
        this.projectRepository = projectRepository;
        this.processingTaskRepository = processingTaskRepository;
    }

    @Transactional
    public ProcessingTask createTask(Long projectId, List<MultipartFile> images) {
        Project project = projectRepository.findById(projectId)
                .orElseThrow(() -> new RuntimeException("Project not found with id: " + projectId));

        List<byte[]> imageDataList = new ArrayList<>();
        List<String> imageNames = new ArrayList<>();

        for (MultipartFile image : images) {
            try {
                imageDataList.add(image.getBytes());
                imageNames.add(image.getOriginalFilename() != null ? image.getOriginalFilename() : "image.jpg");
            } catch (IOException e) {
                throw new RuntimeException("Failed to read image bytes", e);
            }
        }

        JsonNode odmTask = nodeodmClient.createTask(
                imageDataList,
                imageNames,
                "FuncoesODM_Task_" + projectId,
                null,
                null
        );

        if (odmTask == null || !odmTask.has("uuid")) {
            throw new RuntimeException("Failed to create task in NodeODM.");
        }

        ProcessingTask newTask = new ProcessingTask();
        newTask.setProject(project);
        newTask.setTenantId(project.getTenantId()); // Fase 8.5: tenant herdado do projeto-pai
        newTask.setNodeodmTaskId(odmTask.get("uuid").asText());
        // The status from NodeODM might be 'QUEUED' or similar. We'll start with PENDING
        // and could have a background job to update it.
        newTask.setStatus(ProcessingTask.Status.QUEUED);

        return processingTaskRepository.save(newTask);
    }
    
    @Transactional(readOnly = true)
    public List<ProcessingTask> getTasksByProjectId(Long projectId) {
        if (!projectRepository.existsById(projectId)) {
            throw new RuntimeException("Project not found with id: " + projectId);
        }
        return processingTaskRepository.findByProjectId(projectId);
    }
}
