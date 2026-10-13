# backend/modulosil/models.py
"""SIL — Estoque & Logística interna.

Núcleo (SIL.1): `LocalEstoque` (central + canteiros), `SaldoEstoque` (saldo
valorado por custo médio ponderado móvel), `MovimentacaoEstoque` (ledger
append-only) e `Inventario`. Logística (SIL.2): `Requisicao`, `Transferencia`,
`Devolucao` e rastreabilidade (`Lote`/`SaldoLote`). O **que** se estoca vem do
catálogo-mestre (`catalogo.Item`, flag `estocavel`). Desenho em
docs/modulos/modulosil.md.
"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from nucleo.tenancy import TenantScopedModel


class LocalEstoque(TenantScopedModel):
    """Local físico de estoque: almoxarifado **central** ou **canteiro** de obra
    (vínculo opcional a obra/empreendimento; ou a fornecedor p/ consignação)."""

    class Tipo(models.TextChoices):
        CENTRAL = "central", _("Almoxarifado central")
        CANTEIRO = "canteiro", _("Canteiro de obra")
        FORNECEDOR = "fornecedor", _("Consignação (fornecedor)")
        OUTRO = "outro", _("Outro")

    local_id = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=150, verbose_name=_("Nome"))
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.CENTRAL, verbose_name=_("Tipo"))
    obra = models.ForeignKey("obras.Obra", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Obra"))
    empreendimento = models.ForeignKey("empreendimentos.Empreendimento", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Empreendimento"))
    fornecedor = models.ForeignKey("fornecedores.Fornecedor", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Fornecedor (consignação)"))
    endereco = models.CharField(max_length=255, blank=True, verbose_name=_("Endereço"))
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))

    class Meta:
        verbose_name = _("Local de Estoque")
        verbose_name_plural = _("Locais de Estoque")
        ordering = ["nome"]
        constraints = [models.UniqueConstraint(fields=["tenant", "nome"], name="sil_local_nome_por_tenant")]

    def __str__(self):
        return self.nome


class Lote(TenantScopedModel):
    """Rastreabilidade de itens com flag `rastreavel`: número, validade, fornecedor."""

    lote_id = models.AutoField(primary_key=True)
    item = models.ForeignKey("catalogo.Item", on_delete=models.PROTECT, related_name="lotes", verbose_name=_("Item"))
    numero_lote = models.CharField(max_length=60, verbose_name=_("Número do lote"))
    validade = models.DateField(null=True, blank=True, verbose_name=_("Validade"))
    fornecedor = models.ForeignKey("fornecedores.Fornecedor", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Fornecedor"))
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Lote")
        verbose_name_plural = _("Lotes")
        ordering = ["item", "validade"]
        constraints = [models.UniqueConstraint(fields=["tenant", "item", "numero_lote"], name="sil_lote_item_numero")]

    def __str__(self):
        return f"{self.numero_lote} ({self.item_id})"


class SaldoEstoque(TenantScopedModel):
    """Saldo de um `Item` num `LocalEstoque` — tabela de consulta. `custo_medio`
    é ponderado móvel (recalculado a cada entrada). `reservado` protege o saldo
    comprometido por requisições aprovadas."""

    saldo_id = models.AutoField(primary_key=True)
    item = models.ForeignKey("catalogo.Item", on_delete=models.PROTECT, related_name="saldos", verbose_name=_("Item"))
    local = models.ForeignKey(LocalEstoque, on_delete=models.CASCADE, related_name="saldos", verbose_name=_("Local"))
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name=_("Quantidade"))
    custo_medio = models.DecimalField(max_digits=15, decimal_places=4, default=0, verbose_name=_("Custo médio unitário"))
    reservado = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name=_("Reservado"))
    ponto_reposicao = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name=_("Ponto de reposição"))

    class Meta:
        verbose_name = _("Saldo de Estoque")
        verbose_name_plural = _("Saldos de Estoque")
        ordering = ["item"]
        constraints = [models.UniqueConstraint(fields=["tenant", "item", "local"], name="sil_saldo_item_local")]

    @property
    def disponivel(self):
        return self.quantidade - self.reservado

    @property
    def valor_total(self):
        return self.quantidade * self.custo_medio

    @property
    def abaixo_minimo(self):
        return self.ponto_reposicao > 0 and self.quantidade <= self.ponto_reposicao

    def __str__(self):
        return f"{self.item_id}@{self.local_id}: {self.quantidade}"


class SaldoLote(TenantScopedModel):
    """Saldo por lote num local (rastreabilidade fina)."""

    saldo_lote_id = models.AutoField(primary_key=True)
    lote = models.ForeignKey(Lote, on_delete=models.CASCADE, related_name="saldos", verbose_name=_("Lote"))
    local = models.ForeignKey(LocalEstoque, on_delete=models.CASCADE, related_name="saldos_lote", verbose_name=_("Local"))
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name=_("Quantidade"))

    class Meta:
        verbose_name = _("Saldo por Lote")
        verbose_name_plural = _("Saldos por Lote")
        constraints = [models.UniqueConstraint(fields=["tenant", "lote", "local"], name="sil_saldolote_lote_local")]


class Requisicao(TenantScopedModel):
    """Requisição de material da obra: reserva ao aprovar, baixa (SAÍDA) ao atender."""

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        PENDENTE = "pendente", _("Pendente de aprovação")
        APROVADA = "aprovada", _("Aprovada")
        ATENDIDA = "atendida", _("Atendida")
        PARCIAL = "parcial", _("Atendida parcialmente")
        CANCELADA = "cancelada", _("Cancelada")

    requisicao_id = models.AutoField(primary_key=True)
    local = models.ForeignKey(LocalEstoque, on_delete=models.PROTECT, related_name="requisicoes", verbose_name=_("Local (de onde sai)"))
    obra = models.ForeignKey("obras.Obra", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Obra (apropriação)"))
    etapa = models.ForeignKey("obras.EtapaObra", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Etapa (apropriação físico-financeira)"))
    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Solicitante"))
    aprovador = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Aprovador"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RASCUNHO, verbose_name=_("Status"))
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Requisição de Material")
        verbose_name_plural = _("Requisições de Material")
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Requisição #{self.requisicao_id}"


class ItemRequisicao(TenantScopedModel):
    item_requisicao_id = models.AutoField(primary_key=True)
    requisicao = models.ForeignKey(Requisicao, on_delete=models.CASCADE, related_name="itens", verbose_name=_("Requisição"))
    item = models.ForeignKey("catalogo.Item", on_delete=models.PROTECT, related_name="+", verbose_name=_("Item"))
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Quantidade"))
    quantidade_atendida = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name=_("Quantidade atendida"))

    class Meta:
        verbose_name = _("Item de Requisição")
        verbose_name_plural = _("Itens de Requisição")
        ordering = ["item_requisicao_id"]


class Transferencia(TenantScopedModel):
    """Movimento entre locais: transf_saída na origem + transf_entrada no destino."""

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        EXECUTADA = "executada", _("Executada")
        CANCELADA = "cancelada", _("Cancelada")

    transferencia_id = models.AutoField(primary_key=True)
    origem = models.ForeignKey(LocalEstoque, on_delete=models.PROTECT, related_name="transferencias_saida", verbose_name=_("Origem"))
    destino = models.ForeignKey(LocalEstoque, on_delete=models.PROTECT, related_name="transferencias_entrada", verbose_name=_("Destino"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RASCUNHO, verbose_name=_("Status"))
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Transferência")
        verbose_name_plural = _("Transferências")
        ordering = ["-criado_em"]


class ItemTransferencia(TenantScopedModel):
    item_transferencia_id = models.AutoField(primary_key=True)
    transferencia = models.ForeignKey(Transferencia, on_delete=models.CASCADE, related_name="itens", verbose_name=_("Transferência"))
    item = models.ForeignKey("catalogo.Item", on_delete=models.PROTECT, related_name="+", verbose_name=_("Item"))
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Quantidade"))
    lote = models.ForeignKey(Lote, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Lote"))

    class Meta:
        verbose_name = _("Item de Transferência")
        verbose_name_plural = _("Itens de Transferência")
        ordering = ["item_transferencia_id"]


class Devolucao(TenantScopedModel):
    """Devolução ao **fornecedor** (SAÍDA) ou ao **estoque** (ENTRADA, estorno)."""

    class Tipo(models.TextChoices):
        FORNECEDOR = "fornecedor", _("Ao fornecedor")
        ESTOQUE = "estoque", _("Ao estoque")

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        EXECUTADA = "executada", _("Executada")
        CANCELADA = "cancelada", _("Cancelada")

    devolucao_id = models.AutoField(primary_key=True)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.FORNECEDOR, verbose_name=_("Tipo"))
    local = models.ForeignKey(LocalEstoque, on_delete=models.PROTECT, related_name="devolucoes", verbose_name=_("Local"))
    fornecedor = models.ForeignKey("fornecedores.Fornecedor", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Fornecedor"))
    pedido_scm_ref = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Ref. do pedido (SCM)"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RASCUNHO, verbose_name=_("Status"))
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Devolução")
        verbose_name_plural = _("Devoluções")
        ordering = ["-criado_em"]


class ItemDevolucao(TenantScopedModel):
    item_devolucao_id = models.AutoField(primary_key=True)
    devolucao = models.ForeignKey(Devolucao, on_delete=models.CASCADE, related_name="itens", verbose_name=_("Devolução"))
    item = models.ForeignKey("catalogo.Item", on_delete=models.PROTECT, related_name="+", verbose_name=_("Item"))
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Quantidade"))
    lote = models.ForeignKey(Lote, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Lote"))

    class Meta:
        verbose_name = _("Item de Devolução")
        verbose_name_plural = _("Itens de Devolução")
        ordering = ["item_devolucao_id"]


class Inventario(TenantScopedModel):
    """Contagem (geral/cíclica): ao fechar, gera movimentações de AJUSTE."""

    class Tipo(models.TextChoices):
        GERAL = "geral", _("Geral")
        CICLICA = "ciclica", _("Cíclica")

    class Status(models.TextChoices):
        ABERTO = "aberto", _("Aberto")
        FECHADO = "fechado", _("Fechado")

    inventario_id = models.AutoField(primary_key=True)
    local = models.ForeignKey(LocalEstoque, on_delete=models.PROTECT, related_name="inventarios", verbose_name=_("Local"))
    tipo = models.CharField(max_length=8, choices=Tipo.choices, default=Tipo.GERAL, verbose_name=_("Tipo"))
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ABERTO, verbose_name=_("Status"))
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    criado_em = models.DateTimeField(auto_now_add=True)
    fechado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Inventário")
        verbose_name_plural = _("Inventários")
        ordering = ["-criado_em"]


class ItemInventario(TenantScopedModel):
    item_inventario_id = models.AutoField(primary_key=True)
    inventario = models.ForeignKey(Inventario, on_delete=models.CASCADE, related_name="itens", verbose_name=_("Inventário"))
    item = models.ForeignKey("catalogo.Item", on_delete=models.PROTECT, related_name="+", verbose_name=_("Item"))
    lote = models.ForeignKey(Lote, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Lote"))
    quantidade_sistema = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name=_("Quantidade no sistema"))
    quantidade_contada = models.DecimalField(max_digits=14, decimal_places=3, default=0, verbose_name=_("Quantidade contada"))
    #: O ajuste que o fechamento aplicou (contada − saldo de então), **com sinal**.
    #: O ledger guarda só a quantidade absoluta (o sentido vem do tipo, e o AJUSTE
    #: não diz qual); sem este número, reabrir não saberia o que estornar.
    #: Nulo enquanto aberto — e nos fechados antes de este campo existir.
    ajuste_aplicado = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True, verbose_name=_("Ajuste aplicado"))

    class Meta:
        verbose_name = _("Item de Inventário")
        verbose_name_plural = _("Itens de Inventário")
        ordering = ["item_inventario_id"]


class MovimentacaoEstoque(TenantScopedModel):
    """**Ledger append-only** de todo movimento de estoque. A `quantidade` é
    sempre positiva; o sentido vem do `tipo`. Carrega os seams de origem
    (recebimento do SCM, requisição, transferência, devolução, inventário) e a
    obra de apropriação do consumo (→ DRE por obra no ERP)."""

    class Tipo(models.TextChoices):
        ENTRADA = "entrada", _("Entrada")
        SAIDA = "saida", _("Saída")
        AJUSTE = "ajuste", _("Ajuste de inventário")
        TRANSF_SAIDA = "transf_saida", _("Transferência (saída)")
        TRANSF_ENTRADA = "transf_entrada", _("Transferência (entrada)")
        DEVOLUCAO = "devolucao", _("Devolução")

    mov_id = models.AutoField(primary_key=True)
    item = models.ForeignKey("catalogo.Item", on_delete=models.PROTECT, related_name="movimentacoes_sil", verbose_name=_("Item"))
    local = models.ForeignKey(LocalEstoque, on_delete=models.PROTECT, related_name="movimentacoes", verbose_name=_("Local"))
    tipo = models.CharField(max_length=14, choices=Tipo.choices, verbose_name=_("Tipo"))
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Quantidade"))
    custo_unitario = models.DecimalField(max_digits=15, decimal_places=4, default=0, verbose_name=_("Custo unitário"))
    lote = models.ForeignKey(Lote, null=True, blank=True, on_delete=models.SET_NULL, related_name="movimentacoes", verbose_name=_("Lote"))
    obra = models.ForeignKey("obras.Obra", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Obra (apropriação)"))
    etapa = models.ForeignKey("obras.EtapaObra", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Etapa (apropriação físico-financeira)"))
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # Seams de origem (rastreabilidade do documento que gerou o movimento).
    recebimento_scm_ref = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Ref. do recebimento (SCM)"))
    item_recebimento_ref = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Ref. do item de recebimento (SCM)"))
    requisicao = models.ForeignKey(Requisicao, null=True, blank=True, on_delete=models.SET_NULL, related_name="movimentacoes")
    transferencia = models.ForeignKey(Transferencia, null=True, blank=True, on_delete=models.SET_NULL, related_name="movimentacoes")
    devolucao = models.ForeignKey(Devolucao, null=True, blank=True, on_delete=models.SET_NULL, related_name="movimentacoes")
    inventario = models.ForeignKey(Inventario, null=True, blank=True, on_delete=models.SET_NULL, related_name="movimentacoes")
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("Movimentação de Estoque")
        verbose_name_plural = _("Movimentações de Estoque")
        ordering = ["-criado_em", "-mov_id"]
        indexes = [
            models.Index(fields=["tenant", "item", "local"]),
            models.Index(fields=["tenant", "recebimento_scm_ref"]),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.quantidade} de {self.item_id} @ {self.local_id}"


class EntregaEPI(TenantScopedModel):
    """Entrega de EPI a um colaborador (NR-6). É a **prova trabalhista**: quem
    recebeu, qual **CA** e sua validade, quando, e a devolução/troca. Integra ao
    RH (`rh.Funcionario`) quando existe; senão `colaborador_nome` (texto livre)."""

    class Status(models.TextChoices):
        ENTREGUE = "entregue", _("Entregue")
        DEVOLVIDO = "devolvido", _("Devolvido")
        SUBSTITUIDO = "substituido", _("Substituído (troca)")
        DANIFICADO = "danificado", _("Danificado/descartado")

    entrega_epi_id = models.AutoField(primary_key=True)
    item = models.ForeignKey("catalogo.Item", on_delete=models.PROTECT, related_name="entregas_epi", verbose_name=_("EPI (item do catálogo)"))
    colaborador = models.ForeignKey("rh.Funcionario", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Colaborador (RH)"))
    colaborador_nome = models.CharField(max_length=120, blank=True, verbose_name=_("Colaborador (nome)"))
    local = models.ForeignKey(LocalEstoque, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Local (de onde saiu)"))
    obra = models.ForeignKey("obras.Obra", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Obra (apropriação)"))
    quantidade = models.DecimalField(max_digits=10, decimal_places=2, default=1, verbose_name=_("Quantidade"))
    ca_numero = models.CharField(max_length=20, blank=True, verbose_name=_("CA (Certificado de Aprovação)"))
    ca_validade = models.DateField(null=True, blank=True, verbose_name=_("Validade do CA"))
    data_entrega = models.DateField(default=timezone.localdate, verbose_name=_("Data da entrega"))
    data_prevista_troca = models.DateField(null=True, blank=True, verbose_name=_("Troca prevista"))
    data_devolucao = models.DateField(null=True, blank=True, verbose_name=_("Devolução"))
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ENTREGUE, verbose_name=_("Status"))
    baixou_estoque = models.BooleanField(default=False, verbose_name=_("Baixou do estoque"))
    assinado = models.BooleanField(default=False, verbose_name=_("Comprovante assinado"))
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Entrega de EPI")
        verbose_name_plural = _("Entregas de EPI")
        ordering = ["-data_entrega", "-entrega_epi_id"]

    @property
    def vencido(self):
        hoje = timezone.localdate()
        if self.status not in (self.Status.ENTREGUE,):
            return False
        return bool((self.ca_validade and self.ca_validade < hoje) or (self.data_prevista_troca and self.data_prevista_troca < hoje))

    def __str__(self):
        return f"EPI {self.item_id} → {self.colaborador_id or self.colaborador_nome}"


class Ferramenta(TenantScopedModel):
    """Bem de **ferramentaria** (comodato interno): patrimônio, estado e o
    controle de calibração/manutenção. O empréstimo em si é `EmprestimoFerramenta`."""

    class Estado(models.TextChoices):
        DISPONIVEL = "disponivel", _("Disponível")
        EMPRESTADA = "emprestada", _("Emprestada")
        MANUTENCAO = "manutencao", _("Em manutenção")
        BAIXADA = "baixada", _("Baixada")

    ferramenta_id = models.AutoField(primary_key=True)
    item = models.ForeignKey("catalogo.Item", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Item do catálogo (equipamento)"))
    nome = models.CharField(max_length=150, verbose_name=_("Nome/descrição"))
    patrimonio = models.CharField(max_length=40, blank=True, verbose_name=_("Nº de patrimônio"))
    local = models.ForeignKey(LocalEstoque, null=True, blank=True, on_delete=models.SET_NULL, related_name="ferramentas", verbose_name=_("Local base"))
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.DISPONIVEL, verbose_name=_("Estado"))
    calibravel = models.BooleanField(default=False, verbose_name=_("Requer calibração"))
    proxima_calibracao = models.DateField(null=True, blank=True, verbose_name=_("Próxima calibração"))
    proxima_manutencao = models.DateField(null=True, blank=True, verbose_name=_("Próxima manutenção"))
    valor = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Valor do bem"))
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Ferramenta")
        verbose_name_plural = _("Ferramentas")
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "patrimonio"], condition=~models.Q(patrimonio=""), name="sil_ferramenta_patrimonio_por_tenant"),
        ]

    @property
    def manutencao_vencendo(self):
        prazo = timezone.localdate() + timedelta(days=30)
        datas = [d for d in (self.proxima_calibracao, self.proxima_manutencao) if d]
        return any(d <= prazo for d in datas) if datas else False

    def __str__(self):
        return f"{self.nome}{f' ({self.patrimonio})' if self.patrimonio else ''}"


class EmprestimoFerramenta(TenantScopedModel):
    """Comodato interno: empréstimo de uma `Ferramenta` a um colaborador, com
    devolução e alerta de atraso. Integra ao RH quando há."""

    class Status(models.TextChoices):
        EMPRESTADA = "emprestada", _("Emprestada")
        DEVOLVIDA = "devolvida", _("Devolvida")

    emprestimo_id = models.AutoField(primary_key=True)
    ferramenta = models.ForeignKey(Ferramenta, on_delete=models.PROTECT, related_name="emprestimos", verbose_name=_("Ferramenta"))
    colaborador = models.ForeignKey("rh.Funcionario", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Colaborador (RH)"))
    colaborador_nome = models.CharField(max_length=120, blank=True, verbose_name=_("Colaborador (nome)"))
    obra = models.ForeignKey("obras.Obra", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Obra"))
    data_emprestimo = models.DateField(default=timezone.localdate, verbose_name=_("Empréstimo"))
    data_prevista_devolucao = models.DateField(null=True, blank=True, verbose_name=_("Devolução prevista"))
    data_devolucao = models.DateField(null=True, blank=True, verbose_name=_("Devolvida em"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.EMPRESTADA, verbose_name=_("Status"))
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Empréstimo de Ferramenta")
        verbose_name_plural = _("Empréstimos de Ferramenta")
        ordering = ["-data_emprestimo", "-emprestimo_id"]

    @property
    def atrasada(self):
        return bool(self.status == self.Status.EMPRESTADA and self.data_prevista_devolucao and self.data_prevista_devolucao < timezone.localdate())

    def __str__(self):
        return f"Empréstimo #{self.emprestimo_id} · {self.ferramenta_id}"
