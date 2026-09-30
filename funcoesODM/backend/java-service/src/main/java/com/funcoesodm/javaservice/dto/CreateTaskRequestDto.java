package com.funcoesodm.javaservice.dto;

import java.util.Map;

/**
 * Request DTO for creating a new processing task
 */
public class CreateTaskRequestDto {

    private String name;
    private Map<String, Object> options;

    public CreateTaskRequestDto() {}

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Map<String, Object> getOptions() {
        return options;
    }

    public void setOptions(Map<String, Object> options) {
        this.options = options;
    }
}
