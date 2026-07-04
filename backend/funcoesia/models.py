# backend/funcoesia/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from modulodiario.models import DocumentoDiario
from nucleo.tenancy import TenantScopedModel

class AnaliseImagemIA(TenantScopedModel):
    """
    Armazena o resultado estruturado da análise de uma imagem
    feita pelo microserviço de Inteligência Artificial.
    """
    analise_ia_id = models.AutoField(primary_key=True)
    documento = models.OneToOneField(
        DocumentoDiario,
        on_delete=models.CASCADE,
        related_name='analise_ia',
        verbose_name=_("Documento Analisado")
    )
    resultado_analise = models.JSONField(_("Resultado da Análise"), null=True, blank=True)

    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('em_processamento', 'Em Processamento'),
        ('concluido', 'Concluído'),
        ('erro', 'Erro'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pendente',
        verbose_name=_("Status")
    )

    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Análise de Imagem por IA")
        verbose_name_plural = _("Análises de Imagem por IA")

    def __str__(self):
        return f"Análise para o documento {self.documento.documento_diario_id}"
