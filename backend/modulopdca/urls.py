# backend/modulopdca/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AditivoContratoViewSet,
    AntecedenciaDeCompraViewSet,
    ApontamentoAvancoViewSet,
    AtividadeViewSet,
    BuscaView,
    CarteiraView,
    ControleDeCustoView,
    ControleDeMateriaisView,
    HojeView,
    MinhasFrentesView,
    CalendarioTrabalhoViewSet,
    CausaNaoCumprimentoViewSet,
    EquipeObraViewSet,
    MaterialDaAtividadeViewSet,
    ContratoObraViewSet,
    CronogramaViewSet,
    ExcecaoCalendarioViewSet,
    ItemContratoViewSet,
    ParcelaReajusteContratoViewSet,
    ItemModeloVerificacaoViewSet,
    ItemProgramacaoViewSet,
    ItemVerificacaoViewSet,
    LiberacaoRetencaoViewSet,
    LocalObraViewSet,
    MedicaoViewSet,
    ModeloVerificacaoViewSet,
    NaoConformidadeViewSet,
    PdcaStatusView,
    PlanoAcaoViewSet,
    PostoDaMedicaoView,
    PostoDaQualidadeView,
    PostoDaSegurancaView,
    PrecedenciaViewSet,
    ProgramacaoSemanalViewSet,
    RestricaoViewSet,
    VerificacaoViewSet,
    AnexoOcorrenciaViewSet,
    DialogoSegurancaViewSet,
    OcorrenciaViewSet,
)

router = DefaultRouter()
router.register(r"locais", LocalObraViewSet, basename="pdca-local")
router.register(r"calendarios", CalendarioTrabalhoViewSet, basename="pdca-calendario")
router.register(r"excecoes-calendario", ExcecaoCalendarioViewSet, basename="pdca-excecao")
router.register(r"cronogramas", CronogramaViewSet, basename="pdca-cronograma")
router.register(r"antecedencias", AntecedenciaDeCompraViewSet, basename="pdca-antecedencia")
router.register(r"atividades", AtividadeViewSet, basename="pdca-atividade")
router.register(r"precedencias", PrecedenciaViewSet, basename="pdca-precedencia")
router.register(r"apontamentos", ApontamentoAvancoViewSet, basename="pdca-apontamento")
# PDCA.3 — o dinheiro
router.register(r"contratos", ContratoObraViewSet, basename="pdca-contrato")
router.register(r"itens-contrato", ItemContratoViewSet, basename="pdca-item-contrato")
router.register(r"parcelas-reajuste", ParcelaReajusteContratoViewSet, basename="pdca-parcela-reajuste")
router.register(r"medicoes", MedicaoViewSet, basename="pdca-medicao")
router.register(r"liberacoes", LiberacaoRetencaoViewSet, basename="pdca-liberacao")
# PDCA.4 — o contrato mudando por escrito
router.register(r"aditivos", AditivoContratoViewSet, basename="pdca-aditivo")
# PDCA.5 — o Last Planner: o que trava, o que se assume e por que não saiu
router.register(r"restricoes", RestricaoViewSet, basename="pdca-restricao")
router.register(r"causas", CausaNaoCumprimentoViewSet, basename="pdca-causa")
router.register(r"equipes", EquipeObraViewSet, basename="pdca-equipe")
router.register(r"materiais-atividade", MaterialDaAtividadeViewSet, basename="pdca-material-atividade")
router.register(
    r"programacoes", ProgramacaoSemanalViewSet, basename="pdca-programacao",
)
router.register(
    r"itens-programacao", ItemProgramacaoViewSet, basename="pdca-item-programacao",
)
# PDCA.7 — a máquina de verificação: a ficha, o defeito e o laço que o fecha
router.register(
    r"modelos-verificacao", ModeloVerificacaoViewSet, basename="pdca-modelo-verificacao",
)
router.register(
    r"itens-modelo-verificacao", ItemModeloVerificacaoViewSet,
    basename="pdca-item-modelo-verificacao",
)
router.register(r"verificacoes", VerificacaoViewSet, basename="pdca-verificacao")
router.register(
    r"itens-verificacao", ItemVerificacaoViewSet, basename="pdca-item-verificacao",
)
router.register(r"ncs", NaoConformidadeViewSet, basename="pdca-nc")
router.register(r"planos-acao", PlanoAcaoViewSet, basename="pdca-plano-acao")
# PDCA.8 — SSMA: a roda antes do turno e o fato que ninguém queria
router.register(r"dds", DialogoSegurancaViewSet, basename="pdca-dds")
router.register(r"ocorrencias", OcorrenciaViewSet, basename="pdca-ocorrencia")
router.register(
    r"anexos-ocorrencia", AnexoOcorrenciaViewSet, basename="pdca-anexo-ocorrencia",
)

urlpatterns = [
    path("status/", PdcaStatusView.as_view(), name="pdca-status"),
    # O cockpit — as leituras que ATRAVESSAM, e que por isso não são recurso
    # de router nenhum: a carteira cruza obras, `hoje/` junta cinco assuntos de
    # uma obra, `busca/` varre sete tabelas e `minhas-frentes/` junta quatro
    # assuntos de uma pessoa, em qualquer obra. Registrá-las como ação de um
    # viewset as penduraria num dono que elas não têm.
    path("carteira/", CarteiraView.as_view(), name="pdca-carteira"),
    path("hoje/", HojeView.as_view(), name="pdca-hoje"),
    path("controle/custo/", ControleDeCustoView.as_view(), name="pdca-controle-custo"),
    path("controle/materiais/", ControleDeMateriaisView.as_view(), name="pdca-controle-materiais"),
    path("busca/", BuscaView.as_view(), name="pdca-busca"),
    # A quarta, e ela atravessa **assunto** em vez de obra: o posto da medição
    # junta contrato e medição, que têm permissões diferentes. Mora aqui, e não
    # como ação de `medicoes/`, porque não é recurso da medição — a carteira de
    # contratos não é medição nenhuma, e pendurá-la ali obrigaria o portão a
    # exigir `pdca.medicao.view` de quem só lê contrato.
    path("medicao/", PostoDaMedicaoView.as_view(), name="pdca-posto-medicao"),
    path(
        "qualidade/", PostoDaQualidadeView.as_view(), name="pdca-posto-qualidade",
    ),
    path(
        "seguranca/", PostoDaSegurancaView.as_view(), name="pdca-posto-seguranca",
    ),
    # E a quinta, que é a porta da superfície de campo: o que está atribuído a
    # quem pede. Atravessa obras, então mora aqui pelo mesmo motivo que a
    # carteira — não é recurso de router nenhum.
    path(
        "minhas-frentes/", MinhasFrentesView.as_view(), name="pdca-minhas-frentes",
    ),
    path("", include(router.urls)),
]
