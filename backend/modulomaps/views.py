# backend/modulomaps/views.py
"""API do Maps — `/api/maps/`.

O gate segue a divisão da planta §2, e ela aparece no código como duas bases
diferentes de ViewSet:

- `BaseFundacaoViewSet` — **sem** `RequireModule`. `Local` é cadastro: quem não
  assina Maps continua sabendo onde ficam a obra e o almoxarifado, senão SIL e
  SCM perderiam a dimensão espacial de quem não pagou por um módulo que eles
  não usam.
- `BaseCamadaViewSet` — `RequireModule("maps")` + permissão do recurso. Acervo
  de ortofoto, plano de voo e roteirização têm custo próprio e são o produto.
"""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.busca import BuscaSemAcento
from rest_framework import filters, permissions, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from nucleo.permissions import RequireModule, RequirePermission
from nucleo.tenancy import TenantScopedAPIViewMixin, TenantScopedViewSetMixin

from . import deteccao, rotas as motor_rotas, services, voo
from .models import (
    Camada, Feicao, Geofence, Local, Ortofoto, ParadaRota, Precisao, PlanoVoo, Rota,
)
from .pagination import MapsPageNumberPagination
from .serializers import (
    CamadaSerializer, FeicaoSerializer, GeofenceSerializer, LocalResumoSerializer,
    LocalSerializer, OrtofotoSerializer, ParadaRotaSerializer, PlanoVooSerializer,
    RotaSerializer,
)

# Depois de quantos dias uma ortofoto deixa de responder "como está a obra hoje".
# Um trimestre é o intervalo em que um canteiro ativo muda de cara; o número é
# knob porque obra parada e obra em pico têm ritmos diferentes.
DIAS_ORTOFOTO_VENCIDA = 90


def _poligono_do_bbox(texto: str):
    """`?bbox=minLon,minLat,maxLon,maxLat` → Polygon 4326, ou `None`."""
    from django.contrib.gis.geos import Polygon

    try:
        minx, miny, maxx, maxy = (float(p) for p in (texto or "").split(","))
    except (TypeError, ValueError):
        return None
    return Polygon.from_bbox((minx, miny, maxx, maxy))


class MapsStatusView(views.APIView):
    """Status do módulo Maps. Confirma entitlement antes de qualquer dado."""

    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "maps"

    def get(self, request):
        return Response({
            "modulo": "maps",
            "status": "ativo",
            # A tela precisa saber o que a instalação consegue fazer para não
            # oferecer botão que vai falhar — mesma régua de "dados honestos".
            "provedores": {
                "geocodificacao_endereco": bool(getattr(settings, "NOMINATIM_URL", "")),
                "motor_rota": bool(getattr(settings, "OSRM_URL", "")),
                "tiles_raster": bool(getattr(settings, "TITILER_URL", "")),
            },
        })


# ---------------------------------------------------------------------------
# Bases
# ---------------------------------------------------------------------------
class BaseFundacaoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Metade fundação: sem entitlement, com permissão de campo."""

    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    pagination_class = MapsPageNumberPagination


class BaseCamadaViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Metade vendável: entitlement `maps` + permissão do recurso."""

    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "maps"
    pagination_class = MapsPageNumberPagination


# ---------------------------------------------------------------------------
# MAP.0 — Local
# ---------------------------------------------------------------------------
class LocalViewSet(BaseFundacaoViewSet):
    # `unidade__empreendimento` entra porque o detalhe da unidade (medidas,
    # confrontações, conferência da rua) nomeia o empreendimento: sem ele seriam
    # N consultas numa tabela que carrega 100 linhas por página.
    queryset = Local.objects.select_related(
        "obra", "empreendimento", "fornecedor", "local_estoque",
        "unidade", "unidade__empreendimento",
    ).all()
    serializer_class = LocalSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_fields = [
        "tipo", "precisao", "uf", "cidade", "ativo", "obra", "empreendimento",
        "fornecedor", "unidade",
    ]
    search_fields = ["nome", "logradouro", "bairro", "cidade"]
    ordering_fields = ["nome", "cidade"]
    required_resource = "mapa.local"

    def perform_create(self, serializer):
        """Local nasce e já tenta se localizar.

        Se a criação não geocodificasse, todo cadastro novo entraria na fila de
        "sem coordenada" e o mapa da empresa começaria vazio — o usuário teria
        de pedir manualmente aquilo que o sistema sabe fazer sozinho. Um pin
        enviado à mão no POST é respeitado: a cascata não sobrescreve `exata`.
        """
        super().perform_create(serializer)
        local = serializer.instance
        if local.ponto is not None:
            local.precisao = Precisao.EXATA
            local.fonte = local.fonte or "manual"
            local.save(update_fields=["precisao", "fonte", "atualizado_em"])
            return
        services.completar_localidade(local)
        services.geocodificar_local(local)

    @action(detail=True, methods=["post"])
    def geocodificar(self, request, pk=None):
        """Roda a cascata neste local. `?forcar=1` reprocessa quem já tem ponto.

        Nem `forcar` passa por cima de um ponto `exata`: pin arrastado à mão é
        verdade de campo, e nenhum provedor tem autoridade para desfazê-lo.
        """
        local = self.get_object()
        services.completar_localidade(local)
        mudou = services.geocodificar_local(
            local, forcar=request.query_params.get("forcar") in ("1", "true", "True")
        )
        local.refresh_from_db()
        return Response({
            "geocodificado": mudou,
            "motivo": "" if mudou else self._motivo_sem_mudanca(local),
            "local": LocalSerializer(local).data,
        })

    @staticmethod
    def _motivo_sem_mudanca(local) -> str:
        if local.precisao == Precisao.EXATA:
            return "O local já tem coordenada exata (pin ou EXIF) — a cascata não sobrescreve."
        if local.ponto is not None:
            return "Já tem coordenada. Use ?forcar=1 para reprocessar."
        return (
            "Nenhum provedor resolveu este endereço. Confira CEP/cidade/UF, "
            "ou posicione o pin à mão."
        )

    @action(detail=False, methods=["get"])
    def proximos(self, request):
        """`?de=<local_id>&raio_km=50[&tipo=fornecedor]` — vizinhança de um local.

        É o que torna possível "fornecedores num raio de X km desta obra", que
        até aqui era simplesmente impossível: o endereço era texto livre.
        """
        origem = Local.objects.filter(
            pk=request.query_params.get("de") or 0,
            tenant_id=getattr(request.user, "tenant_id", None),
        ).first()
        if origem is None or origem.ponto is None:
            return Response(
                {"detail": "Informe `de` com um local que já tenha coordenada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            raio = float(request.query_params.get("raio_km") or 50)
        except ValueError:
            raio = 50.0

        qs = self.filter_queryset(self.get_queryset()).exclude(pk=origem.pk)
        if request.query_params.get("tipo"):
            qs = qs.filter(tipo=request.query_params["tipo"])
        achados = services.proximos(qs, origem.ponto, raio)[:200]
        return Response({
            "origem": LocalResumoSerializer(origem).data,
            "raio_km": raio,
            "resultados": LocalResumoSerializer(achados, many=True).data,
        })


# ---------------------------------------------------------------------------
# MAP.3 — camadas e feições
# ---------------------------------------------------------------------------
class CamadaViewSet(BaseCamadaViewSet):
    queryset = Camada.objects.all()
    serializer_class = CamadaSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento]
    filterset_fields = ["obra", "visivel"]
    search_fields = ["nome", "descricao"]
    required_resource = "mapa.feicao"

    def get_queryset(self):
        from django.db.models import Count

        return super().get_queryset().annotate(total_feicoes=Count("feicoes"))


class FeicaoViewSet(BaseCamadaViewSet):
    queryset = Feicao.objects.select_related("camada").all()
    serializer_class = FeicaoSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento]
    filterset_fields = ["camada", "obra", "tipo", "grupo", "data_referencia"]
    search_fields = ["nome"]
    required_resource = "mapa.feicao"

    def get_queryset(self):
        """Recorte **espacial e temporal** — as duas dimensões do acervo.

        `?bbox=` é o que impede o mapa de baixar o país inteiro ao dar zoom numa
        quadra; `?ate=` é o que faz o antes/depois funcionar (o mapa de uma data
        mostra o que existia naquela data, não o que existe hoje).
        """
        qs = super().get_queryset()
        caixa = _poligono_do_bbox(self.request.query_params.get("bbox"))
        if caixa is not None:
            qs = qs.filter(geom__intersects=caixa)
        desde = self.request.query_params.get("desde")
        ate = self.request.query_params.get("ate")
        if desde:
            qs = qs.filter(data_referencia__gte=desde)
        if ate:
            qs = qs.filter(data_referencia__lte=ate)
        return qs


class OrtofotoViewSet(BaseCamadaViewSet):
    queryset = Ortofoto.objects.select_related("obra").all()
    serializer_class = OrtofotoSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento]
    filterset_fields = ["obra", "data_voo"]
    search_fields = ["titulo", "chunk_uuid"]
    required_resource = "mapa.ortofoto"

    def get_queryset(self):
        qs = super().get_queryset()
        caixa = _poligono_do_bbox(self.request.query_params.get("bbox"))
        if caixa is not None:
            qs = qs.filter(bbox__intersects=caixa)
        return qs

    @action(detail=True, methods=["get"], url_path=r"tiles/(?P<z>\d+)/(?P<x>\d+)/(?P<y>\d+)")
    def tiles(self, request, pk=None, z=None, x=None, y=None):
        """Tile do COG desta ortofoto, **servido pelo backend**.

        A alternativa era mandar o browser direto no COG do drone, cujo
        `/chunks/*/assets/*` é `permitAll` por desenho do visualizador (achado
        **S10**). Trazer o acervo para o mapa da empresa por aquele caminho
        ampliaria a superfície pública para todo o histórico de voos. Aqui o
        tile passa pelo mesmo gate do resto: autenticado, com entitlement e
        escopado por tenant — o custo é um salto de rede, e vale.
        """
        base = getattr(settings, "TITILER_URL", "")
        ortofoto = self.get_object()
        if not base or not ortofoto.url_cog:
            return Response(
                {"detail": "Servidor de tiles não configurado nesta instalação (TITILER_URL) "
                           "ou a ortofoto não tem COG publicado."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        import requests

        url = f"{base.rstrip('/')}/cog/tiles/{z}/{x}/{y}.png"
        try:
            resp = requests.get(
                url, params={"url": ortofoto.url_cog},
                timeout=getattr(settings, "GEO_TIMEOUT", (5, 15)),
            )
            resp.raise_for_status()
        except requests.RequestException:
            # Tile que falta não é erro de aplicação: é buraco na cobertura, e o
            # MapLibre trata 404 como "nada para desenhar aqui".
            return HttpResponse(status=status.HTTP_404_NOT_FOUND)
        return HttpResponse(resp.content, content_type="image/png")


# ---------------------------------------------------------------------------
# MAP.4 — planos de voo
# ---------------------------------------------------------------------------
class PlanoVooViewSet(BaseCamadaViewSet):
    queryset = PlanoVoo.objects.select_related("obra").all()
    serializer_class = PlanoVooSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento]
    filterset_fields = ["obra", "tipo"]
    search_fields = ["nome"]
    required_resource = "mapa.plano_voo"

    @action(detail=False, methods=["post"], url_path="do-local")
    def do_local(self, request):
        """Cria o plano a partir de um `Local` — a área vem do perímetro ou do raio.

        **Por que existe.** O `PlanoVoo.area` é um polígono, e até aqui a única
        forma de o desenhar era pelo admin ou por um POST à mão com GeoJSON. Na
        tela, a aba Planos de voo só sabia **listar** — então ela nunca saía do
        vazio, e o módulo parecia quebrado a quem abria ("não consigo ver plano
        de voo"). É o mesmo buraco que o `geofences/gerar/` já tinha fechado para
        a cerca, e a saída é a mesma porta: o polígono nasce de um local que a
        empresa já cadastrou.

        **A ordem é a do `gerar_geofence`, e pelo mesmo motivo:** perímetro real
        do canteiro primeiro, raio depois. Quem desenhou a área da obra tem o
        polígono certo, e cobri-lo com um círculo seria perder precisão de graça.
        A resposta diz de onde a área veio — `perimetro` ou `raio` —, porque um
        voo planejado sobre um círculo de 150 m em volta do pin **não** é um voo
        planejado sobre o canteiro, e quem vai autorizar precisa saber a diferença.
        """
        local = Local.objects.filter(
            pk=request.data.get("local") or 0,
            tenant_id=getattr(request.user, "tenant_id", None),
        ).first()
        if local is None:
            return Response({"detail": "Informe um local da sua empresa."},
                            status=status.HTTP_400_BAD_REQUEST)

        raio_pedido = request.data.get("raio_m")
        raio_m = int(raio_pedido) if raio_pedido else None
        if local.area is not None and raio_m is None:
            area, origem_da_area, raio = local.area, "perimetro", None
        else:
            if local.ponto is None:
                return Response(
                    {"detail": "O local não tem coordenada: geocodifique-o antes de planejar o voo."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raio = raio_m or 150
            area, origem_da_area = services.poligono_do_raio(local.ponto, raio), "raio"

        dados = {
            "nome": request.data.get("nome") or f"Voo — {local.nome}",
            "tipo": request.data.get("tipo") or PlanoVoo.Tipo.GRID,
            "obra_id": local.obra_id,
            "area": area,
            "tenant_id": getattr(request.user, "tenant_id", None),
        }
        for campo in ("gsd_alvo_cm", "sobreposicao_frontal_pct", "sobreposicao_lateral_pct"):
            if request.data.get(campo) not in (None, ""):
                dados[campo] = request.data[campo]

        plano = PlanoVoo.objects.create(**dados)
        return Response(
            {
                "plano": PlanoVooSerializer(plano).data,
                "origem_da_area": origem_da_area,
                "raio_m": raio,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def calcular(self, request, pk=None):
        """Gera o traçado, a altura e as estimativas a partir da área e do GSD."""
        plano = self.get_object()
        try:
            resultado = voo.calcular(plano)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        plano.linha = resultado["linha"]
        plano.waypoints = resultado["waypoints"]
        plano.distancia_m = resultado["distancia_m"]
        plano.duracao_min = resultado["duracao_min"]
        plano.fotos_estimadas = resultado["fotos_estimadas"]
        plano.altura_m = resultado["altura_m"]
        plano.calculado_em = timezone.now()
        plano.save(update_fields=[
            "linha", "waypoints", "distancia_m", "duracao_min",
            "fotos_estimadas", "altura_m", "calculado_em",
        ])
        return Response({
            "plano": PlanoVooSerializer(plano).data,
            # Devolvidos à parte porque são a MEMÓRIA DE CÁLCULO: quem confere um
            # voo quer ver de onde saiu a altura, não só o número dela.
            "memoria": {
                "altura_m": resultado["altura_m"],
                "espacamento_m": resultado["espacamento_m"],
                "intervalo_foto_m": resultado["intervalo_foto_m"],
                "waypoints": len(resultado["waypoints"]),
            },
        })

    @action(detail=True, methods=["get"])
    def exportar(self, request, pk=None):
        """`?formato=kml|plan|litchi|wpml` — o plano no formato que o drone lê."""
        plano = self.get_object()
        formato = (request.query_params.get("formato") or "kml").lower()
        if formato not in voo.FORMATOS:
            return Response(
                {"detail": f"Formato desconhecido. Use um de: {', '.join(voo.FORMATOS)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not plano.waypoints:
            return Response(
                {"detail": "Calcule o plano antes de exportar (POST calcular/)."},
                status=status.HTTP_409_CONFLICT,
            )
        gerar, mime, extensao = voo.FORMATOS[formato]
        conteudo = gerar(plano)
        nome = "".join(c if c.isalnum() or c in "-_" else "_" for c in plano.nome)[:60]
        resposta = HttpResponse(conteudo, content_type=mime)
        resposta["Content-Disposition"] = f'attachment; filename="{nome}.{extensao}"'
        return resposta


# ---------------------------------------------------------------------------
# MAP.2 — rotas e cercas
# ---------------------------------------------------------------------------
class RotaViewSet(BaseCamadaViewSet):
    queryset = Rota.objects.select_related("origem", "obra").prefetch_related("paradas__local").all()
    serializer_class = RotaSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento]
    filterset_fields = ["status", "obra", "data_planejada"]
    search_fields = ["nome"]
    required_resource = "mapa.rota"

    def _coordenadas(self, rota):
        """Origem + paradas na ordem atual. Levanta se faltar coordenada."""
        paradas = list(rota.paradas.select_related("local").order_by("ordem", "pk"))
        if rota.origem.ponto is None:
            raise ValueError("A origem da rota não tem coordenada — geocodifique-a antes.")
        sem_ponto = [p.local.nome for p in paradas if p.local.ponto is None]
        if sem_ponto:
            raise ValueError(
                "Estas paradas não têm coordenada: " + ", ".join(sem_ponto[:5]) +
                ". Geocodifique-as antes de traçar a rota."
            )
        coords = [(rota.origem.ponto.x, rota.origem.ponto.y)]
        coords += [(p.local.ponto.x, p.local.ponto.y) for p in paradas]
        return paradas, coords

    @action(detail=True, methods=["post"])
    def tracar(self, request, pk=None):
        """Desenha a rota na ordem atual das paradas, sem reordenar."""
        rota = self.get_object()
        try:
            _, coords = self._coordenadas(rota)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if len(coords) < 2:
            return Response(
                {"detail": "A rota precisa de ao menos uma parada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        linha, metros, segundos, procedencia = motor_rotas.tracar(coords)
        rota.linha, rota.distancia_m, rota.duracao_s = linha, metros, segundos
        rota.procedencia = procedencia
        rota.save(update_fields=["linha", "distancia_m", "duracao_s", "procedencia"])
        return Response(RotaSerializer(rota).data)

    @action(detail=True, methods=["post"])
    def otimizar(self, request, pk=None):
        """Reordena as paradas por tempo de viagem e traça o resultado.

        Devolve as **violações de janela** que a nova ordem produziu. Elas não
        bloqueiam: quem conhece o canteiro decide se troca a ordem ou negocia o
        horário — o que o sistema não pode fazer é entregar a ordem "ótima" sem
        contar que ela chega às 6h num portão que abre às 8h.
        """
        rota = self.get_object()
        try:
            paradas, coords = self._coordenadas(rota)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if len(paradas) < 2:
            return Response(
                {"detail": "Otimizar exige ao menos duas paradas."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ordem, chegadas = motor_rotas.otimizar(coords)
        # `ordem` e `chegadas` são paralelos e indexam [origem, parada…], com a
        # origem fixa na posição 0 — então a parada que ficou em `posicao` tem a
        # chegada de `chegadas[posicao]`, sem tradução de índice.
        sequencia = [paradas[i - 1] for i in ordem if i > 0]
        for posicao, parada in enumerate(sequencia, start=1):
            parada.ordem = posicao
            parada.chegada_estimada_s = int(chegadas[posicao])
        ParadaRota.objects.bulk_update(sequencia, ["ordem", "chegada_estimada_s"])

        coords_ordenadas = [coords[i] for i in ordem]
        linha, metros, segundos, procedencia = motor_rotas.tracar(coords_ordenadas)
        rota.linha, rota.distancia_m, rota.duracao_s = linha, metros, segundos
        rota.procedencia, rota.otimizada_em = procedencia, timezone.now()
        rota.status = Rota.Status.PLANEJADA
        rota.save(update_fields=[
            "linha", "distancia_m", "duracao_s", "procedencia", "otimizada_em", "status",
        ])

        rota.refresh_from_db()
        return Response({
            "rota": RotaSerializer(rota).data,
            "violacoes_de_janela": motor_rotas.violacoes_de_janela(
                sequencia, [p.chegada_estimada_s or 0 for p in sequencia]
            ),
        })


class ParadaRotaViewSet(BaseCamadaViewSet):
    queryset = ParadaRota.objects.select_related("local", "rota").all()
    serializer_class = ParadaRotaSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["rota", "local"]
    required_resource = "mapa.rota"
    pagination_class = None  # lida por rota (poucas paradas)


class GeofenceViewSet(BaseCamadaViewSet):
    queryset = Geofence.objects.select_related("local").all()
    serializer_class = GeofenceSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento]
    filterset_fields = ["tipo", "ativo", "local"]
    search_fields = ["nome"]
    required_resource = "mapa.geofence"

    @action(detail=False, methods=["post"])
    def gerar(self, request):
        """Cria a cerca a partir de um `Local` — do perímetro dele, ou de um raio."""
        local = Local.objects.filter(
            pk=request.data.get("local") or 0,
            tenant_id=getattr(request.user, "tenant_id", None),
        ).first()
        if local is None:
            return Response({"detail": "Informe um local da sua empresa."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            cerca = services.gerar_geofence(
                local,
                nome=request.data.get("nome") or f"Cerca — {local.nome}",
                tipo=request.data.get("tipo") or Geofence.Tipo.CANTEIRO,
                raio_m=int(request.data["raio_m"]) if request.data.get("raio_m") else None,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(GeofenceSerializer(cerca).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def conter(self, request):
        """`?lon=&lat=` — em quais cercas este ponto está.

        O consumo é de outros módulos (ponto por geolocalização no RH, foto do
        diário). Fica aqui porque a cerca é do Maps; quem pergunta é quem tem a
        coordenada na mão.
        """
        try:
            lon, lat = float(request.query_params["lon"]), float(request.query_params["lat"])
        except (KeyError, ValueError):
            return Response({"detail": "Informe `lon` e `lat`."},
                            status=status.HTTP_400_BAD_REQUEST)
        dentro = services.dentro_da_cerca(getattr(request.user, "tenant_id", None), lon, lat)
        return Response({
            "dentro": dentro.exists(),
            "cercas": GeofenceSerializer(dentro, many=True).data,
        })


# ---------------------------------------------------------------------------
# MAP.1 — o mapa da empresa e a fila de decisão
# ---------------------------------------------------------------------------
class MapaDaEmpresaView(TenantScopedAPIViewMixin, views.APIView):
    """Tudo que a empresa tem no território, num payload só.

    **Sem entitlement**: os pins são `Local`, que é fundação. As camadas pagas
    (ortofoto, voo, rota) entram no mesmo payload **apenas se o tenant assina
    Maps** — sem módulo, a chave nem aparece. É a régua do hub da Edição: sem
    fonte, nada; nunca um zero que parece dado.
    """

    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "mapa.local"

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        locais = self.scope_qs(
            Local.objects.filter(ativo=True).select_related(
                "obra", "empreendimento", "fornecedor", "local_estoque",
                "unidade", "unidade__empreendimento",
            )
        )
        com_ponto = locais.filter(ponto__isnull=False)

        payload = {
            "locais": LocalResumoSerializer(com_ponto[:1000], many=True).data,
            "resumo": {
                "total": locais.count(),
                "com_coordenada": com_ponto.count(),
                "por_tipo": {
                    tipo: com_ponto.filter(tipo=tipo).count() for tipo, _ in Local.Tipo.choices
                },
                "por_precisao": {
                    p: locais.filter(precisao=p).count() for p, _ in Precisao.choices
                },
            },
            "requer_decisao": self._fila(request, locais, tenant_id),
            "camadas_contratadas": "maps" in (getattr(request.user, "iam_modules", []) or []),
        }
        return Response(payload)

    #: Teto da varredura de coerência de rua. **Não é limite de produto**
    #: (§5.6 do `payment/planos.py`): é guarda-corpo de uma comparação que roda
    #: em Python, linha a linha, dentro do payload do cockpit. Um loteamento
    #: grande tem centenas de lotes georreferenciados; mil é folga e mantém o
    #: cartaz honesto — acima disso ele diz "mais de mil", que é o que importa.
    _TETO_VARREDURA_RUA = 1000

    def _unidades_com_rua_divergente(self, locais) -> int:
        """Quantas unidades têm a frente apontando para rua diferente do endereço.

        Roda em Python porque a comparação é textual e tolerante (acento,
        abreviatura, número da casa) — SQL faria igualdade literal e acusaria
        divergência em todo cadastro certo. Em compensação é varredura, daí o
        teto: o cockpit não pode custar uma leitura da tabela inteira.
        """
        from . import services

        unidades = (
            locais.filter(tipo=Local.Tipo.UNIDADE)
            .exclude(unidade__confrontante_frente="")
            .select_related("unidade")[: self._TETO_VARREDURA_RUA]
        )
        return sum(
            1 for local in unidades
            if services.rua_confere(local.unidade, local) is False
        )

    def _fila(self, request, locais, tenant_id) -> list[dict]:
        """A fila de decisão real da tela — cada item é uma pendência acionável."""
        fila = []

        sem_coordenada = locais.filter(ponto__isnull=True)
        for rotulo, tipo in (("obras", Local.Tipo.OBRA), ("fornecedores", Local.Tipo.FORNECEDOR),
                             ("almoxarifados", Local.Tipo.LOCAL_ESTOQUE)):
            quantos = sem_coordenada.filter(tipo=tipo).count()
            if quantos:
                fila.append({
                    "tipo": "sem_coordenada",
                    "alvo": tipo,
                    "quantidade": quantos,
                    "titulo": f"{quantos} {rotulo} sem coordenada",
                    "acao": "geocodificar",
                })

        # A rua da frente contra o endereço da unidade. É pendência de cadastro,
        # não de geocodificação: o pin pode estar certíssimo e o memorial dizer
        # que o lote faz frente para outra rua — e é o memorial que vai ao
        # contrato e à matrícula. Quem descobre isso na escritura descobre tarde.
        divergentes = self._unidades_com_rua_divergente(locais)
        if divergentes:
            fila.append({
                "tipo": "rua_divergente",
                "alvo": "unidade",
                "quantidade": divergentes,
                "titulo": f"{divergentes} unidades com a rua da frente diferente do endereço",
                "acao": "conferir",
            })

        # Só município: o pin existe, mas está no centro da cidade. Vale um item
        # próprio porque é o caso que MAIS engana — no mapa parece resolvido.
        grosseiros = locais.filter(precisao=Precisao.MUNICIPIO).count()
        if grosseiros:
            fila.append({
                "tipo": "precisao_grosseira",
                "alvo": "local",
                "quantidade": grosseiros,
                "titulo": f"{grosseiros} pins no centro da cidade (precisão de município)",
                "acao": "refinar",
            })

        if "maps" not in (getattr(request.user, "iam_modules", []) or []):
            return fila

        corte = timezone.localdate() - timedelta(days=DIAS_ORTOFOTO_VENCIDA)
        vencidas = Ortofoto.objects.filter(tenant_id=tenant_id, data_voo__lt=corte).count()
        if vencidas:
            fila.append({
                "tipo": "ortofoto_vencida",
                "alvo": "ortofoto",
                "quantidade": vencidas,
                "titulo": f"{vencidas} ortofotos com mais de {DIAS_ORTOFOTO_VENCIDA} dias",
                "acao": "revoar",
            })

        hoje = timezone.localdate()
        sem_autorizacao = PlanoVoo.objects.filter(tenant_id=tenant_id).filter(
            autorizacao_protocolo=""
        ).count() + PlanoVoo.objects.filter(
            tenant_id=tenant_id, autorizacao_validade__lt=hoje
        ).count()
        if sem_autorizacao:
            fila.append({
                "tipo": "voo_sem_autorizacao",
                "alvo": "plano_voo",
                "quantidade": sem_autorizacao,
                "titulo": f"{sem_autorizacao} planos de voo sem autorização válida",
                "acao": "autorizar",
            })

        return fila


class DetectarEnderecoView(TenantScopedAPIViewMixin, views.APIView):
    """MAP.5 — texto livre (ou XML de NF-e) → endereços candidatos.

    **Não grava nada.** O destino do que sai daqui é a conferência linha a linha
    do `funcoesimpexp` (`maps.local` em impexp.py), onde alguém decide o que
    entra. Extração de endereço erra — e a resposta a isso é a régua R1 do
    motor (nada entra antes da decisão), não um extrator melhor.
    """

    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "mapa.local"
    # Chamada cara (bate no ViaCEP por candidato) e fácil de abusar em laço.
    throttle_scope = "integracao_externa"

    def post(self, request):
        texto = request.data.get("texto") or ""
        xml = request.data.get("xml") or ""
        if xml:
            achado = deteccao.endereco_do_xml(
                xml.encode("utf-8") if isinstance(xml, str) else xml,
                papel=request.data.get("papel") or "emit",
            )
            return Response({"candidatos": [achado] if achado else []})
        if not texto.strip():
            return Response({"detail": "Envie `texto` ou `xml`."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({"candidatos": deteccao.detectar_enderecos(texto)})
