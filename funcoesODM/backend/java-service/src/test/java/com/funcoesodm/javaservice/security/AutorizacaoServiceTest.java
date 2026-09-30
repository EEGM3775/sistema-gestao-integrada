package com.funcoesodm.javaservice.security;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * O PEP do drone (D205), sem Redis nem SpiceDB reais: a subclasse troca os dois.
 * Prova quem decide (claim × PDP), o cache com as chaves do backend e o modo de
 * falha da classe A — PDP fora sem cache nega; Redis fora pergunta direto.
 */
class AutorizacaoServiceTest {

    private static final String T = "t1";
    private static final String U = "u1";

    private static class Falso extends AutorizacaoService {
        final Map<String, String> redis = new HashMap<>();
        boolean redisFora;
        Boolean respostaDoPdp = Boolean.TRUE;
        int perguntasAoPdp;
        String ultimoZedtoken;

        Falso() {
            spicedbUrl = "http://spicedb:8443";
            spicedbChave = "k";
            spicedbTimeoutMs = 300;
        }

        @Override
        protected String redisGet(String chave) {
            if (redisFora) throw new RuntimeException("redis fora");
            return redis.get(chave);
        }

        @Override
        protected List<String> redisMget(String... chaves) {
            if (redisFora) throw new RuntimeException("redis fora");
            List<String> r = new ArrayList<>();
            Arrays.stream(chaves).forEach(c -> r.add(redis.get(c)));
            return r;
        }

        @Override
        protected void redisSetex(String chave, int ttl, String valor) {
            if (redisFora) throw new RuntimeException("redis fora");
            redis.put(chave, valor);
        }

        @Override
        protected Boolean checarNoPdp(String tipo, String id, String permissao, String usuarioId, String zedtoken) {
            perguntasAoPdp++;
            ultimoZedtoken = zedtoken;
            assertEquals("modulo_drone", tipo);
            assertEquals("usa", permissao);
            return respostaDoPdp;
        }
    }

    @Test
    void tokenEnxuto_decidePeloPdp() {
        Falso s = new Falso();
        assertTrue(s.usaModulo(T, U, null, false, "drone"));
        s.respostaDoPdp = false;
        s.redis.clear();
        assertFalse(s.usaModulo(T, U, null, false, "drone"));
    }

    @Test
    void comAClaimEModoToken_decidePelaClaim() {
        Falso s = new Falso();
        s.respostaDoPdp = false;
        assertTrue(s.usaModulo(T, U, List.of("drone"), false, "drone"));
        assertEquals(0, s.perguntasAoPdp);
    }

    @Test
    void moduloVirado_decidePeloPdpMesmoComAClaim() {
        Falso s = new Falso();
        s.redis.put("authz:modo:drone", "pdp");
        s.respostaDoPdp = false;
        assertFalse(s.usaModulo(T, U, List.of("drone"), false, "drone"));
        assertEquals(1, s.perguntasAoPdp);
    }

    @Test
    void tokenDeServico_decidePelaClaim() {
        Falso s = new Falso();
        s.respostaDoPdp = false;
        assertTrue(s.usaModulo(T, null, List.of("drone"), true, "drone"));
        assertEquals(0, s.perguntasAoPdp);
    }

    @Test
    void cacheComAsChavesDoBackend_eVersaoNovaInvalida() {
        Falso s = new Falso();
        s.redis.put("authz:v:g", "1");
        s.redis.put("authz:v:t:t1", "4");
        s.redis.put("authz:zed:t1", "Z");
        assertTrue(s.usaModulo(T, U, null, false, "drone"));
        assertEquals("1", s.redis.get("authz:d:t1:u1:1.4.0:m:drone"));
        assertEquals("Z", s.ultimoZedtoken);

        assertTrue(s.usaModulo(T, U, null, false, "drone"));
        assertEquals(1, s.perguntasAoPdp, "a segunda resposta vem do cache");

        s.redis.put("authz:v:u:t1:u1", "1");  // a IAM mexeu nesta pessoa
        s.respostaDoPdp = false;
        assertFalse(s.usaModulo(T, U, null, false, "drone"));
        assertEquals(2, s.perguntasAoPdp);
    }

    @Test
    void pdpForaSemCache_nega() {
        Falso s = new Falso();
        s.respostaDoPdp = null;
        assertFalse(s.usaModulo(T, U, null, false, "drone"));
    }

    @Test
    void redisFora_perguntaDiretoAoPdp() {
        Falso s = new Falso();
        s.redisFora = true;
        assertTrue(s.usaModulo(T, U, null, false, "drone"));
        assertEquals(1, s.perguntasAoPdp);
    }

    @Test
    void semRelogioDoPdp_nega() {
        Falso s = new Falso();
        s.spicedbTimeoutMs = 0;
        assertFalse(s.usaModulo(T, U, null, false, "drone"));
        assertEquals(0, s.perguntasAoPdp);
    }

    @Test
    void chaveSemTenant_eRecusada() {
        assertThrows(IllegalArgumentException.class,
                () -> AutorizacaoService.chaveDeDecisao("", U, null, null, null, "m:drone"));
    }
}
