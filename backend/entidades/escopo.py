"""O recorte por entidade no ERP — docs/modulos/entidades.md §4.

A permissão de **ação** (`erp.conta_pagar.view`…) continua do catálogo; isto é o
escopo de **objeto** por cima dela: de quais entidades a pessoa vê e opera os
títulos. O administrador vê tudo; com uma entidade do grupo só não há recorte.

`alcance()` devolve `None` quando não há recorte — e o chamador não filtra. O
conjunto é calculado uma vez por requisição e guardado no próprio usuário.
"""
from __future__ import annotations

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied, ValidationError

from nucleo import autorizacao

from .models import ConcessaoEmpreendimento, ConcessaoEntidade, Entidade, ParticipacaoEmpreendimento
from .regras import modo_simples

_CACHE = "_alcance_entidades"
_CACHE_EMP = "_empreendimentos_concedidos"


def sem_recorte(user) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or autorizacao.administra(user):
        return True
    return modo_simples(user.tenant_id)


def alcance(user) -> set[int] | None:
    """As entidades cujo ERP a pessoa alcança; `None` = todas (sem recorte)."""
    if hasattr(user, _CACHE):
        return getattr(user, _CACHE)
    if sem_recorte(user):
        valor = None
    else:
        concessoes = list(ConcessaoEntidade.objects.filter(usuario=user).values_list("entidade_id", "incluir_filiais"))
        ids = {e for e, _ in concessoes}
        com_filiais = [e for e, incluir in concessoes if incluir]
        if com_filiais:
            ids |= set(Entidade.objects.filter(matriz_id__in=com_filiais).values_list("entidade_id", flat=True))
        # A administradora de um empreendimento vê a entidade própria dele inteira.
        if ids:
            ids |= set(
                ParticipacaoEmpreendimento.objects.filter(
                    entidade_id__in=ids, administradora=True, empreendimento__entidade_propria__isnull=False,
                ).values_list("empreendimento__entidade_propria_id", flat=True)
            )
        valor = ids
    try:
        setattr(user, _CACHE, valor)
    except AttributeError:  # pragma: no cover - usuário anônimo/imutável
        pass
    return valor


def empreendimentos_concedidos(user) -> set[int]:
    if hasattr(user, _CACHE_EMP):
        return getattr(user, _CACHE_EMP)
    ids = set(ConcessaoEmpreendimento.objects.filter(usuario=user).values_list("empreendimento_id", flat=True))
    try:
        setattr(user, _CACHE_EMP, ids)
    except AttributeError:  # pragma: no cover
        pass
    return ids


def esquecer(user) -> None:
    for chave in (_CACHE, _CACHE_EMP):
        if hasattr(user, chave):
            delattr(user, chave)


def filtro(user, campo_entidade="entidade", campo_empreendimento="empreendimento") -> Q | None:
    """O `Q` do recorte, ou `None` sem recorte. O empreendimento concedido entra
    pelo recorte dele: títulos do empreendimento, de qualquer entidade."""
    entidades = alcance(user)
    if entidades is None:
        return None
    q = Q(**{f"{campo_entidade}__in": entidades})
    if campo_empreendimento:
        emps = empreendimentos_concedidos(user)
        if emps:
            q |= Q(**{f"{campo_empreendimento}__in": emps})
    return q


def pode_na_entidade(user, entidade_id) -> bool:
    entidades = alcance(user)
    return entidades is None or entidade_id in entidades


def exigir_na_entidade(user, entidade_id, *, empreendimento_id=None) -> None:
    """Escrever num título de entidade fora do alcance é 403 — a não ser pelo
    recorte do empreendimento concedido."""
    if pode_na_entidade(user, entidade_id):
        return
    if empreendimento_id and empreendimento_id in empreendimentos_concedidos(user):
        return
    raise PermissionDenied("Você não tem acesso ao financeiro desta entidade.")


def entidade_do_parametro(request) -> int | None:
    bruto = request.query_params.get("entidade")
    if bruto in (None, ""):
        return None
    try:
        return int(bruto)
    except (TypeError, ValueError):
        raise ValidationError({"entidade": "Entidade inválida."})


class EscopoDeEntidadeMixin:
    """Recorte por entidade num ViewSet do ERP (antes do `TenantScopedViewSetMixin`).

    Lista e detalhe só mostram o que a pessoa alcança; `?entidade=` estreita para
    uma entidade (a barra de camada da tela). Gravar fora do alcance é 403.
    """

    campo_entidade = "entidade"
    campo_empreendimento_escopo: str | None = "empreendimento"

    def get_queryset(self):
        return self.recortar(super().get_queryset())

    def recortar(self, qs):
        user = getattr(self.request, "user", None)
        q = filtro(user, self.campo_entidade, self.campo_empreendimento_escopo)
        if q is not None:
            qs = qs.filter(q)
        entidade = entidade_do_parametro(self.request)
        if entidade is not None:
            qs = qs.filter(**{self.campo_entidade: entidade})
        return qs

    def _conferir_escrita(self, instance):
        if instance is None:
            return
        caminho = self.campo_entidade.split("__")
        alvo = instance
        for parte in caminho[:-1]:
            alvo = getattr(alvo, parte, None)
            if alvo is None:
                return
        entidade_id = getattr(alvo, f"{caminho[-1]}_id", None)
        if entidade_id is None:
            return
        exigir_na_entidade(
            self.request.user, entidade_id, empreendimento_id=getattr(instance, "empreendimento_id", None),
        )

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._conferir_escrita(serializer.instance)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._conferir_escrita(serializer.instance)
