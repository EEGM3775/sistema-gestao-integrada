"""A auditoria de decisão — toda decisão vira evento (§10.9, fase 4).

**Toda** decisão vai ao log estruturado (`sgi.authz.decisao`, o fluxo que a
observabilidade já recolhe); **as da classe C e todas as negações** vão também
para a tabela append-only `DecisaoAcesso`. Uma por pergunta por requisição: a
memória de `nucleo/autorizacao.py` já garante que a mesma pergunta não é
decidida duas vezes na mesma requisição.

**O evento tem campos fixos** — quem, sessão, quando, qual pergunta, sobre que
objeto, a decisão, a classe, de onde veio a resposta e o ZedToken. Não há campo
onde o conteúdo da tela possa escapar (decisão do dono, 24/09/2026).

**A gravação não acompanha a transação da requisição**: vai por uma conexão
própria (`AUTORIZACAO_AUDITORIA_BANCO`, o alias `auditoria` do settings), que
confirma na hora. A primeira versão gravava na transação da requisição — e a
E2E da fase 4 mostrou que toda negação sumia: o DRF marca rollback em toda
resposta de erro, 403 inclusive, e o `ATOMIC_REQUESTS` desfazia a linha que mais
importa guardar.

**A purga** (`purgar`, de hora em hora pelo beat) apaga o que passou da janela
do plano de cada empresa (`auditoria_decisao_retencao_dias`, com o piso legal
de 6 meses — `payment/planos.py`), identificando-se ao gatilho do banco.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from funcoesautorizacao import classes
from payment.planos import AUDITORIA_DECISAO_PISO_DIAS

from . import fichas, observability

logger = logging.getLogger("sgi.authz.decisao")


def registrar(*, quem, sid: str | None, pergunta, recurso: str, decisao: bool,
              origem: str, zedtoken: str = "") -> None:
    evento = {
        "requisicao": observability.get_request_id() or "",
        "tenant": quem.tenant_id,
        "pessoa": quem.usuario_id,
        "sid": sid or "",
        "acao": pergunta.chave,
        "recurso": recurso,
        "decisao": bool(decisao),
        "classe": pergunta.classe,
        "origem": origem,
        "zedtoken": zedtoken or "",
    }
    logger.info("authz.decisao %s", json.dumps(evento, separators=(",", ":")))
    if decisao and pergunta.classe != classes.C:
        return
    from .models import DecisaoAcesso

    try:
        DecisaoAcesso.objects.using(getattr(settings, "AUTORIZACAO_AUDITORIA_BANCO", "default")).create(
            requisicao=evento["requisicao"][:64],
            tenant_id=quem.tenant_id or None,
            usuario_id=str(quem.usuario_id)[:64],
            sid=evento["sid"][:64],
            acao=pergunta.chave[:100],
            recurso=recurso[:140],
            decisao=bool(decisao),
            classe=pergunta.classe,
            origem=origem[:20],
            zedtoken=evento["zedtoken"][:160],
        )
    except Exception:  # noqa: BLE001 - a decisão já foi tomada e está no log
        logger.exception("authz.decisao_nao_gravada acao=%s", pergunta.chave)


def janela_em_dias(tenant_id) -> int | None:
    """A janela do plano da empresa, pela ficha; sem ficha, o piso legal."""
    ficha = fichas.da_empresa(tenant_id) or {}
    quotas = ficha.get("quotas") or {}
    if "auditoria_decisao_retencao_dias" not in quotas:
        return AUDITORIA_DECISAO_PISO_DIAS
    dias = quotas["auditoria_decisao_retencao_dias"]
    return None if dias is None else max(int(dias), AUDITORIA_DECISAO_PISO_DIAS)


def purgar() -> int:
    """Apaga, empresa a empresa, o que passou da janela do plano."""
    from .models import DecisaoAcesso

    agora = timezone.now()
    apagadas = 0
    tenants = DecisaoAcesso.objects.order_by().values_list("tenant_id", flat=True).distinct()
    for tenant_id in list(tenants):
        dias = janela_em_dias(tenant_id) if tenant_id else AUDITORIA_DECISAO_PISO_DIAS
        if dias is None:
            continue  # contrato sem prazo: guarda para sempre
        limite = agora - timedelta(days=dias)
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SET LOCAL sgi.purga_auditoria_decisao = 'on'")
            # O `delete()` do queryset não passa pelo `delete()` do modelo (que
            # recusa); quem barra todo o resto é o gatilho.
            n, _ = DecisaoAcesso.objects.filter(tenant_id=tenant_id, instante__lt=limite).delete()
            apagadas += n
    return apagadas
