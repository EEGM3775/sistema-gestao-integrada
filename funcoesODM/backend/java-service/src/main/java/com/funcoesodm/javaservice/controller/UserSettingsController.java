package com.funcoesodm.javaservice.controller;

import com.funcoesodm.javaservice.dto.UpdateUploadLimitsRequestDto;
import com.funcoesodm.javaservice.dto.UploadLimitsDto;
import com.funcoesodm.javaservice.exception.UnauthorizedException;
import com.funcoesodm.javaservice.service.UploadLimitsService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.security.Principal;

@RestController
@RequestMapping("/api/v1/users/me")
public class UserSettingsController {

    private final UploadLimitsService uploadLimitsService;

    public UserSettingsController(UploadLimitsService uploadLimitsService) {
        this.uploadLimitsService = uploadLimitsService;
    }

    @GetMapping("/upload-limits")
    public ResponseEntity<UploadLimitsDto> getUploadLimits(Principal principal) {
        if (principal == null) {
            throw new UnauthorizedException("Usuário não autenticado");
        }
        UploadLimitsDto limits = uploadLimitsService.getLimitsForUser(principal.getName());
        return ResponseEntity.ok(limits);
    }

    @PutMapping("/upload-limits")
    public ResponseEntity<UploadLimitsDto> updateUploadLimits(
            @RequestBody UpdateUploadLimitsRequestDto request,
            Principal principal) {
        if (principal == null) {
            throw new UnauthorizedException("Usuário não autenticado");
        }
        UploadLimitsDto limits = uploadLimitsService.updateLimitsForUser(principal.getName(), request);
        return ResponseEntity.ok(limits);
    }
}
