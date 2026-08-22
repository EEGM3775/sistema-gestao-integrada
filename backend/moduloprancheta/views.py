# backend/moduloprancheta/views.py
"""API da Prancheta — `/api/prancheta/`.

Tudo aqui está atrás de `RequireModule("prancheta")`: diferente do Maps, a
Prancheta **não tem metade de fundação**. Georreferenciar uma obra é atributo de
cadastro que o SIL e o SCM consomem; abrir o projeto dela não é — nenhum outro
módulo depende do acervo para funcionar, e o custo (storage de CAD/BIM, motor de
conversão) é todo do módulo. Então o gate é um só, e é o entitlement.

A segregação que existe aqui é outra, e é interna: **publicar não é editar**.
Subir uma revisão é `prancheta.documento.edit`; torná-la vigente é
`prancheta.revisao.publicar`, porque publicar muda o que o campo vai executar.
A lição do D28 é que o verbo separado só vale se alguma persona o tiver — a
`projetista` tem ([iam/identity/catalog.py](../../iam/identity/catalog.py)).
"""
from __future__ import annotations

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.busca import BuscaSemAcento
from rest_framework import filters, permissions, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from nucleo.permissions import RequireModule, RequirePermission
from nucleo.tenancy import TenantScopedAPIViewMixin, TenantScopedViewSetMixin

from . import bcf, disciplinas, entrega, interop, pipeline, porta
from .entrega import RECURSO_MARCACAO
from .formatos import TETO_UPLOAD_DIRETO_MB
from .models import (
    ComentarioMarcacao,
    DerivadaProjeto,
    DesenhoProjeto,
    DisciplinaProjeto,
    DocumentoProjeto,
    Marcacao,
    Medicao,
    PontoDeVista,
    RevisaoDocumento,
)
from .motores import estado_dos_motores
from .pagination import PranchetaPageNumberPagination
from .serializers import (
    CalibracaoSerializer,
    ComentarioMarcacaoSerializer,
    DerivadaProjetoSerializer,
    DesenhoProjetoSerializer,
    DisciplinaProjetoSerializer,
    DocumentoProjetoSerializer,
    MarcacaoSerializer,
    MedicaoSerializer,
    PontoDeVistaSerializer,
    RevisaoDocumentoSerializer,
    recalcular_medidas,
)
from .planos import (
    exigir_formato_contratado,
    formatos_declarados,
    teto_de_snap,
    tiers_do_plano,
)
from .taxonomia import proximo_rotulo, revisao_declarada


class PranchetaStatusView(TenantScopedAPIViewMixin, views.APIView):
    """Status do módulo — e o que ESTE plano abre.

    Declara o catálogo inteiro de formatos com `contratado: true/false`, não só
    o que passa: a régua da planta §6 é que formato não contratado apareça
    **travado com o motivo**, nunca escondido. Uma lista só do que o plano abre
    deixaria o cliente sem saber que o produto lê RVT — e um seletor de arquivo
    que aceita tudo e falha depois do upload de 300 MB é a pior hora possível
    para dar a má notícia.
    """

    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "prancheta"

    def get(self, request):
        tiers = tiers_do_plano(request.user)
        motores = [
            {**estado, "habilitado": estado["tier"] in tiers}
            for estado in estado_dos_motores()
        ]
        return Response({
            "modulo": "prancheta",
            "status": "ativo",
            "plano": getattr(request.user, "iam_plano", None),
            "formatos": formatos_declarados(request.user),
            # Três colunas que respondem perguntas diferentes, e é útil que não se
            # confundam: `habilitado` é do PLANO, `implementado` é do CÓDIGO e
            # `disponivel` é desta IMAGEM. Motor habilitado e indisponível é
            # problema de deploy — e é assim que o `dwg2dxf` aparece quando o
            # build stage do LibreDWG não rodou (planta §12.3).
            "motores": motores,
            "teto_upload_direto_mb": TETO_UPLOAD_DIRETO_MB,
            # Deixou de ser `False` fixo no PRA.1: agora é medido. Vale quando
            # existe ao menos um motor habilitado pelo plano E disponível nesta
            # imagem — dizer "sim" com o binário faltando seria prometer um
            # visualizador que vai falhar depois do upload.
            "conversao_disponivel": any(
                m["habilitado"] and m["disponivel"] for m in motores
            ),
        })


class BasePranchetaViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "prancheta"
    pagination_class = PranchetaPageNumberPagination


class DisciplinaProjetoViewSet(BasePranchetaViewSet):
    """`/api/prancheta/disciplinas/` — o vocabulário desta empresa.

    **Listar devolve as 13 embutidas junto das próprias**, resolvidas em
    [disciplinas.py](disciplinas.py), e por isso a listagem não é a do ViewSet: a
    tela precisa do catálogo inteiro para desenhar a fileira de filtro e o seletor
    do envio, e um cliente que tivesse de somar "as fixas do código" com "as do
    servidor" teria duas fontes divergindo na primeira disciplina nova.

    Criar, editar e apagar continuam sendo CRUD normal sobre a tabela do tenant —
    e apagar não toca em prancha nenhuma: o documento guarda o **código** como
    texto, então a prancha volta a se chamar pelo próprio slug. É feio e é
    honesto; `CASCADE` aqui apagaria acervo por causa de uma faxina de rótulo.
    """

    queryset = DisciplinaProjeto.objects.all()
    serializer_class = DisciplinaProjetoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["ativa"]
    ordering_fields = ["ordem", "nome"]
    required_resource = "prancheta.documento"
    pagination_class = None

    def list(self, request, *args, **kwargs):
        return Response(disciplinas.catalogo(self.scope_qs))

    def scope_qs(self, queryset):
        """O mesmo escopo do mixin, exposto com o nome que `disciplinas` espera."""
        return self._scope(queryset)


class DocumentoProjetoViewSet(BasePranchetaViewSet):
    # `prefetch_related("revisoes")` porque o serializer resolve a vigente e a
    # contagem em Python — sem ele, listar 50 documentos custaria 100 queries.
    # As duas camadas seguintes são as mesmas do `acervo/` e pela mesma razão: o
    # resumo da vigente diz se dá para abrir (derivadas) e quantas folhas o
    # arquivo trouxe (desenhos, PRA.1c) — sem elas, cada documento da página
    # custa uma query por revisão e mais uma por folha.
    queryset = (
        DocumentoProjeto.objects.select_related("obra", "etapa")
        .prefetch_related(
            "revisoes__derivadas", "revisoes__desenhos__derivadas", "vinculos_disciplina",
        )
        .all()
    )
    serializer_class = DocumentoProjetoSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = ["obra", "etapa", "ativo"]
    search_fields = ["codigo", "titulo", "projetista"]
    ordering_fields = ["codigo", "titulo", "criado_em"]
    required_resource = "prancheta.documento"
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def filter_queryset(self, queryset):
        """`?disciplina=` passou a casar **qualquer** disciplina da prancha.

        Saiu do `filterset_fields` porque lá ele compararia só a coluna
        denormalizada (a principal), e a prancha que é arquitetura *e* elétrica
        sumiria do filtro de elétrica — o defeito que a fatia existe para não ter.
        O `distinct` é obrigatório: o join com o vínculo duplicaria a linha se
        alguém filtrasse por duas.
        """
        queryset = super().filter_queryset(queryset)
        codigo = self.request.query_params.get("disciplina")
        if codigo:
            queryset = queryset.filter(
                Q(vinculos_disciplina__codigo=codigo)
                # Documento anterior à PRA.9c não tem vínculo: continua achável
                # pela coluna, que é o que dispensa a migração de dados.
                | Q(vinculos_disciplina__isnull=True, disciplina=codigo)
            ).distinct()
        return queryset

    def _revisar(self, request, documento, *, preferido: str) -> RevisaoDocumento:
        """Grava uma revisão no documento, pelo serializer de sempre.

        **Delega em vez de repetir**, e não é economia de linhas: é o serializer
        que chama a `porta.admitir` (allowlist por bytes, teto de peso, gate de
        formato contratado), carimba hash/formato/tamanho e agenda a conversão no
        `on_commit`. Uma segunda gravação escrita aqui nasceria sem porta — que é
        exatamente a forma do D75, do lado de dentro.
        """
        serializer = RevisaoDocumentoSerializer(
            data={
                "documento": documento.pk,
                "revisao": proximo_rotulo(documento, preferido),
                "arquivo": request.data["arquivo"],
                "observacao": request.data.get("observacao", ""),
            },
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        # O `tenant` é read-only no serializer e quem o injeta é o `perform_create`
        # do mixin — que estas actions não atravessam. Vem o do **documento** e não
        # o do usuário: é ele que já passou pelo escopo, e assim revisão e documento
        # não podem divergir nem em teoria.
        return serializer.save(tenant_id=documento.tenant_id)

    @action(detail=True, methods=["post"])
    def atualizar(self, request, pk=None):
        """**Atualizar o arquivo** de uma prancha que já existe — a entrega seguinte.

        Visto de dentro da prancha: escolhe-se o arquivo e pronto. O rótulo vem
        do nome quando ele traz um, e senão é o seguinte ao maior
        (`proximo_rotulo`) — ninguém digita "R03".

        **É a única entrada avulsa que sobrou, e sobreviveu à PRA.9d por não ser
        a mesma coisa que o lote.** O irmão `enviar/` — o upload avulso do acervo
        — saiu: ele era um segundo caminho para o *mesmo* gesto do wizard de
        arquivos, e duas telas de entrada para um destino só é o que faz uma
        delas envelhecer sem ninguém notar. Aqui o gesto é outro: o documento
        **já está escolhido**, é ele que a pessoa tem aberto na tela, e não há
        acervo a conferir — pedir uma passada de conferência para trocar o
        arquivo de uma prancha que se está olhando seria cerimônia sem decisão.

        **Nasce em rascunho, como toda revisão.** Trocar o desenho que o campo
        executa é `revisao.publicar`, e continua sendo: subir a entrega nova não
        pode, sozinho, mudar o que está sendo construído no andaime.
        """
        documento = self.get_object()
        if not request.data.get("arquivo"):
            return Response(
                {"detail": "Escolha o arquivo da revisão nova."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        revisao_lida = revisao_declarada(getattr(request.data["arquivo"], "name", ""))
        with transaction.atomic():
            revisao = self._revisar(request, documento, preferido=revisao_lida)
        return Response(
            RevisaoDocumentoSerializer(revisao, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class RevisaoDocumentoViewSet(BasePranchetaViewSet):
    queryset = RevisaoDocumento.objects.select_related("documento", "enviado_por").prefetch_related(
        "derivadas", "desenhos__derivadas",
    ).all()
    serializer_class = RevisaoDocumentoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    # `documento__obra` existe para o **histórico da obra** (PRA.2): a tela de
    # versionamento pergunta "o que mudou nesta obra", não "o que mudou neste
    # documento". Sem o filtro, o cliente teria de paginar as revisões do tenant
    # inteiro e peneirar — e a página 1 pode não conter nenhuma revisão da obra
    # aberta, o que faria a tela dizer "sem histórico" com o histórico existindo.
    filterset_fields = ["documento", "situacao", "formato", "documento__obra"]
    ordering_fields = ["revisao", "enviado_em"]
    required_resource = "prancheta.documento"
    # Verbos de alçada: precedem o CRUD do recurso (contrato do `RequirePermission`).
    # `reprocessar` tem permissão própria porque queima CPU (e, com a APS da
    # PRA.4, dinheiro por tradução): quem lê o acervo não deve poder disparar a
    # reconversão dele em massa.
    action_permission_map = {
        "publicar": "prancheta.revisao.publicar",
        "publicar_pendentes": "prancheta.revisao.publicar",
        "reprocessar": "prancheta.conversao.reprocessar",
    }
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @action(detail=True, methods=["post"])
    def reprocessar(self, request, pk=None):
        """Reconverte esta revisão ignorando a idempotência.

        Existe porque a idempotência do pipeline é boa exatamente até deixar de
        ser: motor novo na imagem, `dwg2dxf` que finalmente entrou no build,
        derivada que saiu torta. Nesses casos `hash` + versão do motor não
        mudaram e o agendamento normal, corretamente, não faria nada.

        Enfileira e devolve **202** — a conversão é assíncrona por natureza
        (planta §5) e responder 200 daria a entender que já terminou.
        """
        revisao = self.get_object()
        tiers = tiers_do_plano(request.user)
        planejadas = pipeline.planejar(revisao.formato, tiers)
        if not planejadas:
            # Não é erro: KMZ vai para o Maps, LAS para o drone, RVT espera a
            # PRA.4. Um 202 aqui prometeria trabalho que ninguém vai fazer.
            return Response(
                {"detail": (
                    "Nenhum motor disponível converte este formato no seu plano — "
                    "não há o que reprocessar."
                ), "formato": revisao.formato, "agendadas": []},
                status=status.HTTP_409_CONFLICT,
            )

        # **É por aqui que a prancha antiga ganha snap.** O acervo já convertido
        # não é reprocessado em massa quando alguém assina o recurso — seria uma
        # onda de conversão pesada de uma vez, e sobre desenho que talvez ninguém
        # vá medir. O caminho é este verbo, que a tela oferece como "ativar snap"
        # na prancha aberta: quem quer, pede, e paga só o que pediu.
        agendadas = pipeline.agendar(
            revisao, tiers=tiers, teto_snap=teto_de_snap(request.user), forcar=True,
            user=request.user)
        return Response(
            {"detail": f"{len(agendadas)} conversão(ões) reenfileirada(s).",
             "agendadas": agendadas},
            status=status.HTTP_202_ACCEPTED,
        )

    # A ação `arquivo/` saiu na PRA.5. A porta de leitura do acervo é agora
    # `/api/impexp/prancheta.acervo/arquivo/revisao/<id>/`, declarada em
    # [impexp.py](impexp.py) — a porta única é de entrada **e** de saída (decisão
    # do dono, 08/08/2026). O contrato que a docstring daqui defendia não mudou
    # em nada (gate do módulo, 404 sem vazar existência, sem permissão de
    # "baixar" separada, porque baixar o desenho é lê-lo); o que mudou é que ele
    # deixou de ser reimplementado aqui. Manter esta rota viva ao lado da nova
    # deixaria de pé a segunda porta que a fatia existe para fechar.

    @action(detail=True, methods=["post"])
    def publicar(self, request, pk=None):
        """Torna esta revisão a vigente e rebaixa a anterior a superada.

        Atômico e com a linha do **documento** travada: publicar é read-modify-
        write sobre o conjunto de revisões dele, e duas publicações simultâneas
        (o projetista publicando a R02 enquanto o coordenador publica a R03)
        passariam as duas pela checagem antes de qualquer uma gravar. O
        `UniqueConstraint` parcial pegaria a segunda no banco — como 500, não como
        resposta. É o mesmo raciocínio do L5 na baixa de título, e aqui o lock se
        paga pela mesma razão: o que está em jogo é qual desenho o campo executa.
        """
        revisao = self.get_object()
        if revisao.situacao == RevisaoDocumento.Situacao.VIGENTE:
            return Response(
                {"detail": f"A revisão {revisao.revisao} já é a vigente."},
                status=status.HTTP_409_CONFLICT,
            )
        if revisao.situacao == RevisaoDocumento.Situacao.SUPERADA:
            # Republicar uma superada é voltar o canteiro para um desenho antigo.
            # Pode ser legítimo (a R03 foi publicada por engano), mas é decisão
            # com consequência em campo — trata-se como revisão nova, não como
            # um botão que desfaz silenciosamente.
            return Response(
                {"detail": (
                    f"A revisão {revisao.revisao} está superada. Para voltar a este "
                    "desenho, registre-o como uma revisão nova, com o motivo."
                )},
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            documento = (
                DocumentoProjeto.objects.select_for_update()
                .get(pk=revisao.documento_id, tenant_id=revisao.tenant_id)
            )
            (
                RevisaoDocumento.objects
                .filter(documento=documento, situacao=RevisaoDocumento.Situacao.VIGENTE)
                .update(situacao=RevisaoDocumento.Situacao.SUPERADA)
            )
            revisao.situacao = RevisaoDocumento.Situacao.VIGENTE
            revisao.publicado_por = request.user
            revisao.publicado_em = timezone.now()
            revisao.save(update_fields=["situacao", "publicado_por", "publicado_em"])

        return Response(self.get_serializer(revisao).data)

    @action(detail=False, methods=["post"], url_path="publicar-pendentes")
    def publicar_pendentes(self, request):
        """Publica, numa obra, a revisão mais recente de cada documento **sem vigente**.

        **Por que este verbo existe.** A carga em lote do acervo histórico
        (PRA.5b) cria toda revisão em `rascunho`, e com razão — a conferência do
        lote é ato de quem governa o acervo (`documento.edit`), e publicar é ato
        de outra alçada (`revisao.publicar`, §9). Só que sem um verbo em lote a
        segunda alçada ficava impossível de exercer: um acervo de 141 documentos
        exigia 141 cliques, então ninguém publicava e **o canteiro via 141
        pranchas "sem revisão vigente" com o arquivo já convertido e pronto**.
        Medido no acervo de demonstração em 13/08/2026: 159 revisões, todas em
        rascunho, 168 derivadas `pronto`. O desenho estava lá; faltava o ato.

        **O que ele NÃO faz, e é o que o mantém honesto:**

        - **não troca vigente por vigente.** Documento que já tem uma publicada
          fica intocado — trocar o desenho que o campo executa é decisão prancha
          a prancha, com o motivo, e não efeito colateral de um botão de massa;
        - **não republica superada.** Voltar o canteiro a um desenho antigo é o
          409 do `publicar` acima, e vale igual aqui;
        - **não escolhe entre rascunhos por adivinhação.** Quando o documento tem
          vários, publica o de **rótulo maior** (a ordenação do modelo é
          `-revisao`), que é o que "revisão mais recente" significa no carimbo.
          O relatório devolve quais foram, para a decisão poder ser conferida.

        Escopo obrigatório por **obra**: publicar o tenant inteiro de uma vez é
        poder demais para um POST sem alvo, e a tela sempre sabe qual obra está
        aberta.
        """
        obra_id = request.data.get("obra")
        if not obra_id:
            return Response(
                {"detail": "Informe a obra: {\"obra\": <id>}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Escopado pelo `_scope` do mixin — o mesmo que gateia todo queryset
        # deste ViewSet. Filtrar por `request.user.tenant_id` à mão funcionaria
        # e seria a segunda régua de tenancy do arquivo; quando as duas
        # existem, é a cópia que diverge.
        pendentes = (
            self._scope(DocumentoProjeto.objects.filter(obra_id=obra_id, ativo=True))
            .exclude(revisoes__situacao=RevisaoDocumento.Situacao.VIGENTE)
            .filter(revisoes__situacao=RevisaoDocumento.Situacao.RASCUNHO)
            .distinct()
        )

        publicadas, ignorados = [], []
        for documento in pendentes:
            with transaction.atomic():
                travado = (
                    DocumentoProjeto.objects.select_for_update()
                    .filter(pk=documento.pk, tenant_id=documento.tenant_id)
                    .first()
                )
                if travado is None:
                    continue
                # Reconferido DENTRO do lock: entre a lista e a vez deste
                # documento, alguém pode ter publicado uma revisão pela tela.
                # Sem esta releitura, o lote rebaixaria a recém-publicada.
                if RevisaoDocumento.objects.filter(
                    documento=travado, situacao=RevisaoDocumento.Situacao.VIGENTE
                ).exists():
                    ignorados.append({"documento": travado.codigo, "motivo": "ja_tem_vigente"})
                    continue
                escolhida = (
                    RevisaoDocumento.objects
                    .filter(documento=travado, situacao=RevisaoDocumento.Situacao.RASCUNHO)
                    .order_by("-revisao", "-enviado_em")
                    .first()
                )
                if escolhida is None:
                    ignorados.append({"documento": travado.codigo, "motivo": "sem_rascunho"})
                    continue
                escolhida.situacao = RevisaoDocumento.Situacao.VIGENTE
                escolhida.publicado_por = request.user
                escolhida.publicado_em = timezone.now()
                escolhida.save(update_fields=["situacao", "publicado_por", "publicado_em"])
                publicadas.append({"documento": travado.codigo, "revisao": escolhida.revisao})

        return Response({
            "publicadas": len(publicadas),
            "documentos": publicadas,
            "ignorados": ignorados,
        })


class DesenhoProjetoViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """As folhas de uma revisão — nomear e calibrar cada uma.

    **Read-only mais dois verbos**, e não um CRUD: quem cria e apaga desenho é o
    motor, a partir do que está no arquivo. Uma folha criada à mão descreveria um
    desenho que não existe no DWG, e a próxima conversão a apagaria — deixando o
    usuário com a impressão de que o sistema perdeu o trabalho dele.
    """

    queryset = (
        DesenhoProjeto.objects
        .select_related("revisao__documento")
        .prefetch_related("derivadas")
        .all()
    )
    serializer_class = DesenhoProjetoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["revisao", "revisao__documento", "revisao__documento__obra"]
    ordering_fields = ["ordem"]
    # Explícito porque este ViewSet **não** herda de `BasePranchetaViewSet` (é
    # read-only + dois verbos, não um `ModelViewSet`). Omitir a lista deixaria o
    # DRF cair no default global e a segregação de `calibrar` viraria decoração —
    # exatamente o que ela existe para impedir.
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "prancheta"
    pagination_class = PranchetaPageNumberPagination
    required_resource = "prancheta.documento"
    action_permission_map = {
        # Calibrar fica com `documento.edit` — a permissão de quem GOVERNA o
        # acervo — e não com `marcacao.edit`, que o campo tem. É segregação
        # deliberada: quem mede não define a régua. Um operador recalibrando a
        # folha mudaria, de uma vez, o valor de toda medida que qualquer um tirar
        # dali; é decisão do responsável técnico, e é por isso que a referência
        # (os dois pontos + a distância digitada) fica gravada.
        "calibrar": "prancheta.documento.edit",
        # Nomear é da mesma classe, e por um motivo mais simples: o nome viaja
        # para a revisão seguinte por herança. Quem nomeia a folha de hoje nomeia
        # a de todas as próximas, até alguém trocar.
        "renomear": "prancheta.documento.edit",
    }

    @action(detail=True, methods=["post"])
    def renomear(self, request, pk=None):
        """Dá nome a esta folha — `Desenho 2` vira `Poligonal do confrontante norte`.

        **Nome vazio volta ao rótulo automático**, e é por isso que `nome` é
        `blank` no modelo em vez de nascer preenchido: guardar "Desenho 2" como
        valor de fábrica tornaria impossível distinguir o rótulo que o sistema
        gerou do nome que alguém escolheu — e a herança entre revisões passaria a
        propagar um rótulo que ninguém pediu.
        """
        desenho = self.get_object()
        nome = (request.data.get("nome") or "").strip()[:120]
        desenho.nome = nome
        desenho.renomeado_por = request.user
        desenho.renomeado_em = timezone.now()
        # Nome digitado aqui não é mais herdado: a procedência passa a ser esta
        # pessoa, e manter o vínculo antigo faria o histórico atribuir a escolha
        # dela a quem nomeou a revisão passada.
        desenho.herdado_de = None
        desenho.save(update_fields=["nome", "renomeado_por", "renomeado_em", "herdado_de"])
        return Response(self.get_serializer(desenho).data)

    @action(detail=True, methods=["post"])
    def calibrar(self, request, pk=None):
        """Define a escala desta folha a partir de uma cota conhecida.

        O cliente manda dois pontos e quanto eles medem no mundo real; o servidor
        converte para "unidades reais na largura do desenho" — a grandeza que as
        coordenadas normalizadas exigem (ver `DesenhoProjeto.escala_valor`).

        **É por folha, não por revisão**, desde que uma revisão passou a poder
        trazer várias: as coordenadas são normalizadas pela largura da folha, e
        uma régua só descreveria no máximo uma delas — em silêncio, para as
        outras.

        **Recalibrar não reescreve medida antiga**: cada `Medicao` carimbou a
        escala com que foi tirada, e a que ficou para trás passa a se declarar
        `desatualizada`. Reescrever silenciosamente mudaria um número que alguém
        já anotou e levou para o canteiro.
        """
        desenho = self.get_object()
        entrada = CalibracaoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data

        desenho.escala_valor = dados["escala_valor"]
        desenho.escala_unidade = dados["unidade"]
        desenho.escala_referencia = {
            "a": dados["pontos"][0],
            "b": dados["pontos"][1],
            "distancia_real": dados["distancia_real"],
            "unidade": dados["unidade"],
        }
        desenho.escala_calibrada_por = request.user
        desenho.escala_calibrada_em = timezone.now()
        # Carimbar a procedência é o que torna a calibração **soberana**: daqui
        # em diante nenhuma reconversão sobrescreve esta régua com a que o
        # cabeçalho do arquivo declara (`pode_derivar_escala`). Quem conferiu a
        # cota no desenho sabe mais que o `$INSUNITS`.
        desenho.escala_origem = RevisaoDocumento.OrigemEscala.CALIBRADA
        desenho.save(update_fields=[
            "escala_valor", "escala_unidade", "escala_referencia",
            "escala_calibrada_por", "escala_calibrada_em", "escala_origem",
        ])
        recalculadas = recalcular_medidas(desenho)
        dados = self.get_serializer(desenho).data
        # A tela precisa saber que houve conversão em massa para poder avisar —
        # "3 medidas foram recalculadas" é a diferença entre a pessoa confiar no
        # número novo e achar que a tela se atrapalhou.
        return Response({**dados, "medidas_recalculadas": recalculadas})


class DerivadaProjetoViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Só leitura — quem escreve derivada é o pipeline do PRA.1.

    Não tem recurso de permissão próprio: ver a derivada é ver o documento em
    outro formato, e uma permissão separada daria a falsa impressão de que se
    pode liberar uma sem a outra.
    """

    queryset = DerivadaProjeto.objects.select_related("revisao").all()
    serializer_class = DerivadaProjetoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "prancheta"
    required_resource = "prancheta.documento"
    pagination_class = PranchetaPageNumberPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["revisao", "tipo", "motor", "estado"]

    # A ação `arquivo/` saiu na PRA.5, junto com a da revisão — agora é
    # `/api/impexp/prancheta.acervo/arquivo/derivada/<id>/?v=<versão>`. A
    # derivada em erro ou ainda convertendo continua respondendo **404** (não tem
    # binário, e servir bytes vazios faria a tela desenhar o nada): o motor
    # traduz o `EntregaInvalida` do gancho, e o `?v=` do D51 segue na URL que o
    # serializer publica.


# ===========================================================================
# PRA.3 — marcar e medir
# ===========================================================================
class MarcacaoViewSet(BasePranchetaViewSet):
    """Os tópicos BCF — onde a Prancheta deixa de mostrar e passa a resolver.

    **Três permissões, e a terceira é a que importa.** `view` e `edit` são o
    CRUD; `prancheta.marcacao.resolver` é o verbo separado, e ele existe pela
    mesma razão de `publicar`: quem aponta o problema não é quem declara que
    ele acabou. O `campo` recebe `view`+`edit` de fábrica — apontar é
    literalmente o trabalho dele — e **não** recebe `resolver`, senão o
    apontamento se fecharia sozinho antes de o projetista responder.
    """

    queryset = (
        Marcacao.objects
        .select_related(
            "revisao", "revisao__documento", "responsavel", "criado_por", "resolvido_por",
        )
        .prefetch_related("comentarios__autor", "pontos_de_vista", "medicoes")
        .all()
    )
    serializer_class = MarcacaoSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = {
        "revisao": ["exact"],
        "revisao__documento": ["exact"],
        # O eixo da tela: as marcações de uma OBRA, não de um documento. É a
        # mesma razão de `documento__obra` existir no viewset de revisões — a
        # pergunta do canteiro é sobre a obra em que se está.
        "revisao__documento__obra": ["exact"],
        "situacao": ["exact", "in"],
        "tipo": ["exact"],
        "prioridade": ["exact"],
        "responsavel": ["exact"],
    }
    search_fields = ["titulo", "descricao"]
    ordering_fields = ["criado_em", "prazo", "prioridade"]
    required_resource = "prancheta.marcacao"
    action_permission_map = {
        "situacao": "prancheta.marcacao.resolver",
    }
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        """Dois filtros que não cabem em `filterset_fields` por dependerem de
        *quem pergunta* e do vocabulário de "aberta"."""
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("minhas") in ("1", "true"):
            usuario = self.request.user
            # E-mail junto do id: a marcação que veio de um BCF pode ter chegado
            # endereçada ao e-mail de alguém que TEM login mas não foi casado na
            # importação (cadastro sem e-mail, grafia diferente). Quem abre a
            # fila espera vê-la.
            filtro = Q(responsavel=usuario)
            if getattr(usuario, "email", ""):
                filtro |= Q(responsavel__isnull=True, responsavel_email__iexact=usuario.email)
            qs = qs.filter(filtro)
        if params.get("abertas") in ("1", "true"):
            qs = qs.filter(situacao__in=Marcacao.SITUACOES_ABERTAS)
        return qs

    @action(detail=True, methods=["post"])
    def comentar(self, request, pk=None):
        """Responde no tópico. Comentar é `edit`, não `resolver`: a conversa é de
        todo mundo, fechar o assunto não."""
        marcacao = self.get_object()
        entrada = ComentarioMarcacaoSerializer(
            data={**request.data, "marcacao": marcacao.pk}, context={"request": request},
        )
        entrada.is_valid(raise_exception=True)
        comentario = entrada.save(tenant=marcacao.tenant, autor=request.user)
        return Response(
            ComentarioMarcacaoSerializer(comentario).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def situacao(self, request, pk=None):
        """Move o tópico entre aberto e fechado — o verbo de alçada da fatia.

        Grava `resolvido_por`/`resolvido_em` ao sair do conjunto de abertas e os
        **limpa** ao reabrir: um tópico reaberto que continuasse carimbado como
        resolvido por alguém acusaria essa pessoa de um encerramento que a
        realidade desmentiu.
        """
        marcacao = self.get_object()
        nova = request.data.get("situacao")
        validas = {opcao.value for opcao in Marcacao.Situacao}
        if nova not in validas:
            return Response(
                {"detail": f"Situação inválida. Use uma de: {', '.join(sorted(validas))}.",
                 "situacoes": sorted(validas)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        estava_aberta = marcacao.aberta
        marcacao.situacao = nova
        campos = ["situacao"]
        if estava_aberta and not marcacao.aberta:
            marcacao.resolvido_por = request.user
            marcacao.resolvido_em = timezone.now()
            campos += ["resolvido_por", "resolvido_em"]
        elif not estava_aberta and marcacao.aberta:
            marcacao.resolvido_por = None
            marcacao.resolvido_em = None
            campos += ["resolvido_por", "resolvido_em"]
        marcacao.save(update_fields=campos)

        # Comentário automático do próprio ato: sem ele, o tópico exportado
        # chegaria ao escritório mudando de status sem dizer quem mudou nem
        # quando — e o BCF só carrega autoria dentro do comentário.
        ComentarioMarcacao.objects.create(
            tenant=marcacao.tenant, marcacao=marcacao, autor=request.user,
            texto=f"Situação alterada para “{marcacao.get_situacao_display()}”.",
        )

        # **Invalida o cache do prefetch antes de serializar.** O `get_object()`
        # trouxe `comentarios` pelo `prefetch_related`, e esse cache foi montado
        # ANTES do comentário acima — serializar direto devolveria a conversa sem
        # a linha que este próprio ato acabou de escrever. É o idioma que o
        # `UpdateModelMixin` do DRF usa pela mesma razão, e o defeito só aparece
        # no teste que olha a RESPOSTA (o unitário que consultava o banco
        # passava): a tela mostraria o encerramento sem o registro dele até o
        # próximo refetch.
        if getattr(marcacao, "_prefetched_objects_cache", None):
            marcacao._prefetched_objects_cache = {}
        return Response(self.get_serializer(marcacao).data)

    @action(detail=True, methods=["post"], url_path="ponto-de-vista")
    def ponto_de_vista(self, request, pk=None):
        """Anexa o recorte da tela (e a câmera, quando é modelo 3D).

        O snapshot é **opcional por desenho**: a captura acontece no navegador, e
        navegador de celular velho falha nela. Um ponto de vista sem imagem ainda
        é um ponto de vista válido no BCF — bloquear a marcação por causa da foto
        perderia o apontamento para salvar o enfeite.

        **PRA.5b — a imagem entra pela porta única.** Até aqui ela era gravada
        direto do `request.FILES` com uma conferência de tamanho à mão: o formato
        nunca foi olhado, então qualquer binário com o nome certo virava
        `PontoDeVista.snapshot` e era servido de volta como `image/png` pelo
        `entregar_arquivo`. É a mesma forma do [D75](../../docs/historico-correcoes.md),
        na metade que ele não alcançou — e a porta cobre as duas pontas de uma
        vez: reconhece a imagem pelos **bytes** e aplica o teto do recurso.
        """
        marcacao = self.get_object()
        imagem = request.FILES.get("snapshot")
        # **Admitir ANTES de criar o ponto de vista**, e é o que muda de ordem
        # aqui: a recusa passou a ser possível depois da PRA.5b, e criar a linha
        # primeiro deixaria um ponto de vista órfão — sem imagem e sem ninguém
        # para apagá-lo — toda vez que a porta dissesse não.
        if imagem is not None:
            porta.admitir(
                imagem, recurso_id=RECURSO_MARCACAO, user=request.user, campo="snapshot",
            )
        ponto = PontoDeVista.objects.create(
            tenant=marcacao.tenant,
            marcacao=marcacao,
            camera=request.data.get("camera") or {},
        )
        if imagem is not None:
            ponto.snapshot = imagem
            ponto.save(update_fields=["snapshot"])
        return Response(PontoDeVistaSerializer(ponto).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def bcf(self, request):
        """Exporta as marcações filtradas como `.bcfzip`.

        Usa **os mesmos filtros da listagem** (`?revisao__documento__obra=`,
        `?abertas=1`, `?minhas=1`): o que a tela mostra é o que o arquivo leva,
        e não há um segundo conjunto de regras para o usuário entender.

        Atrás da parede comercial do formato `bcf` — marcar dentro do sistema
        vem com o módulo; **atravessar para o software do projetista** é o que o
        plano vende.
        """
        exigir_formato_contratado("bcf", request.user)
        marcacoes = self.filter_queryset(self.get_queryset())
        conteudo = interop.exportar(marcacoes)

        resposta = HttpResponse(conteudo, content_type="application/octet-stream")
        resposta["Content-Disposition"] = 'attachment; filename="marcacoes.bcfzip"'
        resposta["X-Content-Type-Options"] = "nosniff"
        # Ao contrário do acervo, isto NÃO é imutável: o mesmo filtro amanhã dá
        # outro arquivo, porque a marcação muda de situação. Cachear seria
        # entregar ao projetista a caixa de ontem.
        resposta["Cache-Control"] = "no-store"
        return resposta

    @action(detail=False, methods=["post"], url_path="importar-bcf")
    def importar_bcf(self, request):
        """Traz de volta o que o escritório respondeu.

        Exige a **revisão de destino** porque o BCF não diz a qual prancha nossa
        o tópico pertence — ele é centrado em modelo, e o vínculo com o acervo é
        nosso. Adivinhar pela primeira revisão da obra penduraria a marcação no
        desenho errado, que em campo é pior que não importar.

        **PRA.5b — o `.bcfzip` entra pela porta única**, que é a última porta de
        upload da Prancheta fora do motor ([D75](../../docs/historico-correcoes.md) item 2).
        O risco aqui sempre foi menor que o do acervo — quem abre o pacote é o
        nosso leitor de zip, não o LibreDWG —, mas as três coisas que faltavam são
        as mesmas: o formato era decidido pelo **nome**, o teto de entrada era o
        orçamento de *descompressão* (200 MB) usado como se fosse teto de upload,
        e o arquivo não passava pelo lugar onde o antivírus vai entrar (D74).
        """
        exigir_formato_contratado("bcf", request.user)

        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            return Response(
                {"detail": "Envie o arquivo BCF no campo `arquivo`."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        revisao_id = request.data.get("revisao")
        # `_scope` do mixin de ViewSet (o `scope_qs` é o irmão das APIViews puras):
        # a revisão de destino não passa pelo `get_object()` deste viewset, então
        # o escopo de tenant tem de ser aplicado à mão — sem isso, um id de outra
        # empresa penduraria marcações no acervo dela.
        revisao = self._scope(RevisaoDocumento.objects.all()).filter(pk=revisao_id).first()
        if revisao is None:
            return Response(
                {"detail": "Informe em `revisao` a prancha a que estas marcações pertencem."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # **Depois do destino, e de propósito.** A porta lê o arquivo inteiro para
        # calcular o SHA-256, e pagar essa leitura por um pedido que já vai falhar
        # em "qual prancha?" seria gastar banda e CPU para dar a mesma resposta.
        # É a mesma economia que o `validar_entrada` aplica internamente.
        porta.admitir(
            arquivo, recurso_id=RECURSO_MARCACAO, user=request.user, campo="arquivo",
        )
        # O teto de 50 MB da entrada é do registry e vale para o pacote **como
        # chega**; `MAX_DESCOMPRIMIDO_BYTES` continua valendo dentro do `bcf.ler`
        # e mede outra coisa — o quanto ele vira ao ser aberto. Um zip de 2 MB
        # pode declarar 40 GB, e é essa a guarda que não sai daqui.

        try:
            resumo = interop.importar(
                arquivo.read(), revisao=revisao, usuario=request.user,
                tenant=request.user.tenant,
            )
        except bcf.BcfInvalido as erro:
            # A mensagem é escrita para o usuário (ver `bcf.py`), então sobe como
            # está. 400 e não 500: o arquivo é dele, o defeito também.
            return Response({"detail": str(erro)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(resumo, status=status.HTTP_200_OK)


class MedicaoViewSet(BasePranchetaViewSet):
    """Medidas sobre a prancha.

    Compartilha o recurso `prancheta.marcacao` de propósito: medir e apontar são
    o mesmo trabalho — a medida quase sempre vira o argumento do apontamento
    ("está 12 cm fora"). Uma permissão só para medir daria um interruptor que
    ninguém saberia quando desligar.
    """

    queryset = Medicao.objects.select_related("revisao", "marcacao", "criado_por").all()
    serializer_class = MedicaoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["revisao", "marcacao", "tipo"]
    ordering_fields = ["criado_em"]
    required_resource = "prancheta.marcacao"


class PontoDeVistaViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Só leitura + a entrega do snapshot. Quem cria é a ação na marcação.

    Existe como rota própria pela mesma razão de `derivadas`: o arquivo precisa
    de uma URL gateada, e ela tem de ser estável para o `<img>` da tela.
    """

    queryset = PontoDeVista.objects.select_related("marcacao").all()
    serializer_class = PontoDeVistaSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "prancheta"
    required_resource = "prancheta.marcacao"
    pagination_class = PranchetaPageNumberPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["marcacao"]

    # A ação `arquivo/` saiu na PRA.5 — agora é
    # `/api/impexp/prancheta.marcacao/arquivo/snapshot/<id>/`. Recurso próprio, e
    # não o do acervo, porque o gate aqui sempre foi `prancheta.marcacao`
    # (`required_resource` acima): pendurá-lo no acervo o teria trocado por
    # `prancheta.documento` em silêncio, e para mais gente.


class AcervoView(TenantScopedAPIViewMixin, views.APIView):
    """`GET /api/prancheta/acervo/?obra=<id>` — o acervo da obra numa chamada.

    É a tela do canteiro traduzida em endpoint. Devolve os documentos agrupados
    por disciplina, cada um já com a revisão vigente embutida, mais a contagem do
    que **falta decidir** — documento sem vigente e revisão em rascunho.

    Existe separado do `documentos/` paginado porque a pergunta é outra: a lista
    responde "o que existe", e esta responde "o que eu executo hoje, e o que
    ainda não foi resolvido". Montar isso no cliente exigiria buscar todas as
    revisões de todos os documentos e cruzar — N chamadas no celular do canteiro,
    que é onde a conexão é pior.
    """

    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "prancheta"
    required_permission = "prancheta.documento.view"

    def get(self, request):
        obra_id = request.query_params.get("obra")
        if not obra_id:
            return Response(
                {"detail": "Informe a obra: ?obra=<id>."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        documentos = (
            self.scope_qs(DocumentoProjeto.objects.filter(obra_id=obra_id, ativo=True))
            .select_related("obra", "etapa")
            # `revisoes__derivadas` e não só `revisoes`: desde o PRA.1 o resumo da
            # revisão diz se dá para abrir, e sem o prefetch da segunda camada
            # cada card do acervo custaria uma query — o N+1 volta pela porta que
            # o `revisao_vigente` já havia fechado.
            .prefetch_related(
                "revisoes__derivadas",
                "revisoes__desenhos__derivadas",
                # PRA.9c: sem este prefetch, `codigos_de_disciplina` faria uma
                # query por documento — 141 leituras para montar a fileira de
                # filtro, que é o N+1 que o resto deste queryset já fechou.
                "vinculos_disciplina",
            )
            .order_by("disciplina", "codigo")
        )
        # O índice entra no contexto para os 141 documentos resolverem rótulo e
        # cor sem uma leitura da tabela cada — o N+1 pela porta do rótulo.
        catalogo = disciplinas.catalogo(self.scope_qs)
        dados = DocumentoProjetoSerializer(
            documentos,
            many=True,
            context={
                "request": request,
                "indice_disciplinas": {i["codigo"]: i for i in catalogo},
            },
        ).data

        # **A prancha entra em TODAS as suas disciplinas** (PRA.9c). É a semântica
        # de tag: quem filtra por "Elétrica" quer ver a planta de forro que também
        # é arquitetura, e escondê-la seria o mesmo que não ter classificado.
        #
        # Consequência assumida: a soma dos grupos passa a ser maior que
        # `total_documentos`. Não é inconsistência — é o que "várias disciplinas"
        # significa —, e por isso o total continua saindo de `dados` e não da soma.
        por_disciplina: dict[str, list] = {}
        for item in dados:
            codigos = [d["codigo"] for d in item.get("disciplinas") or []]
            for codigo in codigos or [item["disciplina"]]:
                por_disciplina.setdefault(codigo, []).append(item)

        sem_vigente = [d["codigo"] for d in dados if d["vigente"] is None]
        rascunhos = self.scope_qs(
            RevisaoDocumento.objects.filter(
                documento__obra_id=obra_id,
                situacao=RevisaoDocumento.Situacao.RASCUNHO,
            )
        ).count()
        falhas = self.scope_qs(
            DerivadaProjeto.objects.filter(
                revisao__documento__obra_id=obra_id,
                estado=DerivadaProjeto.Estado.ERRO,
            )
        )
        # Contagens separadas **por quem age**, e não uma soma: mandar o operador
        # do canteiro abrir chamado por um upsell, ou o dono comprar um plano por
        # causa de um binário faltando no servidor, é o que a distinção entre
        # `motor_insuficiente` e `motor_indisponivel` existe para evitar (planta
        # §9). A PRA.1b acrescentou os dois últimos atores.
        exigem_upgrade = falhas.filter(
            erro_motivo=DerivadaProjeto.MotivoErro.MOTOR_INSUFICIENTE
        ).count()
        # **Quem enviou resolve**: a geometria está em XREF que não subiu junto.
        # É item de fila de verdade — tem ação, dono e desfecho —, e é por isso
        # que não fica no mesmo balde do desenho vazio.
        aguardando_anexo = falhas.filter(
            erro_motivo=DerivadaProjeto.MotivoErro.REFERENCIA_AUSENTE
        ).count()
        # **Ninguém age.** O arquivo não tem desenho, ou o DWG não traz a
        # miniatura que o CAD grava. Aparece para poder ser SUBTRAÍDO do total:
        # sem esta linha, "conversões com erro" cresce com o que nunca vai ser
        # consertado e a fila perde a credibilidade que a torna útil.
        sem_desenho = falhas.filter(
            erro_motivo__in=[
                DerivadaProjeto.MotivoErro.DESENHO_VAZIO,
                DerivadaProjeto.MotivoErro.SEM_PREVIEW,
            ]
        ).count()

        abertas = self.scope_qs(
            Marcacao.objects.filter(
                revisao__documento__obra_id=obra_id,
                situacao__in=Marcacao.SITUACOES_ABERTAS,
            )
        )
        minhas = abertas.filter(responsavel=request.user)
        if getattr(request.user, "email", ""):
            # Mesmo alcance do `?minhas=1` da listagem: a marcação importada de
            # BCF pode ter chegado endereçada ao e-mail sem casar com o usuário.
            minhas = abertas.filter(
                Q(responsavel=request.user)
                | Q(responsavel__isnull=True, responsavel_email__iexact=request.user.email)
            )

        indice = {i["codigo"]: i for i in catalogo}
        return Response({
            "obra": int(obra_id),
            "total_documentos": len(dados),
            # Rótulo e cor viajam **no grupo**, e não só dentro de cada documento:
            # a fileira de filtro da grade os desenha, e lê-los do primeiro
            # documento do grupo (o que a tela fazia) deixaria a disciplina sem
            # prancha invisível e a renomeada desatualizada até alguém recarregar.
            "disciplinas": [
                {
                    "disciplina": chave,
                    "rotulo": disciplinas.rotulo(chave, indice),
                    "cor": disciplinas.cor(chave, indice),
                    "documentos": itens,
                }
                for chave, itens in por_disciplina.items()
            ],
            # O vocabulário inteiro — inclusive o que ainda não tem prancha, que é
            # justamente o que o seletor do envio precisa oferecer.
            "catalogo_disciplinas": catalogo,
            # A fila de decisão do cockpit (planta §11) — completa desde o PRA.3.
            "requer_decisao": {
                "documentos_sem_revisao_vigente": sem_vigente,
                "revisoes_em_rascunho": rascunhos,
                "conversoes_com_erro": falhas.count(),
                "conversoes_que_exigem_upgrade": exigem_upgrade,
                "conversoes_aguardando_anexo": aguardando_anexo,
                "conversoes_sem_desenho": sem_desenho,
                # A linha que a PRA.0 declarou e deixou por preencher.
                "marcacoes_abertas": abertas.count(),
                "marcacoes_atribuidas_a_mim": minhas.count(),
                # Marcação viva sobre desenho que já não vale: ninguém resolveu,
                # e o desenho mudou embaixo. É a pergunta que só aparece quando o
                # acervo e a marcação convivem — e a resposta ("ainda vale?" /
                # "já era") é humana, por isso é fila e não limpeza automática.
                "marcacoes_em_revisao_superada": abertas.filter(
                    revisao__situacao=RevisaoDocumento.Situacao.SUPERADA
                ).count(),
            },
        })
