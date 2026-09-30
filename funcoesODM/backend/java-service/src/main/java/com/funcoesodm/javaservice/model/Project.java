package com.funcoesodm.javaservice.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "projects")
public class Project {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(length = 1000)
    private String description;
    

    @Column(name = "image_count")
    private Integer imageCount = 0;

    @Column(name = "status")
    private String status = "pending";

    // Fronteira de tenant (UUID da IAM em texto). Toda query de projeto é
    // filtrada por este campo para garantir o isolamento entre clientes.
    @Column(name = "tenant_id")
    private String tenantId;

    // Vínculo (cross-DB, sem FK) com o ERP: id da Obra e do Empreendimento aos
    // quais este projeto de drone pertence. Nullable: um projeto pode existir
    // solto (criado fora do contexto de uma obra). A reconciliação de órfãos
    // (exclusão da obra/empreendimento no ERP) faz soft-unlink destes campos.
    @Column(name = "empreendimento_id")
    private Long empreendimentoId;

    @Column(name = "obra_id")
    private Long obraId;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "owner_id", nullable = false)
    private User owner;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }

    // Standard getters and setters
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
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


    public Integer getImageCount() {
        return imageCount;
    }

    public void setImageCount(Integer imageCount) {
        this.imageCount = imageCount;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getTenantId() {
        return tenantId;
    }

    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
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

    public User getOwner() {
        return owner;
    }

    public void setOwner(User owner) {
        this.owner = owner;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
