"""Trilha de auditoria — Fase 9.E. Helper de gravação + mixin de ViewSet.

A camada de rastreabilidade do AD-9: registra QUEM/O QUÊ/QUAL/QUANDO nas
operações sensíveis de **RH** e **financeiro**, em linhas imutáveis
([AuditLog](models.py)). Dois pontos de uso:

- **`registrar_auditoria(...)`** — chamada explícita nos *choke points* de
  domínio (ex.: `ContaReceber.dar_baixa`, endpoints LGPD). Precisa registrar
  algo que não é um CRUD de ViewSet.
- **`AuditedModelViewSetMixin`** — *opt-in* num `ModelViewSet`: audita
  automaticamente create/update/destroy. Declare-o **antes** do
  `TenantScopedViewSetMixin` na herança (ver docstring do mixin).

**Princípios:**
- A auditoria **nunca derruba** a operação auditada: falha ao gravar é logada,
  não propagada.
- Não grava **valor de campo sensível** — só metadados não-PII. A 9.C
  ([field_masking.py](field_masking.py)) mascara PII; a trilha não pode
  recriá-la em texto puro.
- `AuditLog` é tenant-scoped (NOT NULL) e sob RLS fail-closed: a gravação herda
  o `tenant` do objeto auditado e roda no contexto RLS já armado pela request.
"""
from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def registrar_auditoria(*, acao, instance=None, modelo=None, objeto_id=None,
                        usuario=None, tenant=None, detalhes=None):
    """Grava uma linha de auditoria. Retorna o `AuditLog` criado (ou `None`).

    Deriva `modelo`/`objeto_id`/`tenant` de `instance` quando informado; o
    chamador pode sobrepor qualquer um. `usuario` só é vinculado se autenticado
    (webhook/job sem usuário → `None`, mas o evento é registrado assim mesmo).
    """
    from .models import AuditLog  # lazy: evita ciclo de import na carga do app

    if instance is not None:
        modelo = modelo or f"{instance._meta.app_label}.{instance._meta.object_name}"
        if objeto_id is None:
            objeto_id = getattr(instance, "pk", None)
        if tenant is None:
            tenant = getattr(instance, "tenant", None)

    if tenant is None:
        # AuditLog é tenant-scoped (NOT NULL): sem tenant não há isolamento
        # possível. Não quebra a operação de negócio — só registra o gap.
        logger.warning(
            "Auditoria ignorada (sem tenant): acao=%s modelo=%s obj=%s",
            acao, modelo, objeto_id,
        )
        return None

    u = usuario if (usuario is not None and getattr(usuario, "is_authenticated", False)) else None
    try:
        # Savepoint próprio: se o INSERT falhar (RLS, constraint…), rola de volta
        # SÓ este ponto — sem envenenar a transação do request (o que derrubaria
        # a operação auditada apesar do except). É o que torna o fail-safe real.
        with transaction.atomic():
            return AuditLog.objects.create(
                tenant=tenant,
                usuario=u,
                usuario_nome=(getattr(u, "username", "") or ""),
                acao=str(acao),
                modelo=modelo or "",
                objeto_id=str(objeto_id if objeto_id is not None else ""),
                detalhes=detalhes,
            )
    except Exception:
        # A trilha é defesa-em-profundidade: nunca deve derrubar a operação
        # auditada. Falha de gravação é logada e engolida.
        logger.exception(
            "Falha ao gravar AuditLog: acao=%s modelo=%s obj=%s", acao, modelo, objeto_id
        )
        return None


def _valor_campo(obj, campo):
    """Leitura defensiva de um atributo para o diff de campos (nunca levanta)."""
    try:
        return getattr(obj, campo, None)
    except Exception:
        return None


class AuditedModelViewSetMixin:
    """Audita create/update/destroy de um `ModelViewSet` (opt-in).

    Declare-o **antes** do `TenantScopedViewSetMixin` na herança, para que o
    `perform_*` do tenant rode primeiro (injeta o `tenant` e reforça o
    isolamento) e a auditoria registre o objeto já persistido::

        class FuncionarioViewSet(AuditedModelViewSetMixin, TenantScopedViewSetMixin,
                                 viewsets.ModelViewSet):
            ...

    Registra só QUEM/O QUÊ/QUAL/QUANDO — não grava valores de campos. Para
    anexar contexto não-PII do domínio, sobrescreva
    ``audit_detalhes(instance, acao)``.
    """

    def audit_detalhes(self, instance, acao):  # noqa: D401 - hook opcional
        return None

    def _auditar(self, acao, instance):
        registrar_auditoria(
            acao=acao,
            instance=instance,
            usuario=getattr(self.request, "user", None),
            detalhes=self.audit_detalhes(instance, acao),
        )

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._auditar("criar", serializer.instance)

    def perform_update(self, serializer):
        # Captura os valores ANTES do save para registrar QUAIS campos mudaram —
        # só os nomes, nunca os valores (não recria PII em texto puro na trilha).
        instance = serializer.instance
        campos = list(getattr(serializer, "validated_data", None) or {})
        antes = {c: _valor_campo(instance, c) for c in campos}
        super().perform_update(serializer)
        obj = serializer.instance
        alterados = [c for c in campos if antes.get(c) != _valor_campo(obj, c)]
        detalhes = self.audit_detalhes(obj, "atualizar")
        if alterados:
            detalhes = {**(detalhes or {}), "campos_alterados": alterados}
        registrar_auditoria(
            acao="atualizar", instance=obj,
            usuario=getattr(self.request, "user", None), detalhes=detalhes,
        )

    def perform_destroy(self, instance):
        # Captura a identidade ANTES do delete (o pk some depois).
        modelo = f"{instance._meta.app_label}.{instance._meta.object_name}"
        objeto_id = instance.pk
        tenant = getattr(instance, "tenant", None)
        detalhes = self.audit_detalhes(instance, "excluir")
        super().perform_destroy(instance)
        registrar_auditoria(
            acao="excluir", modelo=modelo, objeto_id=objeto_id, tenant=tenant,
            usuario=getattr(self.request, "user", None), detalhes=detalhes,
        )


class PiiReadAuditMixin:
    """Audita a **leitura** de um registro sensível (`retrieve`) como
    ``visualizar_pii``. Aplique aos ViewSets de PII dedicada (dado médico/
    bancário, ASO) — declare-o antes dos demais mixins.

    `list` não é auditada (evita uma linha por página de resultados); o evento
    relevante para a LGPD é **abrir a ficha de um titular específico**. A
    exportação LGPD (dump integral) é auditada à parte, como ``exportar_lgpd``.
    """

    pii_read_acao = "visualizar_pii"

    def retrieve(self, request, *args, **kwargs):
        from rest_framework.response import Response

        instance = self.get_object()
        registrar_auditoria(
            acao=self.pii_read_acao, instance=instance,
            usuario=getattr(request, "user", None),
        )
        return Response(self.get_serializer(instance).data)
