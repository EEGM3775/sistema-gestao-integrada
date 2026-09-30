package com.funcoesodm.javaservice.dto;

import com.funcoesodm.javaservice.model.Measurement;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

public class MeasurementDto {

    private Long id;
    private Long projectId;
    private Long chunkId;
    private String name;
    private String type;
    private Double value;
    private String unit;
    private String dataSource;
    /** Coordenadas deserializadas: lista de [lat, lng] ou [lat, lng, alt] */
    private List<List<Double>> coordinates;
    private boolean visible;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    private static final ObjectMapper objectMapper = new ObjectMapper();

    public MeasurementDto() {}

    public static MeasurementDto fromEntity(Measurement m) {
        MeasurementDto dto = new MeasurementDto();
        dto.setId(m.getId());
        dto.setProjectId(m.getProject().getId());
        dto.setChunkId(m.getChunkId());
        dto.setName(m.getName());
        dto.setType(m.getType());
        dto.setValue(m.getValue());
        dto.setUnit(m.getUnit());
        dto.setDataSource(m.getDataSource());
        dto.setVisible(m.isVisible());
        dto.setCreatedAt(m.getCreatedAt());
        dto.setUpdatedAt(m.getUpdatedAt());

        if (m.getCoordinatesJson() != null && !m.getCoordinatesJson().isEmpty()) {
            try {
                dto.setCoordinates(objectMapper.readValue(
                    m.getCoordinatesJson(),
                    new TypeReference<List<List<Double>>>() {}
                ));
            } catch (JsonProcessingException e) {
                dto.setCoordinates(new ArrayList<>());
            }
        } else {
            dto.setCoordinates(new ArrayList<>());
        }

        return dto;
    }

    // ─── Getters & Setters ──────────────────────────────────────────────────────

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getProjectId() { return projectId; }
    public void setProjectId(Long projectId) { this.projectId = projectId; }

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

    public List<List<Double>> getCoordinates() { return coordinates; }
    public void setCoordinates(List<List<Double>> coordinates) { this.coordinates = coordinates; }

    public boolean isVisible() { return visible; }
    public void setVisible(boolean visible) { this.visible = visible; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
