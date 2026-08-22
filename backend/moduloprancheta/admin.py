from django.contrib import admin

from .models import (
    ComentarioMarcacao,
    DerivadaProjeto,
    DocumentoProjeto,
    Marcacao,
    Medicao,
    PontoDeVista,
    RevisaoDocumento,
)


@admin.register(DocumentoProjeto)
class DocumentoProjetoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "titulo", "obra", "disciplina", "ativo")
    list_filter = ("disciplina", "ativo")
    search_fields = ("codigo", "titulo", "projetista")


@admin.register(RevisaoDocumento)
class RevisaoDocumentoAdmin(admin.ModelAdmin):
    list_display = ("documento", "revisao", "formato", "situacao", "enviado_em")
    list_filter = ("situacao", "formato")
    search_fields = ("documento__codigo", "revisao", "nome_original", "caminho_origem")
    # Derivados do arquivo, nunca digitados — mesma razão do serializer.
    readonly_fields = (
        "nome_original", "caminho_origem", "formato", "tamanho_bytes", "hash_sha256",
    )


@admin.register(DerivadaProjeto)
class DerivadaProjetoAdmin(admin.ModelAdmin):
    list_display = ("revisao", "tipo", "motor", "motor_versao", "estado", "concluido_em")
    list_filter = ("tipo", "motor", "estado")


class ComentarioInline(admin.TabularInline):
    model = ComentarioMarcacao
    extra = 0
    readonly_fields = ("guid", "criado_em")


@admin.register(Marcacao)
class MarcacaoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "revisao", "tipo", "situacao", "prioridade", "responsavel", "prazo")
    list_filter = ("situacao", "tipo", "prioridade", "origem")
    search_fields = ("titulo", "descricao", "responsavel_email")
    # O GUID é a identidade da marcação FORA daqui: editá-lo à mão quebraria o
    # reencontro no próximo ciclo de BCF e duplicaria o tópico no escritório.
    readonly_fields = ("guid", "criado_em", "atualizado_em")
    inlines = [ComentarioInline]


@admin.register(PontoDeVista)
class PontoDeVistaAdmin(admin.ModelAdmin):
    list_display = ("guid", "marcacao", "criado_em")
    readonly_fields = ("guid",)


@admin.register(Medicao)
class MedicaoAdmin(admin.ModelAdmin):
    list_display = ("revisao", "tipo", "valor", "unidade", "escala_aplicada", "criado_em")
    list_filter = ("tipo",)
    # Calculados a partir dos vértices e da escala — digitá-los criaria uma
    # medida que não corresponde ao que está desenhado.
    readonly_fields = ("valor", "unidade", "escala_aplicada", "criado_em")
