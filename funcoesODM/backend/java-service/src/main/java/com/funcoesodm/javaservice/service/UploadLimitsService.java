package com.funcoesodm.javaservice.service;

import com.funcoesodm.javaservice.dto.UpdateUploadLimitsRequestDto;
import com.funcoesodm.javaservice.dto.UploadLimitsDto;
import com.funcoesodm.javaservice.model.User;
import com.funcoesodm.javaservice.model.UserUploadLimits;
import com.funcoesodm.javaservice.repository.UserRepository;
import com.funcoesodm.javaservice.repository.UserUploadLimitsRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UploadLimitsService {

    private final UserRepository userRepository;
    private final UserUploadLimitsRepository uploadLimitsRepository;

    private final int defaultMaxFileSizeMb;
    private final int defaultMaxRequestSizeMb;
    private final int hardMaxFileSizeMb;
    private final int hardMaxRequestSizeMb;

    public UploadLimitsService(UserRepository userRepository,
                               UserUploadLimitsRepository uploadLimitsRepository,
                               @Value("${app.upload.default-max-file-mb:100}") int defaultMaxFileSizeMb,
                               @Value("${app.upload.default-max-request-mb:500}") int defaultMaxRequestSizeMb,
                               @Value("${app.upload.hard-max-file-mb:5120}") int hardMaxFileSizeMb,
                               @Value("${app.upload.hard-max-request-mb:20480}") int hardMaxRequestSizeMb) {
        this.userRepository = userRepository;
        this.uploadLimitsRepository = uploadLimitsRepository;
        this.defaultMaxFileSizeMb = defaultMaxFileSizeMb;
        this.defaultMaxRequestSizeMb = defaultMaxRequestSizeMb;
        this.hardMaxFileSizeMb = hardMaxFileSizeMb;
        this.hardMaxRequestSizeMb = hardMaxRequestSizeMb;
    }

    @Transactional(readOnly = true)
    public UploadLimitsDto getLimitsForUser(String username) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new IllegalArgumentException("Usuário não encontrado"));

        UserUploadLimits limits = uploadLimitsRepository.findByUserId(user.getId())
                .orElseGet(() -> createDefaultLimits(user));

        return toDto(limits);
    }

    @Transactional
    public UploadLimitsDto updateLimitsForUser(String username, UpdateUploadLimitsRequestDto request) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new IllegalArgumentException("Usuário não encontrado"));

        UserUploadLimits limits = uploadLimitsRepository.findByUserId(user.getId())
                .orElseGet(() -> createDefaultLimits(user));

        int maxFileSize = sanitize(request.getMaxFileSizeMb(), defaultMaxFileSizeMb, hardMaxFileSizeMb, "maxFileSizeMb");
        int maxRequestSize = sanitize(request.getMaxRequestSizeMb(), defaultMaxRequestSizeMb, hardMaxRequestSizeMb, "maxRequestSizeMb");

        if (maxRequestSize < maxFileSize) {
            throw new IllegalArgumentException("maxRequestSizeMb deve ser maior ou igual a maxFileSizeMb");
        }

        limits.setMaxFileSizeMb(maxFileSize);
        limits.setMaxRequestSizeMb(maxRequestSize);
        uploadLimitsRepository.save(limits);

        return toDto(limits);
    }

    @Transactional(readOnly = true)
    public long getMaxFileSizeBytesForUser(String username) {
        UploadLimitsDto limits = getLimitsForUser(username);
        return limits.getMaxFileSizeMb().longValue() * 1024L * 1024L;
    }

    @Transactional(readOnly = true)
    public long getMaxRequestSizeBytesForUser(String username) {
        UploadLimitsDto limits = getLimitsForUser(username);
        return limits.getMaxRequestSizeMb().longValue() * 1024L * 1024L;
    }

    private int sanitize(Integer value, int fallback, int maxAllowed, String field) {
        int sanitized = value == null ? fallback : value;
        if (sanitized <= 0) {
            throw new IllegalArgumentException(field + " deve ser maior que zero");
        }
        if (maxAllowed > 0 && sanitized > maxAllowed) {
            throw new IllegalArgumentException(field + " excede o limite máximo permitido (" + maxAllowed + "MB)");
        }
        return sanitized;
    }

    private UserUploadLimits createDefaultLimits(User user) {
        UserUploadLimits limits = new UserUploadLimits();
        limits.setUser(user);
        limits.setMaxFileSizeMb(defaultMaxFileSizeMb);
        limits.setMaxRequestSizeMb(defaultMaxRequestSizeMb);
        return uploadLimitsRepository.save(limits);
    }

    private UploadLimitsDto toDto(UserUploadLimits limits) {
        UploadLimitsDto dto = new UploadLimitsDto();
        dto.setMaxFileSizeMb(limits.getMaxFileSizeMb());
        dto.setMaxRequestSizeMb(limits.getMaxRequestSizeMb());
        dto.setHardMaxFileSizeMb(hardMaxFileSizeMb);
        dto.setHardMaxRequestSizeMb(hardMaxRequestSizeMb);
        return dto;
    }
}
