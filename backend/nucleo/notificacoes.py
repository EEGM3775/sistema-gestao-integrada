# backend/nucleo/notificacoes.py
"""Centro de notificações in-app (Calendário, Fatia C) — helper de criação.

Ponto único para qualquer módulo emitir uma notificação para um usuário. A
primeira origem são os lembretes de evento do calendário (task Celery), mas o
helper é genérico (ex.: futuros vencimentos do ERP). A criação a partir de um
caminho **fora de request** (Celery/comando) roda sob `rls_bypass()` — a RLS
fail-closed barraria o INSERT sem contexto de tenant. O `tenant` é herdado
**explicitamente** da origem (nunca inferido de um request inexistente).
"""
from __future__ import annotations

from .models import Notificacao


def criar_notificacao(*, user, tenant_id, titulo, mensagem="", tipo=Notificacao.Tipo.SISTEMA, url="",
                      nivel=Notificacao.Nivel.SABER):
    """Cria uma `Notificacao` para `user`. `tenant_id` é obrigatório e deve vir
    da origem (ex.: `evento.tenant_id`). Deve ser chamado dentro de um contexto
    RLS válido — `rls_bypass()` nas tasks/jobs, ou a RLS do request."""
    return Notificacao.objects.create(
        user=user,
        tenant_id=tenant_id,
        titulo=titulo,
        mensagem=mensagem,
        tipo=tipo,
        url=url,
        nivel=nivel,
    )


def avisar_quem_pode(*, tenant_id, permissao, titulo, mensagem="", url="",
                     nivel=Notificacao.Nivel.SABER) -> int:
    """**Um módulo mexeu no outro: avise quem responde por ele.**

    *Regra do dono (11/10/2026): "qualquer alteração que interfira em outro
    módulo tem que ter notificação".* O PDCA que emite um título no ERP, o plano
    que abre demanda no Suprimentos, o recebimento que dá entrada no Estoque —
    quem trabalha do outro lado não estava olhando a tela onde aconteceu.

    Vai a todo usuário ativo do tenant com `permissao` (a do verbo que age sobre
    o que mudou — `docs/modulos/funcoesnotificacoes.md` §3, régua 2) e **uma vez
    por fato**: o mesmo `titulo` ainda não lido não se repete (régua 3). Devolve
    quantos avisos saíram.
    """
    from . import autorizacao
    from .models import Usuario

    enviados = 0
    for usuario in Usuario.objects.filter(tenant_id=tenant_id, is_active=True):
        if not autorizacao.pode(usuario, permissao):
            continue
        if Notificacao.objects.filter(
            user=usuario, titulo=titulo, lida_em__isnull=True,
        ).exists():
            continue
        criar_notificacao(
            user=usuario, tenant_id=tenant_id, titulo=titulo[:200],
            mensagem=mensagem, url=url, nivel=nivel,
        )
        enviados += 1
    return enviados
