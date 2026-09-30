package com.funcoesodm.javaservice.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class ChunkCreateRequestDto {
    
    @NotBlank(message = "Nome do chunk é obrigatório")
    @Size(min = 1, max = 255, message = "Nome deve ter entre 1 e 255 caracteres")
    private String name;
    
    @Size(max = 1000, message = "Descrição deve ter no máximo 1000 caracteres")
    private String description;

    public ChunkCreateRequestDto() {}

    public ChunkCreateRequestDto(String name, String description) {
        this.name = name;
        this.description = description;
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
}
