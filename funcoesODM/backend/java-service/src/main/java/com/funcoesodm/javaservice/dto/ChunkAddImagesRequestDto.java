package com.funcoesodm.javaservice.dto;

import jakarta.validation.constraints.NotEmpty;
import java.util.List;

public class ChunkAddImagesRequestDto {
    
    @NotEmpty(message = "Lista de IDs de imagens não pode estar vazia")
    private List<Long> imageIds;

    public ChunkAddImagesRequestDto() {}

    public ChunkAddImagesRequestDto(List<Long> imageIds) {
        this.imageIds = imageIds;
    }

    public List<Long> getImageIds() {
        return imageIds;
    }

    public void setImageIds(List<Long> imageIds) {
        this.imageIds = imageIds;
    }
}
