package com.funcoesodm.javaservice.dto;

public class AnnotationUpdateRequestDto {
    private String text;
    private Boolean visible;

    public String getText() { return text; }
    public void setText(String text) { this.text = text; }

    public Boolean getVisible() { return visible; }
    public void setVisible(Boolean visible) { this.visible = visible; }
}
