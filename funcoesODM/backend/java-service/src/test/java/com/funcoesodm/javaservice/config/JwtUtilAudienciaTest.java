package com.funcoesodm.javaservice.config;

import io.jsonwebtoken.JwtBuilder;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.security.Keys;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Fase 5 da remodelagem (acesso-e-permissoes.md §10.6): o drone só aceita o que a
 * IAM emitiu para ele — {@code aud} {@code sgi-drone}, {@code iss} {@code sgi-iam}
 * e {@code typ} de pessoa ({@code at+jwt}) ou de serviço ({@code svc+jwt}). O
 * token de serviço só entra na rota de desvínculo, e só com o escopo dela.
 */
class JwtUtilAudienciaTest {

    private static final String SEGREDO = "segredo-de-teste-com-mais-de-32-bytes-de-largura!!";

    private JwtUtil util;

    @BeforeEach
    void preparar() {
        util = new JwtUtil();
        ReflectionTestUtils.setField(util, "SECRET_KEY", SEGREDO);
        ReflectionTestUtils.setField(util, "issuer", "sgi-iam");
        ReflectionTestUtils.setField(util, "audience", "sgi-drone");
    }

    private JwtBuilder base(String tipo, Object aud) {
        JwtBuilder b = Jwts.builder()
                .setSubject("ana")
                .setIssuer("sgi-iam")
                .claim("aud", aud)
                .claim("tenant_id", "t1")
                .setIssuedAt(new Date())
                .setExpiration(new Date(System.currentTimeMillis() + 300_000))
                .signWith(Keys.hmacShaKeyFor(SEGREDO.getBytes(StandardCharsets.UTF_8)), SignatureAlgorithm.HS256);
        if (tipo != null) {
            b.setHeaderParam("typ", tipo);
        }
        return b;
    }

    @Test
    void oAccessDePessoaParaODroneEntra() {
        String token = base("at+jwt", "sgi-drone").compact();
        assertTrue(util.isTokenValid(token));
        assertFalse(util.isServiceToken(token));
        assertEquals("ana", util.extractUsername(token));
    }

    @Test
    void oAccessDeOutroServicoNaoEntra() {
        assertFalse(util.isTokenValid(base("at+jwt", "sgi-api").compact()));
        assertFalse(util.isTokenValid(base("at+jwt", "sgi-iam").compact()));
        assertFalse(util.isTokenValid(base("at+jwt", "sgi").compact()));
    }

    @Test
    void aVoltaAtrasComTodasAsAudienciasEntra() {
        assertTrue(util.isTokenValid(base("at+jwt", List.of("sgi-api", "sgi-drone", "sgi-iam")).compact()));
    }

    @Test
    void outroEmissorNaoEntra() {
        String token = base("at+jwt", "sgi-drone").setIssuer("intruso").compact();
        assertFalse(util.isTokenValid(token));
    }

    @Test
    void semTipoNaoEntra() {
        assertFalse(util.isTokenValid(base(null, "sgi-drone").compact()));
        assertFalse(util.isTokenValid(base("JWT", "sgi-drone").compact()));
    }

    @Test
    void oTokenDeServicoSeReconhecePeloTipo() {
        String token = base("svc+jwt", "sgi-drone").claim("scope", "drone.projetos.desvincular").compact();
        assertTrue(util.isTokenValid(token));
        assertTrue(util.isServiceToken(token));
        assertEquals("drone.projetos.desvincular", util.extractScope(token));
    }

    @Test
    void oServicoSoEntraNaRotaDoEscopoDele() {
        String escopo = "drone.projetos.desvincular";
        assertTrue(JwtAuthenticationFilter.servicoPodeAqui("DELETE", "/api/v1/projects/links/obra/7", escopo));
        assertFalse(JwtAuthenticationFilter.servicoPodeAqui("GET", "/api/v1/projects/links/obra/7", escopo));
        assertFalse(JwtAuthenticationFilter.servicoPodeAqui("DELETE", "/api/v1/projects/7", escopo));
        assertFalse(JwtAuthenticationFilter.servicoPodeAqui("DELETE", "/api/v1/projects/links/obra/7", "outro"));
        assertFalse(JwtAuthenticationFilter.servicoPodeAqui("DELETE", "/api/v1/projects/links/obra/7", null));
    }

    @Test
    void oTokenDoModoIsoladoSaiComOContratoDaFase5() {
        ReflectionTestUtils.setField(util, "EXPIRATION_TIME", 60_000L);
        String token = util.generateToken(
                org.springframework.security.core.userdetails.User.withUsername("local").password("x").roles("U").build());
        assertTrue(util.isTokenValid(token));
    }
}
