package com.funcoesodm.javaservice.dto;

public class ProjectCreateRequestDto {
    private String name;
    private String description;
    // Vínculo opcional com o ERP (cross-DB): obra/empreendimento de origem.
    private Long empreendimentoId;
    private Long obraId;

    // Getters and Setters
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
}
