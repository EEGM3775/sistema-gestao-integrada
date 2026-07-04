# rh/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from nucleo.tenancy import TenantScopedModel

class Cargo(TenantScopedModel):
    cargo_id = models.AutoField(primary_key=True, verbose_name=_("ID do Cargo"))
    nome_cargo = models.CharField(max_length=100, unique=True, verbose_name=_("Nome do Cargo"))
    descricao = models.TextField(blank=True, verbose_name=_("Descrição"))
    departamento = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("Departamento"))

    class Meta:
        verbose_name = _("Cargo")
        verbose_name_plural = _("Cargos")
        ordering = ['nome_cargo']

    def __str__(self):
        return self.nome_cargo

class Funcionario(TenantScopedModel):
    GENERO_CHOICES = [
        ('masculino', _('Masculino')),
        ('feminino', _('Feminino')),
        ('outro', _('Outro')),
    ]
    ESTADO_CIVIL_CHOICES = [
        ('solteiro', _('Solteiro(a)')),
        ('casado', _('Casado(a)')),
        ('divorciado', _('Divorciado(a)')),
        ('viuvo', _('Viúvo(a)')),
        ('uniao_estavel', _('União Estável')),
    ]
    STATUS_CONTRATO_CHOICES = [
        ('ativo', _('Ativo')),
        ('inativo', _('Inativo')),
        ('ferias', _('Férias')),
        ('licenca', _('Licença')),
        ('desligado', _('Desligado')),
    ]

    funcionario_id = models.AutoField(primary_key=True, verbose_name=_("Funcionário ID"))
    usuario = models.OneToOneField('nucleo.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='funcionario_profile', verbose_name=_("Usuário do Sistema"))
    cargo = models.ForeignKey(Cargo, on_delete=models.SET_NULL, null=True, verbose_name=_("Cargo"))
    empreendimento_vinculado = models.ForeignKey(
        'empreendimentos.Empreendimento',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Empreendimento Vinculado"),
        help_text=_("Empreendimento ao qual o funcionário está diretamente contratado, se aplicável.")
    )
    nome_completo = models.CharField(max_length=255, verbose_name=_("Nome Completo"))
    cpf = models.CharField(max_length=14, unique=True, verbose_name=_("CPF"))
    rg = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("RG"))
    data_nascimento = models.DateField(verbose_name=_("Data de Nascimento"))
    genero = models.CharField(max_length=20, choices=GENERO_CHOICES, verbose_name=_("Gênero"))
    estado_civil = models.CharField(max_length=20, choices=ESTADO_CIVIL_CHOICES, blank=True, null=True, verbose_name=_("Estado Civil"))
    telefone_pessoal = models.CharField(max_length=25, null=True, blank=True, verbose_name=_("Telefone"))
    telefone_celular = models.CharField(max_length=20, null=True, blank=True, unique=True, verbose_name=_("Telefone Celular (WhatsApp)"), help_text=_("Número com código do país. Ex: +5575912345678"))
    email_pessoal = models.EmailField(max_length=255, null=True, blank=True, unique=True, verbose_name=_("E-mail Pessoal"))
    endereco_completo = models.TextField(verbose_name=_("Endereço Completo"))
    data_admissao = models.DateField(verbose_name=_("Data de Admissão"))
    data_demissao = models.DateField(null=True, blank=True, verbose_name=_("Data de Demissão"))
    salario_base = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Salário Base"))
    status_contrato = models.CharField(max_length=50, choices=STATUS_CONTRATO_CHOICES, default='ativo', verbose_name=_("Status do Contrato"))
    numero_ctps = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("Número da CTPS (Carteira de Trabalho)"))
    serie_ctps = models.CharField(max_length=10, null=True, blank=True, verbose_name=_("Série da CTPS"))
    pis_pasep = models.CharField(max_length=15, null=True, blank=True, verbose_name=_("PIS/PASEP"))
    carteira_trabalho = models.FileField(upload_to='carteiras_trabalho/', null=True, blank=True, verbose_name=_("Carteira de Trabalho (CTPS)"))
    carteira_trabalho_data_emissao = models.DateField(null=True, blank=True, verbose_name=_("Data de Emissão da CTPS"))
    carteira_trabalho_serie = models.CharField(max_length=10, null=True, blank=True, verbose_name=_("Série da CTPS"))
    carteira_trabalho_numero = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("Número da CTPS"))
    carteira_trabalho_uf = models.CharField(max_length=2, null=True, blank=True, verbose_name=_("UF da CTPS"))
    carteira_trabalho_data_validade = models.DateField(null=True, blank=True, verbose_name=_("Data de Validade da CTPS"))
    carteira_trabalho_observacoes = models.TextField(null=True, blank=True, verbose_name=_("Observações da CTPS"))
    data_cadastro = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Cadastro"))
    data_atualizacao = models.DateTimeField(auto_now=True, verbose_name=_("Data de Atualização"))

    class Meta:
        verbose_name = _("Funcionário")
        verbose_name_plural = _("Funcionários")
        ordering = ['nome_completo']

    def __str__(self):
        return self.nome_completo

class DadoMedicoFuncionario(TenantScopedModel):
    funcionario = models.OneToOneField(Funcionario, on_delete=models.CASCADE, verbose_name=_("Funcionário"))
    numero_cartao_sus = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("Número do Cartão SUS"))
    tipo_sanguineo = models.CharField(max_length=5, null=True, blank=True, verbose_name=_("Tipo Sanguíneo"))
    alergias = models.TextField(null=True, blank=True, verbose_name=_("Alergias"))
    medicamentos = models.TextField(null=True, blank=True, verbose_name=_("Medicamentos em Uso"))
    historico_doencas = models.TextField(null=True, blank=True, verbose_name=_("Histórico de Doenças"))
    contato_emergencia_nome = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Nome do Contato de Emergência"))
    contato_emergencia_telefone = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("Telefone do Contato de Emergência"))
    observacoes_medicas = models.TextField(null=True, blank=True, verbose_name=_("Observações Médicas"))

    class Meta:
        verbose_name = _("Dado Médico do Funcionário")
        verbose_name_plural = _("Dados Médicos dos Funcionários")

    def __str__(self):
        return f"Dados Médicos - {self.funcionario.nome_completo} (Cartão SUS: {self.numero_cartao_sus})"

class ASOFuncionario(TenantScopedModel):
    TIPO_EXAME_CHOICES = [
        ('admissional', _('Admissional')),
        ('periodico', _('Periódico')),
        ('demissional', _('Demissional')),
    ]
    STATUS_CHOICES = [
        ('ativo', _('Ativo')),
        ('inativo', _('Inativo')),
        ('pendente', _('Pendente')),
        ('cancelado', _('Cancelado')),
    ]

    aso_id = models.AutoField(primary_key=True, verbose_name=_("ASO ID"))
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='asos', verbose_name=_("Funcionário"))
    tipo_exame = models.CharField(max_length=50, choices=TIPO_EXAME_CHOICES, verbose_name=_("Tipo de Exame"))
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='ativo', verbose_name=_("Status"))
    data_exame = models.DateField(verbose_name=_("Data do Exame"))
    data_validade = models.DateField(null=True, blank=True, verbose_name=_("Data de Validade"))
    arquivo = models.FileField(upload_to='asos_funcionarios/', null=True, blank=True, verbose_name=_("Documento ASO"))
    observacoes = models.TextField(null=True, blank=True, verbose_name=_("Observações"))

    class Meta:
        verbose_name = _("ASO do Funcionário")
        verbose_name_plural = _("ASOs dos Funcionários")
        ordering = ['-data_exame']

    def __str__(self):
        return f"ASO {self.get_tipo_exame_display()} - {self.funcionario.nome_completo} ({self.data_exame})"

class DocumentoFuncionario(TenantScopedModel):
    TIPO_DOCUMENTO_CHOICES = [
        ('rg', _('RG')),
        ('cpf', _('CPF')),
        ('cnh', _('CNH')),
        ('ctps', _('Carteira de Trabalho (CTPS)')),
        ('comprovante_residencia', _('Comprovante de Residência')),
        ('certificado_curso', _('Certificado de Curso')),
        ('aso', _('ASO (Atestado de Saúde Ocupacional)')),
        ('outros', _('Outros')),
    ]

    documento_id = models.AutoField(primary_key=True, verbose_name=_("Documento ID"))
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='documentos', verbose_name=_("Funcionário"))
    tipo_documento = models.CharField(max_length=50, choices=TIPO_DOCUMENTO_CHOICES, verbose_name=_("Tipo de Documento"))
    nome_documento = models.CharField(max_length=255, verbose_name=_("Nome do Documento"), help_text=_("Especifique o documento se 'Outros' for selecionado."))
    arquivo = models.FileField(upload_to='documentos_funcionarios/', verbose_name=_("Arquivo"))
    data_upload = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Upload"))

    class Meta:
        verbose_name = _("Documento do Funcionário")
        verbose_name_plural = _("Documentos dos Funcionários")
        ordering = ['-data_upload']

    def __str__(self):
        return f"{self.get_tipo_documento_display()} de {self.funcionario.nome_completo}"

class DadoBancarioFuncionario(TenantScopedModel):
    TIPO_CONTA_CHOICES = [
        ('corrente', _('Conta Corrente')),
        ('poupanca', _('Conta Poupança')),
        ('investimento', _('Conta de Investimento')),
        ('salario', _('Conta Salário')),
        ('conta_conjunta', _('Conta Conjunta')),
        ('conta_empresarial', _('Conta Empresarial')),
        ('outro', _('Outro')),
    ]

    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='dados_bancarios', verbose_name=_("Funcionário"))
    codigo_banco = models.CharField(max_length=10, verbose_name=_("Código do Banco"), help_text=_("Código do seu banco"))
    agencia = models.CharField(max_length=10, verbose_name=_("Agência"), help_text=_("Número da agência bancária"))
    agencia_dv = models.CharField(max_length=1, verbose_name=_("DV da Agência"), null=True, blank=True)
    conta = models.CharField(max_length=20, verbose_name=_("Conta"), help_text=_("Número da conta bancária"))
    conta_dv = models.CharField(max_length=1, verbose_name=_("DV da Conta"), null=True, blank=True)
    codigo_cedente = models.CharField(max_length=25, verbose_name=_("Código Cedente"), help_text=_("Também conhecido como Convênio ou Código do Beneficiário"), null=True, blank=True)
    carteira = models.CharField(max_length=25, verbose_name=_("Carteira"), help_text=_("Código da carteira de cobrança (fornecido pelo banco)"), null=True, blank=True)
    tipo_conta = models.CharField(max_length=50, choices=TIPO_CONTA_CHOICES, verbose_name=_("Tipo de Conta"))
    chave_pix = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Chave PIX"))
    titular_nome = models.CharField(max_length=255, verbose_name=_("Nome do Titular"))
    titular_cpf_cnpj = models.CharField(max_length=18, verbose_name=_("CPF do Titular"))
    observacoes = models.TextField(null=True, blank=True, verbose_name=_("Observações"))
    data_atualizacao = models.DateTimeField(auto_now=True, verbose_name=_("Data de Atualização"))

    class Meta:
        verbose_name = _("Dado Bancário do Funcionário")
        verbose_name_plural = _("Dados Bancários dos Funcionários")

    def __str__(self):
        return f"Dados Bancários de {self.funcionario.nome_completo}"

class PagamentoFuncionario(TenantScopedModel):
    FORMA_PAGAMENTO_CHOICES = [
        ('dinheiro', _('Dinheiro')),
        ('cartao_credito', _('Cartão de Crédito')),
        ('cartao_debito', _('Cartão de Débito')),
        ('transferencia', _('Transferência')),
        ('pix', _('PIX')),
        ('boleto', _('Boleto')),
        ('deposito', _('Depósito')),
        ('cheque', _('Cheque')),
        ('outro', _('Outro')),
    ]

    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='pagamentos', verbose_name=_("Funcionário"))
    data_pagamento = models.DateField(verbose_name=_("Data do Pagamento"))
    salario_base = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Salário Base"))
    descontos = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Descontos"), default=0.00)
    adicionais = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Adicionais"), default=0.00)
    extras = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Extras"), default=0.00)
    bonus = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Bônus"), default=0.00)
    tipos_descontos = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Tipos de Descontos (separados por vírgula)"))
    tipos_adicionais = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Tipos de Adicionais (separados por vírgula)"))
    tipos_extras = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Tipos de Extras (separados por vírgula)"))
    tipos_bonus = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Tipos de Bônus (separados por vírgula)"))
    salario_liquido = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("Valor Pago"), blank=True, default=0)
    forma_pagamento = models.CharField(max_length=50, choices=FORMA_PAGAMENTO_CHOICES, verbose_name=_("Forma de Pagamento"))
    parcela = models.IntegerField(verbose_name=_("Parcela"), default=1)
    referencia_pagamento = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("Referência do Pagamento"))
    link_holerite = models.URLField(max_length=512, null=True, blank=True, verbose_name=_("Link do Holerite"))
    observacoes = models.TextField(null=True, blank=True, verbose_name=_("Observações"))

    class Meta:
        verbose_name = _("Pagamento do Funcionário")
        verbose_name_plural = _("Pagamentos dos Funcionários")
        ordering = ['-data_pagamento']

    def __str__(self):
        return f"Pagamento de {self.funcionario.nome_completo} - {self.data_pagamento} - Parcela {self.parcela}"

class FolhaPagamento(TenantScopedModel):
    folha_id = models.AutoField(primary_key=True)
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='folhas_pagamento', verbose_name=_("Funcionário"))
    mes_referencia = models.DateField(verbose_name=_("Mês de Referência"))
    salario_bruto = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Salário Bruto"))
    total_descontos = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_("Total de Descontos"))
    total_proventos = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_("Total de Proventos"))
    salario_liquido = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Salário Líquido"))
    data_pagamento = models.DateField(null=True, blank=True, verbose_name=_("Data de Pagamento"))
    holerite = models.FileField(upload_to='holerites/%Y/%m/', null=True, blank=True, verbose_name=_("Holerite"))

    class Meta:
        verbose_name = _("Folha de Pagamento")
        verbose_name_plural = _("Folhas de Pagamento")
        unique_together = ('funcionario', 'mes_referencia')
        ordering = ['-mes_referencia', 'funcionario']

    def __str__(self):
        return f"Folha de {self.mes_referencia.strftime('%B/%Y')} para {self.funcionario.nome_completo}"
