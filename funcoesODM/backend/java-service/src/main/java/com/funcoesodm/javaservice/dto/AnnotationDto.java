package com.funcoesodm.javaservice.dto;

import com.funcoesodm.javaservice.model.Annotation;
import java.time.LocalDateTime;

public class AnnotationDto {

    private Long id;
    private Long projectId;
    private AuthorDto author;
    private String type;
    private String coordinatesJson;
    private String text;
    private boolean visible;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public static class AuthorDto {
        private final Long id;
        private final String username;

        public AuthorDto(Long id, String username) {
            this.id = id;
            this.username = username;
        }

        public Long getId() { return id; }
        public String getUsername() { return username; }
    }

    public static AnnotationDto fromEntity(Annotation a) {
        AnnotationDto dto = new AnnotationDto();
        dto.id            = a.getId();
        dto.projectId     = a.getProject().getId();
        dto.author        = new AuthorDto(a.getUser().getId(), a.getUser().getUsername());
        dto.type          = a.getType();
        dto.coordinatesJson = a.getCoordinatesJson();
        dto.text          = a.getText();
        dto.visible       = a.isVisible();
        dto.createdAt     = a.getCreatedAt();
        dto.updatedAt     = a.getUpdatedAt();
        return dto;
    }

    // ─── Getters ────────────────────────────────────────────────────────────────

    public Long getId() { return id; }
    public Long getProjectId() { return projectId; }
    public AuthorDto getAuthor() { return author; }
    public String getType() { return type; }
    public String getCoordinatesJson() { return coordinatesJson; }
    public String getText() { return text; }
    public boolean isVisible() { return visible; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
}
