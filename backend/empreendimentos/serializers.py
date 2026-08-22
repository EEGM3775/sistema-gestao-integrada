# backend/empreendimentos/serializers.py
# Este arquivo contém os serializadores para o aplicativo 'empreendimentos'.
# Serializadores convertem objetos complexos, como instâncias de modelos Django,
# em tipos de dados nativos do Python que podem ser facilmente renderizados em JSON para a API.

from rest_framework import serializers
from funcoesimpexp.entrega import ArquivoGateadoSerializerMixin
from nucleo.tenant_validators import TenantScopedUniqueSerializerMixin
from nucleo.upload_validation import UploadValidationMixin
from .impexp import ESPECIE_XML, RECURSO_CUSTO_NFE
from .models import (
    Empreendimento,
    ContaBancariaEmpreendimento,
    CustoEmpreendimento,
    Unidade,
)

class EmpreendimentoSerializer(TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """
    Serializador para o modelo Empreendimento.
    A classe Meta especifica o modelo a ser serializado e os campos a serem incluídos.
    """
    # Quantas unidades o empreendimento tem e como estão — é o que a Visão Geral
    # mostra. Vem de `annotate` na view; fora dela (criação, detalhe sem anotação)
    # cai em `None`, que a tela lê como "ainda não calculado", nunca como zero.
    unidades_total = serializers.IntegerField(read_only=True, default=None)
    unidades_disponiveis = serializers.IntegerField(read_only=True, default=None)
    unidades_vendidas = serializers.IntegerField(read_only=True, default=None)

    class Meta:
        model = Empreendimento
        fields = '__all__'  # '__all__' é um atalho para incluir todos os campos do modelo.


class UnidadeSerializer(TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """A unidade à venda. `rotulo` é o nome que ela tem em toda a plataforma."""
    rotulo = serializers.CharField(read_only=True)
    # Os cinco níveis entram com `default=''` porque compõem o `UniqueConstraint`
    # da identificação: sem default, o validador de unicidade do DRF exigiria os
    # cinco no payload — e loteamento não tem andar, prédio não tem quadra.
    quadra = serializers.CharField(required=False, allow_blank=True, default='', max_length=10)
    lote = serializers.CharField(required=False, allow_blank=True, default='', max_length=10)
    bloco_torre = serializers.CharField(required=False, allow_blank=True, default='', max_length=20)
    andar = serializers.CharField(required=False, allow_blank=True, default='', max_length=10)
    apto = serializers.CharField(required=False, allow_blank=True, default='', max_length=20)
    empreendimento_nome = serializers.CharField(source='empreendimento.empreendimento', read_only=True)
    situacao_display = serializers.CharField(source='get_situacao_display', read_only=True)
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    # Quem comprou — só aparece quando há aquisição, e é o que impede a tela de
    # oferecer para venda uma unidade que já tem dono.
    cliente_id = serializers.IntegerField(source='aquisicoes.first.cliente_id', read_only=True, default=None)
    cliente_nome = serializers.CharField(
        source='aquisicoes.first.cliente.nome_completo', read_only=True, default=None,
    )
    # As confrontações vão nas duas formas de propósito: a lista alimenta a tela
    # lado a lado, e a frase é a que o contrato copia. Derivar a frase no
    # frontend criaria uma segunda redação do mesmo memorial.
    confrontacoes = serializers.ListField(read_only=True)
    descricao_confrontacoes = serializers.CharField(read_only=True)

    class Meta:
        model = Unidade
        fields = '__all__'
        read_only_fields = ['unidade_id', 'tenant', 'data_criacao', 'data_atualizacao']

    def validate(self, attrs):
        dados = {**{
            campo: getattr(self.instance, campo, '')
            for campo in ('quadra', 'lote', 'bloco_torre', 'andar', 'apto')
        }, **attrs} if self.instance else attrs
        if not any(str(dados.get(c) or '').strip() for c in ('quadra', 'lote', 'bloco_torre', 'andar', 'apto')):
            raise serializers.ValidationError(
                "Preencha ao menos um nível da identificação (quadra, lote, bloco/torre, andar ou apto)."
            )
        return attrs

class ContaBancariaEmpreendimentoSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo ContaBancariaEmpreendimento.
    Converte os dados das contas bancárias dos empreendimentos para JSON.
    """
    class Meta:
        model = ContaBancariaEmpreendimento
        fields = '__all__'
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2 / D3)

class CustoEmpreendimentoSerializer(ArquivoGateadoSerializerMixin, UploadValidationMixin, TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """Custos do empreendimento — o XML da NF-e sai gateado (D70)."""
    arquivos_gateados = {"arquivo_xml": (RECURSO_CUSTO_NFE, ESPECIE_XML)}

    class Meta:
        model = CustoEmpreendimento
        fields = '__all__'
