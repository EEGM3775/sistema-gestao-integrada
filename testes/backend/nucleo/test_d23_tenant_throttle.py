"""D23 — teto de entrada por TENANT (camada 1) e fail-open dos três eixos.

O S8 tinha os eixos de IP e usuário; faltava o que define um SaaS. O teste que
importa é o primeiro: **dois usuários da mesma empresa dividem o balde**. É isso
que impede o noisy neighbor, e é exatamente o que os eixos anteriores não fazem —
com teto só por usuário, 20 funcionários multiplicam o consumo da empresa por 20
sem que ninguém tenha declarado esse número em lugar nenhum.

A suíte roda com as taxas desligadas (settings, ver D19), então os testes as
reativam por patch no atributo de CLASSE — `override_settings` não alcança
`THROTTLE_RATES`, que o DRF lê no import.
"""
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from rest_framework.test import APITestCase

from nucleo.models import Notificacao, Tenant, Usuario
from nucleo.throttling import TenantRateThrottle, UsuarioRateThrottle


class D23TenantThrottleTests(APITestCase):
    """`/api/notificacoes/` serve de cobaia: é tenant-scoped e barato."""

    @classmethod
    def setUpTestData(cls):
        cls.empresa_a = Tenant.objects.create(slug="d23-a", nome="Empresa A")
        cls.empresa_b = Tenant.objects.create(slug="d23-b", nome="Empresa B")
        # Dois funcionários da MESMA empresa — o cenário do achado.
        cls.ana = Usuario.objects.create(username="d23_ana", tenant=cls.empresa_a)
        cls.bruno = Usuario.objects.create(username="d23_bruno", tenant=cls.empresa_a)
        cls.carla = Usuario.objects.create(username="d23_carla", tenant=cls.empresa_b)
        for user in (cls.ana, cls.bruno, cls.carla):
            Notificacao.objects.create(user=user, tenant=user.tenant, titulo="oi")

    def setUp(self):
        # LocMem persiste entre testes do mesmo processo: sem limpar, a contagem
        # de um teste vaza para o próximo.
        cache.clear()

    def _get(self, user):
        self.client.force_authenticate(user=user)
        return self.client.get("/api/notificacoes/").status_code

    def test_usuarios_da_mesma_empresa_dividem_o_balde(self):
        """O ponto do D23: o teto é da EMPRESA, não de cada pessoa.

        Sem este eixo, Ana e Bruno teriam um teto cada e a empresa consumiria o
        dobro do declarado. Com ele, o 3º request da empresa é recusado mesmo
        vindo de quem ainda não gastou nada.
        """
        with mock.patch.dict(TenantRateThrottle.THROTTLE_RATES, {"tenant": "2/min"}):
            self.assertEqual(self._get(self.ana), 200)
            self.assertEqual(self._get(self.ana), 200)
            # Bruno é outro usuário, mas a cota da empresa já acabou.
            self.assertEqual(self._get(self.bruno), 429)

    def test_empresas_diferentes_tem_baldes_independentes(self):
        """A contrapartida obrigatória: o teto de uma empresa não pode respingar
        na outra — seria transformar o remédio do noisy neighbor no próprio mal."""
        with mock.patch.dict(TenantRateThrottle.THROTTLE_RATES, {"tenant": "1/min"}):
            self.assertEqual(self._get(self.ana), 200)
            self.assertEqual(self._get(self.ana), 429)
            self.assertEqual(self._get(self.carla), 200, "empresa B pagou pela A")

    def test_429_do_eixo_empresa_diz_que_a_conta_nao_foi_bloqueada(self):
        """Texto do 429 (§2.4): bloqueio da EMPRESA e bloqueio da CONTA levam o
        usuário a ações opostas. A mensagem padrão do DRF não distingue."""
        with mock.patch.dict(TenantRateThrottle.THROTTLE_RATES, {"tenant": "1/min"}):
            self._get(self.ana)
            resposta = self.client.get("/api/notificacoes/")
        self.assertEqual(resposta.status_code, 429)
        self.assertIn("empresa", str(resposta.data["detail"]).lower())
        self.assertIn("Retry-After", resposta.headers)

    def test_usuario_sem_tenant_nao_quebra(self):
        """Dono da plataforma não pertence a empresa nenhuma: o eixo não se
        aplica (devolve None) e a requisição segue pelos eixos anon/user — o que
        NÃO pode acontecer é erro por chave de cache vazia."""
        sem_empresa = Usuario.objects.create(username="d23_plataforma", tenant=None)
        with mock.patch.dict(TenantRateThrottle.THROTTLE_RATES, {"tenant": "1/min"}):
            self.client.force_authenticate(user=sem_empresa)
            for _ in range(3):
                self.assertEqual(self.client.get("/api/notificacoes/").status_code, 200)


class D23TetoDerivadoTests(APITestCase):
    """Guarda de configuração: o teto de usuário é FRAÇÃO do teto da empresa.

    Um valor solto volta a mentir nas duas pontas (ver settings.py). Este teste
    existe para a relação não se perder num ajuste futuro de env.
    """

    def test_teto_de_usuario_e_fracao_do_teto_da_empresa(self):
        taxas = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        self.assertIn("tenant", taxas)
        tenant_qtd = int(settings.THROTTLE_TENANT.split("/")[0])
        user_qtd = int(settings.THROTTLE_USER.split("/")[0])
        self.assertLess(user_qtd, tenant_qtd,
                        "usuário sozinho não pode ter teto ≥ ao da empresa inteira")

    def test_eixo_tenant_esta_ligado_em_producao(self):
        """O desligamento das taxas vale só sob `manage.py test` (D19); a classe
        tem de continuar na lista, senão o eixo some sem ninguém notar."""
        self.assertIn(
            "nucleo.throttling.TenantRateThrottle",
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"],
        )

    def test_derivacao_calcula_a_fracao(self):
        from config.settings import _fracao_do_teto

        self.assertEqual(_fracao_do_teto("60000/hour", 0.05), "3000/hour")
        self.assertEqual(_fracao_do_teto("1000/min", 0.5), "500/min")
        # Taxa malformada não pode virar exceção no boot: quem reclama é o DRF.
        self.assertEqual(_fracao_do_teto("invalido", 0.5), "invalido")


class D23TetoDoPlanoTests(APITestCase):
    """O teto vem do PLANO, pela claim `rate_hora` que a IAM emite.

    Um teto constante não tem valor que funcione: alto para a empresa de 1000 não
    protege contra a de 50 abusando; baixo para proteger inutiliza a de 1000.
    Aqui se prova que dois tenants no mesmo servidor têm tetos diferentes.
    """

    @classmethod
    def setUpTestData(cls):
        cls.pequena = Tenant.objects.create(slug="d23-free", nome="1 engenheiro")
        cls.grande = Tenant.objects.create(slug="d23-emp", nome="Construtora grande")
        cls.joao = Usuario.objects.create(username="d23_joao", tenant=cls.pequena)
        cls.maria = Usuario.objects.create(username="d23_maria", tenant=cls.grande)
        for user in (cls.joao, cls.maria):
            Notificacao.objects.create(user=user, tenant=user.tenant, titulo="oi")

    def setUp(self):
        cache.clear()

    def _get(self, user, teto):
        # É o que a autenticação faz ao ler a claim do JWT da IAM.
        user.iam_rate_hora = teto
        self.client.force_authenticate(user=user)
        return self.client.get("/api/notificacoes/")

    def test_plano_maior_recebe_teto_maior_no_mesmo_servidor(self):
        with mock.patch.dict(TenantRateThrottle.THROTTLE_RATES, {"tenant": "1/min"}):
            # A pequena tem 2/h de teto: a 3ª chamada é recusada.
            self.assertEqual(self._get(self.joao, 2).status_code, 200)
            self.assertEqual(self._get(self.joao, 2).status_code, 200)
            self.assertEqual(self._get(self.joao, 2).status_code, 429)
            # A grande, com teto de 50, segue passando — mesmo servidor, mesma hora.
            for _ in range(5):
                self.assertEqual(self._get(self.maria, 50).status_code, 200)

    def test_sem_claim_vale_o_default_do_settings(self):
        """Token de serviço ou token legado não quebram: caem no teto global."""
        with mock.patch.dict(TenantRateThrottle.THROTTLE_RATES, {"tenant": "2/min"}):
            self.assertEqual(self._get(self.joao, None).status_code, 200)
            self.assertEqual(self._get(self.joao, None).status_code, 200)
            self.assertEqual(self._get(self.joao, None).status_code, 429)

    def test_headers_de_teto_acompanham_a_resposta(self):
        """`X-RateLimit-*` é o padrão de fato (GitHub, Stripe, Shopify). Sem eles
        o cliente só descobre o teto batendo nele — que é o que o teto evita."""
        with mock.patch.dict(TenantRateThrottle.THROTTLE_RATES, {"tenant": "1/min"}):
            resposta = self._get(self.maria, 100)
        self.assertEqual(resposta.headers["X-RateLimit-Limit"], "100")
        self.assertEqual(resposta.headers["X-RateLimit-Remaining"], "99")
        self.assertTrue(int(resposta.headers["X-RateLimit-Reset"]) > 0)


class D23FailOpenTests(APITestCase):
    """Redis fora do ar não pode virar API fora do ar.

    `django_redis` com `IGNORE_EXCEPTIONS=True` devolve **None** (não o default)
    quando o Redis cai — e o `SimpleRateThrottle` do DRF faz `history.insert(...)`
    logo depois. Sem o `FailOpenMixin` isso é `AttributeError` → **500 em toda
    requisição autenticada**: o teto derrubaria justamente o que existe para
    proteger. Este teste simula a queda.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="d23-failopen", nome="FailOpen")
        cls.user = Usuario.objects.create(username="d23_fo", tenant=cls.tenant)
        Notificacao.objects.create(user=cls.user, tenant=cls.tenant, titulo="oi")

    def setUp(self):
        cache.clear()

    def test_cache_devolvendo_none_libera_em_vez_de_500(self):
        self.client.force_authenticate(user=self.user)
        taxas = {"tenant": "10/min", "user": "10/min"}
        with mock.patch.dict(TenantRateThrottle.THROTTLE_RATES, taxas), \
             mock.patch.dict(UsuarioRateThrottle.THROTTLE_RATES, taxas), \
             mock.patch("django.core.cache.cache.get", return_value=None):
            resposta = self.client.get("/api/notificacoes/")
        self.assertEqual(resposta.status_code, 200, "queda do Redis virou erro")

    def test_falha_da_cache_e_registrada_como_erro(self):
        """Fail-open silencioso é indistinguível de protetor funcionando (D21)."""
        self.client.force_authenticate(user=self.user)
        with mock.patch.dict(TenantRateThrottle.THROTTLE_RATES, {"tenant": "10/min"}), \
             mock.patch("django.core.cache.cache.get", side_effect=OSError("redis fora")), \
             self.assertLogs("nucleo.throttling", level="ERROR") as logs:
            self.client.get("/api/notificacoes/")
        self.assertTrue(any("throttle_indisponivel" in linha for linha in logs.output))
