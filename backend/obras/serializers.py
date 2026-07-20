# backend/obras/serializers.py
# Converte os modelos do app 'obras' para o formato JSON para a API.
from rest_framework import serializers
from decimal import Decimal
from datetime import date

from nucleo.upload_validation import UploadValidationMixin

from .models import Obra, EtapaObra, DocumentoObra

class ObraSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo Obra.
    """
    progresso_ponderado = serializers.SerializerMethodField()

    class Meta:
        model = Obra
        # expõe todos os campos do modelo + progresso_ponderado calculado
        fields = [*(f.name for f in Obra._meta.fields), 'progresso_ponderado']
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2 / D3)

    def get_progresso_ponderado(self, obj: Obra) -> int:
        """Calcula o progresso da obra ponderado por valor (orcamento_previsto)
        e por duração (dias entre data_inicio_prevista e data_fim_prevista).

        Retorna um inteiro percentual (0-100).
        """
        etapas = list(obj.etapas.all())
        total_etapas = len(etapas)
        if total_etapas == 0:
            return 0

        # calcula valor e duração por etapa
        valores = []
        duracoes = []
        pct_list = []
        for e in etapas:
            # orcamento_previsto pode ser None
            valor = e.orcamento_previsto if e.orcamento_previsto is not None else Decimal('0')
            valores.append(Decimal(valor))
            inicio = e.data_inicio_prevista
            fim = e.data_fim_prevista
            dur = None
            if inicio and fim and isinstance(inicio, date) and isinstance(fim, date):
                try:
                    dur = max(0, (fim - inicio).days)
                except Exception:
                    dur = 0
            duracoes.append(dur if dur is not None else 0)
            pct_list.append(float(e.percentual_conclusao or 0))

        total_valor = sum(valores) if valores else Decimal('0')
        total_dur = sum(duracoes) if duracoes else 0

        # Se não houver nem valor nem duração, usar média simples
        if (total_valor == 0 or total_valor == Decimal('0')) and total_dur == 0:
            avg = sum(pct_list) / total_etapas
            return int(round(avg))

        COST_TIME_BLEND = 0.6

        weighted_sum = 0.0
        for idx, pct in enumerate(pct_list):
            weight = 0.0
            if total_valor > 0 and total_dur > 0:
                w_val = float(valores[idx] / total_valor) if total_valor > 0 else 0.0
                w_dur = (duracoes[idx] / total_dur) if total_dur > 0 else 0.0
                weight = COST_TIME_BLEND * w_val + (1.0 - COST_TIME_BLEND) * w_dur
            elif total_valor > 0:
                weight = float(valores[idx] / total_valor) if total_valor > 0 else 0.0
            else:
                weight = (duracoes[idx] / total_dur) if total_dur > 0 else 0.0

            weighted_sum += weight * pct

        return int(round(weighted_sum))

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # adiciona campo calculado sem alterar os fields do Meta
        data['progresso_ponderado'] = self.get_progresso_ponderado(instance)
        return data

class EtapaObraSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo EtapaObra.
    """
    class Meta:
        model = EtapaObra
        fields = '__all__'
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2 / D3)

class DocumentoObraSerializer(UploadValidationMixin, serializers.ModelSerializer):
    """
    Serializador para o modelo DocumentoObra.
    """
    class Meta:
        model = DocumentoObra
        fields = '__all__'
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2 / D3)

