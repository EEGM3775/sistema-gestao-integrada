package com.funcoesodm.javaservice.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "measurements", indexes = {
    @Index(name = "idx_measurement_project_id", columnList = "project_id"),
    @Index(name = "idx_measurement_tenant_id", columnList = "tenant_id"),
    @Index(name = "idx_measurement_chunk_id", columnList = "chunk_id"),
    @Index(name = "idx_measurement_created_at", columnList = "created_at")
})
public class Measurement {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // Fase 8.5: tenant herdado do projeto-pai (defesa em profundidade).
    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    /** Projeto ao qual esta medição pertence */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "project_id", nullable = false)
    private Project project;

    /**
     * ID do chunk (tarefa de processamento) ao qual esta medição pertence.
     * Opcional — pode ser nulo se a medição for feita na ortofoto sem chunk específico.
     */
    @Column(name = "chunk_id")
    private Long chunkId;

    /** Nome amigável dado pelo usuário (ex.: "Polígono 1", "Distância A-B") */
    @Column(nullable = false, length = 255)
    private String name;

    /** Tipo: distance | area | volume | height */
    @Column(nullable = false, length = 50)
    private String type;

    /** Valor numérico calculado */
    @Column(nullable = false)
    private Double value;

    /** Unidade (m, m², m³) */
    @Column(nullable = false, length = 20)
    private String unit;

    /** Fonte de dados: orthophoto | dsm | dtm */
    @Column(name = "data_source", nullable = false, length = 50)
    private String dataSource;

    /**
     * Coordenadas serializadas como JSON array de [lat, lng] ou [lat, lng, alt].
     * Ex.: [[lat1,lng1],[lat2,lng2],...]
     */
    @Column(name = "coordinates_json", columnDefinition = "TEXT")
    private String coordinatesJson;

    @Column(nullable = false)
    private boolean visible = true;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    // ─── Getters & Setters ──────────────────────────────────────────────────────

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }

    public Project getProject() { return project; }
    public void setProject(Project project) { this.project = project; }

    public Long getChunkId() { return chunkId; }
    public void setChunkId(Long chunkId) { this.chunkId = chunkId; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getType() { return type; }
    public void setType(String type) { this.type = type; }

    public Double getValue() { return value; }
    public void setValue(Double value) { this.value = value; }

    public String getUnit() { return unit; }
    public void setUnit(String unit) { this.unit = unit; }

    public String getDataSource() { return dataSource; }
    public void setDataSource(String dataSource) { this.dataSource = dataSource; }

    public String getCoordinatesJson() { return coordinatesJson; }
    public void setCoordinatesJson(String coordinatesJson) { this.coordinatesJson = coordinatesJson; }

    public boolean isVisible() { return visible; }
    public void setVisible(boolean visible) { this.visible = visible; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
