package com.funcoesodm.javaservice.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "chunks", indexes = {
    @Index(name = "idx_chunk_project_id", columnList = "project_id"),
    @Index(name = "idx_chunk_tenant_id", columnList = "tenant_id"),
    @Index(name = "idx_chunk_status", columnList = "status"),
    @Index(name = "idx_chunk_created_at", columnList = "created_at")
})
public class Chunk {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // Fase 8.5: fronteira de tenant materializada na própria linha (defesa em
    // profundidade). Herdada do projeto-pai na criação; o isolamento é imposto
    // na borda pelo ProjectTenantInterceptor a partir do projectId da URL.
    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "project_id", nullable = false)
    private Project project;

    @Column(nullable = false, length = 255)
    private String name;

    @Column(length = 1000)
    private String description;

    @Column(name = "image_count")
    private Integer imageCount = 0;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ChunkStatus status = ChunkStatus.EMPTY;

    // Processing options stored as JSON
    @Column(name = "processing_options", columnDefinition = "TEXT")
    private String processingOptions;

    // Reference to NodeODM task if processing
    @Column(name = "nodeodm_task_id")
    private String nodeodmTaskId;

    // Processing progress (0-100)
    @Column(nullable = false)
    private Integer progress = 0;

    // Processing outputs (JSON with available outputs)
    @Column(columnDefinition = "TEXT")
    private String outputs;

    // Error message if processing failed
    @Column(name = "error_message", columnDefinition = "TEXT")
    private String errorMessage;

    // Processing time in seconds
    @Column(name = "processing_time")
    private Long processingTime;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @Column(name = "started_at")
    private LocalDateTime startedAt;

    @Column(name = "completed_at")
    private LocalDateTime completedAt;

    @OneToMany(mappedBy = "chunk", cascade = CascadeType.ALL, orphanRemoval = true, fetch = FetchType.LAZY)
    private List<ChunkImage> chunkImages = new ArrayList<>();

    public enum ChunkStatus {
        EMPTY,           // No images
        READY,           // Has images, ready to process
        QUEUED,          // Queued for processing
        RUNNING,         // Processing in progress
        COMPLETED,       // Processing completed successfully
        FAILED,          // Processing failed
        CANCELED         // Processing was canceled
    }

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    // Getters and Setters
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    public Project getProject() {
        return project;
    }

    public void setProject(Project project) {
        this.project = project;
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

    public ChunkStatus getStatus() {
        return status;
    }

    public void setStatus(ChunkStatus status) {
        this.status = status;
    }

    public String getProcessingOptions() {
        return processingOptions;
    }

    public void setProcessingOptions(String processingOptions) {
        this.processingOptions = processingOptions;
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

    public Long getProcessingTime() {
        return processingTime;
    }

    public void setProcessingTime(Long processingTime) {
        this.processingTime = processingTime;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
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

    public List<ChunkImage> getChunkImages() {
        return chunkImages;
    }

    public void setChunkImages(List<ChunkImage> chunkImages) {
        this.chunkImages = chunkImages;
    }

    public void addImage(ChunkImage image) {
        chunkImages.add(image);
        image.setChunk(this);
    }

    public void removeImage(ChunkImage image) {
        chunkImages.remove(image);
        image.setChunk(null);
    }
}
