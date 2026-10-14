# empreendimentos/models.py
from decimal import Decimal

from django.db import models
from django.db.models import Q
from nucleo.tenancy import Excluivel, TenantScopedModel
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


class Empreendimento(TenantScopedModel, Excluivel):
    empreendimento_id = models.AutoField(primary_key=True)
    empreendimento = models.CharField(max_length=255, verbose_name=_("Nome do Empreendimento"))
    razao_social = models.CharField(max_length=255, verbose_name=_("Razão Social"))
    cnpj = models.CharField(max_length=18, verbose_name=_("CNPJ"))
    # A entidade com CNPJ do empreendimento — a SPE, a SCP, o consórcio, o
    # patrimônio de afetação, ou a entidade externa dona dele quando o tenant só
    # executa (docs/modulos/entidades.md §1). Vazio: o empreendimento é das
    # participantes (ou da matriz), lançado no CNPJ/CPF delas.
    entidade_propria = models.ForeignKey(
        'entidades.Entidade', on_delete=models.PROTECT, null=True, blank=True,
        related_name='empreendimentos_proprios', verbose_name=_("Entidade própria (dona)"),
    )
    telefone = models.CharField(max_length=20, verbose_name=_("Telefone"))
    endereco = models.TextField(verbose_name=_("Endereço"))
    # Cidade/UF estruturados: `endereco` é texto livre e não serve para filtrar
    # nem agrupar a carteira ("clientes por cidade"). É a cidade do imóvel, que
    # não se confunde com a do cliente (Cliente.cidade é o endereço dele).
    cidade = models.CharField(max_length=100, blank=True, verbose_name=_("Cidade"))
    estado = models.CharField(max_length=2, blank=True, verbose_name=_("Estado"))
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
            models.UniqueConstraint(fields=['tenant', 'razao_social'], condition=models.Q(excluido_em__isnull=True), name='empreend_razao_unica_por_tenant'),
            models.UniqueConstraint(fields=['tenant', 'cnpj'], condition=models.Q(excluido_em__isnull=True), name='empreend_cnpj_unico_por_tenant'),
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





# Choices for Unidade
SITUACAO_UNIDADE_CHOICES = [
    ("disponivel", _("Disponível")),
    ("reservada", _("Reservada")),
    ("vendida", _("Vendida")),
    ("indisponivel", _("Indisponível")),
]

TIPO_UNIDADE_CHOICES = [
    ("lote", _("Lote")),
    ("apartamento", _("Apartamento")),
    ("casa", _("Casa")),
    ("sala", _("Sala comercial")),
    ("outro", _("Outro")),
]


class Unidade(TenantScopedModel):
    """O que se vende: o lote, o apartamento, a sala.

    **É cadastro do empreendimento, não da venda.** Antes, a unidade nascia
    junto com a aquisição — o comprador digitava "Apto 101" num campo livre *e*
    quadra/lote/andar em campos estruturados, sem nada garantindo que os dois
    combinassem e sem nada impedindo vender o mesmo lote duas vezes por dois
    caminhos. Aqui a unidade existe antes do comprador: o empreendimento
    cadastra o que tem à venda, e a aquisição apenas **aponta** para uma delas.
    Um lote, um rótulo, um dono.

    O ``valor_base`` é o **preço de tabela** — a referência da negociação, não o
    que o cliente paga. O valor pago sai do plano de pagamento da aquisição
    (desconto, entrada, juros, prazo) e fica lá, porque é da venda, não do lote:
    duas pessoas compram o mesmo tipo de lote por valores finais diferentes.
    """

    unidade_id = models.AutoField(primary_key=True)
    empreendimento = models.ForeignKey(
        Empreendimento, on_delete=models.CASCADE, related_name='unidades',
        verbose_name=_("Empreendimento"),
    )

    # Identificação estruturada — a hierarquia de mercado (loteamento usa
    # quadra/lote; vertical usa torre/andar/apto). Texto porque existe "Quadra A"
    # e "Lote 12-B"; a ordenação natural da grade cuida do "10 depois do 2".
    quadra = models.CharField(max_length=10, blank=True, verbose_name=_("Quadra"))
    lote = models.CharField(max_length=10, blank=True, verbose_name=_("Lote"))
    bloco_torre = models.CharField(max_length=20, blank=True, verbose_name=_("Bloco/Torre"))
    andar = models.CharField(max_length=10, blank=True, verbose_name=_("Andar"))
    apto = models.CharField(max_length=20, blank=True, verbose_name=_("Apto/Número"))

    tipo = models.CharField(
        max_length=20, choices=TIPO_UNIDADE_CHOICES, default="lote", verbose_name=_("Tipo"),
    )
    situacao = models.CharField(
        max_length=20, choices=SITUACAO_UNIDADE_CHOICES, default="disponivel",
        verbose_name=_("Situação"),
    )
    valor_base = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'),
        verbose_name=_("Valor base (tabela)"),
        help_text=_("Preço de tabela da unidade. A venda parte dele e aplica desconto, entrada e juros."),
    )
    area_privativa = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name=_("Área privativa (m²)"),
    )
    area_total = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name=_("Área total (m²)"),
    )
    endereco = models.CharField(max_length=255, blank=True, verbose_name=_("Endereço da unidade"))

    # ── Medidas e confrontações ───────────────────────────────────────────────
    # A área sozinha não descreve o imóvel: o contrato e a matrícula pedem
    # **quanto mede cada lado** e **com quem cada lado divide**. Sem isso o
    # memorial descritivo tem de ser redigido fora do sistema, e o que vai ao
    # cartório deixa de bater com o que está cadastrado.
    #
    # Quatro lados porque é o que o lote retangular — a esmagadora maioria —
    # tem; o irregular descreve o excedente em `observacoes`. A **frente** é, na
    # prática, a rua: é dela que sai o endereço e é ela que o comprador
    # reconhece. Decimal e não texto porque metro linear entra em conta (testada
    # × profundidade confere a área declarada).
    medida_frente = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        verbose_name=_("Frente (m)"),
    )
    medida_fundo = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        verbose_name=_("Fundo (m)"),
    )
    medida_lateral_direita = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        verbose_name=_("Lateral direita (m)"),
    )
    medida_lateral_esquerda = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        verbose_name=_("Lateral esquerda (m)"),
    )
    confrontante_frente = models.CharField(
        max_length=255, blank=True, verbose_name=_("Confrontante da frente"),
        help_text=_("Em geral a rua — é dela que sai o endereço da unidade."),
    )
    confrontante_fundo = models.CharField(
        max_length=255, blank=True, verbose_name=_("Confrontante do fundo"),
    )
    confrontante_lateral_direita = models.CharField(
        max_length=255, blank=True, verbose_name=_("Confrontante da lateral direita"),
    )
    confrontante_lateral_esquerda = models.CharField(
        max_length=255, blank=True, verbose_name=_("Confrontante da lateral esquerda"),
    )

    observacoes = models.TextField(blank=True, verbose_name=_("Observações"))
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Criação"))
    data_atualizacao = models.DateTimeField(auto_now=True, verbose_name=_("Data de Atualização"))

    class Meta:
        verbose_name = _("Unidade")
        verbose_name_plural = _("Unidades")
        ordering = ['empreendimento', 'quadra', 'lote', 'bloco_torre', 'andar', 'apto']
        constraints = [
            # Duas unidades com a mesma identificação no mesmo empreendimento
            # seriam a mesma unidade — e a venda não saberia qual das duas
            # entregou. É a trava que o texto livre nunca teve.
            models.UniqueConstraint(
                fields=['tenant', 'empreendimento', 'quadra', 'lote', 'bloco_torre', 'andar', 'apto'],
                name='unidade_identificacao_unica',
            ),
        ]
        indexes = [
            models.Index(fields=['empreendimento', 'situacao'], name='unidade_emp_situacao_idx'),
        ]

    @property
    def rotulo(self) -> str:
        """Como a unidade aparece na tela: 'QD 12 · LT 05' (loteamento) ou
        'Torre A · 3º · 302' (vertical). Fonte única — grade, ficha, extrato e
        contrato leem daqui, então não há como divergirem."""
        partes = []
        if self.quadra:
            partes.append(f"QD {self.quadra}")
        if self.lote:
            partes.append(f"LT {self.lote}")
        if self.bloco_torre:
            partes.append(self.bloco_torre)
        if self.andar:
            partes.append(f"{self.andar}º")
        if self.apto:
            partes.append(self.apto)
        return " · ".join(partes) or f"Unidade {self.pk}"

    LADOS = (
        ("frente", _("Frente"), "medida_frente", "confrontante_frente"),
        ("fundo", _("Fundo"), "medida_fundo", "confrontante_fundo"),
        ("lateral_direita", _("Lateral direita"),
         "medida_lateral_direita", "confrontante_lateral_direita"),
        ("lateral_esquerda", _("Lateral esquerda"),
         "medida_lateral_esquerda", "confrontante_lateral_esquerda"),
    )

    @property
    def confrontacoes(self) -> list[dict]:
        """Os quatro lados em forma de dado — medida e com quem divide.

        Só devolve o lado que tem alguma coisa preenchida: um lote com três
        divisas não deve exibir uma quarta linha vazia como se faltasse
        cadastro."""
        lados = []
        for chave, rotulo, campo_medida, campo_confrontante in self.LADOS:
            medida = getattr(self, campo_medida)
            confrontante = getattr(self, campo_confrontante)
            if medida is None and not confrontante:
                continue
            lados.append({
                "lado": chave,
                "rotulo": str(rotulo),
                "medida": str(medida) if medida is not None else None,
                "confrontante": confrontante,
            })
        return lados

    @property
    def descricao_confrontacoes(self) -> str:
        """O memorial em uma frase: 'Frente: 12,00 m, com a Rua das Acácias; …'.

        É o texto que vai ao contrato — montado aqui para que ficha, contrato e
        exportação não escrevam três versões da mesma descrição."""
        partes = []
        for lado in self.confrontacoes:
            medida = f"{Decimal(lado['medida']):.2f}".replace(".", ",") + " m" if lado["medida"] else None
            if medida and lado["confrontante"]:
                partes.append(f"{lado['rotulo']}: {medida}, com {lado['confrontante']}")
            elif medida:
                partes.append(f"{lado['rotulo']}: {medida}")
            else:
                partes.append(f"{lado['rotulo']}: com {lado['confrontante']}")
        return "; ".join(partes)

    def __str__(self):
        return f"{self.empreendimento.empreendimento} — {self.rotulo}"
