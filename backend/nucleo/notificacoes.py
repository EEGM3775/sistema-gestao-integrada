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


def criar_notificacao(*, user, tenant_id, titulo, mensagem="", tipo=Notificacao.Tipo.SISTEMA, url=""):
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
    )
