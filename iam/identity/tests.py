"""Testes do RBAC — catálogo + templates + permissões no JWT (Fase 9, fatia A)."""
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from identity import catalog
from identity.models import (
    Tenant, Modulo, Usuario, AssinaturaTenant, AcessoUsuarioModulo, Perfil, Permissao,
)
from identity.tokens import build_claims


class CatalogoConformidadeTests(TestCase):
    """Conformidade estática: o vocabulário é finito, único e os templates ⊆ catálogo."""

    def test_codigos_unicos(self):
        codigos = [p.code for p in catalog.CATALOGO]
        self.assertEqual(len(codigos), len(set(codigos)), "há código duplicado no catálogo")

    def test_formato_modulo_recurso_acao(self):
        for p in catalog.CATALOGO:
            self.assertEqual(p.code.count("."), 2, f"código fora do formato modulo.recurso.acao: {p.code}")

    def test_todo_template_subset_do_catalogo(self):
        self.assertEqual(catalog.templates_invalidos(), {}, "template referencia código fora do catálogo")

    def test_segregacao_medico_x_gestor(self):
        gestor = set(catalog.codigos_do_template("rh_gestor"))
        self.assertNotIn("rh.dado_medico.view", gestor)
        self.assertIn("rh.dado_medico.view", catalog.codigos_do_template("rh_medico"))

    def test_relatorio_financeiro_visivel_aos_papeis_de_dinheiro(self):
        """D3: o hub/dashboard do ERP (`erp.relatorio.view`) deve alcançar todo
        papel com atribuição financeira/fiscal — senão o hub 403 e os KPIs/gráficos
        não carregam. Personas sem relação com dinheiro seguem de fora."""
        for persona in ("diretoria", "financeiro", "tesouraria", "fiscal", "auditor"):
            self.assertIn(
                "erp.relatorio.view", catalog.codigos_do_template(persona),
                f"persona financeira/fiscal '{persona}' sem acesso ao relatório do ERP",
            )
        for persona in ("comercial", "engenharia", "campo", "operacional"):
            self.assertNotIn(
                "erp.relatorio.view", catalog.codigos_do_template(persona),
                f"persona não-financeira '{persona}' não deveria ver o relatório do ERP",
            )


class SyncAuthzTests(TestCase):
    def test_sync_cria_permissoes_e_papeis_idempotente(self):
        t = Tenant.objects.create(nome="T", slug="t")
        call_command("sync_authz", tenant="t")
        self.assertEqual(Permissao.objects.count(), len(catalog.CATALOGO))
        self.assertEqual(
            Perfil.objects.filter(tenant=t).count(), len(catalog.TEMPLATES_PAPEL)
        )
        medico = Perfil.objects.get(tenant=t, nome="rh_medico")
        self.assertTrue(medico.permissoes.filter(codename="rh.dado_medico.view").exists())
        # idempotente: rodar de novo não duplica
        call_command("sync_authz", tenant="t")
        self.assertEqual(Permissao.objects.count(), len(catalog.CATALOGO))
        self.assertEqual(Perfil.objects.filter(tenant=t).count(), len(catalog.TEMPLATES_PAPEL))


class PermissoesEfetivasTests(TestCase):
    def setUp(self):
        self.t = Tenant.objects.create(nome="T", slug="t")
        self.rh = Modulo.objects.create(codigo="rh", nome="RH")
        self.erp = Modulo.objects.create(codigo="erp_financeiro", nome="ERP")
        for m in (self.rh, self.erp):
            AssinaturaTenant.objects.create(tenant=self.t, modulo=m)
        call_command("sync_authz", tenant="t")

    def _user(self, username, papeis, modulos):
        u = Usuario.objects.create(username=username, tenant=self.t)
        for cod in modulos:
            AcessoUsuarioModulo.objects.create(usuario=u, modulo=Modulo.objects.get(codigo=cod))
        u.perfis.set(Perfil.objects.filter(tenant=self.t, nome__in=papeis))
        return u

    def test_permissao_filtrada_por_modulo_assinado(self):
        # papel financeiro dá permissões de ERP; sem acesso ao módulo, não viajam.
        u = self._user("so_rh", ["financeiro"], modulos=["rh"])
        perms = set(u.permissoes_efetivas())
        self.assertNotIn("erp.conta_pagar.view", perms)  # não acessa erp_financeiro
        # já obra.* é base (sem entitlement) — mas financeiro não tem base; fica vazio de ERP
        u2 = self._user("com_erp", ["financeiro"], modulos=["erp_financeiro"])
        self.assertIn("erp.conta_pagar.view", set(u2.permissoes_efetivas()))

    def test_medico_desbloqueia_pii_medica(self):
        u = self._user("medico", ["rh_medico"], modulos=["rh"])
        self.assertIn("rh.dado_medico.view", set(u.permissoes_efetivas()))
        # e NÃO recebe dado bancário (segregação)
        self.assertNotIn("rh.dado_bancario.view", set(u.permissoes_efetivas()))

    def test_admin_recebe_catalogo_limitado_aos_modulos(self):
        u = Usuario.objects.create(username="adm", tenant=self.t, is_tenant_admin=True)
        perms = set(u.permissoes_efetivas())
        self.assertIn("rh.dado_medico.view", perms)          # tem rh
        self.assertIn("erp.conta_pagar.view", perms)          # tem erp
        self.assertIn("obra.obra.view", perms)                # base sempre
        self.assertNotIn("crm.lead.view", perms)              # tenant não assina crm

    def test_jwt_carrega_permissions(self):
        u = self._user("medico2", ["rh_medico"], modulos=["rh"])
        claims = build_claims(u)
        self.assertIn("permissions", claims)
        self.assertIn("rh.dado_medico.view", claims["permissions"])
        self.assertIn("rh_medico", claims["roles"])  # nome mantido p/ transição (fatia B)


class PersonasDinamicasTests(TestCase):
    """Admin de tenant compõe personas do catálogo, sem escalar além do plano."""

    def setUp(self):
        self.t = Tenant.objects.create(nome="T", slug="t")
        self.rh = Modulo.objects.create(codigo="rh", nome="RH")
        self.drone = Modulo.objects.create(codigo="drone", nome="Drone")
        # O tenant assina RH, mas NÃO drone.
        AssinaturaTenant.objects.create(tenant=self.t, modulo=self.rh)
        call_command("sync_authz")  # só o catálogo global (Permissao)
        self.admin = Usuario.objects.create(username="adm", tenant=self.t, is_tenant_admin=True)
        self.comum = Usuario.objects.create(username="joe", tenant=self.t)
        self.client = APIClient()

    def test_admin_le_catalogo_agrupado(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/catalogo-permissoes/")
        self.assertEqual(r.status_code, 200)
        mods = {m["modulo"]: m for m in r.data["modulos"]}
        self.assertTrue(mods["rh"]["atribuivel"])       # assinado
        self.assertFalse(mods["drone"]["atribuivel"])   # não assinado
        self.assertTrue(mods["base"]["atribuivel"])     # base sempre
        self.assertIn("rh_medico", r.data["templates"])

    def test_usuario_comum_nao_le_catalogo(self):
        self.client.force_authenticate(self.comum)
        self.assertEqual(self.client.get("/catalogo-permissoes/").status_code, 403)
        self.assertEqual(self.client.get("/permissoes/").status_code, 403)

    def test_admin_cria_persona_dentro_do_plano(self):
        self.client.force_authenticate(self.admin)
        rh_view = Permissao.objects.get(codename="rh.funcionario.view")
        obra_view = Permissao.objects.get(codename="obra.obra.view")  # base
        r = self.client.post("/perfis/", {
            "nome": "recepcao", "descricao": "",
            "permissoes": [rh_view.id, obra_view.id],
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(Perfil.objects.filter(tenant=self.t, nome="recepcao").exists())

    def test_admin_nao_escala_para_modulo_nao_assinado(self):
        self.client.force_authenticate(self.admin)
        drone_perm = Permissao.objects.get(codename="drone.projeto.view")
        r = self.client.post("/perfis/", {
            "nome": "espiao", "permissoes": [drone_perm.id],
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Perfil.objects.filter(tenant=self.t, nome="espiao").exists())


class SessaoCookieTests(TestCase):
    """Ciclo de sessão (Fase 10.6/F1): access no corpo, refresh em cookie HttpOnly,
    rotação com detecção de reuso, 'lembrar de mim' e logout."""

    def setUp(self):
        self.t = Tenant.objects.create(nome="T", slug="t")
        self.user = Usuario.objects.create(username="alice", tenant=self.t)
        self.user.set_password("segredo123")
        self.user.save()
        self.client = APIClient()

    def _login(self, remember=False):
        return self.client.post(
            "/auth/login/",
            {"username": "alice", "password": "segredo123", "remember": remember},
            format="json",
        )

    def test_login_da_access_e_cookie_sem_refresh_no_corpo(self):
        r = self._login()
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        self.assertNotIn("refresh", r.data)  # refresh NUNCA no corpo
        cookie = r.cookies.get(settings.REFRESH_COOKIE_NAME)
        self.assertIsNotNone(cookie)
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["path"], "/auth/")

    def test_refresh_pelo_cookie_gira_e_devolve_novo_access(self):
        self._login()
        r = self.client.post("/auth/refresh/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        self.assertIn(settings.REFRESH_COOKIE_NAME, r.cookies)  # cookie rotacionado

    def test_reuso_de_refresh_antigo_derruba_sessao(self):
        self._login()
        antigo = self.client.cookies[settings.REFRESH_COOKIE_NAME].value
        self.client.post("/auth/refresh/")  # rotaciona → antigo vai p/ blacklist
        self.client.cookies[settings.REFRESH_COOKIE_NAME] = antigo  # reapresenta o velho
        r = self.client.post("/auth/refresh/")
        self.assertEqual(r.status_code, 401)

    def test_sem_lembrar_e_cookie_de_sessao(self):
        # Sem "manter conectado" → cookie de sessão (sem Max-Age) → morre ao
        # fechar o navegador/desligar o PC.
        c = self._login(remember=False).cookies[settings.REFRESH_COOKIE_NAME]
        self.assertEqual(c["max-age"], "")

    def test_com_lembrar_e_cookie_persistente(self):
        # Com "manter conectado" → cookie persistente ~30d (sobrevive ao reboot).
        c = self._login(remember=True).cookies[settings.REFRESH_COOKIE_NAME]
        self.assertGreater(int(c["max-age"]), 20 * 24 * 3600)

    def test_refresh_sem_cookie_401(self):
        self.assertEqual(self.client.post("/auth/refresh/").status_code, 401)

    def test_logout_limpa_cookie_e_invalida_sessao(self):
        self._login()
        self.assertEqual(self.client.post("/auth/logout/").status_code, 200)
        self.assertEqual(self.client.post("/auth/refresh/").status_code, 401)


class TrocaSenhaTests(TestCase):
    """Trocar a senha encerra as OUTRAS sessões, mantendo o dispositivo atual."""

    def setUp(self):
        self.t = Tenant.objects.create(nome="T", slug="t")
        self.user = Usuario.objects.create(username="bob", tenant=self.t)
        self.user.set_password("senha-antiga-1")
        self.user.save()

    def _login(self, client):
        return client.post(
            "/auth/login/",
            {"username": "bob", "password": "senha-antiga-1", "remember": True},
            format="json",
        )

    def test_troca_encerra_outras_sessoes_mantendo_a_atual(self):
        A, B = APIClient(), APIClient()
        self._login(A); self._login(B)
        self.assertEqual(A.post("/auth/refresh/").status_code, 200)
        self.assertEqual(B.post("/auth/refresh/").status_code, 200)

        A.force_authenticate(user=self.user)  # no app real o Bearer vem do attachAuth
        r = A.post("/auth/senha/", {"senha_atual": "senha-antiga-1", "nova_senha": "senha-nova-99"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)

        self.assertEqual(B.post("/auth/refresh/").status_code, 401)  # outra sessão caiu
        self.assertEqual(A.post("/auth/refresh/").status_code, 200)  # a atual continua

    def test_senha_atual_errada_400(self):
        A = APIClient(); self._login(A); A.force_authenticate(user=self.user)
        r = A.post("/auth/senha/", {"senha_atual": "errada", "nova_senha": "qualquer-outra-1"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_nova_senha_curta_400(self):
        A = APIClient(); self._login(A); A.force_authenticate(user=self.user)
        r = A.post("/auth/senha/", {"senha_atual": "senha-antiga-1", "nova_senha": "curta"}, format="json")
        self.assertEqual(r.status_code, 400)


class AdminRedefinirSenhaTests(TestCase):
    """Admin redefine a senha de um usuário EXIGINDO a senha atual dele; um PATCH
    comum não troca senha (só a ação dedicada)."""

    def setUp(self):
        self.t = Tenant.objects.create(nome="T", slug="t")
        self.admin = Usuario.objects.create(username="adm", tenant=self.t, is_tenant_admin=True)
        self.alvo = Usuario.objects.create(username="alvo", tenant=self.t)
        self.alvo.set_password("antiga-123")
        self.alvo.save()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _url(self):
        return f"/usuarios/{self.alvo.id}/redefinir-senha/"

    def test_reset_com_senha_atual_correta(self):
        r = self.client.post(self._url(), {"senha_atual": "antiga-123", "nova_senha": "nova-1234"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.alvo.refresh_from_db()
        self.assertTrue(self.alvo.check_password("nova-1234"))

    def test_reset_com_senha_atual_errada_400(self):
        r = self.client.post(self._url(), {"senha_atual": "errada", "nova_senha": "nova-1234"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.alvo.refresh_from_db()
        self.assertTrue(self.alvo.check_password("antiga-123"))  # inalterada

    def test_patch_comum_nao_troca_senha(self):
        self.client.patch(f"/usuarios/{self.alvo.id}/", {"password": "hackeado-9"}, format="json")
        self.alvo.refresh_from_db()
        self.assertTrue(self.alvo.check_password("antiga-123"))
        self.assertFalse(self.alvo.check_password("hackeado-9"))
