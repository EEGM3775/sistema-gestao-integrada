# backend/entidades/models.py
"""Quem é o dono jurídico de cada coisa — docs/modulos/entidades.md.

O tenant é a conta que assina a plataforma; a `Entidade` é quem tem CPF ou CNPJ,
emite nota, recebe boleto e tem DRE. Um tenant tem uma ou muitas: do construtor
que trabalha no próprio CPF ao grupo com matriz, filiais e uma SPE por loteamento.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from nucleo.tenancy import TenantScopedModel


class Entidade(TenantScopedModel):
    class TipoPessoa(models.TextChoices):
        PJ = "PJ", _("Pessoa jurídica")
        PF = "PF", _("Pessoa física")

    class Papel(models.TextChoices):
        MATRIZ = "matriz", _("Matriz")
        FILIAL = "filial", _("Filial")
        SPE = "spe", _("SPE — Sociedade de Propósito Específico")
        SCP = "scp", _("SCP — Sociedade em Conta de Participação")
        PATRIMONIO_AFETACAO = "patrimonio_afetacao", _("Patrimônio de afetação (RET)")
        CONSORCIO = "consorcio", _("Consórcio")
        PESSOA_FISICA = "pessoa_fisica", _("Pessoa física")
        OUTRA = "outra", _("Outra")

    entidade_id = models.AutoField(primary_key=True)
    tipo_pessoa = models.CharField(max_length=2, choices=TipoPessoa.choices, default=TipoPessoa.PJ, verbose_name=_("Tipo de pessoa"))
    # Só dígitos. Opcional até a emissão: a matriz nasce sem ele na migração e a
    # tela pede o CNPJ antes da primeira nota ou boleto.
    documento = models.CharField(max_length=14, blank=True, default="", verbose_name=_("CPF/CNPJ"))
    nome = models.CharField(max_length=255, verbose_name=_("Razão social ou nome civil"))
    nome_fantasia = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Nome fantasia"))
    papel = models.CharField(max_length=20, choices=Papel.choices, default=Papel.MATRIZ, verbose_name=_("Papel"))
    # Fora do grupo: o dono do empreendimento em que o tenant só executa, ou o
    # sócio externo de uma SPE. Não tem título, caixa nem DRE aqui.
    externa = models.BooleanField(default=False, verbose_name=_("Externa (fora do grupo)"))
    matriz = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="filiais",
        verbose_name=_("Matriz (da filial)"),
    )
    # A entidade externa costuma ser cliente do tenant (o contratante da obra).
    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name=_("Cliente correspondente"),
    )
    inscricao_estadual = models.CharField(max_length=20, blank=True, default="", verbose_name=_("Inscrição estadual"))
    inscricao_municipal = models.CharField(max_length=20, blank=True, default="", verbose_name=_("Inscrição municipal"))
    endereco = models.TextField(blank=True, default="", verbose_name=_("Endereço"))
    cidade = models.CharField(max_length=100, blank=True, default="", verbose_name=_("Cidade"))
    estado = models.CharField(max_length=2, blank=True, default="", verbose_name=_("UF"))
    ativa = models.BooleanField(default=True, verbose_name=_("Ativa"))
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Entidade")
        verbose_name_plural = _("Entidades")
        ordering = ["externa", "nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "documento"], condition=~models.Q(documento=""),
                name="entidade_documento_unico_por_tenant",
            ),
        ]

    def __str__(self):
        return self.nome_fantasia or self.nome

    @property
    def do_grupo(self) -> bool:
        return not self.externa


class ParticipacaoEmpreendimento(TenantScopedModel):
    """Quem é dono do empreendimento e em que cota (SPE 60/40, SCP, consórcio).

    Com `entidade_propria` no empreendimento, as participações são as sócias
    dela; sem, são as co-donas diretas — e o título de uma gera, para as outras,
    o intercompany da cota (docs/modulos/entidades.md §3).
    """
    participacao_id = models.AutoField(primary_key=True)
    empreendimento = models.ForeignKey(
        "empreendimentos.Empreendimento", on_delete=models.CASCADE, related_name="participacoes",
        verbose_name=_("Empreendimento"),
    )
    entidade = models.ForeignKey(Entidade, on_delete=models.PROTECT, related_name="participacoes", verbose_name=_("Entidade"))
    cota = models.DecimalField(
        max_digits=7, decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001")), MaxValueValidator(Decimal("100"))],
        verbose_name=_("Cota (%)"),
    )
    # A líder do consórcio, a ostensiva da SCP, a sócia que administra a SPE:
    # quem tem acesso a ela vê a `entidade_propria` inteira no ERP.
    administradora = models.BooleanField(default=False, verbose_name=_("Administradora"))

    class Meta:
        verbose_name = _("Participação no empreendimento")
        verbose_name_plural = _("Participações nos empreendimentos")
        ordering = ["empreendimento", "-cota"]
        constraints = [
            models.UniqueConstraint(fields=["empreendimento", "entidade"], name="participacao_unica_por_entidade"),
            models.UniqueConstraint(
                fields=["empreendimento"], condition=models.Q(administradora=True),
                name="uma_administradora_por_empreendimento",
            ),
        ]

    def __str__(self):
        return f"{self.entidade} — {self.cota}% de {self.empreendimento}"


class ConcessaoEntidade(TenantScopedModel):
    """Usuário ↔ entidade: o ERP inteiro dela (docs/modulos/entidades.md §4)."""
    concessao_id = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="concessoes_entidade")
    entidade = models.ForeignKey(Entidade, on_delete=models.CASCADE, related_name="concessoes")
    incluir_filiais = models.BooleanField(default=False, verbose_name=_("Incluir filiais"))
    concedido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    concedido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Acesso à entidade")
        verbose_name_plural = _("Acessos às entidades")
        constraints = [
            models.UniqueConstraint(fields=["usuario", "entidade"], name="concessao_entidade_unica"),
        ]


class ConcessaoEmpreendimento(TenantScopedModel):
    """Usuário ↔ empreendimento: o empreendimento, as obras dele e, no ERP, o
    recorte dele. Fora do ERP é por aqui que se cadastra quem trabalha onde."""
    concessao_id = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="concessoes_empreendimento")
    empreendimento = models.ForeignKey(
        "empreendimentos.Empreendimento", on_delete=models.CASCADE, related_name="concessoes",
    )
    concedido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    concedido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Acesso ao empreendimento")
        verbose_name_plural = _("Acessos aos empreendimentos")
        constraints = [
            models.UniqueConstraint(fields=["usuario", "empreendimento"], name="concessao_empreendimento_unica"),
        ]
