package com.funcoesodm.javaservice.dto;

import jakarta.validation.constraints.Size;

public class ChunkUpdateRequestDto {
    
    @Size(min = 1, max = 255, message = "Nome deve ter entre 1 e 255 caracteres")
    private String name;
    
    @Size(max = 1000, message = "Descrição deve ter no máximo 1000 caracteres")
    private String description;

    public ChunkUpdateRequestDto() {}

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
}
