package com.funcoesodm.javaservice.dto;

import com.funcoesodm.javaservice.model.ProjectImage;
import java.time.LocalDateTime;

public class ProjectImageDto {

    private Long id;
    private String filename;
    private String originalFilename;
    private String contentType;
    private Long fileSize;
    private LocalDateTime uploadedAt;
    private String thumbnailUrl;

    public ProjectImageDto() {}

    public static ProjectImageDto fromEntity(ProjectImage image) {
        ProjectImageDto dto = new ProjectImageDto();
        dto.setId(image.getId());
        dto.setFilename(image.getFilename());
        dto.setOriginalFilename(image.getOriginalFilename());
        dto.setContentType(image.getContentType());
        dto.setFileSize(image.getFileSize());
        dto.setUploadedAt(image.getUploadedAt());
        // Thumbnail URL will be set by service if available
        return dto;
    }

    // Getters and Setters
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getFilename() {
        return filename;
    }

    public void setFilename(String filename) {
        this.filename = filename;
    }

    public String getOriginalFilename() {
        return originalFilename;
    }

    public void setOriginalFilename(String originalFilename) {
        this.originalFilename = originalFilename;
    }

    public String getContentType() {
        return contentType;
    }

    public void setContentType(String contentType) {
        this.contentType = contentType;
    }

    public Long getFileSize() {
        return fileSize;
    }

    public void setFileSize(Long fileSize) {
        this.fileSize = fileSize;
    }

    public LocalDateTime getUploadedAt() {
        return uploadedAt;
    }

    public void setUploadedAt(LocalDateTime uploadedAt) {
        this.uploadedAt = uploadedAt;
    }

    public String getThumbnailUrl() {
        return thumbnailUrl;
    }

    public void setThumbnailUrl(String thumbnailUrl) {
        this.thumbnailUrl = thumbnailUrl;
    }
}
