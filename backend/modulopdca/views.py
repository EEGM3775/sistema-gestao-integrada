# backend/modulopdca/views.py
"""API do PDCA — `/api/pdca/`.

Todo endpoint desta fatia passa por **duas camadas**, na ordem da
docs/acesso-e-permissoes.md: `RequireModule("pdca")` (o tenant assina o módulo?)
e `RequirePermission` (esta pessoa pode isto?). Nada aqui é fundação sem
entitlement — diferente do `Local` do Maps, a hierarquia construtiva só faz
sentido para quem planeja obra, e planejar obra é o produto.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F, Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import (
    filters, mixins, permissions, status, views, viewsets,
)
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from nucleo.busca import BuscaSemAcento
from nucleo.permissions import RequireModule, RequirePermission
from nucleo.quotas import checar_quota
from nucleo.tenancy import TenantScopedAPIViewMixin, TenantScopedViewSetMixin
from payment.planos import (
    PDCA_PROFUNDIDADE_MAXIMA_WBS,
    PDCA_TETO_ADITIVOS_ABERTOS_POR_CONTRATO,
    PDCA_TETO_DEDUCOES_POR_MEDICAO,
    PDCA_TETO_ITENS_POR_ADITIVO,
    PDCA_TETO_APONTAMENTOS_POR_LOTE,
    PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
    PDCA_TETO_ITENS_POR_CONTRATO,
    PDCA_TETO_LINHAS_POR_LOTE,
    PDCA_TETO_LINHAS_POR_MEDICAO,
    PDCA_TETO_ITENS_POR_PROGRAMACAO,
    PDCA_TETO_RESTRICOES_ABERTAS_POR_OBRA,
    PDCA_TETO_CAUSAS_POR_TENANT,
    PDCA_TETO_LINHAS_DE_BALANCO,
    PDCA_TETO_LOCAIS_NA_LINHA_DE_BALANCO,
    PDCA_TETO_LOCAIS_POR_RITMO,
    PDCA_TETO_ACOES_POR_NC,
    PDCA_TETO_ITENS_POR_MODELO_VERIFICACAO,
    PDCA_TETO_MODELOS_POR_TENANT,
    PDCA_TETO_NCS_ABERTAS_POR_OBRA,
    PDCA_TETO_ANEXOS_POR_OCORRENCIA,
    PDCA_TETO_OCORRENCIAS_NA_FILA,
    PDCA_TETO_PARTICIPANTES_POR_DDS,
    PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA,
    PDCA_TETO_LINHAS_POR_FRENTE,
    PDCA_TETO_OBRAS_NA_CARTEIRA,
    PDCA_TETO_RESULTADOS_POR_ESPECIE,
)

from . import services
from .models import (
    AditivoContrato, ApontamentoAvanco, Atividade, CalendarioTrabalho,
    CausaNaoCumprimento, ItemProgramacao, ProgramacaoSemanal, Restricao,
    ContratoObra, Cronograma, ExcecaoCalendario, ItemContrato,
    LiberacaoRetencao, LocalObra, Medicao, Precedencia,
    ItemModeloVerificacao, ItemVerificacao, ModeloVerificacao,
    NaoConformidade, PlanoAcao, Verificacao,
    AnexoOcorrencia, DialogoSeguranca, Ocorrencia,
)
from .pagination import PdcaPageNumberPagination
from .serializers import (
    AbrirAditivoSerializer,
    AbrirMedicaoSerializer,
    AbrirProgramacaoSerializer,
    GerarRitmoSerializer,
    AditivoContratoSerializer,
    AtestarSerializer,
    CausaNaoCumprimentoSerializer,
    EncerrarSerializer,
    GerarDemandaSerializer,
    ItemProgramacaoSerializer,
    JulgarSerializer,
    ProgramacaoSemanalSerializer,
    ReabrirSerializer,
    RemoverRestricaoSerializer,
    RestricaoSerializer,
    CabecalhoDeMedicaoSerializer,
    LinhaDeAditivoSerializer,
    LinhaDeDeducaoSerializer,
    MedicaoResumoSerializer,
    ApontamentoAvancoSerializer,
    ApontamentoEmLoteSerializer,
    AplicarModeloSerializer,
    AtividadeSerializer,
    CalendarioTrabalhoSerializer,
    ContratoObraSerializer,
    CronogramaSerializer,
    ExcecaoCalendarioSerializer,
    GeracaoEmLoteSerializer,
    ItemContratoSerializer,
    LiberacaoRetencaoSerializer,
    LinhaDeMedicaoSerializer,
    LocalObraSerializer,
    LoteSerializer,
    EstornoSerializer,
    MarcarModeloSerializer,
    MedicaoSerializer,
    PrecedenciaSerializer,
    PropostaDeMedicaoSerializer,
    ReplanejarSerializer,
    RetificarSerializer,
    SolicitarLiberacaoSerializer,
    SubmeterSerializer,
    AplicarModeloVerificacaoSerializer,
    CancelarNcSerializer,
    DuplicarModeloSerializer,
    EncerrarNcSerializer,
    GerarRestricaoSerializer,
    ItemModeloVerificacaoSerializer,
    ItemVerificacaoSerializer,
    ModeloResumoSerializer,
    ModeloVerificacaoSerializer,
    NaoConformidadeSerializer,
    NcResumoSerializer,
    PlanoAcaoSerializer,
    RegistrarEficaciaSerializer,
    VerificacaoSerializer,
    AnexoOcorrenciaSerializer,
    ClassificarOcorrenciaSerializer,
    DialogoSegurancaSerializer,
    EncerrarDdsSerializer,
    EncerrarOcorrenciaSerializer,
    InterditarFrenteSerializer,
    OcorrenciaResumoSerializer,
    OcorrenciaSerializer,
    RegistrarCatSerializer,
    RegistrarPresencaSerializer,
)


class PdcaStatusView(views.APIView):
    """Status do módulo. Confirma entitlement antes de qualquer dado."""

    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "pdca"

    def get(self, request):
        return Response({
            "modulo": "pdca",
            "status": "ativo",
            # A tela precisa saber o que existe para não oferecer o que ainda não
            # foi construído — dado honesto vale para a própria capacidade.
            "fatia": "PDCA.8",
            "recursos": {
                "locais": True,
                "calendario": True,
                "cronograma": True,
                "modelo": True,
                "avanco": True,
                "contrato": True,
                "medicao": True,
                "retencao": True,
                # PDCA.4 — o aditivo existe, e com ele a trava do acumulado
                # passou a ser contra o contratado **atual** (original + deltas
                # aprovados), e não contra o do dia da assinatura.
                "aditivo": True,
                "deducoes": True,
                "material_estocado": True,
                # PDCA.5 — o Check e o Act. A restrição bloqueia o compromisso,
                # o compromisso vira PPC e o PPC vira ranking de causa.
                "restricao": True,
                "programacao_semanal": True,
                "ppc": True,
                "ranking_de_causas": True,
                # O seam do SCM é vivo: restrição de material vira demanda.
                "restricao_gera_demanda": True,
                # A semana encerrada deixou de ser um beco: `reabrir/` desce um
                # degrau, com motivo, e a correção fica visível no PPC.
                "reabrir_semana": True,
                # PDCA.6 — o plano visto pelo ritmo, e não pela duração.
                "linha_de_balanco": True,
                "ritmo": True,
                "conflito_de_equipe": True,
                # PDCA.7 — a máquina de verificação: uma máquina, quatro
                # domínios. A ficha congela a pergunta que respondeu, e a NC não
                # encerra sem eficácia verificada.
                "modelo_verificacao": True,
                "verificacao": True,
                "nao_conformidade": True,
                "plano_acao_5w2h": True,
                "verificacao_eficacia": True,
                "conformidade": True,
                "ranking_de_itens_que_reprovam": True,
                # E o seam vivo com o Last Planner: NC grave **para o serviço**
                # de verdade — abre restrição, e a atividade sai do quadro.
                "nc_gera_restricao": True,
                # O que a PDCA.7 **não** fecha, dito na capacidade para a tela
                # não oferecer botão que não existe: a NC aceita ser **ancorada**
                # numa marcação da Prancheta (o campo existe e viaja resolvido),
                # mas **criar** o pino sobre o desenho a partir daqui é verbo do
                # outro módulo — exige revisão e folha, que são dele. E não há
                # biblioteca de fichas de fábrica: FVS é o método da empresa, e
                # semear a nossa faria o cliente se certificar contra o nosso
                # chute (planta §11.14).
                "nc_cria_marcacao_na_prancheta": False,
                "modelos_de_fabrica": False,
                # PDCA.8 — SSMA. Registrar é barato e classificar é que pesa;
                # a CAT é devida mesmo sem afastamento e o sistema avisa o
                # prazo; e o acidente grave **para o serviço** pela mesma
                # corrente da NC crítica.
                "dialogo_seguranca": True,
                "ocorrencia": True,
                "classificacao_segregada": True,
                "cat_prazo_e_protocolo": True,
                "ocorrencia_interdita_frente": True,
                "ocorrencia_gera_investigacao": True,
                "piramide_de_ocorrencias": True,
                # O que a PDCA.8 **não** fecha, dito na capacidade para a tela
                # não prometer o que o sistema não sabe:
                #  · as taxas de frequência e gravidade dividem por homem-hora,
                #    e homem-hora é a PDCA.9 — elas voltam nulas com motivo;
                #  · a entrega de EPI é do SIL *(decisão do dono, 20/09/2026)*:
                #    a SSMA lê, sob `sil.epi.view`, e declara quando o módulo
                #    não está contratado;
                #  · a transmissão do evento eSocial S-2210 é da folha. Aqui
                #    mora o protocolo, não o envio.
                "taxa_frequencia": False,
                "taxa_gravidade": False,
                "epi_proprio": False,
                "transmite_esocial": False,
                # O que a PDCA.4 **não** fecha, dito na própria capacidade: a
                # planilha do empreiteiro entra colando coluna na grade, não por
                # um wizard de xlsx com conferência lado a lado; e o anexo por
                # linha de medição é texto — a evidência fotográfica mora no
                # apontamento de avanço, e a memória de cálculo é a ponte até
                # ela. A tela precisa saber disto para não oferecer botão que
                # não foi feito.
                "importar_planilha_do_empreiteiro": False,
                "anexo_por_linha": False,
                # O cockpit — as leituras que atravessam postos e obras. Estão
                # aqui porque a tela decide **a navegação** por elas: com a
                # busca única, o menu se mantém em seis postos; sem ela, cada
                # assunto novo do backend volta a pressionar por uma porta.
                "carteira": True,
                "fila_do_dia": True,
                "pulso_da_obra": True,
                "busca_unica": True,
                "mudancas_recentes": True,
                # A quinta, e a única que responde a quem está **dentro** da
                # obra: o que é meu, agora. É a leitura da superfície de campo.
                "minhas_frentes": True,
                # O que a superfície de campo **não** faz, dito na capacidade
                # para a tela declarar a dependência em vez de fingir: não há
                # fila local. Perder um apontamento em silêncio é pior do que
                # recusá-lo, e o trabalho offline é fase de plataforma.
                "campo_offline": False,
            },
            # Os tetos que a TELA precisa respeitar antes de mandar a requisição.
            # Só estes: quem decide o número continua sendo o dono, em
            # `payment/planos.py`, e o cliente lê o que vale hoje em vez de
            # carregar uma cópia que envelhece no bundle. Sem isto, colar 900
            # linhas viraria um 400 no fim de uma espera — em vez de dois blocos
            # com barra de progresso.
            "tetos": {
                "linhas_por_lote": PDCA_TETO_LINHAS_POR_LOTE,
                "atividades_por_cronograma": PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
                "profundidade_wbs": PDCA_PROFUNDIDADE_MAXIMA_WBS,
                "apontamentos_por_lote": PDCA_TETO_APONTAMENTOS_POR_LOTE,
                "itens_por_contrato": PDCA_TETO_ITENS_POR_CONTRATO,
                "linhas_por_medicao": PDCA_TETO_LINHAS_POR_MEDICAO,
                "itens_por_aditivo": PDCA_TETO_ITENS_POR_ADITIVO,
                "aditivos_abertos_por_contrato": (
                    PDCA_TETO_ADITIVOS_ABERTOS_POR_CONTRATO
                ),
                "deducoes_por_medicao": PDCA_TETO_DEDUCOES_POR_MEDICAO,
                "itens_por_programacao": PDCA_TETO_ITENS_POR_PROGRAMACAO,
                "restricoes_abertas_por_obra": (
                    PDCA_TETO_RESTRICOES_ABERTAS_POR_OBRA
                ),
                "causas_por_tenant": PDCA_TETO_CAUSAS_POR_TENANT,
                "locais_na_linha_de_balanco": (
                    PDCA_TETO_LOCAIS_NA_LINHA_DE_BALANCO
                ),
                "linhas_de_balanco": PDCA_TETO_LINHAS_DE_BALANCO,
                "locais_por_ritmo": PDCA_TETO_LOCAIS_POR_RITMO,
                "itens_por_modelo_verificacao": (
                    PDCA_TETO_ITENS_POR_MODELO_VERIFICACAO
                ),
                "modelos_por_tenant": PDCA_TETO_MODELOS_POR_TENANT,
                "ncs_abertas_por_obra": PDCA_TETO_NCS_ABERTAS_POR_OBRA,
                "acoes_por_nc": PDCA_TETO_ACOES_POR_NC,
                # PDCA.8. **Não há `ocorrencias_abertas_por_obra`**, e a
                # ausência é declarada: um teto ali recusaria o registro de um
                # acidente porque a obra já tem registros demais (§5.5m).
                "participantes_por_dds": PDCA_TETO_PARTICIPANTES_POR_DDS,
                "anexos_por_ocorrencia": PDCA_TETO_ANEXOS_POR_OCORRENCIA,
                "ocorrencias_na_fila": PDCA_TETO_OCORRENCIAS_NA_FILA,
                # Os três do cockpit. A tela precisa deles para **dizer o que
                # ficou de fora** em vez de mostrar uma lista cortada em
                # silêncio — carteira truncada sem aviso é a diretoria
                # decidindo sobre 40 obras achando que viu 57.
                "obras_na_carteira": PDCA_TETO_OBRAS_NA_CARTEIRA,
                "linhas_por_faixa_da_fila": PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA,
                "resultados_por_especie": PDCA_TETO_RESULTADOS_POR_ESPECIE,
                "linhas_por_frente": PDCA_TETO_LINHAS_POR_FRENTE,
            },
        })


class BasePdcaViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "pdca"
    pagination_class = PdcaPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]


class LocalObraViewSet(BasePdcaViewSet):
    """A árvore de locais da obra."""

    queryset = LocalObra.objects.select_related(
        "obra", "pai", "unidade", "maps_local"
    ).all()
    serializer_class = LocalObraSerializer
    required_resource = "pdca.local"
    filterset_fields = ["obra", "pai", "nivel", "ativo", "unidade"]
    search_fields = ["codigo", "nome"]
    ordering_fields = ["profundidade", "ordem", "codigo", "nome"]

    def get_queryset(self):
        qs = super().get_queryset()
        # `?raiz=1` devolve só o topo da árvore — é o primeiro fôlego da tela,
        # que abre a obra mostrando as torres e busca os galhos sob demanda.
        if self.request.query_params.get("raiz") in ("1", "true"):
            qs = qs.filter(pai__isnull=True)
        return qs

    def perform_create(self, serializer):
        pai = serializer.validated_data.get("pai")
        try:
            services.validar_profundidade(pai)
        except DjangoValidationError as erro:
            raise ValidationError({"pai": erro.messages})
        super().perform_create(serializer)
        serializer.instance.profundidade = services.profundidade_de(pai)
        serializer.instance.save(update_fields=["profundidade"])

    def perform_update(self, serializer):
        pai = serializer.validated_data.get("pai", serializer.instance.pai)
        try:
            services.validar_profundidade(pai)
        except DjangoValidationError as erro:
            raise ValidationError({"pai": erro.messages})
        super().perform_update(serializer)
        instancia = serializer.instance
        nova = services.profundidade_de(pai)
        if instancia.profundidade != nova:
            # Mudar de pai move o galho inteiro. Sem reescrever a profundidade
            # dos descendentes, a ordenação da árvore passaria a mentir para
            # todos eles — e o teto deixaria de ser conferido no lugar certo.
            instancia.profundidade = nova
            instancia.save(update_fields=["profundidade"])
            self._reprofundar(instancia)

    def _reprofundar(self, no: LocalObra) -> None:
        filhos = list(no.filhos.all())
        for filho in filhos:
            filho.profundidade = no.profundidade + 1
            filho.save(update_fields=["profundidade"])
            self._reprofundar(filho)

    @action(detail=False, methods=["post"], url_path="gerar-em-lote")
    def gerar_em_lote(self, request):
        """Cria a árvore a partir de uma receita — o recurso que faz a hierarquia
        ser usada em vez de ignorada (planta §4.1).

        `simular: true` devolve a mesma conta sem gravar nada. A tela pede a
        simulação primeiro; quem chama a API direto decide.
        """
        entrada = GeracaoEmLoteSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data

        obras = self._scope(self._obras())
        obra = obras.filter(pk=dados["obra"]).first()
        if obra is None:
            raise ValidationError({"obra": "Obra não encontrada nesta empresa."})

        pai = None
        if dados.get("pai"):
            pai = self.get_queryset().filter(pk=dados["pai"]).first()
            if pai is None:
                raise ValidationError({"pai": "Local pai não encontrado nesta empresa."})
            if pai.obra_id != obra.pk:
                raise ValidationError({"pai": "O local pai pertence a outra obra."})

        try:
            relatorio = services.gerar_em_lote(
                obra=obra,
                tenant_id=getattr(request.user, "tenant_id", None),
                receita=dados["receita"],
                pai=pai,
                simular=dados["simular"],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"receita": erro.messages})
        return Response(relatorio, status=status.HTTP_200_OK)

    def _obras(self):
        from obras.models import Obra

        return Obra.objects.all()


class CalendarioTrabalhoViewSet(BasePdcaViewSet):
    """Jornada e dias trabalhados."""

    queryset = CalendarioTrabalho.objects.select_related("obra").prefetch_related("excecoes")
    serializer_class = CalendarioTrabalhoSerializer
    required_resource = "pdca.calendario"
    filterset_fields = ["obra", "padrao", "ativo"]
    search_fields = ["nome"]
    ordering_fields = ["nome"]

    def get_queryset(self):
        """`?para_obra=<id>` — os expedientes que **servem** a esta obra.

        Não é sinônimo de `?obra=<id>`, e a diferença é o defeito que esta rota
        já teve ([D118](../../docs/historico-correcoes.md)): o filtro exato casa
        `obra_id = 7` e portanto **exclui os calendários da empresa**, que têm
        `obra` nulo justamente por valerem para todas as obras. O select de quem
        cria um plano ficava vazio numa empresa que tinha expediente cadastrado.

        A regra aqui é a mesma de `services.calendario_da_obra`, que é quem
        resolve o calendário no cálculo: **o da obra, mais os da empresa** — e
        nunca o de uma obra vizinha, que o serializer recusaria depois. A ordem
        põe o específico antes do geral, que é a ordem em que eles vencem.
        """
        qs = super().get_queryset()
        para_obra = self.request.query_params.get("para_obra")
        if para_obra:
            qs = (qs.filter(Q(obra_id=para_obra) | Q(obra__isnull=True))
                    .order_by(F("obra_id").desc(nulls_last=True), "-padrao", "nome"))
        return qs

    @action(detail=True, methods=["get"], url_path="dias-uteis")
    def dias_uteis(self, request, pk=None):
        """`?inicio=AAAA-MM-DD&fim=AAAA-MM-DD` → quantos dias se trabalha, e
        **quais feriados** entraram na conta.

        Devolver os feriados junto não é enfeite: é a diferença entre o
        planejador aceitar o número e desconfiar dele. Quando o cronograma diz
        que a atividade termina três dias depois do esperado, a pergunta é
        sempre "por quê" — e a resposta é esta lista.
        """
        from datetime import date as tipo_data

        calendario = self.get_object()
        try:
            inicio = tipo_data.fromisoformat(request.query_params["inicio"])
            fim = tipo_data.fromisoformat(request.query_params["fim"])
        except (KeyError, ValueError):
            raise ValidationError(
                {"inicio": "Informe `inicio` e `fim` no formato AAAA-MM-DD."}
            )
        if fim < inicio:
            raise ValidationError({"fim": "A data final é anterior à inicial."})

        feriados = services.feriados_do_periodo(calendario, inicio, fim)
        return Response({
            "calendario": calendario.calendario_id,
            "inicio": inicio, "fim": fim,
            "dias_uteis": services.dias_uteis(calendario, inicio, fim),
            "dias_corridos": (fim - inicio).days + 1,
            "feriados": [
                {"data": data, "nome": nome} for data, nome in sorted(feriados.items())
            ],
            # A tabela de feriados é global e nasce vazia (quem a enche é o
            # comando `sincronizar_feriados`). Sem este campo, um calendário que
            # promete considerar feriados devolve a conta sem eles e ninguém
            # fica sabendo — número errado com cara de certo.
            "feriados_sincronizados": services.base_de_feriados_sincronizada(),
        })

    @action(detail=True, methods=["get"], url_path="termino")
    def termino(self, request, pk=None):
        """`?inicio=AAAA-MM-DD&duracao=N` → a data de término. É a função que o
        CPM da PDCA.1 vai chamar; existir como endpoint agora permite que a tela
        de cadastro mostre o efeito da jornada antes de haver cronograma."""
        from datetime import date as tipo_data

        calendario = self.get_object()
        try:
            inicio = tipo_data.fromisoformat(request.query_params["inicio"])
            duracao = int(request.query_params["duracao"])
        except (KeyError, ValueError):
            raise ValidationError(
                {"inicio": "Informe `inicio` (AAAA-MM-DD) e `duracao` (inteiro ≥ 1)."}
            )
        try:
            fim = services.somar_dias_uteis(calendario, inicio, duracao)
        except DjangoValidationError as erro:
            raise ValidationError({"duracao": erro.messages})
        return Response({"inicio": inicio, "duracao": duracao, "termino": fim})


class ExcecaoCalendarioViewSet(BasePdcaViewSet):
    """Recesso, parada de chuva, mutirão de sábado."""

    queryset = ExcecaoCalendario.objects.select_related("calendario")
    serializer_class = ExcecaoCalendarioSerializer
    required_resource = "pdca.calendario"
    filterset_fields = ["calendario", "trabalha"]
    ordering_fields = ["data"]


# ---------------------------------------------------------------------------
# PDCA.1 — o plano de tempo
# ---------------------------------------------------------------------------


class CronogramaViewSet(BasePdcaViewSet):
    """O plano da obra e seus verbos: calcular, publicar, replanejar.

    Os três verbos não são CRUD, e por isso cada um declara a **sua** permissão
    (§8 da planta). Calcular é do mesmo nível de quem edita; publicar e replanejar
    são atos de compromisso — quem monta o plano não é necessariamente quem o
    assume perante a obra, e é a mesma segregação que o ORC.6 provou necessária.
    """

    queryset = Cronograma.objects.select_related("obra", "calendario", "origem")
    serializer_class = CronogramaSerializer
    required_resource = "pdca.cronograma"
    action_permission_map = {
        "publicar": "pdca.cronograma.publicar",
        "replanejar": "pdca.cronograma.replanejar",
        # Marcar um padrão da empresa e aplicá-lo numa obra nova são atos da
        # mesma classe de quem monta o plano — quem edita, edita. Publicar
        # continua sendo o ato à parte, e o modelo aplicado nasce em rascunho
        # justamente para passar por ele.
        "marcar_modelo": "pdca.cronograma.edit",
        "desmarcar_modelo": "pdca.cronograma.edit",
        "aplicar_modelo": "pdca.cronograma.edit",
        "lote": "pdca.cronograma.edit",
        "renumerar_eap": "pdca.cronograma.edit",
    }
    filterset_fields = ["obra", "status", "versao", "eh_modelo"]
    search_fields = ["descricao", "nome_modelo"]
    ordering_fields = ["versao", "data_inicio", "criado_em"]

    def perform_create(self, serializer):
        """Uma obra tem **um** cronograma, que ganha versões.

        Deixar criar um segundo do zero produziria dois planos sem parentesco
        para a mesma obra — e a linha de base, que é o parentesco, deixaria de
        existir justamente onde ela importa.
        """
        obra = serializer.validated_data.get("obra")
        existente = (self.get_queryset().filter(obra=obra).order_by("-versao").first())
        if existente is not None:
            raise ValidationError({
                "obra": (
                    f"Esta obra já tem cronograma (v{existente.versao}). Para mudar o "
                    "plano, replaneje a versão vigente — é o que preserva a anterior "
                    "como linha de base."
                ),
            })
        super().perform_create(serializer)

    def perform_update(self, serializer):
        if not serializer.instance.editavel:
            raise ValidationError(
                "Só um cronograma em rascunho é editável. Para mudar o plano vigente, replaneje."
            )
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.status == Cronograma.Status.VIGENTE:
            raise ValidationError(
                "O cronograma vigente não é excluído — ele é substituído por um replanejamento."
            )
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def calcular(self, request, pk=None):
        """Roda o CPM e grava datas, folgas e caminho crítico."""
        cronograma = self.get_object()
        try:
            return Response(services.calcular_cpm(cronograma))
        except DjangoValidationError as erro:
            raise ValidationError({"cronograma": erro.messages})

    @action(detail=True, methods=["post"])
    def publicar(self, request, pk=None):
        """Rascunho → vigente, com o CPM rodado antes de virar a chave."""
        cronograma = self.get_object()
        quem = (
            getattr(request.user, "get_full_name", lambda: "")()
            or getattr(request.user, "username", "")
        )
        try:
            resultado = services.publicar(cronograma, por=quem)
        except DjangoValidationError as erro:
            raise ValidationError({"cronograma": erro.messages})
        return Response({
            "cronograma": CronogramaSerializer(cronograma, context=self.get_serializer_context()).data,
            "cpm": resultado,
        })

    @action(detail=True, methods=["get"], url_path="linha-de-balanco")
    def linha_de_balanco(self, request, pk=None):
        """A LOB — eixo de locais, retas por serviço, ritmo, gargalo e choques.

        Derivada inteira (§4.9), como o CPM e a curva S: vem do servidor porque
        a inclinação é conta sobre datas, e duas contas para o mesmo ritmo
        produziriam dois ritmos na mesma obra.
        """
        cronograma = self.get_object()
        return Response(_str_decimais(services.linha_de_balanco(
            cronograma, tenant_id=request.user.tenant_id,
        )))

    @action(detail=True, methods=["post"])
    def ritmo(self, request, pk=None):
        """**Desenhar a linha** — o gesto que a planta §5.2 põe no lugar do arrastar.

        Exige `pdca.cronograma.edit`, e não um verbo próprio: o que este gesto
        faz é **criar atividades e precedências**. Um `pdca.lob.edit` separado
        seria uma permissão para uma *vista* do plano, e daria a alguém o poder
        de mudar o cronograma por uma porta que não se chama cronograma.
        """
        cronograma = self.get_object()
        entrada = GerarRitmoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data
        try:
            resultado = services.gerar_ritmo(
                cronograma=cronograma,
                locais=dados["locais"],
                inicio=dados["inicio"],
                duracao_por_local=dados["duracao_por_local"],
                ritmo_dias=dados.get("ritmo_dias"),
                pai_id=dados.get("pai"),
                nome=dados.get("nome", ""),
                codigo=dados.get("codigo", ""),
                simular=dados["simular"],
                tenant_id=request.user.tenant_id,
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(
            _str_decimais(resultado),
            status=status.HTTP_200_OK if dados["simular"] else status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def replanejar(self, request, pk=None):
        """Cria a versão seguinte em rascunho; esta vira linha de base."""
        cronograma = self.get_object()
        entrada = ReplanejarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            nova = services.replanejar(cronograma, motivo=entrada.validated_data["motivo"])
        except DjangoValidationError as erro:
            raise ValidationError({"motivo": erro.messages})
        return Response(
            CronogramaSerializer(nova, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def gantt(self, request, pk=None):
        """**Uma** chamada com o cronograma inteiro — árvore, setas e linha de base.

        Não é atalho de conveniência: o Gantt sincroniza árvore e linha do tempo,
        e montá-lo em três requisições paginadas produziria a tela desenhando a
        WBS antes de saber as datas, depois pulando quando as setas chegassem. O
        payload é grande de propósito, e é o cliente que virtualiza (planta §5.2).
        """
        cronograma = self.get_object()
        atividades = (cronograma.atividades
                      .select_related("local", "etapa", "item_orcado", "calendario",
                                      "responsavel")
                      .prefetch_related("filhos")
                      .order_by("ordem", "codigo", "atividade_id"))
        ligacoes = Precedencia.objects.filter(origem__cronograma=cronograma)
        contexto = self.get_serializer_context()
        return Response({
            "cronograma": CronogramaSerializer(cronograma, context=contexto).data,
            "atividades": AtividadeSerializer(atividades, many=True, context=contexto).data,
            "precedencias": PrecedenciaSerializer(ligacoes, many=True, context=contexto).data,
            "base": services.comparar_com_base(cronograma),
            "cobertura_orcamento": services.cobertura_do_orcamento(cronograma),
            # PDCA.2: o avanço viaja **junto**, pelo mesmo motivo que as datas —
            # a barra do Gantt mostra o executado dentro do previsto, e buscá-lo
            # numa segunda chamada faria a grade desenhar duas vezes, a segunda
            # com as barras mudando de cor na frente de quem olha.
            "avanco": services.avanco_do_cronograma(cronograma),
        })

    @action(detail=True, methods=["get"], url_path="linha-de-base")
    def linha_de_base(self, request, pk=None):
        """Atividade a atividade, o desvio entre este plano e o combinado."""
        return Response(services.comparar_com_base(self.get_object()))

    # -- PDCA.2: o que a obra respondeu ------------------------------------

    @action(detail=True, methods=["get"])
    def avanco(self, request, pk=None):
        """O avanço de cada atividade e o da obra — físico e financeiro.

        Leitura do plano, e por isso `pdca.cronograma.view`: quem enxerga o
        cronograma enxerga o quanto dele já andou. *Apontar* é outro verbo, com
        outra permissão, noutra rota.
        """
        return Response(services.avanco_do_cronograma(self.get_object()))

    @action(detail=True, methods=["get"], url_path="curva-s")
    def curva_s(self, request, pk=None):
        """Prevista × realizada, física × financeira.

        `?granularidade=dia|semana|mes` (padrão `semana`). Passado o teto de
        pontos do `planos.py`, o servidor **engrossa a granularidade e diz qual
        valeu** — a tela lê `granularidade` e `granularidade_pedida` e rotula o
        gráfico pelo que realmente foi desenhado.
        """
        pedida = request.query_params.get("granularidade", "semana")
        try:
            return Response(services.curva_s(self.get_object(), granularidade=pedida))
        except DjangoValidationError as erro:
            raise ValidationError({"granularidade": erro.messages})

    # -- Plano modelo (PDCA.1b) --------------------------------------------

    @action(detail=False, methods=["get"])
    def modelos(self, request):
        """A biblioteca de padrões da empresa, para o seletor da tela.

        Rota **de coleção** e não filtro da listagem porque a pergunta é outra:
        a listagem responde "quais planos esta empresa tem"; esta responde "que
        padrões eu posso aplicar numa obra nova". Quem pergunta a segunda quase
        nunca quer ver as 40 versões de plano das obras em andamento no meio.
        """
        biblioteca = services.modelos_do_tenant(request.user.tenant_id)
        pagina = self.paginate_queryset(biblioteca)
        serializer = self.get_serializer(pagina if pagina is not None else biblioteca, many=True)
        if pagina is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="marcar-modelo")
    def marcar_modelo(self, request, pk=None):
        """Promove este plano a modelo da biblioteca — e é aqui que a quota morde.

        A checagem vem **antes** de gravar, com o mecanismo de sempre: 402 com o
        limite e o uso no corpo, para a tela oferecer upgrade em vez de mandar
        falar com alguém.
        """
        cronograma = self.get_object()
        entrada = MarcarModeloSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        if not cronograma.eh_modelo:
            checar_quota(request.user, "planos_modelo")
        try:
            services.marcar_como_modelo(cronograma, nome=entrada.validated_data["nome"])
        except DjangoValidationError as erro:
            raise ValidationError({"nome": erro.messages})
        return Response(self.get_serializer(cronograma).data)

    @action(detail=True, methods=["post"], url_path="desmarcar-modelo")
    def desmarcar_modelo(self, request, pk=None):
        cronograma = self.get_object()
        services.desmarcar_modelo(cronograma)
        return Response(self.get_serializer(cronograma).data)

    @action(detail=True, methods=["post"], url_path="aplicar-modelo")
    def aplicar_modelo(self, request, pk=None):
        """Cria o plano de uma obra a partir deste modelo."""
        modelo = self.get_object()
        entrada = AplicarModeloSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data

        # A obra é buscada pelo queryset com escopo do tenant, e não por
        # `Obra.objects`: um id de outra empresa tem de virar 400 aqui, e não
        # um cronograma nascendo do lado de lá da fronteira.
        from obras.models import Obra
        obra = (Obra.objects.filter(pk=dados["obra"], tenant_id=request.user.tenant_id)
                .first())
        if obra is None:
            raise ValidationError({"obra": "Obra não encontrada nesta empresa."})

        calendario = None
        if dados.get("calendario"):
            calendario = (CalendarioTrabalho.objects
                          .filter(pk=dados["calendario"], tenant_id=request.user.tenant_id)
                          .first())
            if calendario is None:
                raise ValidationError({"calendario": "Calendário não encontrado."})
            if calendario.obra_id and calendario.obra_id != obra.pk:
                raise ValidationError({"calendario": "Este calendário é de outra obra."})

        try:
            novo = services.aplicar_modelo(
                modelo, obra=obra, descricao=dados.get("descricao", ""),
                data_inicio=dados["data_inicio"], calendario=calendario,
            )
        except DjangoValidationError as erro:
            raise ValidationError({"modelo": erro.messages})
        return Response(
            CronogramaSerializer(novo, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="renumerar-eap")
    def renumerar_eap(self, request, pk=None):
        """Reescreve a EAP inteira na ordem da árvore, numa transação.

        `{"simular": true}` conta sem escrever — a tela pergunta antes de mexer
        no código de 87 atividades de uma vez.
        """
        cronograma = self.get_object()
        simular = bool(request.data.get("simular"))
        try:
            return Response(services.renumerar_eap(cronograma, simular=simular))
        except DjangoValidationError as erro:
            raise ValidationError({"cronograma": erro.messages})

    @action(detail=True, methods=["post"])
    def lote(self, request, pk=None):
        """Muitas células numa requisição — o gesto de colar planilha."""
        cronograma = self.get_object()
        entrada = LoteSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.escrever_em_lote(
                cronograma, entrada.validated_data["edicoes"],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"edicoes": erro.messages})
        return Response(resultado)

    @action(detail=True, methods=["get"])
    def cobertura(self, request, pk=None):
        """Quantas atividades têm régua de custo — vínculo que não existe não é
        inventado (planta §11.1)."""
        return Response(services.cobertura_do_orcamento(self.get_object()))


class AtividadeViewSet(BasePdcaViewSet):
    """A WBS. Pertence ao cronograma, e por isso usa a permissão dele."""

    queryset = Atividade.objects.select_related(
        "cronograma", "pai", "local", "etapa", "item_orcado", "calendario", "responsavel"
    )
    serializer_class = AtividadeSerializer
    required_resource = "pdca.cronograma"
    filterset_fields = ["cronograma", "pai", "critica", "eh_marco", "local", "etapa"]
    search_fields = ["codigo", "nome"]
    ordering_fields = ["ordem", "codigo", "inicio_cedo", "termino_cedo", "folga_total"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("raiz") in ("1", "true"):
            qs = qs.filter(pai__isnull=True)
        return qs

    def perform_create(self, serializer):
        cronograma = serializer.validated_data.get("cronograma")
        pai = serializer.validated_data.get("pai")
        try:
            services.validar_teto_de_atividades(cronograma)
            services.validar_profundidade_wbs(pai)
        except DjangoValidationError as erro:
            raise ValidationError({"cronograma": erro.messages})
        super().perform_create(serializer)
        serializer.instance.profundidade = 1 if pai is None else pai.profundidade + 1
        serializer.instance.save(update_fields=["profundidade"])

    def perform_update(self, serializer):
        super().perform_update(serializer)
        instancia = serializer.instance
        nova = 1 if instancia.pai is None else instancia.pai.profundidade + 1
        if instancia.profundidade != nova:
            instancia.profundidade = nova
            instancia.save(update_fields=["profundidade"])
            self._reprofundar(instancia)

    def _reprofundar(self, no: Atividade) -> None:
        for filho in no.filhos.all():
            filho.profundidade = no.profundidade + 1
            filho.save(update_fields=["profundidade"])
            self._reprofundar(filho)

    def perform_destroy(self, instance):
        if not instance.cronograma.editavel:
            raise ValidationError(
                "Este cronograma não é mais rascunho. Para mudar o plano, replaneje."
            )
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def reprogramar(self, request, pk=None):
        """O gesto de **arrastar a barra** no Gantt, com nome de domínio.

        Arrastar não move a barra: fixa uma **restrição de data** ("não começar
        antes de") e manda o CPM recalcular. É a diferença entre uma tela de
        desenho e um cronograma — a barra que o planejador soltou pode voltar
        para trás se uma predecessora não permitir, e é isso que ele precisa ver
        acontecer.

        Aceita também `duracao_dias` (o gesto de esticar a ponta da barra).
        """
        atividade = self.get_object()
        if not atividade.cronograma.editavel:
            raise ValidationError(
                "Este cronograma não é mais rascunho. Para reprogramar, replaneje."
            )

        from datetime import date as tipo_data

        dados = request.data
        if "nao_comecar_antes_de" in dados:
            bruto = dados.get("nao_comecar_antes_de")
            if bruto in (None, ""):
                atividade.nao_comecar_antes_de = None
            else:
                try:
                    atividade.nao_comecar_antes_de = tipo_data.fromisoformat(str(bruto))
                except ValueError:
                    raise ValidationError({
                        "nao_comecar_antes_de": "Use o formato AAAA-MM-DD.",
                    })
        if "duracao_dias" in dados:
            try:
                duracao = int(dados["duracao_dias"])
            except (TypeError, ValueError):
                raise ValidationError({"duracao_dias": "Informe um inteiro."})
            if not atividade.eh_marco and duracao < 1:
                raise ValidationError({
                    "duracao_dias": "A duração precisa ser de ao menos 1 dia útil.",
                })
            atividade.duracao_dias = duracao
        atividade.save(update_fields=["nao_comecar_antes_de", "duracao_dias"])

        try:
            cpm = services.calcular_cpm(atividade.cronograma)
        except DjangoValidationError as erro:
            raise ValidationError({"cronograma": erro.messages})
        atividade.refresh_from_db()
        return Response({
            "atividade": AtividadeSerializer(
                atividade, context=self.get_serializer_context()
            ).data,
            "cpm": cpm,
        })


class PrecedenciaViewSet(BasePdcaViewSet):
    """As setas do Gantt. Criar uma é o gesto de ligar duas barras."""

    queryset = Precedencia.objects.select_related("origem", "destino")
    serializer_class = PrecedenciaSerializer
    required_resource = "pdca.cronograma"
    filterset_fields = ["origem", "destino", "tipo"]
    ordering_fields = ["destino", "origem"]

    def get_queryset(self):
        qs = super().get_queryset()
        cronograma = self.request.query_params.get("cronograma")
        if cronograma:
            qs = qs.filter(origem__cronograma_id=cronograma)
        return qs

    def perform_destroy(self, instance):
        if not instance.origem.cronograma.editavel:
            raise ValidationError(
                "Este cronograma não é mais rascunho. Para mudar as precedências, replaneje."
            )
        super().perform_destroy(instance)


# ---------------------------------------------------------------------------
# PDCA.2 — o avanço apontado
# ---------------------------------------------------------------------------


class ApontamentoAvancoViewSet(TenantScopedViewSetMixin,
                               mixins.CreateModelMixin,
                               mixins.ListModelMixin,
                               mixins.RetrieveModelMixin,
                               viewsets.GenericViewSet):
    """O livro-razão do avanço — **lê, cria e estorna; não edita nem apaga**.

    Não é `ModelViewSet` de propósito, e a diferença não é estética: um
    `ModelViewSet` publicaria `PUT`, `PATCH` e `DELETE`, e a fatia inteira existe
    para que esses três verbos não existam aqui. Corrigir é estornar — o registro
    errado continua legível, a correção aponta para ele, e a soma dá o número
    certo.

    **Duas permissões, e não o par `view`/`edit` de um CRUD** (planta §8): ler o
    avanço é do gestor e do cliente do relatório; *apontar* é o ato de campo que
    vira dinheiro na medição da PDCA.3.
    """

    queryset = ApontamentoAvanco.objects.select_related(
        "atividade", "atividade__cronograma", "local", "estorna",
    )
    serializer_class = ApontamentoAvancoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "pdca"
    pagination_class = PdcaPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    permission_map = {"view": "pdca.avanco.view", "write": "pdca.avanco.apontar"}
    action_permission_map = {
        "estornar": "pdca.avanco.apontar",
        "lote": "pdca.avanco.apontar",
    }
    filterset_fields = ["atividade", "local", "origem", "data"]
    search_fields = ["observacao", "apontado_por"]
    ordering_fields = ["data", "registrado_em", "percentual"]

    def get_queryset(self):
        qs = super().get_queryset()
        # O recorte natural do apontamento não é a atividade: é o **plano**
        # (a tela do avanço) ou a **janela de datas** (o boletim da semana).
        cronograma = self.request.query_params.get("cronograma")
        if cronograma:
            qs = qs.filter(atividade__cronograma_id=cronograma)
        obra = self.request.query_params.get("obra")
        if obra:
            qs = qs.filter(atividade__cronograma__obra_id=obra)
        de = self.request.query_params.get("de")
        if de:
            qs = qs.filter(data__gte=de)
        ate = self.request.query_params.get("ate")
        if ate:
            qs = qs.filter(data__lte=ate)
        return qs

    def _quem(self) -> str:
        return (
            getattr(self.request.user, "get_full_name", lambda: "")()
            or getattr(self.request.user, "username", "")
        )

    def _da_minha_empresa(self, atividade) -> None:
        """A FK garante que a atividade existe, não que ela é desta empresa.

        No Postgres a RLS já barraria a escrita; no SQLite de desenvolvimento ela
        é no-op, e sem esta linha um id adivinhado gravaria avanço no plano do
        vizinho. É a mesma defesa em profundidade do resto da casa.
        """
        meu = getattr(self.request.user, "tenant_id", None)
        if meu is not None and atividade.tenant_id != meu:
            raise ValidationError({"atividade": "Esta atividade não é desta empresa."})

    def perform_create(self, serializer):
        """A escrita passa pelo **serviço**, e não pelo `serializer.save()`.

        As recusas do avanço (sintética, marco, plano não vigente, acumulado
        acima de 100) e a trava de concorrência vivem lá porque a escrita em
        lote, o estorno e — depois — o WhatsApp entram pelos mesmos portões sem
        passar por este.
        """
        dados = serializer.validated_data
        atividade = dados["atividade"]
        self._da_minha_empresa(atividade)
        try:
            serializer.instance = services.registrar_apontamento(
                atividade=atividade,
                percentual=dados["percentual"],
                data=dados["data"],
                local=dados.get("local"),
                origem=dados.get("origem") or "web",
                observacao=dados.get("observacao", ""),
                foto=dados.get("foto"),
                por=self._quem(),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"percentual": erro.messages})

    @action(detail=True, methods=["post"])
    def estornar(self, request, pk=None):
        """Corrigir um apontamento é criar o de sinal contrário, com motivo."""
        apontamento = self.get_object()
        entrada = EstornoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            estorno = services.estornar(
                apontamento,
                motivo=entrada.validated_data["motivo"],
                data=entrada.validated_data.get("data"),
                por=self._quem(),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"motivo": erro.messages})
        return Response(
            self.get_serializer(estorno).data, status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"])
    def lote(self, request):
        """A grade da semana: N frentes numa transação — tudo ou nada."""
        entrada = ApontamentoEmLoteSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        cronograma = entrada.validated_data["cronograma"]
        meu = getattr(request.user, "tenant_id", None)
        if meu is not None and cronograma.tenant_id != meu:
            raise ValidationError({"cronograma": "Este plano não é desta empresa."})
        linhas = [
            {
                "atividade": linha["atividade"],
                "data": linha["data"],
                "percentual": linha["percentual"],
                "local": linha.get("local"),
                "origem": linha.get("origem"),
                "observacao": linha.get("observacao", ""),
            }
            for linha in entrada.validated_data["linhas"]
        ]
        try:
            resultado = services.apontar_em_lote(cronograma, linhas, por=self._quem())
        except DjangoValidationError as erro:
            raise ValidationError({"linhas": erro.messages})
        return Response(resultado, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# PDCA.3 — contrato, medição e liberação de retenção
# ---------------------------------------------------------------------------
#
# A segregação da planta §8 aparece aqui como **três verbos para a medição**, e
# não o par `view`/`edit`:
#
#   - `pdca.medicao.view` — ler. É do gestor, da diretoria e de quem recebe
#     relatório;
#   - `pdca.medicao.apurar` — abrir o boletim e conferir a proposta. É o gesto
#     de quem acompanha a obra;
#   - `pdca.medicao.atestar` — decidir. É o que faz o dinheiro sair.
#
# Quem apura **não** ateste, e a máquina do `nucleo` já recusa o autoatesto por
# padrão. Separar os dois verbos aqui é o que torna essa recusa configurável em
# vez de acidental — um tenant que queira a mesma pessoa nos dois papéis liga
# `permite_autoatesto` no fluxo, por escrito.


def _quem_e(request) -> str:
    """Rótulo durável de quem agiu, no molde do resto do módulo."""
    return (
        getattr(request.user, "get_full_name", lambda: "")()
        or getattr(request.user, "username", "")
    )


def _meu_contrato(request, contrato_id):
    """O contrato, conferido contra o tenant de quem pede.

    A RLS já recusaria o cruzamento no banco, mas ela devolve "não existe" — e
    quem está montando um aditivo precisa saber a diferença entre um id errado e
    um contrato de outra empresa.
    """
    if not contrato_id:
        raise ValidationError({"contrato": "Informe o contrato."})
    contrato = ContratoObra.objects.filter(pk=contrato_id).first()
    if contrato is None:
        raise ValidationError({"contrato": "Contrato não encontrado."})
    meu = getattr(request.user, "tenant_id", None)
    if meu is not None and contrato.tenant_id != meu:
        raise ValidationError({"contrato": "Este contrato não é desta empresa."})
    return contrato


def _minha_obra(request, obra_id):
    """A obra, conferida contra o tenant de quem pede — irmão do `_meu_contrato`.

    Mesma razão: a RLS recusaria o cruzamento, mas devolvendo "não existe", e
    quem abre a programação da semana precisa saber a diferença entre um id
    errado e uma obra de outra empresa.
    """
    from obras.models import Obra

    if not obra_id:
        raise ValidationError({"obra": "Informe a obra."})
    obra = Obra.objects.filter(pk=obra_id).first()
    if obra is None:
        raise ValidationError({"obra": "Obra não encontrada."})
    meu = getattr(request.user, "tenant_id", None)
    if meu is not None and obra.tenant_id != meu:
        raise ValidationError({"obra": "Esta obra não é desta empresa."})
    return obra


def _exige(request, permissao: str, motivo: str) -> None:
    """Confere uma permissão **além** da do portão, com a mesma leitura
    fail-closed do `RequirePermission`: admin de tenant e superusuário passam,
    os demais precisam do código exato na claim.

    É o que separa "submeter" de "aprovar" no tenant que ainda não montou
    escada — ali submeter aprova em um passo, e quem não tem a permissão de
    decidir não pode exercê-la por falta de configuração alheia.
    """
    usuario = request.user
    if getattr(usuario, "is_tenant_admin", False) or getattr(
        usuario, "is_superuser", False
    ):
        return
    if permissao not in (getattr(usuario, "iam_permissions", None) or []):
        raise PermissionDenied(motivo)


def _tem_permissao(request, permissao: str) -> bool:
    """A mesma leitura do `_exige`, mas **perguntando em vez de barrando**.

    Existe para a regra que depende de duas coisas ao mesmo tempo — a permissão
    e o estado —, e em que só quem conhece o estado sabe se a permissão é
    exigida. O caso é o encerramento antecipado da semana: a data mora no
    `services`, a claim mora aqui, e conferir a data nas duas pontas criaria
    duas regras que discordam no dia em que uma delas mudar.
    """
    usuario = request.user
    if getattr(usuario, "is_tenant_admin", False) or getattr(
        usuario, "is_superuser", False
    ):
        return True
    return permissao in (getattr(usuario, "iam_permissions", None) or [])


class ContratoObraViewSet(BasePdcaViewSet):
    """O que foi combinado com o empreiteiro, e o cockpit do saldo.

    **Só dois verbos** (`view`/`edit`), diferente da medição: montar o contrato é
    um ato só. A segregação que importa está do outro lado — quem monta o
    contrato pode não ser quem ateste a medição que nasce dele.
    """

    queryset = ContratoObra.objects.select_related("obra", "fornecedor")
    serializer_class = ContratoObraSerializer
    permission_map = {"view": "pdca.contrato.view", "write": "pdca.contrato.edit"}
    action_permission_map = {
        "saldo": "pdca.contrato.view",
        "proposta_de_medicao": "pdca.medicao.view",
        "periodo_sugerido": "pdca.medicao.view",
        "retencao": "pdca.contrato.view",
        # **Liberar retenção é ato de atesto, não de cadastro.** Sem esta linha
        # a ação cairia no `write` do mapa acima (`pdca.contrato.edit`) e quem
        # monta a planilha contratual poderia devolver a caução sozinho — a
        # mesma pessoa definindo o valor retido e mandando-o de volta. É a
        # segregação da §8 aplicada ao dinheiro que estava parado.
        "liberar_retencao": "pdca.medicao.atestar",
    }
    filterset_fields = ["obra", "fornecedor", "status", "regime", "regime_publico"]
    search_fields = ["numero", "objeto", "fornecedor__razao_social"]
    ordering_fields = ["criado_em", "numero", "data_inicio"]

    @action(detail=True, methods=["get"])
    def saldo(self, request, pk=None):
        """Contratado × medido × saldo × retenção — derivado inteiro (§4.9).

        É a leitura que abre a tela do contrato. Vem do servidor, e não montada
        no navegador a partir da lista de medições, pelo mesmo motivo do CPM:
        é número de dinheiro, e dois lugares somando dariam duas verdades.
        """
        contrato = self.get_object()
        dados = services.saldo_do_contrato(contrato)
        return Response(_str_decimais(dados))

    @action(detail=True, methods=["get"], url_path="proposta-de-medicao")
    def proposta_de_medicao(self, request, pk=None):
        """A prévia: o que se mediria neste período, **sem gravar nada**.

        Existe separada do `abrir` porque o gesto do gestor é olhar antes de
        decidir. Abrir a medição só para ver a proposta encheria o contrato de
        rascunhos que ele teria de apagar depois — e cada rascunho apagado é uma
        linha na lixeira.
        """
        contrato = self.get_object()
        entrada = PropostaDeMedicaoSerializer(data=request.query_params)
        entrada.is_valid(raise_exception=True)
        try:
            proposta = services.propor_medicao(
                contrato,
                inicio=entrada.validated_data["inicio"],
                fim=entrada.validated_data["fim"],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"periodo": erro.messages})
        return Response(_str_decimais(proposta))

    @action(detail=True, methods=["get"], url_path="periodo-sugerido")
    def periodo_sugerido(self, request, pk=None):
        """De quando a **próxima** medição deveria falar.

        Medição de obra é uma corrente: o período começa no dia seguinte ao fim
        do anterior. A tela abria sempre em "primeiro do mês → hoje", o que
        produzia sobreposição no mês medido quinzenalmente e buraco no mês em
        que a medição atrasou — e nenhum dos dois aparecia em lugar nenhum.
        """
        contrato = self.get_object()
        return Response(_str_decimais(services.sugerir_periodo(contrato)))

    @action(detail=True, methods=["get"], url_path="retencao")
    def retencao(self, request, pk=None):
        """Retido, liberado e disponível — as três parcelas, não só o saldo."""
        contrato = self.get_object()
        return Response(_str_decimais(services.retencao_disponivel(contrato)))

    @action(detail=True, methods=["post"], url_path="liberar-retencao")
    def liberar_retencao(self, request, pk=None):
        """Põe na escada o pedido de devolver o retido.

        **Escada própria, não a da medição** (ver o model): quem ateste medição
        confere serviço executado; quem libera caução confere condição
        contratual cumprida.
        """
        contrato = self.get_object()
        entrada = SolicitarLiberacaoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.solicitar_liberacao(
                contrato=contrato,
                valor=entrada.validated_data["valor"],
                data=entrada.validated_data["data"],
                condicao_atendida=entrada.validated_data["condicao_atendida"],
                solicitante=request.user,
                por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"valor": erro.messages})
        return Response(
            {
                "estado": resultado["estado"],
                "escada": resultado["escada"],
                "liberacao": LiberacaoRetencaoSerializer(
                    resultado["liberacao"], context=self.get_serializer_context(),
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ItemContratoViewSet(BasePdcaViewSet):
    """As linhas do contrato. O teto do `planos.py` é cobrado na criação."""

    queryset = ItemContrato.objects.select_related(
        "contrato", "item_orcado", "atividade",
    )
    serializer_class = ItemContratoSerializer
    permission_map = {"view": "pdca.contrato.view", "write": "pdca.contrato.edit"}
    filterset_fields = ["contrato", "item_orcado", "atividade"]
    search_fields = ["codigo", "descricao"]
    ordering_fields = ["ordem", "codigo"]

    def perform_create(self, serializer):
        """Confere o teto e o estado do contrato, e **delega a gravação**.

        O `super()` no fim não é formalidade: é ele que injeta o `tenant_id` do
        usuário (`TenantScopedViewSetMixin.perform_create`). Um `serializer.save()`
        direto aqui gravaria a linha sem tenant — e a RLS fail-closed da tabela
        recusa o INSERT com um 500 seco, que foi exatamente o que o E2E pegou
        nesta view antes de esta linha existir.
        """
        contrato = serializer.validated_data["contrato"]
        try:
            services.validar_teto_de_itens(contrato)
        except DjangoValidationError as erro:
            raise ValidationError({"contrato": erro.messages})
        self._so_com_contrato_editavel(contrato)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        contrato = serializer.instance.contrato
        self._so_com_contrato_editavel(contrato)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._so_com_contrato_editavel(instance.contrato)
        if instance.medicoes.exists():
            raise ValidationError({
                "detail": (
                    f"O item {instance.codigo} já foi medido — excluí-lo apagaria "
                    f"a razão de uma linha paga. Se ele não vale mais, a saída é "
                    f"o aditivo de supressão."
                ),
            })
        super().perform_destroy(instance)

    def _so_com_contrato_editavel(self, contrato) -> None:
        """**A planilha contratual fecha quando alguém já mediu contra ela.**

        A regra mora em `services.planilha_editavel`, e esta view só a aplica —
        a mesma função responde ao serializer, para a tela nunca oferecer um
        botão que a API vai recusar.

        **Esta trava nasceu de um achado do dono** (15/09/2026): a tela dizia
        *"a planilha não se edita mais aqui"* e a API aceitava a edição do mesmo
        jeito — ele mudou uma quantidade contratada de 53.150 para 631.500 num
        contrato com medição em aprovação. Regra que mora só na interface não é
        regra: é aviso. O comando de bancada, a importação e a aba antiga
        aberta no navegador continuam passando por aqui.
        """
        aberta, motivo = services.planilha_editavel(contrato)
        if not aberta:
            raise ValidationError({"contrato": motivo})



class MedicaoViewSet(TenantScopedViewSetMixin,
                     mixins.ListModelMixin,
                     mixins.RetrieveModelMixin,
                     mixins.DestroyModelMixin,
                     viewsets.GenericViewSet):
    """O boletim do período — **abre, submete, retifica; não se edita por PUT**.

    Não é `ModelViewSet`, e pelo mesmo motivo do apontamento: o documento tem
    ciclo de vida, e um `PATCH` genérico publicaria um caminho que atravessa o
    congelamento. Criar é `abrir/` (que roda a proposta); mudar a grade é
    `linhas/` e só em rascunho; corrigir depois de aprovada é `retificar/`.

    `DELETE` existe e vai para a **lixeira** (o `Excluivel` no model), não para o
    banco — e só em rascunho: medição que já subiu a escada é documento com
    decisão registrada.
    """

    queryset = Medicao.objects.select_related(
        "contrato", "contrato__obra", "contrato__fornecedor", "retifica",
    ).prefetch_related(
        "itens", "itens__item_contrato", "deducoes",
        # Sem estes dois, `escada` dispara uma consulta **por medição** — 100
        # consultas para desenhar a lista lateral de um contrato antigo.
        "aprovacoes", "aprovacoes__nivel_atual", "aprovacoes__atestos",
    )
    serializer_class = MedicaoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "pdca"
    pagination_class = PdcaPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    permission_map = {"view": "pdca.medicao.view", "write": "pdca.medicao.apurar"}
    action_permission_map = {
        "abrir": "pdca.medicao.apurar",
        "linhas": "pdca.medicao.apurar",
        "submeter": "pdca.medicao.apurar",
        "retificar": "pdca.medicao.apurar",
        #: **Piso, e o degrau certo é exigido dentro da ação** — mesma forma do
        #: `reabrir` da programação, porque aqui também é o **estado** que
        #: decide de quem é o ato. Cancelar um rascunho é de quem apura;
        #: cancelar uma aprovada derruba um título a pagar e é de quem ateste.
        #:
        #: Exigir `apurar` no portão parecia o piso natural e **fechava a porta
        #: para a pessoa certa**: `diretoria` e `fiscal_de_obra` têm
        #: `medicao.atestar` e **não** têm `apurar` (é a segregação da §8, de
        #: propósito), então o portão as barrava antes de a ação rodar.
        "cancelar": "pdca.medicao.view",
        # Decidir é verbo de outra pessoa (planta §8). Quando há escada
        # configurada, o motor do `nucleo` confere a permissão do **degrau** e
        # esta aqui é só o portão de entrada; sem escada, ela é a decisão.
        "atestar": "pdca.medicao.atestar",
    }
    filterset_fields = ["contrato", "status", "contrato__obra"]
    search_fields = ["observacao", "apurada_por", "contrato__numero"]
    ordering_fields = ["numero", "periodo_fim", "apurada_em"]

    def get_serializer_class(self):
        """`?resumo=1` devolve a medição **sem as linhas**.

        Quem lista quer o cabeçalho; quem abre um documento pede o documento. A
        lista da tela do contrato mandava todos os itens de todas as medições —
        meio megabyte de JSON para escrever quarenta linhas de texto.
        """
        if self.action == "list" and self.request.query_params.get("resumo") in (
            "1", "true",
        ):
            return MedicaoResumoSerializer
        return super().get_serializer_class()

    @action(detail=False, methods=["post"])
    def abrir(self, request):
        """Abre o boletim do período a partir da proposta do avanço."""
        contrato_id = request.data.get("contrato")
        if not contrato_id:
            raise ValidationError({"contrato": "Informe o contrato."})
        contrato = self._meu_contrato(contrato_id)

        entrada = AbrirMedicaoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data
        linhas = dados.get("linhas")
        try:
            medicao = services.criar_medicao(
                contrato=contrato,
                inicio=dados["inicio"],
                fim=dados["fim"],
                por=_quem_e(request),
                linhas=(
                    [
                        {"item_contrato_id": l["item_contrato_id"],
                         "quantidade": l["quantidade"]}
                        for l in linhas
                    ] if linhas is not None else None
                ),
                custo_reembolsavel=dados.get("custo_reembolsavel"),
                observacao=dados.get("observacao", ""),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(
            self.get_serializer(medicao).data, status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def contexto(self, request, pk=None):
        """**A grade desta medição, inteira, calculada no servidor.**

        Devolve uma linha por item do contrato — com contratado original,
        aditivos, contratado atual, acumulado anterior (já **sem** esta
        medição), proposta do período, material estocado, saldo e o que está
        gravado aqui —, mais os totais e o degrau da escada.

        **Existe porque a tela não pode fazer esta conta.** A primeira escrita
        da página montava `saldo = contratado − já medido` no navegador, a
        partir de uma prévia que só era buscada quando *não* havia medição
        aberta. Quem chegasse pelo link direto de uma medição via "já medido"
        **negativo** e saldo acima do contratado — e, como a trava de excesso da
        grade compara contra esse saldo, ela também parava de funcionar
        exatamente ali. Um endpoint, uma verdade.
        """
        medicao = self.get_object()
        try:
            dados = services.contexto_de_medicao(medicao)
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        dados["escada"] = self.get_serializer(medicao).data.get("escada")
        return Response(_str_decimais(dados))

    @action(detail=True, methods=["post"])
    def cabecalho(self, request, pk=None):
        """Os campos do documento que não são a grade, em rascunho.

        São dois — custo reembolsável e observação —, e eles não cabiam em
        `linhas/`: no regime de **administração** não há linha nenhuma, o que se
        mede é o custo, e sem este endpoint esse regime inteiro ficava sem porta
        na tela (abria a medição e nunca conseguia submetê-la).
        """
        medicao = self.get_object()
        self._so_rascunho(medicao)
        entrada = CabecalhoDeMedicaoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data

        campos = []
        if "custo_reembolsavel" in dados:
            medicao.custo_reembolsavel = dados["custo_reembolsavel"]
            campos.append("custo_reembolsavel")
        if "observacao" in dados:
            medicao.observacao = dados["observacao"]
            campos.append("observacao")
        if campos:
            medicao.save(update_fields=campos)
        return Response(self.get_serializer(medicao).data)

    @action(detail=True, methods=["post"])
    def deducoes(self, request, pk=None):
        """Reescreve as deduções do rascunho — substitui, não soma.

        Retenção contratual **não** entra aqui: ela é cláusula do contrato,
        congelada no nascimento do documento, e volta para o empreiteiro pela
        `LiberacaoRetencao`. O que entra são os descontos que **não voltam** —
        imposto retido, amortização de adiantamento, multa.
        """
        medicao = self.get_object()
        self._so_rascunho(medicao)
        entrada = LinhaDeDeducaoSerializer(
            data=request.data.get("deducoes", []), many=True,
        )
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.reescrever_deducoes(
                medicao=medicao,
                deducoes=[dict(linha) for linha in entrada.validated_data],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"deducoes": erro.messages})
        return Response(_str_decimais(resultado))

    @action(detail=True, methods=["post"])
    def linhas(self, request, pk=None):
        """Reescreve a grade do rascunho — o gestor conferindo item a item.

        Substitui, não soma: a grade da tela é o documento inteiro, e um
        endpoint que acumulasse faria dois envios acidentais dobrarem a medição.
        """
        medicao = self.get_object()
        self._so_rascunho(medicao)
        entrada = LinhaDeMedicaoSerializer(data=request.data.get("linhas", []), many=True)
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.reescrever_linhas(
                medicao=medicao, linhas=entrada.validated_data,
            )
        except DjangoValidationError as erro:
            raise ValidationError({"linhas": erro.messages})
        return Response(_str_decimais(resultado))

    @action(detail=True, methods=["post"])
    def submeter(self, request, pk=None):
        """Rascunho → escada de atesto (ou aprovação em um passo, sem fluxo).

        **Sem fluxo configurado o caminho é de um passo, e ele exige
        `pdca.medicao.atestar`** — não o `apurar` que abriu o documento. Sem
        essa conferência, um tenant que ainda não montou a escada daria a quem
        apura o poder de aprovar o próprio boletim, que é exatamente a
        segregação que a fatia existe para manter.
        """
        from nucleo import aprovacao as motor

        medicao = self.get_object()
        entrada = SubmeterSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        if motor.fluxo_para(medicao, tenant_id=medicao.tenant_id) is None:
            self._exige(request, "pdca.medicao.atestar", (
                "Esta empresa não tem escada de aprovação configurada para "
                "medição, então submeter aprovaria em um passo — e aprovar exige "
                "'pdca.medicao.atestar', que você não tem. Peça ao administrador "
                "do tenant que monte o fluxo em /api/aprovacao/fluxos/ (alvo "
                "'modulopdca.medicao'), para separar quem apura de quem decide."
            ))
        try:
            resultado = services.submeter_medicao(
                medicao=medicao, solicitante=request.user,
                observacao=entrada.validated_data.get("observacao", ""),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})

        medicao.refresh_from_db()
        return Response({
            "estado": resultado["estado"],
            "escada": resultado["escada"],
            "avisos": resultado["avisos"],
            "medicao": self.get_serializer(medicao).data,
        })

    @action(detail=True, methods=["post"])
    def retificar(self, request, pk=None):
        """Abre a medição que corrige uma já congelada (§11.5)."""
        medicao = self.get_object()
        entrada = RetificarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            nova = services.retificar(
                medicao=medicao,
                motivo=entrada.validated_data["motivo"],
                por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"motivo": erro.messages})
        return Response(
            self.get_serializer(nova).data, status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def atestar(self, request, pk=None):
        """Um degrau da escada, decidido a partir da tela da medição.

        É um encaminhador fino para `/api/aprovacao/`, e existe por um motivo de
        produto: quem ateste está **olhando a medição** — a grade, os itens, o
        líquido. Obrigá-lo a sair para outra tela para clicar em "aprovar"
        separaria a decisão da evidência, que é o oposto do que a escada existe
        para garantir.

        Quem decide de verdade é o motor do `nucleo`: ele confere a permissão
        **do degrau**, recusa o autoatesto e trava a linha do pedido. Esta view
        não redecide nada disso.
        """
        from nucleo import aprovacao as motor

        medicao = self.get_object()
        pedido = motor.pedido_de(medicao)
        if pedido is None:
            raise ValidationError({
                "detail": (
                    "Esta medição não está em nenhuma escada de aprovação "
                    f"(status: {medicao.get_status_display().lower()})."
                ),
            })
        entrada = AtestarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            pedido = motor.decidir(
                pedido=pedido, usuario=request.user,
                aprovar=entrada.validated_data["aprovar"],
                observacao=entrada.validated_data.get("observacao", ""),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})

        medicao.refresh_from_db()
        return Response({
            "estado_do_pedido": pedido.estado,
            "nivel_atual": getattr(pedido.nivel_atual, "nome", None),
            "medicao": self.get_serializer(medicao).data,
        })

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        """Retira o documento sem decidir o mérito — **e o título do ERP junto**.

        Cancelar **também congela** (ver `Medicao.esta_congelada`): um documento
        retirado que voltasse a ser editável seria o caminho para reaproveitar
        número de medição.

        **A medição aprovada passou a poder ser cancelada**, e é a correção do
        defeito que o dono achou: antes a porta era fechada para ela, então o
        gestor cancelava a que ainda estava em aprovação — e para a aprovada não
        havia gesto nenhum que alcançasse o título já gerado no ERP. O título
        ficava aberto no financeiro apontando para um boletim retirado.

        **A permissão é a de atestar, não a de apurar.** Cancelar uma medição
        aprovada derruba um título a pagar: é ato da mesma alçada que autorizou
        o dinheiro a sair, e não de quem monta o boletim. Enquanto ela é
        rascunho ou está em aprovação, nada saiu, e `apurar` basta.
        """
        from nucleo import aprovacao as motor

        medicao = self.get_object()
        if medicao.status == Medicao.Status.APROVADA:
            self._exige(request, "pdca.medicao.atestar", (
                "Cancelar uma medição aprovada derruba o título a pagar que ela "
                "gerou — é ato de quem tem alçada sobre o dinheiro, e exige "
                "'pdca.medicao.atestar'."
            ))
        else:
            #: O portão só pede `view` (ver o `action_permission_map`), então o
            #: degrau de quem **monta** o boletim é cobrado aqui. Sem esta linha,
            #: baixar o piso teria deixado qualquer leitor retirar um rascunho.
            self._exige(request, "pdca.medicao.apurar", (
                "Retirar uma medição que ainda não foi aprovada é ato de quem a "
                "monta — exige 'pdca.medicao.apurar'."
            ))
        pedido = motor.pedido_de(medicao)
        if pedido is not None and not medicao.esta_congelada:
            try:
                motor.cancelar(
                    pedido=pedido, usuario=request.user,
                    motivo=request.data.get("motivo", ""),
                )
            except DjangoValidationError as erro:
                raise ValidationError({"detail": erro.messages})
        try:
            resultado = services.cancelar_medicao(
                medicao=medicao,
                motivo=request.data.get("motivo", ""),
                por=_quem_e(request),
                usuario=request.user,
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response({
            **resultado, "medicao_dados": self.get_serializer(medicao).data,
        })

    def perform_destroy(self, instance):
        self._so_rascunho(instance)
        super().perform_destroy(instance)

    # --- apoio ------------------------------------------------------------
    def _meu_contrato(self, contrato_id):
        return _meu_contrato(self.request, contrato_id)

    def _so_rascunho(self, medicao) -> None:
        if medicao.status != Medicao.Status.RASCUNHO:
            raise ValidationError({
                "detail": (
                    f"A medição está {medicao.get_status_display().lower()} e não "
                    f"aceita mais mudança. Para corrigir uma medição aprovada, "
                    f"use 'retificar'."
                ),
            })

    def _exige(self, request, permissao: str, motivo: str) -> None:
        _exige(request, permissao, motivo)


class AditivoContratoViewSet(TenantScopedViewSetMixin,
                             mixins.ListModelMixin,
                             mixins.RetrieveModelMixin,
                             mixins.DestroyModelMixin,
                             viewsets.GenericViewSet):
    """O aditivo — **abre, submete, aprova; não se edita por PUT**.

    Mesma forma da medição, pelo mesmo motivo: o documento tem ciclo de vida, e
    um `PATCH` genérico publicaria um caminho que atravessa a aprovação. Criar é
    `abrir/`, mudar as linhas é `itens/` e só em rascunho, decidir é `atestar/`.

    **Aprovar é `pdca.aditivo.aprovar`, e montar é `pdca.aditivo.edit`.** A
    separação é a mesma da medição e existe pela mesma razão: quem negocia o
    acréscimo com o empreiteiro não pode ser quem autoriza a empresa a gastá-lo.
    """

    queryset = AditivoContrato.objects.select_related(
        "contrato", "contrato__obra", "contrato__fornecedor",
    ).prefetch_related(
        "itens", "itens__item_contrato",
        "aprovacoes", "aprovacoes__nivel_atual", "aprovacoes__atestos",
    )
    serializer_class = AditivoContratoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "pdca"
    pagination_class = PdcaPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    permission_map = {"view": "pdca.contrato.view", "write": "pdca.aditivo.edit"}
    action_permission_map = {
        "abrir": "pdca.aditivo.edit",
        "itens": "pdca.aditivo.edit",
        "submeter": "pdca.aditivo.edit",
        "cancelar": "pdca.aditivo.edit",
        "atestar": "pdca.aditivo.aprovar",
    }
    filterset_fields = ["contrato", "status", "contrato__obra"]
    search_fields = ["objeto", "justificativa", "contrato__numero"]
    ordering_fields = ["numero", "criado_em"]

    @action(detail=False, methods=["post"])
    def abrir(self, request):
        """Abre o aditivo em rascunho. Não move saldo nenhum ainda."""
        entrada = AbrirAditivoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data
        contrato = _meu_contrato(request, dados["contrato"])
        try:
            aditivo = services.criar_aditivo(
                contrato=contrato,
                objeto=dados["objeto"],
                justificativa=dados["justificativa"],
                data_assinatura=dados.get("data_assinatura"),
                nova_data_fim=dados.get("nova_data_fim"),
                por=_quem_e(request),
                itens=[dict(linha) for linha in dados.get("itens", [])],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(
            self.get_serializer(aditivo).data, status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def itens(self, request, pk=None):
        """Reescreve as linhas do rascunho — substitui, não soma."""
        aditivo = self.get_object()
        entrada = LinhaDeAditivoSerializer(
            data=request.data.get("itens", []), many=True,
        )
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.reescrever_itens_do_aditivo(
                aditivo=aditivo, itens=[dict(linha) for linha in entrada.validated_data],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"itens": erro.messages})
        return Response(_str_decimais(resultado))

    @action(detail=True, methods=["post"])
    def submeter(self, request, pk=None):
        """Rascunho → escada (ou aprovação em um passo, sem fluxo configurado).

        Sem escada, submeter **aprova e aplica** — e por isso exige
        `pdca.aditivo.aprovar`, não o `edit` que montou o documento. É a mesma
        conferência que a medição faz, pela mesma razão.
        """
        from nucleo import aprovacao as motor

        aditivo = self.get_object()
        if motor.fluxo_para(aditivo, tenant_id=aditivo.tenant_id) is None:
            _exige(request, "pdca.aditivo.aprovar", (
                "Esta empresa não tem escada de aprovação configurada para "
                "aditivo, então submeter aprovaria em um passo — e aprovar exige "
                "'pdca.aditivo.aprovar', que você não tem. Peça ao administrador "
                "do tenant que monte o fluxo em /api/aprovacao/fluxos/ (alvo "
                "'modulopdca.aditivocontrato')."
            ))
        try:
            resultado = services.submeter_aditivo(
                aditivo=aditivo, solicitante=request.user,
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})

        aditivo.refresh_from_db()
        return Response(_str_decimais({
            "estado": resultado["estado"],
            "escada": resultado["escada"],
            "avisos": resultado["avisos"],
            "aditivo": self.get_serializer(aditivo).data,
        }))

    @action(detail=True, methods=["post"])
    def atestar(self, request, pk=None):
        """Um degrau da escada, decidido de dentro da tela do aditivo."""
        from nucleo import aprovacao as motor

        aditivo = self.get_object()
        entrada = AtestarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        pedido = motor.pedido_de(aditivo)
        if pedido is None:
            raise ValidationError({
                "detail": (
                    "Este aditivo não está em nenhuma escada de aprovação "
                    f"(status: {aditivo.get_status_display().lower()})."
                ),
            })
        try:
            pedido = motor.decidir(
                pedido=pedido, usuario=request.user,
                aprovar=entrada.validated_data["aprovar"],
                observacao=entrada.validated_data.get("observacao", ""),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})

        aditivo.refresh_from_db()
        return Response({
            "estado_do_pedido": pedido.estado,
            "nivel_atual": getattr(pedido.nivel_atual, "nome", None),
            "aditivo": self.get_serializer(aditivo).data,
        })

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        """Retira o aditivo sem decidir o mérito."""
        from nucleo import aprovacao as motor

        aditivo = self.get_object()
        if aditivo.esta_congelado:
            raise ValidationError({
                "detail": (
                    f"O aditivo já está {aditivo.get_status_display().lower()} e "
                    f"não se cancela."
                ),
            })
        pedido = motor.pedido_de(aditivo)
        if pedido is not None:
            try:
                motor.cancelar(
                    pedido=pedido, usuario=request.user,
                    motivo=request.data.get("motivo", ""),
                )
            except DjangoValidationError as erro:
                raise ValidationError({"detail": erro.messages})
        aditivo.status = AditivoContrato.Status.CANCELADO
        aditivo.save(update_fields=["status"])
        return Response(self.get_serializer(aditivo).data)

    def perform_destroy(self, instance):
        if instance.status != AditivoContrato.Status.RASCUNHO:
            raise ValidationError({
                "detail": (
                    f"O aditivo está {instance.get_status_display().lower()} e não "
                    f"vai para a lixeira — documento com decisão registrada fica."
                ),
            })
        super().perform_destroy(instance)


class LiberacaoRetencaoViewSet(TenantScopedViewSetMixin,
                               mixins.ListModelMixin,
                               mixins.RetrieveModelMixin,
                               viewsets.GenericViewSet):
    """Leitura das liberações. **Criar é pelo contrato** (`liberar-retencao/`),
    porque o teto é o saldo retido daquele contrato — e um `POST` solto aqui
    convidaria a criar a linha sem passar pela conferência do saldo."""

    queryset = LiberacaoRetencao.objects.select_related(
        "contrato", "contrato__fornecedor",
    )
    serializer_class = LiberacaoRetencaoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "pdca"
    pagination_class = PdcaPageNumberPagination
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    permission_map = {"view": "pdca.contrato.view", "write": "pdca.medicao.atestar"}
    filterset_fields = ["contrato", "status"]
    search_fields = ["condicao_atendida", "solicitada_por"]
    ordering_fields = ["data", "valor"]


#: `Decimal` vira string no JSON, recursivamente — a definição mora no
#: `services` desde 15/09/2026, porque o serializer também precisa dela e não
#: pode importar daqui (este módulo importa dele). Ver a docstring lá.
_str_decimais = services.str_decimais


# ---------------------------------------------------------------------------
# PDCA.5 — Last Planner: make-ready, compromisso da semana e causa
# ---------------------------------------------------------------------------
# Três viewsets e uma separação de verbos que segue a mesma régua da medição:
#   - `pdca.restricao.view|edit|remover` — **remover** é ato que conclui (§5.4
#     da planta), e não uma edição mais forte: é a declaração de que o
#     make-ready aconteceu, e ela carrega a nota que a reunião seguinte lê;
#   - `pdca.programacao.view|comprometer|encerrar` — **comprometer** é o time
#     assumindo perante os colegas e **encerrar** é julgar o que saiu. Montar o
#     quadro (puxar cartão) é `comprometer` também: quem monta a parede é quem
#     vai assumi-la, e separar os dois criaria um papel que arruma cartão sem
#     poder assinar embaixo.


class RestricaoViewSet(BasePdcaViewSet):
    """O *constraint log* — o que trava a obra, e o ato de destravar."""

    queryset = Restricao.objects.select_related(
        "atividade", "atividade__cronograma", "local", "demanda_scm",
    ).all()
    serializer_class = RestricaoSerializer
    required_resource = "pdca.restricao"
    action_permission_map = {
        "remover": "pdca.restricao.remover",
        "gerar_demanda": "pdca.restricao.edit",
    }
    filterset_fields = {
        "atividade": ["exact"],
        "atividade__cronograma__obra": ["exact"],
        "tipo": ["exact"],
        "status": ["exact"],
        "prazo": ["exact", "lte", "gte"],
    }
    search_fields = ["descricao", "responsavel", "atividade__nome"]
    ordering_fields = ["prazo", "criada_em", "status"]

    def perform_create(self, serializer):
        atividade = serializer.validated_data.get("atividade")
        obra_id = getattr(
            getattr(atividade, "cronograma", None), "obra_id", None
        )
        if obra_id:
            try:
                services.validar_teto_de_restricoes(
                    obra_id, tenant_id=self.request.user.tenant_id,
                )
            except DjangoValidationError as erro:
                raise ValidationError({"detail": erro.messages})
        #: O `tenant_id` vai **explícito**, e não por herança: sobrescrever
        #: `perform_create` sem repeti-lo faz a linha nascer sem tenant, e a RLS
        #: recusa o INSERT com 500 (achado pelo `pdca5_programacao_test.py` — a
        #: suíte não pegava porque monta `Restricao` pelo ORM, com o tenant na
        #: mão, e nunca atravessa este método).
        serializer.save(
            tenant_id=getattr(self.request.user, "tenant_id", None),
            criada_por=_quem_e(self.request),
        )

    @action(detail=True, methods=["post"])
    def remover(self, request, pk=None):
        """O ato que conclui o make-ready — e ele exige dizer **como**."""
        restricao = self.get_object()
        entrada = RemoverRestricaoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            services.remover_restricao(
                restricao=restricao,
                por=_quem_e(request),
                nota=entrada.validated_data["nota"],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(self.get_serializer(restricao).data)

    @action(detail=True, methods=["post"], url_path="gerar-demanda")
    def gerar_demanda(self, request, pk=None):
        """O seam do SCM, vivo: restrição de material → demanda de compra.

        Exige **a permissão de comprar, além da de editar restrição**: abrir
        demanda é gesto do Suprimentos, e deixar que só `pdca.restricao.edit`
        o fizesse criaria uma porta lateral para a fila de compras.
        """
        restricao = self.get_object()
        _exige(request, "scm.demanda.edit", (
            "Gerar demanda a partir de uma restrição abre um documento no "
            "Suprimentos, e isso exige 'scm.demanda.edit'. Peça ao "
            "administrador ou registre a restrição sem gerar a compra."
        ))
        entrada = GerarDemandaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            demanda_id = services.gerar_demanda_scm(
                restricao=restricao,
                quantidade=entrada.validated_data.get("quantidade"),
                unidade=entrada.validated_data.get("unidade", ""),
                solicitante=request.user,
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(
            {"demanda": demanda_id,
             "restricao": self.get_serializer(restricao).data},
            status=status.HTTP_201_CREATED,
        )


class CausaNaoCumprimentoViewSet(BasePdcaViewSet):
    """O catálogo de causas — de fábrica e extensível pelo tenant.

    **Gateado por `pdca.programacao.*`, e não por um recurso próprio.** A causa
    não é um cadastro que alguém administra por si: ela existe para ser escolhida
    no encerramento da semana, e quem encerra é quem precisa poder acrescentar a
    que faltou na hora em que ela faltou. Um `pdca.causa.edit` separado
    produziria a reunião parada esperando um administrador.
    """

    queryset = CausaNaoCumprimento.objects.all()
    serializer_class = CausaNaoCumprimentoSerializer
    required_resource = "pdca.programacao"
    permission_map = {
        "view": "pdca.programacao.view",
        "write": "pdca.programacao.encerrar",
    }
    filterset_fields = ["categoria", "ativo", "de_fabrica"]
    search_fields = ["codigo", "nome"]
    ordering_fields = ["codigo", "categoria", "nome"]

    def perform_create(self, serializer):
        try:
            services.validar_teto_de_causas(self.request.user.tenant_id)
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        #: Mesma razão da `Restricao` acima — o tenant vai explícito.
        serializer.save(tenant_id=getattr(self.request.user, "tenant_id", None))

    def perform_destroy(self, instance):
        #: Causa já usada não se apaga — o histórico de PPC perderia o rótulo.
        #: O caminho é `ativo=False`, que a tira da lista de escolha e a mantém
        #: legível no passado.
        if instance.itens.exists():
            raise ValidationError({"detail": [
                "Esta causa já foi usada para explicar um compromisso que não "
                "saiu. Apagá-la deixaria aquele histórico sem rótulo — "
                "desative-a: ela sai da lista de escolha e continua legível no "
                "que já passou."
            ]})
        if instance.de_fabrica:
            raise ValidationError({"detail": [
                "Causa de fábrica não se apaga — desative-a. Ela é a âncora que "
                "permite comparar o histórico de duas obras."
            ]})
        super().perform_destroy(instance)

    @action(detail=False, methods=["post"])
    def semear(self, request):
        """Repõe o catálogo de fábrica. Idempotente."""
        criadas = services.semear_causas_de_fabrica(request.user.tenant_id)
        return Response({"criadas": criadas})


class ItemProgramacaoViewSet(BasePdcaViewSet):
    """Os cartões do quadro. **Puxar e devolver é `comprometer`** — quem monta
    a parede é quem assina embaixo dela."""

    queryset = ItemProgramacao.objects.select_related(
        "atividade", "local", "causa", "programacao",
    ).all()
    serializer_class = ItemProgramacaoSerializer
    required_resource = "pdca.programacao"
    permission_map = {
        "view": "pdca.programacao.view",
        "write": "pdca.programacao.comprometer",
    }
    filterset_fields = ["programacao", "atividade", "cumprido", "causa"]
    ordering_fields = ["ordem", "item_programacao_id"]

    def get_serializer_context(self):
        #: Resolve o agregado de restrições **uma vez por página**, e não por
        #: cartão: um quadro de 300 cartões faria 300 consultas (é o D136 do
        #: outro lado — a lista de medições que trazia ~200 consultas).
        contexto = super().get_serializer_context()
        if self.action == "list":
            ids = list(
                self.filter_queryset(self.get_queryset())
                .values_list("atividade_id", flat=True)[
                    :PDCA_TETO_ITENS_POR_PROGRAMACAO
                ]
            )
            contexto["restricoes_por_atividade"] = (
                services.restricoes_abertas_por_atividade(
                    ids, tenant_id=self.request.user.tenant_id,
                )
            )
            #: E os defeitos abertos da PDCA.7, pelo mesmo motivo: uma consulta
            #: por quadro, não uma por cartão.
            contexto["ncs_por_atividade"] = services.ncs_abertas_por_atividade(
                ids, tenant_id=self.request.user.tenant_id,
            )
            #: E o avanço que o campo apontou na semana, pela mesma razão: é
            #: uma consulta por quadro, não uma por cartão.
            prog_id = self.request.query_params.get("programacao")
            if prog_id:
                prog = ProgramacaoSemanal.objects.filter(
                    tenant_id=self.request.user.tenant_id, pk=prog_id,
                ).first()
                if prog is not None:
                    contexto["apontado_por_item"] = (
                        services.avanco_apontado_dos_itens(prog)
                    )
        return contexto

    def perform_destroy(self, instance):
        if not instance.programacao.esta_aberta_para_montagem:
            raise ValidationError({"detail": [
                "Esta semana já foi comprometida: o cartão não sai mais do "
                "quadro. Tirar um compromisso depois de assumido é apagar a "
                "aposta em vez de julgá-la — no encerramento, diga que não saiu "
                "e por quê."
            ]})
        super().perform_destroy(instance)


class ProgramacaoSemanalViewSet(TenantScopedViewSetMixin,
                                mixins.ListModelMixin,
                                mixins.RetrieveModelMixin,
                                mixins.UpdateModelMixin,
                                mixins.DestroyModelMixin,
                                viewsets.GenericViewSet):
    """A semana — **abre, compromete, julga, encerra**.

    Sem `create` genérico: a programação nasce por `abrir/`, que ancora a semana
    na segunda-feira e semeia o catálogo de causas. Um `POST` cru deixaria o
    cliente escolher o dia da âncora, e duas telas escolheriam dias diferentes
    para a mesma semana.

    `PATCH` existe só para a `nota` da reunião — o resto do documento muda por
    verbo, que é a mesma forma da medição e do aditivo.
    """

    queryset = ProgramacaoSemanal.objects.select_related("obra").all()
    serializer_class = ProgramacaoSemanalSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "pdca"
    pagination_class = PdcaPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    permission_map = {
        "view": "pdca.programacao.view",
        "write": "pdca.programacao.comprometer",
    }
    action_permission_map = {
        "abrir": "pdca.programacao.comprometer",
        "comprometer": "pdca.programacao.comprometer",
        "candidatos": "pdca.programacao.view",
        "julgar": "pdca.programacao.encerrar",
        #: Piso. Encerrar **antes** do fim da semana exige, além deste, o
        #: `pdca.programacao.encerrar_antecipado` — conferido dentro da ação,
        #: porque depende da data (ver `encerrar` abaixo).
        "encerrar": "pdca.programacao.encerrar",
        #: Arrastar é montar o quadro da semana seguinte: cartão que entra em
        #: rascunho é gesto de quem compromete, não de quem julga.
        "arrastar": "pdca.programacao.comprometer",
        #: Piso: o degrau certo (`encerrar` ou `comprometer`) é exigido dentro
        #: da ação, porque ele depende do estado em que a semana está.
        "reabrir": "pdca.programacao.view",
        "ppc": "pdca.programacao.view",
        "causas": "pdca.programacao.view",
    }
    filterset_fields = ["obra", "status", "semana_inicio"]
    ordering_fields = ["semana_inicio", "criada_em"]

    @action(detail=False, methods=["post"])
    def abrir(self, request):
        """Abre (ou devolve) a programação da semana, em rascunho."""
        entrada = AbrirProgramacaoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        obra = _minha_obra(request, entrada.validated_data["obra"])
        programacao = services.abrir_programacao(
            obra=obra,
            semana_inicio=entrada.validated_data["semana"],
            por=_quem_e(request),
            tenant_id=request.user.tenant_id,
        )
        return Response(
            self.get_serializer(programacao).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def candidatos(self, request, pk=None):
        """A área de rascunho: o que o plano diz que é desta semana.

        **Sugestão, não imposição** — o Last Planner existe porque o plano de
        meses atrás não sabe da obra de hoje.
        """
        programacao = self.get_object()
        return Response(services.candidatos_da_semana(programacao=programacao))

    @action(detail=True, methods=["post"])
    def comprometer(self, request, pk=None):
        """Rascunho → comprometida. Depois disto a lista não recebe item novo."""
        programacao = self.get_object()
        try:
            resultado = services.comprometer(
                programacao=programacao, por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response({
            **resultado, "programacao_dados": self.get_serializer(programacao).data,
        })

    @action(detail=True, methods=["post"])
    def julgar(self, request, pk=None):
        """O gesto do fim da semana — o quadro inteiro numa transação."""
        programacao = self.get_object()
        entrada = JulgarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.julgar_itens(
                programacao=programacao,
                julgamentos=[
                    dict(linha)
                    for linha in entrada.validated_data["julgamentos"]
                ],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(resultado)

    @action(detail=True, methods=["post"])
    def encerrar(self, request, pk=None):
        """Comprometida → encerrada. É aqui que o PPC passa a existir.

        **A semana que ainda não acabou pede outra permissão.** `encerrar` é o
        verbo de julgar o que saiu; fechar antes do domingo é decidir que a
        semana acabou para a obra, e isso não é a mesma alçada — ver
        `services.encerrar`. O `action_permission_map` continua exigindo
        `pdca.programacao.encerrar` como piso, e o degrau extra é conferido
        aqui, onde se sabe a data.

        O serviço é quem decide **se** o degrau extra é preciso: passamos se ele
        está disponível, não se ele é exigido. Conferir a data aqui também
        duplicaria a regra em dois lugares, e o dia em que ela mudasse os dois
        discordariam.
        """
        programacao = self.get_object()
        entrada = EncerrarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        pode_antecipar = _tem_permissao(
            request, "pdca.programacao.encerrar_antecipado",
        )
        try:
            resultado = services.encerrar(
                programacao=programacao, por=_quem_e(request),
                pode_antecipar=pode_antecipar,
                motivo_antecipado=entrada.validated_data.get("motivo", ""),
                arrastar=entrada.validated_data.get("arrastar", True),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        #: O PPC é `Decimal`, e atravessa como string — o `types.ts` do frontend
        #: já o declarava assim, e sem esta passada ele saía como número.
        return Response(_str_decimais(resultado))

    @action(detail=True, methods=["post"])
    def arrastar(self, request, pk=None):
        """Leva o que não saiu para a semana seguinte, em rascunho.

        **Encerrar já faz isto**, e esta porta existe para os dois casos em que
        o automático não alcança: a semana que foi encerrada com `arrastar:
        false` e depois se decidiu o contrário, e a que foi **reaberta e
        rejulgada** — aí o conjunto do que não saiu mudou, e o arrasto precisa
        correr de novo. É idempotente (ver `services.arrastar_pendentes`), então
        chamar duas vezes não duplica cartão.
        """
        programacao = self.get_object()
        try:
            resultado = services.arrastar_pendentes(
                programacao=programacao, por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(resultado)

    @action(detail=True, methods=["post"])
    def reabrir(self, request, pk=None):
        """Desce **um** degrau na semana, com motivo obrigatório.

        **A permissão depende do degrau, e por isso é conferida aqui dentro.**
        Desfazer o encerramento é desfazer o julgamento, e isso é de quem julga
        (`encerrar`); desfazer o compromisso é de quem assume (`comprometer`).
        Um só código para os dois daria a quem julga o poder de desmontar o
        quadro que a equipe assumiu — ou o contrário, que é pior: quem monta a
        parede passaria a poder apagar o índice que ela produziu.

        Por isso o `action_permission_map` pede só `view`: ele é o piso (quem
        nem enxerga a semana não a reabre), e o degrau certo é exigido abaixo.
        """
        programacao = self.get_object()
        if programacao.status == ProgramacaoSemanal.Status.ENCERRADA:
            _exige(request, "pdca.programacao.encerrar", (
                "Reabrir uma semana encerrada desfaz o julgamento dela, e isso "
                "é ato de quem julga — exige 'pdca.programacao.encerrar'."
            ))
        else:
            _exige(request, "pdca.programacao.comprometer", (
                "Desfazer o compromisso da semana devolve o quadro ao rascunho, "
                "e isso é ato de quem assume — exige "
                "'pdca.programacao.comprometer'."
            ))
        entrada = ReabrirSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.reabrir(
                programacao=programacao, por=_quem_e(request),
                motivo=entrada.validated_data["motivo"],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response({
            **resultado,
            "programacao_dados": self.get_serializer(programacao).data,
        })

    @action(detail=False, methods=["get"])
    def ppc(self, request):
        """A série histórica de PPC da obra — só semanas encerradas."""
        obra = _minha_obra(request, request.query_params.get("obra"))
        return Response(_str_decimais({
            "obra": obra.pk,
            "serie": services.serie_ppc(
                obra_id=obra.pk, tenant_id=request.user.tenant_id,
            ),
        }))

    @action(detail=False, methods=["get"])
    def causas(self, request):
        """**O "Act"** — o ranking de por que os compromissos não saem."""
        obra = _minha_obra(request, request.query_params.get("obra"))
        return Response(_str_decimais(services.ranking_de_causas(
            obra_id=obra.pk, tenant_id=request.user.tenant_id,
            desde=request.query_params.get("desde") or None,
            ate=request.query_params.get("ate") or None,
        )))


# ---------------------------------------------------------------------------
# PDCA.7 — a máquina de verificação: FVS, NC, 5W2H e eficácia
# ---------------------------------------------------------------------------
# Cinco viewsets e uma separação de verbos que é a da qualidade, não a de CRUD:
#
#   - `pdca.verificacao.view|modelo_edit|aplicar` — **montar a ficha e responder
#     a ficha são pessoas diferentes.** Quem escreve o método da empresa é o
#     engenheiro da qualidade, no escritório, e isso muda o que toda obra passa
#     a conferir; quem responde é o técnico no canteiro, e isso muda uma obra.
#     Um `edit` único daria ao campo o poder de afrouxar o critério da FVS no
#     momento em que ela reprovasse — que é exatamente quando alguém quer.
#   - `pdca.nc.view|abrir|tratar|verificar_eficacia` — quatro degraus, e o
#     último é o que dá sentido aos outros três. **Quem trata não verifica a
#     própria eficácia**: é a mesma régua que separa `apurar` de `atestar` na
#     medição, aplicada ao conserto. Sem ela, quem consertou assina que o
#     conserto funcionou, e o laço do §4.5 vira carimbo.


class ModeloVerificacaoViewSet(BasePdcaViewSet):
    """A biblioteca de fichas em branco da empresa."""

    queryset = ModeloVerificacao.objects.prefetch_related("itens").all()
    serializer_class = ModeloVerificacaoSerializer
    required_resource = "pdca.verificacao"
    permission_map = {
        "view": "pdca.verificacao.view",
        "write": "pdca.verificacao.modelo_edit",
    }
    action_permission_map = {"duplicar": "pdca.verificacao.modelo_edit"}
    filterset_fields = ["dominio", "ativo"]
    search_fields = ["codigo", "nome"]
    ordering_fields = ["codigo", "nome", "dominio", "criado_em"]

    def get_serializer_class(self):
        #: A listagem não carrega os 150 itens de cada ficha — D136.
        if self.action == "list":
            return ModeloResumoSerializer
        return ModeloVerificacaoSerializer

    def perform_create(self, serializer):
        try:
            services.validar_teto_de_modelos(self.request.user.tenant_id)
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        #: O `tenant_id` vai **explícito** — sobrescrever `perform_create` sem
        #: repeti-lo faz a linha nascer sem tenant e a RLS recusar o INSERT com
        #: 500. Foi o D149 da PDCA.5, e ele não se repete aqui.
        serializer.save(
            tenant_id=getattr(self.request.user, "tenant_id", None),
            criado_por=_quem_e(self.request),
        )

    def perform_destroy(self, instance):
        if instance.verificacoes.exists():
            raise ValidationError({"detail": [
                "Este modelo já foi aplicado em fichas de verificação. Apagá-lo "
                "deixaria aquelas inspeções sem o nome do que responderam — "
                "desative-o: ele sai da lista de escolha e continua legível em "
                "tudo que já foi verificado com ele."
            ]})
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def duplicar(self, request, pk=None):
        """Copia a ficha inteira com os itens — o gesto real da biblioteca."""
        modelo = self.get_object()
        entrada = DuplicarModeloSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            copia = services.duplicar_modelo(
                modelo=modelo,
                codigo=entrada.validated_data["codigo"],
                nome=entrada.validated_data.get("nome", ""),
                por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(
            ModeloVerificacaoSerializer(copia).data,
            status=status.HTTP_201_CREATED,
        )


class ItemModeloVerificacaoViewSet(BasePdcaViewSet):
    """As perguntas da ficha em branco."""

    queryset = ItemModeloVerificacao.objects.select_related("modelo").all()
    serializer_class = ItemModeloVerificacaoSerializer
    required_resource = "pdca.verificacao"
    permission_map = {
        "view": "pdca.verificacao.view",
        "write": "pdca.verificacao.modelo_edit",
    }
    filterset_fields = ["modelo"]
    ordering_fields = ["ordem", "item_modelo_id"]

    def perform_create(self, serializer):
        modelo = serializer.validated_data.get("modelo")
        if modelo is not None:
            try:
                services.validar_teto_de_itens_do_modelo(modelo)
            except DjangoValidationError as erro:
                raise ValidationError({"detail": erro.messages})
        serializer.save(tenant_id=getattr(self.request.user, "tenant_id", None))


class VerificacaoViewSet(TenantScopedViewSetMixin,
                         mixins.ListModelMixin,
                         mixins.RetrieveModelMixin,
                         mixins.UpdateModelMixin,
                         mixins.DestroyModelMixin,
                         viewsets.GenericViewSet):
    """A ficha aplicada — **abre por `aplicar/`, fecha por `concluir/`**.

    Sem `create` genérico, pela mesma razão da programação semanal: a ficha não é
    um registro que alguém preenche, é o resultado de **copiar um modelo para
    dentro dela** (o congelamento da pergunta). Um `POST` cru criaria ficha sem
    item, que conclui com 100% de conformidade sem ninguém ter olhado nada.

    `PATCH` existe para `nota` e `inspetor` — o resto do documento muda por
    verbo, que é a forma da medição, do aditivo e da semana.
    """

    queryset = Verificacao.objects.select_related(
        "modelo", "obra", "local", "atividade",
    ).all()
    serializer_class = VerificacaoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "pdca"
    pagination_class = PdcaPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    permission_map = {
        "view": "pdca.verificacao.view",
        "write": "pdca.verificacao.aplicar",
    }
    action_permission_map = {
        "aplicar": "pdca.verificacao.aplicar",
        "concluir": "pdca.verificacao.aplicar",
        "resultado": "pdca.verificacao.view",
        #: Abrir a NC a partir dos reprovados é ato de **abrir NC**, e não de
        #: responder ficha: é o degrau em que o defeito deixa de ser uma linha
        #: da inspeção e passa a ser um documento que alguém tem de tratar.
        "abrir_ncs": "pdca.nc.abrir",
    }
    filterset_fields = {
        "obra": ["exact"],
        "modelo": ["exact"],
        "modelo__dominio": ["exact"],
        "status": ["exact"],
        "local": ["exact"],
        "atividade": ["exact"],
        "data": ["exact", "lte", "gte"],
    }
    ordering_fields = ["data", "criada_em", "status"]

    def paginate_queryset(self, queryset):
        #: Guardada porque o `get_serializer_context` abaixo precisa saber
        #: **quais** fichas a página traz para montar o agregado de uma vez.
        self._pagina = super().paginate_queryset(queryset)
        return self._pagina

    def get_serializer_context(self):
        #: Resolve o resultado de todas as fichas da página **em uma consulta**.
        #: Sem isto, uma lista de 50 fichas faria 50 agregações — é o D136 do
        #: outro lado, a listagem de medições com ~200 consultas.
        contexto = super().get_serializer_context()
        if self.action == "list" and getattr(self, "_pagina", None):
            contexto["resultado_por_verificacao"] = _str_decimais(
                services.resultados_das_verificacoes(
                    self._pagina, tenant_id=self.request.user.tenant_id,
                )
            )
        return contexto

    @action(detail=False, methods=["post"])
    def aplicar(self, request):
        """Abre a ficha copiando as perguntas do modelo para dentro dela."""
        entrada = AplicarModeloVerificacaoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data
        obra = _minha_obra(request, dados["obra"])
        modelo = ModeloVerificacao.objects.filter(
            tenant_id=request.user.tenant_id, pk=dados["modelo"],
        ).first()
        if modelo is None:
            raise ValidationError({"modelo": "Modelo não encontrado."})
        try:
            verificacao = services.aplicar_verificacao(
                modelo=modelo, obra=obra, data=dados["data"],
                local_id=dados.get("local"), atividade_id=dados.get("atividade"),
                inspetor=dados.get("inspetor", ""),
                por=_quem_e(request), tenant_id=request.user.tenant_id,
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(
            self.get_serializer(verificacao).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def resultado(self, request, pk=None):
        """As contagens e a conformidade — derivadas (§4.9)."""
        return Response(_str_decimais(
            services.resultado_da_verificacao(self.get_object())
        ))

    @action(detail=True, methods=["post"])
    def concluir(self, request, pk=None):
        """Fecha a ficha e devolve os reprovados que ainda não viraram NC."""
        verificacao = self.get_object()
        try:
            resultado = services.concluir_verificacao(
                verificacao=verificacao, por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(_str_decimais({
            **resultado,
            "verificacao_dados": self.get_serializer(verificacao).data,
        }))

    @action(detail=True, methods=["post"], url_path="abrir-ncs")
    def abrir_ncs(self, request, pk=None):
        """Uma NC por item reprovado que ainda não tem uma — idempotente.

        **Sem corpo:** cada NC nasce com a gravidade do seu item, respondida por
        quem o reprovou (§11.15). Este verbo não escolhe peso nenhum.
        """
        verificacao = self.get_object()
        try:
            resultado = services.abrir_ncs_dos_reprovados(
                verificacao=verificacao, por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(resultado, status=status.HTTP_201_CREATED)


class ItemVerificacaoViewSet(TenantScopedViewSetMixin,
                             mixins.ListModelMixin,
                             mixins.RetrieveModelMixin,
                             mixins.UpdateModelMixin,
                             viewsets.GenericViewSet):
    """A resposta — **uma pergunta por vez, e é essa a física do instrumento**.

    O campo é o oposto da grade de medição (planta §5.2): lá se digitam 200
    células e a gravação é em lote; aqui se responde uma pergunta, com luva e
    sol na tela, e cada resposta vale por si. Por isso a porta é o `PATCH` do
    item, e não um lote — e por isso a foto sobe **nesta mesma requisição**, que
    é o que evita o segundo gesto no canteiro.

    **Sem `create` e sem `destroy`:** os itens nascem da aplicação do modelo e a
    lista deles é a ficha. Acrescentar ou tirar pergunta depois de a inspeção
    começar mudaria o denominador da conformidade no meio da conta.

    A regra ("ficha aberta", "desvio exige observação") mora no **`services`**, e
    este método a chama em vez de repeti-la: é a mesma função que a importação e
    o comando de bancada usariam, e duas cópias divergiriam na primeira mudança.
    """

    queryset = ItemVerificacao.objects.select_related("verificacao").all()
    serializer_class = ItemVerificacaoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "pdca"
    pagination_class = PdcaPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    permission_map = {
        "view": "pdca.verificacao.view",
        "write": "pdca.verificacao.aplicar",
    }
    filterset_fields = ["verificacao", "resultado"]
    ordering_fields = ["ordem", "item_verificacao_id"]

    def perform_update(self, serializer):
        item = serializer.instance
        dados = serializer.validated_data
        try:
            services.responder_itens(
                verificacao=item.verificacao,
                respostas=[{
                    "item_verificacao": item.pk,
                    "resultado": dados.get("resultado", item.resultado),
                    "observacao": dados.get("observacao", item.observacao),
                    #: **O peso deste defeito** (§11.15). Sem repassá-lo aqui, o
                    #: `PATCH` que traz a gravidade a perderia no caminho e o
                    #: serviço recusaria a resposta que o campo acabou de dar —
                    #: a recusa certa pelo motivo errado.
                    "gravidade": dados.get("gravidade", item.gravidade),
                }],
                por=_quem_e(self.request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        #: A foto é o que **este** método grava, porque ela não passa pelo
        #: serviço: o binário sobe pela porta única da plataforma, conferido
        #: pelo `UploadValidationMixin` contra o teto do tenant.
        if "foto" in dados:
            item.refresh_from_db()
            item.foto = dados["foto"]
            item.save(update_fields=["foto"])
        #: `serializer.instance` **é** este objeto, e o serviço escreveu no
        #: banco por fora dele — sem o refresh a resposta do `PATCH` devolveria
        #: o estado anterior, e a tela do campo mostraria a pergunta ainda
        #: pendente logo depois de respondê-la.
        item.refresh_from_db()


class NaoConformidadeViewSet(BasePdcaViewSet):
    """O defeito e o laço que o fecha.

    **`encerrar` e `eficacia` exigem `verificar_eficacia`, e `tratar` não
    alcança os dois.** É a segregação inteira desta fatia: quem monta o plano de
    ação não assina que o plano funcionou.
    """

    queryset = NaoConformidade.objects.select_related(
        "obra", "local", "atividade", "restricao", "marcacao_prancheta",
        "item_verificacao",
    ).prefetch_related("acoes", "eficacias").all()
    serializer_class = NaoConformidadeSerializer
    required_resource = "pdca.nc"
    permission_map = {"view": "pdca.nc.view", "write": "pdca.nc.abrir"}
    action_permission_map = {
        "gerar_restricao": "pdca.nc.tratar",
        "cancelar": "pdca.nc.tratar",
        "eficacia": "pdca.nc.verificar_eficacia",
        "encerrar": "pdca.nc.verificar_eficacia",
        "fila": "pdca.nc.view",
        "painel": "pdca.nc.view",
    }
    filterset_fields = {
        "obra": ["exact"],
        "atividade": ["exact"],
        "local": ["exact"],
        "gravidade": ["exact"],
        "status": ["exact"],
    }
    search_fields = ["descricao", "aberta_por"]
    ordering_fields = ["aberta_em", "gravidade", "status"]

    def get_serializer_class(self):
        if self.action == "list":
            return NcResumoSerializer
        return NaoConformidadeSerializer

    def perform_create(self, serializer):
        obra = serializer.validated_data.get("obra")
        if obra is not None:
            try:
                services.validar_teto_de_ncs(
                    obra.pk, tenant_id=self.request.user.tenant_id,
                )
            except DjangoValidationError as erro:
                raise ValidationError({"detail": erro.messages})
        serializer.save(
            tenant_id=getattr(self.request.user, "tenant_id", None),
            aberta_por=_quem_e(self.request),
        )

    @action(detail=True, methods=["post"], url_path="gerar-restricao")
    def gerar_restricao(self, request, pk=None):
        """O seam vivo com o Last Planner: a NC **para o serviço** de verdade.

        Exige **a permissão de travar a obra, além da de tratar**: abrir
        restrição impede o time de se comprometer com aquela frente, e deixar
        que só `pdca.nc.tratar` o fizesse criaria uma porta lateral para o
        quadro da semana. É a mesma régua do `gerar-demanda` da restrição.
        """
        nc = self.get_object()
        _exige(request, "pdca.restricao.edit", (
            "Gerar restrição a partir de uma NC trava a atividade no quadro da "
            "semana, e isso exige 'pdca.restricao.edit'. Peça ao administrador "
            "ou registre a não-conformidade sem parar a frente."
        ))
        entrada = GerarRestricaoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            restricao_id = services.gerar_restricao_da_nc(
                nc=nc,
                prazo=entrada.validated_data.get("prazo"),
                responsavel=entrada.validated_data.get("responsavel", ""),
                por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(
            {"restricao": restricao_id, "nc": self.get_serializer(nc).data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def eficacia(self, request, pk=None):
        """Registra se o conserto pegou. O "não" devolve a NC ao tratamento."""
        nc = self.get_object()
        entrada = RegistrarEficaciaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.registrar_eficacia(
                nc=nc,
                data=entrada.validated_data["data"],
                eficaz=entrada.validated_data["eficaz"],
                evidencia=entrada.validated_data["evidencia"],
                por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        nc.refresh_from_db()
        return Response(
            {**resultado, "nc": self.get_serializer(nc).data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def encerrar(self, request, pk=None):
        """Fecha a NC — e recusa fechar sem eficácia verificada (§4.5)."""
        nc = self.get_object()
        entrada = EncerrarNcSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            services.encerrar_nc(
                nc=nc, por=_quem_e(request),
                nota=entrada.validated_data.get("nota", ""),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(self.get_serializer(nc).data)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        """"Não era não-conformidade" — e isso exige dizer por quê."""
        nc = self.get_object()
        entrada = CancelarNcSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        if nc.status == NaoConformidade.Status.ENCERRADA:
            raise ValidationError({"detail": [
                "Esta NC já foi encerrada com eficácia verificada — cancelá-la "
                "agora apagaria da estatística um defeito que existiu e foi "
                "consertado."
            ]})
        nc.status = NaoConformidade.Status.CANCELADA
        nc.encerrada_em = timezone.now()
        nc.encerrada_por = _quem_e(request)
        nc.nota_encerramento = entrada.validated_data["motivo"].strip()
        nc.save(update_fields=[
            "status", "encerrada_em", "encerrada_por", "nota_encerramento",
        ])
        return Response(self.get_serializer(nc).data)

    @action(detail=False, methods=["get"])
    def fila(self, request):
        """**A fila de decisão da qualidade** — o que espera alguém, agora."""
        obra = _minha_obra(request, request.query_params.get("obra"))
        return Response(_str_decimais(services.fila_da_qualidade(
            obra_id=obra.pk, tenant_id=request.user.tenant_id,
        )))

    @action(detail=False, methods=["get"])
    def painel(self, request):
        """**O "Act" da qualidade** — conformidade e o que mais reprova."""
        obra = _minha_obra(request, request.query_params.get("obra"))
        return Response(_str_decimais(services.painel_de_conformidade(
            obra_id=obra.pk, tenant_id=request.user.tenant_id,
            desde=request.query_params.get("desde") or None,
            ate=request.query_params.get("ate") or None,
        )))


class PlanoAcaoViewSet(BasePdcaViewSet):
    """O 5W2H. **Montar é `tratar`; concluir também** — quem executa declara
    que executou, e é justamente por isso que essa declaração não encerra a NC."""

    queryset = PlanoAcao.objects.select_related("nao_conformidade").all()
    serializer_class = PlanoAcaoSerializer
    required_resource = "pdca.nc"
    permission_map = {"view": "pdca.nc.view", "write": "pdca.nc.tratar"}
    action_permission_map = {"concluir": "pdca.nc.tratar"}
    filterset_fields = {
        "nao_conformidade": ["exact"],
        "nao_conformidade__obra": ["exact"],
        "tipo": ["exact"],
        "status": ["exact"],
        "quando": ["exact", "lte", "gte"],
    }
    ordering_fields = ["quando", "criada_em", "status"]

    def perform_create(self, serializer):
        nc = serializer.validated_data.get("nao_conformidade")
        if nc is not None:
            try:
                services.validar_teto_de_acoes(nc)
            except DjangoValidationError as erro:
                raise ValidationError({"detail": erro.messages})
        serializer.save(
            tenant_id=getattr(self.request.user, "tenant_id", None),
            criada_por=_quem_e(self.request),
        )
        #: A NC passa a "em tratamento" no primeiro plano. É o degrau que separa
        #: "ninguém pegou" de "está sendo consertado" na fila de decisão — sem
        #: ele o cockpit mostraria as duas como a mesma urgência.
        if nc is not None and nc.status == NaoConformidade.Status.ABERTA:
            nc.status = NaoConformidade.Status.EM_TRATAMENTO
            nc.save(update_fields=["status"])

    @action(detail=True, methods=["post"])
    def concluir(self, request, pk=None):
        """Executado. **Não encerra a NC** — ver a docstring do serviço."""
        plano = self.get_object()
        try:
            services.concluir_acao(plano=plano, por=_quem_e(request))
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        return Response(self.get_serializer(plano).data)


# ---------------------------------------------------------------------------
# PDCA.8 — SSMA
# ---------------------------------------------------------------------------


class DialogoSegurancaViewSet(BasePdcaViewSet):
    """O DDS — a roda antes do turno, e a lista que a prova.

    Verbo único de escrita (`registrar`), porque não há aqui o que segregar: a
    roda é conduzida e registrada pela mesma pessoa, e quem a conduz é quem sabe
    quem estava lá.
    """

    queryset = DialogoSeguranca.objects.select_related(
        "obra", "local", "atividade", "responsavel", "diario",
    ).prefetch_related("participantes__funcionario").all()
    serializer_class = DialogoSegurancaSerializer
    required_resource = "pdca.dds"
    permission_map = {"view": "pdca.dds.view", "write": "pdca.dds.registrar"}
    action_permission_map = {
        "presenca": "pdca.dds.registrar",
        "encerrar": "pdca.dds.registrar",
    }
    filterset_fields = {
        "obra": ["exact"],
        "local": ["exact"],
        "atividade": ["exact"],
        "status": ["exact"],
        "data": ["exact", "gte", "lte"],
    }
    search_fields = ["tema", "assunto", "responsavel_nome"]
    ordering_fields = ["data", "status"]

    def perform_create(self, serializer):
        serializer.save(
            tenant_id=getattr(self.request.user, "tenant_id", None),
            registrado_por=_quem_e(self.request),
        )

    @action(detail=True, methods=["post"])
    def presenca(self, request, pk=None):
        """Grava a lista em lote — e recusa depois do encerramento."""
        dds = self.get_object()
        entrada = RegistrarPresencaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.registrar_presenca(
                dds=dds, participantes=entrada.validated_data["participantes"],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        dds.refresh_from_db()
        return Response(
            {**resultado, "dds": self.get_serializer(dds).data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def encerrar(self, request, pk=None):
        """Fecha a roda, fecha a lista — **e escreve no diário do dia**."""
        dds = self.get_object()
        entrada = EncerrarDdsSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.encerrar_dds(
                dds=dds, por=_quem_e(request),
                publicar_no_diario=entrada.validated_data["publicar_no_diario"],
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        dds.refresh_from_db()
        return Response({**resultado, "dds": self.get_serializer(dds).data})


class OcorrenciaViewSet(BasePdcaViewSet):
    """O fato de segurança — **e os quatro verbos que ele separa**.

    `registrar` é a porta larga e `classificar` é a estreita: a segregação desta
    fatia é *quem é medido não classifica a própria medida*. `emitir_cat` mora
    no RH, que é quem fala com o INSS, e `dado_medico` abre o bloco clínico —
    nenhum dos dois alcança os outros.
    """

    queryset = Ocorrencia.objects.select_related(
        "obra", "local", "atividade", "acidentado", "restricao",
        "nao_conformidade",
    ).prefetch_related("anexos").all()
    serializer_class = OcorrenciaSerializer
    required_resource = "pdca.ocorrencia"
    permission_map = {
        "view": "pdca.ocorrencia.view", "write": "pdca.ocorrencia.registrar",
    }
    action_permission_map = {
        "classificar": "pdca.ocorrencia.classificar",
        "cat": "pdca.ocorrencia.emitir_cat",
        "interditar": "pdca.ocorrencia.classificar",
        "investigar": "pdca.ocorrencia.registrar",
        "encerrar": "pdca.ocorrencia.classificar",
        "fila": "pdca.ocorrencia.view",
        "painel": "pdca.ocorrencia.view",
        "epi_vencido": "pdca.ocorrencia.view",
    }
    filterset_fields = {
        "obra": ["exact"],
        "local": ["exact"],
        "atividade": ["exact"],
        "tipo": ["exact"],
        "classificacao": ["exact"],
        "status": ["exact"],
    }
    search_fields = ["descricao", "agente_causador", "acidentado_nome"]
    ordering_fields = ["ocorrido_em", "tipo", "status"]

    def get_serializer_class(self):
        if self.action == "list":
            return OcorrenciaResumoSerializer
        return OcorrenciaSerializer

    def perform_create(self, serializer):
        serializer.save(
            tenant_id=getattr(self.request.user, "tenant_id", None),
            registrada_por=_quem_e(self.request),
        )

    @action(detail=True, methods=["post"])
    def classificar(self, request, pk=None):
        """O verbo estreito — tipo, afastamento e dias."""
        ocorrencia = self.get_object()
        entrada = ClassificarOcorrenciaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            services.classificar_ocorrencia(
                ocorrencia=ocorrencia,
                classificacao=entrada.validated_data["classificacao"],
                dias_perdidos=entrada.validated_data.get("dias_perdidos"),
                dias_debitados=entrada.validated_data.get("dias_debitados"),
                por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        ocorrencia.refresh_from_db()
        return Response(self.get_serializer(ocorrencia).data)

    @action(detail=True, methods=["post"])
    def cat(self, request, pk=None):
        """Guarda que a CAT foi comunicada — **o registro do ato, não o ato**.

        O sistema não transmite o evento eSocial S-2210: é obrigação da folha, e
        uma segunda porta para um ato com prazo legal criaria duas verdades
        sobre se a CAT foi comunicada.
        """
        ocorrencia = self.get_object()
        entrada = RegistrarCatSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            resultado = services.registrar_cat(
                ocorrencia=ocorrencia,
                tipo=entrada.validated_data["tipo"],
                emitida_em=entrada.validated_data["emitida_em"],
                protocolo=entrada.validated_data.get("protocolo", ""),
                por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        ocorrencia.refresh_from_db()
        return Response(
            {**resultado, "ocorrencia": self.get_serializer(ocorrencia).data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def interditar(self, request, pk=None):
        """**O dente**: a frente para de verdade, no quadro da semana.

        Exige `pdca.restricao.edit` **além** do verbo de SSMA, pela mesma régua
        do `gerar-restricao` da NC: sem isso a segurança viraria porta lateral
        para travar a programação de quem quer que seja.
        """
        ocorrencia = self.get_object()
        _exige(request, "pdca.restricao.edit", (
            "Interditar a frente trava a atividade no quadro da semana, e isso "
            "exige 'pdca.restricao.edit'. Peça ao administrador ou registre a "
            "ocorrência sem parar o serviço."
        ))
        entrada = InterditarFrenteSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            restricao = services.gerar_restricao_da_ocorrencia(
                ocorrencia=ocorrencia,
                prazo=entrada.validated_data.get("prazo"),
                por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        ocorrencia.refresh_from_db()
        return Response(
            {
                "restricao": restricao.pk,
                "ocorrencia": self.get_serializer(ocorrencia).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def investigar(self, request, pk=None):
        """Põe o fato na máquina de tratamento da PDCA.7 — sem duplicá-la."""
        ocorrencia = self.get_object()
        _exige(request, "pdca.nc.abrir", (
            "Investigar a ocorrência abre uma não-conformidade, e isso exige "
            "'pdca.nc.abrir'."
        ))
        try:
            nc = services.abrir_nc_da_ocorrencia(
                ocorrencia=ocorrencia, por=_quem_e(request),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        ocorrencia.refresh_from_db()
        return Response(
            {"nc": nc.pk, "ocorrencia": self.get_serializer(ocorrencia).data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def encerrar(self, request, pk=None):
        """Fecha o fato — e recusa fechar por cima de frente interditada."""
        ocorrencia = self.get_object()
        entrada = EncerrarOcorrenciaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            services.encerrar_ocorrencia(
                ocorrencia=ocorrencia, por=_quem_e(request),
                nota=entrada.validated_data.get("nota", ""),
            )
        except DjangoValidationError as erro:
            raise ValidationError({"detail": erro.messages})
        ocorrencia.refresh_from_db()
        return Response(self.get_serializer(ocorrencia).data)

    @action(detail=False, methods=["get"])
    def fila(self, request):
        """**A fila de decisão da segurança** — a CAT primeiro, que tem prazo."""
        obra = _minha_obra(request, request.query_params.get("obra"))
        return Response(_str_decimais(services.fila_da_ssma(
            obra_id=obra.pk, tenant_id=request.user.tenant_id,
        )))

    @action(detail=False, methods=["get"])
    def painel(self, request):
        """Os indicadores — **e os dois que o sistema declara não saber**."""
        obra = _minha_obra(request, request.query_params.get("obra"))
        return Response(_str_decimais(services.indicadores_de_ssma(
            obra_id=obra.pk, tenant_id=request.user.tenant_id,
            desde=request.query_params.get("desde") or None,
            ate=request.query_params.get("ate") or None,
        )))

    @action(detail=False, methods=["get"], url_path="epi-vencido")
    def epi_vencido(self, request):
        """O seam com o SIL — **e ele cobra a permissão do outro módulo**.

        A entrega de EPI é do SIL *(decisão do dono, 20/09/2026)*, e ler dado
        protegido de outro módulo sem cobrar a permissão dele faria da SSMA uma
        porta lateral. É a régua do `gerar-demanda` com o SCM.
        """
        obra = _minha_obra(request, request.query_params.get("obra"))
        _exige(request, "sil.epi.view", (
            "A ficha de EPI é do módulo de estoque (SIL), e lê-la exige "
            "'sil.epi.view'. Peça ao administrador."
        ))
        return Response(services.epi_vencido_da_obra(
            obra_id=obra.pk, tenant_id=request.user.tenant_id,
        ))


class AnexoOcorrenciaViewSet(BasePdcaViewSet):
    """Os arquivos da ocorrência — com o teto que a coleção obrigou a criar."""

    queryset = AnexoOcorrencia.objects.select_related("ocorrencia").all()
    serializer_class = AnexoOcorrenciaSerializer
    required_resource = "pdca.ocorrencia"
    permission_map = {
        "view": "pdca.ocorrencia.view", "write": "pdca.ocorrencia.registrar",
    }
    filterset_fields = {"ocorrencia": ["exact"], "especie": ["exact"]}

    def perform_create(self, serializer):
        ocorrencia = serializer.validated_data.get("ocorrencia")
        if ocorrencia is not None:
            try:
                services.validar_teto_de_anexos(ocorrencia)
            except DjangoValidationError as erro:
                raise ValidationError({"detail": erro.messages})
        serializer.save(
            tenant_id=getattr(self.request.user, "tenant_id", None),
            enviado_por=_quem_e(self.request),
        )


# ===========================================================================
# O cockpit — as leituras que atravessam postos e obras
# ===========================================================================
#
# **Estas quatro não declaram `RequirePermission`, e a ausência é deliberada.**
# Todo o resto do módulo é um recurso com um dono (`pdca.medicao`,
# `pdca.nc`, …) e o portão da camada 2 resolve num código só. Uma leitura que
# junta cinco assuntos não tem um dono: exigir `pdca.nc.view` para abrir a
# carteira recusaria a página ao técnico de segurança, e exigir o menor
# denominador não recusaria nada.
#
# O recorte é **por bloco**, dentro do serviço, pela mesma leitura fail-closed
# do `RequirePermission` (`_leitor` abaixo é o `_tem_permissao` virado do
# avesso). O que a pessoa não pode ver não vem, e vem no lugar uma linha em
# `sem_permissao` dizendo qual permissão falta — a régua omitir × trancar
# aplicada a um agregado. O portão que continua valendo para todas é o
# `RequireModule`: quem não assina o PDCA não abre o cockpit do PDCA.


def _leitor(request):
    """As claims de quem pede viram uma função `pode(codigo) -> bool`.

    Espelho exato do `_tem_permissao`, incluindo o atalho de admin de tenant e
    superusuário. Existe como função porque o `services` **não conhece
    `request`** — é o que permite exercer a carteira e a fila do comando de
    bancada e do teste sem forjar um token.
    """
    usuario = request.user
    if getattr(usuario, "is_tenant_admin", False) or getattr(
        usuario, "is_superuser", False
    ):
        return lambda _permissao: True
    concedidas = frozenset(getattr(usuario, "iam_permissions", None) or [])
    return lambda permissao: permissao in concedidas


class LeituraDoCockpit(TenantScopedAPIViewMixin, views.APIView):
    """A base das três: entitlement de módulo, e o recorte fica no serviço.

    **O mixin de tenancy não é decoração.** Todo o resto do módulo é
    `ModelViewSet` e herda o `TenantScopedViewSetMixin`, que arma a RLS no
    `initial()`; uma `APIView` pura não arma nada, e foi exatamente o achado S1
    (*"views de dashboard e de NF eram `APIView` puras, logo liam dados de
    qualquer tenant"*). A carteira é uma view de dashboard: sem isto ela seria
    a repetição literal daquele defeito, agora numa leitura que cruza obras de
    propósito.
    """

    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "pdca"


class CarteiraView(LeituraDoCockpit):
    """`GET /api/pdca/carteira/` — **as obras lado a lado** (B1).

    A porta de fora do módulo: daqui se **entra** numa obra. `?obras=1,2,3`
    recorta; sem recorte vêm todas as do tenant, até o teto do `planos.py`.
    """

    def get(self, request):
        recorte = (request.query_params.get("obras") or "").strip()
        escolhidas = None
        if recorte:
            try:
                escolhidas = [
                    int(pedaco) for pedaco in recorte.split(",") if pedaco.strip()
                ]
            except ValueError:
                raise ValidationError({
                    "obras": "Informe os números das obras separados por vírgula.",
                })
        return Response(_str_decimais(services.carteira(
            tenant_id=request.user.tenant_id,
            pode=_leitor(request),
            obras=escolhidas,
        )))


class HojeView(LeituraDoCockpit):
    """`GET /api/pdca/hoje/?obra=N` — **a fila, o pulso e o que mudou** (B2+B6).

    Os três blocos numa leitura só, e é o motivo de o endpoint existir: em
    chamadas separadas a tela de abertura esperava três vezes e cada número
    chegava com um recorte de período diferente do vizinho.

    `?mudancas=0` desliga o terceiro bloco, para quem só quer atualizar a fila
    sem recontar a semana inteira.
    """

    def get(self, request):
        obra = _minha_obra(request, request.query_params.get("obra"))
        pode = _leitor(request)
        tenant_id = request.user.tenant_id
        corpo = {
            "obra": obra.pk,
            "obra_nome": obra.nome_obra,
            "fila": services.fila_do_dia(
                obra_id=obra.pk, tenant_id=tenant_id, pode=pode,
            ),
            "pulso": services.pulso_da_obra(
                obra_id=obra.pk, tenant_id=tenant_id, pode=pode,
                desde=request.query_params.get("desde") or None,
                ate=request.query_params.get("ate") or None,
            ),
        }
        if request.query_params.get("mudancas") not in ("0", "false"):
            corpo["mudancas"] = services.mudancas_recentes(
                obra_id=obra.pk, tenant_id=tenant_id, pode=pode,
                dias=_inteiro(
                    request.query_params.get("dias"),
                    services.DIAS_DE_MUDANCAS, campo="dias",
                ),
            )
        return Response(_str_decimais(corpo))


class MinhasFrentesView(LeituraDoCockpit):
    """`GET /api/pdca/minhas-frentes/` — **o que é meu, agora** (B5).

    A porta da segunda superfície. As outras três respondem a quem olha a obra
    de fora; esta responde a quem está dentro dela, e por isso não exige
    `?obra=`: o encarregado costuma estar numa obra, e o mestre que cobre duas
    veria metade do trabalho dele se a leitura obrigasse a escolher.

    `?como=` troca o nome contra o qual a busca casa. Existe porque o alvo é
    **rótulo de texto** em todo o módulo (ver `services.minhas_frentes`): o
    escritório escreve "Mestre Antônio" no quadro, e quem entra como
    `antonio.silva` não casaria com nada. Sem essa saída, a pessoa cujo
    cadastro diverge veria a frente vazia para sempre — e frente vazia sem
    explicação é a forma de falha que não parece falha.
    """

    def get(self, request):
        obra_id = None
        if request.query_params.get("obra"):
            obra_id = _minha_obra(request, request.query_params.get("obra")).pk
        return Response(_str_decimais(services.minhas_frentes(
            tenant_id=request.user.tenant_id,
            quem=(request.query_params.get("como") or "").strip() or _quem_e(request),
            pode=_leitor(request),
            obra_id=obra_id,
        )))


class BuscaView(LeituraDoCockpit):
    """`GET /api/pdca/busca/?q=` — **uma busca sobre as sete espécies** (B4).

    É o que permite o menu ficar em seis postos: quem procura escreve o nome
    em vez de caçar a porta. `?obra=N` restringe à obra corrente — é o que a
    paleta de comando manda quando já se está dentro de uma.
    """

    def get(self, request):
        obra_id = None
        if request.query_params.get("obra"):
            obra_id = _minha_obra(request, request.query_params.get("obra")).pk
        return Response(_str_decimais(services.busca_unica(
            tenant_id=request.user.tenant_id,
            termo=request.query_params.get("q", ""),
            pode=_leitor(request),
            obra_id=obra_id,
        )))


def _inteiro(bruto, padrao: int, *, campo: str) -> int:
    """Um inteiro de query string — **e a recusa tem frase**.

    `?dias=ontem` cairia num `ValueError` cru e devolveria 500. É a régua do
    D187 na entrada: erro de quem digitou responde 400 dizendo o que corrigir.
    """
    if bruto in (None, ""):
        return padrao
    try:
        return int(bruto)
    except (TypeError, ValueError):
        raise ValidationError({campo: "Informe um número inteiro de dias."})
