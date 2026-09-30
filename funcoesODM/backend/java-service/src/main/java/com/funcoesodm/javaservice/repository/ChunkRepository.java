package com.funcoesodm.javaservice.repository;

import com.funcoesodm.javaservice.model.Chunk;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface ChunkRepository extends JpaRepository<Chunk, Long> {

    @Query("SELECT c FROM Chunk c WHERE c.project.id = :projectId ORDER BY c.createdAt ASC")
    List<Chunk> findByProjectId(@Param("projectId") Long projectId);

    @Query("SELECT c FROM Chunk c WHERE c.project.id = :projectId AND c.id = :chunkId")
    Optional<Chunk> findByProjectIdAndChunkId(@Param("projectId") Long projectId, @Param("chunkId") Long chunkId);

    @Query("SELECT COUNT(c) FROM Chunk c WHERE c.project.id = :projectId")
    long countByProjectId(@Param("projectId") Long projectId);

    @Query("SELECT c FROM Chunk c WHERE c.status = :status")
    List<Chunk> findByStatus(@Param("status") Chunk.ChunkStatus status);

    @Query("SELECT c FROM Chunk c JOIN FETCH c.project WHERE c.status IN :statuses ORDER BY c.createdAt ASC")
    List<Chunk> findByStatusIn(@Param("statuses") List<Chunk.ChunkStatus> statuses);

    @Query("SELECT c FROM Chunk c WHERE c.nodeodmTaskId = :nodeodmTaskId")
    Optional<Chunk> findByNodeodmTaskId(@Param("nodeodmTaskId") String nodeodmTaskId);

    @Query("SELECT c FROM Chunk c WHERE c.project.id = :projectId AND c.status IN :statuses ORDER BY c.createdAt DESC")
    List<Chunk> findByProjectIdAndStatusIn(@Param("projectId") Long projectId, @Param("statuses") List<Chunk.ChunkStatus> statuses);

    void deleteByProjectId(Long projectId);
}
