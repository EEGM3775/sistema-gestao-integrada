package com.funcoesodm.javaservice.config;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jws;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.security.Keys;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.stereotype.Component;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;
import java.util.Collection;
import java.util.Collections;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * Validação dos JWTs emitidos pela IAM (SSO).
 *
 * <p>O funcoesODM passou a ser um <em>resource server</em> da IAM: ele apenas
 * valida a assinatura (HS256 com segredo compartilhado — {@code JWT_SECRET}) e
 * lê as claims da plataforma ({@code tenant_id}, {@code modules}, ...). A geração
 * local de tokens só é usada no modo standalone (ver
 * {@code app.auth.local-login-enabled}). Migração para RS256/JWKS na Fase 5.
 */
@Component
public class JwtUtil {

    private static final Logger logger = LoggerFactory.getLogger(JwtUtil.class);

    // Segredo HS256 (compat / modo standalone). Opcional quando há RS256.
    @Value("${jwt.secret:}")
    private String SECRET_KEY;

    // Usado apenas pela emissão local (modo standalone). Default de 10h.
    @Value("${jwt.expiration:36000000}")
    private long EXPIRATION_TIME;

    // Fase 5: caminho da chave PÚBLICA RSA da IAM (PEM). Quando presente, valida
    // RS256 (assimétrico) — o drone só conhece a pública, nunca pode forjar token.
    @Value("${jwt.public-key-path:}")
    private String publicKeyPath;

    private PublicKey rsaPublicKey;

    // Fase 5 da remodelagem (§10.6): o drone só aceita o que foi emitido PARA ele.
    // Os valores são os de `funcoesautorizacao/audiencias.py` (o teste da IAM
    // cobra que batem com os defaults daqui).
    @Value("${jwt.issuer:sgi-iam}")
    private String issuer;

    @Value("${jwt.audience:sgi-drone}")
    private String audience;

    /** {@code typ} do access de pessoa (RFC 9068) e do token de serviço. */
    public static final String TIPO_PESSOA = "at+jwt";
    public static final String TIPO_SERVICO = "svc+jwt";

    @PostConstruct
    void loadPublicKey() {
        if (publicKeyPath == null || publicKeyPath.isBlank()) {
            logger.info("JWT: validação HS256 (segredo compartilhado).");
            return;
        }
        try {
            String pem = Files.readString(Path.of(publicKeyPath))
                    .replace("-----BEGIN PUBLIC KEY-----", "")
                    .replace("-----END PUBLIC KEY-----", "")
                    .replaceAll("\\s", "");
            byte[] der = Base64.getDecoder().decode(pem);
            rsaPublicKey = KeyFactory.getInstance("RSA")
                    .generatePublic(new X509EncodedKeySpec(der));
            logger.info("JWT: validação RS256 via chave pública {}.", publicKeyPath);
        } catch (Exception e) {
            logger.error("Falha ao carregar a chave pública RSA ({}): {}", publicKeyPath, e.getMessage());
        }
    }

    // ----- Leitura de claims -----

    public String extractUsername(String token) {
        return extractClaim(token, Claims::getSubject);
    }

    public Date extractExpiration(String token) {
        return extractClaim(token, Claims::getExpiration);
    }

    public String extractEmail(String token) {
        return extractClaim(token, claims -> claims.get("email", String.class));
    }

    public String extractTenantId(String token) {
        return extractClaim(token, claims -> claims.get("tenant_id", String.class));
    }

    public String extractTenantSlug(String token) {
        return extractClaim(token, claims -> claims.get("tenant_slug", String.class));
    }

    /**
     * ID numérico do usuário na IAM (claim {@code user_id}, padrão do SimpleJWT),
     * como texto — é a chave do carimbo de revogação {@code sess:revoked_after:<user_id>}.
     * {@code null} se ausente.
     */
    public String extractUserId(String token) {
        return extractClaim(token, claims -> {
            Object raw = claims.get("user_id");
            return raw == null ? null : String.valueOf(raw);
        });
    }

    /** Emissão do token ({@code iat}) em segundos epoch; {@code 0} se ausente. */
    public long extractIssuedAtSeconds(String token) {
        Date iat = extractClaim(token, Claims::getIssuedAt);
        return iat == null ? 0L : iat.getTime() / 1000L;
    }

    /**
     * Entitlements de módulo (ex.: {@code ["erp_financeiro", "drone"]}), ou
     * {@code null} quando o token não traz a claim — o token enxuto da fase 4,
     * em que quem responde é o PDP ({@code AutorizacaoService}).
     */
    @SuppressWarnings("unchecked")
    public List<String> extractModules(String token) {
        return extractClaim(token, claims -> {
            Object raw = claims.get("modules");
            if (raw == null) {
                return null;
            }
            if (raw instanceof List<?>) {
                return (List<String>) raw;
            }
            return Collections.<String>emptyList();
        });
    }

    /** A sessão ({@code sid}, fase 4) — {@code null} em token anterior a ela ou de serviço. */
    public String extractSid(String token) {
        return extractClaim(token, claims -> {
            Object raw = claims.get("sid");
            return raw == null ? null : String.valueOf(raw);
        });
    }

    /**
     * Token serviço→serviço — não representa uma pessoa. Desde a fase 5 é o
     * {@code typ} do cabeçalho que diz ({@code svc+jwt}), e não uma claim.
     */
    public boolean isServiceToken(String token) {
        return TIPO_SERVICO.equals(parse(token).getHeader().getType());
    }

    /** O escopo do token de serviço ({@code scope}); {@code null} no de pessoa. */
    public String extractScope(String token) {
        return extractClaim(token, claims -> claims.get("scope", String.class));
    }

    public <T> T extractClaim(String token, Function<Claims, T> claimsResolver) {
        final Claims claims = extractAllClaims(token);
        return claimsResolver.apply(claims);
    }

    private Claims extractAllClaims(String token) {
        return parse(token).getBody();
    }

    /**
     * Assinatura, {@code exp}, emissor, audiência e tipo — o que o drone exige
     * de todo token. A audiência pode vir como texto ou como lista (a volta atrás
     * da fase 5 emite um token para todos os serviços): basta conter a do drone.
     */
    private Jws<Claims> parse(String token) {
        Jws<Claims> jws = Jwts.parserBuilder().setSigningKey(getVerifyKey())
                .requireIssuer(issuer).build().parseClaimsJws(token);
        Object aud = jws.getBody().get("aud");
        boolean audOk = audience.equals(aud)
                || (aud instanceof Collection<?> lista && lista.contains(audience));
        if (!audOk) {
            throw new JwtException("Token emitido para outra audiência: " + aud);
        }
        String tipo = jws.getHeader().getType();
        if (!TIPO_PESSOA.equals(tipo) && !TIPO_SERVICO.equals(tipo)) {
            throw new JwtException("Tipo de token não aceito: " + tipo);
        }
        return jws;
    }

    /** Chave de VALIDAÇÃO: pública RSA (RS256) se carregada; senão o segredo HMAC. */
    private Key getVerifyKey() {
        return rsaPublicKey != null ? rsaPublicKey : getSignKey();
    }

    private Boolean isTokenExpired(String token) {
        return extractExpiration(token).before(new Date());
    }

    /**
     * Valida assinatura + expiração de um token da IAM, sem precisar de um
     * {@code UserDetails} local (a identidade vem do próprio token).
     */
    public boolean isTokenValid(String token) {
        try {
            return !isTokenExpired(token);
        } catch (Exception e) {
            logger.debug("Token inválido: {}", e.getMessage());
            return false;
        }
    }

    // ----- Emissão local (apenas modo standalone) -----

    public String generateToken(UserDetails userDetails) {
        Map<String, Object> claims = new HashMap<>();
        return createToken(claims, userDetails.getUsername());
    }

    private String createToken(Map<String, Object> claims, String userName) {
        return Jwts.builder()
                .setHeaderParam("typ", TIPO_PESSOA)
                .setClaims(claims)
                .setIssuer(issuer)
                .setAudience(audience)
                .setSubject(userName)
                .setIssuedAt(new Date(System.currentTimeMillis()))
                .setExpiration(new Date(System.currentTimeMillis() + EXPIRATION_TIME))
                .signWith(getSignKey(), SignatureAlgorithm.HS256).compact();
    }

    public Boolean validateToken(String token, UserDetails userDetails) {
        final String username = extractUsername(token);
        return (username.equals(userDetails.getUsername()) && !isTokenExpired(token));
    }

    private Key getSignKey() {
        // O segredo é usado como bytes UTF-8 diretamente (mesmo esquema da IAM/simplejwt).
        byte[] keyBytes = SECRET_KEY.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        return Keys.hmacShaKeyFor(keyBytes);
    }
}
