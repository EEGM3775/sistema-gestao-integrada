package com.funcoesodm.javaservice.repository;

import com.funcoesodm.javaservice.model.Measurement;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface MeasurementRepository extends JpaRepository<Measurement, Long> {

    /** Todas as medições de um projeto */
    List<Measurement> findByProjectIdOrderByCreatedAtDesc(Long projectId);

    /** Medições de um chunk específico dentro de um projeto */
    List<Measurement> findByProjectIdAndChunkIdOrderByCreatedAtDesc(Long projectId, Long chunkId);

    /** Verificar se a medição pertence ao projeto (para validação de acesso) */
    Optional<Measurement> findByIdAndProjectId(Long id, Long projectId);

    /** Total de medições de um projeto */
    long countByProjectId(Long projectId);
}
