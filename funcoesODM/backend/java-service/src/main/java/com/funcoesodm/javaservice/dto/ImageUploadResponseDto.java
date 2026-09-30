package com.funcoesodm.javaservice.dto;

import java.util.List;

public class ImageUploadResponseDto {

    private int totalUploaded;
    private int totalFailed;
    private List<ProjectImageDto> images;
    private List<String> errors;

    public ImageUploadResponseDto() {}

    public ImageUploadResponseDto(int totalUploaded, int totalFailed, 
                                   List<ProjectImageDto> images, List<String> errors) {
        this.totalUploaded = totalUploaded;
        this.totalFailed = totalFailed;
        this.images = images;
        this.errors = errors;
    }

    // Getters and Setters
    public int getTotalUploaded() {
        return totalUploaded;
    }

    public void setTotalUploaded(int totalUploaded) {
        this.totalUploaded = totalUploaded;
    }

    public int getTotalFailed() {
        return totalFailed;
    }

    public void setTotalFailed(int totalFailed) {
        this.totalFailed = totalFailed;
    }

    public List<ProjectImageDto> getImages() {
        return images;
    }

    public void setImages(List<ProjectImageDto> images) {
        this.images = images;
    }

    public List<String> getErrors() {
        return errors;
    }

    public void setErrors(List<String> errors) {
        this.errors = errors;
    }
}
