package com.funcoesodm.javaservice.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * Represents the association between a Chunk and an Image.
 * An image can belong to multiple chunks (for flexibility),
 * and a chunk contains multiple images.
 */
@Entity
@Table(name = "chunk_images", indexes = {
    @Index(name = "idx_chunk_image_chunk_id", columnList = "chunk_id"),
    @Index(name = "idx_chunk_image_image_id", columnList = "image_id")
}, uniqueConstraints = {
    @UniqueConstraint(name = "uk_chunk_image", columnNames = {"chunk_id", "image_id"})
})
public class ChunkImage {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // Fase 8.5: tenant herdado do chunk-pai (defesa em profundidade).
    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "chunk_id", nullable = false)
    private Chunk chunk;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "image_id", nullable = false)
    private ProjectImage image;

    @Column(name = "added_at", nullable = false, updatable = false)
    private LocalDateTime addedAt;

    // Ordering within the chunk
    @Column(name = "sort_order")
    private Integer sortOrder = 0;

    @PrePersist
    protected void onCreate() {
        addedAt = LocalDateTime.now();
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

    public Chunk getChunk() {
        return chunk;
    }

    public void setChunk(Chunk chunk) {
        this.chunk = chunk;
    }

    public ProjectImage getImage() {
        return image;
    }

    public void setImage(ProjectImage image) {
        this.image = image;
    }

    public LocalDateTime getAddedAt() {
        return addedAt;
    }

    public Integer getSortOrder() {
        return sortOrder;
    }

    public void setSortOrder(Integer sortOrder) {
        this.sortOrder = sortOrder;
    }
}
