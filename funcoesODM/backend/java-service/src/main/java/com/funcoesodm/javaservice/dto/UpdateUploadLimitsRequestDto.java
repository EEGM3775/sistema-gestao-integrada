package com.funcoesodm.javaservice.dto;

public class UpdateUploadLimitsRequestDto {
    private Integer maxFileSizeMb;
    private Integer maxRequestSizeMb;

    public Integer getMaxFileSizeMb() {
        return maxFileSizeMb;
    }

    public void setMaxFileSizeMb(Integer maxFileSizeMb) {
        this.maxFileSizeMb = maxFileSizeMb;
    }

    public Integer getMaxRequestSizeMb() {
        return maxRequestSizeMb;
    }

    public void setMaxRequestSizeMb(Integer maxRequestSizeMb) {
        this.maxRequestSizeMb = maxRequestSizeMb;
    }
}
