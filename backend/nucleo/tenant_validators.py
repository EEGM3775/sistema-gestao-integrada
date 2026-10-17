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
from django.db.models import Q, UniqueConstraint
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

#: A condição que a lixeira (D116) acrescentou a 17 `UniqueConstraint`s: a
#: unicidade vale **entre os vivos**, para que um CPF na lixeira não fique
#: segurando o recadastro por 15 dias.
#:
#: Ela é tratada à parte das demais condições por um motivo exato: o queryset do
#: validador é o `_default_manager`, e nos modelos `Excluivel` esse gerente
#: **já** filtra a lápide. Ou seja, a condição não precisa ser reproduzida — ela
#: já está no queryset. Qualquer outra condição continua sendo motivo para pular,
#: porque aí o queryset de fato não a representa.
CONDICAO_DA_LAPIDE = Q(excluido_em__isnull=True)


class TenantReadOnlyFieldMixin:
    """Torna o campo `tenant` **read-only** sempre que ele estiver exposto no
    serializer (típico de `fields='__all__'`). Fecha o achado **D3**: com `tenant`
    NOT NULL (Fase 8.2) o DRF passou a **exigir `tenant` no payload** do POST, mas
    quem o injeta é o `TenantScopedViewSetMixin.perform_create` — **depois** do
    `is_valid()`. Sem isto, todo POST de recurso tenant-scoped com `__all__`
    respondia **400 "tenant é obrigatório"** (o front nunca envia tenant).

    No-op quando o modelo não tem campo `tenant` — seguro de herdar amplamente.
    Herde **antes** de `ModelSerializer` para que `super().get_fields()` resolva.
    """

    def get_fields(self):
        fields = super().get_fields()
        tenant_field = fields.get("tenant")
        if tenant_field is not None:
            tenant_field.read_only = True
            tenant_field.required = False
        return fields


class TenantScopedUniqueTogetherValidator(UniqueTogetherValidator):
    """`UniqueTogetherValidator` restrito ao tenant do request.

    `fields` são os campos do constraint **sem** o `tenant` — a unicidade dos
    demais é verificada dentro do tenant do usuário autenticado.

    Mensagem curta, no campo: o texto padrão do DRF ("Os campos tenant, email
    devem criar um set único") não diz nada a quem preenche.
    """
    message = "Já cadastrado."

    def __call__(self, attrs, serializer):
        try:
            super().__call__(attrs, serializer)
        except serializers.ValidationError as exc:
            if len(self.fields) == 1:
                raise serializers.ValidationError({self.fields[0]: [self.message]}) from exc
            raise

    def filter_queryset(self, attrs, queryset, serializer):
        queryset = super().filter_queryset(attrs, queryset, serializer)
        request = getattr(serializer, "context", {}).get("request")
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        if tenant_id is not None:
            queryset = queryset.filter(tenant_id=tenant_id)
        return queryset


class TenantScopedUniqueSerializerMixin(TenantReadOnlyFieldMixin):
    """Reintroduz, por-tenant, as validações de unicidade que o DRF descarta
    quando o `UniqueConstraint` inclui `tenant` — **e** força `tenant` read-only
    (via `TenantReadOnlyFieldMixin`, achado D3), já que ambos derivam do `tenant`
    ser injetado no servidor.

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
            if "tenant" not in constraint.fields:
                continue
            # Condição nenhuma, ou exatamente a da lápide (que o `_default_manager`
            # já aplica). Sem esta exceção, pôr a lixeira nos 7 módulos teria
            # rebaixado 17 duplicatas de **400 com o campo apontado** para **500
            # com `IntegrityError`** — o defeito que este arquivo inteiro existe
            # para evitar, reintroduzido pela porta dos fundos.
            if constraint.condition is not None and constraint.condition != CONDICAO_DA_LAPIDE:
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


class TenantScopedModelSerializer(TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """Base única p/ serializers de modelos tenant-scoped: `tenant` read-only (D3)
    + unicidade por-tenant (Fase 8.3). Prefira herdar desta base a repetir os
    mixins em cada serializer."""
