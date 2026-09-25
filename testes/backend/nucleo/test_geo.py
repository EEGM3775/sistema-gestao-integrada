"""Testes do serviço compartilhado de resolução de endereço (`nucleo.geo`).

Cobre os dois caminhos: CEP (ViaCEP) e nome→IBGE (sem CEP), além do parse de
texto livre e do endpoint HTTP. Rede externa é sempre mockada.
"""
from unittest.mock import MagicMock, patch

from django.test import override_settings
from rest_framework.test import APITestCase

from nucleo import geo
from nucleo.models import Tenant, Usuario

DUMMY_CACHE = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}

VIACEP_SP = {
    "cep": "01001-000", "logradouro": "Praça da Sé", "bairro": "Sé",
    "localidade": "São Paulo", "uf": "SP", "ibge": "3550308",
}
MUNICIPIOS = {
    "SP": [
        {"id": 3550308, "nome": "São Paulo"},
        {"id": 3509502, "nome": "Campinas"},
    ],
    "BA": [
        {"id": 2928703, "nome": "Santo Antônio de Jesus"},
        {"id": 2927408, "nome": "Salvador"},
    ],
}


def _resp(payload):
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = payload
    return mock


def _fake_get(url, *args, **kwargs):
    if "viacep" in url:
        return _resp(VIACEP_SP)
    if "localidades/estados" in url:
        # .../localidades/estados/{UF}/municipios
        uf = url.split("/estados/")[1].split("/")[0]
        return _resp(MUNICIPIOS.get(uf, []))
    raise AssertionError(f"URL inesperada: {url}")


@override_settings(CACHES=DUMMY_CACHE)
class GeoParseTests(APITestCase):
    def test_parse_cidade_uf_formato_traco(self):
        self.assertEqual(geo.parse_endereco("Rua X, 123, Centro, Campinas - SP"),
                         ("Campinas", "SP"))

    def test_parse_cidade_uf_formato_barra(self):
        self.assertEqual(geo.parse_endereco("Av. Brasil, 500 - São Paulo/SP"),
                         ("São Paulo", "SP"))

    def test_parse_sem_uf_retorna_none(self):
        self.assertEqual(geo.parse_endereco("Rua sem estado, 10"), (None, None))

    def test_parse_estado_por_extenso(self):
        # "Ba 026" (nome de via) não é confundido com a UF; o estado é "Bahia".
        self.assertEqual(
            geo.parse_endereco("Ba 026, Santo Antonio de Jesus/Bahia"),
            ("Santo Antonio de Jesus", "BA"))

    def test_parse_estado_por_extenso_com_traco(self):
        self.assertEqual(geo.parse_endereco("Rua A, 10, Salvador - Bahia"),
                         ("Salvador", "BA"))

    def test_parse_estado_com_erro_de_digitacao(self):
        # "Bahiaa" (typo) ainda resolve para BA (fuzzy).
        _cidade, uf = geo.parse_endereco("Rua A, Salvador/Bahiaa")
        self.assertEqual(uf, "BA")

    def test_parse_nao_confunde_rua_homonima_de_estado(self):
        # "Rua Bahia" no início não vira o estado — a UF vem do fim.
        self.assertEqual(geo.parse_endereco("Rua Bahia, 100, Campinas - SP"),
                         ("Campinas", "SP"))


@override_settings(CACHES=DUMMY_CACHE)
class GeoResolverTests(APITestCase):
    @patch("nucleo.geo.requests.get", side_effect=_fake_get)
    def test_resolve_por_cep(self, _get):
        r = geo.resolver(cep="01001-000")
        self.assertEqual(r["ibge"], "3550308")
        self.assertEqual(r["cidade"], "São Paulo")
        self.assertEqual(r["uf"], "SP")
        self.assertEqual(r["fonte"], "viacep_cep")

    @patch("nucleo.geo.requests.get", side_effect=_fake_get)
    def test_resolve_por_nome_sem_cep(self, _get):
        r = geo.resolver(endereco="Rua das Flores, 10, Centro, Campinas - SP")
        self.assertEqual(r["ibge"], "3509502")
        self.assertEqual(r["cidade"], "Campinas")
        self.assertEqual(r["fonte"], "ibge_nome")

    @patch("nucleo.geo.requests.get", side_effect=_fake_get)
    def test_resolve_por_cidade_uf_explicitos(self, _get):
        r = geo.resolver(cidade="sao paulo", uf="sp")  # tolerante a acento/caixa
        self.assertEqual(r["ibge"], "3550308")

    @patch("nucleo.geo.requests.get", side_effect=_fake_get)
    def test_resolve_endereco_real_estado_por_extenso(self, _get):
        # Caso relatado: "Ba 026, Santo Antonio de Jesus/Bahia" (estado por
        # extenso + cidade sem acento) resolve para o IBGE correto.
        r = geo.resolver(endereco="Ba 026, Santo Antonio de Jesus/Bahia")
        self.assertEqual(r["uf"], "BA")
        self.assertEqual(r["cidade"], "Santo Antônio de Jesus")
        self.assertEqual(r["ibge"], "2928703")

    @patch("nucleo.geo.requests.get", side_effect=_fake_get)
    def test_resolve_endereco_com_cep_prefere_viacep(self, _get):
        # CEP embutido no texto → ViaCEP (mais confiável que o parse por nome).
        r = geo.resolver(endereco="Rua X, 100, Bairro, 01001-000")
        self.assertEqual(r["fonte"], "viacep_cep")
        self.assertEqual(r["ibge"], "3550308")

    @patch("nucleo.geo.requests.get", side_effect=_fake_get)
    def test_resolve_cidade_com_erro_digitacao(self, _get):
        # "Santo Antonio de Jesuz" (typo) é corrigido para o nome oficial.
        r = geo.resolver(cidade="Santo Antonio de Jesuz", uf="BA")
        self.assertEqual(r["cidade"], "Santo Antônio de Jesus")

    @patch("nucleo.geo.requests.get", side_effect=_fake_get)
    def test_uf_sem_cidade_reconhecivel_devolve_so_estado(self, _get):
        r = geo.resolver(cidade="Cidade Inexistente XYZ", uf="BA")
        self.assertEqual(r["uf"], "BA")
        self.assertEqual(r["cidade"], "")
        self.assertEqual(r["fonte"], "uf_apenas")

    @patch("nucleo.geo.requests.get", side_effect=_fake_get)
    def test_municipio_inexistente_sem_uf_retorna_none(self, _get):
        self.assertIsNone(geo.resolver(endereco="Rua sem estado, 10"))


@override_settings(CACHES=DUMMY_CACHE)
class GeoEndpointTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="geo-a", nome="Geo A")
        cls.user = Usuario.objects.create(username="geo_user", tenant=cls.tenant)

    @patch("nucleo.geo.requests.get", side_effect=_fake_get)
    def test_endpoint_resolve_por_cep(self, _get):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/geo/resolver/", {"cep": "01001-000"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["resultado"]["ibge"], "3550308")

    def test_endpoint_exige_autenticacao(self):
        resp = self.client.get("/api/geo/resolver/", {"cep": "01001-000"})
        self.assertIn(resp.status_code, (401, 403))

    @patch("nucleo.geo.requests.get", side_effect=_fake_get)
    def test_endpoint_lista_municipios_por_uf(self, _get):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/geo/municipios/", {"uf": "SP"})
        self.assertEqual(resp.status_code, 200)
        nomes = [m["nome"] for m in resp.json()["municipios"]]
        self.assertIn("São Paulo", nomes)
        self.assertIn("Campinas", nomes)
