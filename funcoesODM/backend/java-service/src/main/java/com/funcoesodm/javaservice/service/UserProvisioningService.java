package com.funcoesodm.javaservice.service;

import com.funcoesodm.javaservice.model.User;
import com.funcoesodm.javaservice.repository.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * JIT (just-in-time) provisioning do usuário local a partir das claims da IAM.
 *
 * <p>A IAM é a única autoridade de identidade; o funcoesODM não cria mais
 * usuários por conta própria. Na primeira requisição autenticada de um usuário,
 * garantimos uma linha local em {@code users} (espelho), preservando as FKs
 * existentes ({@code projects.owner_id}, anotações, etc.) e gravando o
 * {@code tenant_id} para o isolamento multi-tenant.
 */
@Service
public class UserProvisioningService {

    private static final Logger logger = LoggerFactory.getLogger(UserProvisioningService.class);

    // Senha-placeholder: a coluna é NOT NULL, mas nunca é usada para login
    // (a autenticação é sempre via IAM). Não é um hash válido de bcrypt.
    private static final String IAM_MANAGED_PASSWORD = "IAM_MANAGED";

    private final UserRepository userRepository;

    public UserProvisioningService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Transactional
    public User provision(String username, String email, String tenantId) {
        String safeEmail = (email == null || email.isBlank())
                ? username + "@iam.local"
                : email;

        User user = userRepository.findByUsername(username).orElse(null);
        if (user == null) {
            user = new User();
            user.setUsername(username);
            user.setEmail(safeEmail);
            user.setPassword(IAM_MANAGED_PASSWORD);
            user.setTenantId(tenantId);
            logger.info("JIT provisioning: novo usuário '{}' (tenant {})", username, tenantId);
            return userRepository.save(user);
        }

        // Reconcilia claims voláteis (email/tenant podem ter mudado na IAM).
        boolean dirty = false;
        if (tenantId != null && !tenantId.equals(user.getTenantId())) {
            user.setTenantId(tenantId);
            dirty = true;
        }
        if (email != null && !email.isBlank() && !email.equals(user.getEmail())) {
            user.setEmail(email);
            dirty = true;
        }
        return dirty ? userRepository.save(user) : user;
    }
}
