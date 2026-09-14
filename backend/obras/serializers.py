# backend/obras/serializers.py
# Converte os modelos do app 'obras' para o formato JSON para a API.
from rest_framework import serializers
from decimal import Decimal
from datetime import date

from funcoesimpexp.entrega import ArquivoGateadoSerializerMixin
from nucleo.upload_validation import UploadValidationMixin

from .impexp import (
    ESPECIE_DOCUMENTO as ESPECIE_DOCUMENTO_OBRA,
    RECURSO_DOCUMENTOS as RECURSO_DOCUMENTOS_OBRA,
)
from .models import Obra, EtapaObra, DocumentoObra
from .nomes import (
    NomeDeObraEmUso, descrever_conflito, obra_em_conflito, sugerir_nome_livre,
)

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

    def validate(self, attrs):
        """O nome é único no empreendimento — e a recusa vem com um nome pronto.

        **Isto não existia.** As duas `UniqueConstraint` da `Obra` são
        condicionais e incluem `tenant` (que é read-only), e o DRF descarta as
        duas coisas: não havia validador nenhum, então nome repetido ia direto ao
        banco e voltava como `IntegrityError` — 500. Era falha invisível porque o
        índice do banco de desenvolvimento estava **corrompido** e deixava a
        duplicata passar; foi assim que o seed criou duas "Torre A — Fundações"
        no mesmo empreendimento, e só a reconstrução do índice revelou.

        A recusa carrega três coisas, e cada uma responde a uma pergunta de quem
        está cadastrando: `nome_obra` (o quê), `conflito` (é a mesma obra que eu
        já tenho?) e `sugestao_nome` (então como chamo esta?).
        """
        attrs = super().validate(attrs)

        instancia = self.instance
        nome = attrs.get('nome_obra', getattr(instancia, 'nome_obra', None))
        if 'empreendimento' in attrs:
            empreendimento = attrs['empreendimento']
        else:
            empreendimento = getattr(instancia, 'empreendimento', None)
        empreendimento_id = getattr(empreendimento, 'pk', None)

        usuario = getattr(self.context.get('request'), 'user', None)
        tenant_id = getattr(instancia, 'tenant_id', None) or getattr(usuario, 'tenant_id', None)
        if tenant_id is None or not nome:
            # Sem tenant não há escopo em que conferir; quem barra é o banco, e o
            # `perform_create` injeta o tenant logo depois. Inventar um escopo
            # aqui daria falso negativo silencioso.
            return attrs

        conflito = obra_em_conflito(
            tenant_id=tenant_id, empreendimento_id=empreendimento_id,
            nome=nome, excluir_pk=getattr(instancia, 'pk', None),
        )
        if conflito is None:
            return attrs

        data_inicio = attrs.get(
            'data_inicio_prevista', getattr(instancia, 'data_inicio_prevista', None)
        )
        raise NomeDeObraEmUso({
            'nome_obra': ['Já existe uma obra com este nome neste empreendimento.'],
            'conflito': descrever_conflito(conflito),
            'sugestao_nome': sugerir_nome_livre(
                tenant_id=tenant_id, empreendimento_id=empreendimento_id,
                nome=nome, data_inicio=data_inicio,
                excluir_pk=getattr(instancia, 'pk', None),
            ),
        })

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

# ---------------------------------------------------------------------------
# O percentual da etapa: digitado × apurado (planta do PDCA §11.2)
# ---------------------------------------------------------------------------
#
# `percentual_conclusao` é digitado à mão desde sempre, e pondera quatro leituras
# desta casa: o resumo da obra, o `progresso_ponderado` acima, o portal do
# cliente e a curva S do Orçamento. Com o PDCA no ar e atividades vinculadas à
# etapa, ele passa a ser **apurado** pelo avanço apontado — o módulo escreve o
# espelho aqui a cada apontamento.
#
# Este arquivo NÃO importa o `modulopdca` no topo, e a razão é de arquitetura:
# `obras` é fundação sem entitlement, e fundação não depende de módulo vendido. A
# leitura é oferecida pelo módulo e pedida sob demanda; sem ele — tenant que não
# contrata, instalação que não tem o app — a etapa continua sendo o que sempre
# foi, e ninguém quebra.


def _etapas_apuradas(obra_id, tenant_id) -> frozenset:
    if not obra_id or not tenant_id:
        return frozenset()
    try:
        from modulopdca.services import etapas_com_apuracao
    except Exception:
        return frozenset()
    return etapas_com_apuracao(obra_id=obra_id, tenant_id=tenant_id)


def _pode_digitar_percentual(usuario) -> bool:
    """Espelha o `RequirePermission`: admin de tenant e superusuário passam; os
    demais precisam do código exato na claim do token."""
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return False
    if getattr(usuario, "is_tenant_admin", False) or getattr(usuario, "is_superuser", False):
        return True
    return "obra.etapa.percentual_manual" in (
        getattr(usuario, "iam_permissions", None) or []
    )


class EtapaObraSerializer(serializers.ModelSerializer):
    """Serializador para o modelo EtapaObra.

    **A tela sempre diz de onde veio o percentual** (planta do PDCA §11.2). Duas
    fontes silenciosas para o mesmo número é como se perde a confiança nas duas:
    `percentual_origem` responde `apurado` quando há cronograma vigente com
    atividade vinculada a esta etapa, e `informado` quando o número continua
    sendo o que alguém digitou.
    """

    percentual_origem = serializers.SerializerMethodField()

    class Meta:
        model = EtapaObra
        fields = [*(f.name for f in EtapaObra._meta.fields), 'percentual_origem']
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2 / D3)

    def _apuradas(self) -> frozenset:
        """Uma consulta por **requisição**, e não por linha da lista: o resultado
        fica no contexto, que o DRF compartilha entre os itens do `many=True`."""
        contexto = self.context if isinstance(self.context, dict) else {}
        cache = contexto.setdefault('_pdca_etapas_apuradas', {}) if contexto else {}
        return cache

    def get_percentual_origem(self, obj) -> str:
        cache = self._apuradas()
        chave = (obj.obra_id, obj.tenant_id)
        if chave not in cache:
            cache[chave] = _etapas_apuradas(obj.obra_id, obj.tenant_id)
        return 'apurado' if obj.pk in cache[chave] else 'informado'

    def validate(self, dados):
        """A caneta do percentual apurado é de quem tem a permissão.

        Não é proibição de editar a etapa: nome, datas e status continuam livres
        para quem gere a obra. É o **número** que passou a ter dono — e mesmo com
        a permissão, o valor digitado dura até o próximo apontamento de avanço,
        que é o que a mensagem diz em vez de deixar a pessoa descobrir sozinha.
        """
        if 'percentual_conclusao' not in dados or self.instance is None:
            return dados
        anterior = self.instance.percentual_conclusao
        if dados['percentual_conclusao'] == anterior:
            return dados

        obra_id = self.instance.obra_id
        tenant_id = self.instance.tenant_id
        if self.instance.pk not in _etapas_apuradas(obra_id, tenant_id):
            return dados

        request = self.context.get('request') if isinstance(self.context, dict) else None
        if not _pode_digitar_percentual(getattr(request, 'user', None)):
            raise serializers.ValidationError({
                'percentual_conclusao': (
                    'O avanço desta etapa é apurado pelo cronograma da obra '
                    '(módulo PDCA). Para digitá-lo à mão é preciso a permissão '
                    '"Digitar o percentual da etapa" — e o valor digitado vale '
                    'até o próximo apontamento de avanço.'
                ),
            })
        return dados

class DocumentoObraSerializer(ArquivoGateadoSerializerMixin, UploadValidationMixin, serializers.ModelSerializer):
    """Contrato, licença, memorial — o arquivo sai gateado (D70)."""
    arquivos_gateados = {"arquivo": (RECURSO_DOCUMENTOS_OBRA, ESPECIE_DOCUMENTO_OBRA)}

    class Meta:
        model = DocumentoObra
        fields = '__all__'
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2 / D3)

