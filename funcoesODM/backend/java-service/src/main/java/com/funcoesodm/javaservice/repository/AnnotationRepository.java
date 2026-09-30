package com.funcoesodm.javaservice.repository;

import com.funcoesodm.javaservice.model.Annotation;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface AnnotationRepository extends JpaRepository<Annotation, Long> {

    @Query("SELECT a FROM Annotation a JOIN FETCH a.user WHERE a.project.id = :projectId ORDER BY a.createdAt DESC")
    List<Annotation> findByProjectIdWithUser(@Param("projectId") Long projectId);

    Optional<Annotation> findByIdAndProjectId(Long id, Long projectId);
}
