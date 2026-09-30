package com.funcoesodm.javaservice.config;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Lógica de decisão da revogação imediata de sessão (Fase 10.6.5), exercitada
 * sem Redis real: a subclasse injeta a resposta do Redis (ou uma exceção). Prova
 * o contrato do espelho do {@code nucleo.revocation} do ERP: comparação estrita
 * {@code iat < revoked_after}, ausência de carimbo = não revoga, e a degradação
 * fail-open (permite) / fail-closed (nega) quando o Redis cai.
 */
class SessionRevocationServiceTest {

    /** Subclasse que injeta a resposta do Redis (ou uma exceção) sem Redis real. */
    private static class FakeRevocationService extends SessionRevocationService {
        volatile String raw;
        volatile RuntimeException boom;
        volatile Boolean iamDiz = Boolean.TRUE;
        volatile int perguntasAIam;

        @Override
        protected Boolean perguntarAIam(String sid) {
            perguntasAIam++;
            return iamDiz;
        }

        @Override
        protected String redisGet(String key) {
            if (boom != null) {
                throw boom;
            }
            return raw;
        }
    }

    private FakeRevocationService service(boolean enabled, boolean failOpen) {
        FakeRevocationService s = new FakeRevocationService();
        s.enabled = enabled;
        s.failOpen = failOpen;
        s.prefix = "sess:revoked_after:";
        s.redisUrl = "redis://localhost:6379/2";
        return s;
    }

    @Test
    void semCarimbo_naoRevoga() {
        FakeRevocationService s = service(true, true);
        s.raw = null;
        assertFalse(s.isSessionRevoked("42", 1_000_000L));
    }

    @Test
    void iatAnteriorAoCarimbo_revoga() {
        FakeRevocationService s = service(true, true);
        s.raw = "2000";
        assertTrue(s.isSessionRevoked("42", 1999L));
    }

    @Test
    void iatIgualOuPosterior_naoRevoga() {
        FakeRevocationService s = service(true, true);
        s.raw = "2000";
        assertFalse(s.isSessionRevoked("42", 2000L)); // estrito: reemitido no mesmo instante sobrevive
        assertFalse(s.isSessionRevoked("42", 2001L));
    }

    @Test
    void desabilitado_naoRevoga() {
        FakeRevocationService s = service(false, true);
        s.raw = "9999999999";
        assertFalse(s.isSessionRevoked("42", 1L));
    }

    @Test
    void redisFora_failOpen_permite() {
        FakeRevocationService s = service(true, true);
        s.boom = new RuntimeException("connection refused");
        assertFalse(s.isSessionRevoked("42", 1L));
    }

    @Test
    void redisFora_failClosed_nega() {
        FakeRevocationService s = service(true, false);
        s.boom = new RuntimeException("connection refused");
        assertTrue(s.isSessionRevoked("42", 1L));
    }

    @Test
    void semUserIdOuIat_naoRevoga() {
        // Mesmo fail-closed, sem identidade/`iat` no token não há o que revogar.
        FakeRevocationService s = service(true, false);
        s.raw = "9999999999";
        assertFalse(s.isSessionRevoked(null, 1L));
        assertFalse(s.isSessionRevoked("", 1L));
        assertFalse(s.isSessionRevoked("42", 0L));
    }

    // --- sid (fase 4, classe B) ------------------------------------------------

    @Test
    void sid_semMarcaNoRedis_valeENaoPerguntaAIam() {
        FakeRevocationService s = service(true, true);
        s.raw = null;
        assertFalse(s.isSidRevoked("s1"));
        assertTrue(s.perguntasAIam == 0);
    }

    @Test
    void sid_marcadoNoRedis_revogado() {
        FakeRevocationService s = service(true, true);
        s.raw = "1";
        assertTrue(s.isSidRevoked("s1"));
    }

    @Test
    void sid_redisFora_perguntaAIam_eNegaSeElaTambemCair() {
        FakeRevocationService s = service(true, true);  // o fail-open da época não vale para o sid
        s.boom = new RuntimeException("connection refused");
        s.iamDiz = Boolean.TRUE;
        assertFalse(s.isSidRevoked("s-ativa"));
        s.iamDiz = Boolean.FALSE;
        assertTrue(s.isSidRevoked("s-encerrada"));
        s.iamDiz = null;
        assertTrue(s.isSidRevoked("s-ninguem-responde"));
    }

    @Test
    void semSid_naoHaSessaoAConferir() {
        FakeRevocationService s = service(true, false);
        s.raw = "1";
        assertFalse(s.isSidRevoked(null));
        assertFalse(s.isSidRevoked(""));
    }
}
