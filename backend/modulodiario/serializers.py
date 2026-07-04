# backend/modulodiario/serializers.py
from rest_framework import serializers
from .models import DiarioObra, EntradaDiario, DocumentoDiario
from .permissions import get_funcionario, pode_moderar


class EntradaDiarioSerializer(serializers.ModelSerializer):
    autor_nome = serializers.CharField(source='autor.nome_completo', read_only=True, default=None)

    class Meta:
        model = EntradaDiario
        fields = [
            'entrada_id', 'diario_obra', 'autor', 'autor_nome', 'origem',
            'texto', 'eh_ocorrencia', 'data_criacao', 'data_atualizacao',
        ]
        read_only_fields = ['autor', 'origem', 'data_criacao', 'data_atualizacao']


class DocumentoDiarioSerializer(serializers.ModelSerializer):
    autor_nome = serializers.CharField(source='autor.nome_completo', read_only=True, default=None)
    analise_ia = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoDiario
        fields = [
            'documento_diario_id', 'diario_obra', 'autor', 'autor_nome', 'origem',
            'arquivo', 'descricao', 'data_criacao', 'analise_ia',
        ]
        read_only_fields = ['autor', 'origem', 'data_criacao']

    def get_analise_ia(self, obj):
        analise = getattr(obj, 'analise_ia', None)
        if analise is None:
            return None
        return {
            'analise_id': analise.analise_ia_id,
            'status': analise.status,
            'resultado': analise.resultado_analise,
            'data_atualizacao': analise.data_atualizacao,
        }


class DiarioObraSerializer(serializers.ModelSerializer):
    entradas = EntradaDiarioSerializer(many=True, read_only=True)
    documentos = DocumentoDiarioSerializer(many=True, read_only=True)
    criado_por_nome = serializers.CharField(source='criado_por.username', read_only=True, default=None)
    obra_nome = serializers.CharField(source='obra.nome_obra', read_only=True, default=None)
    pode_moderar = serializers.SerializerMethodField()

    class Meta:
        model = DiarioObra
        fields = [
            'diario_obra_id', 'obra', 'obra_nome', 'data', 'descricao',
            'condicoes_climaticas', 'criado_por', 'criado_por_nome',
            'data_criacao', 'data_atualizacao', 'pode_moderar',
            'entradas', 'documentos',
        ]
        read_only_fields = ['criado_por', 'data_criacao', 'data_atualizacao']

    def get_pode_moderar(self, obj):
        request = self.context.get('request')
        if request is None:
            return False
        return pode_moderar(get_funcionario(request.user), obj.obra)
