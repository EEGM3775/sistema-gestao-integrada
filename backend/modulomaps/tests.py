"""Testes do Maps (MAP.0–MAP.5).

O que se prova aqui, em ordem de importância:

1. **A divisão em duas metades vale de fato** — `Local` responde sem o módulo
   `maps`; camada, voo e rota fecham em 403. Se isso quebrar, ou o Maps virou
   fundação inteira (dando de graça o que é produto) ou o SIL/SCM de quem não
   assina perdeu a dimensão espacial.
2. **Precisão nunca é apagada para pior** — a cascata não sobrescreve `exata`.
3. **A conta do voo é a conta certa** — altura sai do GSD e da câmera.
4. **Coordenada trocada não entra** — lon/lat invertidos são o erro mais comum
   de importação, e passam em qualquer validação de intervalo global.
"""
from datetime import date, time
from decimal import Decimal
from unittest.mock import patch

from django.contrib.gis.geos import Point, Polygon
from rest_framework.test import APITestCase

from empreendimentos.models import Empreendimento
from fornecedores.models import Fornecedor
from nucleo import geo
from nucleo.models import Tenant, Usuario
from obras.models import Obra

from . import deteccao, services, voo
from .models import Camada, Feicao, Geofence, Local, Ortofoto, ParadaRota, PlanoVoo, Precisao, Rota

PERMS_FULL = [
    "mapa.local.view", "mapa.local.edit",
    "mapa.feicao.view", "mapa.feicao.edit",
    "mapa.ortofoto.view", "mapa.ortofoto.edit",
    "mapa.plano_voo.view", "mapa.plano_voo.edit",
    "mapa.rota.view", "mapa.rota.edit",
    "mapa.geofence.view", "mapa.geofence.edit",
]

# Salvador (BA) — as coordenadas dos testes ficam todas no Nordeste para o
# filtro "está no Brasil" do impexp ser exercitado com dado plausível.
SALVADOR = (-38.4813, -12.9714)
LAURO = (-38.3270, -12.8940)   # ~18 km de Salvador
FEIRA = (-38.9660, -12.2660)   # ~100 km de Salvador


class MapsTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="maps-a", nome="Empresa A")
        cls.tenant_b = Tenant.objects.create(slug="maps-b", nome="Empresa B")
        cls.user = Usuario.objects.create(username="topo_a", tenant=cls.tenant)

    def autenticar(self, user=None, modules=("maps",), perms=PERMS_FULL):
        user = user or self.user
        user.iam_modules = list(modules)
        user.iam_permissions = list(perms)
        self.client.force_authenticate(user=user)
        return user

    def _local(self, nome="Canteiro", coord=SALVADOR, tenant=None, precisao=Precisao.EXATA):
        return Local.objects.create(
            tenant=tenant or self.tenant, nome=nome, tipo=Local.Tipo.AVULSO,
            ponto=Point(*coord, srid=4326), precisao=precisao, cidade="Salvador", uf="BA",
        )

    def _area(self, centro=SALVADOR, lado_graus=0.004):
        lon, lat = centro
        return Polygon.from_bbox(
            (lon - lado_graus, lat - lado_graus, lon + lado_graus, lat + lado_graus)
        )


# ---------------------------------------------------------------------------
# Acesso — a divisão em duas metades
# ---------------------------------------------------------------------------
class DuasMetadesTests(MapsTestBase):
    def test_local_responde_sem_o_modulo_maps(self):
        """Fundação: quem não assina Maps continua georreferenciando cadastro."""
        self.autenticar(modules=[])
        self.assertEqual(self.client.get("/api/maps/locais/").status_code, 200)

    def test_camadas_exigem_o_modulo(self):
        self.autenticar(modules=[])
        for rota in ("camadas", "feicoes", "ortofotos", "planos-voo", "rotas", "geofences"):
            self.assertEqual(
                self.client.get(f"/api/maps/{rota}/").status_code, 403,
                f"/api/maps/{rota}/ deveria exigir o entitlement `maps`",
            )

    def test_sem_permissao_de_local_fecha_mesmo_com_o_modulo(self):
        self.autenticar(modules=["maps"], perms=[])
        self.assertEqual(self.client.get("/api/maps/locais/").status_code, 403)

    def test_mapa_da_empresa_nao_exige_modulo_mas_declara_o_que_falta(self):
        self.autenticar(modules=[])
        self._local()
        resposta = self.client.get("/api/maps/mapa/")
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.data["camadas_contratadas"])
        self.assertEqual(resposta.data["resumo"]["com_coordenada"], 1)


class IsolamentoTests(MapsTestBase):
    def test_local_de_outro_tenant_nao_aparece(self):
        self._local(nome="Meu canteiro")
        self._local(nome="Canteiro alheio", tenant=self.tenant_b)
        self.autenticar()
        resposta = self.client.get("/api/maps/locais/")
        nomes = [linha["nome"] for linha in resposta.data["results"]]
        self.assertEqual(nomes, ["Meu canteiro"])


# ---------------------------------------------------------------------------
# MAP.0 — cascata e precisão
# ---------------------------------------------------------------------------
class CascataTests(MapsTestBase):
    def test_pin_enviado_a_mao_vira_precisao_exata(self):
        self.autenticar()
        resposta = self.client.post("/api/maps/locais/", {
            "nome": "Obra com pin", "tipo": "avulso",
            "ponto": {"lon": SALVADOR[0], "lat": SALVADOR[1]},
        }, format="json")
        self.assertEqual(resposta.status_code, 201)
        local = Local.objects.get(pk=resposta.data["local_id"])
        self.assertEqual(local.precisao, Precisao.EXATA)

    @patch("nucleo.geo.geocodificar")
    @patch("nucleo.geo.resolver")
    def test_sem_pin_a_cascata_grava_precisao_e_procedencia(self, resolver, geocodificar):
        resolver.return_value = {"cidade": "Salvador", "uf": "BA", "ibge": "2927408"}
        geocodificar.return_value = {
            "lon": SALVADOR[0], "lat": SALVADOR[1], "precisao": "cep", "fonte": "cep",
        }
        self.autenticar()
        resposta = self.client.post("/api/maps/locais/", {
            "nome": "Obra sem pin", "tipo": "avulso", "cep": "41820-021",
        }, format="json")
        self.assertEqual(resposta.status_code, 201)
        local = Local.objects.get(pk=resposta.data["local_id"])
        self.assertEqual(local.precisao, Precisao.CEP)
        self.assertEqual(local.fonte, "cep")
        self.assertIsNotNone(local.geocodificado_em)

    @patch("nucleo.geo.geocodificar")
    def test_cascata_nao_rebaixa_um_ponto_exato(self, geocodificar):
        """O pin de campo vale mais que qualquer provedor — nem `forcar` o troca."""
        geocodificar.return_value = {
            "lon": FEIRA[0], "lat": FEIRA[1], "precisao": "municipio", "fonte": "ibge",
        }
        local = self._local(precisao=Precisao.EXATA)
        self.autenticar()
        resposta = self.client.post(f"/api/maps/locais/{local.pk}/geocodificar/?forcar=1")
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.data["geocodificado"])
        local.refresh_from_db()
        self.assertEqual(local.precisao, Precisao.EXATA)
        self.assertAlmostEqual(local.ponto.x, SALVADOR[0], places=4)

    @patch("nucleo.geo.geocodificar", return_value=None)
    def test_sem_provedor_o_local_fica_sem_coordenada_e_entra_na_fila(self, _geo):
        """Ninguém inventa 0,0: sem resposta, o local vira item da fila de decisão."""
        local = Local.objects.create(
            tenant=self.tenant, nome="Sem endereço", tipo=Local.Tipo.AVULSO
        )
        self.assertFalse(services.geocodificar_local(local))
        local.refresh_from_db()
        self.assertIsNone(local.ponto)
        self.assertEqual(local.precisao, Precisao.DESCONHECIDA)

    def test_vocabulario_de_precisao_bate_entre_nucleo_e_o_modelo(self):
        """`nucleo.geo` não pode importar app de negócio, então o contrato é
        textual — e contrato textual sem guarda apodrece em silêncio."""
        valores = {p.value for p in Precisao}
        for texto in (geo.PRECISAO_ENDERECO, geo.PRECISAO_CEP, geo.PRECISAO_MUNICIPIO):
            self.assertIn(texto, valores)

    def test_coordenada_invertida_e_recusada_no_serializer(self):
        self.autenticar()
        resposta = self.client.post("/api/maps/locais/", {
            "nome": "Invertida", "tipo": "avulso", "ponto": {"lon": -12.97, "lat": -238.4},
        }, format="json")
        self.assertEqual(resposta.status_code, 400)

    def test_tipo_sem_a_entidade_correspondente_da_400(self):
        self.autenticar()
        resposta = self.client.post(
            "/api/maps/locais/", {"nome": "Órfã", "tipo": "obra"}, format="json"
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("obra", resposta.data)


class CentroideTests(MapsTestBase):
    def test_centroide_de_anel_quadrado_e_o_centro(self):
        anel = [(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)]
        x, y = geo._centroide_anel(anel)
        self.assertAlmostEqual(x, 1.0, places=6)
        self.assertAlmostEqual(y, 1.0, places=6)


# ---------------------------------------------------------------------------
# MAP.1 — vizinhança e mapa da empresa
# ---------------------------------------------------------------------------
class VizinhancaTests(MapsTestBase):
    def test_proximos_respeita_o_raio_e_ordena_por_distancia(self):
        origem = self._local(nome="Canteiro")
        self._local(nome="Perto", coord=LAURO)
        self._local(nome="Longe", coord=FEIRA)
        self.autenticar()

        resposta = self.client.get(f"/api/maps/locais/proximos/?de={origem.pk}&raio_km=30")
        self.assertEqual(resposta.status_code, 200)
        nomes = [r["nome"] for r in resposta.data["resultados"]]
        self.assertEqual(nomes, ["Perto"])
        self.assertGreater(resposta.data["resultados"][0]["distancia_km"], 0)

        amplo = self.client.get(f"/api/maps/locais/proximos/?de={origem.pk}&raio_km=200")
        self.assertEqual([r["nome"] for r in amplo.data["resultados"]], ["Perto", "Longe"])

    def test_proximos_exige_origem_com_coordenada(self):
        orfao = Local.objects.create(tenant=self.tenant, nome="Sem ponto", tipo=Local.Tipo.AVULSO)
        self.autenticar()
        self.assertEqual(
            self.client.get(f"/api/maps/locais/proximos/?de={orfao.pk}").status_code, 400
        )

    def test_fila_de_decisao_lista_sem_coordenada_e_precisao_grosseira(self):
        obra = Obra.objects.create(tenant=self.tenant, nome_obra="Aurora", endereco="Rua X")
        Local.objects.create(tenant=self.tenant, nome="Aurora", tipo=Local.Tipo.OBRA, obra=obra)
        self._local(nome="Só cidade", precisao=Precisao.MUNICIPIO)
        self.autenticar()

        fila = self.client.get("/api/maps/mapa/").data["requer_decisao"]
        tipos = {item["tipo"] for item in fila}
        self.assertIn("sem_coordenada", tipos)
        self.assertIn("precisao_grosseira", tipos)


# ---------------------------------------------------------------------------
# MAP.2 — rotas e cercas
# ---------------------------------------------------------------------------
class RotaTests(MapsTestBase):
    def _rota_com_paradas(self):
        origem = self._local(nome="Almoxarifado central")
        rota = Rota.objects.create(tenant=self.tenant, nome="Entrega segunda", origem=origem)
        # Fora de ordem de propósito: a mais distante entra primeiro.
        longe = ParadaRota.objects.create(
            tenant=self.tenant, rota=rota, local=self._local(nome="Feira", coord=FEIRA), ordem=1
        )
        perto = ParadaRota.objects.create(
            tenant=self.tenant, rota=rota, local=self._local(nome="Lauro", coord=LAURO), ordem=2
        )
        return rota, perto, longe

    def test_otimizar_reordena_e_declara_a_procedencia_estimada(self):
        """Sem OSRM configurado, a rota é reta — e diz que é."""
        rota, perto, longe = self._rota_com_paradas()
        self.autenticar()
        resposta = self.client.post(f"/api/maps/rotas/{rota.pk}/otimizar/")
        self.assertEqual(resposta.status_code, 200)

        perto.refresh_from_db()
        longe.refresh_from_db()
        self.assertEqual(perto.ordem, 1)
        self.assertEqual(longe.ordem, 2)
        self.assertEqual(resposta.data["rota"]["procedencia"], "estimada")
        self.assertGreater(resposta.data["rota"]["distancia_km"], 0)

    def test_otimizar_relata_violacao_de_janela_sem_bloquear(self):
        rota, perto, longe = self._rota_com_paradas()
        # Janela impossível para quem chega depois de rodar 100 km.
        longe.janela_fim = time(8, 5)
        longe.save(update_fields=["janela_fim"])
        self.autenticar()
        resposta = self.client.post(f"/api/maps/rotas/{rota.pk}/otimizar/")
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.data["violacoes_de_janela"])

    def test_parada_sem_coordenada_impede_tracar_com_mensagem_util(self):
        origem = self._local(nome="Central")
        rota = Rota.objects.create(tenant=self.tenant, nome="Rota torta", origem=origem)
        orfao = Local.objects.create(tenant=self.tenant, nome="Obra nova", tipo=Local.Tipo.AVULSO)
        ParadaRota.objects.create(tenant=self.tenant, rota=rota, local=orfao, ordem=1)
        self.autenticar()
        resposta = self.client.post(f"/api/maps/rotas/{rota.pk}/tracar/")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("Obra nova", resposta.data["detail"])


class GeofenceTests(MapsTestBase):
    def test_gerar_por_raio_e_verificar_conteudo(self):
        local = self._local(nome="Canteiro Aurora")
        self.autenticar()
        criada = self.client.post("/api/maps/geofences/gerar/", {
            "local": local.pk, "nome": "Cerca Aurora", "raio_m": 300,
        }, format="json")
        self.assertEqual(criada.status_code, 201)

        dentro = self.client.get(
            f"/api/maps/geofences/conter/?lon={SALVADOR[0]}&lat={SALVADOR[1]}"
        )
        self.assertTrue(dentro.data["dentro"])

        fora = self.client.get(f"/api/maps/geofences/conter/?lon={FEIRA[0]}&lat={FEIRA[1]}")
        self.assertFalse(fora.data["dentro"])

    def test_cerca_prefere_o_perimetro_desenhado_ao_circulo(self):
        local = self._local(nome="Com perímetro")
        local.area = self._area()
        local.save(update_fields=["area"])
        cerca = services.gerar_geofence(local, "Cerca real", Geofence.Tipo.CANTEIRO)
        self.assertIsNone(cerca.raio_m)
        self.assertEqual(cerca.area.num_points, local.area.num_points)

    def test_sem_coordenada_a_cerca_falha_com_motivo(self):
        local = Local.objects.create(tenant=self.tenant, nome="Sem ponto", tipo=Local.Tipo.AVULSO)
        with self.assertRaises(ValueError):
            services.gerar_geofence(local, "Impossível", Geofence.Tipo.CANTEIRO)


# ---------------------------------------------------------------------------
# MAP.3 — feições e ortofotos
# ---------------------------------------------------------------------------
class AcervoTests(MapsTestBase):
    def test_feicoes_recortam_por_bbox_e_por_data(self):
        camada = Camada.objects.create(tenant=self.tenant, nome="Progresso")
        Feicao.objects.create(
            tenant=self.tenant, camada=camada, nome="Bloco A", geom=Point(*SALVADOR, srid=4326),
            data_referencia=date(2026, 3, 1), grupo="bloco-a",
        )
        Feicao.objects.create(
            tenant=self.tenant, camada=camada, nome="Bloco A (junho)",
            geom=Point(*SALVADOR, srid=4326), data_referencia=date(2026, 6, 1), grupo="bloco-a",
        )
        Feicao.objects.create(
            tenant=self.tenant, camada=camada, nome="Fora da área",
            geom=Point(*FEIRA, srid=4326), data_referencia=date(2026, 6, 1),
        )
        self.autenticar()

        lon, lat = SALVADOR
        bbox = f"{lon - 0.05},{lat - 0.05},{lon + 0.05},{lat + 0.05}"
        na_area = self.client.get(f"/api/maps/feicoes/?bbox={bbox}")
        self.assertEqual(na_area.data["count"], 2)

        ate_abril = self.client.get(f"/api/maps/feicoes/?bbox={bbox}&ate=2026-04-01")
        self.assertEqual(ate_abril.data["count"], 1)
        self.assertEqual(ate_abril.data["results"][0]["nome"], "Bloco A")

    def test_tiles_sem_servidor_configurado_respondem_503_e_nao_500(self):
        orto = Ortofoto.objects.create(
            tenant=self.tenant, titulo="Voo março", bbox=self._area(),
            data_voo=date(2026, 3, 1), url_cog="https://exemplo/cog.tif",
        )
        self.autenticar()
        resposta = self.client.get(f"/api/maps/ortofotos/{orto.pk}/tiles/12/100/200/")
        self.assertEqual(resposta.status_code, 503)


# ---------------------------------------------------------------------------
# MAP.4 — plano de voo
# ---------------------------------------------------------------------------
class PlanoVooTests(MapsTestBase):
    def _plano(self, **extra):
        campos = {
            "tenant": self.tenant, "nome": "Voo Aurora", "area": self._area(),
            "gsd_alvo_cm": Decimal("2.00"),
        }
        campos.update(extra)
        return PlanoVoo.objects.create(**campos)

    def test_altura_sai_do_gsd_e_da_geometria_da_camera(self):
        """2 cm/px, focal 8,8 mm, 5472 px, sensor 13,2 mm → ~72,9 m."""
        altura = voo.altura_para_gsd(2, 8.8, 5472, 13.2)
        self.assertAlmostEqual(altura, 0.02 * 8.8 * 5472 / 13.2, places=6)
        self.assertAlmostEqual(altura, 72.96, places=1)

    def test_calcular_gera_traçado_waypoints_e_memoria(self):
        plano = self._plano()
        self.autenticar()
        resposta = self.client.post(f"/api/maps/planos-voo/{plano.pk}/calcular/")
        self.assertEqual(resposta.status_code, 200)
        self.assertGreater(resposta.data["memoria"]["waypoints"], 2)
        self.assertAlmostEqual(float(resposta.data["memoria"]["altura_m"]), 73.0, delta=0.5)

        plano.refresh_from_db()
        self.assertIsNotNone(plano.linha)
        self.assertGreater(plano.fotos_estimadas, 0)
        self.assertGreater(float(plano.duracao_min), 0)

    def test_sobreposicao_maior_gera_mais_linhas(self):
        """A sobreposição lateral é o que aperta o espaçamento — se isto inverter,
        o voo sai com buraco entre faixas e o processamento não fecha."""
        folgado = voo.calcular(self._plano(nome="Folgado", sobreposicao_lateral_pct=40))
        apertado = voo.calcular(self._plano(nome="Apertado", sobreposicao_lateral_pct=85))
        self.assertGreater(len(apertado["waypoints"]), len(folgado["waypoints"]))

    def test_exportar_antes_de_calcular_da_409(self):
        plano = self._plano()
        self.autenticar()
        resposta = self.client.get(f"/api/maps/planos-voo/{plano.pk}/exportar/?formato=kml")
        self.assertEqual(resposta.status_code, 409)

    def test_os_quatro_formatos_saem_com_conteudo_reconhecivel(self):
        plano = self._plano()
        self.autenticar()
        self.client.post(f"/api/maps/planos-voo/{plano.pk}/calcular/")

        kml = self.client.get(f"/api/maps/planos-voo/{plano.pk}/exportar/?formato=kml")
        self.assertIn(b"<kml", kml.content)

        mavlink = self.client.get(f"/api/maps/planos-voo/{plano.pk}/exportar/?formato=plan")
        import json as _json
        conteudo = _json.loads(mavlink.content)
        self.assertEqual(conteudo["fileType"], "Plan")
        self.assertTrue(conteudo["mission"]["items"])

        litchi = self.client.get(f"/api/maps/planos-voo/{plano.pk}/exportar/?formato=litchi")
        self.assertIn(b"latitude,longitude,altitude(m)", litchi.content)

        wpml = self.client.get(f"/api/maps/planos-voo/{plano.pk}/exportar/?formato=wpml")
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(wpml.content)) as z:
            self.assertEqual(
                sorted(z.namelist()), ["wpmz/template.kml", "wpmz/waylines.wpml"]
            )

    def test_formato_desconhecido_da_400(self):
        plano = self._plano()
        self.autenticar()
        self.client.post(f"/api/maps/planos-voo/{plano.pk}/calcular/")
        resposta = self.client.get(f"/api/maps/planos-voo/{plano.pk}/exportar/?formato=dwg")
        self.assertEqual(resposta.status_code, 400)


# ---------------------------------------------------------------------------
# MAP.5 — detecção e XML da NF-e
# ---------------------------------------------------------------------------
XML_NFE = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe>
<emit><CNPJ>12345678000199</CNPJ><xNome>Concreteira Bahia Ltda</xNome>
<enderEmit><xLgr>Av. Tancredo Neves</xLgr><nro>1632</nro><xBairro>Caminho das Árvores</xBairro>
<cMun>2927408</cMun><xMun>Salvador</xMun><UF>BA</UF><CEP>41820021</CEP></enderEmit></emit>
<dest><CNPJ>98765432000188</CNPJ><xNome>Construtora Demo</xNome>
<enderDest><xLgr>Rua do Canteiro</xLgr><nro>10</nro><xBairro>Centro</xBairro>
<cMun>2927408</cMun><xMun>Salvador</xMun><UF>BA</UF><CEP>40010000</CEP></enderDest></dest>
</infNFe></NFe></nfeProc>"""


class DeteccaoTests(MapsTestBase):
    @patch("modulomaps.deteccao.buscar_por_cep")
    def test_cep_no_texto_vira_candidato_de_alta_confianca(self, buscar):
        buscar.return_value = {
            "logradouro": "Avenida Tancredo Neves", "bairro": "Caminho das Árvores",
            "localidade": "Salvador", "uf": "BA", "ibge": "2927408",
        }
        achados = deteccao.detectar_enderecos(
            "O imóvel fica na Av. Tancredo Neves, nº 1632, CEP 41820-021, e será entregue em 2027."
        )
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0]["confianca"], "alta")
        self.assertEqual(achados[0]["cidade"], "Salvador")
        self.assertEqual(achados[0]["numero"], "1632")

    def test_texto_sem_endereco_nao_inventa_candidato(self):
        self.assertEqual(deteccao.detectar_enderecos("Reunião de obra às 14h com a equipe."), [])

    def test_xml_da_nfe_devolve_o_endereco_do_emitente(self):
        achado = deteccao.endereco_do_xml(XML_NFE.encode("utf-8"), papel="emit")
        self.assertEqual(achado["nome"], "Concreteira Bahia Ltda")
        self.assertEqual(achado["logradouro"], "Av. Tancredo Neves")
        self.assertEqual(achado["cep"], "41820-021")
        self.assertEqual(achado["ibge"], "2927408")
        self.assertEqual(achado["confianca"], "alta")

    def test_xml_do_destinatario_e_outro_endereco(self):
        achado = deteccao.endereco_do_xml(XML_NFE.encode("utf-8"), papel="dest")
        self.assertEqual(achado["logradouro"], "Rua do Canteiro")

    def test_xml_invalido_devolve_none_em_vez_de_estourar(self):
        self.assertIsNone(deteccao.endereco_do_xml(b"nao e xml"))

    def test_endpoint_de_deteccao_exige_texto_ou_xml(self):
        self.autenticar()
        self.assertEqual(
            self.client.post("/api/maps/detectar-endereco/", {}, format="json").status_code, 400
        )

    def test_endpoint_aceita_xml_e_devolve_candidato(self):
        self.autenticar()
        resposta = self.client.post(
            "/api/maps/detectar-endereco/", {"xml": XML_NFE}, format="json"
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.data["candidatos"][0]["cidade"], "Salvador")


class ImpexpTests(MapsTestBase):
    """O recurso do motor de importação — o `IE.n` do Maps."""

    def setUp(self):
        from funcoesimpexp.registro import obter

        self.recurso = obter("maps.local")

    def test_coordenada_fora_do_brasil_e_recusada(self):
        """lon/lat trocados passam nos limites globais e põem a obra na China."""
        motivo = self.recurso.validar_linha({
            "nome": "Trocada", "longitude": "-12.97", "latitude": "-38.48",
        })
        self.assertIn("Brasil", motivo)

    def test_coordenada_solitaria_e_recusada(self):
        motivo = self.recurso.validar_linha({"nome": "Meia", "longitude": "-38.48"})
        self.assertIn("juntas", motivo)

    def test_linha_sem_ancora_nenhuma_e_recusada(self):
        motivo = self.recurso.validar_linha({"nome": "Solta"})
        self.assertIn("localizar", motivo)

    def test_aplicar_cria_com_precisao_exata_e_desfazer_apaga(self):
        dados = {
            "nome": "Depósito Norte", "longitude": "-38.4813", "latitude": "-12.9714",
            "cidade": "Salvador", "uf": "BA",
        }
        self.assertEqual(self.recurso.validar_linha(dados), "")
        estado = self.recurso.aplicar_linha(dados, None, self.tenant.pk)
        self.assertEqual(estado["acao"], "criou")

        local = Local.objects.get(pk=estado["pk"])
        self.assertEqual(local.precisao, Precisao.EXATA)

        self.recurso.desfazer_linha(estado, self.tenant.pk)
        self.assertFalse(Local.objects.filter(pk=estado["pk"]).exists())

    def test_reaplicar_atualiza_e_desfazer_restaura_o_valor_anterior(self):
        local = self._local(nome="Depósito Sul")
        antes_cidade = local.cidade
        estado = self.recurso.aplicar_linha(
            {"nome": "Depósito Sul", "cidade": "Feira de Santana", "uf": "BA"},
            local, self.tenant.pk,
        )
        self.assertEqual(estado["acao"], "atualizou")
        local.refresh_from_db()
        self.assertEqual(local.cidade, "Feira de Santana")

        self.recurso.desfazer_linha(estado, self.tenant.pk)
        local.refresh_from_db()
        self.assertEqual(local.cidade, antes_cidade)


class SincronizacaoTests(MapsTestBase):
    @patch("nucleo.geo.geocodificar", return_value=None)
    @patch("nucleo.geo.resolver", return_value=None)
    def test_sincronizar_e_idempotente(self, _resolver, _geo):
        obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Residencial Aurora",
            endereco="Av. Tancredo Neves, 1632, Salvador - BA",
        )
        primeiro = services.sincronizar_local(obra, Local.Tipo.OBRA)
        segundo = services.sincronizar_local(obra, Local.Tipo.OBRA)
        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(Local.objects.filter(obra=obra).count(), 1)
        self.assertEqual(primeiro.nome, "Residencial Aurora")

    @patch("nucleo.geo.geocodificar", return_value=None)
    @patch("nucleo.geo.resolver", return_value=None)
    def test_sincronizar_cobre_os_quatro_cadastros(self, _resolver, _geo):
        obra = Obra.objects.create(tenant=self.tenant, nome_obra="Obra X", endereco="Rua A")
        empreendimento = Empreendimento.objects.create(
            tenant=self.tenant, empreendimento="Emp Y", razao_social="Emp Y SA",
            cnpj="11222333000181", telefone="7130000000", endereco="Rua B",
            cidade="Salvador", estado="BA",
        )
        fornecedor = Fornecedor.objects.create(
            tenant=self.tenant, razao_social="Forn Z", email="z@forn.com"
        )
        from modulosil.models import LocalEstoque

        almox = LocalEstoque.objects.create(
            tenant=self.tenant, nome="Central", endereco="Rua C"
        )

        for entidade, tipo in (
            (obra, Local.Tipo.OBRA),
            (empreendimento, Local.Tipo.EMPREENDIMENTO),
            (fornecedor, Local.Tipo.FORNECEDOR),
            (almox, Local.Tipo.LOCAL_ESTOQUE),
        ):
            local = services.sincronizar_local(entidade, tipo)
            self.assertEqual(local.tipo, tipo)
            self.assertEqual(local.tenant_id, self.tenant.pk)
