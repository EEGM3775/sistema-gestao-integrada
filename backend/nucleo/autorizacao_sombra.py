"""A sombra — cada decisão conferida com o PDP, sem atrasar a resposta (fase 2).

docs/acesso-e-permissoes.md §10.12: "`pode()` decide pelo token **e** consulta o
PDP, registrando toda divergência". A consulta acontece numa thread de fundo:
a pessoa recebe a resposta do token no mesmo tempo de sempre, e o PDP é
conferido depois. Se o PDP ficar lento, as conferências fazem fila até
`AUTORIZACAO_SOMBRA_FILA`; dali em diante são descartadas **e contadas** — o
relatório não pode dizer "zero divergência" sobre um dia que ele não viu.

Depois da virada (fase 3), o mesmo registro continua ao contrário: o PDP decide
e o token é quem é conferido. É o que diz se a volta atrás seria segura.

**O tipo da divergência é o que separa defeito de desenho:**

- `token_defasado` — o token nasceu antes da última troca de acesso do tenant e
  ainda diz o que era verdade. É a janela que a fase 4 fecha; não conta contra
  a saída da fase 2;
- `pdp_indisponivel` e `fora_do_esquema` — o PDP não deu resposta utilizável;
- `real` — nenhuma das anteriores. É o que zera o relógio das duas semanas.

**Medida da auditoria (§10.9):** cada comparação soma um no volume do dia por
tenant e pessoa. É de onde sai o número que o dono ainda precisa para fixar a
retenção por plano — o volume real, e não a estimativa da planta.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from django.db import connection
from django.utils import timezone

from funcoesautorizacao import chaves
from payment.planos import AUTORIZACAO_DIVERGENCIA_JANELA_S, AUTORIZACAO_SOMBRA_FILA

from . import autorizacao_pdp, observability
from .autorizacao_pdp import FALHA, FORA_DO_ESQUEMA, Pergunta, Quem

logger = logging.getLogger(__name__)

# Duas threads bastam: a pergunta ao PDP é de milissegundos, e a fila é que
# absorve o pico. Não é teto de cliente (§5.6), é o tamanho do motor.
_THREADS = 2
# Por quanto tempo os contadores do dia ficam no Redis — TTL (§5.6), não teto.
_CONTADORES_TTL_S = 120 * 86400

_executor: ThreadPoolExecutor | None = None
_vagas = threading.BoundedSemaphore(AUTORIZACAO_SOMBRA_FILA)
_trava = threading.Lock()

if observability.PROMETHEUS_AVAILABLE:
    from prometheus_client import Counter

    DIVERGENCIAS = Counter(
        "sgi_authz_divergencias_total",
        "Perguntas em que token e PDP responderam diferente.",
        ["tipo", "modo"],
    )
    DESCARTES = Counter(
        "sgi_authz_sombra_descartes_total",
        "Comparações da sombra descartadas por fila cheia.",
    )
else:  # pragma: no cover
    DIVERGENCIAS = DESCARTES = None


@dataclass(frozen=True)
class Comparacao:
    quem: Quem
    iat: int | None
    pergunta: Pergunta
    modo: str
    decisao_token: bool
    #: Já conhecida quando o PDP decidiu a requisição (fase 3); senão, é a
    #: sombra que vai perguntar.
    decisao_pdp: bool | None = None
    origem_pdp: str | None = None


def _pool() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        with _trava:
            if _executor is None:
                _executor = ThreadPoolExecutor(max_workers=_THREADS, thread_name_prefix="sombra")
    return _executor


def submeter(c: Comparacao) -> None:
    """Enfileira a comparação. Fila cheia: descarta e conta — nunca bloqueia."""
    if not _vagas.acquire(blocking=False):
        _contar_descarte()
        return

    def tarefa():
        try:
            executar(c)
        finally:
            _vagas.release()

    try:
        _pool().submit(tarefa)
    except RuntimeError:  # executor encerrado (processo saindo)
        _vagas.release()


def _dia() -> str:
    return timezone.now().strftime("%Y%m%d")


def _contar_descarte() -> None:
    if DESCARTES is not None:
        DESCARTES.inc()
    r = autorizacao_pdp.redis()
    if r is None:
        return
    try:
        chave = chaves.descartes_do_dia(_dia())
        r.incr(chave)
        r.expire(chave, _CONTADORES_TTL_S)
    except Exception:  # noqa: BLE001
        autorizacao_pdp.redis_caiu()


def _contar(c: Comparacao) -> None:
    r = autorizacao_pdp.redis()
    if r is None:
        return
    dia = _dia()
    try:
        pipe = r.pipeline()
        pipe.incr(chaves.comparacoes_do_dia(dia))
        pipe.expire(chaves.comparacoes_do_dia(dia), _CONTADORES_TTL_S)
        pipe.hincrby(chaves.volume_do_dia(dia), f"{c.quem.tenant_id}|{c.quem.usuario_id}", 1)
        pipe.expire(chaves.volume_do_dia(dia), _CONTADORES_TTL_S)
        pipe.execute()
    except Exception:  # noqa: BLE001
        autorizacao_pdp.redis_caiu()


def classificar(c: Comparacao, decisao_pdp: bool, origem: str) -> str | None:
    """O tipo da divergência, ou None quando os dois lados concordam."""
    from .models import DivergenciaAutorizacao as D

    if origem == FALHA:
        return D.Tipo.PDP_INDISPONIVEL
    if origem == FORA_DO_ESQUEMA:
        # Pergunta que o PDP não conhece e que o token também nega não é
        # divergência — é o "negar por padrão" dos dois lados.
        return D.Tipo.FORA_DO_ESQUEMA if c.decisao_token else None
    if decisao_pdp == c.decisao_token:
        return None
    mudanca = None
    r = autorizacao_pdp.redis()
    if r is not None:
        try:
            mudanca = r.get(chaves.mudanca_do_tenant(c.quem.tenant_id))
        except Exception:  # noqa: BLE001
            autorizacao_pdp.redis_caiu()
    if c.iat and mudanca and int(c.iat) <= int(mudanca):
        return D.Tipo.TOKEN_DEFASADO
    return D.Tipo.REAL


def _primeira_da_janela(c: Comparacao, tipo: str) -> bool:
    r = autorizacao_pdp.redis()
    if r is None:
        return True  # sem Redis, registra — melhor repetido que perdido
    try:
        return bool(r.set(
            chaves.divergencia_vista(c.quem.tenant_id, c.quem.usuario_id, c.pergunta.chave, tipo),
            "1", nx=True, ex=AUTORIZACAO_DIVERGENCIA_JANELA_S,
        ))
    except Exception:  # noqa: BLE001
        autorizacao_pdp.redis_caiu()
        return True


def executar(c: Comparacao) -> str | None:
    """Pergunta ao PDP (se ainda não se sabe), compara e registra. Devolve o tipo."""
    try:
        if c.decisao_pdp is None:
            decisao_pdp, origem = autorizacao_pdp.decidir(c.quem, c.pergunta)
        else:
            decisao_pdp, origem = c.decisao_pdp, c.origem_pdp or autorizacao_pdp.PDP
        _contar(c)
        tipo = classificar(c, decisao_pdp, origem)
        if tipo is None:
            return None
        if DIVERGENCIAS is not None:
            DIVERGENCIAS.labels(tipo=tipo, modo=c.modo).inc()
        logger.warning(
            "authz.divergencia tipo=%s pergunta=%s modo=%s token=%s pdp=%s tenant=%s",
            tipo, c.pergunta.chave, c.modo, c.decisao_token, decisao_pdp, c.quem.tenant_id,
        )
        if _primeira_da_janela(c, tipo):
            _gravar(c, decisao_pdp, origem, tipo)
        return tipo
    except Exception:  # noqa: BLE001 - a sombra nunca derruba nada
        logger.exception("authz.sombra_falhou pergunta=%s", c.pergunta.chave)
        return None


def _gravar(c: Comparacao, decisao_pdp: bool, origem: str, tipo: str) -> None:
    from .models import DivergenciaAutorizacao

    fora_da_requisicao = threading.current_thread() is not threading.main_thread() and (
        threading.current_thread().name.startswith("sombra")
    )
    try:
        DivergenciaAutorizacao.objects.create(
            tenant_id=c.quem.tenant_id or None,
            usuario_id=c.quem.usuario_id,
            pergunta=c.pergunta.chave[:100],
            modulo=c.pergunta.modulo,
            classe=c.pergunta.classe,
            modo=c.modo,
            decisao_token=c.decisao_token,
            decisao_pdp=None if origem in (FALHA, FORA_DO_ESQUEMA) else decisao_pdp,
            tipo=tipo,
            idade_do_token_s=int(time.time() - int(c.iat)) if c.iat else None,
        )
    finally:
        # A thread da sombra abre a própria conexão; fechar aqui evita que ela
        # fique pendurada entre uma divergência e outra.
        if fora_da_requisicao:
            connection.close()
