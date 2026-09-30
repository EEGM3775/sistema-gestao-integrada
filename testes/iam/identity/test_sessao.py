"""Fase 4 — a sessão tem identidade (`sid`) e se revoga em segundos (§10.5).

O access já emitido deixa de valer em todo serviço quando a sessão acaba —
logout, troca de senha, "encerrar todas", desativação —, e não quando expira.
Aqui se cobra o lado da IAM: a linha da `Sessao`, a publicação no Redis, a
rotação que preserva a sessão, o refresh que recusa a sessão encerrada e a
pergunta interna que o PEP sem Redis faz. E as fichas que substituem o que
era da empresa e da pessoa no token.
"""
import base64
import json
from unittest import mock

from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient

from funcoesautorizacao import chaves
from identity import fichas, sessoes
from identity.models import Sessao, Tenant, Usuario

from .bff_de_teste import access_do_bff


def _carga(token) -> dict:
    parte = str(token).split(".")[1]
    return json.loads(base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4)))


class RedisDeMentira:
    def __init__(self):
        self.dados = {}

    def set(self, chave, valor, ex=None):
        self.dados[chave] = str(valor)

    def get(self, chave):
        return self.dados.get(chave)

    def delete(self, *chaves_):
        for chave in chaves_:
            self.dados.pop(chave, None)

    def pipeline(self):
        return self

    def execute(self):
        return []


class SessaoTests(TestCase):
    def setUp(self):
        self.t = Tenant.objects.create(nome="T", slug="t-sessao")
        self.user = Usuario.objects.create(username="sid", email="sid@teste.com", tenant=self.t)
        self.user.set_password("segredo123")
        self.user.save()
        self.client = APIClient()
        self.redis = RedisDeMentira()
        patcher = mock.patch("identity.sessoes._redis", return_value=self.redis)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _login(self, client=None):
        r = (client or self.client).post(
            "/auth/login/", {"username": "sid", "password": "segredo123"}, format="json"
        )
        self.assertEqual(r.status_code, 200)
        return _carga(access_do_bff(client or self.client))["sid"]

    def test_o_login_abre_uma_sessao_e_o_access_a_carrega(self):
        sid = self._login()
        self.assertTrue(Sessao.objects.get(sid=sid).ativa)

    def test_a_rotacao_preserva_a_sessao(self):
        sid = self._login()
        r = self.client.post("/auth/refresh/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(_carga(access_do_bff(self.client))["sid"], sid)
        self.assertEqual(Sessao.objects.filter(usuario=self.user).count(), 1)

    def test_logout_revoga_a_sessao_e_publica_no_redis(self):
        sid = self._login()
        self.assertEqual(self.client.post("/auth/logout/").status_code, 200)
        self.assertFalse(Sessao.objects.get(sid=sid).ativa)
        self.assertEqual(Sessao.objects.get(sid=sid).motivo, "logout")
        self.assertIn(chaves.sessao_revogada(sid), self.redis.dados)

    def test_refresh_de_sessao_encerrada_e_recusado(self):
        """Mesmo com um refresh que não está na blacklist — a sessão é que manda."""
        sid = self._login()
        sessoes.revogar(sid, "encerrar_todas")
        self.assertEqual(self.client.post("/auth/refresh/").status_code, 401)

    def test_trocar_a_senha_encerra_as_outras_sessoes(self):
        outro = APIClient()
        sid_outro = self._login(outro)
        self._login()
        r = self.client.post(
            "/auth/senha/", {"senha_atual": "segredo123", "nova_senha": "segredo456"}, format="json",
            HTTP_X_SGI_CSRF="1",
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Sessao.objects.get(sid=sid_outro).ativa)
        self.assertTrue(Sessao.objects.get(sid=_carga(access_do_bff(self.client))["sid"]).ativa)

    def test_desativar_encerra_todas(self):
        sid = self._login()
        self.user.is_active = False
        self.user.save()
        self.assertFalse(Sessao.objects.get(sid=sid).ativa)
        self.assertEqual(Sessao.objects.get(sid=sid).motivo, "desativacao")

    def test_a_pergunta_interna_do_pep(self):
        sid = self._login()
        r = self.client.get(f"/auth/interno/sessao/{sid}/")
        self.assertEqual((r.status_code, r.data), (200, {"ativa": True}))
        sessoes.revogar(sid, "logout")
        self.assertEqual(self.client.get(f"/auth/interno/sessao/{sid}/").data, {"ativa": False})
        self.assertEqual(self.client.get("/auth/interno/sessao/nao-e-uuid/").status_code, 404)

    def test_redis_fora_nao_impede_a_revogacao_na_tabela(self):
        sid = self._login()
        with mock.patch("identity.sessoes._redis", side_effect=ConnectionError("fora")):
            sessoes.revogar(sid, "logout")
        self.assertFalse(sessoes.ativa(sid))

    def test_o_me_da_a_lista_mesmo_com_o_token_enxuto(self):
        self._login()
        self.assertNotIn("permissions", _carga(access_do_bff(self.client)))
        r = self.client.get("/auth/me/")  # o navegador entra pelo cookie da sessão
        self.assertEqual(r.status_code, 200)
        self.assertIn("permissions", r.data)
        self.assertIn("modules", r.data)


class FichasTests(TestCase):
    def setUp(self):
        self.t = Tenant.objects.create(nome="Construtora", slug="t-fichas", plano="profissional")
        self.ana = Usuario.objects.create(username="ana", email="ana@teste.com", tenant=self.t)
        Usuario.objects.create(username="inativo", email="x@teste.com", tenant=self.t, is_active=False)
        self.redis = RedisDeMentira()

    def test_publica_a_empresa_e_as_pessoas_ativas(self):
        self.assertEqual(fichas.publicar(self.t.id, self.redis), 2)
        empresa = json.loads(self.redis.dados[chaves.ficha_da_empresa(str(self.t.id))])
        self.assertEqual(empresa["slug"], "t-fichas")
        self.assertEqual(empresa["plano"], "profissional")
        for chave in ("rate_hora", "quotas"):
            self.assertIn(chave, empresa)
        self.assertGreaterEqual(empresa["quotas"]["auditoria_decisao_retencao_dias"], 180)
        pessoa = json.loads(self.redis.dados[chaves.ficha_da_pessoa(str(self.ana.id))])
        self.assertEqual(pessoa, {"email": "ana@teste.com", "janela_confirmacao_min": 15})

    def test_empresa_excluida_perde_a_ficha(self):
        fichas.publicar(self.t.id, self.redis)
        fichas.apagar_empresa(self.t.id, self.redis)
        self.assertNotIn(chaves.ficha_da_empresa(str(self.t.id)), self.redis.dados)

    def test_a_ficha_nao_leva_o_que_ninguem_precisa(self):
        """Minimização (§10.6): a ficha da pessoa é o e-mail e a janela do step-up."""
        fichas.publicar(self.t.id, self.redis)
        pessoa = json.loads(self.redis.dados[chaves.ficha_da_pessoa(str(self.ana.id))])
        self.assertEqual(set(pessoa), {"email", "janela_confirmacao_min"})


class TokenDeServicoTests(TestCase):
    def test_leva_so_o_escopo_do_produto_alvo(self):
        from identity.emissao import token_de_servico

        carga = _carga(token_de_servico(caller="backend", tenant_id="t1", produto="drone"))
        self.assertTrue(carga["svc"])
        self.assertEqual(carga["aud"], "sgi-drone")
        self.assertEqual(carga["scope"], "drone.projetos.desvincular")
        for claim in ("permissions", "roles", "modules", "is_tenant_admin", "email", "user_id", "sid"):
            self.assertNotIn(claim, carga)

    def test_sem_cookie_de_refresh_no_logout_nao_quebra(self):
        self.assertEqual(APIClient().post("/auth/logout/").status_code, 200)
        self.assertTrue(settings.REFRESH_COOKIE_NAME)
