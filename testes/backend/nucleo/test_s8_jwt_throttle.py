"""S8 — o backend verifica `iss`/`aud` do JWT, e a API tem teto de requisições.

Até aqui o backend só conferia a **assinatura** e o `exp`: qualquer token assinado
com a mesma chave era aceito, viesse de onde viesse. Num ecossistema com vários
consumidores da mesma chave (backend, drone, tokens de serviço), isso significa
que um token emitido para outro público passava aqui como se fosse desta API.

Os dois valores precisam bater com os da emissão (`iam/iam_project/settings.py`).
Divergência derruba TODA a autenticação — por isso a regressão existe: é o tipo de
config que quebra silenciosamente num deploy e só aparece como "ninguém consegue
entrar".
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from unittest import mock

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory, APITestCase
from rest_framework.throttling import UserRateThrottle

from nucleo.authentication import IamJWTAuthentication
from nucleo.models import Notificacao, Tenant, Usuario


@lru_cache(maxsize=1)
def _par_efemero():
    """Um par RSA gerado aqui, para o teste poder assinar — o D50.

    **O backend não tem chave privada, e isso está certo.** Ele é *resource
    server*: recebe `JWT_PUBLIC_KEY_PATH`, verifica, e não emite nada. Quem
    assina é a IAM. Então `SIGNING_KEY` é string vazia por desenho, e o teste que
    assinava com ela morria em `InvalidKeyError` — não por defeito do backend,
    mas por pedir à configuração de produção uma capacidade que ela nega de
    propósito.

    **O vermelho era o menor dos dois problemas.** No CI estes testes *passavam*:
    lá não há `JWT_PUBLIC_KEY_PATH`, o arranjo do S3 cai no ramo HS256 e assina
    com o `JWT_SECRET`. As quatro regressões que provam o S8 exercitavam, então,
    só a configuração que **não** é a de produção — e a que é (RS256, sem
    privada) era exatamente onde elas não rodavam. Um erro no caminho RS256
    passaria pelo gate sem ninguém ver.

    Com o par efêmero o teste deixa de perguntar como a máquina está configurada:
    assina com a privada daqui, verifica com a pública daqui, e é **RS256 sempre**
    — no CI, no contêiner e no laptop. É a mesma doença do
    [D125](../../docs/historico-correcoes.md), que era teste dependente de
    ambiente, numa segunda forma.

    `lru_cache` porque gerar RSA de 2048 bits custa dezenas de milissegundos e o
    par não precisa ser diferente a cada teste — o que ele precisa é não vir de
    fora.
    """
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    privada = chave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    publica = chave.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return privada, publica


def _jwt_com_par_efemero():
    """`SIMPLE_JWT` igual ao de produção, trocando só o arranjo de chaves.

    `deepcopy` e não um dicionário novo: `ISSUER`, `AUDIENCE` e o resto têm de
    continuar vindo do settings real, senão o teste passaria a provar os valores
    que ele mesmo escreveu — que é o oposto do que a regressão do S8 existe para
    fazer.
    """
    privada, publica = _par_efemero()
    config = deepcopy(settings.SIMPLE_JWT)
    config.update({
        "ALGORITHM": "RS256",
        "SIGNING_KEY": privada,
        "VERIFYING_KEY": publica,
    })
    return config


def _payload(**overrides):
    """Claims mínimas de um access token da IAM, com `iss`/`aud` corretos."""
    agora = datetime.now(timezone.utc)
    base = {
        "token_type": "access",
        "sub": "s8_user",
        "user_id": 1,
        "jti": "s8-teste",
        "iat": int(agora.timestamp()),
        "exp": int((agora + timedelta(minutes=5)).timestamp()),
        "iss": settings.SIMPLE_JWT["ISSUER"],
        "aud": settings.SIMPLE_JWT["AUDIENCE"],
        "tenant_id": None,
        "modules": [],
        "roles": [],
        "permissions": [],
    }
    base.update(overrides)
    return base


def _assinar(payload):
    """Assina com a privada efêmera, sempre em RS256 — ver `_par_efemero`."""
    privada, _ = _par_efemero()
    return jwt.encode(payload, privada, algorithm="RS256")


def _token(**overrides):
    return _assinar(_payload(**overrides))


@override_settings(SIMPLE_JWT=_jwt_com_par_efemero())
class S8IssuerAudienceTests(APITestCase):
    """A validação roda na classe de autenticação, então é ali que se testa —
    passar por uma view misturaria o resultado com entitlement e permissão.

    O `override_settings` troca **só as chaves** (D50). Ele chega mesmo ao
    verificador: o `rest_framework_simplejwt.settings` liga `reload_api_settings`
    ao sinal `setting_changed`, então o `TokenBackend` é remontado em vez de
    ficar preso ao que foi lido no import.
    """

    def setUp(self):
        self.auth = IamJWTAuthentication()
        self.factory = APIRequestFactory()

    def _autenticar(self, token):
        request = self.factory.get("/api/notificacoes/", HTTP_AUTHORIZATION=f"Bearer {token}")
        return self.auth.authenticate(request)

    def test_o_que_roda_aqui_e_rs256_de_verdade(self):
        """O D50 em uma linha — e ele não era sobre o vermelho.

        Era sobre estas regressões exercitarem **só** o ramo HS256, que é a
        configuração do CI e não a de produção. Sem esta asserção a lacuna volta
        em silêncio: bastaria alguém remover o `override_settings` num ambiente
        com `JWT_SECRET` para os quatro testes abaixo passarem verdes provando o
        caminho errado — que foi exatamente o estado anterior.
        """
        self.assertEqual(settings.SIMPLE_JWT["ALGORITHM"], "RS256")
        self.assertIn("BEGIN PRIVATE KEY", settings.SIMPLE_JWT["SIGNING_KEY"])
        self.assertIn("BEGIN PUBLIC KEY", settings.SIMPLE_JWT["VERIFYING_KEY"])
        # E os valores que a regressão do S8 existe para provar continuam vindo
        # do settings real, não do dicionário do teste.
        self.assertEqual(_payload()["iss"], settings.SIMPLE_JWT["ISSUER"])
        self.assertEqual(_payload()["aud"], settings.SIMPLE_JWT["AUDIENCE"])

    def test_assinatura_de_outra_chave_rsa_e_recusada(self):
        """A contraprova do par efêmero: ele não pode ter afrouxado a verificação.

        Um token com `iss`/`aud` perfeitos, RS256, bem formado — e assinado por
        **outra** privada. Se isto passasse, os quatro testes abaixo estariam
        provando nada.
        """
        intrusa = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = intrusa.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        token = jwt.encode(_payload(), pem, algorithm="RS256")
        with self.assertRaises(AuthenticationFailed):
            self._autenticar(token)

    def test_token_bem_formado_e_aceito(self):
        resultado = self._autenticar(_token())
        self.assertIsNotNone(resultado)
        user, _ = resultado
        self.assertEqual(user.username, "s8_user")

    def test_emissor_desconhecido_e_recusado(self):
        """Token assinado com a MESMA chave, mas emitido por outro `iss`."""
        with self.assertRaises(AuthenticationFailed):
            self._autenticar(_token(iss="emissor-invasor"))

    def test_audiencia_de_outro_produto_e_recusada(self):
        """O caso que motiva o `aud`: token válido, porém destinado a outro consumidor."""
        with self.assertRaises(AuthenticationFailed):
            self._autenticar(_token(aud="outro-produto"))

    def test_sem_iss_ou_aud_e_recusado(self):
        """Token legado (anterior ao S8) não é aceito: exigir a claim é o ponto."""
        for claim in ("iss", "aud"):
            payload = _payload()
            del payload[claim]
            token = _assinar(payload)
            with self.subTest(claim=claim), self.assertRaises(AuthenticationFailed):
                self._autenticar(token)


class S8ThrottleTests(APITestCase):
    """O teto em si. A suíte roda com as taxas desligadas (settings), então o
    teste as reativa — senão passaria verde sem exercitar nada."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="s8-throttle", nome="S8")
        cls.user = Usuario.objects.create(username="s8_throttle", tenant=cls.tenant)
        Notificacao.objects.create(user=cls.user, tenant=cls.tenant, titulo="oi")

    def setUp(self):
        # LocMem persiste entre testes do mesmo processo: sem limpar, a contagem
        # de um teste vaza para o próximo (a mesma armadilha que o S8 causou na
        # suíte da IAM, só que dentro de um run).
        cache.clear()

    def test_estoura_o_teto_e_recebe_429(self):
        self.client.force_authenticate(user=self.user)
        # `THROTTLE_RATES` é atributo de CLASSE, lido no import do DRF — por isso
        # não adianta `override_settings(REST_FRAMEWORK=...)` aqui.
        with mock.patch.dict(UserRateThrottle.THROTTLE_RATES, {"user": "3/min"}):
            codigos = [
                self.client.get("/api/notificacoes/").status_code for _ in range(5)
            ]
        self.assertEqual(codigos[:3], [200, 200, 200], f"início inesperado: {codigos}")
        self.assertEqual(codigos[3:], [429, 429], f"teto não aplicado: {codigos}")

    def test_configuracao_de_producao_tem_teto_definido(self):
        """Guarda contra o teto ser silenciosamente removido do settings — o
        desligamento vale só sob `manage.py test`.

        A asserção é sobre a CLASSE efetiva, não sobre o caminho de import: desde
        o D23 os eixos são as subclasses locais (DRF + fail-open), e travar o
        caminho literal faria este guard falhar a cada refatoração legítima em vez
        de a cada remoção do teto, que é o que ele existe para pegar.
        """
        from django.utils.module_loading import import_string

        classes = [
            import_string(caminho)
            for caminho in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"]
        ]
        self.assertTrue(
            any(issubclass(c, UserRateThrottle) for c in classes),
            "eixo por usuário saiu da configuração",
        )
        self.assertIn("anon", settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])
        self.assertIn("user", settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])

    def test_num_proxies_configurado(self):
        """Sem isto o DRF usa a cadeia INTEIRA do X-Forwarded-For como identidade.
        Como o gateway ACRESCENTA o IP real ao header que o cliente enviou, um XFF
        falso rotativo dava um balde novo a cada requisição — teto por IP furado."""
        self.assertEqual(settings.REST_FRAMEWORK.get("NUM_PROXIES"), 1)


class S8EscoposLigadosTests(APITestCase):
    """Os escopos nomeados só valem se alguma view os declarar. `relatorio` e
    `integracao_externa` nasceram no settings **sem nenhum consumidor** — taxa
    definida, efeito zero. Este teste existe para não voltarem a ser letra morta."""

    def test_dashboard_do_erp_usa_o_escopo_relatorio(self):
        from moduloerp.views import ERPDashboardView

        self.assertEqual(getattr(ERPDashboardView, "throttle_scope", None), "relatorio")

    def test_acoes_que_gastam_cota_de_terceiro_usam_escopo_proprio(self):
        """Emitir boleto/NF custa dinheiro e gera documento fiscal: teto menor."""
        from moduloerp.views import ContaReceberViewSet

        vs = ContaReceberViewSet()
        for acao in ("gerar_cobranca", "emitir_nota_fiscal_servico",
                     "emitir_nota_fiscal_produto", "emitir_lote_nfse"):
            with self.subTest(acao=acao):
                vs.action = acao
                vs.get_throttles()
                self.assertEqual(vs.throttle_scope, "integracao_externa")

    def test_crud_comum_nao_herda_o_escopo_apertado(self):
        """O teto de integração não pode vazar para listar/editar título, senão
        300/hora viraria o limite do uso normal da tela."""
        from moduloerp.views import ContaReceberViewSet

        vs = ContaReceberViewSet()
        vs.action = "list"
        vs.get_throttles()
        self.assertNotEqual(getattr(vs, "throttle_scope", None), "integracao_externa")
