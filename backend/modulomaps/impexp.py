# backend/modulomaps/impexp.py
"""MAP.5 — o Maps declara o que sai e o que entra. É o `IE.n` do módulo.

O caminho inteiro da detecção termina aqui, e de propósito: `detectar-endereco/`
acha candidatos num contrato ou num XML, mas **nada disso vira pin sozinho**.
Extração de endereço em texto livre erra — troca número por CEP, pega a cidade
do cabeçalho do documento —, e a resposta certa a isso não é um extrator melhor,
é a régua **R1** do motor: zero linhas no destino antes da decisão. O operador vê
nova/duplicada/inválida linha a linha e confirma o lote inteiro — que só entra se
todas forem novas —, e o lote fica desfazível.

Exportar também importa aqui: a carteira georreferenciada é o insumo de estudo
de mercado, de rota e de laudo — sair em XLSX/CSV é o mínimo para o dado ser da
empresa, e não do sistema.
"""
from __future__ import annotations

from funcoesimpexp.registro import Coluna, Recurso, registrar

from .models import FonteGeo, Local, Precisao

ALIAS_CEP = ("cep", "código postal", "codigo postal")
ALIAS_LOGRADOURO = ("logradouro", "endereco", "endereço", "rua", "avenida")
ALIAS_CIDADE = ("cidade", "municipio", "município", "localidade")
ALIAS_UF = ("uf", "estado", "sigla")


@registrar("maps.local")
class LocaisGeorreferenciados(Recurso):
    """Locais da empresa: onde cada obra, fornecedor e almoxarifado fica."""

    rotulo = "Locais (georreferenciamento)"
    modulo = "maps"
    # **Fundação, não produto vendido.** `Local` é a metade do Maps que abre para
    # todo tenant (MAP.0): georreferenciar obra, fornecedor e almoxarifado é
    # cadastro, e as permissões `mapa.local.*` moram no módulo `base`. Sem este
    # `None`, o entitlement de escrita cobraria o módulo `maps` de quem só está
    # subindo o endereço das próprias obras — o oposto do desenho das duas
    # metades. As camadas, o acervo e o voo é que ficam atrás de `maps`.
    entitlement = None
    # §3 — acesso total: ver o local e poder gravá-lo. Endereço de obra não é
    # PII de titular (é da empresa), então não há permissão de máscara a somar.
    permissoes_exigidas = ("mapa.local.view", "mapa.local.edit")
    chave = "nome"

    colunas = (
        Coluna("nome", "Nome", obrigatoria=True, exemplo="Obra Residencial Aurora"),
        Coluna("cep", "CEP", exemplo="41820-021", aliases=ALIAS_CEP),
        Coluna("logradouro", "Logradouro", exemplo="Av. Tancredo Neves", aliases=ALIAS_LOGRADOURO),
        Coluna("numero", "Número", exemplo="1632", aliases=("numero", "nro", "nº", "n.")),
        Coluna("bairro", "Bairro", exemplo="Caminho das Árvores"),
        Coluna("cidade", "Cidade", exemplo="Salvador", aliases=ALIAS_CIDADE),
        Coluna("uf", "UF", exemplo="BA", aliases=ALIAS_UF),
        # Coordenada é opcional: quem já tem (levantamento, GPS de campo) entra
        # com precisão `exata`; quem não tem cai na cascata. As duas portas
        # existem porque as duas situações são reais no mesmo cliente.
        Coluna("longitude", "Longitude", exemplo="-38.4567", aliases=("lon", "lng", "x")),
        Coluna("latitude", "Latitude", exemplo="-12.9876", aliases=("lat", "y")),
        Coluna("precisao", "Precisão", exemplo="exata"),
    )

    # ------------------------------------------------------------------
    # Saída
    # ------------------------------------------------------------------
    def queryset(self, request, recorte: dict):
        qs = Local.objects.filter(tenant_id=getattr(request.user, "tenant_id", None))
        if recorte.get("tipo"):
            qs = qs.filter(tipo=recorte["tipo"])
        if recorte.get("uf"):
            qs = qs.filter(uf=recorte["uf"])
        return qs.order_by("nome")

    def serializar_objeto(self, obj) -> dict:
        return {
            "nome": obj.nome,
            "cep": obj.cep,
            "logradouro": obj.logradouro,
            "numero": obj.numero,
            "bairro": obj.bairro,
            "cidade": obj.cidade,
            "uf": obj.uf,
            "longitude": f"{obj.ponto.x:.7f}" if obj.ponto else "",
            "latitude": f"{obj.ponto.y:.7f}" if obj.ponto else "",
            # Sai o RÓTULO, não o código: a planilha é lida por gente, e
            # "Centroide de município" diz o que "municipio" não diz.
            "precisao": obj.get_precisao_display(),
        }

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------
    def validar_linha(self, dados: dict) -> str:
        if not (dados.get("nome") or "").strip():
            return "Sem nome — o nome é a identidade do local."

        tem_lon, tem_lat = bool(dados.get("longitude")), bool(dados.get("latitude"))
        if tem_lon != tem_lat:
            return "Longitude e latitude precisam vir juntas."
        if tem_lon:
            try:
                lon, lat = float(str(dados["longitude"]).replace(",", ".")), float(
                    str(dados["latitude"]).replace(",", ".")
                )
            except (TypeError, ValueError):
                return "Coordenada não numérica."
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                return "Coordenada fora do intervalo válido (lon/lat trocados?)."
            # O Brasil inteiro cabe nesta caixa. Não é purismo: lon/lat trocados
            # passam nos limites globais e põem a obra na China — erro que só
            # aparece quando alguém abre o mapa, semanas depois.
            if not (-74 <= lon <= -34 and -34 <= lat <= 6):
                return "Coordenada fora do Brasil — confira se lon e lat não estão trocados."

        if not (dados.get("cep") or dados.get("cidade") or tem_lon):
            return "Sem CEP, sem cidade e sem coordenada: não há como localizar."
        return ""

    def localizar(self, dados: dict, tenant_id):
        return Local.objects.filter(
            tenant_id=tenant_id, nome=(dados.get("nome") or "").strip()
        ).first()

    def aplicar_linha(self, dados: dict, existente, tenant_id) -> dict | None:
        from django.contrib.gis.geos import Point

        from . import services

        campos = {
            "cep": (dados.get("cep") or "")[:9],
            "logradouro": (dados.get("logradouro") or "")[:255],
            "numero": (dados.get("numero") or "")[:20],
            "bairro": (dados.get("bairro") or "")[:120],
            "cidade": (dados.get("cidade") or "")[:120],
            "uf": (dados.get("uf") or "").upper()[:2],
        }
        ponto = None
        if dados.get("longitude") and dados.get("latitude"):
            ponto = Point(
                float(str(dados["longitude"]).replace(",", ".")),
                float(str(dados["latitude"]).replace(",", ".")),
                srid=4326,
            )

        # Só cria: o motor trava o lote quando o nome já existe (14/10/2026).
        local = Local.objects.create(
            tenant_id=tenant_id,
            nome=(dados.get("nome") or "").strip()[:180],
            tipo=Local.Tipo.AVULSO,
            ponto=ponto,
            precisao=Precisao.EXATA if ponto else Precisao.DESCONHECIDA,
            fonte=FonteGeo.IMPORTACAO if ponto else "",
            **campos,
        )
        if ponto is None:
            services.completar_localidade(local)
            services.geocodificar_local(local)
        return {"acao": "criou", "pk": local.pk}

    def desfazer_linha(self, estado_anterior: dict, tenant_id) -> None:
        # O ramo "atualizou" abaixo serve só aos lotes aplicados antes de a
        # importação passar a só criar (14/10/2026) — eles continuam desfazíveis.
        from django.contrib.gis.geos import GEOSGeometry

        local = Local.objects.filter(pk=estado_anterior.get("pk"), tenant_id=tenant_id).first()
        if local is None:
            return
        if estado_anterior.get("acao") == "criou":
            local.delete()
            return
        antes = estado_anterior.get("antes") or {}
        for campo, valor in antes.items():
            if campo == "ponto":
                local.ponto = GEOSGeometry(valor, srid=4326) if valor else None
            else:
                setattr(local, campo, valor)
        local.save()
