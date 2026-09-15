# backend/modulopdca/admin.py
"""Admin do PDCA — leitura de apoio à operação, não porta de edição.

O `/admin` é do supervisor da plataforma, e ele **não altera dado de empresa**
(docs/acesso-e-permissoes.md). Por isso o que se registra aqui é o mínimo que
ajuda a diagnosticar: ver a árvore de uma obra e o calendário que ela usa quando
alguém reclama que "o prazo saiu errado".
"""
from django.contrib import admin

from .models import (
    AditivoContrato, ApontamentoAvanco, CalendarioTrabalho, ContratoObra,
    ExcecaoCalendario, LocalObra, Medicao,
)


@admin.register(LocalObra)
class LocalObraAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "nivel", "obra", "profundidade", "ativo")
    list_filter = ("nivel", "ativo")
    search_fields = ("codigo", "nome")
    raw_id_fields = ("obra", "pai", "maps_local", "unidade", "tenant")


class ExcecaoInline(admin.TabularInline):
    model = ExcecaoCalendario
    extra = 0
    raw_id_fields = ("tenant",)


@admin.register(CalendarioTrabalho)
class CalendarioTrabalhoAdmin(admin.ModelAdmin):
    list_display = ("nome", "obra", "padrao", "horas_por_dia", "considera_feriados", "ativo")
    list_filter = ("padrao", "considera_feriados", "ativo")
    search_fields = ("nome",)
    raw_id_fields = ("obra", "tenant")
    inlines = [ExcecaoInline]


@admin.register(ApontamentoAvanco)
class ApontamentoAvancoAdmin(admin.ModelAdmin):
    """**Somente leitura, e aqui isso é regra de negócio, não cautela de admin.**

    O apontamento é append-only: o model recusa o segundo `save()`, e um
    formulário de edição no `/admin` só produziria um erro feio na cara do
    supervisor. Diagnosticar "o avanço da obra está errado" é ler a lista e ver
    qual lançamento não bate — corrigir é do dono do dado, pelo estorno.
    """

    list_display = ("data", "atividade", "percentual", "origem", "apontado_por", "estorna")
    list_filter = ("origem", "data")
    search_fields = ("observacao", "apontado_por")
    raw_id_fields = ("atividade", "local", "estorna", "tenant")
    date_hierarchy = "data"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class _SomenteLeitura(admin.ModelAdmin):
    """Base dos documentos da PDCA.3 no `/admin`.

    **Somente leitura pela mesma regra do apontamento, e com um motivo a mais.**
    O contrato e a medição são documentos com efeito financeiro: a medição
    aprovada gerou um `ContaPagar` no ERP, e um `save()` no formulário do admin
    mudaria o valor do documento **sem** tocar no título — deixando dois números
    divergentes, um deles já conciliado pelo contador.

    Diagnosticar continua possível, que é para o que o `/admin` serve aqui:
    ver o contrato, o saldo e a que título cada medição deu origem.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContratoObra)
class ContratoObraAdmin(_SomenteLeitura):
    list_display = (
        "numero", "obra", "fornecedor", "regime", "status", "regime_publico",
        "retencao_percentual", "data_inicio",
    )
    list_filter = ("regime", "status", "regime_publico", "retencao_natureza")
    search_fields = ("numero", "objeto")
    raw_id_fields = ("obra", "fornecedor", "tenant")


@admin.register(Medicao)
class MedicaoAdmin(_SomenteLeitura):
    list_display = (
        "numero", "contrato", "periodo_inicio", "periodo_fim", "status",
        "conta_pagar_ref", "congelada_em",
    )
    list_filter = ("status", "custo_origem")
    search_fields = ("apurada_por", "observacao")
    raw_id_fields = ("contrato", "retifica", "tenant")
    date_hierarchy = "periodo_fim"


@admin.register(AditivoContrato)
class AditivoContratoAdmin(_SomenteLeitura):
    """Somente leitura pelo mesmo motivo dos irmãos, e com um agravante: o
    aditivo **aplicado** já reescreveu preço e criou item na planilha
    contratual. Editá-lo aqui mudaria o documento sem desfazer o efeito."""

    list_display = (
        "numero", "contrato", "status", "data_assinatura", "nova_data_fim",
        "aplicado_em",
    )
    list_filter = ("status",)
    search_fields = ("objeto", "justificativa", "criado_por")
    raw_id_fields = ("contrato", "tenant")
