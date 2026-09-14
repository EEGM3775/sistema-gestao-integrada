# obras/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.db.models import Q, UniqueConstraint
from nucleo.tenancy import Excluivel, TenantScopedModel

class Obra(TenantScopedModel, Excluivel):
    STATUS_OBRA_CHOICES = [
        ("planejamento", _("Planejamento")),
        ("em_execucao", _("Em Execução")),
        ("concluida", _("Concluída")),
        ("cancelada", _("Cancelada")),
    ]

    obra_id = models.AutoField(primary_key=True)
    empreendimento = models.ForeignKey('empreendimentos.Empreendimento', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Empreendimento"))
    nome_obra = models.CharField(max_length=255, verbose_name=_("Nome da Obra"))
    endereco = models.TextField(verbose_name=_("Endereço"))
    status_obra = models.CharField(max_length=50, choices=STATUS_OBRA_CHOICES, default="planejamento", verbose_name=_("Status da Obra"))
    
    responsaveis_tecnicos = models.ManyToManyField(
        'rh.Funcionario',
        related_name="obras_responsaveis",
        blank=True,
        verbose_name=_("Responsáveis Técnicos")
    )
    equipe = models.ManyToManyField(
        'rh.Funcionario',
        related_name="obras_equipe",
        blank=True,
        verbose_name=_("Equipe da Obra")
    )

    data_inicio_prevista = models.DateField(null=True, blank=True, verbose_name=_("Data de Início Prevista"))
    data_fim_prevista = models.DateField(null=True, blank=True, verbose_name=_("Data de Fim Prevista"))
    data_inicio_real = models.DateField(null=True, blank=True, verbose_name=_("Data de Início Real"))
    data_fim_real = models.DateField(null=True, blank=True, verbose_name=_("Data de Fim Real"))
    orcamento_previsto = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name=_("Orçamento Previsto"))
    descricao = models.TextField(null=True, blank=True, verbose_name=_("Descrição"))
    data_cadastro = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Cadastro"))
    data_atualizacao = models.DateTimeField(auto_now=True, verbose_name=_("Data de Atualização"))

    class Meta:
        verbose_name = _("Obra")
        verbose_name_plural = _("Obras")
        ordering = ['nome_obra']
        # Unicidade por-tenant (Fase 8.3): o nome da obra sem empreendimento era
        # global (bloqueava o mesmo nome em tenants distintos); agora inclui o
        # tenant. A variante com empreendimento já era escopada pela FK-pai, mas
        # incluímos o tenant por consistência/defesa.
        constraints = [
            UniqueConstraint(fields=['tenant', 'empreendimento', 'nome_obra'], condition=Q(empreendimento__isnull=False) & Q(excluido_em__isnull=True), name='unique_obra_empreendimento'),
            UniqueConstraint(fields=['tenant', 'nome_obra'], condition=Q(empreendimento__isnull=True) & Q(excluido_em__isnull=True), name='unique_obra_sem_empreendimento'),
        ]

    def __str__(self):
        return self.nome_obra

class EtapaObra(TenantScopedModel, Excluivel):
    STATUS_ETAPA_CHOICES = [
        ("planejamento", _("Planejamento")),
        ("em_execucao", _("Em Execução")),
        ("concluida", _("Concluída")),
        ("cancelada", _("Cancelada")),
    ]

    etapa_id = models.AutoField(primary_key=True)
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name="etapas", verbose_name=_("Obra"))
    nome_etapa = models.CharField(max_length=255, verbose_name=_("Nome da Etapa"))
    ordem = models.PositiveIntegerField(verbose_name=_("Ordem de Execução"))
    percentual_conclusao = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name=_("Percentual de Conclusão"))
    responsavel = models.ForeignKey('rh.Funcionario', on_delete=models.SET_NULL, null=True, blank=True, related_name="etapas_responsaveis", verbose_name=_("Responsável pela Etapa"))
    data_inicio_prevista = models.DateField(null=True, blank=True, verbose_name=_("Data de Início Prevista"))
    data_fim_prevista = models.DateField(null=True, blank=True, verbose_name=_("Data de Fim Prevista"))
    data_inicio_real = models.DateField(null=True, blank=True, verbose_name=_("Data de Início Real"))
    data_fim_real = models.DateField(null=True, blank=True, verbose_name=_("Data de Fim Real"))
    status_etapa = models.CharField(max_length=50, choices=STATUS_ETAPA_CHOICES, default="planejamento", verbose_name=_("Status da Etapa"))
    descricao = models.TextField(null=True, blank=True, verbose_name=_("Descrição"))
    orcamento_previsto = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name=_("Orçamento Previsto"))
    data_cadastro = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Cadastro"))
    data_atualizacao = models.DateTimeField(auto_now=True, verbose_name=_("Data de Atualização"))

    class Meta:
        verbose_name = _("Etapa da Obra")
        verbose_name_plural = _("Etapas das Obras")
        ordering = ['obra', 'ordem']
        unique_together = ('obra', 'nome_etapa')

    def __str__(self):
        return f"{self.obra.nome_obra} - {self.nome_etapa}"

class DocumentoObra(TenantScopedModel, Excluivel):
    TIPO_DOCUMENTO_CHOICES = [
        ("projeto", _("Projeto")),
        ("relatorio", _("Relatório")),
        ("memorial_descritivo", _("Memorial Descritivo")),
        ("alvara", _("Alvará")),
        ("contrato", _("Contrato")),
        ("licenca", _("Licença")),
        ("viabilidade", _("Viabilidade")),
        ("outros", _("Outros")),
    ]
    
    STATUS_DOCUMENTO_CHOICES = [
        ("rascunho", _("Rascunho")),
        ("em_revisao", _("Em Revisão")),
        ("aprovacao", _("Aprovação")),
        ("correcoes", _("Correções")),
        ("aprovado", _("Aprovado")),
        ("rejeitado", _("Rejeitado")),
        ("publicado", _("Publicado")),
        ("cancelado", _("Cancelado")),
    ]

    documento_id = models.AutoField(primary_key=True)
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name="documentos", verbose_name=_("Obra"))
    nome_documento = models.CharField(max_length=255, verbose_name=_("Nome do Documento"))
    tipo_documento = models.CharField(max_length=50, choices=TIPO_DOCUMENTO_CHOICES, verbose_name=_("Tipo de Documento"))
    versao = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Versão"))
    descricao = models.TextField(null=True, blank=True, verbose_name=_("Descrição"))
    data_emissao = models.DateField(null=True, blank=True, verbose_name=_("Data de Emissão"))
    responsavel = models.ForeignKey('rh.Funcionario', on_delete=models.SET_NULL, null=True, blank=True, related_name="documentos_responsaveis", verbose_name=_("Responsável"))
    arquivo = models.FileField(upload_to="documentos_obras/")
    status_documento = models.CharField(max_length=50, choices=STATUS_DOCUMENTO_CHOICES, default="rascunho", verbose_name=_("Status do Documento"))
    data_aprovacao = models.DateField(null=True, blank=True, verbose_name=_("Data de Aprovação"))
    aprovador = models.ForeignKey('nucleo.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name="documentos_aprovados", verbose_name=_("Aprovador"))
    observacoes = models.TextField(null=True, blank=True, verbose_name=_("Observações"))
    data_cadastro = models.DateTimeField(auto_now_add=True, verbose_name=_("Data de Cadastro"))
    data_atualizacao = models.DateTimeField(auto_now=True, verbose_name=_("Data de Atualização"))

    class Meta:
        verbose_name = _("Documento da Obra")
        verbose_name_plural = _("Documentos das Obras")
        ordering = ['-data_cadastro']
        unique_together = ('obra', 'nome_documento', 'versao')

    def __str__(self):
        return f"{self.nome_documento} (v{self.versao})"
