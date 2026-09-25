"""Uma decisão, um lugar — toda pergunta "pode?" do backend passa por aqui.

docs/acesso-e-permissoes.md §10.3, princípio 2. Até a remodelagem, o "pode?"
estava espalhado em treze arquivos, cada um lendo a claim do seu jeito; hoje
eles perguntam a este módulo, e ler `iam_permissions`, `iam_modules`,
`is_tenant_admin` ou `is_platform_admin` fora daqui quebra a esteira
(`testes/backend/nucleo/test_autorizacao.py`).

**As perguntas** — a semântica de cada uma é a que vigorava antes, sem mudança:

| Função | Pergunta | Pelo token (o que era) |
|---|---|---|
| `pode(u, código)` | tem a permissão? | admin do tenant, ou o código na claim |
| `usa_modulo(u, m)` | usa o módulo? | `m` na claim `modules` |
| `tem_na_lista(u, código)` | o código está na lista do token? | `pode` e, se de módulo, `usa_modulo` |
| `administra(u)` | é admin do tenant? | `is_tenant_admin` |
| `supervisiona(u)` | é o supervisor da plataforma? | `is_platform_admin` |
| `permitidos(u, códigos)` | quais destes pode? | `pode` código a código |

O superusuário **local** do Django (`is_superuser` do espelho, não uma claim)
passa em `pode` e `administra` nos dois modos, como sempre passou.

**Quem decide** é a tabela `ModoAutorizacao`, módulo a módulo (fase 3): o token,
como sempre, ou o PDP (`autorizacao_pdp.py`). Com a sombra ligada (fase 2), a
resposta que **não** decidiu é conferida em segundo plano
(`autorizacao_sombra.py`) e a divergência fica registrada. Token de serviço (sem
`user_id`) decide sempre pelo token — é outro tipo de token, e a separação dele
é a fase 5.

**Uma resposta por requisição.** A máscara de campo pergunta a mesma coisa para
cada linha de uma lista; a primeira resposta fica guardada no próprio `user` da
requisição, e a sombra confere cada pergunta uma vez só.
"""
from __future__ import annotations

import logging
import time
from typing import Iterable

from django.conf import settings

import funcoesautorizacao
from funcoesautorizacao import classes
from funcoesautorizacao.esquema import MODULOS_DE_FUNDACAO, permissao_do_codigo, tipo_do_modulo

from . import autorizacao_pdp, autorizacao_sombra, observability
from .autorizacao_pdp import Pergunta, Quem

logger = logging.getLogger(__name__)

TOKEN, PDP = "token", "pdp"

#: A que "módulo" pertencem as perguntas de papel — a virada delas acompanha a
#: dos códigos `plataforma.*`.
MODULO_DAS_PERGUNTAS_DE_PAPEL = "plataforma"
#: Código fora do catálogo não tem módulo que possa virar: fica com o token, e a
#: sombra o registra como `fora_do_esquema`.
MODULO_DESCONHECIDO = "?"

_MEMO = "_authz_memo"

# Quanto tempo o processo confia na leitura da tabela de modos — TTL (§5.6).
# A volta atrás vale em até este tempo, em todos os processos.
_MODOS_TTL_S = 5.0
_modos: dict[str, str] = {}
_modos_lidos_em = 0.0

if observability.PROMETHEUS_AVAILABLE:
    from prometheus_client import Counter

    DECISOES = Counter(
        "sgi_authz_decisoes_total",
        "Decisões de acesso por quem decidiu e de onde veio a resposta.",
        ["modo", "origem"],
    )
else:  # pragma: no cover
    DECISOES = None


# --- As perguntas ------------------------------------------------------------


def _pergunta_de_codigo(codigo: str) -> Pergunta:
    info = funcoesautorizacao.catalogo()["codigos"].get(codigo)
    if info is None:
        return Pergunta(f"c:{codigo}", codigo, MODULO_DESCONHECIDO, classes.B, "", "")
    return Pergunta(
        f"c:{codigo}", codigo, info["modulo"], info["classe"],
        tipo_do_modulo(info["modulo"]), permissao_do_codigo(codigo),
    )


def _pergunta_de_modulo(modulo: str) -> Pergunta:
    conhecido = modulo in funcoesautorizacao.catalogo()["modulos_vendaveis"]
    return Pergunta(
        f"m:{modulo}", modulo, modulo if conhecido else MODULO_DESCONHECIDO,
        classes.CLASSE_DE_USA_MODULO, tipo_do_modulo(modulo) if conhecido else "", "usa",
    )


_ADMINISTRA = Pergunta("administra", "", MODULO_DAS_PERGUNTAS_DE_PAPEL,
                       classes.CLASSE_DE_ADMINISTRA, "empresa", "administra")
_SUPERVISIONA = Pergunta("supervisiona", "", MODULO_DAS_PERGUNTAS_DE_PAPEL,
                         classes.CLASSE_DE_SUPERVISIONA, "plataforma", "supervisiona",
                         na_plataforma=True)


# --- A resposta do token (a regra que vigorava) -------------------------------


def _pelo_token(user, p: Pergunta) -> bool:
    if p is _ADMINISTRA:
        return bool(getattr(user, "is_tenant_admin", False))
    if p is _SUPERVISIONA:
        return bool(getattr(user, "is_platform_admin", False))
    if p.chave.startswith("m:"):
        return p.valor in (getattr(user, "iam_modules", None) or ())
    return bool(getattr(user, "is_tenant_admin", False)) or p.valor in (
        getattr(user, "iam_permissions", None) or ()
    )


# --- Quem decide ------------------------------------------------------------


def _pdp_configurado() -> bool:
    return bool(getattr(settings, "SPICEDB_URL", ""))


def _quem(user) -> Quem | None:
    """Pessoa com sessão da IAM. Token de serviço e usuário forjado em teste não têm."""
    uid = getattr(user, "iam_user_id", None)
    tid = getattr(user, "iam_tenant_id", None)
    if not uid or not tid:
        return None
    return Quem(tenant_id=str(tid), usuario_id=str(uid))


def modo_do_modulo(modulo: str) -> str:
    """O que a tabela `ModoAutorizacao` diz, lido no máximo a cada `_MODOS_TTL_S`."""
    global _modos, _modos_lidos_em
    if not _pdp_configurado() or modulo == MODULO_DESCONHECIDO:
        return TOKEN
    agora = time.monotonic()
    if agora - _modos_lidos_em > _MODOS_TTL_S:
        try:
            from .models import ModoAutorizacao

            _modos = dict(ModoAutorizacao.objects.values_list("modulo", "modo"))
        except Exception:  # noqa: BLE001 - sem a tabela, o token decide (como antes)
            logger.warning("authz.modos_ilegiveis", exc_info=True)
            _modos = {}
        _modos_lidos_em = agora
    return PDP if _modos.get(modulo) == PDP else TOKEN


def esquecer_modos() -> None:
    """Força a próxima pergunta a reler a tabela (o comando e os testes usam)."""
    global _modos_lidos_em
    _modos_lidos_em = 0.0


def _impressao(user) -> tuple:
    """O que, mudando, invalida a memória. Na requisição real o `user` nasce a
    cada vez e ela nunca muda; em teste o mesmo objeto atravessa várias
    requisições com a claim trocada no meio, e a resposta velha não pode vazar."""
    perms = getattr(user, "iam_permissions", None)
    mods = getattr(user, "iam_modules", None)
    return (
        id(perms), len(perms or ()), id(mods), len(mods or ()),
        getattr(user, "is_tenant_admin", False), getattr(user, "is_platform_admin", False),
        getattr(user, "iam_token_iat", None),
    )


def _decidir(user, p: Pergunta) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    impressao = _impressao(user)
    guardado = user.__dict__.get(_MEMO)
    if guardado is None or guardado[0] != impressao:
        guardado = user.__dict__[_MEMO] = (impressao, {})
    memo = guardado[1]
    if p.chave in memo:
        return memo[p.chave]

    pelo_token = _pelo_token(user, p)
    quem = _quem(user) if _pdp_configurado() else None
    modo = modo_do_modulo(p.modulo) if quem else TOKEN

    if modo == PDP:
        pelo_pdp, origem = autorizacao_pdp.decidir(quem, p)
        final = pelo_pdp
    else:
        pelo_pdp, origem = None, "token"
        final = pelo_token

    if quem is not None and getattr(settings, "AUTORIZACAO_SOMBRA", False):
        autorizacao_sombra.submeter(autorizacao_sombra.Comparacao(
            quem=quem, iat=getattr(user, "iam_token_iat", None), pergunta=p, modo=modo,
            decisao_token=pelo_token, decisao_pdp=pelo_pdp, origem_pdp=origem if pelo_pdp is not None else None,
        ))
    if DECISOES is not None:
        DECISOES.labels(modo=modo, origem=origem).inc()

    memo[p.chave] = final
    return final


# --- A API ------------------------------------------------------------------


def _superusuario_local(user) -> bool:
    return bool(getattr(user, "is_superuser", False))


def pode(user, codigo: str) -> bool:
    """Tem a permissão `codigo` (``modulo.recurso.acao``)? O admin do tenant passa."""
    if _superusuario_local(user) and getattr(user, "is_authenticated", False):
        return True
    return _decidir(user, _pergunta_de_codigo(codigo))


def usa_modulo(user, modulo: str) -> bool:
    """A empresa assina o módulo e a pessoa foi liberada nele (entitlement)."""
    return _decidir(user, _pergunta_de_modulo(modulo))


def tem_na_lista(user, codigo: str) -> bool:
    """O código estaria na lista do token — `pode` sem o atalho do admin fora do
    módulo. É a leitura exata de quem conferia `código in iam_permissions` sem
    olhar `is_tenant_admin` (a fila da conversão, `frota_views`). Sem o atalho do
    superusuário local, que aquela leitura também não tinha."""
    if not _decidir(user, _pergunta_de_codigo(codigo)):
        return False
    modulo = (funcoesautorizacao.catalogo()["codigos"].get(codigo) or {}).get("modulo")
    if modulo is None or modulo in MODULOS_DE_FUNDACAO:
        return True
    return usa_modulo(user, modulo)


def administra(user) -> bool:
    """Admin do próprio tenant (ou o superusuário local do Django)."""
    if _superusuario_local(user) and getattr(user, "is_authenticated", False):
        return True
    return _decidir(user, _ADMINISTRA)


def supervisiona(user) -> bool:
    """O supervisor da plataforma (superusuário da IAM)."""
    return _decidir(user, _SUPERVISIONA)


def permitidos(user, codigos: Iterable[str]) -> set[str]:
    """Quais destes códigos a pessoa tem — `pode` para cada um."""
    return {c for c in set(codigos) if c and pode(user, c)}
