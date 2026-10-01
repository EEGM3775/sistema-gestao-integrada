# backend/moduloerp/serializers.py
from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from funcoesimpexp.entrega import ArquivoGateadoSerializerMixin
from nucleo.tenant_validators import TenantScopedUniqueSerializerMixin
from .impexp import RECURSO_NOTA_FISCAL
from .models import (
    Transacao, NotaFiscalServico, NotaFiscalProduto,
    NotaFiscal, ContaPagar, ContaReceber, CobrancaCliente, Boleto,
    CentroCusto, RateioContaPagar, RateioContaReceber, LoteRemessa, RevisaoBaixa
)

# --- Serializers for API Endpoints ---

class BoletoSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo Boleto.
    """
    class Meta:
        model = Boleto
        fields = '__all__'
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2 / D3)


def _rotulo_unidade(conta):
    aquisicao = getattr(conta, 'cliente_empreendimento', None) if conta else None
    unidade = getattr(aquisicao, 'unidade', None)
    return unidade.rotulo if unidade else ''


class BoletoListaSerializer(BoletoSerializer):
    """O boleto com a origem dita por extenso (item 54 do dono).

    A tela de boletos mostrava "Conta a receber #172000" e mais nada: não dava
    para saber de quem era o boleto nem de que lote. Os nomes vêm do
    `select_related` da view — nada de consulta por linha.
    """
    pessoa_nome = serializers.SerializerMethodField()
    cliente_id = serializers.SerializerMethodField()
    conta_descricao = serializers.SerializerMethodField()
    empreendimento_nome = serializers.SerializerMethodField()
    unidade = serializers.SerializerMethodField()

    def _conta(self, obj):
        return obj.conta_receber or obj.conta_pagar

    def get_pessoa_nome(self, obj):
        if obj.conta_receber_id:
            return obj.conta_receber.cliente.nome_completo
        if obj.conta_pagar_id:
            return obj.conta_pagar.fornecedor.razao_social
        return ''

    def get_cliente_id(self, obj):
        return obj.conta_receber.cliente_id if obj.conta_receber_id else None

    def get_conta_descricao(self, obj):
        conta = self._conta(obj)
        return conta.descricao if conta else ''

    def get_empreendimento_nome(self, obj):
        conta = self._conta(obj)
        emp = getattr(conta, 'empreendimento', None)
        return emp.empreendimento if emp else ''

    def get_unidade(self, obj):
        return _rotulo_unidade(obj.conta_receber) if obj.conta_receber_id else ''

class NotaFiscalServicoSerializer(ArquivoGateadoSerializerMixin, TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """NFS-e emitida pela NFE.io — PDF e XML pela porta única (D70)."""
    arquivos_gateados = {
        "arquivo_pdf": (RECURSO_NOTA_FISCAL, "nfse_pdf"),
        "arquivo_xml": (RECURSO_NOTA_FISCAL, "nfse_xml"),
    }

    class Meta:
        model = NotaFiscalServico
        fields = '__all__'

class NotaFiscalProdutoSerializer(ArquivoGateadoSerializerMixin, TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """NF-e de produto — PDF e XML pela porta única (D70)."""
    arquivos_gateados = {
        "arquivo_pdf": (RECURSO_NOTA_FISCAL, "nfe_pdf"),
        "arquivo_xml": (RECURSO_NOTA_FISCAL, "nfe_xml"),
    }

    class Meta:
        model = NotaFiscalProduto
        fields = '__all__'

class TransacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transacao
        fields = '__all__'
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2 / D3)

class NotaFiscalSerializer(ArquivoGateadoSerializerMixin, TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    """Nota de **entrada** (a que o fornecedor mandou) — XML e PDF gateados (D70)."""
    arquivos_gateados = {
        "arquivo_pdf": (RECURSO_NOTA_FISCAL, "entrada_pdf"),
        "arquivo_xml": (RECURSO_NOTA_FISCAL, "entrada_xml"),
    }

    class Meta:
        model = NotaFiscal
        fields = '__all__'

class CentroCustoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CentroCusto
        fields = ['centro_custo_id', 'nome', 'codigo', 'empreendimento', 'ativo']


class RateioContaPagarSerializer(serializers.ModelSerializer):
    centro_custo_nome = serializers.CharField(source='centro_custo.nome', read_only=True)

    class Meta:
        model = RateioContaPagar
        fields = ['rateio_id', 'centro_custo', 'centro_custo_nome', 'valor']


class RateioContaReceberSerializer(serializers.ModelSerializer):
    centro_custo_nome = serializers.CharField(source='centro_custo.nome', read_only=True)

    class Meta:
        model = RateioContaReceber
        fields = ['rateio_id', 'centro_custo', 'centro_custo_nome', 'valor']


def _validar_rateios(rateios, valor, campo='rateios'):
    """
    Valida o array de rateio antes de chegar no banco — sem isso, um centro de
    custo repetido só apareceria como IntegrityError (UniqueConstraint) e um
    500 cru, em vez de um 400 com mensagem legível para o formulário.
    """
    if not rateios:
        return

    centros = [r['centro_custo'].pk for r in rateios]
    if len(centros) != len(set(centros)):
        raise serializers.ValidationError({
            campo: _('Cada centro de custo só pode aparecer uma vez no rateio.')
        })

    soma = sum((r['valor'] for r in rateios), Decimal('0'))
    if valor is not None and soma != valor:
        raise serializers.ValidationError({
            campo: _(
                'A soma dos rateios (R$ %(soma)s) deve ser igual ao valor da conta (R$ %(valor)s).'
            ) % {'soma': soma, 'valor': valor}
        })


class TravaDeEdicaoMixin(serializers.Serializer):
    """Item 57: o que a baixa trava, publicado para a tela e cobrado na escrita.

    A tela lê `campos_travados`/`travado_porque` em vez de reimplementar a
    condição (frontend-convencoes §11) — e a mensagem que ela mostra é a mesma
    que a API devolveria. `pode_estornar` só vem no detalhe: é uma pergunta ao
    PDP, e cem delas por página de lista não valem o custo.
    """
    campos_travados = serializers.SerializerMethodField()
    travado_porque = serializers.SerializerMethodField()
    pode_estornar = serializers.SerializerMethodField()
    estorno_impedido_porque = serializers.SerializerMethodField()

    permissao_estorno = ''

    def get_campos_travados(self, obj):
        from .estorno import travas
        return travas(obj)[0]

    def get_travado_porque(self, obj):
        from .estorno import travas
        return travas(obj)[1]

    def _eh_detalhe(self):
        view = self.context.get('view')
        return getattr(view, 'action', None) in ('retrieve', 'estornar_baixa', 'partial_update', 'update')

    def get_pode_estornar(self, obj):
        if not self._eh_detalhe() or obj.valor_pago <= 0:
            return False
        from nucleo import autorizacao
        request = self.context.get('request')
        return bool(request and autorizacao.pode(request.user, self.permissao_estorno))

    def get_estorno_impedido_porque(self, obj):
        if not self._eh_detalhe():
            return ''
        from .estorno import motivo_para_nao_estornar
        return motivo_para_nao_estornar(obj) if obj.valor_pago > 0 else ''

    def _recusar_campos_travados(self, attrs):
        from .estorno import recusa_de_edicao
        erros = recusa_de_edicao(self.instance, attrs)
        if erros:
            raise serializers.ValidationError(erros)

    CAMPOS_AUDITADOS = ('valor', 'data_vencimento')

    def _foto_financeira(self, conta) -> dict:
        campos = {c: getattr(conta, c) for c in self.CAMPOS_AUDITADOS}
        campos['pessoa'] = conta.cliente_id if isinstance(conta, ContaReceber) else conta.fornecedor_id
        return campos

    def _auditar_mudanca_financeira(self, conta, antes: dict, **extra):
        """Item 57 (01/10/2026): mudar valor, vencimento ou contraparte deixa rastro.

        A conta do dono foi corrigida de 01/01 para 02/01/2030 e não havia como
        saber quem nem quando — a edição comum não passava pela auditoria.
        """
        depois = self._foto_financeira(conta)
        mudancas = {c: [str(antes[c]), str(depois[c])] for c in depois if antes.get(c) != depois[c]}
        if not mudancas:
            return
        from nucleo.auditoria import registrar_auditoria
        request = self.context.get('request')
        registrar_auditoria(
            acao="editar_financeiro", instance=conta, usuario=getattr(request, 'user', None),
            detalhes={'mudancas': mudancas, **extra},
        )


def _validar_edicao_valor(instance, valor, rateios_no_payload):
    """
    L6: numa EDIÇÃO de título, o novo `valor` não pode (a) deixar o título com
    saldo negativo — total devido menor que o já baixado — nem (b) quebrar
    silenciosamente o rateio existente quando só o valor muda. Sem (a), um PATCH
    reduzia `valor` abaixo de `valor_pago`; sem (b), os rateios deixavam de somar
    o total e a divergência só aparecia depois.
    """
    if instance is None or valor is None:
        return

    total_devido = valor + instance.juros + instance.multa - instance.desconto
    if total_devido < instance.valor_pago:
        raise serializers.ValidationError({
            'valor': _(
                'O valor não pode ficar menor que o total já baixado (R$ %(pago)s).'
            ) % {'pago': instance.valor_pago}
        })

    # Rateios não vieram no payload mas o valor mudou: os existentes precisam
    # continuar fechando com o novo valor (se vieram, `_validar_rateios` já cuida).
    if not rateios_no_payload:
        existentes = list(instance.rateios.all())
        if existentes:
            soma = sum((r.valor for r in existentes), Decimal('0'))
            if soma != valor:
                raise serializers.ValidationError({
                    'valor': _(
                        'Alterar o valor para R$ %(valor)s quebra o rateio existente '
                        '(soma R$ %(soma)s). Envie os rateios ajustados junto.'
                    ) % {'valor': valor, 'soma': soma}
                })


class ContaPagarSerializer(TravaDeEdicaoMixin, serializers.ModelSerializer):
    """
    Serializador para o modelo ContaPagar.

    Campos de baixa (status, valor_pago, juros, multa, desconto, data_pagamento)
    são somente leitura aqui — só são alterados via a ação `dar_baixa`, que é o
    único caminho (manual ou futuro webhook do Asaas) que mantém esses valores e
    o ledger de Transacao consistentes entre si.
    """
    boletos = BoletoSerializer(many=True, read_only=True)
    rateios = RateioContaPagarSerializer(many=True, required=False)
    total_devido = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    saldo_aberto = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    # Os nomes vêm prontos (item 53 do dono): a tela procurava o nome numa lista
    # de opções e mostrava "Fornecedor #12" quando ele não estava entre elas.
    permissao_estorno = 'erp.conta_pagar.estornar'
    fornecedor_nome = serializers.CharField(source='fornecedor.razao_social', read_only=True, default='')
    empreendimento_nome = serializers.CharField(source='empreendimento.empreendimento', read_only=True, default='')

    class Meta:
        model = ContaPagar
        fields = [
            'conta_pagar_id', 'fornecedor', 'fornecedor_nome', 'empreendimento', 'empreendimento_nome',
            'nota_fiscal',
            'descricao', 'valor', 'data_emissao', 'data_vencimento', 'data_agendamento',
            'status', 'valor_pago', 'juros', 'multa', 'desconto', 'data_pagamento',
            'total_devido', 'saldo_aberto', 'rateios', 'boletos',
            'campos_travados', 'travado_porque', 'pode_estornar', 'estorno_impedido_porque',
        ]
        read_only_fields = ['status', 'valor_pago', 'juros', 'multa', 'desconto', 'data_pagamento']

    def validate(self, attrs):
        rateios = attrs.get('rateios')
        valor = attrs.get('valor', getattr(self.instance, 'valor', None))
        self._recusar_campos_travados(attrs)  # item 57: a trava fala primeiro, com a saída
        _validar_rateios(rateios, valor)
        _validar_edicao_valor(self.instance, valor, rateios is not None)  # L6
        return attrs

    def create(self, validated_data):
        rateios_data = validated_data.pop('rateios', [])
        conta = super().create(validated_data)
        for rateio in rateios_data:
            RateioContaPagar.objects.create(conta_pagar=conta, tenant=conta.tenant, **rateio)
        return conta

    def update(self, instance, validated_data):
        rateios_data = validated_data.pop('rateios', None)
        antes = self._foto_financeira(instance)
        conta = super().update(instance, validated_data)
        if rateios_data is not None:
            conta.rateios.all().delete()
            for rateio in rateios_data:
                RateioContaPagar.objects.create(conta_pagar=conta, tenant=conta.tenant, **rateio)
        self._auditar_mudanca_financeira(conta, antes)
        return conta


class ContaReceberSerializer(TravaDeEdicaoMixin, serializers.ModelSerializer):
    """
    Serializador para o modelo ContaReceber.

    Mesma regra do ContaPagarSerializer: campos de baixa são somente leitura,
    alterados exclusivamente pela ação `dar_baixa`.
    """
    boletos = BoletoSerializer(many=True, read_only=True)
    rateios = RateioContaReceberSerializer(many=True, required=False)
    total_devido = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    saldo_aberto = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    # Nomes prontos (itens 53/54 do dono) — ver ContaPagarSerializer.
    permissao_estorno = 'erp.conta_receber.estornar'
    cliente_nome = serializers.CharField(source='cliente.nome_completo', read_only=True, default='')
    empreendimento_nome = serializers.CharField(source='empreendimento.empreendimento', read_only=True, default='')
    unidade = serializers.SerializerMethodField()
    # Item 57 (01/10/2026): com boleto vivo no Asaas, mudar valor ou vencimento
    # cancela o boleto e emite outro — e isso só acontece com a confirmação.
    atualizar_boleto = serializers.BooleanField(write_only=True, required=False, default=False)
    boleto_desatualizado = serializers.SerializerMethodField()

    class Meta:
        model = ContaReceber
        fields = [
            'conta_receber_id', 'cliente', 'cliente_nome', 'empreendimento', 'empreendimento_nome',
            'cliente_empreendimento', 'unidade',
            'nota_fiscal_recebida', 'nota_fiscal_servico', 'nota_fiscal_produto',
            'descricao', 'valor', 'data_emissao', 'data_vencimento', 'data_agendamento',
            'status', 'valor_pago', 'juros', 'multa', 'desconto', 'data_recebimento',
            'total_devido', 'saldo_aberto', 'rateios', 'boletos',
            'campos_travados', 'travado_porque', 'pode_estornar', 'estorno_impedido_porque',
            'atualizar_boleto', 'boleto_desatualizado',
        ]
        read_only_fields = [
            'status', 'valor_pago', 'juros', 'multa', 'desconto', 'data_recebimento',
            'cliente_empreendimento',
        ]

    def get_unidade(self, obj):
        return _rotulo_unidade(obj)

    def get_boleto_desatualizado(self, obj):
        """A frase de por que o boleto vivo não é mais o desta conta (só no detalhe)."""
        if not self._eh_detalhe():
            return ''
        from .boleto_da_conta import desencontro
        return desencontro(obj)

    def validate(self, attrs):
        rateios = attrs.get('rateios')
        valor = attrs.get('valor', getattr(self.instance, 'valor', None))
        confirmado = attrs.pop('atualizar_boleto', False)
        self._recusar_campos_travados(attrs)  # item 57: a trava fala primeiro, com a saída
        if self.instance is not None:
            from .boleto_da_conta import recusa_por_boleto
            erros = recusa_por_boleto(self.instance, attrs, confirmado=confirmado)
            if erros:
                raise serializers.ValidationError(erros)
        _validar_rateios(rateios, valor)
        _validar_edicao_valor(self.instance, valor, rateios is not None)  # L6
        return attrs

    def create(self, validated_data):
        rateios_data = validated_data.pop('rateios', [])
        conta = super().create(validated_data)
        for rateio in rateios_data:
            RateioContaReceber.objects.create(conta_receber=conta, tenant=conta.tenant, **rateio)
        return conta

    def update(self, instance, validated_data):
        from .boleto_da_conta import reemitir_se_preciso

        rateios_data = validated_data.pop('rateios', None)
        antes = self._foto_financeira(instance)
        conta = super().update(instance, validated_data)
        if rateios_data is not None:
            conta.rateios.all().delete()
            for rateio in rateios_data:
                RateioContaReceber.objects.create(conta_receber=conta, tenant=conta.tenant, **rateio)
        reemitido = reemitir_se_preciso(conta, antes=antes)
        self._auditar_mudanca_financeira(conta, antes, **({'boleto_reemitido': True} if reemitido else {}))
        return conta


class BaixaSerializer(serializers.Serializer):
    """
    Valida o payload da ação `dar_baixa` — usado tanto pela baixa manual (UI)
    quanto, futuramente, pelo handler de webhook do Asaas (D.1.2), garantindo
    que os dois caminhos cheguem ao model.dar_baixa() com os mesmos tipos/regras.
    """
    valor = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('0.01'))
    data = serializers.DateField()
    juros = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, default=Decimal('0'), min_value=Decimal('0'))
    multa = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, default=Decimal('0'), min_value=Decimal('0'))
    desconto = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, default=Decimal('0'), min_value=Decimal('0'))
    meio_pagamento = serializers.CharField(required=False, allow_blank=True, default='')


class RevisaoBaixaSerializer(serializers.ModelSerializer):
    """
    Fila de revisão do financeiro para baixas tentadas em títulos já
    QUITADOS/CANCELADOS (ver `ContaPagar.dar_baixa`/`BaixaRequerRevisao`).
    Somente leitura — a decisão acontece pelas ações `aprovar`/`rejeitar`
    do `RevisaoBaixaViewSet`, nunca por escrita direta nos campos.
    """
    conta_tipo = serializers.SerializerMethodField()
    conta_descricao = serializers.SerializerMethodField()

    class Meta:
        model = RevisaoBaixa
        fields = [
            'revisao_id', 'conta_pagar', 'conta_receber', 'conta_tipo', 'conta_descricao',
            'valor', 'data', 'juros', 'multa', 'desconto', 'meio_pagamento', 'origem', 'motivo',
            'status', 'solicitado_por', 'solicitado_em',
            'revisado_por', 'revisado_em', 'observacao_revisor',
        ]
        read_only_fields = fields

    def get_conta_tipo(self, obj):
        return 'pagar' if obj.conta_pagar_id else 'receber'

    def get_conta_descricao(self, obj):
        conta = obj.conta
        return conta.descricao if conta else ''


class LoteRemessaSerializer(serializers.ModelSerializer):
    """
    Registro do lote de remessa bancária. Geração do arquivo CNAB em si fica
    fora deste serializer — ver nota em models.LoteRemessa sobre o adiamento.
    """
    contas_pagar = serializers.PrimaryKeyRelatedField(many=True, queryset=ContaPagar.objects.all(), required=False)
    contas_resumo = serializers.SerializerMethodField()

    class Meta:
        model = LoteRemessa
        fields = [
            'lote_id', 'status', 'banco', 'data_geracao', 'data_envio',
            'valor_total', 'observacoes', 'contas_pagar', 'contas_resumo',
        ]
        read_only_fields = ['valor_total', 'data_geracao']

    def get_contas_resumo(self, obj):
        return [
            {
                'id': conta.conta_pagar_id,
                'descricao': conta.descricao,
                'fornecedor': conta.fornecedor.razao_social if conta.fornecedor else None,
                'valor': conta.valor,
            }
            for conta in obj.contas_pagar.all()[:50]
        ]

class CobrancaClienteSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo CobrancaCliente.
    """
    class Meta:
        model = CobrancaCliente
        fields = '__all__'
        read_only_fields = ['tenant']  # injetado pelo perform_create (Fase 8.2 / D3)

# --- Serializers for Dashboard Aggregations ---

class AgingDataSerializer(serializers.Serializer):
    categoria = serializers.CharField()
    total = serializers.DecimalField(max_digits=12, decimal_places=2)

class FluxoCaixaMensalSerializer(serializers.Serializer):
    mes = serializers.DateField()
    receitas = serializers.DecimalField(max_digits=12, decimal_places=2)
    despesas = serializers.DecimalField(max_digits=12, decimal_places=2)

class DashboardERPSerializer(serializers.Serializer):
    agingContasAReceber = AgingDataSerializer(many=True)
    agingContasAPagar = AgingDataSerializer(many=True)
    fluxoDeCaixaMensal = FluxoCaixaMensalSerializer(many=True)
