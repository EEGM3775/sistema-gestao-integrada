# empreendimentos/models.py
from django.db import models
from django.db.models import Q
from nucleo.tenancy import TenantScopedModel
from django.utils.translation import gettext_lazy as _

# Choices for Empreendimento.status_empreendimento
STATUS_EMPREENDIMENTO_CHOICES = [
    ('planejamento', _('Planejamento')),
    ('em_execucao', _('Em Execução')),
    ('concluido', _('Concluído')),
    ('cancelado', _('Cancelado')),
]

# Choices for ContaBancariaEmpreendimento.tipo_conta
TIPO_CONTA_CHOICES = [
    ("corrente", _("Corrente")),
    ("poupanca", _("Poupança")),
    ("investimento", _("Investimento")),
]

# Choices for CustoEmpreendimento.tipo_custo
TIPO_CUSTO_CHOICES = [
    ("automovel", _("Automóvel")),
    ("equipamentos", _("Equipamentos")),
    ("extra", _("Extra")),
    ("fixo", _("Fixo")),
    ("funcionarios", _("Funcionários")),
    ("imovel", _("Imóvel")),
    ("impostos", _("Impostos")),
    ("imprevisto", _("Imprevisto")),
    ("manutencao", _("Manutenção")),
    ("materiais", _("Materiais")),
    ("mobiliario", _("Mobiliário")),
    ("publicidade", _("Publicidade")),
    ("seguros", _("Seguros")),
    ("servicos", _("Serviços")),
    ("servicos_terceiros", _("Serviços de Terceiros")),
    ("taxas", _("Taxas")),
    ("transporte", _("Transporte")),
    ("variavel", _("Variável")),
    ("outros", _("Outros")),
]


class Empreendimento(TenantScopedModel):
    empreendimento_id = models.AutoField(primary_key=True)
    empreendimento = models.CharField(max_length=255, verbose_name=_("Nome do Empreendimento"))
    razao_social = models.CharField(max_length=255, verbose_name=_("Razão Social"))
    cnpj = models.CharField(max_length=18, verbose_name=_("CNPJ"))
    telefone = models.CharField(max_length=20, verbose_name=_("Telefone"))
    endereco = models.TextField(verbose_name=_("Endereço"))
    data_inicio_prevista = models.DateField(null=True, blank=True, verbose_name=_("Data de Início Prevista"))
    data_fim_prevista = models.DateField(null=True, blank=True, verbose_name=_("Data de Fim Prevista"))
    data_inicio_real = models.DateField(null=True, blank=True, verbose_name=_("Data de Início Real"))
    data_fim_real = models.DateField(null=True, blank=True, verbose_name=_("Data de Fim Real"))
    orcamento_total = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name=_("Orçamento Total"))
    status_empreendimento = models.CharField(max_length=50, choices=STATUS_EMPREENDIMENTO_CHOICES, default="planejamento", verbose_name=_("Status do Empreendimento"))
    descricao = models.TextField(null=True, blank=True, verbose_name=_("Descrição do Empreendimento"))
    data_criacao = models.DateTimeField(auto_now_add=True, null=False, verbose_name=_("Data de Criação"))
    data_atualizacao = models.DateTimeField(auto_now=True, null=False, verbose_name=_("Data de Atualização"))

    class Meta:
        verbose_name = _("Empreendimento")
        verbose_name_plural = _("Empreendimentos")
        ordering = ['empreendimento']
        indexes = [
            models.Index(
                fields=['status_empreendimento'],
                name='emp_status_execucao_idx',
                condition=Q(status_empreendimento='em_execucao')
            ),
        ]
        # Unicidade por-tenant (Fase 8.3).
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'razao_social'], name='empreend_razao_unica_por_tenant'),
            models.UniqueConstraint(fields=['tenant', 'cnpj'], name='empreend_cnpj_unico_por_tenant'),
        ]

    def __str__(self):
        return self.empreendimento


class ContaBancariaEmpreendimento(TenantScopedModel):
    empreendimento = models.ForeignKey(Empreendimento, on_delete=models.CASCADE, related_name='contas_bancarias', verbose_name=_("Empreendimento"))
    codigo_banco = models.CharField(max_length=10, verbose_name=_("Código do Banco"))
    agencia = models.CharField(max_length=20, null=False, blank=False, verbose_name=_("Agência"))
    agencia_dv = models.CharField(max_length=1, null=True, blank=True, verbose_name=_("DV da Agência"))
    conta = models.CharField(max_length=20, null=False, blank=False, verbose_name=_("Conta"))
    conta_dv = models.CharField(max_length=1, null=True, blank=True, verbose_name=_("DV da Conta"))
    codigo_cedente = models.CharField(max_length=25, null=True, blank=True, verbose_name=_("Código Cedente"))
    carteira = models.CharField(max_length=25, null=True, blank=True, verbose_name=_("Carteira"))
    codigo_pix = models.CharField(max_length=512, null=True, blank=True, verbose_name=_("Código PIX"))
    tipo_conta = models.CharField(max_length=50, choices=TIPO_CONTA_CHOICES, default="corrente", null=False, blank=False, verbose_name=_("Tipo de Conta"))
    numero_agencia = models.CharField(max_length=20, verbose_name=_("Número da Agência"))
    numero_conta = models.CharField(max_length=20, null=False, verbose_name=_("Número da Conta"))
    is_principal = models.IntegerField(choices=[(1, _("Sim")), (0, _("Não"))], default=1, verbose_name=_("É Principal"))
    observacoes = models.TextField(null=True, blank=True, verbose_name=_("Observações"))
    data_criacao = models.DateTimeField(auto_now_add=True, null=False, verbose_name=_("Data de Criação"))
    data_atualizacao = models.DateTimeField(auto_now=True, null=False, verbose_name=_("Data de Atualização"))

    class Meta:
        verbose_name = _("Conta Bancária do Empreendimento")
        verbose_name_plural = _("Contas Bancárias dos Empreendimentos")

    def __str__(self):
        return f"{self.empreendimento.empreendimento} - {self.codigo_banco} - {self.agencia}/{self.conta}"


class CustoEmpreendimento(TenantScopedModel):
    custo_id = models.AutoField(primary_key=True)
    empreendimento = models.ForeignKey(Empreendimento, null=True, blank=True, on_delete=models.SET_NULL, related_name='custos', verbose_name=_("Empreendimento"))
    descricao = models.TextField(null=True, blank=True, verbose_name=_("Descrição do Custo"))
    tipo_custo = models.CharField(max_length=50, choices=TIPO_CUSTO_CHOICES, default="fixo", null=False, blank=False, verbose_name=_("Tipo de Custo"))
    fornecedor = models.ForeignKey('fornecedores.Fornecedor', on_delete=models.SET_NULL, null=True, blank=True, related_name='custos_empreendimento', verbose_name=_("Fornecedor"))
    produto_servico = models.ForeignKey('fornecedores.ProdutoServicoFornecedor', on_delete=models.SET_NULL, null=True, blank=True, related_name='custos_empreendimento', verbose_name=_("Produto/Serviço"))
    valor = models.DecimalField(max_digits=15, decimal_places=2, null=False, blank=False, verbose_name=_("Preço Unitário"))
    quantidade = models.DecimalField(max_digits=15, decimal_places=2, null=False, blank=False, verbose_name=_("Quantidade"))
    data_custo = models.DateField(null=False, blank=False, verbose_name=_("Data do Custo"))
    chave_acesso = models.CharField(max_length=44, null=True, blank=True, verbose_name=_("Chave de Acesso NF-e"))
    data_emissao = models.DateTimeField(auto_now_add=True, null=False, verbose_name=_("Data de Emissão"))
    valor_total = models.DecimalField(max_digits=15, decimal_places=4, null=False, blank=False, verbose_name=_("Valor Total"))
    arquivo_xml = models.FileField(upload_to="nfe_xmls/%Y/%m/", null=True, blank=True, verbose_name=_("Arquivo XML NF-e"))
    data_upload = models.DateTimeField(auto_now_add=True, null=False, verbose_name=_("Data de Upload"))
    nota_fiscal = models.CharField(_("Nota Fiscal"), max_length=100, blank=True, null=True, db_index=True)

    class Meta:
        verbose_name = _("Custo do Empreendimento")
        verbose_name_plural = _("Custos dos Empreendimentos")
        # Chave de acesso NF-e única por-tenant (nullable → múltiplos NULL ok).
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'chave_acesso'], name='custo_chave_acesso_unica_por_tenant'),
        ]

    def __str__(self):
        return f"Custo: {self.descricao} - {self.valor}"



