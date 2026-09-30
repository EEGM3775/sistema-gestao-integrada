"""Remodelagem da segurança, fase 1 — o segundo fator (acesso-e-permissoes.md §10.5).

Critério de saída da fase (§10.12): **nenhum admin entra sem segundo fator**.
As classes abaixo cobram isso pela porta de verdade (`/auth/login/` e
`/auth/refresh/`), e cobram também o que torna o segundo fator digno do nome:
código que não se reusa, bloqueio por tentativa, código de recuperação de uso
único, desafio que não abre duas sessões e redefinição que nunca é silenciosa.
"""
import base64
import inspect

from django.core import mail
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from identity import catalog, segundo_fator, views
from identity.models import CodigoRecuperacao, EventoSeguranca, SegundoFator, Tenant, Usuario
from identity.tokens import access_with_claims, issue_refresh
from payment import planos

from .bff_de_teste import access_do_bff, carga


def _codigo(usuario, deslocamento=0):
    """O código que o app do usuário mostraria agora (ou no passo vizinho)."""
    fator = SegundoFator.objects.get(usuario=usuario)
    segredo = segundo_fator.decifrar(fator.segredo_cifrado)
    return segundo_fator.codigo_do_passo(segredo, segundo_fator.passo_atual() + deslocamento)


def _ativar(usuario):
    segundo_fator.iniciar_cadastro(usuario)
    return segundo_fator.confirmar_cadastro(usuario, _codigo(usuario))


class TotpRfc6238Tests(SimpleTestCase):
    """Os vetores do apêndice B da RFC 6238 (SHA-1, segredo ASCII
    `12345678901234567890`), nos 6 dígitos finais que o app mostra. Se isto
    passa, qualquer app autenticador gera o mesmo código que o servidor aceita."""

    SEGREDO = base64.b32encode(b"12345678901234567890").decode().rstrip("=")

    def test_vetores_da_rfc(self):
        for instante, esperado in [
            (59, "287082"), (1111111109, "081804"), (1111111111, "050471"),
            (1234567890, "005924"), (2000000000, "279037"),
        ]:
            with self.subTest(instante=instante):
                passo = segundo_fator.passo_atual(instante)
                self.assertEqual(segundo_fator.codigo_do_passo(self.SEGREDO, passo), esperado)

    def test_aceita_um_passo_para_cada_lado_e_nao_dois(self):
        agora = 1111111109
        passo = segundo_fator.passo_atual(agora)
        for delta, casa in [(-2, False), (-1, True), (0, True), (1, True), (2, False)]:
            codigo = segundo_fator.codigo_do_passo(self.SEGREDO, passo + delta)
            with self.subTest(delta=delta):
                self.assertEqual(
                    segundo_fator._passo_que_casa(self.SEGREDO, codigo, agora) is not None, casa,
                )

    def test_segredo_novo_tem_160_bits_em_base32(self):
        segredo = segundo_fator.novo_segredo()
        self.assertEqual(len(base64.b32decode(segredo + "=" * (-len(segredo) % 8))), 20)

    def test_uri_otpauth_e_qr(self):
        u = Usuario(username="ana")
        uri = segundo_fator.uri_otpauth(u, self.SEGREDO)
        self.assertTrue(uri.startswith("otpauth://totp/SGI%3Aana?secret="))
        self.assertTrue(segundo_fator.qr_svg(uri).startswith("data:image/svg+xml"))


class RegraDaCasaTests(SimpleTestCase):
    def test_limites_vem_do_payment(self):
        """Nenhum número de teto no módulo: todos chegam de `payment/planos.py`."""
        fonte = inspect.getsource(segundo_fator)
        for nome in (
            "SEGUNDO_FATOR_TENTATIVAS", "SEGUNDO_FATOR_BLOQUEIO_S",
            "SEGUNDO_FATOR_DESAFIO_VALIDADE_S", "SEGUNDO_FATOR_CODIGOS_DE_RECUPERACAO",
        ):
            self.assertIs(getattr(segundo_fator, nome), getattr(planos, nome))
            self.assertIn(nome, fonte)
        self.assertIs(views.CONFIRMACAO_JANELA_MAX_MIN, planos.CONFIRMACAO_JANELA_MAX_MIN)

    def test_contas_visadas_sao_codigos_do_catalogo(self):
        for codigo in segundo_fator.ALCADA_FINANCEIRA | segundo_fator.DADO_DE_SAUDE:
            self.assertIn(codigo, catalog.POR_CODIGO, f"{codigo} saiu do catálogo")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_HOST="mailpit-de-teste",
)
class BaseSegundoFator(TestCase):
    def setUp(self):
        cache.clear()
        self.t = Tenant.objects.create(nome="T", slug="t")
        self.admin = self._usuario("adm", is_tenant_admin=True)
        self.comum = self._usuario("ana")
        self.client = APIClient()

    def _usuario(self, username, **extra):
        u = Usuario.objects.create(username=username, email=f"{username}@t.com", tenant=self.t, **extra)
        u.set_password("senha-forte-1")
        u.save()
        return u

    def _login(self, username, **extra):
        return self.client.post(
            "/auth/login/", {"username": username, "password": "senha-forte-1", **extra}, format="json",
        )

    def _segunda_etapa(self, desafio, codigo):
        return self.client.post(
            "/auth/login/segundo-fator/", {"desafio": desafio, "codigo": codigo}, format="json",
        )

    def _bearer(self, usuario, amr=("pwd", "otp")):
        refresh = issue_refresh(usuario, remember=False, amr=list(amr))
        self.client.cookies["sgi_refresh"] = str(refresh)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_with_claims(refresh, usuario)}")
        return refresh


class QuemEObrigadoTests(BaseSegundoFator):
    def test_admin_e_supervisor_sim_comum_nao(self):
        dono = self._usuario("dono", is_superuser=True)
        self.assertTrue(segundo_fator.obrigatorio(self.admin))
        self.assertTrue(segundo_fator.obrigatorio(dono))
        self.assertFalse(segundo_fator.obrigatorio(self.comum))

    def test_a_volta_atras_por_tenant_nao_alcanca_o_supervisor(self):
        self.t.segundo_fator_obrigatorio = False
        self.t.save()
        dono = self._usuario("dono", is_superuser=True)
        self.assertFalse(segundo_fator.obrigatorio(Usuario.objects.get(pk=self.admin.pk)))
        self.assertTrue(segundo_fator.obrigatorio(dono))

    def test_o_segredo_fica_cifrado_no_banco(self):
        segredo, _uri = segundo_fator.iniciar_cadastro(self.comum)
        guardado = SegundoFator.objects.get(usuario=self.comum).segredo_cifrado
        self.assertNotIn(segredo, guardado)
        self.assertEqual(segundo_fator.decifrar(guardado), segredo)


class NenhumAdminEntraSemSegundoFatorTests(BaseSegundoFator):
    """O critério de saída da fase 1, pela porta de verdade."""

    def test_comum_sem_segundo_fator_entra_so_com_senha(self):
        r = self._login("ana")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(carga(access_do_bff(self.client))["amr"], ["pwd"])

    def test_admin_sem_segundo_fator_cai_no_cadastro_e_nao_ganha_sessao(self):
        r = self._login("adm")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["segundo_fator"], "cadastro")
        self.assertNotIn("access", r.data)
        self.assertNotIn("sgi_refresh", r.cookies)

    def test_o_cadastro_pelo_login_termina_em_sessao_com_otp(self):
        desafio = self._login("adm").data["desafio"]
        inicio = self.client.post("/auth/segundo-fator/cadastro/", {"desafio": desafio}, format="json")
        self.assertEqual(inicio.status_code, 200, inicio.data)
        self.assertTrue(inicio.data["qr"].startswith("data:image/svg+xml"))
        r = self.client.post(
            "/auth/segundo-fator/cadastro/confirmar/",
            {"desafio": desafio, "codigo": _codigo(self.admin)}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(carga(access_do_bff(self.client))["amr"], ["pwd", "otp"])
        self.assertEqual(len(r.data["codigos"]), planos.SEGUNDO_FATOR_CODIGOS_DE_RECUPERACAO)
        self.assertIn("sgi_refresh", r.cookies)
        self.assertTrue(
            EventoSeguranca.objects.filter(
                alvo=self.admin, tipo=EventoSeguranca.Tipo.SEGUNDO_FATOR_ATIVADO,
            ).exists()
        )

    def test_o_desafio_do_cadastro_nao_abre_a_etapa_do_codigo(self):
        desafio = self._login("adm").data["desafio"]
        _ativar(self.admin)
        self.assertEqual(self._segunda_etapa(desafio, _codigo(self.admin, 1)).status_code, 401)

    def test_com_segundo_fator_a_senha_so_da_o_desafio(self):
        _ativar(self.admin)
        r = self._login("adm", remember=True)
        self.assertEqual(r.data["segundo_fator"], "codigo")
        self.assertNotIn("access", r.data)
        ok = self._segunda_etapa(r.data["desafio"], _codigo(self.admin, 1))
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(carga(access_do_bff(self.client))["amr"], ["pwd", "otp"])
        self.assertIsNotNone(ok.cookies["sgi_refresh"]["max-age"])  # o "lembrar" atravessou

    def test_a_sessao_antiga_do_admin_cai_no_refresh(self):
        """O dia do deploy: a sessão lembrada, aberta só com senha, não renova."""
        self._bearer(self.admin, amr=("pwd",))
        r = self.client.post("/auth/refresh/")
        self.assertEqual(r.status_code, 401)
        self.assertIn("segundo fator", r.data["detail"])

    def test_refresh_preserva_o_amr(self):
        _ativar(self.admin)
        self._bearer(self.admin)
        r = self.client.post("/auth/refresh/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(carga(access_do_bff(self.client))["amr"], ["pwd", "otp"])

    def test_comum_que_ativou_perde_a_sessao_so_de_senha(self):
        _ativar(self.comum)
        self._bearer(self.comum, amr=("pwd",))
        self.assertEqual(self.client.post("/auth/refresh/").status_code, 401)

    def test_volta_atras_do_tenant_devolve_o_login_so_com_senha(self):
        self.t.segundo_fator_obrigatorio = False
        self.t.save()
        r = self._login("adm")
        self.assertNotIn("segundo_fator", r.data)
        self.assertEqual(carga(access_do_bff(self.client))["amr"], ["pwd"])


class CodigoTests(BaseSegundoFator):
    def setUp(self):
        super().setUp()
        self.codigos = _ativar(self.comum)

    def _desafio(self):
        return self._login("ana").data["desafio"]

    def test_codigo_errado_e_recusado(self):
        r = self._segunda_etapa(self._desafio(), "000000" if _codigo(self.comum) != "000000" else "111111")
        self.assertEqual(r.status_code, 400)

    def test_o_mesmo_codigo_nao_vale_duas_vezes(self):
        codigo = _codigo(self.comum, 1)
        self.assertEqual(self._segunda_etapa(self._desafio(), codigo).status_code, 200)
        self.assertEqual(self._segunda_etapa(self._desafio(), codigo).status_code, 400)

    def test_o_desafio_nao_abre_duas_sessoes(self):
        desafio = self._desafio()
        self.assertEqual(self._segunda_etapa(desafio, _codigo(self.comum, 1)).status_code, 200)
        self.assertEqual(self._segunda_etapa(desafio, self.codigos[0]).status_code, 401)

    def test_desafio_adulterado_e_recusado(self):
        self.assertEqual(self._segunda_etapa(self._desafio() + "x", _codigo(self.comum, 1)).status_code, 401)

    def test_codigo_de_recuperacao_vale_uma_vez_e_avisa(self):
        mail.outbox.clear()
        r = self._segunda_etapa(self._desafio(), self.codigos[0].upper())
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["codigos_restantes"], planos.SEGUNDO_FATOR_CODIGOS_DE_RECUPERACAO - 1)
        self.assertEqual(self._segunda_etapa(self._desafio(), self.codigos[0]).status_code, 400)
        self.assertTrue(any("recuperação" in m.body for m in mail.outbox))

    def test_na_quinta_falha_trava_ate_o_codigo_certo(self):
        errado = "000000" if _codigo(self.comum) != "000000" else "111111"
        for _ in range(planos.SEGUNDO_FATOR_TENTATIVAS):
            self._segunda_etapa(self._desafio(), errado)
        r = self._segunda_etapa(self._desafio(), _codigo(self.comum, 1))
        self.assertEqual(r.status_code, 429)
        self.assertTrue(r.data["bloqueado"])
        self.assertTrue(
            EventoSeguranca.objects.filter(
                alvo=self.comum, tipo=EventoSeguranca.Tipo.SEGUNDO_FATOR_BLOQUEADO,
            ).exists()
        )

    def test_os_codigos_so_existem_como_hash(self):
        guardados = set(CodigoRecuperacao.objects.filter(usuario=self.comum).values_list("codigo_hash", flat=True))
        self.assertFalse(guardados & set(self.codigos))


class TelaDePerfilTests(BaseSegundoFator):
    def test_ativar_pelo_perfil_derruba_as_outras_sessoes(self):
        outra = issue_refresh(self.comum, remember=False)
        self._bearer(self.comum, amr=("pwd",))
        self.client.post("/auth/segundo-fator/cadastro/", {}, format="json")
        r = self.client.post(
            "/auth/segundo-fator/cadastro/confirmar/", {"codigo": _codigo(self.comum)}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(carga(access_do_bff(self.client))["amr"], ["pwd", "otp"])
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=outra["jti"]).exists())
        nova = RefreshToken(r.cookies["sgi_refresh"].value)  # valida: não está na blacklist
        self.assertNotEqual(nova["jti"], outra["jti"])

    def test_ativar_de_novo_e_conflito(self):
        _ativar(self.comum)
        self._bearer(self.comum)
        self.assertEqual(self.client.post("/auth/segundo-fator/cadastro/", {}, format="json").status_code, 409)

    def test_desativar_pede_senha_e_codigo(self):
        _ativar(self.comum)
        self._bearer(self.comum)
        r = self.client.post(
            "/auth/segundo-fator/desativar/", {"senha": "errada", "codigo": _codigo(self.comum, 1)}, format="json",
        )
        self.assertEqual(r.status_code, 400)
        mail.outbox.clear()
        r = self.client.post(
            "/auth/segundo-fator/desativar/",
            {"senha": "senha-forte-1", "codigo": _codigo(self.comum, 1)}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIsNone(segundo_fator.ativo(self.comum))
        self.assertEqual(len(mail.outbox), 1)

    def test_trocar_codigos_so_com_o_app(self):
        codigos = _ativar(self.comum)
        self._bearer(self.comum)
        r = self.client.post("/auth/segundo-fator/codigos/", {"codigo": codigos[0]}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/auth/segundo-fator/codigos/", {"codigo": _codigo(self.comum, 1)}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(set(r.data["codigos"]) & set(codigos))

    def test_estado_e_janela_de_confirmacao(self):
        self._bearer(self.admin)
        r = self.client.get("/auth/conta/seguranca/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["segundo_fator"]["obrigatorio"])
        self.assertIn("administrador", r.data["segundo_fator"]["motivos"])
        self.assertEqual(r.data["janela_confirmacao"]["minutos"], planos.CONFIRMACAO_JANELA_PADRAO_MIN)
        for invalido in (0, planos.CONFIRMACAO_JANELA_MAX_MIN + 1, "muito"):
            with self.subTest(minutos=invalido):
                r = self.client.patch(
                    "/auth/conta/seguranca/", {"janela_confirmacao_min": invalido}, format="json",
                )
                self.assertEqual(r.status_code, 400)
        r = self.client.patch("/auth/conta/seguranca/", {"janela_confirmacao_min": 30}, format="json")
        self.assertEqual(r.data["janela_confirmacao"]["minutos"], 30)


class RedefinicaoPeloAdminTests(BaseSegundoFator):
    def setUp(self):
        super().setUp()
        _ativar(self.comum)
        self.sessao_do_alvo = issue_refresh(self.comum, remember=False, amr=["pwd", "otp"])
        self._bearer(self.admin)

    def _redefinir(self, alvo):
        return self.client.post(f"/usuarios/{alvo.pk}/redefinir-segundo-fator/", {}, format="json")

    def test_redefine_derruba_as_sessoes_registra_e_avisa(self):
        mail.outbox.clear()
        r = self._redefinir(self.comum)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIsNone(segundo_fator.ativo(self.comum))
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=self.sessao_do_alvo["jti"]).exists())
        evento = EventoSeguranca.objects.get(tipo=EventoSeguranca.Tipo.SEGUNDO_FATOR_REDEFINIDO)
        self.assertEqual((evento.alvo_id, evento.autor_id), (self.comum.pk, self.admin.pk))
        self.assertEqual(mail.outbox[0].to, [self.comum.email])
        self.assertIn(self.admin.username, mail.outbox[0].body)

    def test_nao_redefine_a_propria_conta(self):
        _ativar(self.admin)
        self.assertEqual(self._redefinir(self.admin).status_code, 400)

    def test_admin_do_tenant_nao_alcanca_o_supervisor(self):
        dono = self._usuario("dono", is_superuser=True)
        _ativar(dono)
        self.assertEqual(self._redefinir(dono).status_code, 403)
        self.assertIsNotNone(segundo_fator.ativo(dono))

    def test_lista_de_usuarios_mostra_quem_tem(self):
        linhas = {u["username"]: u["segundo_fator_ativo"] for u in self.client.get("/usuarios/").data}
        self.assertEqual((linhas["ana"], linhas["adm"]), (True, False))
