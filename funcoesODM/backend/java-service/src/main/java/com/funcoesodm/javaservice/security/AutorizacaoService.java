package com.funcoesodm.javaservice.security;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
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
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * O "pode?" do drone — o PEP da remodelagem da segurança (D205,
 * docs/acesso-e-permissoes.md §10.3, princípio 2: "o equivalente no drone").
 *
 * <p>O drone faz uma pergunta só: <em>esta pessoa usa o módulo {@code drone}
 * nesta empresa?</em> É a mesma pergunta {@code m:drone} do backend
 * ({@code nucleo/autorizacao.py}), com a mesma tradução para o schema
 * ({@code modulo_drone:<tenant>#usa}), as mesmas chaves de Redis
 * ({@code funcoesautorizacao/chaves.py}) e o mesmo modo de falha da classe A
 * (§10.8). A decisão cacheada por um serve ao outro, de propósito.
 *
 * <p><strong>Quem decide.</strong> O PDP, quando o token não traz a lista de
 * módulos (o token enxuto da fase 4) ou quando o módulo foi virado para o PDP
 * ({@code manage.py modo_autorizacao drone pdp} grava {@code authz:modo:drone} no
 * Redis). Senão, a claim {@code modules}, como sempre. Token de serviço decide
 * pela claim — é outro tipo de token (fase 5).
 *
 * <p><strong>Modo de falha</strong> (classe A): Redis fora → pergunta direto ao
 * PDP; PDP fora → serve o que ainda estiver no cache e, sem cache, <strong>nega</strong>.
 */
@Service
public class AutorizacaoService {

    private static final Logger logger = LoggerFactory.getLogger(AutorizacaoService.class);

    /** Formato das chaves — espelho de {@code funcoesautorizacao/chaves.py}. */
    static final String PREFIXO = "authz";
    static final String VERSAO_GLOBAL = PREFIXO + ":v:g";

    /** TTL da classe A (§10.8, {@code funcoesautorizacao/classes.py}). Não é teto (§5.6). */
    static final int TTL_CLASSE_A_S = 60;
    /** Quanto o processo confia na leitura do modo — o mesmo do backend. */
    static final long MODO_TTL_NANOS = 5_000_000_000L;
    private static final long REDIS_PAUSA_NANOS = 5_000_000_000L;
    private static final int REDIS_TIMEOUT_MS = 250;

    public static final String TOKEN = "token";
    public static final String PDP = "pdp";

    @Value("${authz.spicedb.url:}")
    String spicedbUrl;

    @Value("${authz.spicedb.chave:}")
    String spicedbChave;

    /**
     * O relógio da pergunta — {@code AUTORIZACAO_PDP_TIMEOUT_MS} do
     * {@code payment/planos.py}, pelo arquivo gerado. Sem ele (0), o PDP é tratado
     * como não configurado: nega, e diz por quê no log.
     */
    @Value("${authz.spicedb.timeout-ms:0}")
    int spicedbTimeoutMs;

    @Value("${authz.redis-url:redis://localhost:6379/5}")
    String redisUrl;

    private final ObjectMapper json = new ObjectMapper();
    private volatile HttpClient http;
    private volatile JedisPooled redis;
    private volatile long redisParadoAte = 0L;
    private final Map<String, Object[]> modos = new java.util.concurrent.ConcurrentHashMap<>();

    /**
     * A pessoa usa o módulo nesta empresa?
     *
     * @param modulosDoToken a claim {@code modules}, ou {@code null} quando o
     *                       token não a traz (token enxuto)
     * @param servico        token de serviço — decide sempre pela claim
     */
    public boolean usaModulo(String tenantId, String usuarioId, List<String> modulosDoToken,
                             boolean servico, String modulo) {
        if (servico || usuarioId == null || usuarioId.isBlank() || tenantId == null || tenantId.isBlank()) {
            return modulosDoToken != null && modulosDoToken.contains(modulo);
        }
        if (modulosDoToken != null && TOKEN.equals(modoDoModulo(modulo))) {
            return modulosDoToken.contains(modulo);
        }
        return decidirNoPdp(tenantId, usuarioId, modulo);
    }

    /** O que {@code authz:modo:<módulo>} diz; sem PDP configurado, sempre o token. */
    String modoDoModulo(String modulo) {
        if (spicedbUrl == null || spicedbUrl.isBlank()) {
            return TOKEN;
        }
        long agora = System.nanoTime();
        Object[] guardado = modos.get(modulo);
        if (guardado != null && agora - (long) guardado[1] < MODO_TTL_NANOS) {
            return (String) guardado[0];
        }
        // Sem o Redis, vale o modo que se conhecia; sem nenhum, o token.
        String modo = guardado != null ? (String) guardado[0] : TOKEN;
        if (agora >= redisParadoAte) {
            try {
                modo = PDP.equals(redisGet(PREFIXO + ":modo:" + modulo)) ? PDP : TOKEN;
            } catch (Exception e) {
                redisCaiu();
            }
        }
        modos.put(modulo, new Object[]{modo, agora});
        return modo;
    }

    boolean decidirNoPdp(String tenantId, String usuarioId, String modulo) {
        if (spicedbUrl == null || spicedbUrl.isBlank()) {
            logger.warn("authz: PDP não configurado e o token não traz módulos — nega.");
            return false;
        }
        if (spicedbTimeoutMs <= 0) {
            logger.error("authz: sem o relógio do PDP (/authz/limites-drone.properties) — nega.");
            return false;
        }
        String chave = null;
        String zedtoken = null;
        if (System.nanoTime() >= redisParadoAte) {
            try {
                List<String> v = redisMget(
                        VERSAO_GLOBAL,
                        PREFIXO + ":v:t:" + tenantId,
                        PREFIXO + ":v:u:" + tenantId + ":" + usuarioId,
                        PREFIXO + ":zed:" + tenantId);
                zedtoken = v.get(3);
                chave = chaveDeDecisao(tenantId, usuarioId, v.get(0), v.get(1), v.get(2), "m:" + modulo);
                String guardada = redisGet(chave);
                if (guardada != null) {
                    return "1".equals(guardada);
                }
            } catch (Exception e) { // Redis fora: pergunta direto ao PDP
                logger.warn("authz: Redis indisponível; perguntando direto ao PDP.");
                redisCaiu();
                chave = null;
            }
        }
        Boolean ok = checarNoPdp("modulo_" + modulo, tenantId, "usa", usuarioId, zedtoken);
        if (ok == null) {
            logger.warn("authz: PDP indisponível (m:{}, tenant {}) — nega.", modulo, tenantId);
            return false;
        }
        if (chave != null) {
            try {
                redisSetex(chave, TTL_CLASSE_A_S, ok ? "1" : "0");
            } catch (Exception e) {
                redisCaiu();
            }
        }
        return ok;
    }

    /** {@code funcoesautorizacao.chaves.decisao}: o tenant e a pessoa em toda chave. */
    static String chaveDeDecisao(String tenantId, String usuarioId, String vg, String vt, String vu,
                                 String pergunta) {
        if (tenantId == null || tenantId.isBlank() || usuarioId == null || usuarioId.isBlank()) {
            throw new IllegalArgumentException("Chave de decisão sem tenant ou sem pessoa é recusada (§10.8).");
        }
        return PREFIXO + ":d:" + tenantId + ":" + usuarioId + ":"
                + nz(vg) + "." + nz(vt) + "." + nz(vu) + ":" + pergunta;
    }

    private static String nz(String v) {
        return v == null || v.isEmpty() ? "0" : v;
    }

    /** {@code true}/{@code false}, ou {@code null} quando o PDP não deu resposta utilizável. */
    protected Boolean checarNoPdp(String tipo, String id, String permissao, String usuarioId, String zedtoken) {
        Map<String, Object> corpo = new LinkedHashMap<>();
        corpo.put("consistency", zedtoken != null && !zedtoken.isBlank()
                ? Map.of("atLeastAsFresh", Map.of("token", zedtoken))
                : Map.of("minimizeLatency", true));
        corpo.put("resource", Map.of("objectType", tipo, "objectId", id));
        corpo.put("permission", permissao);
        corpo.put("subject", Map.of("object", Map.of("objectType", "usuario", "objectId", usuarioId)));
        try {
            HttpRequest req = HttpRequest.newBuilder(URI.create(spicedbUrl.replaceAll("/+$", "") + "/v1/permissions/check"))
                    .timeout(Duration.ofMillis(spicedbTimeoutMs))
                    .header("Authorization", "Bearer " + spicedbChave)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(corpo), StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> resp = http().send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() != 200) {
                logger.warn("authz: PDP respondeu {} para {}#{}", resp.statusCode(), tipo, permissao);
                return null;
            }
            JsonNode r = json.readTree(resp.body());
            return "PERMISSIONSHIP_HAS_PERMISSION".equals(r.path("permissionship").asText());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return null;
        } catch (Exception e) {
            return null;
        }
    }

    private HttpClient http() {
        HttpClient c = http;
        if (c == null) {
            synchronized (this) {
                if (http == null) {
                    http = HttpClient.newBuilder().connectTimeout(Duration.ofMillis(spicedbTimeoutMs)).build();
                }
                c = http;
            }
        }
        return c;
    }

    // --- Redis (isolado para o teste trocar sem Redis real) ---------------------

    protected String redisGet(String chave) {
        return redis().get(chave);
    }

    protected List<String> redisMget(String... chaves) {
        return new ArrayList<>(redis().mget(chaves));
    }

    protected void redisSetex(String chave, int ttl, String valor) {
        redis().setex(chave, ttl, valor);
    }

    private void redisCaiu() {
        redisParadoAte = System.nanoTime() + REDIS_PAUSA_NANOS;
    }

    private JedisPooled redis() {
        JedisPooled c = redis;
        if (c == null) {
            synchronized (this) {
                if (redis == null) {
                    URI uri = URI.create(redisUrl);
                    int porta = uri.getPort() > 0 ? uri.getPort() : 6379;
                    int db = 0;
                    String caminho = uri.getPath();
                    if (caminho != null && caminho.length() > 1) {
                        try {
                            db = Integer.parseInt(caminho.substring(1));
                        } catch (NumberFormatException ignore) {
                            // DB 0
                        }
                    }
                    JedisClientConfig cfg = DefaultJedisClientConfig.builder()
                            .socketTimeoutMillis(REDIS_TIMEOUT_MS)
                            .connectionTimeoutMillis(REDIS_TIMEOUT_MS)
                            .database(db)
                            .build();
                    redis = new JedisPooled(new HostAndPort(uri.getHost(), porta), cfg);
                }
                c = redis;
            }
        }
        return c;
    }

    @PreDestroy
    void fechar() {
        if (redis != null) {
            try {
                redis.close();
            } catch (Exception ignore) {
                // encerramento best-effort
            }
        }
    }
}
