package com.funcoesodm.javaservice.repository;

import com.funcoesodm.javaservice.model.UserUploadLimits;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface UserUploadLimitsRepository extends JpaRepository<UserUploadLimits, Long> {
    Optional<UserUploadLimits> findByUserId(Long userId);
}
