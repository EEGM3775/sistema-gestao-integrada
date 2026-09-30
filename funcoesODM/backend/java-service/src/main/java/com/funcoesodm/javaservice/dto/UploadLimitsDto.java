package com.funcoesodm.javaservice.dto;

public class UploadLimitsDto {
    private Integer maxFileSizeMb;
    private Integer maxRequestSizeMb;
    private Integer hardMaxFileSizeMb;
    private Integer hardMaxRequestSizeMb;

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

    public Integer getHardMaxFileSizeMb() {
        return hardMaxFileSizeMb;
    }

    public void setHardMaxFileSizeMb(Integer hardMaxFileSizeMb) {
        this.hardMaxFileSizeMb = hardMaxFileSizeMb;
    }

    public Integer getHardMaxRequestSizeMb() {
        return hardMaxRequestSizeMb;
    }

    public void setHardMaxRequestSizeMb(Integer hardMaxRequestSizeMb) {
        this.hardMaxRequestSizeMb = hardMaxRequestSizeMb;
    }
}
