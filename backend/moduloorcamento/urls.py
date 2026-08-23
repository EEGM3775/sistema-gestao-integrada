# backend/moduloorcamento/urls.py
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BancoPrecoViewSet,
    BaseReferencialResumoView,
    BaseReferencialViewSet,
    CargaBaseViewSet,
    ComponenteBancoPrecoViewSet,
    ComposicaoBDIViewSet,
    ComposicaoEncargosViewSet,
    ControleDeCustoView,
    FonteOficialViewSet,
    FormulaReajusteViewSet,
    IndiceEconomicoViewSet,
    InsumoReferenciaViewSet,
    ItemBancoPrecoViewSet,
    ItemOrcadoViewSet,
    LinhaMedicaoViewSet,
    MemorialNBRViewSet,
    OrcamentoStatusView,
    OrcamentoViewSet,
    ParametroObraViewSet,
    ParcelaEtapaViewSet,
    ParcelaFormulaReajusteViewSet,
    PastaComposicaoViewSet,
    PavimentoObraViewSet,
    QuadrosNBRView,
    ReprecificacaoViewSet,
    RevisaoOrcamentoViewSet,
    RubricaEncargosViewSet,
    UnidadeAutonomaViewSet,
)

router = DefaultRouter()
router.register(r"bases", BaseReferencialViewSet, basename="orcamento-base")
router.register(r"referencias", InsumoReferenciaViewSet, basename="orcamento-referencia")
router.register(r"orcamentos", OrcamentoViewSet, basename="orcamento-orcamento")
router.register(r"itens", ItemOrcadoViewSet, basename="orcamento-item")
router.register(r"revisoes", RevisaoOrcamentoViewSet, basename="orcamento-revisao")
router.register(r"bdi", ComposicaoBDIViewSet, basename="orcamento-bdi")
router.register(r"parcelas", ParcelaEtapaViewSet, basename="orcamento-parcela")
router.register(r"parametricos", ParametroObraViewSet, basename="orcamento-parametrico")
router.register(r"pavimentos", PavimentoObraViewSet, basename="orcamento-pavimento")
router.register(r"unidades", UnidadeAutonomaViewSet, basename="orcamento-unidade")
router.register(r"memoriais", MemorialNBRViewSet, basename="orcamento-memorial")
# ORC.5b — bancos da empresa, importação e reprecificação
router.register(r"bancos", BancoPrecoViewSet, basename="orcamento-banco")
router.register(r"pastas", PastaComposicaoViewSet, basename="orcamento-pasta")
router.register(r"itens-banco", ItemBancoPrecoViewSet, basename="orcamento-item-banco")
router.register(r"componentes-banco", ComponenteBancoPrecoViewSet, basename="orcamento-componente-banco")
router.register(r"reprecificacoes", ReprecificacaoViewSet, basename="orcamento-reprecificacao")
# ORC.7 — encargos analíticos, memória do quantitativo e reajuste contratual
router.register(r"encargos", ComposicaoEncargosViewSet, basename="orcamento-encargos")
router.register(r"rubricas-encargos", RubricaEncargosViewSet, basename="orcamento-rubrica-encargos")
router.register(r"medicoes", LinhaMedicaoViewSet, basename="orcamento-medicao")
router.register(r"indices", IndiceEconomicoViewSet, basename="orcamento-indice")
router.register(r"formulas-reajuste", FormulaReajusteViewSet, basename="orcamento-formula-reajuste")
router.register(
    r"parcelas-reajuste", ParcelaFormulaReajusteViewSet, basename="orcamento-parcela-reajuste",
)
# ORC.8 — a carga da base oficial: onde a fonte mora e o que já foi tentado
router.register(r"fontes-oficiais", FonteOficialViewSet, basename="orcamento-fonte-oficial")
router.register(r"cargas", CargaBaseViewSet, basename="orcamento-carga")

urlpatterns = [
    path("status/", OrcamentoStatusView.as_view(), name="orcamento-status"),
    path("bases-resumo/", BaseReferencialResumoView.as_view(), name="orcamento-bases-resumo"),
    path("controle/", ControleDeCustoView.as_view(), name="orcamento-controle"),
    path("nbr12721/", QuadrosNBRView.as_view(), name="orcamento-nbr12721"),
    *router.urls,
]
