# backend/modulodiario/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from obras.models import Obra
from nucleo.models import Usuario

class DiarioObra(models.Model):
    """
    Registra as atividades diárias de uma obra.
    """
    diario_obra_id = models.AutoField(primary_key=True)
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name='diarios_obra', verbose_name=_("Obra"))
    data = models.DateField(_("Data"))
    descricao = models.TextField(_("Descrição das Atividades"))
    condicoes_climaticas = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Condições Climáticas"))
    problemas_ocorrencias = models.TextField(_("Problemas ou Ocorrências"), blank=True, null=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Usuário que Registrou"))
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Diário de Obra")
        verbose_name_plural = _("Diários de Obra")
        ordering = ['-data']

    def __str__(self):
        return f"Diário da Obra {self.obra.nome} - {self.data.strftime('%d/%m/%Y')}"

class DocumentoDiario(models.Model):
    """
    Armazena arquivos de mídia (fotos, vídeos, etc.) associados a um registro
    do diário de obra.
    """
    documento_diario_id = models.AutoField(primary_key=True)
    diario_obra = models.ForeignKey(DiarioObra, on_delete=models.CASCADE, related_name='documentos', verbose_name=_("Diário de Obra"))
    arquivo = models.FileField(upload_to='diario_obra_media/', verbose_name=_("Arquivo"))
    descricao = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Descrição do Arquivo"))
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Documento do Diário")
        verbose_name_plural = _("Documentos do Diário")

    def __str__(self):
        return f"Documento para {self.diario_obra}"
