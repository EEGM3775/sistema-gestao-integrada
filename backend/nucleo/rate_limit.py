"""Camada 2 — limite de SAÍDA, por fornecedor (token bucket no Redis).

Desenho e justificativas: docs/arquitetura/rate-limiting.md.

Resumo do porquê, para quem chegar aqui pelo código:

- **Por fornecedor, não por endpoint/usuário.** A cota disputada é a da NFE.io, a
  do Asaas, a da Meta. O fornecedor não distingue se a nota veio do lote ou da
  tela. Um balde por fornecedor faz qualquer caminho novo herdar o limite de
  graça — inclusive os que ainda não existem.
- **No worker, no cliente HTTP.** Toda integração de escrita é assíncrona: a view
  enfileira, o worker executa. Limitar na view limita *intenção*, não consumo —
  e o endpoint de lote emite N notas numa requisição só, com `max_retries=3`
  multiplicando cada uma por até 4.
- **Token bucket.** Tolera rajada mantendo a média, que é o padrão real de uso
  (remessa, emissão em massa, fechamento de mês). Janela fixa quebraria o lote
  legítimo.

O algoritmo roda **inteiro dentro do Redis** (script Lua): com vários workers
concorrendo pelo mesmo balde, ler-decidir-gravar em passos separados deixaria
dois processos consumirem o mesmo token.
"""
from __future__ import annotations

import logging
import time

from django.conf import settings
from rest_framework.exceptions import Throttled

logger = logging.getLogger(__name__)


class LimiteFornecedorExcedido(Throttled):
    """Sem token disponível agora. NÃO é erro do fornecedor nem falha permanente:
    o chamador deve **reagendar** (as tasks fazem `retry` com `countdown`), nunca
    bloquear o worker esperando — worker parado deixa de atender toda a fila,
    inclusive tarefas de outros tenants.

    Herda de `Throttled` (DRF) porque nem toda chamada a fornecedor vem de task:
    `gerar-cobranca` e `divergencias-asaas` consultam o Asaas **dentro da
    requisição**, e essas views capturam só `AsaasAPIError` — uma exceção comum
    viraria **500**. Sendo `Throttled`, o DRF a converte sozinho em **429 com
    `Retry-After`**, em qualquer view, inclusive as que ainda não existem.
    """

    default_code = "limite_fornecedor"

    def __init__(self, fornecedor: str, espera_segundos: float):
        self.fornecedor = fornecedor
        self.espera_segundos = max(1, int(round(espera_segundos)))
        super().__init__(
            wait=self.espera_segundos,
            detail=(
                f"O sistema atingiu o limite de chamadas ao serviço externo "
                f"'{fornecedor}'. Nada foi perdido: tente novamente em "
                f"~{self.espera_segundos}s."
            ),
        )


# Token bucket clássico, atômico. Guarda dois campos por balde: tokens restantes
# e o instante da última reposição; repõe proporcionalmente ao tempo decorrido.
# Devolve {1, tokens_restantes} se consumiu, {0, espera_em_ms} se não havia.
_LUA_TOKEN_BUCKET = """
local chave    = KEYS[1]
local taxa     = tonumber(ARGV[1])   -- tokens por segundo
local balde    = tonumber(ARGV[2])   -- capacidade (burst)
local agora    = tonumber(ARGV[3])   -- epoch em segundos (float)
local pedidos  = tonumber(ARGV[4])   -- tokens a consumir

local dados    = redis.call('HMGET', chave, 'tokens', 'visto')
local tokens   = tonumber(dados[1])
local visto    = tonumber(dados[2])

if tokens == nil then
  tokens = balde
  visto  = agora
end

-- Reposição proporcional ao tempo decorrido, limitada à capacidade.
local decorrido = math.max(0, agora - visto)
tokens = math.min(balde, tokens + decorrido * taxa)

local concedido = 0
local espera_ms = 0
if tokens >= pedidos then
  tokens = tokens - pedidos
  concedido = 1
else
  espera_ms = math.ceil(((pedidos - tokens) / taxa) * 1000)
end

redis.call('HSET', chave, 'tokens', tokens, 'visto', agora)
-- TTL de sobra: balde ocioso some sozinho em vez de acumular chave morta.
redis.call('EXPIRE', chave, math.ceil(balde / taxa) + 60)

return {concedido, espera_ms}
"""

_cliente = None
_script = None


def _redis():
    """Cliente preguiçoso, com timeouts curtos: o limitador nunca pode ser o
    motivo de uma task travar."""
    global _cliente, _script
    if _cliente is None:
        import redis

        url = getattr(settings, "RATE_LIMIT_REDIS_URL", None) or settings.CELERY_BROKER_URL
        _cliente = redis.Redis.from_url(
            url, socket_timeout=0.5, socket_connect_timeout=0.5
        )
        _script = _cliente.register_script(_LUA_TOKEN_BUCKET)
    return _cliente, _script


def _config(fornecedor: str):
    """(taxa_por_segundo, capacidade) do fornecedor, ou None se não tiver limite.

    Fornecedor sem entrada em `RATE_LIMIT_FORNECEDORES` passa direto — é
    deliberado: integração nova não fica bloqueada por esquecimento de config, e
    a ausência aparece no inventário da documentação.
    """
    conf = getattr(settings, "RATE_LIMIT_FORNECEDORES", {}).get(fornecedor)
    if not conf:
        return None
    taxa = float(conf.get("taxa_por_segundo", 0))
    if taxa <= 0:
        return None
    return taxa, float(conf.get("burst", max(1.0, taxa)))


def consumir(fornecedor: str, tokens: int = 1, *, chave_extra: str = "") -> None:
    """Consome `tokens` do balde do fornecedor ou levanta `LimiteFornecedorExcedido`.

    `chave_extra` separa baldes dentro do mesmo fornecedor — usar quando a
    credencial deixar de ser global e passar a ser por tenant (previsto para o
    Asaas): aí a cota disputada é a daquela empresa, e um balde único limitaria
    empresas sem relação entre si.
    """
    conf = _config(fornecedor)
    if conf is None:
        return
    taxa, capacidade = conf

    if getattr(settings, "RATE_LIMIT_DESLIGADO", False):
        return

    chave = f"ratelimit:fornecedor:{fornecedor}"
    if chave_extra:
        chave = f"{chave}:{chave_extra}"

    try:
        _, script = _redis()
        concedido, espera_ms = script(keys=[chave], args=[taxa, capacidade, time.time(), tokens])
    except Exception:  # noqa: BLE001
        # FAIL-OPEN, mas RUIDOSO. Travar aqui pararia emissão de nota e boleto do
        # sistema inteiro; deixar passar, no pior caso, gera 429 do próprio
        # fornecedor — que o retry já trata. O log é `error` de propósito: um
        # protetor fail-open que perdeu a dependência fica indistinguível de um
        # protetor funcionando (foi a origem do achado D21).
        logger.error(
            "RATE LIMIT INATIVO para '%s': o Redis do limitador não respondeu. "
            "As chamadas estão passando SEM limite até o Redis voltar.",
            fornecedor, exc_info=True,
        )
        return

    if not int(concedido):
        raise LimiteFornecedorExcedido(fornecedor, int(espera_ms) / 1000.0)


def estado(fornecedor: str, *, chave_extra: str = "") -> dict:
    """Leitura só para diagnóstico/teste — não consome token."""
    conf = _config(fornecedor)
    if conf is None:
        return {"fornecedor": fornecedor, "limitado": False}
    taxa, capacidade = conf
    chave = f"ratelimit:fornecedor:{fornecedor}"
    if chave_extra:
        chave = f"{chave}:{chave_extra}"
    try:
        cliente, _ = _redis()
        dados = cliente.hgetall(chave)
    except Exception:  # noqa: BLE001
        return {"fornecedor": fornecedor, "limitado": True, "redis": "indisponivel"}
    tokens = float(dados.get(b"tokens", capacidade)) if dados else capacidade
    return {
        "fornecedor": fornecedor,
        "limitado": True,
        "taxa_por_segundo": taxa,
        "burst": capacidade,
        "tokens_disponiveis": round(tokens, 2),
    }
