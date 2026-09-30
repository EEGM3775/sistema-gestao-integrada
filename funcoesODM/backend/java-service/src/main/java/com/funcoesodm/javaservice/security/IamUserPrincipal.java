package com.funcoesodm.javaservice.security;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

/**
 * Identidade vinda do JWT da IAM, materializada no contexto de segurança.
 *
 * <p>Implementa {@link UserDetails} para que {@code principal.getName()} continue
 * retornando o username (compatível com os controllers existentes), mas carrega
 * também o {@code tenantId} e os {@code modules} (entitlements) extraídos do token.
 * Cada módulo vira uma authority {@code MODULE_<código>} — é assim que o
 * {@code SecurityConfig} exige o entitlement {@code drone}.
 */
public class IamUserPrincipal implements UserDetails {

    public static final String MODULE_AUTHORITY_PREFIX = "MODULE_";

    private final String username;
    private final String email;
    private final String tenantId;
    private final String tenantSlug;
    private final List<String> modules;
    private final List<GrantedAuthority> authorities;

    public IamUserPrincipal(String username, String email, String tenantId,
                            String tenantSlug, List<String> modules) {
        this.username = username;
        this.email = email;
        this.tenantId = tenantId;
        this.tenantSlug = tenantSlug;
        this.modules = modules == null ? List.of() : List.copyOf(modules);
        this.authorities = this.modules.stream()
                .filter(Objects::nonNull)
                .map(m -> new SimpleGrantedAuthority(MODULE_AUTHORITY_PREFIX + m))
                .collect(Collectors.toUnmodifiableList());
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getTenantSlug() {
        return tenantSlug;
    }

    public String getEmail() {
        return email;
    }

    public List<String> getModules() {
        return modules;
    }

    public boolean hasModule(String moduleCode) {
        return modules.contains(moduleCode);
    }

    // ----- UserDetails -----

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getPassword() {
        return null; // sem senha local — a autenticação é sempre da IAM
    }

    @Override
    public String getUsername() {
        return username;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return true;
    }
}
