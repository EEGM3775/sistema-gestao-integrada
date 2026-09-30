package com.funcoesodm.javaservice.repository;

import com.funcoesodm.javaservice.model.ProjectImage;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface ProjectImageRepository extends JpaRepository<ProjectImage, Long> {

    @Query("SELECT pi FROM ProjectImage pi LEFT JOIN FETCH pi.project WHERE pi.project.id = :projectId ORDER BY pi.uploadedAt DESC")
    List<ProjectImage> findByProjectId(@Param("projectId") Long projectId);

    @Query("SELECT COUNT(pi) FROM ProjectImage pi WHERE pi.project.id = :projectId")
    long countByProjectId(@Param("projectId") Long projectId);

    void deleteByProjectId(Long projectId);
}
