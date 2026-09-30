"""Fase 5 da remodelagem — o BFF e a audiência por serviço (acesso-e-permissoes.md §10.5, §10.6).

Critério de saída (§10.12): **nenhum token acessível ao JavaScript**. O navegador
fica com dois cookies HttpOnly; o gateway troca o da sessão pelo access do
serviço de destino (`/auth/interno/bff/<serviço>/`), e cada serviço aceita só o
que foi emitido para ele. Aqui se cobra o lado da IAM:

- nenhuma resposta que o navegador recebe carrega um JWT;
- o access sai com o `aud` do serviço pedido, `typ` `at+jwt` e a sessão;
- escrita pelo cookie exige o cabeçalho anti-CSRF e a mesma origem;
- sessão revogada, vencida ou desconhecida não vira token;
- a volta atrás existe, e desligada não abre nada.
"""
import re
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from funcoesautorizacao import audiencias, chaves
from identity import sessoes
from identity.models import Sessao, Tenant, Usuario
from identity.tokens import access_with_claims, issue_refresh

from .bff_de_teste import access_do_bff, cabecalho, carga, decodificar

#: Um JWT em qualquer lugar de um texto: três partes base64url, a primeira `eyJ`.
_JWT = re.compile(r"eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+")


class RedisDeMentira:
    def __init__(self):
        self.dados = {}

    def get(self, chave):
        return self.dados.get(chave)

    def set(self, chave, valor, ex=None):
        self.dados[chave] = valor

    def delete(self, *chaves_):
        for chave in chaves_:
            self.dados.pop(chave, None)


class BaseBff(TestCase):
    def setUp(self):
        self.t = Tenant.objects.create(nome="T", slug="t-bff")
        self.ana = Usuario.objects.create(username="ana", email="ana@teste.com", tenant=self.t)
        self.ana.set_password("senha-forte-1")
        self.ana.save()
        self.client = APIClient()
        self.redis = RedisDeMentira()
        patcher = mock.patch("identity.revocation._redis", return_value=self.redis)
        patcher.start()
        self.addCleanup(patcher.stop)
        for alvo in ("identity.sessoes._redis", "identity.bff._redis"):
            p = mock.patch(alvo, return_value=self.redis)
            p.start()
            self.addCleanup(p.stop)

    def _login(self, client=None, **extra):
        r = (client or self.client).post(
            "/auth/login/", {"username": "ana", "password": "senha-forte-1", **extra}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        return r


class NenhumTokenNoNavegadorTests(BaseBff):
    """O critério de saída da fase 5, resposta por resposta."""

    def _sem_jwt(self, resposta, rotulo):
        corpo = resposta.content.decode()
        self.assertIsNone(_JWT.search(corpo), f"{rotulo}: há um token no corpo")
        for nome, valor in resposta.items():
            if nome.lower() != "set-cookie":
                self.assertIsNone(_JWT.search(valor), f"{rotulo}: há um token no cabeçalho {nome}")

    def test_login_renovacao_troca_de_senha_e_me(self):
        self._sem_jwt(self._login(), "login")
        self._sem_jwt(self.client.post("/auth/refresh/"), "renovação")
        self._sem_jwt(self.client.get("/auth/me/"), "me")
        self._sem_jwt(self.client.get("/auth/confirmar/"), "estado da confirmação")
        r = self.client.post("/auth/senha/", {"senha_atual": "senha-forte-1", "nova_senha": "outra-senha-2"},
                             format="json", HTTP_X_SGI_CSRF="1")
        self.assertEqual(r.status_code, 200, r.data)
        self._sem_jwt(r, "troca de senha")

    def test_os_cookies_sao_httponly(self):
        r = self._login()
        for nome in (settings.REFRESH_COOKIE_NAME, settings.SESSAO_COOKIE_NAME):
            self.assertTrue(r.cookies[nome]["httponly"], nome)
            self.assertEqual(r.cookies[nome]["samesite"], "Strict", nome)

    def test_a_credencial_do_cookie_so_existe_como_hash(self):
        r = self._login()
        credencial = r.cookies[settings.SESSAO_COOKIE_NAME].value
        sessao = Sessao.objects.get(usuario=self.ana)
        self.assertNotEqual(sessao.credencial_hash, credencial)
        self.assertEqual(sessao.credencial_hash, sessoes.hash_da_credencial(credencial))


class TrocaDoCookiePeloTokenTests(BaseBff):
    def test_o_access_de_cada_servico_tem_a_audiencia_dele(self):
        self._login()
        for servico, audiencia in audiencias.DO_BFF.items():
            with self.subTest(servico=servico):
                token = access_do_bff(self.client, servico)
                self.assertEqual(decodificar(token, audiencia)["aud"], audiencia)
                self.assertEqual(cabecalho(token)["typ"], "at+jwt")

    def test_o_access_carrega_a_sessao_e_a_idade_da_autenticacao(self):
        self._login()
        sessao = Sessao.objects.get(usuario=self.ana)
        c = carga(access_do_bff(self.client))
        self.assertEqual(c["sid"], str(sessao.sid))
        self.assertEqual(c["amr"], ["pwd"])
        self.assertEqual(c["acr"], "aal1")
        self.assertEqual(c["auth_time"], int(sessao.auth_time.timestamp()))
        self.assertEqual(c["sub"], "ana")
        self.assertEqual(c["tenant_id"], str(self.t.id))
        self.assertEqual(c["token_type"], "access")

    def test_o_mesmo_access_serve_aos_pedidos_seguintes(self):
        self._login()
        self.assertEqual(access_do_bff(self.client), access_do_bff(self.client))

    def test_servico_desconhecido_e_404(self):
        self._login()
        self.assertEqual(self.client.get("/auth/interno/bff/iam/").status_code, 404)

    def test_sem_cookie_o_pedido_segue_anonimo(self):
        r = self.client.get("/auth/interno/bff/api/")
        self.assertEqual(r.status_code, 204)
        self.assertNotIn("X-BFF-Authorization", r)

    def test_credencial_inventada_nao_vira_token(self):
        self.client.cookies[settings.SESSAO_COOKIE_NAME] = "inventada"
        self.assertIsNone(access_do_bff(self.client))

    def test_sessao_revogada_nao_vira_token_e_o_guardado_sai(self):
        self._login()
        access_do_bff(self.client)  # fica guardado
        self.assertTrue(any(k.startswith("sess:bff:") for k in self.redis.dados))
        sessoes.revogar(Sessao.objects.get(usuario=self.ana).sid, "logout")
        self.assertFalse(any(k.startswith("sess:bff:") for k in self.redis.dados))
        self.assertIsNone(access_do_bff(self.client))

    def test_sessao_vencida_nao_vira_token(self):
        self._login()
        Sessao.objects.filter(usuario=self.ana).update(expira_em=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(access_do_bff(self.client))

    def test_pessoa_desativada_perde_o_token(self):
        self._login()
        self.ana.is_active = False
        self.ana.save()
        self.assertIsNone(access_do_bff(self.client))

    def test_logout_apaga_o_cookie_e_a_sessao(self):
        self._login()
        r = self.client.post("/auth/logout/")
        self.assertEqual(r.cookies[settings.SESSAO_COOKIE_NAME].value, "")
        self.assertFalse(Sessao.objects.get(usuario=self.ana).ativa)

    def test_redis_fora_assina_de_novo_a_cada_pedido(self):
        self._login()
        with mock.patch("identity.bff._redis", side_effect=ConnectionError("fora")):
            self.assertIsNotNone(access_do_bff(self.client))

    def test_a_sessao_de_antes_da_fase_5_ganha_o_cookie_na_renovacao(self):
        """Quem estava logado no deploy não entra de novo: o refresh prova a sessão."""
        refresh = issue_refresh(self.ana, remember=False)
        Sessao.objects.filter(sid=refresh["sid"]).update(credencial_hash=None, auth_time=None)
        self.client.cookies[settings.REFRESH_COOKIE_NAME] = str(refresh)
        r = self.client.post("/auth/refresh/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIn(settings.SESSAO_COOKIE_NAME, r.cookies)
        self.assertEqual(carga(access_do_bff(self.client))["sid"], refresh["sid"])


class EscritaPeloCookieTests(BaseBff):
    """O cookie viaja sozinho; o cabeçalho anti-CSRF, não."""

    def _pedir(self, metodo, **extra):
        return self.client.get("/auth/interno/bff/api/", HTTP_X_ORIGINAL_METHOD=metodo, **extra)

    def test_leitura_nao_precisa_do_cabecalho(self):
        self._login()
        self.assertEqual(self._pedir("GET").status_code, 204)

    def test_escrita_sem_o_cabecalho_e_recusada(self):
        self._login()
        for metodo in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(metodo=metodo):
                self.assertEqual(self._pedir(metodo).status_code, 403)

    def test_escrita_com_o_cabecalho_passa(self):
        self._login()
        r = self._pedir("POST", HTTP_X_SGI_CSRF="1")
        self.assertEqual(r.status_code, 204)
        self.assertTrue(r["X-BFF-Authorization"].startswith("Bearer "))

    def test_escrita_de_outro_site_e_recusada_mesmo_com_o_cabecalho(self):
        self._login()
        self.assertEqual(
            self._pedir("POST", HTTP_X_SGI_CSRF="1", HTTP_SEC_FETCH_SITE="cross-site").status_code, 403,
        )
        self.assertEqual(
            self._pedir("POST", HTTP_X_SGI_CSRF="1", HTTP_ORIGIN="https://evil.example").status_code, 403,
        )

    def test_o_websocket_de_outro_site_nao_abre_com_a_sessao(self):
        """CSWSH: o upgrade é GET e não leva cabeçalho próprio — o `Origin` decide."""
        self._login()
        ws = {"HTTP_X_ORIGINAL_UPGRADE": "websocket"}  # como o gateway o repassa
        self.assertEqual(self._pedir("GET", HTTP_ORIGIN="https://evil.example", **ws).status_code, 403)
        self.assertEqual(self._pedir("GET", **ws).status_code, 403)  # sem Origin, nada
        r = self._pedir("GET", HTTP_ORIGIN="http://testserver", **ws)
        self.assertEqual(r.status_code, 204)
        self.assertTrue(r["X-BFF-Authorization"].startswith("Bearer "))

    def test_escrita_anonima_nao_e_barrada_aqui(self):
        """Sem cookie não há sessão a proteger; o serviço responde 401 à rota protegida."""
        self.assertEqual(self._pedir("POST").status_code, 204)


class VoltaAtrasTests(BaseBff):
    def test_desligada_o_bearer_do_cliente_nao_passa(self):
        r = self.client.get("/auth/interno/bff/api/", HTTP_AUTHORIZATION="Bearer qualquer")
        self.assertNotIn("X-BFF-Authorization", r)

    @override_settings(BFF_BEARER_DO_CLIENTE=True)
    def test_ligada_o_bearer_do_cliente_segue(self):
        r = self.client.get("/auth/interno/bff/api/", HTTP_AUTHORIZATION="Bearer qualquer")
        self.assertEqual(r["X-BFF-Authorization"], "Bearer qualquer")


class AudienciaDaIamTests(BaseBff):
    """O Bearer que a própria IAM aceita: `aud` sgi-iam e `typ` at+jwt."""

    def _me(self, token):
        return APIClient().get("/auth/me/", HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_o_access_da_iam_entra(self):
        refresh = issue_refresh(self.ana, remember=False)
        self.assertEqual(self._me(access_with_claims(refresh, self.ana)).status_code, 200)

    def test_o_access_de_outro_servico_nao_entra(self):
        self._login()
        self.assertEqual(self._me(access_do_bff(self.client, "api")).status_code, 401)
        self.assertEqual(self._me(access_do_bff(self.client, "drone")).status_code, 401)

    def test_o_token_de_servico_nao_entra_como_pessoa(self):
        from identity.emissao import token_de_servico

        self.assertEqual(
            self._me(token_de_servico(caller="x", tenant_id=str(self.t.id), produto="drone")).status_code,
            401,
        )

    def test_o_access_sem_typ_nao_entra(self):
        """O access do SimpleJWT puro (sem `typ`), mesmo com a audiência certa."""
        refresh = issue_refresh(self.ana, remember=False)
        self.assertEqual(self._me(str(refresh.access_token)).status_code, 401)

    def test_as_audiencias_do_drone_batem_com_as_do_java(self):
        """O drone não importa `funcoesautorizacao`: os valores estão no
        `application.properties` dele. Se um lado mudar, a esteira quebra aqui."""
        from pathlib import Path

        props = None
        for raiz in (Path(settings.BASE_DIR).parent, Path(settings.BASE_DIR)):
            candidato = raiz / "ImgDrone/funcoesODM/backend/java-service/src/main/resources/application.properties"
            if candidato.is_file():
                props = candidato.read_text(encoding="utf-8")
                break
        if props is None:
            self.skipTest("o fonte do drone não está nesta árvore (ImgDrone fica fora do git)")
        self.assertIn(f"jwt.audience=${{JWT_AUDIENCE_DRONE:{audiencias.DRONE}}}", props)
        self.assertIn(f"jwt.issuer=${{JWT_ISSUER:{audiencias.EMISSOR}}}", props)
        self.assertEqual(chaves.token_da_sessao("h", audiencias.API), "sess:bff:h:sgi-api")
