"""D17 — a trilha de identidade legível por quem audita.

`EventoSeguranca` (D11) guarda reset de senha, troca de e-mail, escalada de
privilégio, segundo fator e acesso do suporte — mas até aqui só se lia por shell
ou admin do Django. O auditor que reconstitui "admin comprometido" precisava
cruzar o `reset_assistido` daqui com o que a conta fez depois no backend, à mão.

`GET /iam/eventos-seguranca/` devolve a trilha com a mesma permissão da trilha do
backend (`plataforma.auditoria.view`), recortada pela empresa de quem pergunta, e
paginada e filtrada do mesmo jeito que `GET /api/auditoria/` — é o que deixa a
tela "Trilha de auditoria" intercalar as duas pelo horário.

Somente leitura: a linha é append-only no modelo e no banco.
"""
from __future__ import annotations

from django.db.models import Q
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO

from . import suporte
from .models import EventoSeguranca

PERMISSAO = "plataforma.auditoria.view"


class LeAuditoria(BasePermission):
    """Quem lê a trilha do backend lê esta (o admin da empresa recebe o catálogo)."""

    message = "Você não tem permissão para ler a trilha de auditoria."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and PERMISSAO in u.permissoes_efetivas())


class AuditoriaPagination(PageNumberPagination):
    page_size = PAGINA_PADRAO["auditoria"]
    page_size_query_param = "page_size"
    max_page_size = PAGINA_MAXIMA["auditoria"]


def _quando(valor):
    """(data ou data-hora, tem hora?). Só data vale o dia inteiro — e o
    `parse_datetime` do Django aceitaria "2026-10-10" como meia-noite sem fuso."""
    if not valor:
        return None, False
    if "T" not in valor and " " not in valor.strip():
        return parse_date(valor), False
    return parse_datetime(valor), True


class EventosSegurancaView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, LeAuditoria]
    pagination_class = AuditoriaPagination

    def get_queryset(self):
        u = self.request.user
        params = self.request.query_params
        qs = EventoSeguranca.objects.all()
        # A empresa de quem pergunta. O supervisor da plataforma vê a dele e as
        # que liberaram o suporte (§10.7) — a mesma régua das pessoas e papéis;
        # `?tenant=` escolhe uma delas.
        if u.is_superuser:
            qs = qs.filter(tenant_id__in=suporte.empresas_que_o_supervisor_ve(u))
            if params.get("tenant"):
                qs = qs.filter(tenant_id=params["tenant"])
        else:
            qs = qs.filter(tenant_id=u.tenant_id)

        tipo = params.get("tipo")
        if tipo:
            qs = qs.filter(tipo=tipo)
        pessoa = (params.get("pessoa") or "").strip()
        if pessoa:
            qs = qs.filter(Q(alvo_username__iexact=pessoa) | Q(autor_username__iexact=pessoa))
        desde, com_hora = _quando(params.get("desde"))
        if desde is not None:
            qs = qs.filter(**{"criado_em__gte" if com_hora else "criado_em__date__gte": desde})
        ate, com_hora = _quando(params.get("ate"))
        if ate is not None:
            qs = qs.filter(**{"criado_em__lte" if com_hora else "criado_em__date__lte": ate})
        return qs.order_by("-criado_em", "-id")

    def list(self, request, *args, **kwargs):
        pagina = self.paginate_queryset(self.get_queryset())
        rotulos = dict(EventoSeguranca.Tipo.choices)
        return self.get_paginated_response([
            {
                "id": e.pk,
                "tipo": e.tipo,
                "tipo_rotulo": str(rotulos.get(e.tipo, e.tipo)),
                "alvo_username": e.alvo_username,
                # Vazio = o próprio fluxo público (esqueci minha senha).
                "autor_username": e.autor_username,
                "ip": e.ip,
                "user_agent": e.user_agent,
                "detalhes": e.detalhes,
                "criado_em": e.criado_em,
            }
            for e in pagina
        ])
