package com.funcoesodm.javaservice.controller;

import com.funcoesodm.javaservice.model.ProcessingTask;
import com.funcoesodm.javaservice.service.TaskService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

/**
 * Legacy TaskController - creates tasks with direct image upload to NodeODM
 * Use ProcessingTaskController for the new queue-based processing
 */
@RestController
@RequestMapping("/api/v1/projects/{projectId}/odm-tasks")
public class TaskController {

    private final TaskService taskService;

    @Autowired
    public TaskController(TaskService taskService) {
        this.taskService = taskService;
    }

    /**
    * Create task with direct image upload to NodeODM
     * @deprecated Use POST /api/v1/projects/{projectId}/tasks with ProcessingTaskController
     */
    @PostMapping
    public ResponseEntity<ProcessingTask> createTask(
            @PathVariable Long projectId,
            @RequestParam("images") List<MultipartFile> images) {
        
        ProcessingTask createdTask = taskService.createTask(projectId, images);
        return ResponseEntity.ok(createdTask);
    }
    
    @GetMapping
    public ResponseEntity<List<ProcessingTask>> getTasksForProject(@PathVariable Long projectId) {
        List<ProcessingTask> tasks = taskService.getTasksByProjectId(projectId);
        return ResponseEntity.ok(tasks);
    }
}