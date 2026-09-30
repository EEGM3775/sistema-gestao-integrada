package com.funcoesodm.javaservice.repository;

import com.funcoesodm.javaservice.model.ChunkImage;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface ChunkImageRepository extends JpaRepository<ChunkImage, Long> {

    @Query("SELECT ci FROM ChunkImage ci JOIN FETCH ci.image WHERE ci.chunk.id = :chunkId ORDER BY ci.sortOrder ASC, ci.addedAt ASC")
    List<ChunkImage> findByChunkId(@Param("chunkId") Long chunkId);

    @Query("SELECT ci FROM ChunkImage ci WHERE ci.image.id = :imageId")
    List<ChunkImage> findByImageId(@Param("imageId") Long imageId);

    @Query("SELECT COUNT(ci) FROM ChunkImage ci WHERE ci.chunk.id = :chunkId")
    long countByChunkId(@Param("chunkId") Long chunkId);

    @Query("SELECT ci FROM ChunkImage ci WHERE ci.chunk.id = :chunkId AND ci.image.id = :imageId")
    ChunkImage findByChunkIdAndImageId(@Param("chunkId") Long chunkId, @Param("imageId") Long imageId);

    @Query("SELECT ci FROM ChunkImage ci WHERE ci.chunk.id = :chunkId AND ci.image.id IN :imageIds")
    List<ChunkImage> findByChunkIdAndImageIds(@Param("chunkId") Long chunkId, @Param("imageIds") List<Long> imageIds);

    void deleteByChunkId(Long chunkId);

    void deleteByImageId(Long imageId);
}
