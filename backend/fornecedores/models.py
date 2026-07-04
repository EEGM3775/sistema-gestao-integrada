# fornecedores/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from nucleo.tenancy import TenantScopedModel

class Fornecedor(TenantScopedModel):
    fornecedor_id = models.AutoField(primary_key=True, verbose_name=_("ID do Fornecedor"))
    razao_social = models.CharField(max_length=255, unique=True, verbose_name=_("Razão Social"))
    cnpj = models.CharField(max_length=18, unique=True, null=True, blank=True, verbose_name=_("CNPJ"))
    contato = models.CharField(max_length=100, blank=True, verbose_name=_("Contato"))
    email = models.EmailField(max_length=255, unique=True, verbose_name=_("E-mail"))
    telefone = models.CharField(max_length=20, blank=True, verbose_name=_("Telefone"))

    class Meta:
        verbose_name = _("Fornecedor")
        verbose_name_plural = _("Fornecedores")
        ordering = ['razao_social']

    def __str__(self):
        return self.razao_social

class DadoBancarioFornecedor(TenantScopedModel):
    TIPO_CONTA_CHOICES = [
        ('corrente', _('Conta Corrente')),
        ('poupanca', _('Conta Poupança')),
        ('outro', _('Outro'))
    ]

    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.CASCADE, related_name='dados_bancarios', verbose_name=_("Fornecedor Associado"))
    codigo_banco = models.CharField(max_length=10, verbose_name=_("Código do Banco"))
    agencia = models.CharField(max_length=10, verbose_name=_("Agência"))
    agencia_dv = models.CharField(max_length=1, null=True, blank=True, verbose_name=_("DV da Agência"))
    conta = models.CharField(max_length=20, verbose_name=_("Conta"))
    conta_dv = models.CharField(max_length=1, null=True, blank=True, verbose_name=_("DV da Conta"))
    codigo_cedente = models.CharField(max_length=25, null=True, blank=True, verbose_name=_("Código Cedente/Convênio"))
    carteira = models.CharField(max_length=25, null=True, blank=True, verbose_name=_("Carteira"))
    chave_pix = models.CharField(max_length=512, null=True, blank=True, verbose_name=_("Chave PIX"))
    tipo_conta = models.CharField(max_length=50, choices=TIPO_CONTA_CHOICES, default='corrente', verbose_name=_("Tipo de Conta"))
    observacoes = models.TextField(null=True, blank=True, verbose_name=_("Observações"))
    data_atualizacao = models.DateTimeField(auto_now=True, verbose_name=_("Data de Atualização"))
        
    class Meta:
        verbose_name = _("Dado Bancário do Fornecedor")
        verbose_name_plural = _("Dados Bancários dos Fornecedores")

    def __str__(self):
        return f"Dados Bancários de {self.fornecedor.razao_social} - Banco {self.codigo_banco}"

class ProdutoServicoFornecedor(TenantScopedModel):
    TIPO_PRODUTO_SERVICO_CHOICES = [
        ('aluguel', _('Aluguel')),
        ('aluguel_equipamento', _('Aluguel de Equipamento')),
        ('aluguel_maquinario', _('Aluguel de Maquinário')),
        ('assinatura', _('Assinatura')),
        ('comissao', _('Comissão')),
        ('consultoria', _('Consultoria')),
        ('equipamento_obra', _('Equipamento de Obra')),
        ('equipamento_pessoal', _('Equipamento Pessoal')),
        ('ferramenta', _('Ferramenta')),
        ('frete', _('Frete')),
        ('hardware', _('Hardware')),
        ('imposto', _('Imposto')),
        ('licenca', _('Licença')),
        ('maquina', _('Máquina')),
        ('manutencao', _('Manutenção')),
        ('material_acabamento', _('Material de Acabamento')),
        ('material_construcao', _('Material de Construção')),
        ('material_electrico', _('Material Elétrico')),
        ('material_escritorio', _('Material de Escritório')),
        ('material_hidraulico', _('Material Hidráulico')),
        ('material_jardinagem', _('Material de Jardinagem')),
        ('material_limpeza', _('Material de Limpeza')),
        ('material_manutencao', _('Material de Manutenção')),
        ('material_pavimentacao', _('Material de Pavimentação')),
        ('obra', _('Obra')),
        ('produto', _('Produto')),
        ('projeto', _('Projeto')),
        ('servico', _('Serviço')),
        ('servico_administrativo', _('Serviço Administrativo')),
        ('servico_almoxarifado', _('Serviço de Almoxarifado')),
        ('servico_construcao', _('Serviço de Construção')),
        ('servico_construcao_civil', _('Serviço de Construção Civil')),
        ('servico_contabil', _('Serviço Contábil')),
        ('servico_consultoria', _('Serviço de Consultoria')),
        ('servico_eletrica', _('Serviço Elétrico')),
        ('servico_engenharia_arquitetura', _('Serviço de Engenharia e Arquitetura')),
        ('servico_estoque', _('Serviço de Estoque')),
        ('servico_financeiro', _('Serviço Financeiro')),
        ('servico_gerenciamento', _('Serviço de Gerenciamento')),
        ('servico_hidraulica', _('Serviço Hidráulico')),
        ('servico_instalacao', _('Serviço de Instalação')),
        ('servico_juridico', _('Serviço Jurídico')),
        ('servico_logistica', _('Serviço de Logística')),
        ('servico_manutencao', _('Serviço de Manutenção')),
        ('servico_marketing', _('Serviço de Marketing')),
        ('servico_pintura', _('Serviço de Pintura')),
        ('servico_reforma', _('Serviço de Reforma')),
        ('servico_tecnico', _('Serviço Técnico')),
        ('servico_terceirizado', _('Serviço Terceirizado')),
        ('servico_terraplenagem', _('Serviço de Terraplenagem')),
        ('servico_transporte', _('Serviço de Transporte')),
        ('servico_vendas', _('Serviço de Vendas')),
        ('software', _('Software')),
        ('suporte', _('Suporte')),
        ('taxa', _('Taxa')),
        ('treinamento', _('Treinamento')),
        ('veiculo', _('Veículo')),
        ('outro', _('Outro')),
    ]

    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.SET_NULL, null=True, blank=True, related_name="produtos", verbose_name=_("Fornecedor"))
    nome_produto_servico = models.CharField(max_length=255, verbose_name=_("Nome do Produto/Serviço"))
    descricao = models.TextField(null=True, blank=True, verbose_name=_("Descrição do Produto/Serviço"))
    unidade_medida = models.CharField(max_length=50, verbose_name=_("Unidade de Medida"))
    preco_unitario = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Preço Unitário"))
    data_cotacao = models.DateField(auto_now_add=True, verbose_name=_("Data da Cotação"))
    tipo_produto_servico = models.CharField(max_length=50, choices=TIPO_PRODUTO_SERVICO_CHOICES, default='produto', verbose_name=_("Tipo de Produto/Serviço"))

    class Meta:
        verbose_name = _("Produto ou Serviço do Fornecedor")
        verbose_name_plural = _("Produtos e Serviços dos Fornecedores")
        ordering = ['nome_produto_servico']

    def __str__(self):
        return self.nome_produto_servico
