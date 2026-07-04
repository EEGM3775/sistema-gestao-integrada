# backend/modulodiario/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from obras.models import Obra
from nucleo.models import Usuario
from nucleo.tenancy import TenantScopedModel

ORIGEM_CHOICES = [
    ('web', 'Web'),
    ('whatsapp', 'WhatsApp'),
]


class DiarioObra(TenantScopedModel):
    """
    Container do dia: existe **um** diário por obra por data. Todas as
    contribuições (texto e mídia) daquele dia ficam agregadas aqui.
    A unicidade (obra, data) é garantida via get-or-create na aplicação;
    a UniqueConstraint formal por tenant entra na Fase 8.
    """
    diario_obra_id = models.AutoField(primary_key=True)
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name='diarios_obra', verbose_name=_("Obra"))
    data = models.DateField(_("Data"))
    # Resumo opcional do dia (as contribuições ficam em EntradaDiario).
    descricao = models.TextField(_("Resumo do Dia"), blank=True, null=True)
    # Clima é do dia inteiro (um valor, editável por quem contribui).
    condicoes_climaticas = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Condições Climáticas"))
    # Quem abriu o diário do dia (espelho JIT do usuário da IAM).
    criado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Criado por"))
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Diário de Obra")
        verbose_name_plural = _("Diários de Obra")
        ordering = ['-data']

    def __str__(self):
        return f"Diário {self.obra.nome_obra} — {self.data.strftime('%d/%m/%Y')}"


class EntradaDiario(TenantScopedModel):
    """
    Uma contribuição de texto ao diário do dia, com autoria. Append-only para
    a equipe; responsáveis técnicos podem editar/excluir qualquer entrada.
    """
    entrada_id = models.AutoField(primary_key=True)
    diario_obra = models.ForeignKey(DiarioObra, on_delete=models.CASCADE, related_name='entradas', verbose_name=_("Diário de Obra"))
    autor = models.ForeignKey('rh.Funcionario', on_delete=models.SET_NULL, null=True, blank=True, related_name='entradas_diario', verbose_name=_("Autor"))
    origem = models.CharField(max_length=20, choices=ORIGEM_CHOICES, default='web', verbose_name=_("Origem"))
    texto = models.TextField(_("Conteúdo"))
    eh_ocorrencia = models.BooleanField(_("É problema/ocorrência"), default=False)
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Entrada do Diário")
        verbose_name_plural = _("Entradas do Diário")
        ordering = ['data_criacao']

    def __str__(self):
        return f"Entrada {self.entrada_id} — {self.diario_obra}"


class DocumentoDiario(TenantScopedModel):
    """
    Arquivo de mídia (foto/vídeo) anexado ao diário do dia. Ao ser criado,
    dispara a análise de IA. Guarda autoria e origem (web/whatsapp).
    """
    documento_diario_id = models.AutoField(primary_key=True)
    diario_obra = models.ForeignKey(DiarioObra, on_delete=models.CASCADE, related_name='documentos', verbose_name=_("Diário de Obra"))
    autor = models.ForeignKey('rh.Funcionario', on_delete=models.SET_NULL, null=True, blank=True, related_name='documentos_diario', verbose_name=_("Autor"))
    origem = models.CharField(max_length=20, choices=ORIGEM_CHOICES, default='web', verbose_name=_("Origem"))
    arquivo = models.FileField(upload_to='diario_obra_media/', verbose_name=_("Arquivo"))
    descricao = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Descrição do Arquivo"))
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Documento do Diário")
        verbose_name_plural = _("Documentos do Diário")
        ordering = ['data_criacao']

    def __str__(self):
        return f"Documento para {self.diario_obra}"
