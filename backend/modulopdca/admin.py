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
    CausaNaoCumprimento, ExcecaoCalendario, ItemProgramacao, LocalObra,
    Medicao, ProgramacaoSemanal, Restricao,
    ItemModeloVerificacao, ItemVerificacao, ModeloVerificacao,
    NaoConformidade, PlanoAcao, Verificacao, VerificacaoEficacia,
    AnexoOcorrencia, DialogoSeguranca, Ocorrencia, ParticipanteDDS,
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


# --- PDCA.5 — Last Planner ---------------------------------------------------


@admin.register(Restricao)
class RestricaoAdmin(admin.ModelAdmin):
    """Editável, ao contrário dos documentos da PDCA.3.

    A restrição não tem efeito financeiro e não atravessa escada de aprovação —
    é insumo de planejamento. O que o `/admin` **não** deve fazer aqui é
    remover: `remover_restricao` grava quem e como, e um `status='removida'`
    digitado no formulário deixaria a nota vazia, que é exatamente o buraco que
    a obrigatoriedade daquela nota existe para fechar.
    """

    list_display = (
        "restricao_id", "tipo", "atividade", "local", "responsavel", "prazo",
        "status", "demanda_scm",
    )
    list_filter = ("tipo", "status")
    search_fields = ("descricao", "responsavel", "criada_por")
    raw_id_fields = ("atividade", "local", "demanda_scm", "tenant")
    date_hierarchy = "prazo"


@admin.register(CausaNaoCumprimento)
class CausaNaoCumprimentoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "categoria", "de_fabrica", "ativo")
    list_filter = ("categoria", "de_fabrica", "ativo")
    search_fields = ("codigo", "nome")
    raw_id_fields = ("tenant",)


class ItemProgramacaoInline(admin.TabularInline):
    """Somente leitura **também aqui**, e não só no pai.

    O `_SomenteLeitura` do pai fecha a página de mudança dele; o inline carrega
    permissões próprias, e sem estas três o `cumprido` de cada compromisso
    continuaria editável — que é exatamente o campo cuja edição silenciosa a
    docstring do pai proíbe.
    """

    model = ItemProgramacao
    extra = 0
    raw_id_fields = ("atividade", "local", "causa", "tenant")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProgramacaoSemanal)
class ProgramacaoSemanalAdmin(_SomenteLeitura):
    """Somente leitura, e o motivo é o mesmo do apontamento — não o do dinheiro.

    O compromisso é o denominador de um índice já publicado. Mudar `cumprido`
    no formulário do admin reescreveria um PPC que alguém levou para uma
    reunião, e sem deixar rastro de que foi reescrito.
    """

    list_display = (
        "programacao_id", "obra", "semana_inicio", "semana_fim", "status",
        "comprometida_em", "encerrada_em",
    )
    list_filter = ("status",)
    search_fields = ("criada_por", "comprometida_por", "encerrada_por", "nota")
    raw_id_fields = ("obra", "tenant")
    date_hierarchy = "semana_inicio"
    inlines = [ItemProgramacaoInline]


# ---------------------------------------------------------------------------
# PDCA.7 — a máquina de verificação
# ---------------------------------------------------------------------------


class ItemModeloVerificacaoInline(admin.TabularInline):
    model = ItemModeloVerificacao
    extra = 0
    raw_id_fields = ("tenant",)


@admin.register(ModeloVerificacao)
class ModeloVerificacaoAdmin(admin.ModelAdmin):
    """O **único** desta fatia que não é somente leitura, e a razão é o que ele
    é: a ficha em branco, antes de qualquer inspeção. Corrigir o texto de uma
    pergunta aqui muda o que as próximas fichas perguntam e **não toca** em
    nenhuma resposta já dada — porque a resposta guarda a pergunta congelada
    dentro dela (ver `ItemVerificacao`). É justamente esse congelamento que
    torna seguro editar o modelo pelo admin."""

    list_display = ("codigo", "nome", "dominio", "ativo", "criado_em")
    list_filter = ("dominio", "ativo")
    search_fields = ("codigo", "nome", "descricao")
    raw_id_fields = ("tenant",)
    inlines = [ItemModeloVerificacaoInline]


class ItemVerificacaoInline(admin.TabularInline):
    """Somente leitura **também aqui** — a lição do `ItemProgramacaoInline`.

    O inline carrega permissões próprias; sem estas três, o `resultado` de cada
    item continuaria editável no formulário do pai, que é exatamente o campo
    cuja edição silenciosa a ficha existe para impedir.
    """

    model = ItemVerificacao
    extra = 0
    raw_id_fields = ("item_modelo", "tenant")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Verificacao)
class VerificacaoAdmin(_SomenteLeitura):
    """Somente leitura — **é prova de auditoria**.

    A ficha respondida é o documento que o organismo certificador do PBQP-H vem
    conferir. Um `save()` no formulário do admin mudaria o que um inspetor
    respondeu num dia em que ele estava no canteiro, sem deixar rastro de que
    foi reescrito — e a ficha continuaria parecendo legítima.
    """

    list_display = (
        "verificacao_id", "modelo", "obra", "data", "status", "inspetor",
        "concluida_em",
    )
    list_filter = ("status", "modelo__dominio")
    search_fields = ("inspetor", "criada_por", "concluida_por", "nota")
    raw_id_fields = ("modelo", "obra", "local", "atividade", "tenant")
    date_hierarchy = "data"
    inlines = [ItemVerificacaoInline]


class PlanoAcaoInline(admin.TabularInline):
    model = PlanoAcao
    extra = 0
    raw_id_fields = ("tenant",)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class VerificacaoEficaciaInline(admin.TabularInline):
    model = VerificacaoEficacia
    extra = 0
    raw_id_fields = ("tenant",)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NaoConformidade)
class NaoConformidadeAdmin(_SomenteLeitura):
    """Somente leitura, e aqui o motivo é o mais forte da fatia.

    Mudar `status` para `encerrada` no admin pularia a única regra que dá
    sentido a este modelo — a NC não encerra sem eficácia verificada (§4.5). O
    formulário do admin não passa pelo `services.encerrar_nc`, então um clique
    aqui arquivaria um defeito que ninguém voltou a conferir, e a estatística de
    qualidade da obra passaria a mentir para cima.
    """

    list_display = (
        "nc_id", "obra", "gravidade", "status", "atividade", "aberta_em",
        "encerrada_em",
    )
    list_filter = ("status", "gravidade")
    search_fields = ("descricao", "aberta_por", "encerrada_por")
    raw_id_fields = (
        "obra", "local", "atividade", "item_verificacao", "marcacao_prancheta",
        "restricao", "tenant",
    )
    date_hierarchy = "aberta_em"
    inlines = [PlanoAcaoInline, VerificacaoEficaciaInline]


# --- PDCA.8 — SSMA ---------------------------------------------------------


class ParticipanteDDSInline(admin.TabularInline):
    model = ParticipanteDDS
    extra = 0
    raw_id_fields = ("funcionario", "tenant")


@admin.register(DialogoSeguranca)
class DialogoSegurancaAdmin(_SomenteLeitura):
    """Somente leitura — **a lista de presença é o que se falsifica**.

    Encerrar pelo admin pularia a única regra que faz o registro provar algo (o
    DDS não encerra sem presente) e, pior, deixaria a lista reabrível por
    caminho que o `services` fecha. É esse registro que prova que a obra fazia
    prevenção **antes** do acidente, e é por isso que ele vale numa ação
    regressiva do INSS.
    """

    list_display = ("dds_id", "obra", "data", "tema", "status", "encerrado_em")
    list_filter = ("status",)
    search_fields = ("tema", "assunto", "responsavel_nome")
    raw_id_fields = (
        "obra", "local", "atividade", "responsavel", "diario", "tenant",
    )
    date_hierarchy = "data"
    inlines = [ParticipanteDDSInline]


class AnexoOcorrenciaInline(admin.TabularInline):
    model = AnexoOcorrencia
    extra = 0
    raw_id_fields = ("tenant",)


@admin.register(Ocorrencia)
class OcorrenciaAdmin(_SomenteLeitura):
    """Somente leitura, e aqui o motivo é o mais forte do módulo inteiro.

    A ocorrência guarda dado de saúde (LGPD art. 11) e é peça de prova num ato
    com prazo legal. O admin **não** passa pelo `services`, então um clique aqui
    classificaria um acidente sem a segregação que a fatia existe para impor,
    encerraria por cima de uma frente ainda interditada, ou registraria um
    protocolo de CAT que ninguém protocolou.

    E o bloco clínico **não entra em `list_display` nem em `search_fields`**: o
    mascaramento por permissão mora no serializer, e o admin de plataforma não o
    atravessa — listar CID aqui seria contornar a própria máscara.
    """

    list_display = (
        "ocorrencia_id", "obra", "tipo", "classificacao", "status",
        "ocorrido_em", "cat_emitida_em",
    )
    list_filter = ("tipo", "classificacao", "status")
    search_fields = ("descricao", "agente_causador", "registrada_por")
    raw_id_fields = (
        "obra", "local", "atividade", "acidentado", "restricao",
        "nao_conformidade", "tenant",
    )
    date_hierarchy = "ocorrido_em"
    inlines = [AnexoOcorrenciaInline]
