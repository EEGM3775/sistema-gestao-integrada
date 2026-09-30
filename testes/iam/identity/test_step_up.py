"""Fase 6 da remodelagem — o step-up do ato que muda quem pode (§10.5, §10.8 classe C).

Mudar papel é da lista de atos críticos do dono (`plataforma.papel.gerir`). Na
IAM isso é compor persona, liberar módulo e pôr ou tirar papel e admin de alguém.
Esses pedidos exigem que a sessão tenha provado quem é **dentro da janela** que a
pessoa escolheu; fora dela, a IAM responde o desafio da RFC 9470, e a tela pede
o código (ou a senha, para quem não tem segundo fator) em `/auth/confirmar/`.
"""
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from identity import segundo_fator
from identity.models import Perfil, Permissao, SegundoFator, Sessao, Tenant, Usuario
from payment import planos

from .bff_de_teste import access_do_bff, carga


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


def _codigo(usuario, deslocamento=0):
    fator = SegundoFator.objects.get(usuario=usuario)
    segredo = segundo_fator.decifrar(fator.segredo_cifrado)
    return segundo_fator.codigo_do_passo(segredo, segundo_fator.passo_atual() + deslocamento)


class BaseStepUp(TestCase):
    def setUp(self):
        cache.clear()
        self.t = Tenant.objects.create(nome="T", slug="t-step", segundo_fator_obrigatorio=False)
        call_command("sync_authz")
        self.admin = Usuario.objects.create(
            username="adm", email="adm@t.com", tenant=self.t, is_tenant_admin=True,
        )
        self.admin.set_password("senha-forte-1")
        self.admin.save()
        self.ana = Usuario.objects.create(username="ana", email="ana@t.com", tenant=self.t)
        self.client = APIClient()
        self.redis = RedisDeMentira()
        for alvo in ("identity.sessoes._redis", "identity.bff._redis", "identity.revocation._redis"):
            p = mock.patch(alvo, return_value=self.redis)
            p.start()
            self.addCleanup(p.stop)

    def _entrar(self):
        r = self.client.post("/auth/login/", {"username": "adm", "password": "senha-forte-1"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

    def _envelhecer(self, minutos):
        Sessao.objects.filter(usuario=self.admin).update(
            auth_time=timezone.now() - timedelta(minutes=minutos),
        )

    def _criar_persona(self, nome="recepcao"):
        obra_view = Permissao.objects.get(codename="obra.obra.view")
        return self.client.post(
            "/perfis/", {"nome": nome, "permissoes": [obra_view.id]}, format="json", HTTP_X_SGI_CSRF="1",
        )


class AtoGraveNaIamTests(BaseStepUp):
    def test_logo_depois_do_login_a_prova_e_recente(self):
        self._entrar()
        self.assertEqual(self._criar_persona().status_code, 201)

    def test_fora_da_janela_o_desafio_da_rfc_9470(self):
        self._entrar()
        self._envelhecer(planos.CONFIRMACAO_JANELA_PADRAO_MIN + 1)
        r = self._criar_persona()
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.data["codigo"], "confirmacao_necessaria")
        self.assertIn('error="insufficient_user_authentication"', r["WWW-Authenticate"])
        self.assertIn(f"max_age={planos.CONFIRMACAO_JANELA_PADRAO_MIN * 60}", r["WWW-Authenticate"])
        self.assertFalse(Perfil.objects.filter(tenant=self.t, nome="recepcao").exists())

    def test_a_janela_e_a_que_a_pessoa_escolheu(self):
        self.admin.janela_confirmacao_min = 60
        self.admin.save()
        self._entrar()
        self._envelhecer(30)
        self.assertEqual(self._criar_persona().status_code, 201)

    def test_a_janela_fora_da_faixa_do_dono_vale_o_teto(self):
        Usuario.objects.filter(pk=self.admin.pk).update(janela_confirmacao_min=10_000)
        self._entrar()
        self._envelhecer(planos.CONFIRMACAO_JANELA_MAX_MIN + 1)
        self.assertEqual(self._criar_persona().status_code, 401)

    def test_leitura_nao_pede_confirmacao(self):
        self._entrar()
        self._envelhecer(600)
        self.assertEqual(self.client.get("/perfis/").status_code, 200)

    def test_por_papel_e_admin_sim_por_nome_nao(self):
        self._entrar()
        self._envelhecer(600)
        url = f"/usuarios/{self.ana.id}/"
        self.assertEqual(
            self.client.patch(url, {"first_name": "Ana"}, format="json", HTTP_X_SGI_CSRF="1").status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(url, {"is_tenant_admin": True}, format="json", HTTP_X_SGI_CSRF="1").status_code,
            401,
        )
        self.ana.refresh_from_db()
        self.assertFalse(self.ana.is_tenant_admin)

    def test_liberar_modulo_pede_confirmacao(self):
        self._entrar()
        self._envelhecer(600)
        r = self.client.post("/acessos-modulo/", {}, format="json", HTTP_X_SGI_CSRF="1")
        self.assertEqual(r.status_code, 401)


class ConfirmarComSenhaTests(BaseStepUp):
    """Sem segundo fator, a senha redigitada (decisão 6 do dono)."""

    def test_o_estado_diz_o_que_pedir(self):
        self._entrar()
        r = self.client.get("/auth/confirmar/")
        self.assertEqual(r.data["metodo"], "senha")
        self.assertEqual(r.data["janela_s"], planos.CONFIRMACAO_JANELA_PADRAO_MIN * 60)

    def test_a_senha_faz_a_prova_andar_e_o_ato_passa(self):
        self._entrar()
        self._envelhecer(600)
        antes = carga(access_do_bff(self.client))["auth_time"]
        r = self.client.post("/auth/confirmar/", {"senha": "senha-forte-1"}, format="json", HTTP_X_SGI_CSRF="1")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertGreater(carga(access_do_bff(self.client))["auth_time"], antes)  # o guardado saiu
        self.assertEqual(self._criar_persona().status_code, 201)

    def test_senha_errada_nao_confirma(self):
        self._entrar()
        self._envelhecer(600)
        r = self.client.post("/auth/confirmar/", {"senha": "errada"}, format="json", HTTP_X_SGI_CSRF="1")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._criar_persona().status_code, 401)

    def test_errar_a_senha_trava_como_o_codigo(self):
        self._entrar()
        for _ in range(planos.SEGUNDO_FATOR_TENTATIVAS):
            self.client.post("/auth/confirmar/", {"senha": "errada"}, format="json", HTTP_X_SGI_CSRF="1")
        r = self.client.post("/auth/confirmar/", {"senha": "senha-forte-1"}, format="json", HTTP_X_SGI_CSRF="1")
        self.assertEqual(r.status_code, 429)

    def test_confirmar_pelo_cookie_exige_o_anti_csrf(self):
        self._entrar()
        r = self.client.post("/auth/confirmar/", {"senha": "senha-forte-1"}, format="json")
        self.assertEqual(r.status_code, 403)


class ConfirmarComCodigoTests(BaseStepUp):
    """Com segundo fator, o código do app — e só ele."""

    def setUp(self):
        super().setUp()
        segundo_fator.iniciar_cadastro(self.admin)
        segundo_fator.confirmar_cadastro(self.admin, _codigo(self.admin))
        r = self.client.post("/auth/login/", {"username": "adm", "password": "senha-forte-1"}, format="json")
        ok = self.client.post(
            "/auth/login/segundo-fator/", {"desafio": r.data["desafio"], "codigo": _codigo(self.admin, 1)},
            format="json",
        )
        self.assertEqual(ok.status_code, 200, ok.data)
        self._envelhecer(600)

    def test_o_estado_pede_o_codigo(self):
        self.assertEqual(self.client.get("/auth/confirmar/").data["metodo"], "codigo")

    def test_a_senha_nao_basta(self):
        r = self.client.post("/auth/confirmar/", {"senha": "senha-forte-1"}, format="json", HTTP_X_SGI_CSRF="1")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._criar_persona().status_code, 401)

    def test_codigo_de_recuperacao_nao_assina_ato_grave(self):
        codigos = segundo_fator.gerar_codigos(self.admin)
        r = self.client.post("/auth/confirmar/", {"codigo": codigos[0]}, format="json", HTTP_X_SGI_CSRF="1")
        self.assertEqual(r.status_code, 400)

    def test_o_codigo_do_app_confirma(self):
        # O cadastro gastou o passo atual e o login o seguinte: a confirmação é
        # 30 s depois, no passo de depois (o anti-reuso não aceita voltar).
        codigo = _codigo(self.admin, 2)
        daqui_a_pouco = segundo_fator.passo_atual() + 1
        with mock.patch("identity.segundo_fator.passo_atual", return_value=daqui_a_pouco):
            r = self.client.post(
                "/auth/confirmar/", {"codigo": codigo}, format="json", HTTP_X_SGI_CSRF="1",
            )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(carga(access_do_bff(self.client))["amr"], ["pwd", "otp"])
        self.assertEqual(self._criar_persona().status_code, 201)
