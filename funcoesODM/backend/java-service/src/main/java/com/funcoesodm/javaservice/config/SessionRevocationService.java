package com.funcoesodm.javaservice.config;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import redis.clients.jedis.DefaultJedisClientConfig;
import redis.clients.jedis.HostAndPort;
import redis.clients.jedis.JedisClientConfig;
import redis.clients.jedis.JedisPooled;

import java.net.URI;

/**
 * Revogação imediata de sessão — lado <em>resource server</em> (Fase 10.6.5),
 * espelho do {@code nucleo.revocation} do ERP.
 *
 * <p>O access token é <em>stateless</em>: validado só por assinatura+{@code exp},
 * ele sobrevive à troca/reset de senha ou desativação do usuário até expirar (a
 * janela residual que um funcionário descontente exploraria). Para fechar isso, a
 * IAM grava um carimbo {@code sess:revoked_after:<user_id>=<epoch>} num Redis
 * compartilhado (DB 2, ver {@code identity.revocation}); aqui rejeitamos, por
 * requisição, todo access token cujo {@code iat} seja anterior ao carimbo do
 * usuário.
 *
 * <p><strong>FAIL-OPEN</strong> ({@code session.revocation.fail-open=true},
 * padrão): se o Redis não responder, NÃO bloqueia — a pior consequência é voltar
 * à janela de ≤ access TTL enquanto o Redis estiver fora, em vez de derrubar
 * TODA a autenticação do drone. Configurável para fail-closed onde contenção
 * importa mais que disponibilidade (ver docs/acesso-e-permissoes.md §5.1).
 */
@Service
public class SessionRevocationService {

    private static final Logger logger = LoggerFactory.getLogger(SessionRevocationService.class);

    // Circuit breaker: um Redis fora do ar pode custar segundos por chamada (a
    // resolução DNS do host parado NÃO é limitada pelo socket timeout). Sem isto,
    // uma queda do Redis deixaria TODA requisição autenticada lenta. Ao primeiro
    // erro abrimos o breaker por este período e respondemos pela política
    // fail-open/closed na hora, sem tocar no Redis — pagando só uma sondagem
    // lenta a cada cooldown, não uma por requisição.
    private static final long BREAKER_COOLDOWN_NANOS = 5_000_000_000L; // 5s
    private static final int SOCKET_TIMEOUT_MS = 250;

    @Value("${session.revocation.enabled:true}")
    boolean enabled;

    @Value("${session.revocation.fail-open:true}")
    boolean failOpen;

    @Value("${session.revoke.redis-url:redis://localhost:6379/2}")
    String redisUrl;

    @Value("${session.revoke.prefix:sess:revoked_after:}")
    String prefix;

    private volatile JedisPooled client;
    private volatile long breakerUntilNanos = 0L;

    /**
     * A sessão deste access token foi revogada? {@code true} → o caller deve
     * negar (não autenticar → 401 no {@code SecurityConfig}).
     *
     * <p>Compara o {@code iat} do token com o carimbo {@code revoked_after} do
     * usuário: emitido ANTES do carimbo ({@code iat < revoked_after}, estrito — o
     * token reemitido no mesmo instante para quem trocou a própria senha
     * sobrevive) → revogado. Ausência de carimbo → não revogado. Erro de Redis →
     * decisão degradada (fail-open/closed), com o circuit breaker evitando pagar
     * o custo do Redis fora em toda requisição.
     */
    public boolean isSessionRevoked(String userId, long iatSeconds) {
        if (!enabled) {
            return false;
        }
        if (userId == null || userId.isBlank() || iatSeconds <= 0) {
            return false;
        }
        if (System.nanoTime() < breakerUntilNanos) {
            // Breaker aberto: decide sem tocar no Redis (rápido).
            return degradedDecision();
        }
        String raw;
        try {
            raw = redisGet(prefix + userId);
        } catch (Exception e) { // Redis fora não pode quebrar a autenticação
            breakerUntilNanos = System.nanoTime() + BREAKER_COOLDOWN_NANOS;
            logger.warn("Redis indisponível na checagem de revogação; abrindo breaker por 5s; fail-{}.",
                    failOpen ? "open (permitindo)" : "closed (negando)");
            return degradedDecision();
        }
        if (raw == null) {
            return false;
        }
        try {
            long revokedAfter = Long.parseLong(raw.trim());
            return iatSeconds < revokedAfter;
        } catch (NumberFormatException e) {
            return false;
        }
    }

    // --- A sessão (sid) — fase 4 da remodelagem (§10.5 e §10.8, classe B) -------

    /** TTL da classe B: por quanto tempo a resposta sobre um sid vale sem o Redis. */
    private static final long SID_TTL_NANOS = 5_000_000_000L;
    /** Tamanho do motor (não teto de cliente): esvaziar custa uma ida ao Redis. */
    private static final int SIDS_LEMBRADOS = 10_000;

    @Value("${session.iam-internal-url:http://iam:8001}")
    String iamInternalUrl;

    private final java.util.concurrent.ConcurrentHashMap<String, long[]> sids =
            new java.util.concurrent.ConcurrentHashMap<>();
    private volatile java.net.http.HttpClient http;

    /**
     * A sessão deste access foi encerrada (logout, "encerrar todas", troca de
     * senha)? {@code true} → não autentica.
     *
     * <p>A regra da classe B, e não o fail-open do carimbo por época — espelho do
     * {@code nucleo.revocation.is_sid_revoked} do backend: Redis de pé responde na
     * hora; Redis fora serve o que foi visto há até 5 s e depois pergunta à IAM
     * ({@code /auth/interno/sessao/<sid>/}); IAM também fora → <strong>nega</strong>.
     * Token sem {@code sid} (anterior à fase 4, ou de serviço) não tem sessão a conferir.
     */
    public boolean isSidRevoked(String sid) {
        if (!enabled || sid == null || sid.isBlank()) {
            return false;
        }
        long agora = System.nanoTime();
        if (agora >= breakerUntilNanos) {
            try {
                boolean revogada = redisGet("sess:sid:" + sid) != null;
                lembrar(sid, agora, revogada);
                return revogada;
            } catch (Exception e) {
                breakerUntilNanos = agora + BREAKER_COOLDOWN_NANOS;
                logger.warn("Redis indisponível na checagem do sid; cache de 5s, depois a IAM.");
            }
        }
        long[] visto = sids.get(sid);
        if (visto != null && agora - visto[0] < SID_TTL_NANOS) {
            return visto[1] == 1L;
        }
        Boolean ativa = perguntarAIam(sid);
        if (ativa == null) {
            logger.warn("Nem o Redis nem a IAM responderam sobre o sid — nega.");
            return true;
        }
        lembrar(sid, agora, !ativa);
        return !ativa;
    }

    private void lembrar(String sid, long agora, boolean revogada) {
        if (sids.size() >= SIDS_LEMBRADOS) {
            sids.clear();
        }
        sids.put(sid, new long[]{agora, revogada ? 1L : 0L});
    }

    /** A IAM é a autoridade das sessões: ativa?, ou {@code null} quando ela não responde. */
    protected Boolean perguntarAIam(String sid) {
        try {
            java.net.http.HttpClient c = http;
            if (c == null) {
                c = java.net.http.HttpClient.newBuilder()
                        .connectTimeout(java.time.Duration.ofSeconds(1)).build();
                http = c;
            }
            java.net.http.HttpRequest req = java.net.http.HttpRequest.newBuilder(
                            URI.create(iamInternalUrl.replaceAll("/+$", "") + "/auth/interno/sessao/" + sid + "/"))
                    .timeout(java.time.Duration.ofSeconds(1)).GET().build();
            java.net.http.HttpResponse<String> resp = c.send(req, java.net.http.HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() == 404) {
                return false; // não é um sid (a rota só aceita UUID)
            }
            if (resp.statusCode() != 200) {
                return null;
            }
            return resp.body().replace(" ", "").contains("\"ativa\":true");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return null;
        } catch (Exception e) {
            return null;
        }
    }

    /**
     * Decisão quando o Redis está indisponível: fail-open → não revoga
     * ({@code false}, permite); fail-closed → revoga ({@code true}, nega).
     */
    private boolean degradedDecision() {
        return !failOpen;
    }

    /** GET isolado (sobrescrito em teste para exercitar a lógica sem Redis real). */
    protected String redisGet(String key) {
        return client().get(key);
    }

    /**
     * Cliente Jedis preguiçoso, com timeouts curtos e sem retry (a checagem roda
     * em toda requisição autenticada; falha rápido para o breaker assumir). O
     * pool não conecta na criação — a 1ª falha aparece no {@code get}, não aqui.
     */
    private JedisPooled client() {
        JedisPooled c = client;
        if (c == null) {
            synchronized (this) {
                c = client;
                if (c == null) {
                    URI uri = URI.create(redisUrl);
                    int port = uri.getPort() > 0 ? uri.getPort() : 6379;
                    int db = 0;
                    String path = uri.getPath();
                    if (path != null && path.length() > 1) {
                        try {
                            db = Integer.parseInt(path.substring(1));
                        } catch (NumberFormatException ignore) {
                            // mantém DB 0
                        }
                    }
                    JedisClientConfig cfg = DefaultJedisClientConfig.builder()
                            .socketTimeoutMillis(SOCKET_TIMEOUT_MS)
                            .connectionTimeoutMillis(SOCKET_TIMEOUT_MS)
                            .database(db)
                            .build();
                    c = new JedisPooled(new HostAndPort(uri.getHost(), port), cfg);
                    client = c;
                }
            }
        }
        return c;
    }

    @PreDestroy
    void close() {
        if (client != null) {
            try {
                client.close();
            } catch (Exception ignore) {
                // encerramento best-effort
            }
        }
    }
}
