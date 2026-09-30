package com.funcoesodm.javaservice.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * Fase 8.5 — retrocompatibilidade do {@code tenant_id} nas entidades-filhas.
 *
 * <p>O schema é gerido por {@code hibernate.ddl-auto=update}. Numa base nova, as
 * tabelas nascem com {@code tenant_id NOT NULL} (via {@code CREATE TABLE}). Numa
 * base já existente, o Hibernate adiciona a coluna como <em>nullable</em> (um
 * {@code ALTER ADD COLUMN NOT NULL} sem default falharia com linhas presentes),
 * deixando as linhas antigas com {@code tenant_id} nulo.
 *
 * <p>Este runner roda no start (depois do {@code ddl-auto}) e:
 * <ol>
 *   <li>preenche {@code tenant_id} das linhas-filhas a partir do projeto/chunk-pai;</li>
 *   <li>quando não sobra nenhum nulo, promove a coluna a {@code NOT NULL} — a
 *       3ª camada de isolamento no próprio banco, espelhando o que a Fase 8.2 fez
 *       no ERP.</li>
 * </ol>
 * É idempotente e nunca derruba o start: cada passo é tolerante a falha (uma
 * coluna que continue com nulos — ex.: projeto legado sem tenant — apenas registra
 * aviso e segue).
 */
@Component
@Order(0)
public class TenantBackfillRunner implements ApplicationRunner {

    private static final Logger logger = LoggerFactory.getLogger(TenantBackfillRunner.class);

    /** Backfill a partir do projeto-pai (project_id → projects.tenant_id). */
    private static final List<String> CHILD_TABLES_VIA_PROJECT = List.of(
            "chunks", "processing_tasks", "measurements", "annotations", "project_images");

    private final JdbcTemplate jdbc;

    public TenantBackfillRunner(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void run(ApplicationArguments args) {
        // 1) Filhos diretos do projeto.
        for (String table : CHILD_TABLES_VIA_PROJECT) {
            backfill(table,
                    "UPDATE " + table + " c SET tenant_id = p.tenant_id "
                            + "FROM projects p WHERE c.project_id = p.id AND c.tenant_id IS NULL");
        }
        // 2) chunk_images herda do chunk-pai (que já foi preenchido acima).
        backfill("chunk_images",
                "UPDATE chunk_images ci SET tenant_id = c.tenant_id "
                        + "FROM chunks c WHERE ci.chunk_id = c.id AND ci.tenant_id IS NULL");

        // 3) Promove a coluna a NOT NULL onde já não há nulos (defesa em profundidade no banco).
        for (String table : CHILD_TABLES_VIA_PROJECT) {
            enforceNotNull(table);
        }
        enforceNotNull("chunk_images");
    }

    private void backfill(String table, String sql) {
        try {
            int n = jdbc.update(sql);
            if (n > 0) {
                logger.info("Fase 8.5 backfill: {} linha(s) de '{}' receberam tenant_id do pai", n, table);
            }
        } catch (Exception e) {
            // Tabela ainda inexistente ou outra particularidade → não impede o start.
            logger.warn("Fase 8.5 backfill de '{}' ignorado: {}", table, e.getMessage());
        }
    }

    private void enforceNotNull(String table) {
        try {
            Integer nulls = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM " + table + " WHERE tenant_id IS NULL", Integer.class);
            if (nulls != null && nulls > 0) {
                logger.warn("Fase 8.5: '{}' ainda tem {} linha(s) sem tenant_id — NOT NULL adiado "
                        + "(investigar projeto/pai órfão)", table, nulls);
                return;
            }
            jdbc.execute("ALTER TABLE " + table + " ALTER COLUMN tenant_id SET NOT NULL");
        } catch (Exception e) {
            logger.warn("Fase 8.5: não foi possível impor NOT NULL em '{}': {}", table, e.getMessage());
        }
    }
}
