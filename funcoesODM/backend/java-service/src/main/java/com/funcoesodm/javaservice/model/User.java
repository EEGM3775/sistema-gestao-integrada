package com.funcoesodm.javaservice.model;

import jakarta.persistence.*;

@Entity
@Table(name = "users") // Use 'users' as table name to avoid conflict with 'user' keyword in some DBs
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String username;

    @Column(nullable = false)
    private String password;

    @Column(nullable = false, unique = true)
    private String email;

    // Tenant da IAM ao qual o usuário pertence (UUID em texto). Preenchido via
    // JIT provisioning a partir das claims do token. Nullable para tolerar linhas
    // legadas; usuários provisionados pela IAM sempre o têm.
    @Column(name = "tenant_id")
    private String tenantId;

    // Standard getters and setters
    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
