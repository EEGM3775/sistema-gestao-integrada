# backend/moduloorcamento/views.py
"""API da base referencial — **read-only** por desenho.

A base é catálogo público de plataforma, gravado só por
`manage.py importar_base_referencial` (ver `models.py`). Então aqui não existe
`ModelViewSet`: quem tenta `POST`/`PUT`/`DELETE` numa publicação recebe 405, não
403 — a operação não existe, não é questão de permissão.

O único verbo de escrita do módulo nesta fatia é **adotar**, e ele não escreve na
base: escreve no `catalogo.Item` **do tenant**. Por isso exige permissão própria
(`orcamento.base.adotar`) e não o `.edit` do recurso.

**A ORC.8 não abriu exceção a isso.** O botão de carga escreve na base-mãe, mas
não é endpoint de tenant: é operação de plataforma, gateada por
`is_platform_admin` — o mesmo gate que já guardava a base-mãe em `impexp.py` —,
e o que ele faz é enfileirar um job, não gravar na requisição.
"""
from datetime import timedelta
from urllib.parse import urlsplit

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_date
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.busca import BuscaSemAcento
from rest_framework import (
    exceptions,
    filters,
    permissions,
    serializers,
    status,
    views,
    viewsets,
)
from rest_framework.decorators import action
from rest_framework.response import Response

from catalogo.models import Item
from nucleo.frota import MINUTOS_ATE_ORFA
from nucleo import autorizacao
from nucleo.permissions import RequireModule, RequirePermission
from nucleo.quotas import QuotaEnforcedMixin
from nucleo.tenancy import TenantScopedViewSetMixin

from payment import planos

from . import (
    bancos as servico_bancos,
    carga,
    cronograma as servico_cronograma,
    duplicacao,
    edicao,
    encargos,
    exportacao,
    insumos as servico_insumos,
    nbr12721,
    oficial,
    planilha,
    precificacao,
    quantitativos,
    reprecificacao as servico_reprecificacao,
    services,
    tasks,
)
from .models import (
    BancoPreco,
    BaseReferencial,
    CargaBase,
    ComponenteBancoPreco,
    ComposicaoBDI,
    ComposicaoEncargos,
    Fonte,
    FonteOficial,
    InsumoReferencia,
    ItemBancoPreco,
    ItemOrcado,
    ItemOrcadoInsumo,
    LinhaMedicao,
    LinhaReprecificacao,
    MemorialNBR,
    Orcamento,
    ParametroObra,
    ParcelaEtapa,
    PlanoEtapa,
    PastaComposicao,
    PavimentoObra,
    Reprecificacao,
    RubricaEncargos,
    RevisaoOrcamento,
    UnidadeAutonoma,
)
from .pagination import OrcamentoPageNumberPagination
from .serializers import (
    BancoPrecoSerializer,
    BaseReferencialSerializer,
    CargaBaseSerializer,
    ComponenteBancoPrecoSerializer,
    ComposicaoBDISerializer,
    ComposicaoEncargosSerializer,
    ComposicaoReferenciaItemSerializer,
    FonteOficialSerializer,
    InsumoReferenciaSerializer,
    ItemBancoPrecoSerializer,
    ItemOrcadoInsumoSerializer,
    ItemOrcadoSerializer,
    LinhaMedicaoSerializer,
    LinhaReprecificacaoSerializer,
    MemorialNBRSerializer,
    OrcamentoSerializer,
    ParametroObraSerializer,
    ParcelaEtapaSerializer,
    PastaComposicaoSerializer,
    PavimentoObraSerializer,
    ReprecificacaoSerializer,
    RevisaoOrcamentoSerializer,
    RubricaEncargosSerializer,
    UnidadeAutonomaSerializer,
)

MODULO = "orcamento"


class OrcamentoStatusView(views.APIView):
    """Status do módulo. Confirma entitlement antes de qualquer dado."""

    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = MODULO

    def get(self, request):
        publicacoes = BaseReferencial.objects.filter(ativa=True).count()
        return Response({"modulo": MODULO, "status": "ativo", "bases_referenciais": publicacoes})


class _OrcamentoPermsMixin:
    """Entitlement do módulo + permissão de campo, na mesma ordem dos outros
    módulos pagos (SCM/SIL): sem assinar → 403; assinando sem permissão → 403."""

    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = MODULO
    pagination_class = OrcamentoPageNumberPagination

    def _tenant_id(self):
        return getattr(getattr(self.request, "user", None), "tenant_id", None)


class BaseReferencialViewSet(_OrcamentoPermsMixin, viewsets.ReadOnlyModelViewSet):
    """As publicações disponíveis (SINAPI SP 07/2026 desonerado, ORSE SE 07/2026…)."""

    queryset = BaseReferencial.objects.all()
    serializer_class = BaseReferencialSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["fonte", "uf", "regime_encargos", "ativa"]
    ordering_fields = ["mes_referencia", "fonte", "uf"]
    # `required_permission` (fixa), NÃO `required_resource`: o atalho do recurso
    # derivaria `orcamento.base.edit` no método de escrita — uma permissão que
    # **não existe no catálogo**, porque a base não é editável por ninguém. O
    # efeito seria um 403 mentiroso ("falta permissão") no lugar do 405 correto
    # ("esta operação não existe aqui").
    required_permission = "orcamento.base.view"


class InsumoReferenciaViewSet(_OrcamentoPermsMixin, viewsets.ReadOnlyModelViewSet):
    """Insumos e composições de uma publicação, com busca server-side.

    A busca é o modo de uso real: ninguém navega 80 mil linhas — digita "concreto
    fck 25" e adota o que serve.
    """

    queryset = InsumoReferencia.objects.select_related("base").all()
    serializer_class = InsumoReferenciaSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["base", "tipo", "unidade"]
    search_fields = ["codigo", "descricao", "grupo"]
    ordering_fields = ["codigo", "descricao", "custo_unitario"]
    required_permission = "orcamento.base.view"  # ver nota em BaseReferencialViewSet
    action_permission_map = {
        "adotar": "orcamento.base.adotar",
        "adotar_lote": "orcamento.base.adotar",
    }

    def get_serializer_context(self):
        """Marca o que já está adotado no catálogo da empresa — um SELECT por
        página, para a lista não perguntar linha por linha."""
        contexto = super().get_serializer_context()
        pagina = getattr(self, "_pagina_atual", None)
        if not pagina:
            return contexto
        codigos = {obj.codigo for obj in pagina}
        fontes = {obj.base.fonte for obj in pagina}
        adotados = Item.objects.filter(
            tenant_id=self._tenant_id(),
            fonte_referencia__in=fontes,
            codigo_referencia__in=codigos,
        ).values_list("fonte_referencia", "codigo_referencia", "item_id")
        contexto["adotados"] = {(f, c): i for f, c, i in adotados}
        return contexto

    def paginate_queryset(self, queryset):
        pagina = super().paginate_queryset(queryset)
        self._pagina_atual = pagina
        return pagina

    def retrieve(self, request, *args, **kwargs):
        self._pagina_atual = [self.get_object()]
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="composicao")
    def composicao(self, request, pk=None):
        """A analítica da composição: insumos, coeficientes e a parcela de cada um."""
        referencia = self.get_object()
        componentes = services.componentes_da_composicao(referencia)
        return Response({
            "composicao": InsumoReferenciaSerializer(referencia, context=self.get_serializer_context()).data,
            "componentes": ComposicaoReferenciaItemSerializer(componentes, many=True).data,
        })

    @action(detail=True, methods=["post"], url_path="adotar")
    def adotar(self, request, pk=None):
        """Traz o item da base para o catálogo da empresa (idempotente).

        **409, não 400, quando a identidade diverge** (D110): não há nada errado
        com o pedido nem com o dado — o código existe dos dois lados e está bem
        formado. O que houve é conflito de identidade, e a resposta carrega os
        dois lados justamente para quem está na tela poder olhar e decidir. A
        decisão volta como `{"forcar": true}`.
        """
        referencia = self.get_object()
        recursivo = request.data.get("recursivo", True) not in (False, "false", "0", 0)
        forcar = request.data.get("forcar", False) not in (False, "false", "0", 0, None, "")
        try:
            item = services.adotar_no_catalogo(
                referencia, self._tenant_id(), recursivo=recursivo, forcar=forcar
            )
        except services.AdocaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except services.IdentidadeDivergente as exc:
            return Response(
                {"detail": str(exc), "divergencia": exc.como_dict()},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {
                "item_id": item.item_id,
                "codigo_interno": item.codigo_interno,
                "descricao": item.descricao,
                "tipo": item.tipo,
                "componentes": item.componentes.count(),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="adotar-lote")
    def adotar_lote(self, request):
        """Adota a seleção da busca de uma vez (`{"referencias": [1, 2, 3]}`)."""
        ids = request.data.get("referencias") or []
        if not isinstance(ids, list) or not ids:
            return Response(
                {"detail": "Informe 'referencias' com ao menos um id."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        referencias = list(
            InsumoReferencia.objects.filter(pk__in=ids).select_related("base")
        )
        if not referencias:
            return Response({"detail": "Nenhuma referência encontrada."}, status=status.HTTP_404_NOT_FOUND)
        forcar = request.data.get("forcar", False) not in (False, "false", "0", 0, None, "")
        try:
            resultado = services.adotar_muitos(referencias, self._tenant_id(), forcar=forcar)
        except services.AdocaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        # O lote não falha por causa de um divergente: os que conferem entram e
        # os que não conferem voltam listados, para a tela dizer quais ficaram
        # de fora e por quê (D110).
        return Response(
            {
                "adotados": len(resultado.adotados),
                "itens": [
                    {"item_id": i.item_id, "codigo_interno": i.codigo_interno, "descricao": i.descricao}
                    for i in resultado.adotados
                ],
                "divergentes": resultado.divergentes,
            },
            status=status.HTTP_201_CREATED,
        )


class BaseReferencialResumoView(views.APIView):
    """Resumo por publicação para o seletor de base-de-preço da planilha:
    o que existe, de quando é e quanto a empresa já adotou de cada uma."""

    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = MODULO
    required_permission = "orcamento.base.view"

    def get(self, request):
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        bases = (
            BaseReferencial.objects.filter(ativa=True)
            .order_by("-mes_referencia", "fonte")
        )
        adotados_por_fonte = dict(
            Item.objects.filter(tenant_id=tenant_id)
            .exclude(codigo_referencia="")
            .values_list("fonte_referencia")
            .annotate(total=Count("item_id"))
        )
        # **Por que agregado solto, e não `annotate` na lista de publicações.**
        # O `Count("itens")` correlacionado custa uma varredura da tabela de
        # referências *por publicação*. Com a SINAPI inteira carregada — 1.460
        # publicações sobre 16,8 milhões de linhas — isso media ~2,4 s a cada
        # abertura, e seis telas do módulo pedem este mesmo resumo. Duas
        # agregações chapadas, casadas em memória por `base_id`, dão os mesmos
        # números em ~0,9 s e continuam **derivadas do dado real**: nenhum
        # contador gravado que possa defasar e fazer a tela mentir sobre o que
        # há na publicação.
        #
        # O `.order_by()` vazio não é enfeite. `Meta.ordering` do
        # `InsumoReferencia` é `["base", "codigo"]`, e o Django empurra os campos
        # de ordenação para dentro do `GROUP BY` — sem zerar, o agrupamento sai
        # por item e toda contagem vira 1.
        totais_por_base: dict[int, dict[str, int]] = {}
        for linha in (
            InsumoReferencia.objects.values("base_id", "tipo")
            .annotate(n=Count("referencia_id"))
            .order_by()
        ):
            totais_por_base.setdefault(linha["base_id"], {})[linha["tipo"]] = linha["n"]
        # As classes distintas que cada publicação usa em INSUMO — no pior caso
        # real, oito por publicação. Sem isto, `classifica_insumo` significava só
        # "a coluna veio preenchida", e uma base de vocabulário próprio (ORSE,
        # SICRO, tabela de prefeitura) acendia o indicador verde enquanto
        # **nenhuma** das classes dela era compreendida — falso "está tudo
        # certo", que é pior do que a publicação antiga, onde o campo vazio ao
        # menos era evidente.
        #
        # Um `GROUP BY (base_id, grupo)` responde as duas perguntas de uma vez:
        # a soma das contagens é quantos insumos vieram classificados, e as
        # chaves são o vocabulário da publicação. O agrupamento do banco separa
        # "Agregados" de "Agregados " — para o SQL são textos diferentes, e a
        # tela listava a mesma classe duas vezes. Quem deduplica é o `set` sobre
        # o texto já aparado.
        classificados_por_base: dict[int, int] = {}
        desconhecidas_por_base: dict[int, set[str]] = {}
        for linha in (
            InsumoReferencia.objects.filter(tipo=InsumoReferencia.Tipo.INSUMO)
            .exclude(grupo="")
            # `base__fonte` entra no GROUP BY porque **ler classe é por fonte**: o
            # de-para declarado vive em `dados/classes/<fonte>.csv` e vence o
            # embutido (ORC.9c). Sem a fonte aqui só o `PREFIXOS_DE_CLASSE`
            # respondia, e o vocabulário em sigla da EMBASA (`MAT.`, `M.O.`,
            # `EQ.LOC`) era reportado como ilegível embora o CSV o traduza — o
            # indicador de honestidade acusando defeito onde não havia, que é o
            # mesmo tipo de mentira que a ORC.9c existe para impedir, só que na
            # direção contrária.
            .values("base_id", "base__fonte", "grupo")
            .annotate(n=Count("referencia_id"))
            .order_by()
        ):
            base_id, grupo = linha["base_id"], linha["grupo"]
            classificados_por_base[base_id] = (
                classificados_por_base.get(base_id, 0) + linha["n"]
            )
            if services.classificacao_desconhecida(grupo, linha["base__fonte"]):
                desconhecidas_por_base.setdefault(base_id, set()).add(grupo.strip())
        def resumo_de(b) -> dict:
            contagens = totais_por_base.get(b.base_id, {})
            insumos = contagens.get(InsumoReferencia.Tipo.INSUMO, 0)
            classificados = classificados_por_base.get(b.base_id, 0)
            return {
                "base_id": b.base_id,
                "rotulo": b.rotulo or b.rotulo_automatico(),
                "fonte": b.fonte,
                "uf": b.uf,
                "mes_referencia": b.mes_referencia,
                "regime_encargos": b.regime_encargos,
                # ORC.8b — o quarto eixo, vazio em quase toda publicação. Ele
                # precisa sair aqui porque o seletor encadeia praça → mês →
                # regime: na EMBASA, duas publicações que só diferem na convenção
                # coletiva chegariam ao último passo como duas linhas de nome
                # igual, e escolher entre elas seria adivinhar.
                "variante": b.variante,
                "insumos": insumos,
                "composicoes": contagens.get(InsumoReferencia.Tipo.COMPOSICAO, 0),
                "insumos_classificados": classificados,
                # As classes que a publicação usa e que o de-para de
                # `PREFIXOS_DE_CLASSE` não conhece, com o texto literal — é o que
                # a tela mostra para alguém decidir se aquilo vira mapeamento ou
                # `--de-para`.
                "classes_desconhecidas": sorted(
                    desconhecidas_por_base.get(b.base_id, set())
                )[:12],
                # Publicação sem insumo nenhum não "deixa de classificar" — não
                # há o que classificar. O `False` é reservado para a publicação
                # que **tem** insumo e cuja classificação não chega até a
                # natureza: ou porque o campo vem vazio (D111), ou porque veio
                # num vocabulário que não sabemos ler — que dá no mesmo para
                # quem orça, e por isso acende o mesmo aviso.
                "classifica_insumo": (
                    insumos == 0
                    or (classificados > 0 and b.base_id not in desconhecidas_por_base)
                ),
                "adotados_no_catalogo": adotados_por_fonte.get(b.fonte, 0),
            }

        return Response([resumo_de(b) for b in bases])


# ---------------------------------------------------------------------------
# ORC.8 — a carga da base oficial (só o dono da plataforma)
# ---------------------------------------------------------------------------


class SoDonoDaPlataforma(permissions.BasePermission):
    """`is_platform_admin`, e **só** ele — sem entitlement de módulo junto.

    Exigir também o `orcamento` seria errado por um motivo concreto: a base-mãe
    vale para todos os tenants, e o tenant do dono da plataforma pode não assinar
    o módulo. Ele estaria barrado de carregar a base que os clientes dele usam.

    É o mesmo desenho do `IncidenteLGPD` no `nucleo/lgpd_views.py`: operação da
    plataforma sobre dado que não é de ninguém em particular.
    """

    message = (
        "Só o dono da plataforma carrega base oficial — ela vale para todas as "
        "empresas. Para trazer preços da sua empresa, use um banco de preço."
    )

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and autorizacao.supervisiona(user))


def _nome_de_quem_pediu(request) -> str:
    user = getattr(request, "user", None)
    return (getattr(user, "username", "") or getattr(user, "email", "") or "")[:150]


class FonteOficialViewSet(viewsets.ModelViewSet):
    """Onde mora o endereço de cada fonte — a caixa de texto que evita o deploy.

    Escrita liberada de propósito, e é a decisão de rumo: a URL da Caixa **já
    mudou uma vez** (o padrão por UF morreu em 12/2024). Template compilado no
    código transformaria isso num release no meio do mês; numa caixa de texto, o
    conserto é de trinta segundos e é feito por quem percebeu o problema.
    """

    permission_classes = [permissions.IsAuthenticated, SoDonoDaPlataforma]
    queryset = FonteOficial.objects.all()
    serializer_class = FonteOficialSerializer
    pagination_class = None


class CargaBaseViewSet(viewsets.ReadOnlyModelViewSet):
    """O histórico das corridas e os verbos que disparam uma nova.

    **Histórico guardado, nada apagado** — inclusive o das que falharam, que são
    as que mais valem: a diferença entre "o WAF cortou", "o mês ainda não saiu" e
    "o layout mudou" só existe se alguém a escrever no momento em que ela é
    conhecida.
    """

    permission_classes = [permissions.IsAuthenticated, SoDonoDaPlataforma]
    queryset = CargaBase.objects.all()
    serializer_class = CargaBaseSerializer
    pagination_class = OrcamentoPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["fonte", "estado", "origem", "competencia"]
    ordering_fields = ["criada_em", "competencia"]

    # --- o que a tela precisa saber antes de oferecer o botão ---------------

    @action(detail=False, methods=["get"], url_path="estado")
    def estado(self, request):
        """Fontes configuradas, corrida em andamento e a última de cada fonte."""
        fontes = FonteOficial.objects.all().order_by("fonte")
        andamento = CargaBase.objects.filter(
            estado__in=[
                CargaBase.Estado.PENDENTE, CargaBase.Estado.BAIXANDO,
                CargaBase.Estado.LENDO, CargaBase.Estado.GRAVANDO,
            ]
        ).order_by("-criada_em").first()
        ultimas = {}
        for registro in CargaBase.objects.order_by("fonte", "-criada_em"):
            ultimas.setdefault(registro.fonte, registro)
        return Response({
            "fontes": FonteOficialSerializer(fontes, many=True).data,
            "fontes_com_motor": carga.fontes_conhecidas(),
            "em_andamento": (
                CargaBaseSerializer(andamento).data if andamento is not None else None
            ),
            "ultima_por_fonte": {
                fonte: CargaBaseSerializer(registro).data
                for fonte, registro in ultimas.items()
            },
            "teto_mb": planos.ORCAMENTO_CARGA_TETO_MB,
        })

    @action(detail=False, methods=["get"], url_path="documentos-disponiveis")
    def documentos_disponiveis(self, request):
        """O **menu** de artefatos da fonte — o que a tela lista antes do botão.

        Existe porque "a publicação do mês" deixou de ser uma coisa só quando a
        EMBASA entrou: ela publica por semestre, e são 65 tabelas carregáveis
        (expansão, operação de água e de esgoto, cada uma por convenção
        coletiva), nenhuma delas a principal. Sem esta lista a única saída seria
        pedir que alguém colasse a URL — e colar a errada é indistinguível de
        colar a certa até o preço sair na planilha.

        Bate no site da fonte, então é `GET` que custa rede: a tela chama quando
        o operador abre a fonte, não a cada render.
        """
        fonte = str(request.query_params.get("fonte") or "").strip()
        if fonte not in dict(Fonte.choices):
            raise exceptions.ValidationError({"fonte": "Fonte desconhecida."})
        competencia = request.query_params.get("competencia")
        try:
            documentos = carga.documentos_disponiveis(
                fonte, self._competencia(competencia, fonte) if competencia else None
            )
        except oficial.CargaIndisponivel as exc:
            # A fonte fora do ar não é erro do pedido: é o estado do mundo, e a
            # tela precisa dizê-lo com o motivo para oferecer o plano B (upload)
            # em vez de uma lista vazia que parece "não há nada publicado".
            return Response(
                {"documentos": [], "erro": str(exc), "motivo": exc.motivo},
                status=status.HTTP_200_OK,
            )
        return Response({"fonte": fonte, "documentos": documentos, "erro": "", "motivo": ""})

    # --- disparar ------------------------------------------------------------

    def _disparar(self, carga_nova: CargaBase) -> Response:
        """Enfileira e responde 202: a corrida é job, não requisição.

        Um ZIP nacional rende 54 publicações de ~17 mil linhas — trabalho de
        minutos. Fazê-lo na requisição seria timeout no gateway com a carga
        rodando por trás, que é o pior dos dois mundos.
        """
        transaction.on_commit(
            lambda: tasks.carregar_base_oficial.delay(carga_nova.pk)
        )
        return Response(
            CargaBaseSerializer(carga_nova).data, status=status.HTTP_202_ACCEPTED
        )

    def _recusar_concorrente(self, fonte: str) -> None:
        """Duas cargas da mesma fonte ao mesmo tempo escreveriam as mesmas
        publicações em paralelo. Não é corrupção (o upsert é por código), mas é
        trabalho dobrado numa operação medida em minutos — e some com o relato,
        porque as duas mexem no mesmo mês.

        **"Em andamento" tem prazo, e essa parte foi aprendida apanhando.** Uma
        corrida enfileirada para um worker que não estava ouvindo fica `pendente`
        para sempre, e sem o prazo ela travaria aquela fonte **em definitivo**:
        nenhuma carga nova entra, e a tela não oferece saída porque, para ela, há
        uma carga rodando. É a mesma morte violenta que o
        `nucleo.liberar_cadeiras_presas` já trata na frota (OOM do cgroup,
        contêiner derrubado, broker reiniciado), e a resposta aqui é a mesma:
        parada de crescer o carimbo, a corrida deixou de estar viva.

        `MINUTOS_ATE_ORFA` é folga larga sobre o relógio de uma carga honesta
        (`ORCAMENTO_CARGA_SEGUNDOS` = 30 min do dono), e o `atualizada_em` é
        reescrito a cada degrau — baixando, lendo, gravando cada UF —, então uma
        carga viva nunca chega perto dele.
        """
        limite = timezone.now() - timedelta(minutes=MINUTOS_ATE_ORFA)
        if CargaBase.objects.filter(
            fonte=fonte,
            atualizada_em__gte=limite,
            estado__in=[
                CargaBase.Estado.PENDENTE, CargaBase.Estado.BAIXANDO,
                CargaBase.Estado.LENDO, CargaBase.Estado.GRAVANDO,
            ],
        ).exists():
            raise exceptions.ValidationError(
                {"fonte": "Já existe uma carga desta fonte em andamento."}
            )
        # A órfã não some: vira `falhou` com o motivo escrito, senão o histórico
        # guardaria uma corrida eternamente "na fila" e ninguém saberia por quê.
        CargaBase.objects.filter(
            fonte=fonte,
            atualizada_em__lt=limite,
            estado__in=[
                CargaBase.Estado.PENDENTE, CargaBase.Estado.BAIXANDO,
                CargaBase.Estado.LENDO, CargaBase.Estado.GRAVANDO,
            ],
        ).update(
            estado=CargaBase.Estado.FALHOU,
            etapa="",
            erro=(
                f"Sem notícia por mais de {MINUTOS_ATE_ORFA} minutos — a corrida foi "
                "dada como órfã. Quase sempre é o worker do Celery fora do ar quando "
                "ela foi enfileirada; o trabalho não começou, e repetir é seguro."
            ),
        )

    def create(self, request, *args, **kwargs):
        """Baixa do site oficial. É o botão."""
        fonte = str(request.data.get("fonte") or "").strip()
        if fonte not in dict(Fonte.choices):
            raise exceptions.ValidationError({"fonte": "Fonte desconhecida."})
        self._recusar_concorrente(fonte)
        competencia = self._competencia(request.data.get("competencia"), fonte)
        nova = CargaBase.objects.create(
            fonte=fonte,
            competencia=competencia,
            origem=CargaBase.Origem.DOWNLOAD,
            # O documento escolhido na lista, quando a fonte tem mais de um. A
            # corrida nasce com o endereço e o motor o respeita; vazio, o
            # template da `FonteOficial` decide, como era na ORC.8.
            url_origem=self._documento(request.data.get("url"), fonte),
            somente_resumo=bool(request.data.get("somente_resumo")),
            aceitar_sem_classe=bool(request.data.get("aceitar_sem_classe")),
            solicitada_por_nome=_nome_de_quem_pediu(request),
        )
        return self._disparar(nova)

    def _documento(self, bruta, fonte: str) -> str:
        """Confere a URL escolhida contra o endereço cadastrado da fonte.

        **A conferência não é burocracia.** Este endpoint é do dono da
        plataforma e manda o worker buscar uma URL arbitrária de dentro da rede
        interna — é SSRF com convite. Amarrar o endereço ao host que já está
        cadastrado em `FonteOficial` mantém a liberdade que a EMBASA exige
        (escolher entre 65 documentos do mesmo site) sem abrir a porta para
        `http://169.254.169.254/` nem para o Redis do compose.
        """
        url = str(bruta or "").strip()
        if not url:
            return ""
        configuracao = FonteOficial.objects.filter(fonte=fonte).first()
        cadastrado = (configuracao.template_url if configuracao else "") or ""
        esperado = urlsplit(cadastrado).netloc.lower()
        pedido = urlsplit(url)
        if pedido.scheme not in ("http", "https") or not esperado:
            raise exceptions.ValidationError({
                "url": (
                    "Escolha o documento pela lista de `documentos-disponiveis`. "
                    "A fonte precisa ter o endereço cadastrado antes."
                )
            })
        if pedido.netloc.lower() != esperado:
            raise exceptions.ValidationError({
                "url": (
                    f"O documento tem de estar em {esperado} — é o endereço "
                    f"cadastrado para esta fonte. Veio de {pedido.netloc or '(vazio)'}."
                )
            })
        return url[:500]

    @action(detail=False, methods=["post"], url_path="enviar")
    def enviar(self, request):
        """**Plano B**: o mês em que a Caixa muda o layout ou aperta o WAF não
        pode parar a carga. O arquivo vem à mão e segue o mesmo caminho."""
        fonte = str(request.data.get("fonte") or "").strip()
        if fonte not in dict(Fonte.choices):
            raise exceptions.ValidationError({"fonte": "Fonte desconhecida."})
        arquivo = request.FILES.get("arquivo")
        if arquivo is None:
            raise exceptions.ValidationError({
                "arquivo": "Envie o artefato oficial — ZIP/.xlsx da SINAPI, .pdf da EMBASA."
            })
        teto = planos.ORCAMENTO_CARGA_TETO_MB * 1024 * 1024
        if arquivo.size > teto:
            raise exceptions.ValidationError({
                "arquivo": (
                    f"O arquivo tem {arquivo.size / (1024 * 1024):.0f} MB e o teto é "
                    f"{planos.ORCAMENTO_CARGA_TETO_MB} MB."
                )
            })
        self._recusar_concorrente(fonte)
        nova = CargaBase.objects.create(
            fonte=fonte,
            competencia=self._competencia(request.data.get("competencia"), fonte),
            origem=CargaBase.Origem.UPLOAD,
            arquivo=arquivo,
            arquivo_nome=(arquivo.name or "")[:255],
            somente_resumo=bool(request.data.get("somente_resumo")),
            aceitar_sem_classe=bool(request.data.get("aceitar_sem_classe")),
            solicitada_por_nome=_nome_de_quem_pediu(request),
        )
        return self._disparar(nova)

    @action(detail=True, methods=["post"], url_path="repetir")
    def repetir(self, request, pk=None):
        """Roda de novo a mesma corrida — é o caminho de volta do `aguardando`.

        A carga que parou por classe sem tradução fez uma **pergunta**; esta é a
        resposta. Ou o superuser declarou o de-para em `dados/classes/<fonte>.csv`
        e repete igual, ou aceita que aqueles insumos entrem pela unidade e
        repete com `aceitar_sem_classe`.
        """
        anterior = self.get_object()
        self._recusar_concorrente(anterior.fonte)
        nova = CargaBase.objects.create(
            fonte=anterior.fonte,
            competencia=anterior.competencia,
            origem=anterior.origem,
            # Repetir é repetir **o mesmo documento**: numa fonte com 65 tabelas,
            # perder o endereço faria a segunda tentativa carregar outra coisa
            # com a mesma cara de sucesso.
            url_origem=anterior.url_origem,
            arquivo=anterior.arquivo,
            arquivo_nome=anterior.arquivo_nome,
            somente_resumo=bool(request.data.get("somente_resumo")),
            aceitar_sem_classe=bool(request.data.get("aceitar_sem_classe")),
            solicitada_por_nome=_nome_de_quem_pediu(request),
        )
        return self._disparar(nova)

    def _competencia(self, bruta, fonte: str):
        if not bruta:
            return carga.competencia_sugerida(fonte)
        competencia = parse_date(str(bruta)) or parse_date(f"{bruta}-01")
        if competencia is None:
            raise exceptions.ValidationError({"competencia": "Use AAAA-MM."})
        return competencia.replace(day=1)


# ---------------------------------------------------------------------------
# ORC.1 — planilha orçamentária
# ---------------------------------------------------------------------------


class _PeriodoSerializer(serializers.Serializer):
    """Entrada da distribuição do cronograma. Serializer em vez de leitura crua
    do `request.data` para a data inválida virar 400 com mensagem de campo."""

    inicio = serializers.DateField()
    fim = serializers.DateField()
    curva = serializers.ChoiceField(choices=PlanoEtapa.Curva.choices, required=False)
    so_sem_plano = serializers.BooleanField(required=False, default=False)


class _PlanoEtapaSerializer(serializers.Serializer):
    grupo = serializers.IntegerField()
    inicio = serializers.DateField()
    termino = serializers.DateField()
    curva = serializers.ChoiceField(choices=PlanoEtapa.Curva.choices, required=False)
    observacao = serializers.CharField(required=False, allow_blank=True, max_length=255)


class DocumentoFechado(exceptions.APIException):
    """**409**, não 403: não falta permissão, o documento é que não está aberto.

    A distinção importa para a tela — 403 manda o usuário procurar o admin, 409
    manda ele criar uma revisão, que é o caminho real.
    """

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Orçamento não editável."
    default_code = "documento_fechado"


def _exigir_editavel(orcamento) -> None:
    """Ponte entre a exceção de domínio e o vocabulário HTTP."""
    try:
        planilha.exigir_editavel(orcamento)
    except planilha.OrcamentoNaoEditavel as exc:
        raise DocumentoFechado(str(exc)) from exc


class OrcamentoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """A planilha: CRUD + os verbos que mudam o **estado** da régua de custo.

    `aprovar` e `revisar` são permissões próprias (`orcamento.orcamento.aprovar`
    /`.revisar`), não o `.edit` do recurso: congelar o custo de uma obra é
    decisão de quem responde por ela, e quem digita a planilha (persona
    `orcamentista`) não é necessariamente quem assina embaixo.
    """

    queryset = Orcamento.objects.select_related("obra", "base_referencial").all()
    serializer_class = OrcamentoSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["obra", "status", "versao", "base_referencial"]
    search_fields = ["descricao", "obra__nome_obra"]
    ordering_fields = ["criado_em", "valor_total", "versao"]
    required_resource = "orcamento.orcamento"
    action_permission_map = {
        "aprovar": "orcamento.orcamento.aprovar",
        # ORC.10e — permissão própria, e não `edit`: reabrir documento aprovado
        # é alçada, do mesmo tipo que aprovar. Quem monta a planilha não herda
        # o poder de descongelar a régua contra a qual o custo é medido.
        "destravar": "orcamento.orcamento.destravar",
        "revisar": "orcamento.orcamento.revisar",
        "recalcular": "orcamento.orcamento.edit",
        "arvore": "orcamento.orcamento.view",
        "analitica": "orcamento.orcamento.view",
        # Relatórios de controle sob `relatorio.view`; mexer no cronograma é
        # editar o orçamento. Os dois reusam as 9 permissões do catálogo em vez
        # de criar `orcamento.cronograma.*` — permissão nova exige rebuild da
        # imagem da IAM + re-seed, e o recorte aqui não pedia granularidade nova.
        "curva_abc": "orcamento.relatorio.view",
        "por_categoria": "orcamento.relatorio.view",
        "cronograma": "orcamento.relatorio.view",
        "distribuir_cronograma": "orcamento.orcamento.edit",
        "planejar_etapa": "orcamento.orcamento.edit",
        "remover_etapa": "orcamento.orcamento.edit",
        "vincular_etapa": "orcamento.orcamento.edit",
        # ORC.5b. Duplicar cria planilha nova → `.edit`; reprecificar mexe no
        # preço da régua, também `.edit`. Exportar é leitura de relatório.
        # Nenhuma permissão nova: ver §12.1 da planta — permissão nova exige
        # rebuild da imagem da IAM + re-seed, e o recorte aqui não pediu.
        "duplicar": "orcamento.orcamento.edit",
        "copiar_itens": "orcamento.orcamento.edit",
        "reprecificar": "orcamento.orcamento.edit",
        "reprecificacoes": "orcamento.orcamento.view",
        "avisos": "orcamento.orcamento.view",
        "exportar": "orcamento.relatorio.view",
        # ORC.7 — quatro leituras novas, todas relatório. Continuam sem
        # permissão nova pelo mesmo motivo de sempre.
        "relacao_insumos": "orcamento.relatorio.view",
        # Gera a memória de cálculo das linhas (o mesmo verbo do `explodir` da
        # linha), sem tocar preço.
        "explodir_pendentes": "orcamento.item.edit",
        "curva_abc_insumos": "orcamento.relatorio.view",
        "desembolso_insumos": "orcamento.relatorio.view",
        "cobertura_medicao": "orcamento.relatorio.view",
    }

    #: Os estados em que a planilha **não rege mais nada** e por isso pode sair.
    #:
    #: A régua é a do dono (13/09/2026): a trava existe para proteger a empresa,
    #: **não para tutelar o usuário**. Rascunho é tentativa, cancelado é morto e
    #: superado foi trocado por revisão — nenhum dos três rege obra nenhuma, e
    #: segurar documento morto não é proteção, é estorvo: o cliente fica pagando
    #: espaço por lixo que o sistema se recusa a deixá-lo limpar.
    #:
    #: **Aprovado é o único fora**, porque é base contratual — e mesmo ele não é
    #: beco sem saída: cancelar já existe, é um clique, e abre o caminho. Nunca
    #: há estado do qual não se saia; é isso que separa trava de tutela.
    STATUS_QUE_SAEM = (
        Orcamento.Status.RASCUNHO,
        Orcamento.Status.CANCELADO,
        Orcamento.Status.SUPERADO,
    )

    def perform_update(self, serializer):
        _exigir_editavel(self.get_object())
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        """Sai o que não rege mais nada — e a recusa diz como destravar.

        **A trava existia e era apertada demais.** Ela usava `_exigir_editavel`,
        que é a régua da **escrita**: só rascunho. O efeito colateral é que
        cancelado e superado — documentos mortos, que não regem obra nenhuma —
        também não saíam. O usuário ficava com lixo que o sistema se recusava a
        deixá-lo limpar, que é exatamente o que a decisão do dono (13/09/2026)
        veio corrigir: *"um orçamento que não pode ser usado também não pode
        atrapalhar o usuário"*.

        Editar e excluir passaram a ser réguas **diferentes**, e a diferença é o
        ponto: um superado não aceita escrita (é história de revisão) mas aceita
        exclusão (não rege nada). Reusar a régua da escrita para a exclusão foi o
        que criou a armadilha.

        **Aprovado continua fora**, porque é a base contratual contra a qual
        medições já foram feitas — e mesmo ele não é beco sem saída: cancelar
        abre o caminho.

        O `super()` agora marca a lápide (D116) em vez de apagar — o
        `instance.delete()` que estava aqui passaria por cima da lixeira e
        levaria as sete tabelas filhas junto, sem desfazer.
        """
        if instance.status not in self.STATUS_QUE_SAEM:
            # `DocumentoFechado` (409) pelo mesmo motivo que a escrita usa: não
            # falta permissão — o documento é que está em vigor. Um 403 mandaria
            # a pessoa procurar o administrador, que não resolveria nada.
            raise DocumentoFechado(
                f"Orçamento v{instance.versao} está aprovado e é a base "
                "contratual da obra — por isso não sai. Cancele-o primeiro: "
                "depois de cancelado, ele pode ser excluído normalmente."
            )
        super().perform_destroy(instance)

    @action(detail=True, methods=["get"], url_path="avisos")
    def avisos(self, request, pk=None):
        """Linhas com preço mais velho que a data-base que a planilha anuncia.

        Fica no **orçamento**, e não no lote de reprecificação, porque é a
        planilha que vai para a licitação: quem abre o arquivo meses depois
        precisa ver o defeito sem ir atrás do histórico de lotes.
        """
        return Response(
            servico_reprecificacao.avisos_de_data_base(self.get_object())
        )

    @action(detail=True, methods=["get"], url_path="arvore")
    def arvore(self, request, pk=None):
        """A planilha inteira numa resposta, já ordenada pela EAP.

        A tela de orçamento é uma árvore que se lê de cima a baixo; paginar
        linha a linha quebraria a hierarquia (um filho poderia cair numa página
        sem o pai). Quem precisa de fatia usa o `itens/` filtrado.
        """
        orcamento = self.get_object()
        itens = (
            ItemOrcado.objects.filter(orcamento=orcamento)
            .select_related("etapa", "item")
            .order_by("codigo_eap", "ordem", "item_orcado_id")
        )
        return Response({
            "orcamento": self.get_serializer(orcamento).data,
            "itens": ItemOrcadoSerializer(itens, many=True).data,
        })

    @action(detail=True, methods=["get"], url_path="analitica")
    def analitica(self, request, pk=None):
        """A composição de **todas** as linhas, indexada pelo id da linha.

        É o que a grade desenha embaixo de cada serviço no modo analítico — a
        convenção da SINAPI, onde sintético e analítico são a mesma planilha
        vista com e sem a composição, e não dois recortes da EAP.

        Resposta separada da `arvore/` de propósito: trocar de modo na tela não
        pode jogar fora a árvore já carregada nem esperar por ela de novo, e
        quem só lê a planilha nunca chega a pedir esta.
        """
        return Response(precificacao.analitica_por_linha(self.get_object()))

    @action(detail=True, methods=["post"], url_path="recalcular")
    def recalcular(self, request, pk=None):
        """Renumera a EAP e refaz os totais de baixo para cima."""
        orcamento = self.get_object()
        planilha.recalcular_orcamento(orcamento)
        orcamento.refresh_from_db()
        return Response(self.get_serializer(orcamento).data)

    @action(detail=True, methods=["post"], url_path="aprovar")
    def aprovar(self, request, pk=None):
        orcamento = self.get_object()
        try:
            planilha.aprovar_orcamento(
                orcamento, usuario_nome=self._nome_do_usuario(request)
            )
        except planilha.OrcamentoNaoEditavel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        orcamento.refresh_from_db()
        return Response(self.get_serializer(orcamento).data)

    @action(detail=True, methods=["get"], url_path="por-categoria")
    def por_categoria(self, request, pk=None):
        """Custo direto por natureza de insumo (material × mão de obra × equipamento).

        Só vê linha explodida, então a resposta carrega a `cobertura_pct` — a
        tela mostra o gráfico e diz de quanto da planilha ele fala.

        Com `?por_etapa=1` (ORC.7) o corte desce para a etapa, que é o que
        transforma o gráfico em decisão: uma obra 60% material no total pode ser
        90% mão de obra no acabamento, e é essa etapa que precisa de efetivo
        contratado com antecedência.
        """
        if request.query_params.get("por_etapa") in ("1", "true", "True"):
            return Response(
                servico_insumos.resumo_por_natureza(self.get_object(), por_etapa=True)
            )
        return Response(precificacao.custo_por_categoria(self.get_object()))

    # --- ORC.7: o orçamento visto por insumo ---

    @action(detail=True, methods=["get"], url_path="relacao-insumos")
    def relacao_insumos(self, request, pk=None):
        """A **lista de compra da obra**: cada insumo uma vez, com quantidade total.

        É a saída que o SCM consome para gerar `Demanda` — e a peça que faltava
        para a planilha virar entrada do suprimento em vez de documento parado.
        Aceita `?categoria=material` para separar o que se compra do que se
        contrata.
        """
        return Response(servico_insumos.relacao_de_insumos(
            self.get_object(), categoria=request.query_params.get("categoria") or None,
        ))

    @action(detail=True, methods=["post"], url_path="explodir-pendentes")
    def explodir_pendentes(self, request, pk=None):
        """Abre de uma vez as composições que faltam, **sem mexer no preço** —
        o gesto que o comprador fazia linha a linha, indo e voltando."""
        resultado = precificacao.explodir_pendentes(self.get_object())
        return Response(resultado)

    @action(detail=True, methods=["get"], url_path="curva-abc-insumos")
    def curva_abc_insumos(self, request, pk=None):
        """Curva ABC **de insumos** — onde negociar preço.

        Complementa a de serviços, que diz onde negociar escopo. O aço diluído
        em nove serviços nunca aparece como item A na curva de serviços, e é
        item A da obra.
        """
        return Response(servico_insumos.curva_abc_insumos(self.get_object()))

    @action(detail=True, methods=["get"], url_path="desembolso-insumos")
    def desembolso_insumos(self, request, pk=None):
        """Quanto de cada insumo cai em cada mês, herdando o cronograma da etapa."""
        return Response(servico_cronograma.desembolso_por_insumo(
            self.get_object(), categoria=request.query_params.get("categoria") or None,
        ))

    @action(detail=True, methods=["get"], url_path="cobertura-medicao")
    def cobertura_medicao(self, request, pk=None):
        """Quanto do custo tem quantidade com memória — ponderado por valor."""
        return Response(quantitativos.cobertura_do_orcamento(self.get_object()))

    @action(detail=True, methods=["get"], url_path="curva-abc")
    def curva_abc(self, request, pk=None):
        """Onde está o dinheiro do orçamento — ~20% dos itens, ~80% do custo.

        Mesma leitura que o SIL faz do estoque, agora do lado do planejado: as
        duas telas usam a mesma convenção de classe, então A no orçado e A no
        aplicado querem dizer a mesma coisa.
        """
        return Response(precificacao.curva_abc(self.get_object()))

    # --- Cronograma físico-financeiro, por etapa (decisão do dono, 10/10/2026) ---

    @action(detail=True, methods=["get"], url_path="cronograma")
    def cronograma(self, request, pk=None):
        """As etapas planejadas, a grade etapa × mês, o desembolso mensal e a
        conferência dos 100% — tudo numa chamada."""
        return Response(servico_cronograma.cronograma(self.get_object()))

    def _escrever_cronograma(self, gesto, *, criado=False):
        orcamento = self.get_object()
        try:
            gesto(orcamento)
        except servico_cronograma.CronogramaFechado as exc:
            raise DocumentoFechado(str(exc)) from exc
        except servico_cronograma.CronogramaInvalido as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            servico_cronograma.cronograma(orcamento),
            status=status.HTTP_201_CREATED if criado else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="distribuir-cronograma")
    def distribuir_cronograma(self, request, pk=None):
        """Ponto de partida: o mesmo período e a mesma curva para toda etapa com
        valor (ou só para as ainda não planejadas, com `so_sem_plano`). O ajuste
        é etapa a etapa, em `planejar-etapa/`."""
        serializer = _PeriodoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data
        return self._escrever_cronograma(lambda orc: servico_cronograma.planejar_todas(
            orc, inicio=dados["inicio"], termino=dados["fim"],
            curva=dados.get("curva") or PlanoEtapa.Curva.LINEAR,
            so_sem_plano=dados.get("so_sem_plano", False),
        ), criado=True)

    @action(detail=True, methods=["post"], url_path="planejar-etapa")
    def planejar_etapa(self, request, pk=None):
        """Início, término e curva de uma etapa — a grade dela é refeita."""
        serializer = _PlanoEtapaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data
        return self._escrever_cronograma(lambda orc: servico_cronograma.planejar_etapa(
            orc, grupo_id=dados["grupo"], inicio=dados["inicio"], termino=dados["termino"],
            curva=dados.get("curva") or PlanoEtapa.Curva.LINEAR,
            observacao=dados.get("observacao", ""),
        ))

    @action(detail=True, methods=["post"], url_path="remover-etapa")
    def remover_etapa(self, request, pk=None):
        """Tira a etapa do cronograma (plano e células)."""
        grupo = request.data.get("grupo")
        if not str(grupo or "").isdigit():
            return Response({"grupo": "Informe a etapa."}, status=status.HTTP_400_BAD_REQUEST)
        return self._escrever_cronograma(
            lambda orc: servico_cronograma.remover_etapa(orc, grupo_id=int(grupo))
        )

    @action(detail=True, methods=["post"], url_path="vincular-etapa")
    def vincular_etapa(self, request, pk=None):
        """Liga a etapa do orçamento a uma etapa da obra — ou desliga (`etapa`
        nula). Opcional: o cronograma não depende disso; serve para o orçado
        casar com o aplicado do SIL e com o plano do PDCA."""
        grupo, etapa = request.data.get("grupo"), request.data.get("etapa")
        if not str(grupo or "").isdigit():
            return Response({"grupo": "Informe a etapa do orçamento."}, status=status.HTTP_400_BAD_REQUEST)
        if etapa not in (None, "") and not str(etapa).isdigit():
            return Response({"etapa": "Etapa da obra inválida."}, status=status.HTTP_400_BAD_REQUEST)
        return self._escrever_cronograma(lambda orc: servico_cronograma.vincular_etapa_da_obra(
            orc, grupo_id=int(grupo), etapa_id=int(etapa) if etapa not in (None, "") else None,
        ))

    @action(detail=True, methods=["post"], url_path="destravar")
    def destravar(self, request, pk=None):
        """Devolve o orçamento aprovado ao rascunho — com motivo e rastro.

        O congelamento continua sendo o padrão, e `revisar` continua sendo o
        caminho quando o escopo muda de verdade: ele versiona, que é o que uma
        obra pública exige e o que faz o orçado×realizado ter régua fixa. Este
        verbo é para o outro caso — o erro de digitação encontrado dez minutos
        depois de aprovar —, e por isso tem permissão própria
        (`orcamento.orcamento.destravar`), motivo obrigatório e registro que
        acompanha o documento.
        """
        orcamento = self.get_object()
        try:
            edicao.destravar_orcamento(
                orcamento, motivo=request.data.get("motivo") or "",
                usuario_nome=self._nome_do_usuario(request),
            )
        except edicao.EdicaoInvalida as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc
        return Response(OrcamentoSerializer(orcamento).data)

    @action(detail=True, methods=["post"], url_path="revisar")
    def revisar(self, request, pk=None):
        """Gera a versão seguinte a partir da aprovada (aditivo/supressão)."""
        orcamento = self.get_object()
        tipo = request.data.get("tipo") or RevisaoOrcamento.Tipo.ADITIVO
        motivo = (request.data.get("motivo") or "").strip()
        if not motivo:
            return Response(
                {"motivo": "Informe o motivo da revisão — é o que justifica o aditivo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tipo not in RevisaoOrcamento.Tipo.values:
            return Response({"tipo": f"Tipo inválido. Use um de {RevisaoOrcamento.Tipo.values}."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            nova = planilha.revisar_orcamento(
                orcamento, tipo=tipo, motivo=motivo,
                usuario_nome=self._nome_do_usuario(request),
            )
        except planilha.RevisaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(nova).data, status=status.HTTP_201_CREATED)

    # --- ORC.5b: duplicar, copiar, reprecificar, exportar ---

    @action(detail=True, methods=["post"], url_path="duplicar")
    def duplicar(self, request, pk=None):
        """Clona a planilha para outra obra (ou a mesma), em rascunho v-nova.

        Não é `revisar`: não rebaixa a origem nem registra aditivo. Reaproveitar
        obra parecida é o caso mais comum de partida numa construtora.
        """
        origem = self.get_object()
        obra_id = request.data.get("obra")
        obra = None
        if obra_id:
            obra = origem.obra.__class__.objects.filter(
                tenant_id=self._tenant_id(), pk=obra_id
            ).first()
            if obra is None:
                return Response({"obra": "Obra não encontrada."}, status=status.HTTP_404_NOT_FOUND)

        novo, sem_etapa = duplicacao.duplicar_orcamento(
            origem, obra_destino=obra,
            descricao=(request.data.get("descricao") or "").strip(),
            usuario_nome=self._nome_do_usuario(request),
        )
        return Response(
            duplicacao.resumo_da_duplicata(novo, sem_etapa), status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"], url_path="copiar-itens")
    def copiar_itens(self, request, pk=None):
        """Traz um bloco de linhas de outro orçamento para dentro deste."""
        destino = self.get_object()
        ids = request.data.get("itens") or []
        if not isinstance(ids, list) or not ids:
            return Response(
                {"itens": "Informe a lista de linhas a copiar."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        itens = list(
            ItemOrcado.objects.filter(tenant_id=self._tenant_id(), pk__in=ids)
            .select_related("orcamento")
        )
        if not itens:
            return Response({"itens": "Nenhuma linha encontrada."}, status=status.HTTP_404_NOT_FOUND)

        pai = None
        if request.data.get("pai"):
            pai = ItemOrcado.objects.filter(
                tenant_id=self._tenant_id(), pk=request.data["pai"], orcamento=destino
            ).first()

        try:
            copiadas, sem_etapa = duplicacao.copiar_itens(destino=destino, itens=itens, pai=pai)
        except duplicacao.CopiaInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except planilha.OrcamentoNaoEditavel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        destino.refresh_from_db()
        return Response({
            "copiadas": copiadas,
            "linhas_sem_etapa": sem_etapa,
            "valor_total": str(destino.valor_total),
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="reprecificar")
    def reprecificar(self, request, pk=None):
        """Monta a **prévia** de troca de data-base. Não altera nada ainda."""
        orcamento = self.get_object()
        base = banco = None
        if request.data.get("base_destino"):
            base = BaseReferencial.objects.filter(pk=request.data["base_destino"]).first()
            if base is None:
                return Response({"base_destino": "Publicação não encontrada."}, status=404)
        if request.data.get("banco_destino"):
            banco = BancoPreco.objects.filter(
                tenant_id=self._tenant_id(), pk=request.data["banco_destino"]
            ).first()
            if banco is None:
                return Response({"banco_destino": "Banco não encontrado."}, status=404)

        try:
            lote = servico_reprecificacao.gerar_previa(
                orcamento, base_destino=base, banco_destino=banco,
                somente_ate=request.data.get("somente_ate") or None,
                usuario_nome=self._nome_do_usuario(request),
            )
        except planilha.OrcamentoNaoEditavel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except servico_reprecificacao.ReprecificacaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(servico_reprecificacao.serializar_previa(lote))

    @action(detail=True, methods=["get"], url_path="reprecificacoes")
    def reprecificacoes(self, request, pk=None):
        """Histórico de lotes deste orçamento — é aqui que mora o desfazer."""
        lotes = Reprecificacao.objects.filter(orcamento=self.get_object()).order_by("-criado_em")
        return Response(ReprecificacaoSerializer(lotes, many=True).data)

    @action(detail=True, methods=["get"], url_path="exportar")
    def exportar(self, request, pk=None):
        """XLSX ou PDF das peças da proposta.

        `?formato=xlsx|pdf&nivel=analitico|sintetico&peca=…`

        As peças (ORC.7 acrescentou as cinco últimas): `planilha`, `curva-abc`,
        `cronograma`, `composicao-bdi`, `encargos`, `relacao-insumos`,
        `curva-abc-insumos`, `carta-proposta`. Juntas, são o envelope inteiro —
        até o ORC.6 o módulo emitia a planilha e deixava o orçamentista montar
        os anexos à mão.
        """
        orcamento = self.get_object()
        formato = (request.query_params.get("formato") or "xlsx").lower()
        analitico = (request.query_params.get("nivel") or "analitico").lower() != "sintetico"
        peca = (request.query_params.get("peca") or "planilha").lower()
        XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        try:
            if peca == "curva-abc":
                conteudo = exportacao.curva_abc_xlsx(orcamento, precificacao.curva_abc(orcamento))
                nome = exportacao.nome_do_arquivo(orcamento, sufixo="curva-abc", extensao="xlsx")
                tipo = XLSX
            elif peca == "composicao-bdi":
                conteudo = exportacao.composicao_bdi_xlsx(orcamento)
                nome = exportacao.nome_do_arquivo(orcamento, sufixo="composicao-bdi", extensao="xlsx")
                tipo = XLSX
            elif peca == "encargos":
                conteudo = exportacao.quadro_encargos_xlsx(orcamento)
                nome = exportacao.nome_do_arquivo(orcamento, sufixo="encargos-sociais", extensao="xlsx")
                tipo = XLSX
            elif peca == "relacao-insumos":
                conteudo = exportacao.relacao_insumos_xlsx(
                    orcamento, servico_insumos.relacao_de_insumos(orcamento),
                )
                nome = exportacao.nome_do_arquivo(orcamento, sufixo="relacao-insumos", extensao="xlsx")
                tipo = XLSX
            elif peca == "curva-abc-insumos":
                conteudo = exportacao.curva_abc_insumos_xlsx(
                    orcamento, servico_insumos.curva_abc_insumos(orcamento),
                )
                nome = exportacao.nome_do_arquivo(orcamento, sufixo="curva-abc-insumos", extensao="xlsx")
                tipo = XLSX
            elif peca == "carta-proposta":
                # Sempre PDF: é peça de assinar, e assinar planilha editável não
                # faz sentido. O `?formato=` é ignorado aqui de propósito.
                conteudo = exportacao.carta_proposta_pdf(orcamento, dados=request.query_params.dict())
                nome = exportacao.nome_do_arquivo(orcamento, sufixo="carta-proposta", extensao="pdf")
                tipo = "application/pdf"
            elif peca == "cronograma":
                dados = servico_cronograma.grade(orcamento)
                conteudo = exportacao.cronograma_xlsx(orcamento, dados)
                nome = exportacao.nome_do_arquivo(orcamento, sufixo="cronograma", extensao="xlsx")
                tipo = XLSX
            elif formato == "pdf":
                conteudo = exportacao.planilha_pdf(orcamento, analitico=analitico)
                nome = exportacao.nome_do_arquivo(
                    orcamento, sufixo="analitica" if analitico else "sintetica", extensao="pdf",
                )
                tipo = "application/pdf"
            else:
                conteudo = exportacao.planilha_xlsx(orcamento, analitico=analitico)
                nome = exportacao.nome_do_arquivo(
                    orcamento, sufixo="analitica" if analitico else "sintetica", extensao="xlsx",
                )
                tipo = XLSX
        except exportacao.ExportacaoIndisponivel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_501_NOT_IMPLEMENTED)

        from django.http import HttpResponse

        resposta = HttpResponse(conteudo, content_type=tipo)
        resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
        return resposta

    @staticmethod
    def _nome_do_usuario(request) -> str:
        user = getattr(request, "user", None)
        return getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "") or ""


class ItemOrcadoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """As linhas da planilha.

    Toda escrita recalcula o orçamento — a alternativa (recalcular só quando o
    usuário pedir) deixaria a planilha exibindo um total que não corresponde às
    linhas, que é o pior defeito possível num sistema de orçamento.
    """

    queryset = ItemOrcado.objects.select_related("orcamento", "etapa", "item").all()
    serializer_class = ItemOrcadoSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["orcamento", "pai", "etapa", "item", "tipo_linha"]
    search_fields = ["descricao", "codigo_referencia", "codigo_eap"]
    ordering_fields = ["codigo_eap", "ordem", "total_custo_direto"]
    required_resource = "orcamento.item"
    action_permission_map = {
        "memoria": "orcamento.item.view",
        "composicao_natureza": "orcamento.item.view",
        "memoria_quantitativo": "orcamento.item.view",
        "preco_real": "orcamento.item.view",
        "explodir": "orcamento.item.edit",
        "aplicar_preco_real": "orcamento.item.edit",
        "do_catalogo": "orcamento.item.edit",
        # ORC.10 — todos os verbos de edição estrutural pedem a mesma permissão
        # de escrita de linha. Não ganham permissão própria de propósito: quem
        # pode mudar a quantidade de um item já pode mudar o total da planilha,
        # e inventar `orcamento.item.mover` daria a falsa impressão de que
        # arrastar é mais perigoso que digitar.
        "mover": "orcamento.item.edit",
        "duplicar": "orcamento.item.edit",
        "excluir_lote": "orcamento.item.edit",
        "restaurar": "orcamento.item.edit",
        "aplicar_percentual": "orcamento.item.edit",
        "arredondar": "orcamento.item.edit",
        "substituir_texto": "orcamento.item.edit",
        "recompor": "orcamento.item.edit",
        # Promover é escrita no **banco da empresa**, não na planilha: é a
        # permissão do banco que manda, pela mesma régua que separa "orçar" de
        # "curar preço" desde a ORC.9.
        "promover_composicao": "orcamento.banco.edit",
    }

    def perform_create(self, serializer):
        # `super()` é quem injeta o `tenant_id` (TenantScopedViewSetMixin) —
        # salvar direto aqui gravaria a linha sem tenant e a RLS a rejeitaria.
        _exigir_editavel(serializer.validated_data.get("orcamento"))
        super().perform_create(serializer)
        planilha.recalcular_orcamento(serializer.instance.orcamento)

    def perform_update(self, serializer):
        _exigir_editavel(serializer.instance.orcamento)
        super().perform_update(serializer)
        planilha.recalcular_orcamento(serializer.instance.orcamento)

    def perform_destroy(self, instance):
        orcamento = instance.orcamento
        _exigir_editavel(orcamento)
        instance.delete()
        planilha.recalcular_orcamento(orcamento)

    @action(detail=False, methods=["post"], url_path="do-catalogo")
    def do_catalogo(self, request):
        """Cria a linha a partir de um `catalogo.Item`, **tirando o snapshot**.

        É o caminho normal de montar planilha: escolher o item do catálogo (que
        veio da SINAPI pela adoção, ou é próprio da empresa) e informar a
        quantidade. Descrição, unidade e código de referência são copiados
        agora e congelam aqui — mudar o item no catálogo depois não mexe neste
        orçamento.

        **De onde sai o preço (ORC.10a).** `base` é a publicação que estava
        aberta no seletor quando o item foi escolhido, e é dela que o preço vem
        — não da publicação do cabeçalho. O cliente manda o que pescou; sem
        `base`, cai na do orçamento, como era antes. Isso é o que permite
        planilha com linhas de fontes diferentes (uma SINAPI, uma ORSE, uma de
        preço digitado), cada uma carregando a sua data-base, que é como o
        Arquimedes e os bancos de preço do setor funcionam.

        Nunca inventamos preço: sem preço conhecido a linha nasce zerada e
        visível como pendência, em vez de com um número plausível.
        """
        orcamento_id = request.data.get("orcamento")
        item_id = request.data.get("item")
        base_id = request.data.get("base")
        orcamento = Orcamento.objects.filter(
            tenant_id=self._tenant_id(), pk=orcamento_id
        ).select_related("base_referencial").first()
        if orcamento is None:
            return Response({"orcamento": "Orçamento não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        _exigir_editavel(orcamento)

        item = Item.objects.filter(tenant_id=self._tenant_id(), pk=item_id).first()
        if item is None:
            return Response({"item": "Item não encontrado no catálogo."}, status=status.HTTP_404_NOT_FOUND)

        # A base referencial é pública e sem tenant (§11.1), então não há o que
        # escopar aqui — só conferir que o id existe. Id inválido vira 400 e não
        # silêncio: se o cliente disse de onde pescou, errar o endereço não pode
        # virar uma linha zerada sem explicação, que é o defeito que a ORC.10a
        # está justamente fechando.
        base = None
        if base_id not in (None, ""):
            base = BaseReferencial.objects.filter(pk=base_id).first()
            if base is None:
                return Response(
                    {"base": "Publicação não encontrada."}, status=status.HTTP_400_BAD_REQUEST,
                )

        linha = services.linha_a_partir_do_item(
            orcamento=orcamento,
            item=item,
            quantidade=request.data.get("quantidade") or 0,
            custo_unitario=request.data.get("custo_unitario"),
            pai_id=request.data.get("pai"),
            etapa_id=request.data.get("etapa"),
            ordem=request.data.get("ordem") or 0,
            base=base,
        )
        planilha.recalcular_orcamento(orcamento)
        linha.refresh_from_db()
        return Response(ItemOrcadoSerializer(linha).data, status=status.HTTP_201_CREATED)


    # --- ORC.10b/d — os verbos de edição estrutural ------------------------

    def _orcamento_do_pedido(self, request):
        """Resolve e escopa o orçamento que o lote vai mexer.

        Os verbos de lote são `detail=False` e recebem os ids no corpo, então o
        escopo por tenant não vem de graça do `get_object()` — é preciso pedir
        explicitamente, senão um id de outra empresa entraria pelo payload.
        """
        orcamento = Orcamento.objects.filter(
            tenant_id=self._tenant_id(), pk=request.data.get("orcamento"),
        ).first()
        if orcamento is None:
            raise exceptions.NotFound("Orçamento não encontrado.")
        return orcamento

    @staticmethod
    def _responder_edicao(fn, *args, **kwargs):
        """Traduz as duas exceções de domínio para o vocabulário HTTP.

        `EdicaoInvalida` é 400 (o pedido não faz sentido na árvore) e
        `OrcamentoNaoEditavel` é 409 (o pedido faz sentido, o documento é que
        está fechado) — a mesma distinção que o módulo já fazia na ORC.1.
        """
        try:
            return fn(*args, **kwargs)
        except edicao.EdicaoInvalida as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc
        except planilha.OrcamentoNaoEditavel as exc:
            raise DocumentoFechado(str(exc)) from exc

    @action(detail=False, methods=["post"], url_path="mover")
    def mover(self, request):
        """Arrastar, indentar, desindentar e reordenar — com a subárvore junto.

        Corpo: `orcamento`, `itens` e **ou** `operacao`
        (`indentar`/`desindentar`/`cima`/`baixo`) **ou** `pai` + `posicao`.
        """
        orcamento = self._orcamento_do_pedido(request)
        movidas = self._responder_edicao(
            edicao.mover, orcamento, request.data.get("itens") or [],
            operacao=request.data.get("operacao") or None,
            pai_id=request.data.get("pai"),
            posicao=request.data.get("posicao"),
        )
        return Response({"movidas": movidas})

    @action(detail=False, methods=["post"], url_path="duplicar")
    def duplicar(self, request):
        """Copia as linhas logo abaixo das originais, com composição e medição."""
        orcamento = self._orcamento_do_pedido(request)
        novos = self._responder_edicao(
            edicao.duplicar, orcamento, request.data.get("itens") or [],
        )
        return Response({"criadas": len(novos), "itens": novos}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="excluir-lote")
    def excluir_lote(self, request):
        """Exclui a seleção e devolve o material do Ctrl+Z em `desfazer`."""
        orcamento = self._orcamento_do_pedido(request)
        resultado = self._responder_edicao(
            edicao.excluir, orcamento, request.data.get("itens") or [],
        )
        return Response(resultado)

    @action(detail=False, methods=["post"], url_path="restaurar")
    def restaurar(self, request):
        """Recria o que `excluir-lote` devolveu — o outro lado do desfazer."""
        orcamento = self._orcamento_do_pedido(request)
        criados = self._responder_edicao(
            edicao.restaurar, orcamento, request.data.get("linhas") or [],
        )
        return Response({"restauradas": len(criados), "itens": criados})

    @action(detail=False, methods=["post"], url_path="aplicar-percentual")
    def aplicar_percentual(self, request):
        """±x% sobre custo unitário ou quantidade da seleção."""
        orcamento = self._orcamento_do_pedido(request)
        afetadas = self._responder_edicao(
            edicao.aplicar_percentual, orcamento, request.data.get("itens") or [],
            request.data.get("percentual") or 0,
            campo=request.data.get("campo") or "custo_unitario",
        )
        return Response({"afetadas": afetadas})

    @action(detail=False, methods=["post"], url_path="arredondar")
    def arredondar(self, request):
        """Arredonda quantidade ou custo da seleção para N casas."""
        orcamento = self._orcamento_do_pedido(request)
        afetadas = self._responder_edicao(
            edicao.arredondar, orcamento, request.data.get("itens") or [],
            request.data.get("casas", 2), campo=request.data.get("campo") or "quantidade",
        )
        return Response({"afetadas": afetadas})

    @action(detail=False, methods=["post"], url_path="substituir-texto")
    def substituir_texto(self, request):
        """Localizar e substituir na descrição — só nela, por desenho (ORC.10f)."""
        orcamento = self._orcamento_do_pedido(request)
        afetadas = self._responder_edicao(
            edicao.substituir_texto, orcamento,
            request.data.get("procurar") or "", request.data.get("trocar_por") or "",
            ids=request.data.get("itens") or None,
        )
        return Response({"afetadas": afetadas})

    # --- ORC.10c — a composição editada vira composição de banco -----------

    @action(detail=True, methods=["post"], url_path="recompor")
    def recompor(self, request, pk=None):
        """Refaz o custo unitário a partir dos insumos que a linha tem agora."""
        linha = self.get_object()
        _exigir_editavel(linha.orcamento)
        total = self._responder_edicao(edicao.recompor_linha, linha)
        linha.refresh_from_db()
        return Response({"custo_unitario": str(total), **precificacao.memoria_de_calculo(linha)})

    @action(detail=True, methods=["post"], url_path="promover-composicao")
    def promover_composicao(self, request, pk=None):
        """Publica a composição da linha num banco da empresa — o reuso explícito.

        Sem `banco` no corpo, vai para o banco **da obra**, que é onde a edição
        já grava sozinha; com `banco`, vai para o acervo que o orçamentista
        escolheu, que é como uma composição ajustada numa obra vira régua da
        empresa.
        """
        linha = self.get_object()
        banco_id = request.data.get("banco")
        if banco_id in (None, ""):
            banco = edicao.banco_da_obra(linha.orcamento)
        else:
            banco = BancoPreco.objects.filter(
                tenant_id=self._tenant_id(), pk=banco_id,
            ).first()
            if banco is None:
                raise exceptions.NotFound("Banco de preço não encontrado.")
        composicao = self._responder_edicao(edicao.promover_para_banco, linha, banco)
        return Response({
            "banco": banco.banco_id, "banco_nome": banco.nome,
            "item_banco": composicao.item_banco_id, "codigo": composicao.codigo,
        }, status=status.HTTP_201_CREATED)

    # --- ORC.2: composição analítica ---

    @action(detail=True, methods=["post"], url_path="explodir")
    def explodir(self, request, pk=None):
        """Abre a composição do item em insumos e refaz o custo unitário.

        Depois disto o preço da linha deixa de ser digitado e passa a ser a
        soma dos insumos — é o que torna o orçamento auditável.
        """
        linha = self.get_object()
        _exigir_editavel(linha.orcamento)
        atualizar = request.data.get("atualizar_custo", True) not in (False, "false", "0", 0)
        try:
            precificacao.explodir_item(linha, atualizar_custo=atualizar)
        except precificacao.ComposicaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        planilha.recalcular_orcamento(linha.orcamento)
        linha.refresh_from_db()
        return Response(precificacao.memoria_de_calculo(linha))

    @action(detail=True, methods=["get"], url_path="memoria")
    def memoria(self, request, pk=None):
        """A memória de cálculo da linha: insumos, pesos e resumo por categoria."""
        return Response(precificacao.memoria_de_calculo(self.get_object()))

    # --- ORC.7: composição separada e memória do quantitativo ---

    @action(detail=True, methods=["get"], url_path="composicao-natureza")
    def composicao_natureza(self, request, pk=None):
        """A composição da linha **separada em material, mão de obra e equipamento**.

        É como ORSE e Arquimedes imprimem a analítica, e não é estética: as três
        naturezas têm regimes diferentes (encargo só incide sobre mão de obra,
        material entra na relação de compra, equipamento admite BDI diferenciado
        pelo TCU). Numa coluna só, some exatamente a informação que decide.
        """
        return Response(servico_insumos.composicao_por_natureza(self.get_object()))

    @action(detail=True, methods=["get"], url_path="memoria-quantitativo")
    def memoria_quantitativo(self, request, pk=None):
        """As parciais que somam a quantidade, com o par somado × subtraído."""
        return Response(quantitativos.memoria_do_quantitativo(self.get_object()))

    @action(detail=True, methods=["get"], url_path="preco-real")
    def preco_real(self, request, pk=None):
        """Preço de tabela × o que a empresa pagou (SCM) × o que carrega (SIL).

        A integração fica visível aqui: a mesma tela que orça mostra o histórico
        real dos outros dois módulos, porque o item é o mesmo `catalogo.Item`.
        """
        linha = self.get_object()
        if linha.item_id is None:
            return Response(
                {"detail": "A linha não aponta item do catálogo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        dados = precificacao.preco_real_do_item(self._tenant_id(), linha.item_id)
        dados["orcado"] = {
            "custo_unitario": str(linha.custo_unitario),
            "fonte": linha.fonte_referencia or "propria",
            "data_base": linha.data_base_preco,
        }
        return Response(dados)

    @action(detail=True, methods=["post"], url_path="aplicar-preco-real")
    def aplicar_preco_real(self, request, pk=None):
        """Troca o preço de tabela pelo histórico real (`origem`: scm | sil)."""
        linha = self.get_object()
        _exigir_editavel(linha.orcamento)
        origem = request.data.get("origem") or "scm"
        if origem not in ("scm", "sil"):
            return Response({"origem": "Use 'scm' ou 'sil'."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            precificacao.aplicar_preco_real(linha, origem=origem)
        except precificacao.ComposicaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        planilha.recalcular_orcamento(linha.orcamento)
        linha.refresh_from_db()
        return Response(ItemOrcadoSerializer(linha).data)



class ItemOrcadoInsumoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """A composição de uma linha — ORC.10c.

    **Por que isto não existia.** A memória de cálculo nasceu na ORC.2 como
    saída da explosão: o catálogo dizia a composição, o módulo a achatava em
    folhas e gravava. Ler de volta nunca fez falta porque não havia como
    escrever. O resultado é que o preço de um serviço só podia ser aceito
    inteiro ou digitado por cima — e ajustar o coeficiente que estava errado,
    que é o gesto mais comum de quem orça no Arquimedes, não tinha caminho.

    **Toda escrita recompõe.** Mexer num coeficiente sem refazer o custo
    unitário deixaria a composição somando um número e a linha exibindo outro,
    que é a divergência que uma memória de cálculo existe para impedir. O
    recompor também espelha a composição no banco da obra (ver
    `edicao.banco_da_obra`) e recalcula a planilha.
    """

    queryset = ItemOrcadoInsumo.objects.select_related("item_orcado", "item").all()
    serializer_class = ItemOrcadoInsumoSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["item_orcado", "categoria", "item"]
    search_fields = ["descricao"]
    ordering_fields = ["categoria", "descricao", "custo_no_item"]
    required_resource = "orcamento.item"

    def _linha_do(self, serializer_ou_instancia):
        alvo = getattr(serializer_ou_instancia, "instance", serializer_ou_instancia)
        return alvo.item_orcado

    def perform_create(self, serializer):
        _exigir_editavel(serializer.validated_data["item_orcado"].orcamento)
        super().perform_create(serializer)
        edicao.recompor_linha(self._linha_do(serializer))

    def perform_update(self, serializer):
        _exigir_editavel(serializer.instance.item_orcado.orcamento)
        super().perform_update(serializer)
        edicao.recompor_linha(self._linha_do(serializer))

    def perform_destroy(self, instance):
        linha = instance.item_orcado
        _exigir_editavel(linha.orcamento)
        instance.delete()
        edicao.recompor_linha(linha)

class ComposicaoBDIViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """BDI analítico (Acórdão 2622/2013-TCU).

    Toda escrita passa por `precificacao.salvar_bdi`, que recalcula o
    percentual, garante um único `padrao` por orçamento e propaga o número para
    o cabeçalho — o percentual jamais é aceito do cliente.
    """

    queryset = ComposicaoBDI.objects.select_related("orcamento").all()
    serializer_class = ComposicaoBDISerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["orcamento", "padrao"]
    required_resource = "orcamento.orcamento"

    def perform_create(self, serializer):
        _exigir_editavel(serializer.validated_data.get("orcamento"))
        super().perform_create(serializer)
        self._salvar(serializer.instance)

    def perform_update(self, serializer):
        _exigir_editavel(serializer.instance.orcamento)
        super().perform_update(serializer)
        self._salvar(serializer.instance)

    @staticmethod
    def _salvar(composicao):
        try:
            precificacao.salvar_bdi(composicao)
        except precificacao.ComposicaoInvalida as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc
        planilha.recalcular_orcamento(composicao.orcamento)


class ParcelaEtapaViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Células do cronograma — a edição fina, célula a célula.

    Cada escrita reconverte percentuais em dinheiro e passa a curva da etapa
    para **manual**: a célula ajustada à mão não pode ser apagada pela próxima
    mudança de data. Não travamos a soma em 100% — um cronograma em construção
    passa por estados inconsistentes, e a conferência é informada em
    `cronograma/`, não imposta na digitação.
    """

    queryset = ParcelaEtapa.objects.select_related("orcamento", "grupo").all()
    serializer_class = ParcelaEtapaSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["orcamento", "grupo", "competencia"]
    ordering_fields = ["competencia", "percentual"]
    required_resource = "orcamento.item"

    @staticmethod
    def _exigir_cronograma_editavel(orcamento):
        try:
            servico_cronograma.exigir_cronograma_editavel(orcamento)
        except servico_cronograma.CronogramaFechado as exc:
            raise DocumentoFechado(str(exc)) from exc

    def _depois(self, orcamento, grupo_id):
        servico_cronograma.marcar_manual(orcamento, grupo_id)
        servico_cronograma.recalcular_parcelas(orcamento)
        servico_cronograma.carimbar(orcamento)

    def perform_create(self, serializer):
        self._exigir_cronograma_editavel(serializer.validated_data.get("orcamento"))
        super().perform_create(serializer)
        self._depois(serializer.instance.orcamento, serializer.instance.grupo_id)

    def perform_update(self, serializer):
        self._exigir_cronograma_editavel(serializer.instance.orcamento)
        super().perform_update(serializer)
        self._depois(serializer.instance.orcamento, serializer.instance.grupo_id)

    def perform_destroy(self, instance):
        orcamento, grupo_id = instance.orcamento, instance.grupo_id
        self._exigir_cronograma_editavel(orcamento)
        instance.delete()
        self._depois(orcamento, grupo_id)


# ---------------------------------------------------------------------------
# ORC.4 — paramétrico e NBR 12721
# ---------------------------------------------------------------------------


class ParametroObraViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Orçamento paramétrico da viabilidade (área equivalente × CUB)."""

    queryset = ParametroObra.objects.select_related("obra").all()
    serializer_class = ParametroObraSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["obra", "projeto_padrao"]
    ordering_fields = ["criado_em", "custo_estimado"]
    required_resource = "orcamento.orcamento"
    action_permission_map = {"comparar": "orcamento.relatorio.view"}

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._calcular(serializer.instance)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._calcular(serializer.instance)

    def _calcular(self, parametro):
        sincronizar = self.request.data.get("sincronizar_area", False) in (True, "true", "1", 1)
        nbr12721.calcular_parametrico(parametro, sincronizar_area=sincronizar)

    @action(detail=True, methods=["get"], url_path="comparar")
    def comparar(self, request, pk=None):
        """Paramétrico × analítico aprovado — o que calibra a próxima estimativa."""
        return Response(nbr12721.comparar_parametrico_com_analitico(self.get_object()))


class PavimentoObraViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Pavimentos e suas áreas — a base do Quadro I."""

    queryset = PavimentoObra.objects.select_related("obra").all()
    serializer_class = PavimentoObraSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["obra"]
    ordering_fields = ["ordem", "nome"]
    required_resource = "orcamento.item"


class UnidadeAutonomaViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Unidades autônomas — base dos Quadros II e IV."""

    queryset = UnidadeAutonoma.objects.select_related("obra", "pavimento").all()
    serializer_class = UnidadeAutonomaSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["obra", "pavimento", "tipo"]
    search_fields = ["designacao", "tipo"]
    ordering_fields = ["designacao", "coeficiente_proporcionalidade"]
    required_resource = "orcamento.item"


class MemorialNBRViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Linhas dos quadros descritivos V a VIII."""

    queryset = MemorialNBR.objects.select_related("obra").all()
    serializer_class = MemorialNBRSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["obra", "quadro"]
    search_fields = ["dependencia", "descricao"]
    ordering_fields = ["quadro", "ordem"]
    required_resource = "orcamento.item"


class QuadrosNBRView(views.APIView):
    """Os oito quadros da NBR 12721 de uma obra — o dossiê de incorporação.

    `GET /api/orcamento/nbr12721/?obra=<id>[&quadro=I|II|III|IV|v|vi|vii|viii]`
    `POST …/?obra=<id>` com `{"acao": "coeficientes"|"ratear"}` recalcula.

    Uma `APIView` e não um ViewSet porque isto não é um recurso CRUD: é uma
    **leitura composta** sobre pavimentos, unidades e a base de custo. Os
    recursos que a alimentam têm seus próprios endpoints.
    """

    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = MODULO
    # Chaves do contrato do `RequirePermission`: "view" p/ métodos seguros,
    # "write" para os demais.
    permission_map = {"view": "orcamento.relatorio.view", "write": "orcamento.item.edit"}

    def _obra(self, request):
        obra = request.query_params.get("obra") or request.data.get("obra")
        if not obra:
            raise exceptions.ValidationError({"obra": "Informe a obra."})
        return obra

    @staticmethod
    def _tenant(request):
        return getattr(getattr(request, "user", None), "tenant_id", None)

    def _parametro(self, tenant_id, obra_id):
        """Paramétrico mais recente da obra — base de custo quando não há
        planilha analítica aprovada."""
        return (
            ParametroObra.objects.filter(tenant_id=tenant_id, obra_id=obra_id)
            .order_by("-criado_em").first()
        )

    def get(self, request):
        tenant_id, obra_id = self._tenant(request), self._obra(request)
        parametro = self._parametro(tenant_id, obra_id)
        quadro = (request.query_params.get("quadro") or "").strip()

        try:
            if not quadro:
                return Response(nbr12721.dossie(tenant_id, obra_id, parametro=parametro))
            if quadro == "I":
                return Response(nbr12721.quadro_i(tenant_id, obra_id))
            if quadro == "II":
                return Response(nbr12721.quadro_ii(tenant_id, obra_id))
            if quadro == "III":
                return Response(nbr12721.quadro_iii(tenant_id, obra_id, parametro=parametro))
            if quadro == "IV":
                return Response(
                    nbr12721.quadro_iv(tenant_id, obra_id, parametro=parametro, gravar=False)
                )
            if quadro.lower() in MemorialNBR.Quadro.values:
                return Response(
                    nbr12721.quadros_descritivos(tenant_id, obra_id, quadro.lower())
                )
        except nbr12721.DadosInsuficientes as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            {"quadro": f"Use I, II, III, IV ou {MemorialNBR.Quadro.values}."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def post(self, request):
        tenant_id, obra_id = self._tenant(request), self._obra(request)
        acao = request.data.get("acao")
        try:
            if acao == "coeficientes":
                replicar = request.data.get("replicar_na_fracao_ideal", False) in (True, "true", "1", 1)
                nbr12721.calcular_coeficientes(
                    tenant_id, obra_id, replicar_na_fracao_ideal=replicar
                )
                return Response(nbr12721.quadro_ii(tenant_id, obra_id))
            if acao == "ratear":
                parametro = self._parametro(tenant_id, obra_id)
                return Response(nbr12721.quadro_iv(tenant_id, obra_id, parametro=parametro))
        except nbr12721.DadosInsuficientes as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            {"acao": "Use 'coeficientes' ou 'ratear'."}, status=status.HTTP_400_BAD_REQUEST
        )


class RevisaoOrcamentoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Histórico de aditivos/supressões — read-only.

    A revisão nasce como **efeito** de `orcamentos/{id}/revisar/`, nunca por
    POST direto: um registro de revisão sem a versão nova correspondente seria
    rastro falso.
    """

    queryset = RevisaoOrcamento.objects.select_related("orcamento", "orcamento_anterior").all()
    serializer_class = RevisaoOrcamentoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["orcamento", "tipo", "orcamento__obra"]
    ordering_fields = ["criado_em", "numero"]
    required_permission = "orcamento.orcamento.view"


# ---------------------------------------------------------------------------
# ORC.5b — bancos da empresa, importação e reprecificação
# ---------------------------------------------------------------------------
#
# **A condição do §12.1 se cumpriu (20/08/2026).** A nota original dizia: manter
# o banco de preço é a mesma mão que monta a planilha, e permissão nova custa
# rebuild da imagem da IAM + re-seed — "se na prática 'quem cuida do banco de
# preço' virar um papel distinto de 'quem orça', aí sim vale criar
# `orcamento.banco.*`". Virou, por decisão do dono: a régua de preço da casa é
# função específica, como quem cria e exclui cliente. Daí a família nova.
#
# Ler o banco é `orcamento.banco.view`; mexer nele (item, pasta, coeficiente,
# trava, importação) é `orcamento.banco.edit`. Trazer preço **para dentro do
# catálogo** continua sendo `orcamento.base.adotar`: é escrita no cadastro-
# mestre, não no banco, e quem pode uma coisa não precisa poder a outra. A
# persona `orcamentista` nasce com as duas — quem quiser separar tira a linha
# do papel de fábrica em `/app/admin/papeis`.


class BancoPrecoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Bancos de preço **da empresa** — o espelho tenant-scoped da base pública."""

    queryset = BancoPreco.objects.select_related("obra").all()
    serializer_class = BancoPrecoSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["fonte", "uf", "obra", "travado", "ativo", "origem"]
    search_fields = ["nome", "descricao"]
    ordering_fields = ["nome", "mes_referencia", "total_itens", "criado_em"]
    required_resource = "orcamento.banco"
    action_permission_map = {
        "create": "orcamento.banco.edit",
        "update": "orcamento.banco.edit",
        "partial_update": "orcamento.banco.edit",
        "destroy": "orcamento.banco.edit",
        "travar": "orcamento.banco.edit",
        "destravar": "orcamento.banco.edit",
        "adotar_lote": "orcamento.base.adotar",
        "copiar_da_base": "orcamento.base.adotar",
        "resumo": "orcamento.banco.view",
    }

    def perform_update(self, serializer):
        banco = self.get_object()
        if banco.travado:
            raise exceptions.ValidationError(
                {"detail": f'O banco "{banco.nome}" está travado. Destrave para editar.'}
            )
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.travado:
            raise exceptions.ValidationError(
                {"detail": "Banco travado não é excluído — destrave primeiro, de propósito."}
            )
        instance.delete()

    @action(detail=False, methods=["get"], url_path="resumo")
    def resumo(self, request):
        return Response(servico_bancos.resumo(self._tenant_id()))

    @action(detail=True, methods=["post"], url_path="travar")
    def travar(self, request, pk=None):
        banco = servico_bancos.travar(
            self.get_object(), usuario_nome=self._usuario(request)
        )
        return Response(self.get_serializer(banco).data)

    @action(detail=True, methods=["post"], url_path="destravar")
    def destravar(self, request, pk=None):
        banco = servico_bancos.destravar(
            self.get_object(), usuario_nome=self._usuario(request)
        )
        return Response(self.get_serializer(banco).data)

    @action(detail=True, methods=["post"], url_path="adotar-lote")
    def adotar_lote(self, request, pk=None):
        """Adota itens deste banco no catálogo da empresa."""
        banco = self.get_object()
        ids = request.data.get("itens") or []
        itens = list(ItemBancoPreco.objects.filter(
            tenant_id=self._tenant_id(), banco=banco, pk__in=ids
        ).select_related("banco"))
        if not itens:
            return Response({"itens": "Nenhum item encontrado."}, status=status.HTTP_400_BAD_REQUEST)
        forcar = request.data.get("forcar", False) not in (False, "false", "0", 0, None, "")
        try:
            resultado = servico_bancos.adotar_muitos(itens, self._tenant_id(), forcar=forcar)
        except servico_bancos.AdocaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "adotados": [i.pk for i in resultado.adotados],
            "criados": len(resultado.adotados),
            "divergentes": resultado.divergentes,
        })

    @action(detail=True, methods=["post"], url_path="copiar-da-base")
    def copiar_da_base(self, request, pk=None):
        """Copia itens da SINAPI/ORSE para dentro deste banco, **editáveis**.

        O caminho pedido pelo dono do produto: ajustar coeficiente sem tocar na
        base oficial, que segue read-only.
        """
        banco = self.get_object()
        ids = request.data.get("referencias") or []
        referencias = list(
            InsumoReferencia.objects.filter(pk__in=ids).select_related("base")
        )
        if not referencias:
            return Response(
                {"referencias": "Nenhuma referência encontrada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            criados = servico_bancos.copiar_da_base_publica(
                referencias, banco_destino=banco,
                com_composicao=request.data.get("com_composicao", True) is not False,
            )
        except servico_bancos.BancoTravado as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        banco.refresh_from_db()
        return Response({"criados": criados, "total_itens": banco.total_itens})

    @staticmethod
    def _usuario(request) -> str:
        user = getattr(request, "user", None)
        return getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "") or ""


# ---------------------------------------------------------------------------
# ORC.7 — encargos analíticos, memória do quantitativo e reajuste
# ---------------------------------------------------------------------------


class ComposicaoEncargosViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """O quadro de encargos sociais (grupos A/B/C/D).

    Espelha o `ComposicaoBDIViewSet` de propósito: são as duas peças analíticas
    que compõem o preço, e um orçamentista que aprendeu uma tela já sabe a
    outra. Toda escrita passa por `encargos.salvar_encargos`, que deriva o grupo
    D, mantém um único `padrao` e propaga o percentual para o cabeçalho.

    Reusa `orcamento.orcamento.edit` — encargo é parâmetro do orçamento, como o
    BDI, e não justificou permissão nova (§12.1 da planta).
    """

    queryset = ComposicaoEncargos.objects.select_related("orcamento").prefetch_related("rubricas").all()
    serializer_class = ComposicaoEncargosSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["orcamento", "padrao", "tipo_mao_de_obra", "regime"]
    required_resource = "orcamento.orcamento"
    action_permission_map = {
        "quadro": "orcamento.orcamento.view",
        "do_modelo": "orcamento.orcamento.edit",
        "recalcular": "orcamento.orcamento.edit",
    }

    def perform_create(self, serializer):
        _exigir_editavel(serializer.validated_data.get("orcamento"))
        super().perform_create(serializer)
        self._salvar(serializer.instance)

    def perform_update(self, serializer):
        _exigir_editavel(serializer.instance.orcamento)
        super().perform_update(serializer)
        self._salvar(serializer.instance)

    def perform_destroy(self, instance):
        _exigir_editavel(instance.orcamento)
        instance.delete()

    @staticmethod
    def _salvar(composicao):
        try:
            encargos.salvar_encargos(composicao)
        except encargos.QuadroInvalido as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc

    @action(detail=False, methods=["post"], url_path="do-modelo")
    def do_modelo(self, request):
        """Cria o quadro já preenchido com o modelo de partida.

        Sem isto o usuário digitaria trinta rubricas para chegar onde toda
        publicação já chega — e digitaria com erro no grupo D, que é derivado.
        As alíquotas do grupo A são lei e entram prontas; B e C entram como
        valores de partida a conferir com a publicação vigente.
        """
        orcamento = Orcamento.objects.filter(
            tenant_id=self._tenant_id(), pk=request.data.get("orcamento")
        ).first()
        if orcamento is None:
            return Response({"orcamento": "Orçamento não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        _exigir_editavel(orcamento)

        tipo = request.data.get("tipo_mao_de_obra") or ComposicaoEncargos.TipoMaoDeObra.HORISTA
        if tipo not in ComposicaoEncargos.TipoMaoDeObra.values:
            return Response(
                {"tipo_mao_de_obra": "Use 'horista' ou 'mensalista'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if ComposicaoEncargos.objects.filter(orcamento=orcamento, tipo_mao_de_obra=tipo).exists():
            return Response(
                {"detail": f"Este orçamento já tem quadro de {tipo}."},
                status=status.HTTP_409_CONFLICT,
            )

        composicao = encargos.criar_quadro_padrao(
            orcamento, tipo=tipo, regime=request.data.get("regime") or None,
        )
        return Response(self.get_serializer(composicao).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="quadro")
    def quadro(self, request, pk=None):
        """O quadro pronto para a tela e para o PDF, com a conta do grupo D."""
        return Response(encargos.quadro(self.get_object()))

    @action(detail=True, methods=["post"], url_path="recalcular")
    def recalcular(self, request, pk=None):
        """Refaz as derivadas depois de editar rubricas em lote."""
        composicao = self.get_object()
        _exigir_editavel(composicao.orcamento)
        self._salvar(composicao)
        composicao.refresh_from_db()
        return Response(encargos.quadro(composicao))


class RubricaEncargosViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """As linhas do quadro. Escrever aqui recalcula o quadro inteiro.

    Tem de recalcular: mexer numa alíquota do grupo A muda a reincidência A×B do
    grupo D, e um quadro que só atualiza o que foi digitado passa a somar errado
    sem avisar.
    """

    queryset = RubricaEncargos.objects.select_related("composicao", "composicao__orcamento").all()
    serializer_class = RubricaEncargosSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["composicao", "grupo"]
    ordering_fields = ["grupo", "ordem"]
    required_resource = "orcamento.orcamento"

    def perform_create(self, serializer):
        _exigir_editavel(serializer.validated_data["composicao"].orcamento)
        super().perform_create(serializer)
        self._recalcular(serializer.instance.composicao)

    def perform_update(self, serializer):
        _exigir_editavel(serializer.instance.composicao.orcamento)
        super().perform_update(serializer)
        self._recalcular(serializer.instance.composicao)

    def perform_destroy(self, instance):
        composicao = instance.composicao
        _exigir_editavel(composicao.orcamento)
        instance.delete()
        self._recalcular(composicao)

    @staticmethod
    def _recalcular(composicao):
        try:
            encargos.salvar_encargos(composicao)
        except encargos.QuadroInvalido as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc


class LinhaMedicaoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """As parciais da memória do quantitativo.

    Toda escrita recalcula o total da parcial e **sincroniza a quantidade da
    linha-pai**, que passa a ser derivada. É a mesma disciplina que o
    `ItemOrcadoViewSet` tem com o recálculo do orçamento: deixar a soma para
    quando o usuário pedir exibiria uma quantidade que não corresponde às
    parciais logo abaixo dela.

    Reusa `orcamento.item.*` — medir é detalhar a linha orçada, e a planta (§12.1)
    já registrou que permissão nova custa rebuild da imagem da IAM.
    """

    queryset = LinhaMedicao.objects.select_related("item_orcado", "item_orcado__orcamento").all()
    serializer_class = LinhaMedicaoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["item_orcado"]
    ordering_fields = ["ordem", "medicao_id"]
    required_resource = "orcamento.item"
    action_permission_map = {
        "em_lote": "orcamento.item.edit",
    }

    def perform_create(self, serializer):
        _exigir_editavel(serializer.validated_data["item_orcado"].orcamento)
        super().perform_create(serializer)
        self._sincronizar(serializer.instance)

    def perform_update(self, serializer):
        _exigir_editavel(serializer.instance.item_orcado.orcamento)
        super().perform_update(serializer)
        self._sincronizar(serializer.instance)

    def perform_destroy(self, instance):
        item = instance.item_orcado
        _exigir_editavel(item.orcamento)
        instance.delete()
        quantitativos.sincronizar_quantidade(item)

    @staticmethod
    def _sincronizar(linha):
        try:
            quantitativos.salvar_linha(linha)
        except (quantitativos.FormulaInvalida, quantitativos.MedicaoInvalida) as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc

    @action(detail=False, methods=["post"], url_path="em-lote")
    def em_lote(self, request):
        """Grava várias parciais de uma vez — o caminho do colar do Excel.

        Uma a uma, cada parcial dispararia um recálculo da árvore inteira; num
        bloco de cinquenta linhas isso é cinquenta recálculos para chegar ao
        mesmo lugar. Aqui a sincronização acontece uma vez, no fim.
        """
        item = ItemOrcado.objects.filter(
            tenant_id=self._tenant_id(), pk=request.data.get("item_orcado")
        ).select_related("orcamento").first()
        if item is None:
            return Response({"item_orcado": "Linha não encontrada."}, status=status.HTTP_404_NOT_FOUND)
        _exigir_editavel(item.orcamento)

        parciais = request.data.get("linhas") or []
        if not isinstance(parciais, list):
            return Response({"linhas": "Envie uma lista."}, status=status.HTTP_400_BAD_REQUEST)

        if request.data.get("substituir"):
            LinhaMedicao.objects.filter(item_orcado=item).delete()

        criadas = []
        try:
            with transaction.atomic():
                base = LinhaMedicao.objects.filter(item_orcado=item).count()
                for indice, dados in enumerate(parciais):
                    serializer = self.get_serializer(data={
                        **dados, "item_orcado": item.pk, "ordem": dados.get("ordem", base + indice),
                    })
                    serializer.is_valid(raise_exception=True)
                    linha = LinhaMedicao(
                        tenant_id=self._tenant_id(), **serializer.validated_data
                    )
                    linha.total = quantitativos.calcular_linha(linha)
                    criadas.append(linha)
                LinhaMedicao.objects.bulk_create(criadas)
                quantitativos.recalcular_linhas(item)
        except (quantitativos.FormulaInvalida, quantitativos.MedicaoInvalida) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        item.refresh_from_db()
        return Response(
            quantitativos.memoria_do_quantitativo(item), status=status.HTTP_201_CREATED,
        )


class PastaComposicaoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Pastas dentro de um banco — organização por obra/tipo."""

    queryset = PastaComposicao.objects.select_related("banco", "obra").all()
    serializer_class = PastaComposicaoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["banco", "obra"]
    ordering_fields = ["ordem", "nome"]
    required_resource = "orcamento.banco"
    action_permission_map = {
        "create": "orcamento.banco.edit",
        "update": "orcamento.banco.edit",
        "partial_update": "orcamento.banco.edit",
        "destroy": "orcamento.banco.edit",
    }


class ItemBancoPrecoViewSet(
    _OrcamentoPermsMixin, QuotaEnforcedMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet
):
    """Itens de um banco da empresa. Busca server-side, como a base pública.

    A quota `banco_preco_linhas` vale aqui também, não só na importação: sem
    isto, o teto do plano seria contornável criando item a item pela API — o
    caminho é mais lento, mas o limite é comercial, e limite que se contorna com
    paciência não é limite.
    """

    quota_recurso = "banco_preco_linhas"
    queryset = ItemBancoPreco.objects.select_related("banco", "pasta").all()
    serializer_class = ItemBancoPrecoSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["banco", "pasta", "tipo"]
    search_fields = ["codigo", "descricao", "grupo"]
    ordering_fields = ["codigo", "descricao", "custo_unitario"]
    required_resource = "orcamento.banco"
    action_permission_map = {
        "create": "orcamento.banco.edit",
        "update": "orcamento.banco.edit",
        "partial_update": "orcamento.banco.edit",
        "destroy": "orcamento.banco.edit",
        "adotar": "orcamento.base.adotar",
        "duplicar": "orcamento.banco.edit",
        "composicao": "orcamento.banco.view",
    }

    def get_serializer_context(self):
        """Marca o que já foi adotado — um SELECT por página, não um por linha."""
        contexto = super().get_serializer_context()
        if self.action != "list":
            return contexto
        pagina = getattr(self, "_pagina_atual", None) or []
        codigos = [(i.banco.fonte, i.codigo) for i in pagina]
        if codigos:
            adotados = Item.objects.filter(
                tenant_id=self._tenant_id(),
                codigo_referencia__in=[c for _, c in codigos],
            ).values_list("fonte_referencia", "codigo_referencia", "item_id")
            contexto["adotados"] = {(f, c): i for f, c, i in adotados}
        return contexto

    def paginate_queryset(self, queryset):
        pagina = super().paginate_queryset(queryset)
        self._pagina_atual = pagina
        return pagina

    def perform_destroy(self, instance):
        if instance.banco.travado:
            raise exceptions.ValidationError({"detail": "Banco travado — destrave primeiro."})
        banco = instance.banco
        instance.delete()
        servico_bancos.recontar(banco)

    def perform_create(self, serializer):
        super().perform_create(serializer)
        servico_bancos.recontar(serializer.instance.banco)

    @action(detail=True, methods=["get"], url_path="composicao")
    def composicao(self, request, pk=None):
        componentes = ComponenteBancoPreco.objects.filter(
            composicao=self.get_object()
        ).select_related("filho")
        return Response(ComponenteBancoPrecoSerializer(componentes, many=True).data)

    @action(detail=True, methods=["post"], url_path="adotar")
    def adotar(self, request, pk=None):
        forcar = request.data.get("forcar", False) not in (False, "false", "0", 0, None, "")
        try:
            item = servico_bancos.adotar_no_catalogo(
                self.get_object(), self._tenant_id(), forcar=forcar
            )
        except servico_bancos.AdocaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except servico_bancos.IdentidadeDivergente as exc:
            return Response(
                {"detail": str(exc), "divergencia": exc.como_dict()},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({"item": item.pk, "criado": True})

    @action(detail=True, methods=["post"], url_path="duplicar")
    def duplicar(self, request, pk=None):
        """Copia o item (com a composição) para outro banco, para editar lá."""
        destino_id = request.data.get("banco_destino")
        destino = BancoPreco.objects.filter(
            tenant_id=self._tenant_id(), pk=destino_id
        ).first()
        if destino is None:
            return Response(
                {"banco_destino": "Banco de destino não encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            clone = servico_bancos.duplicar_item(
                self.get_object(), banco_destino=destino,
                novo_codigo=(request.data.get("codigo") or "").strip(),
            )
        except servico_bancos.BancoTravado as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(clone).data, status=status.HTTP_201_CREATED)


class ComponenteBancoPrecoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Coeficientes das composições próprias — a memória de cálculo da empresa."""

    queryset = ComponenteBancoPreco.objects.select_related("composicao", "filho").all()
    serializer_class = ComponenteBancoPrecoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["composicao", "filho"]
    required_resource = "orcamento.banco"
    action_permission_map = {
        "create": "orcamento.banco.edit",
        "update": "orcamento.banco.edit",
        "partial_update": "orcamento.banco.edit",
        "destroy": "orcamento.banco.edit",
    }


class ReprecificacaoViewSet(_OrcamentoPermsMixin, TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Lotes de troca de data-base — o histórico com o desfazer."""

    queryset = Reprecificacao.objects.select_related(
        "orcamento", "base_destino", "banco_destino"
    ).all()
    serializer_class = ReprecificacaoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["orcamento", "status", "orcamento__obra"]
    ordering_fields = ["criado_em", "aplicada_em"]
    required_resource = "orcamento.orcamento"
    action_permission_map = {
        "aplicar": "orcamento.orcamento.edit",
        "desfazer": "orcamento.orcamento.edit",
        "linhas": "orcamento.orcamento.view",
    }

    @action(detail=True, methods=["get"], url_path="linhas")
    def linhas(self, request, pk=None):
        return Response(servico_reprecificacao.serializar_previa(self.get_object()))

    @action(detail=True, methods=["post"], url_path="aplicar")
    def aplicar(self, request, pk=None):
        try:
            lote = servico_reprecificacao.aplicar(
                self.get_object(),
                selecionadas=request.data.get("linhas"),
                usuario_nome=self._usuario(request),
            )
        except planilha.OrcamentoNaoEditavel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except servico_reprecificacao.ReprecificacaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(servico_reprecificacao.serializar_previa(lote))

    @action(detail=True, methods=["post"], url_path="desfazer")
    def desfazer(self, request, pk=None):
        try:
            lote = servico_reprecificacao.desfazer(self.get_object())
        except planilha.OrcamentoNaoEditavel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except servico_reprecificacao.ReprecificacaoInvalida as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(lote).data)

    @staticmethod
    def _usuario(request) -> str:
        user = getattr(request, "user", None)
        return getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "") or ""
