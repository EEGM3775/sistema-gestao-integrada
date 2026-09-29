"""A IAM escreve no PDP — remodelagem da segurança, fase 2 (acesso-e-permissoes.md §10.4).

A IAM continua a autoridade de **quem é** a pessoa e a tela onde o admin compõe
papéis. O que muda é que cada troca de papel, acesso a módulo ou assinatura
chega também ao SpiceDB, como relação, **na mesma operação** — é dali que o
backend passa a perguntar "pode?".

**Reconciliação, e não evento a evento.** A unidade de escrita é o tenant
inteiro: calcula-se o conjunto de relações que as tabelas de hoje implicam
(`relacoes_do_tenant`), lê-se o que o PDP tem, e grava-se só a diferença. É
idempotente — rodar duas vezes não muda nada — e por isso o mesmo código serve
à escrita da tela (disparada por sinal, ao fim da transação), à volta periódica
do `sincronizar_pdp --continuo` e ao conserto depois de uma queda do PDP. Um
tradutor evento a evento teria de acertar cada transição; a reconciliação só
precisa acertar o estado.

**Enquanto dura a sombra, as tabelas continuam a fonte.** A planta quer, ao fim,
uma fonte só (quem tem cada papel morando no SpiceDB). Na fase 2 o token ainda
decide, e ele sai destas tabelas: se o PDP fosse a fonte, a sombra compararia o
token com ele mesmo. A troca de fonte vem com a fase 4, quando o token deixa de
carregar permissão.

**O que as relações reproduzem** é a régua de `Usuario.modulos_efetivos` e
`permissoes_efetivas`, pergunta por pergunta; o schema que as lê está em
`funcoesautorizacao/esquema.py`, com a explicação de cada regra.

**PDP fora não derruba nada aqui.** A troca de papel é gravada no banco da IAM de
qualquer jeito; se a escrita no SpiceDB falhar, o tenant entra na fila de
pendentes no Redis e o `iam-pdp` o refaz. Se o Redis também estiver fora, a
volta periódica acha a diferença sozinha.
"""
from __future__ import annotations

import logging
import time

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

import funcoesautorizacao
from funcoesautorizacao import chaves
from funcoesautorizacao.cliente import ClienteSpiceDB, ErroDoPdp, Rel
from funcoesautorizacao.esquema import (
    ID_PLATAFORMA,
    MODULOS_DE_FUNDACAO,
    id_do_papel,
    relacao_de_concessao,
    tipo_do_modulo,
)
from payment.planos import AUTORIZACAO_PDP_TIMEOUT_MS

logger = logging.getLogger(__name__)

_cliente: ClienteSpiceDB | None = None
_redis_cliente = None


def ativo() -> bool:
    """Sem `SPICEDB_URL`, a IAM não escreve no PDP (é o caso da suíte de testes)."""
    return bool(getattr(settings, "SPICEDB_URL", ""))


def cliente() -> ClienteSpiceDB:
    global _cliente
    if _cliente is None:
        # A escrita da tela roda dentro da requisição de quem troca o papel; o
        # teto é o mesmo relógio da decisão, e a reconciliação lenta tem o seu
        # próprio fôlego no `ler` do cliente.
        _cliente = ClienteSpiceDB(
            settings.SPICEDB_URL,
            settings.SPICEDB_CHAVE,
            timeout_s=max(AUTORIZACAO_PDP_TIMEOUT_MS / 1000, 2.0),
        )
    return _cliente


def _redis():
    global _redis_cliente
    if _redis_cliente is None:
        import redis

        _redis_cliente = redis.Redis.from_url(
            settings.AUTORIZACAO_REDIS_URL,
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
            decode_responses=True,
        )
    return _redis_cliente


def _modulos_vendaveis() -> list[str]:
    return funcoesautorizacao.catalogo()["modulos_vendaveis"]


# --- O que as tabelas implicam ---------------------------------------------


def relacoes_do_tenant(tenant_id) -> set[Rel]:
    """Todas as relações que as tabelas da IAM implicam para uma empresa, hoje."""
    from identity.catalog import POR_CODIGO

    from .models import AcessoUsuarioModulo, AssinaturaTenant, Modulo, Perfil, Usuario

    tid = str(tenant_id)
    rels: set[Rel] = set()

    # Quem é da empresa. Conta desativada não entra: ela não recebe token.
    for u in Usuario.objects.filter(tenant_id=tenant_id, is_active=True).values(
        "id", "is_tenant_admin", "is_superuser"
    ):
        uid = str(u["id"])
        rels.add(Rel("empresa", tid, "membro", "usuario", uid))
        if u["is_tenant_admin"]:
            rels.add(Rel("empresa", tid, "administrador", "usuario", uid))
        if u["is_superuser"]:
            rels.add(Rel("empresa", tid, "supervisor", "usuario", uid))

    # Os módulos. Um objeto por módulo vendável do schema, sempre com a empresa;
    # `catalogado` quando o módulo existe na tabela de módulos (é a régua do
    # supervisor); `assinatura` só enquanto a assinatura vale hoje — a mesma
    # consulta de `Usuario.modulos_efetivos`, com a mesma data (UTC).
    catalogados = set(Modulo.objects.values_list("codigo", flat=True))
    hoje = timezone.now().date()
    assinados = set(
        AssinaturaTenant.objects.filter(
            tenant_id=tenant_id, status=AssinaturaTenant.Status.ATIVA, inicio__lte=hoje
        )
        .filter(Q(fim__isnull=True) | Q(fim__gte=hoje))
        .values_list("modulo__codigo", flat=True)
    )
    vendaveis = _modulos_vendaveis()
    for modulo in vendaveis:
        tipo = tipo_do_modulo(modulo)
        rels.add(Rel(tipo, tid, "empresa", "empresa", tid))
        if modulo in catalogados:
            rels.add(Rel(tipo, tid, "catalogado", "empresa", tid))
        if modulo in assinados:
            rels.add(Rel(tipo, tid, "assinatura", "empresa", tid))
    for modulo in MODULOS_DE_FUNDACAO:
        rels.add(Rel(tipo_do_modulo(modulo), tid, "empresa", "empresa", tid))

    for uid, codigo in AcessoUsuarioModulo.objects.filter(
        usuario__tenant_id=tenant_id, usuario__is_active=True
    ).values_list("usuario_id", "modulo__codigo"):
        if codigo in vendaveis:
            rels.add(Rel(tipo_do_modulo(codigo), tid, "liberado", "usuario", str(uid)))

    # Os papéis e o que cada um concede. Código fora do catálogo não vira
    # relação — pela mesma regra que o deixa fora do token.
    for perfil in Perfil.objects.filter(tenant_id=tenant_id).prefetch_related("permissoes"):
        pid = id_do_papel(tid, perfil.id)
        rels.add(Rel("papel", pid, "empresa", "empresa", tid))
        for permissao in perfil.permissoes.all():
            p = POR_CODIGO.get(permissao.codename)
            if p is None:
                continue
            rels.add(Rel(
                tipo_do_modulo(p.modulo), tid, relacao_de_concessao(p.code),
                "papel", pid, "portador",
            ))

    # Quem porta cada papel — só papel e pessoa da mesma empresa. Um papel de
    # outra empresa atribuído por engano entra no token hoje; aqui não entra, e
    # a sombra acusa a diferença, que é o que deve acontecer com um defeito.
    for uid, perfil_id in Usuario.perfis.through.objects.filter(
        usuario__tenant_id=tenant_id, usuario__is_active=True, perfil__tenant_id=tenant_id,
    ).values_list("usuario_id", "perfil_id"):
        rels.add(Rel("papel", id_do_papel(tid, perfil_id), "portador", "usuario", str(uid)))

    return rels


def relacoes_da_plataforma() -> set[Rel]:
    """O supervisor da plataforma, que não é de empresa nenhuma."""
    from .models import Usuario

    return {
        Rel("plataforma", ID_PLATAFORMA, "supervisor", "usuario", str(uid))
        for uid in Usuario.objects.filter(is_superuser=True, is_active=True).values_list(
            "id", flat=True
        )
    }


# --- Reconciliação ------------------------------------------------------------


def _tipos_de_tenant() -> list[str]:
    return (
        ["empresa", "papel"]
        + [tipo_do_modulo(m) for m in MODULOS_DE_FUNDACAO]
        + [tipo_do_modulo(m) for m in _modulos_vendaveis()]
    )


def _relacoes_no_pdp(cli: ClienteSpiceDB, tenant_id: str) -> set[Rel]:
    atuais: set[Rel] = set()
    for tipo in _tipos_de_tenant():
        atuais.update(cli.ler(tipo, tenant_id))
    return atuais


def _anotar_mudanca(tenant_id: str, zedtoken: str) -> None:
    """ZedToken, versão e hora da mudança — o que o backend lê para não servir
    decisão velha do cache (funcoesautorizacao/chaves.py)."""
    try:
        chaves.marcar_mudanca(_redis(), tenant_id, zedtoken, time.time())
    except Exception:  # noqa: BLE001 - o Watch do invalidador cobre a mesma mudança
        logger.warning("pdp.anotacao_falhou tenant=%s", tenant_id, exc_info=True)


def _publicar_fichas(tenant_id) -> None:
    """Fase 4: a ficha da empresa e das pessoas vai ao Redis no mesmo ciclo
    (`identity/fichas.py`). Falha aqui não impede a escrita no PDP."""
    from . import fichas

    try:
        fichas.publicar(tenant_id, _redis())
    except Exception:  # noqa: BLE001 - a volta periódica publica de novo
        logger.warning("fichas.publicacao_falhou tenant=%s", tenant_id, exc_info=True)


def reconciliar_tenant(tenant_id, cli: ClienteSpiceDB | None = None) -> dict:
    """Deixa o PDP igual às tabelas para uma empresa, e publica as fichas dela.
    Devolve o que mudou no PDP."""
    _publicar_fichas(tenant_id)
    cli = cli or cliente()
    tid = str(tenant_id)
    desejadas = relacoes_do_tenant(tenant_id)
    atuais = _relacoes_no_pdp(cli, tid)
    tocar = sorted(desejadas - atuais)
    remover = sorted(atuais - desejadas)
    if tocar or remover:
        token = cli.escrever(tocar=tocar, remover=remover)
        _anotar_mudanca(tid, token)
        logger.info("pdp.reconciliado tenant=%s tocadas=%d removidas=%d",
                    tid, len(tocar), len(remover))
    return {"tenant": tid, "tocadas": len(tocar), "removidas": len(remover)}


def reconciliar_plataforma(cli: ClienteSpiceDB | None = None) -> dict:
    cli = cli or cliente()
    desejadas = relacoes_da_plataforma()
    atuais = set(cli.ler("plataforma", ID_PLATAFORMA))
    tocar, remover = sorted(desejadas - atuais), sorted(atuais - desejadas)
    if tocar or remover:
        cli.escrever(tocar=tocar, remover=remover)
        # O supervisor muda a resposta de toda empresa — sobe a versão global.
        try:
            _redis().incr(chaves.VERSAO_GLOBAL)
        except Exception:  # noqa: BLE001
            logger.warning("pdp.anotacao_global_falhou", exc_info=True)
    return {"tocadas": len(tocar), "removidas": len(remover)}


def remover_tenant(tenant_id: str, cli: ClienteSpiceDB | None = None) -> int:
    """Apaga do PDP tudo de uma empresa que não existe mais na IAM."""
    cli = cli or cliente()
    try:
        from . import fichas

        fichas.apagar_empresa(tenant_id, _redis())
    except Exception:  # noqa: BLE001
        logger.warning("fichas.remocao_falhou tenant=%s", tenant_id, exc_info=True)
    atuais = _relacoes_no_pdp(cli, tenant_id)
    if atuais:
        token = cli.escrever(remover=sorted(atuais))
        _anotar_mudanca(tenant_id, token)
    return len(atuais)


def reconciliar_tudo(cli: ClienteSpiceDB | None = None) -> dict:
    """Toda empresa, o supervisor, e as empresas que sumiram da IAM."""
    from .models import Tenant

    cli = cli or cliente()
    ids = {str(t) for t in Tenant.objects.values_list("id", flat=True)}
    resumo = {"tenants": 0, "tocadas": 0, "removidas": 0, "orfaos": 0}
    for tid in sorted(ids):
        r = reconciliar_tenant(tid, cli)
        resumo["tenants"] += 1
        resumo["tocadas"] += r["tocadas"]
        resumo["removidas"] += r["removidas"]
    # `modulo_base` e não `empresa`: toda empresa tem o objeto da fundação, mas
    # só a que tem gente ativa tem relação em `empresa`.
    no_pdp = {rel.id for rel in cli.ler(tipo_do_modulo("base"))}
    for orfao in sorted(no_pdp - ids):
        resumo["removidas"] += remover_tenant(orfao, cli)
        resumo["orfaos"] += 1
    try:
        from . import fichas

        resumo["fichas_orfas"] = fichas.limpar_orfas(_redis())
    except Exception:  # noqa: BLE001 - a próxima volta tenta de novo
        logger.warning("fichas.limpeza_falhou", exc_info=True)
    plataforma = reconciliar_plataforma(cli)
    resumo["tocadas"] += plataforma["tocadas"]
    resumo["removidas"] += plataforma["removidas"]
    return resumo


def garantir_esquema(cli: ClienteSpiceDB | None = None) -> None:
    """Grava o schema gerado do catálogo. Sempre: o SpiceDB reformata o texto ao
    devolvê-lo, então comparar não diz nada, e regravar o mesmo schema é inócuo.
    Um schema que apagaria relação com dado é recusado pelo próprio SpiceDB."""
    (cli or cliente()).escrever_esquema(funcoesautorizacao.texto_do_esquema())


# --- A escrita da tela, ao fim da transação -----------------------------------


def marcar_pendente(tenant_id) -> None:
    try:
        _redis().sadd(chaves.TENANTS_PENDENTES, str(tenant_id))
    except Exception:  # noqa: BLE001
        logger.error(
            "pdp.pendente_nao_marcado tenant=%s — a volta periódica acerta", tenant_id,
            exc_info=True,
        )


def _sincronizar_ou_adiar(tenant_id) -> None:
    try:
        reconciliar_tenant(tenant_id)
    except ErroDoPdp:
        logger.warning("pdp.escrita_adiada tenant=%s", tenant_id, exc_info=True)
        marcar_pendente(tenant_id)
    except Exception:  # noqa: BLE001 - a troca de papel já foi gravada; o PDP se acerta depois
        logger.exception("pdp.escrita_falhou tenant=%s", tenant_id)
        marcar_pendente(tenant_id)


def agendar(tenant_id) -> None:
    """Reconcilia o tenant quando a transação atual confirmar — uma vez só, por
    mais que a operação mexa em dez linhas dele.

    **A deduplicação não guarda estado próprio**: olha os callbacks que a própria
    transação já registrou. A primeira versão usava um conjunto por thread,
    esvaziado pelo callback — e um rollback descarta o callback sem rodá-lo, então
    o tenant ficava preso no conjunto e as trocas seguintes dele, naquela thread,
    deixavam de chegar ao PDP até a volta periódica.
    """
    if not ativo() or not tenant_id:
        return
    chave = str(tenant_id)
    conexao = transaction.get_connection()
    if conexao.in_atomic_block and any(
        getattr(registro[1], "_pdp_tenant", None) == chave for registro in conexao.run_on_commit
    ):
        return

    def executar():
        _sincronizar_ou_adiar(chave)

    executar._pdp_tenant = chave
    transaction.on_commit(executar)


def agendar_plataforma() -> None:
    if not ativo():
        return

    def executar():
        try:
            reconciliar_plataforma()
        except Exception:  # noqa: BLE001
            logger.warning("pdp.plataforma_adiada", exc_info=True)

    transaction.on_commit(executar)


def drenar_pendentes(cli: ClienteSpiceDB | None = None) -> int:
    """Refaz os tenants cuja escrita falhou. Devolve quantos acertou."""
    cli = cli or cliente()
    acertados = 0
    while True:
        tid = _redis().spop(chaves.TENANTS_PENDENTES)
        if not tid:
            return acertados
        try:
            reconciliar_tenant(tid, cli)
            acertados += 1
        except Exception:
            _redis().sadd(chaves.TENANTS_PENDENTES, tid)
            raise
