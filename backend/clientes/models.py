# clientes/models.py
from decimal import Decimal

from django.db import models
from django.core.validators import RegexValidator
from nucleo.tenancy import Excluivel, TenantScopedModel
from django.utils.translation import gettext_lazy as _

# Reusable validator
cpf_cnpj_validator = RegexValidator(
    regex=r'^\d+$',
    message=_("O CPF/CNPJ deve conter apenas números.")
)

class Cliente(TenantScopedModel, Excluivel):
    """
    Armazena os dados cadastrais dos clientes.
    """
    ESTADO_CIVIL_CHOICES = [
        ('solteiro', _('Solteiro(a)')),
        ('casado', _('Casado(a)')),
        ('divorciado', _('Divorciado(a)')),
        ('viuvo', _('Viúvo(a)')),
        ('uniao_estavel', _('União Estável')),
    ]

    cliente_id = models.AutoField(primary_key=True)
    nome_completo = models.CharField(max_length=255, verbose_name=_("Nome Completo"))
    cpf_cnpj = models.CharField(max_length=18, blank=False, verbose_name=_("CPF/CNPJ"), validators=[cpf_cnpj_validator])
    email = models.EmailField(max_length=255, blank=False, verbose_name=_("E-mail"))
    telefone = models.CharField(max_length=20, blank=True, verbose_name=_("Telefone"))
    endereco = models.TextField(blank=True, verbose_name=_("Endereço"))
    numero_endereco = models.CharField(max_length=10, blank=True, verbose_name=_("Número do Endereço"))
    complemento_endereco = models.CharField(max_length=100, blank=True, verbose_name=_("Complemento do Endereço"))
    bairro = models.CharField(max_length=100, blank=True, verbose_name=_("Bairro"))
    cidade = models.CharField(max_length=100, blank=True, verbose_name=_("Cidade"))
    estado = models.CharField(max_length=2, blank=True, verbose_name=_("Estado"))
    cep = models.CharField(max_length=10, blank=True, verbose_name=_("CEP"))
    cidade_ibge = models.CharField(max_length=10, blank=True, verbose_name=_("Código IBGE da Cidade"))
    data_nascimento = models.DateField(verbose_name=_("Data de Nascimento"))
    estado_civil = models.CharField(max_length=50, choices=ESTADO_CIVIL_CHOICES, null=True, blank=True, verbose_name=_("Estado Civil"))
    profissao = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("Profissão"))
    data_cadastro = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Cadastro"))
    id_cliente_gateway = models.CharField(max_length=512, null=True, blank=True, verbose_name=_("ID do Cliente no Gateway de Pagamento"))

    def __str__(self):
        return self.nome_completo

    class Meta:
        verbose_name = _("Cliente")
        verbose_name_plural = _("Clientes")
        ordering = ['nome_completo']
        # Unicidade por-tenant (Fase 8.3): dois tenants podem ter o mesmo
        # CPF/CNPJ ou e-mail; dentro de um tenant, não.
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'cpf_cnpj'], condition=models.Q(excluido_em__isnull=True), name='cliente_cpf_cnpj_unico_por_tenant'),
            models.UniqueConstraint(fields=['tenant', 'email'], condition=models.Q(excluido_em__isnull=True), name='cliente_email_unico_por_tenant'),
        ]


class ClienteEmpreendimento(TenantScopedModel, Excluivel):
    """
    Vincula um cliente a um empreendimento específico, registrando a aquisição.
    """
    CONDICOES_PAGAMENTO_CHOICES = [
        ('a_vista', _('À Vista')),
        ('financiamento_bancario', _('Financiamento Bancário')),
        ('financiamento_direto', _('Financiamento Direto com a Construtora')),
        ('permuta', _('Permuta')),
        ('cartao', _('Cartão de Crédito/Débito')),
        ('outro', _('Outro')),
    ]

    SISTEMA_AMORTIZACAO_CHOICES = [
        ('price', _('Price — parcela fixa')),
        ('sac', _('SAC — amortização constante, parcela decrescente')),
    ]

    PERIODICIDADE_BALAO_CHOICES = [
        ('anual', _('Anual')),
        ('semestral', _('Semestral')),
    ]

    PERIODICIDADE_CORRECAO_CHOICES = [
        ('anual', _('Anual (aniversário do contrato)')),
        ('mensal', _('Mensal')),
    ]

    cliente_empreendimento_id = models.AutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.RESTRICT, verbose_name=_("Cliente"))
    # Denormalizado de propósito (a unidade já sabe o empreendimento): a carteira,
    # a ContaReceber e os filtros por empreendimento leem daqui sem um join a
    # mais. `save()` mantém em dia a partir da unidade — não é campo de digitação.
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.RESTRICT, verbose_name=_("Empreendimento"))
    # A unidade vendida. **Único lugar** onde a identificação mora: quadra, lote,
    # bloco, andar, apto e endereço são do cadastro do empreendimento, não da
    # venda. Antes eram digitados aqui, em paralelo a um rótulo livre — os dois
    # podiam divergir e o mesmo lote podia ser vendido duas vezes.
    unidade = models.ForeignKey(
        'empreendimentos.Unidade', on_delete=models.RESTRICT, related_name='aquisicoes',
        verbose_name=_("Unidade"),
    )
    data_compra = models.DateField(verbose_name=_("Data da Compra"))
    condicoes_pagamento = models.CharField(max_length=50, choices=CONDICOES_PAGAMENTO_CHOICES, verbose_name=_("Condições de Pagamento"))
    observacoes_compra = models.TextField(null=True, blank=True, verbose_name=_("Observações da Compra"))

    # ─── Proposta: da tabela ao que o cliente paga ────────────────────────────
    # O preço de tabela entra como **snapshot**: a unidade pode ser reprecificada
    # amanhã, e o contrato assinado hoje não muda por causa disso.
    valor_tabela = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'),
        verbose_name=_("Valor de tabela na venda"),
    )
    desconto_percentual = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal('0'), verbose_name=_("Desconto (%)"),
    )
    desconto_valor = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Desconto (R$)"),
    )
    # O valor negociado à vista — tabela menos desconto. Mantém o nome histórico
    # porque é o "valor da compra" que a carteira e as quotas já leem.
    valor_compra = models.DecimalField(max_digits=20, decimal_places=2, verbose_name=_("Valor negociado (à vista)"))

    entrada_valor = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Entrada / ATO (R$)"),
    )
    entrada_parcelas = models.PositiveSmallIntegerField(
        default=1, verbose_name=_("Parcelas da entrada"),
        help_text=_("A entrada parcelada não rende juros — é sinal, não financiamento."),
    )
    entrada_primeiro_vencimento = models.DateField(
        null=True, blank=True, verbose_name=_("1º vencimento da entrada"),
    )

    sistema_amortizacao = models.CharField(
        max_length=10, choices=SISTEMA_AMORTIZACAO_CHOICES, default='price',
        verbose_name=_("Sistema de amortização"),
    )
    juros_mensal = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal('0'), verbose_name=_("Juros (% ao mês)"),
        help_text=_("Zero é venda sem juros: a parcela vira o saldo dividido pelo prazo."),
    )
    num_parcelas = models.PositiveSmallIntegerField(default=0, verbose_name=_("Nº de parcelas do saldo"))
    primeiro_vencimento = models.DateField(
        null=True, blank=True, verbose_name=_("1º vencimento das parcelas"),
    )

    # Balão/intercalada: parcela extra periódica, prática corrente em loteamento.
    # Soma-se à mensal que vence no mesmo mês, não a substitui.
    balao_valor = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'), verbose_name=_("Valor do balão (R$)"),
    )
    balao_quantidade = models.PositiveSmallIntegerField(default=0, verbose_name=_("Quantidade de balões"))
    balao_periodicidade = models.CharField(
        max_length=10, choices=PERIODICIDADE_BALAO_CHOICES, default='anual',
        verbose_name=_("Periodicidade do balão"),
    )
    balao_primeiro_vencimento = models.DateField(
        null=True, blank=True, verbose_name=_("1º vencimento do balão"),
    )

    valor_total_plano = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'),
        verbose_name=_("Total do plano (desembolso)"),
        help_text=_("Entrada + parcelas + balões. Maior que o negociado quando há juros."),
    )
    # Carimbo do botão "Gerar parcelas": impede gerar o mesmo carnê duas vezes e
    # diz na tela que o financeiro já existe.
    parcelas_geradas_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Parcelas geradas em"),
    )

    # ─── Correção monetária ───────────────────────────────────────────────────
    # Contrato longo sem índice é desconto silencioso: a parcela de 2033 vale, em
    # poder de compra, uma fração da de 2026. Por isso o mercado corrige — e
    # corrige **no aniversário do contrato**, não na data do boleto: a data-base
    # é a da compra, e a partir dela o saldo devedor é reajustado a cada 12 meses
    # (anual) ou a cada mês (mensal, o padrão do INCC durante a obra). O boleto
    # não é a âncora, é só o portador: ele carrega o valor **já corrigido** pelo
    # que estava publicado quando foi lançado.
    indice_correcao = models.ForeignKey(
        'nucleo.IndiceEconomico', on_delete=models.PROTECT, null=True, blank=True,
        related_name='aquisicoes', verbose_name=_("Índice de correção"),
        help_text=_("Vazio = contrato sem correção monetária."),
    )
    periodicidade_correcao = models.CharField(
        max_length=10, choices=PERIODICIDADE_CORRECAO_CHOICES, default='anual',
        verbose_name=_("Periodicidade da correção"),
    )
    data_base_correcao = models.DateField(
        null=True, blank=True, verbose_name=_("Data-base da correção"),
        help_text=_("De onde o índice começa a contar. Vazio = a data da compra."),
    )

    @property
    def data_base_efetiva(self):
        """A âncora do reajuste. Cai na data da compra quando não foi negociada
        outra — é o que o comprador entende por 'aniversário do contrato'."""
        return self.data_base_correcao or self.data_compra

    @property
    def rotulo_unidade(self) -> str:
        """Atalho para o rótulo da unidade — a fonte é o cadastro dela."""
        return self.unidade.rotulo

    def save(self, *args, **kwargs):
        # O empreendimento da venda é o da unidade, sempre. Deixar o cliente
        # informar os dois abriria a porta para uma aquisição apontando para um
        # empreendimento e uma unidade de outro.
        if self.unidade_id and self.unidade.empreendimento_id != self.empreendimento_id:
            self.empreendimento_id = self.unidade.empreendimento_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cliente} - {self.empreendimento} ({self.rotulo_unidade})"

    class Meta:
        verbose_name = _("Aquisição de Empreendimento")
        verbose_name_plural = _("Aquisições de Empreendimentos")
        constraints = [
            # Uma unidade, um dono. Era o papel do `unique_together` antigo sobre
            # o texto livre — que não valia nada, porque "Apto 101" e "apto 101"
            # passavam como unidades diferentes.
            models.UniqueConstraint(
                fields=['tenant', 'unidade'], condition=models.Q(excluido_em__isnull=True), name='aquisicao_unica_por_unidade',
            ),
        ]


class ContratoCliente(TenantScopedModel, Excluivel):
    """
    Mantém os contratos firmados com os clientes.
    """
    STATUS_CONTRATO_CHOICES = [
        ('ativo', _('Ativo')),
        ('inativo', _('Inativo')),
        ('cancelado', _('Cancelado')),
        ('concluido', _('Concluído')),
    ]

    contrato_cliente_id = models.AutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='contratos', verbose_name=_('Cliente'))
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.RESTRICT, related_name='contratos_gerados', verbose_name=_('Empreendimento'))
    cliente_empreendimento = models.ForeignKey('ClienteEmpreendimento', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Aquisição Vinculada"))
    numero_contrato = models.CharField(max_length=50, verbose_name=_("Número do Contrato"))
    data_assinatura = models.DateField(verbose_name=_("Data de Assinatura"), null=True, blank=True)
    objeto_contrato = models.TextField(verbose_name=_("Objeto do Contrato"))
    arquivo_contrato = models.URLField(max_length=512, null=True, blank=True, verbose_name=_("Arquivo do Contrato"))
    status_contrato = models.CharField(max_length=50, choices=STATUS_CONTRATO_CHOICES, default='ativo', verbose_name=_("Status do Contrato"))
    responsavel = models.ForeignKey('rh.Funcionario', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Responsável"))
    vendedor = models.ForeignKey('fornecedores.Fornecedor', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Vendedor"))

    def __str__(self):
        return f"Contrato {self.numero_contrato} - {self.cliente.nome_completo}"

    class Meta:
        verbose_name = _("Contrato do Cliente")
        verbose_name_plural = _("Contratos dos Clientes")
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'numero_contrato'], condition=models.Q(excluido_em__isnull=True), name='contrato_numero_unico_por_tenant'),
        ]


class DocumentoCliente(TenantScopedModel):
    """
    Armazena documentos diversos dos clientes (RG, CPF, etc.).
    """
    TIPO_DOCUMENTO_CHOICES = [
        ('rg', _('RG')),
        ('cpf', _('CPF')),
        ('cnh', _('CNH')),
        ('comprovante_residencia', _('Comprovante de Residência')),
        ('certidao_casamento', _('Certidão de Casamento')),
        ('outros', _('Outros')),
    ]

    documento_cliente_id = models.AutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='documentos', verbose_name=_('Cliente'))
    tipo_documento = models.CharField(max_length=50, choices=TIPO_DOCUMENTO_CHOICES, verbose_name=_("Tipo de Documento"))
    nome_documento = models.CharField(max_length=255, verbose_name=_("Nome do Documento"), help_text=_("Especifique o documento se 'Outros' for selecionado."))
    arquivo = models.FileField(upload_to='documentos_clientes/', verbose_name=_("Arquivo"))
    data_upload = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Upload"))

    def __str__(self):
        return f"{self.get_tipo_documento_display()} de {self.cliente.nome_completo}"

    class Meta:
        verbose_name = _("Documento do Cliente")
        verbose_name_plural = _("Documentos dos Clientes")


class DadoBancarioCliente(TenantScopedModel):
    """
    Guarda as informações bancárias dos clientes para faturamento.
    Relação One-to-One com Cliente.
    """
    TIPO_CONTA_CHOICES = [
        ('corrente', _('Conta Corrente')),
        ('poupanca', _('Conta Poupança')),
        ('investimento', _('Conta de Investimento')),
        ('salario', _('Conta Salário')),
        ('outros', _('Outros')),
    ]

    cliente = models.ForeignKey(
        'Cliente',
        on_delete=models.CASCADE,
        related_name='dados_bancarios',
        verbose_name=_("Cliente")
    )
    codigo_banco = models.CharField(max_length=10, verbose_name=_("Código do Banco"))
    agencia = models.CharField(max_length=10, verbose_name=_("Agência"))
    agencia_dv = models.CharField(max_length=1, verbose_name=_("Dígito Verificador da Agência"), null=True, blank=True)
    conta = models.CharField(max_length=20, verbose_name=_("Conta"))
    conta_dv = models.CharField(max_length=1, verbose_name=_("Dígito Verificador da Conta"), null=True, blank=True)
    tipo_conta = models.CharField(max_length=50, choices=TIPO_CONTA_CHOICES, verbose_name=_("Tipo de Conta"))
    titular_nome = models.CharField(max_length=255, verbose_name=_("Nome do Titular"))
    titular_cpf_cnpj = models.CharField(max_length=18, verbose_name=_("CPF/CNPJ do Titular"), validators=[cpf_cnpj_validator])
    chave_pix = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Chave PIX"))
    codigo_cedente = models.CharField(max_length=25, verbose_name=_("Código Cedente/Convênio"), help_text=_("Também conhecido como Convênio ou Código do Beneficiário."), blank=True)
    carteira = models.CharField(max_length=25, verbose_name=_("Carteira"), help_text=_("Código da carteira de cobrança (fornecido pelo banco)."), blank=True)
    observacoes = models.TextField(null=True, blank=True, verbose_name=_("Observações"))
    data_atualizacao = models.DateTimeField(auto_now=True, verbose_name=_("Data de Atualização"))

    def __str__(self):
        return f"Dados Bancários de {self.cliente.nome_completo}"

    class Meta:
        verbose_name = _("Dado Bancário do Cliente")
        verbose_name_plural = _("Dados Bancários dos Clientes")
