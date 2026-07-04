"""
Unicidade **por-tenant** na camada DRF (Fase 8.3).

Depois que os `unique=True` globais viraram `UniqueConstraint(fields=["tenant",
…])`, o DRF **descarta** o validador automático de unicidade: o campo `tenant`
não é exposto no serializer (é injetado no servidor), então o constraint deixa
de casar com os campos do serializer. Sem tratamento, uma duplicata **dentro do
mesmo tenant** só seria pega pelo banco → `IntegrityError` → HTTP 500.

Aqui reconstruímos essa validação escopada ao tenant do request:

- `TenantScopedUniqueTogetherValidator`: igual ao do DRF, mas restringe o
  queryset ao `tenant_id` do usuário do request. Necessário inclusive porque no
  **SQLite de dev a RLS é no-op** — sem este filtro a checagem voltaria a ser
  global. No Postgres é defesa redundante à RLS (que já escopa as leituras).
- `TenantScopedUniqueSerializerMixin`: deriva um validador desses de cada
  `UniqueConstraint` do modelo que começa por `tenant`, sem boilerplate por
  campo. Basta o serializer herdar o mixin.
"""
from django.db.models import UniqueConstraint
from rest_framework.validators import UniqueTogetherValidator


class TenantScopedUniqueTogetherValidator(UniqueTogetherValidator):
    """`UniqueTogetherValidator` restrito ao tenant do request.

    `fields` são os campos do constraint **sem** o `tenant` — a unicidade dos
    demais é verificada dentro do tenant do usuário autenticado.
    """

    def filter_queryset(self, attrs, queryset, serializer):
        queryset = super().filter_queryset(attrs, queryset, serializer)
        request = getattr(serializer, "context", {}).get("request")
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        if tenant_id is not None:
            queryset = queryset.filter(tenant_id=tenant_id)
        return queryset


class TenantScopedUniqueSerializerMixin:
    """Reintroduz, por-tenant, as validações de unicidade que o DRF descarta
    quando o `UniqueConstraint` inclui `tenant`.

    Herde este mixin antes de `ModelSerializer`. Cada `UniqueConstraint` do
    modelo que comece por `tenant` e cujos demais campos estejam expostos (e
    graváveis) no serializer vira um `TenantScopedUniqueTogetherValidator`.
    """

    def get_unique_together_validators(self):
        validators = super().get_unique_together_validators()
        model = getattr(getattr(self, "Meta", None), "model", None)
        if model is None:
            return validators

        # source (nome do campo no modelo) -> nome do campo no serializer
        source_to_name = {
            field.source: name
            for name, field in self.fields.items()
            if not getattr(field, "read_only", False) and field.source
        }

        for constraint in getattr(model._meta, "constraints", []):
            if not isinstance(constraint, UniqueConstraint):
                continue
            if "tenant" not in constraint.fields or constraint.condition is not None:
                continue
            others = [f for f in constraint.fields if f != "tenant"]
            if not others or not all(f in source_to_name for f in others):
                continue
            validators.append(
                TenantScopedUniqueTogetherValidator(
                    queryset=model._default_manager,
                    fields=[source_to_name[f] for f in others],
                )
            )
        return validators
