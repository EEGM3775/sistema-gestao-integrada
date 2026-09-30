package com.funcoesodm.javaservice.dto;

import com.funcoesodm.javaservice.model.Project;
import java.time.LocalDateTime;

public class ProjectResponseDto {
    private Long id;
    private String name;
    private String description;
    private Integer imageCount;
    private String status;
    private Long empreendimentoId;
    private Long obraId;
    private OwnerDto owner;
    private LocalDateTime createdAt;

    // Nested DTO for owner to avoid serialization issues
    public static class OwnerDto {
        private Long id;
        private String username;
        private String email;

        public OwnerDto() {}

        public OwnerDto(Long id, String username, String email) {
            this.id = id;
            this.username = username;
            this.email = email;
        }

        public Long getId() { return id; }
        public void setId(Long id) { this.id = id; }
        public String getUsername() { return username; }
        public void setUsername(String username) { this.username = username; }
        public String getEmail() { return email; }
        public void setEmail(String email) { this.email = email; }
    }

    public ProjectResponseDto() {}

    /**
     * Converts a Project entity to a ProjectResponseDto
     */
    public static ProjectResponseDto fromEntity(Project project) {
        ProjectResponseDto dto = new ProjectResponseDto();
        dto.setId(project.getId());
        dto.setName(project.getName());
        dto.setDescription(project.getDescription());
        dto.setImageCount(project.getImageCount());
        dto.setStatus(project.getStatus());
        dto.setEmpreendimentoId(project.getEmpreendimentoId());
        dto.setObraId(project.getObraId());
        dto.setCreatedAt(project.getCreatedAt());
        
        // Handle lazy loading of owner
        if (project.getOwner() != null) {
            dto.setOwner(new OwnerDto(
                project.getOwner().getId(),
                project.getOwner().getUsername(),
                project.getOwner().getEmail()
            ));
        }
        
        return dto;
    }

    // Getters and Setters
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
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

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Long getEmpreendimentoId() {
        return empreendimentoId;
    }

    public void setEmpreendimentoId(Long empreendimentoId) {
        this.empreendimentoId = empreendimentoId;
    }

    public Long getObraId() {
        return obraId;
    }

    public void setObraId(Long obraId) {
        this.obraId = obraId;
    }

    public OwnerDto getOwner() {
        return owner;
    }

    public void setOwner(OwnerDto owner) {
        this.owner = owner;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
