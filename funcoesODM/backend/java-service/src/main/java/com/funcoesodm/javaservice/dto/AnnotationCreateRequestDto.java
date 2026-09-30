package com.funcoesodm.javaservice.dto;

public class AnnotationCreateRequestDto {

    private String type;
    private String coordinatesJson;
    private String text;

    public String getType() { return type; }
    public void setType(String type) { this.type = type; }

    public String getCoordinatesJson() { return coordinatesJson; }
    public void setCoordinatesJson(String coordinatesJson) { this.coordinatesJson = coordinatesJson; }

    public String getText() { return text; }
    public void setText(String text) { this.text = text; }
}
