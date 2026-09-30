package com.funcoesodm.javaservice.repository;

import com.funcoesodm.javaservice.model.ProcessingTask;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface ProcessingTaskRepository extends JpaRepository<ProcessingTask, Long> {
    
    List<ProcessingTask> findByProjectId(Long projectId);
    
    void deleteByProjectId(Long projectId);
    
    @Query("SELECT t FROM ProcessingTask t JOIN FETCH t.project WHERE t.id = :taskId")
    Optional<ProcessingTask> findByIdWithProject(@Param("taskId") Long taskId);
    
    @Query("SELECT t FROM ProcessingTask t WHERE t.status = :status ORDER BY t.createdAt ASC")
    List<ProcessingTask> findByStatus(@Param("status") ProcessingTask.Status status);
    
    @Query("SELECT t FROM ProcessingTask t WHERE t.status IN ('QUEUED', 'RUNNING') ORDER BY t.createdAt ASC")
    List<ProcessingTask> findPendingTasks();
    
    @Query("SELECT COUNT(t) FROM ProcessingTask t WHERE t.project.id = :projectId")
    long countByProjectId(@Param("projectId") Long projectId);

    @Query("SELECT t FROM ProcessingTask t WHERE t.project.id = :projectId AND t.status = :status ORDER BY t.createdAt DESC")
    List<ProcessingTask> findByProjectIdAndStatusOrderByCreatedAtDesc(@Param("projectId") Long projectId, @Param("status") ProcessingTask.Status status);
}
