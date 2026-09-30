package com.funcoesodm.javaservice.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

public class MeasurementCreateRequestDto {

    @NotBlank(message = "Nome é obrigatório")
    private String name;

    @NotBlank(message = "Tipo é obrigatório (distance, area, volume, height)")
    private String type;

    @NotNull(message = "Valor é obrigatório")
    private Double value;

    @NotBlank(message = "Unidade é obrigatória")
    private String unit;

    @NotBlank(message = "Fonte de dados é obrigatória (orthophoto, dsm, dtm)")
    private String dataSource;

    /** Lista de coordenadas [[lat,lng], [lat,lng], ...] */
    private List<List<Double>> coordinates;

    // ─── Getters & Setters ──────────────────────────────────────────────────────

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
}
