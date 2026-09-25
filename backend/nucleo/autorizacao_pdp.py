"""A decisão pelo PDP — cache por classe, versão por evento e o modo de falha.

docs/acesso-e-permissoes.md §10.8. Quem chama é `nucleo/autorizacao.py` (quando
o módulo virou para o PDP) e a sombra (quando o módulo ainda é do token, para
comparar). O caminho é o mesmo nos dois casos, de propósito: a sombra da fase 2
mede exatamente o que a fase 3 vai decidir, cache incluído.

**A chave do cache carrega três versões** — a global, a do tenant e a da pessoa
—, e quem as sobe é quem muda relação (a IAM, ao gravar) e o invalidador (a cada
evento do Watch). Subiu a versão, a decisão velha deixa de ser lida: a
revogação vale na hora, e o TTL da classe é só o pior caso com o invalidador
fora.

**Modo de falha, por classe:**

- Redis fora → pergunta direto ao PDP (mais lento, correto);
- PDP fora → A e B servem o que ainda estiver no cache e, sem cache, **negam**;
  C nunca usa cache e **nega na hora**;
- pergunta que o PDP não conhece (código fora do catálogo) → **nega**.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from django.conf import settings

from funcoesautorizacao import chaves, classes
from funcoesautorizacao.cliente import (
    ClienteSpiceDB,
    PdpIndisponivel,
    PerguntaInvalida,
    consistencia_ao_menos,
    consistencia_total,
)
from funcoesautorizacao.esquema import ID_PLATAFORMA
from payment.planos import AUTORIZACAO_PDP_TIMEOUT_MS

from . import observability

logger = logging.getLogger(__name__)

# Origem da resposta — vai para a métrica e para a divergência.
CACHE, PDP, FALHA, FORA_DO_ESQUEMA = "cache", "pdp", "falha", "fora_do_esquema"

_cliente: ClienteSpiceDB | None = None
_redis_cliente = None
# Mesmo disjuntor da revogação (nucleo/revocation.py): um Redis fora custa
# segundos por chamada, e isto roda em toda requisição.
_REDIS_PAUSA_S = 5.0
_redis_parado_ate = 0.0

if observability.PROMETHEUS_AVAILABLE:
    from prometheus_client import Histogram

    PDP_LATENCIA = Histogram(
        "sgi_authz_pdp_segundos",
        "Latência da pergunta ao PDP (SpiceDB).",
        ["classe"],
        buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    )
else:  # pragma: no cover
    PDP_LATENCIA = None


@dataclass(frozen=True)
class Quem:
    """O que o PDP precisa saber de quem pergunta — e nada mais."""

    tenant_id: str
    usuario_id: str


@dataclass(frozen=True)
class Pergunta:
    """Uma pergunta "pode?" já traduzida para o PDP.

    `chave` identifica a pergunta no cache e na divergência (``c:<código>``,
    ``m:<módulo>``, ``administra``, ``supervisiona``); `modulo` diz quem decide
    (a tabela `ModoAutorizacao`); `tipo` vazio é pergunta que o schema não tem.
    """

    chave: str
    valor: str
    modulo: str
    classe: str
    tipo: str
    permissao: str
    na_plataforma: bool = False


def cliente() -> ClienteSpiceDB:
    global _cliente
    if _cliente is None:
        _cliente = ClienteSpiceDB(
            settings.SPICEDB_URL, settings.SPICEDB_CHAVE,
            timeout_s=AUTORIZACAO_PDP_TIMEOUT_MS / 1000,
        )
    return _cliente


def redis():
    """O Redis da autorização, ou None enquanto o disjuntor está aberto."""
    global _redis_cliente
    if time.monotonic() < _redis_parado_ate:
        return None
    if _redis_cliente is None:
        import redis as _r

        _redis_cliente = _r.Redis.from_url(
            settings.AUTORIZACAO_REDIS_URL,
            socket_timeout=0.25,
            socket_connect_timeout=0.25,
            retry_on_timeout=False,
            decode_responses=True,
        )
    return _redis_cliente


def redis_caiu() -> None:
    global _redis_parado_ate
    _redis_parado_ate = time.monotonic() + _REDIS_PAUSA_S


def _consistencia(classe: str, zedtoken: str | None) -> dict:
    """C: total. A e B: pelo menos tão nova quanto a última mudança do tenant.

    **A classe A não usa a consistência "rápida" pura**, e o motivo foi medido na
    E2E da virada: a rápida pode responder com o estado de alguns segundos atrás
    (a quantização do SpiceDB). Logo depois de uma revogação, a versão sobe, a
    primeira pergunta nova cai exatamente nessa janela, recebe a resposta de
    ANTES — e a guarda no cache por 60 s sob a chave nova. A invalidação por
    evento ficava anulada. Com o ZedToken da última mudança, a resposta nunca é
    anterior a ela; sem mudança conhecida, cai na rápida, e aí não há o que esperar.
    """
    if classe == classes.C:
        return consistencia_total()
    return consistencia_ao_menos(zedtoken)


def decidir(quem: Quem, p: Pergunta) -> tuple[bool, str]:
    """``(permitido, origem)``. Nunca levanta: sem resposta utilizável, nega."""
    if not p.tipo:
        return False, FORA_DO_ESQUEMA

    r = redis()
    chave = None
    zedtoken = None
    if r is not None:
        try:
            vg, vt, vu, zedtoken = r.mget(
                chaves.VERSAO_GLOBAL,
                chaves.versao_do_tenant(quem.tenant_id),
                chaves.versao_do_usuario(quem.tenant_id, quem.usuario_id),
                chaves.zedtoken_do_tenant(quem.tenant_id),
            )
            if p.classe != classes.C:
                chave = chaves.decisao(quem.tenant_id, quem.usuario_id, (vg, vt, vu), p.chave)
                guardada = r.get(chave)
                if guardada is not None:
                    return guardada == "1", CACHE
        except Exception:  # noqa: BLE001 - Redis fora: pergunta direto ao PDP
            logger.warning("authz.redis_indisponivel", exc_info=True)
            redis_caiu()
            r, chave = None, None

    recurso = ID_PLATAFORMA if p.na_plataforma else quem.tenant_id
    inicio = time.monotonic()
    try:
        ok, _ = cliente().checar(
            p.tipo, recurso, p.permissao, quem.usuario_id, _consistencia(p.classe, zedtoken)
        )
    except PerguntaInvalida:
        logger.warning("authz.fora_do_esquema pergunta=%s", p.chave)
        return False, FORA_DO_ESQUEMA
    except PdpIndisponivel:
        logger.warning("authz.pdp_indisponivel pergunta=%s classe=%s", p.chave, p.classe)
        return False, FALHA
    finally:
        if PDP_LATENCIA is not None:
            PDP_LATENCIA.labels(classe=p.classe).observe(time.monotonic() - inicio)

    if chave is not None and r is not None:
        try:
            r.setex(chave, classes.TTL_S[p.classe], "1" if ok else "0")
        except Exception:  # noqa: BLE001
            redis_caiu()
    return ok, PDP
