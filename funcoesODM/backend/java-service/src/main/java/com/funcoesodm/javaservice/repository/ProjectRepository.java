package com.funcoesodm.javaservice.repository;

import com.funcoesodm.javaservice.model.Project;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface ProjectRepository extends JpaRepository<Project, Long> {

    @Query("SELECT p FROM Project p JOIN FETCH p.owner")
    List<Project> findAllWithOwner();

    @Query("SELECT p FROM Project p JOIN FETCH p.owner WHERE p.id = :id")
    Optional<Project> findByIdWithOwner(Long id);

    // ----- Variantes escopadas por tenant (isolamento multi-tenant) -----

    @Query("SELECT p FROM Project p JOIN FETCH p.owner WHERE p.tenantId = :tenantId")
    List<Project> findAllWithOwnerByTenantId(@Param("tenantId") String tenantId);

    @Query("SELECT p FROM Project p JOIN FETCH p.owner WHERE p.id = :id AND p.tenantId = :tenantId")
    Optional<Project> findByIdAndTenantIdWithOwner(@Param("id") Long id, @Param("tenantId") String tenantId);

    /**
     * Fase 8.5: usado pelo {@code ProjectTenantInterceptor} para autorizar, na
     * borda, qualquer rota {@code /api/v1/projects/{projectId}/**} — o projeto da
     * URL precisa pertencer ao tenant do token, senão a request vira 404.
     */
    boolean existsByIdAndTenantId(Long id, String tenantId);

    // ----- Vínculo com o ERP (Fase 3): filtrar por empreendimento/obra -----

    @Query("SELECT p FROM Project p JOIN FETCH p.owner "
            + "WHERE p.tenantId = :tenantId AND p.empreendimentoId = :empreendimentoId")
    List<Project> findAllWithOwnerByTenantIdAndEmpreendimentoId(
            @Param("tenantId") String tenantId,
            @Param("empreendimentoId") Long empreendimentoId);

    @Query("SELECT p FROM Project p JOIN FETCH p.owner "
            + "WHERE p.tenantId = :tenantId AND p.obraId = :obraId")
    List<Project> findAllWithOwnerByTenantIdAndObraId(
            @Param("tenantId") String tenantId,
            @Param("obraId") Long obraId);

    // ----- Reconciliação cross-DB (soft-unlink de órfãos), escopada ao tenant -----

    @Modifying
    @Query("UPDATE Project p SET p.empreendimentoId = null "
            + "WHERE p.tenantId = :tenantId AND p.empreendimentoId = :empreendimentoId")
    int unlinkEmpreendimento(@Param("tenantId") String tenantId,
                             @Param("empreendimentoId") Long empreendimentoId);

    @Modifying
    @Query("UPDATE Project p SET p.obraId = null "
            + "WHERE p.tenantId = :tenantId AND p.obraId = :obraId")
    int unlinkObra(@Param("tenantId") String tenantId, @Param("obraId") Long obraId);
}
