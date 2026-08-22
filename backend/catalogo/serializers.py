# backend/catalogo/serializers.py
from rest_framework import serializers

from nucleo.tenant_validators import TenantScopedModelSerializer

from .models import ComponenteComposicao, Item, TipoItemProprio


class ItemSerializer(TenantScopedModelSerializer):
    tipo_nome = serializers.CharField(source="get_tipo_display", read_only=True)
    tipo_proprio_nome = serializers.CharField(source="tipo_proprio.nome", read_only=True, default=None)

    class Meta:
        model = Item
        fields = "__all__"
        # `tipo` continua editável para quem não usa tipo próprio; quando o tipo
        # próprio está preenchido, o `save()` do model reescreve o `tipo` pela
        # natureza dele — a API não precisa repetir a regra, e assim não existe
        # um segundo lugar para ela divergir.
        #
        # `publicacao_referencia` é procedência, não cadastro: quem escreve é a
        # adoção, e deixá-la editável pela API abriria a porta para o item dizer
        # que veio de uma edição da qual ele não veio.
        read_only_fields = ["tenant", "publicacao_referencia"]


class TipoItemProprioSerializer(TenantScopedModelSerializer):
    natureza_nome = serializers.CharField(source="get_natureza_display", read_only=True)
    itens_com_este_tipo = serializers.SerializerMethodField()

    class Meta:
        model = TipoItemProprio
        fields = "__all__"
        read_only_fields = ["tenant"]

    def get_itens_com_este_tipo(self, obj) -> int:
        """Quantos itens já usam este tipo — é o que diz se mexer nele é
        inofensivo ou se vai mudar o comportamento de trezentos cadastros."""
        return obj.itens.count()

    def validate(self, attrs):
        """As regras do `clean()` valem também na API — a tela não é o único
        caminho até esta tabela, e a incoerência que elas barram vira preço
        errado, não tela feia."""
        def campo(nome, padrao=None):
            if nome in attrs:
                return attrs[nome]
            return getattr(self.instance, nome, padrao)

        TipoItemProprio(
            natureza=campo("natureza", TipoItemProprio._meta.get_field("natureza").default),
            leva_encargo_social=bool(campo("leva_encargo_social", False)),
            compravel=bool(campo("compravel", True)),
            estocavel=bool(campo("estocavel", True)),
        ).clean()
        return attrs


class ComponenteComposicaoSerializer(TenantScopedModelSerializer):
    item_filho_descricao = serializers.CharField(source="item_filho.descricao", read_only=True)
    item_filho_unidade = serializers.CharField(source="item_filho.unidade", read_only=True)

    class Meta:
        model = ComponenteComposicao
        fields = "__all__"
        read_only_fields = ["tenant"]
