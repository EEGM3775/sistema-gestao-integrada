# backend/modulomaps/serializers.py
"""Serializers do Maps.

Duas coisas atravessam todos eles:

1. **Precisão e procedência viajam junto do ponto.** Nenhum serializer devolve
   coordenada crua — `precisao_rotulo` acompanha, porque a tela precisa desenhar
   pin de porta e pin de centroide de município de formas diferentes (planta §5).
2. **Rótulo da entidade vinculada vem resolvido.** Sem `vinculo_rotulo`, o
   frontend precisaria de N chamadas para escrever "Obra Residencial Aurora" ao
   lado do pin — e o mapa da empresa é exatamente uma lista de pins de coisas
   diferentes.
"""
from rest_framework import serializers

from nucleo.tenant_validators import TenantScopedModelSerializer

from .campos import GeometriaField, PontoField
from .models import (
    Camada, Feicao, Geofence, Local, Ortofoto, ParadaRota, PlanoVoo, Rota,
)


# ---------------------------------------------------------------------------
# A unidade vista do mapa
# ---------------------------------------------------------------------------
def detalhe_da_unidade(local) -> dict | None:
    """O que o Maps precisa saber de uma unidade imobiliária, e não sabia.

    Um lote no mapa vinha com área e mais nada. **Área não descreve terreno**: o
    que o contrato, a matrícula e o vizinho reconhecem é *quanto mede cada lado*
    e *com quem cada lado divide* — e o lado da frente é a rua, que é de onde sai
    o endereço. O cadastro da unidade já guarda tudo isso
    (`empreendimentos.Unidade`, campos `medida_*`/`confrontante_*`); o que
    faltava era o mapa mostrar.

    `rua_confere` é a checagem que o pedido pede por extenso: a rua da frente
    tem de bater com o endereço. `None` quando não há como comparar — cadastro
    incompleto não é cadastro errado, e acusar divergência onde só falta dado
    ensina a ignorar o aviso.
    """
    unidade = getattr(local, "unidade", None)
    if unidade is None:
        return None
    from . import services

    return {
        "unidade_id": unidade.pk,
        "rotulo": unidade.rotulo,
        "empreendimento": (
            unidade.empreendimento.empreendimento if unidade.empreendimento_id else ""
        ),
        "tipo": unidade.tipo,
        "situacao": unidade.situacao,
        "situacao_rotulo": unidade.get_situacao_display(),
        "area_privativa": str(unidade.area_privativa) if unidade.area_privativa is not None else None,
        "area_total": str(unidade.area_total) if unidade.area_total is not None else None,
        "endereco": unidade.endereco,
        "rua": unidade.confrontante_frente,
        "confrontacoes": unidade.confrontacoes,
        "memorial": unidade.descricao_confrontacoes,
        "rua_confere": services.rua_confere(unidade, local),
    }


class LocalSerializer(TenantScopedModelSerializer):
    ponto = PontoField(required=False, allow_null=True)
    area = GeometriaField(required=False, allow_null=True, tipos=("Polygon",))
    precisao_rotulo = serializers.CharField(source="get_precisao_display", read_only=True)
    fonte_rotulo = serializers.CharField(source="get_fonte_display", read_only=True)
    vinculo_rotulo = serializers.SerializerMethodField()
    endereco_completo = serializers.CharField(source="endereco_formatado", read_only=True)
    unidade_detalhe = serializers.SerializerMethodField()

    class Meta:
        model = Local
        fields = "__all__"
        read_only_fields = ["tenant", "geocodificado_em", "criado_em", "atualizado_em"]

    def get_vinculo_rotulo(self, obj) -> str:
        alvo = obj.obra or obj.empreendimento or obj.fornecedor or obj.local_estoque or obj.unidade
        return str(alvo) if alvo else ""

    def get_unidade_detalhe(self, obj):
        """Medidas, confrontações e a conferência da rua — `null` fora de unidade."""
        return detalhe_da_unidade(obj)

    def validate(self, dados):
        """O `tipo` tem de bater com a FK preenchida.

        A trava existe no banco (CheckConstraint), mas um `IntegrityError` vira
        500 e mensagem de driver. Aqui vira 400 com o nome do campo que falta.
        """
        instancia = getattr(self, "instance", None)

        def valor(campo):
            return dados.get(campo, getattr(instancia, campo, None) if instancia else None)

        tipo = valor("tipo") or Local.Tipo.AVULSO
        if tipo != Local.Tipo.AVULSO and not valor(tipo):
            raise serializers.ValidationError(
                {tipo: f"Obrigatório quando o tipo do local é '{tipo}'."}
            )
        return dados


class LocalResumoSerializer(serializers.ModelSerializer):
    """Versão enxuta para o mapa da empresa — só o que desenha um pin.

    Existe separada porque o mapa carrega centenas de locais de uma vez e o
    serializer completo traria endereço estruturado inteiro para cada um.
    """

    ponto = PontoField()
    precisao_rotulo = serializers.CharField(source="get_precisao_display", read_only=True)
    vinculo_rotulo = serializers.SerializerMethodField()
    distancia_km = serializers.SerializerMethodField()

    unidade_detalhe = serializers.SerializerMethodField()

    class Meta:
        model = Local
        fields = [
            "local_id", "nome", "tipo", "ponto", "precisao", "precisao_rotulo",
            "fonte", "cidade", "uf", "vinculo_rotulo", "distancia_km",
            "unidade_detalhe",
        ]

    def get_vinculo_rotulo(self, obj) -> str:
        alvo = obj.obra or obj.empreendimento or obj.fornecedor or obj.local_estoque or obj.unidade
        return str(alvo) if alvo else ""

    def get_unidade_detalhe(self, obj):
        """`null` para os outros tipos — e é `null` na maioria das linhas, então
        não pesa: o custo é o `select_related("unidade")` que a view já faz."""
        return detalhe_da_unidade(obj)

    def get_distancia_km(self, obj):
        """Só existe quando a consulta foi "o que está perto de X" (`proximos`)."""
        distancia = getattr(obj, "distancia", None)
        return round(distancia.km, 2) if distancia is not None else None


class CamadaSerializer(TenantScopedModelSerializer):
    total_feicoes = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Camada
        fields = "__all__"
        read_only_fields = ["tenant", "criado_em"]


class FeicaoSerializer(TenantScopedModelSerializer):
    geom = GeometriaField()
    camada_nome = serializers.CharField(source="camada.nome", read_only=True)
    camada_cor = serializers.CharField(source="camada.cor", read_only=True)

    class Meta:
        model = Feicao
        fields = "__all__"
        read_only_fields = ["tenant", "criado_em"]


class OrtofotoSerializer(TenantScopedModelSerializer):
    bbox = GeometriaField(tipos=("Polygon",))
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    # Idade do voo é o que responde "esta ortofoto ainda vale?" — é a pergunta
    # que gera a fila de decisão "ortofoto vencida", não a data crua.
    dias_desde_voo = serializers.SerializerMethodField()

    class Meta:
        model = Ortofoto
        fields = "__all__"
        read_only_fields = ["tenant", "criado_em"]

    def get_dias_desde_voo(self, obj) -> int:
        from django.utils import timezone

        return (timezone.localdate() - obj.data_voo).days


class PlanoVooSerializer(TenantScopedModelSerializer):
    area = GeometriaField(tipos=("Polygon",))
    linha = GeometriaField(read_only=True)
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    tipo_rotulo = serializers.CharField(source="get_tipo_display", read_only=True)

    class Meta:
        model = PlanoVoo
        fields = "__all__"
        read_only_fields = [
            "tenant", "criado_em", "linha", "waypoints", "distancia_m",
            "duracao_min", "fotos_estimadas", "calculado_em", "altura_m",
        ]


class ParadaRotaSerializer(TenantScopedModelSerializer):
    local_nome = serializers.CharField(source="local.nome", read_only=True)
    local_ponto = PontoField(source="local.ponto", read_only=True)

    class Meta:
        model = ParadaRota
        fields = "__all__"
        read_only_fields = ["tenant", "chegada_estimada_s"]


class RotaSerializer(TenantScopedModelSerializer):
    linha = GeometriaField(read_only=True)
    paradas = ParadaRotaSerializer(many=True, read_only=True)
    # A rota nasce com as paradas num POST só. Sem isto a tela teria de criar a
    # rota e depois uma parada por requisição — e uma falha no meio deixava uma
    # rota pela metade, que o otimizador ordenaria como se estivesse completa.
    # Na edição, a lista SUBSTITUI as paradas (na ordem enviada).
    paradas_locais = serializers.ListField(
        child=serializers.IntegerField(min_value=1), write_only=True, required=False,
    )
    origem_nome = serializers.CharField(source="origem.nome", read_only=True)
    procedencia_rotulo = serializers.CharField(source="get_procedencia_display", read_only=True)
    distancia_km = serializers.SerializerMethodField()

    class Meta:
        model = Rota
        fields = "__all__"
        read_only_fields = [
            "tenant", "criado_em", "linha", "distancia_m", "duracao_s",
            "procedencia", "otimizada_em",
        ]

    def get_distancia_km(self, obj):
        return round(float(obj.distancia_m) / 1000, 1) if obj.distancia_m else None

    def validate_paradas_locais(self, ids):
        """Só locais desta empresa, sem repetição — a mesma régua da origem."""
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError("Um local aparece mais de uma vez nas paradas.")
        request = self.context.get("request")
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        achados = set(
            Local.objects.filter(tenant_id=tenant_id, pk__in=ids).values_list("pk", flat=True)
        )
        faltando = [i for i in ids if i not in achados]
        if faltando:
            raise serializers.ValidationError(f"Locais inexistentes nesta empresa: {faltando}.")
        return ids

    def validate(self, dados):
        origem = dados.get("origem") or getattr(self.instance, "origem", None)
        if origem is not None and origem.pk in (dados.get("paradas_locais") or []):
            raise serializers.ValidationError(
                {"paradas_locais": "A origem não pode ser também uma parada."}
            )
        return super().validate(dados)

    def _gravar_paradas(self, rota, ids):
        from django.db import transaction

        with transaction.atomic():
            rota.paradas.all().delete()
            ParadaRota.objects.bulk_create([
                ParadaRota(tenant_id=rota.tenant_id, rota=rota, local_id=local_id, ordem=ordem)
                for ordem, local_id in enumerate(ids, start=1)
            ])
            # Paradas novas = traçado velho. A linha e os números da rota
            # anterior não descrevem mais esta sequência.
            rota.linha = rota.distancia_m = rota.duracao_s = None
            rota.procedencia = ""
            rota.save(update_fields=["linha", "distancia_m", "duracao_s", "procedencia"])

    def create(self, dados):
        ids = dados.pop("paradas_locais", None)
        rota = super().create(dados)
        if ids:
            self._gravar_paradas(rota, ids)
        return rota

    def update(self, instancia, dados):
        ids = dados.pop("paradas_locais", None)
        rota = super().update(instancia, dados)
        if ids is not None:
            self._gravar_paradas(rota, ids)
        return rota


class GeofenceSerializer(TenantScopedModelSerializer):
    area = GeometriaField(tipos=("Polygon",), required=False)
    local_nome = serializers.CharField(source="local.nome", read_only=True)

    class Meta:
        model = Geofence
        fields = "__all__"
        read_only_fields = ["tenant", "criado_em"]
