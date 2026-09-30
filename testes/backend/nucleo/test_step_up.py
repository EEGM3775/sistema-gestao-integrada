"""Fase 6 da remodelagem — o step-up do ato grave no backend (§10.5, §10.8 classe C).

Atestar medição, aprovar aditivo, pagar, mandar lote ao banco, mudar alçada ou
escada, exportar ou apagar dado pessoal, purgar a lixeira e emitir CAT pedem que
a sessão tenha provado quem é **há pouco**: o `auth_time` do token dentro da
janela da pessoa (ficha publicada pela IAM; padrão 15 min, faixa 1–120 do dono).
Fora dela, 401 com o desafio da RFC 9470 — a pessoa pode, só precisa confirmar.
"""
import json
import time
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from funcoesautorizacao import chaves, classes
from nucleo import autorizacao, fichas
from nucleo.permissions import RequirePermission
from payment.planos import (
    CONFIRMACAO_JANELA_MAX_MIN,
    CONFIRMACAO_JANELA_PADRAO_MIN,
)

UID = "6fc85482-6578-4e40-85fd-c1edde6f806e"
TENANT = "15c4c985-f9a9-4d25-be7c-480641667e81"


def _pessoa(minutos_atras=0, **extra):
    return SimpleNamespace(
        is_authenticated=True, is_superuser=False, pk=1, username="ana",
        iam_user_id=UID, iam_tenant_id=TENANT,
        iam_auth_time=int(time.time()) - int(minutos_atras * 60), **extra,
    )


class RedisDeMentira:
    def __init__(self, dados=None):
        self.dados = dict(dados or {})

    def get(self, chave):
        return self.dados.get(chave)


class JanelaEClasseTests(SimpleTestCase):
    def setUp(self):
        fichas.esquecer()
        self.addCleanup(fichas.esquecer)
        self._redis(None)

    def _redis(self, janela_min):
        dados = {}
        if janela_min is not None:
            dados[chaves.ficha_da_pessoa(UID)] = json.dumps({"email": "a@b", "janela_confirmacao_min": janela_min})
        p = mock.patch("nucleo.autorizacao_pdp.redis", return_value=RedisDeMentira(dados))
        p.start()
        self.addCleanup(p.stop)
        fichas.esquecer()

    def test_so_a_classe_c_pede(self):
        velho = _pessoa(minutos_atras=600)
        for codigo in ("pdca.medicao.view", "pdca.nc.abrir", "rh.cpf.view"):
            with self.subTest(codigo=codigo):
                self.assertNotEqual(classes.classe_do_codigo(codigo), classes.C)
                autorizacao.exigir_confirmacao(velho, codigo)  # não levanta

    def test_cada_ato_da_lista_do_dono_pede(self):
        velho = _pessoa(minutos_atras=600)
        for codigo in sorted(classes.CRITICOS):
            with self.subTest(codigo=codigo), self.assertRaises(autorizacao.ConfirmacaoNecessaria):
                autorizacao.exigir_confirmacao(velho, codigo)

    def test_dentro_da_janela_padrao_passa_e_fora_nao(self):
        autorizacao.exigir_confirmacao(_pessoa(CONFIRMACAO_JANELA_PADRAO_MIN - 1), "erp.conta_pagar.baixar")
        with self.assertRaises(autorizacao.ConfirmacaoNecessaria) as erro:
            autorizacao.exigir_confirmacao(_pessoa(CONFIRMACAO_JANELA_PADRAO_MIN + 1), "erp.conta_pagar.baixar")
        self.assertEqual(erro.exception.status_code, 401)
        self.assertEqual(erro.exception.detail["codigo"], "confirmacao_necessaria")
        self.assertIn('error="insufficient_user_authentication"', erro.exception.auth_header)
        self.assertIn(f"max_age={CONFIRMACAO_JANELA_PADRAO_MIN * 60}", erro.exception.auth_header)

    def test_a_janela_e_a_da_ficha_da_pessoa(self):
        self._redis(60)
        autorizacao.exigir_confirmacao(_pessoa(45), "pdca.medicao.atestar")

    def test_a_ficha_nao_passa_do_teto_do_dono(self):
        self._redis(10_000)
        with self.assertRaises(autorizacao.ConfirmacaoNecessaria):
            autorizacao.exigir_confirmacao(_pessoa(CONFIRMACAO_JANELA_MAX_MIN + 1), "pdca.medicao.atestar")

    def test_sem_auth_time_pede(self):
        sem_prova = _pessoa()
        sem_prova.iam_auth_time = None
        with self.assertRaises(autorizacao.ConfirmacaoNecessaria):
            autorizacao.exigir_confirmacao(sem_prova, "plataforma.lgpd.exportar")

    def test_sem_pessoa_da_iam_nao_ha_sessao_a_confirmar(self):
        autorizacao.exigir_confirmacao(SimpleNamespace(is_authenticated=True), "plataforma.lixo.purgar")


class _Purgar(APIView):
    permission_classes = [RequirePermission]
    required_permission = "plataforma.lixo.purgar"

    def post(self, request):
        from rest_framework.response import Response

        return Response({"ok": True})


class PeloPortaoTests(TestCase):
    """O `RequirePermission` — o portão por onde passa quase todo ato grave."""

    def setUp(self):
        fichas.esquecer()
        self.addCleanup(fichas.esquecer)
        p = mock.patch("nucleo.autorizacao_pdp.redis", return_value=RedisDeMentira())
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(autorizacao, "pode", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def _post(self, usuario):
        request = APIRequestFactory().post("/x/", {}, format="json")
        from rest_framework.test import force_authenticate

        force_authenticate(request, user=usuario)
        return _Purgar.as_view()(request)

    def test_prova_velha_leva_401_com_o_desafio(self):
        r = self._post(_pessoa(minutos_atras=600))
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.data["codigo"], "confirmacao_necessaria")
        self.assertIn("insufficient_user_authentication", r["WWW-Authenticate"])

    def test_prova_recente_passa(self):
        self.assertEqual(self._post(_pessoa(minutos_atras=1)).status_code, 200)

    def test_sem_a_permissao_continua_403(self):
        with mock.patch.object(autorizacao, "pode", return_value=False):
            self.assertEqual(self._post(_pessoa(minutos_atras=600)).status_code, 403)
