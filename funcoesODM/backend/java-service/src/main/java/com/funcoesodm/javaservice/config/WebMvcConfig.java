package com.funcoesodm.javaservice.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Registro dos interceptors de MVC.
 *
 * <p>Fase 8.5: aplica o {@link ProjectTenantInterceptor} a toda rota sob
 * {@code /api/v1/projects/**}, impondo o isolamento de tenant na borda para os
 * recursos-filhos do drone.
 */
@Configuration
public class WebMvcConfig implements WebMvcConfigurer {

    private final ProjectTenantInterceptor projectTenantInterceptor;

    public WebMvcConfig(ProjectTenantInterceptor projectTenantInterceptor) {
        this.projectTenantInterceptor = projectTenantInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(projectTenantInterceptor)
                .addPathPatterns("/api/v1/projects/**");
    }
}
