package com.funcoesodm.javaservice.controller;

import com.funcoesodm.javaservice.config.JwtUtil;
import com.funcoesodm.javaservice.dto.AuthRequest;
import com.funcoesodm.javaservice.dto.AuthResponse;
import com.funcoesodm.javaservice.dto.RegisterRequest;
import com.funcoesodm.javaservice.model.User;
import com.funcoesodm.javaservice.repository.UserRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import jakarta.validation.Valid;
import java.security.Principal;

/**
 * Autenticação local — APOSENTADA por padrão (a identidade é sempre da IAM).
 *
 * <p>Os endpoints de emissão de token ({@code /authenticate}, {@code /login},
 * {@code /register}) só respondem quando {@code app.auth.local-login-enabled=true}
 * (modo standalone, sem IAM). Em operação normal, o frontend recebe o token da
 * IAM e o injeta; este controller serve apenas o {@code /me}, que reflete a
 * identidade provisionada via JIT a partir do JWT da IAM.
 */
@RestController
@RequestMapping("/api/v1/auth")
public class AuthenticationController {

    private final AuthenticationManager authenticationManager;
    private final UserDetailsService userDetailsService;
    private final JwtUtil jwtUtil;
    private final UserRepository userRepository; // Inject UserRepository
    private final PasswordEncoder passwordEncoder; // Inject PasswordEncoder

    @Value("${app.auth.local-login-enabled:false}")
    private boolean localLoginEnabled;

    public AuthenticationController(AuthenticationManager authenticationManager,
                                    UserDetailsService userDetailsService,
                                    JwtUtil jwtUtil,
                                    UserRepository userRepository, // Add to constructor
                                    PasswordEncoder passwordEncoder) { // Add to constructor
        this.authenticationManager = authenticationManager;
        this.userDetailsService = userDetailsService;
        this.jwtUtil = jwtUtil;
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
    }

    @PostMapping("/authenticate")
    public ResponseEntity<?> authenticate(@RequestBody AuthRequest authRequest) {
        if (!localLoginEnabled) {
            return iamOnlyResponse();
        }
        Authentication authenticate = authenticationManager.authenticate(
                new UsernamePasswordAuthenticationToken(authRequest.getUsername(), authRequest.getPassword())
        );

        UserDetails userDetails = (UserDetails) authenticate.getPrincipal();
        String token = jwtUtil.generateToken(userDetails);

        User user = userRepository.findByUsername(userDetails.getUsername())
                .orElseThrow(() -> new RuntimeException("User not found"));
        AuthResponse.UserInfo userInfo = new AuthResponse.UserInfo(user.getId(), user.getUsername(), user.getEmail());

        return ResponseEntity.ok(new AuthResponse(token, userInfo));
    }

    // Alias para /authenticate - compatibilidade com frontend
    @PostMapping("/login")
    public ResponseEntity<?> login(@RequestBody AuthRequest authRequest) {
        return authenticate(authRequest);
    }

    @GetMapping("/me")
    public ResponseEntity<AuthResponse.UserInfo> getCurrentUser(Principal principal) {
        if (principal == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }
        User user = userRepository.findByUsername(principal.getName())
                .orElseThrow(() -> new RuntimeException("User not found"));
        return ResponseEntity.ok(new AuthResponse.UserInfo(user.getId(), user.getUsername(), user.getEmail()));
    }

    @PostMapping("/register")
    public ResponseEntity<?> registerUser(@RequestBody @Valid RegisterRequest registerRequest) {
        if (!localLoginEnabled) {
            return iamOnlyResponse();
        }
        if (userRepository.findByUsername(registerRequest.getUsername()).isPresent()) {
            return new ResponseEntity<>("Username is already taken!", HttpStatus.BAD_REQUEST);
        }
        if (userRepository.findByEmail(registerRequest.getEmail()).isPresent()) {
            return new ResponseEntity<>("Email is already in use!", HttpStatus.BAD_REQUEST);
        }

        // Create new user's account
        User user = new User();
        user.setUsername(registerRequest.getUsername());
        user.setEmail(registerRequest.getEmail());
        user.setPassword(passwordEncoder.encode(registerRequest.getPassword()));

        userRepository.save(user);

        return new ResponseEntity<>("User registered successfully!", HttpStatus.OK);
    }

    private ResponseEntity<?> iamOnlyResponse() {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body("Login local desabilitado. Autentique-se na IAM (SSO).");
    }
}
