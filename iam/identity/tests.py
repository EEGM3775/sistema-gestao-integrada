"""Testes do RBAC — catálogo + templates + permissões no JWT (Fase 9, fatia A)."""
from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from identity import catalog
from identity.models import (
    Tenant, Modulo, Usuario, AssinaturaTenant, AcessoUsuarioModulo, Perfil, Permissao,
)
from identity.models import EventoSeguranca, TokenRecuperacaoSenha
from identity.recuperacao import hash_token
from identity.tokens import build_claims, issue_refresh


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
        u = Usuario.objects.create(username=username, email=f"{username}@teste.com", tenant=self.t)
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
        u = Usuario.objects.create(username="adm", email="adm@teste.com", tenant=self.t, is_tenant_admin=True)
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
        self.admin = Usuario.objects.create(username="adm", email="adm@teste.com", tenant=self.t, is_tenant_admin=True)
        self.comum = Usuario.objects.create(username="joe", email="joe@teste.com", tenant=self.t)
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
        self.user = Usuario.objects.create(username="alice", email="alice@teste.com", tenant=self.t)
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
        # Com "manter conectado" → cookie PERSISTENTE (sobrevive ao reboot), com
        # Max-Age casando a janela deslizante. Derivado do settings de propósito: a
        # versão antiga cravava "> 20 dias", número amarrado aos 30d de então, e
        # quebrou ao ajustarmos a janela — travava o valor, não o comportamento.
        c = self._login(remember=True).cookies[settings.REFRESH_COOKIE_NAME]
        janela = int(settings.SESSION_REMEMBER.total_seconds())
        self.assertGreater(int(c["max-age"]), janela * 0.9)
        self.assertLessEqual(int(c["max-age"]), janela)

    @override_settings(REFRESH_COOKIE_SECURE=True)
    def test_cookie_de_refresh_leva_secure_quando_ligado(self):
        # O refresh é setado à mão (cookies.py), fora do endurecimento que o bloco de
        # produção aplica aos cookies do Django — por isso o flag precisa de teste
        # próprio: o staging chegou a emitir a sessão SEM `Secure` sob HTTPS.
        c = self._login().cookies[settings.REFRESH_COOKIE_NAME]
        self.assertTrue(c["secure"])

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
        self.user = Usuario.objects.create(username="bob", email="bob@teste.com", tenant=self.t)
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
        self.admin = Usuario.objects.create(username="adm", email="adm@teste.com", tenant=self.t, is_tenant_admin=True)
        self.alvo = Usuario.objects.create(username="alvo", email="alvo@teste.com", tenant=self.t)
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


@override_settings(SERVICE_TOKEN_SECRET="segredo-de-servico-teste")
class ServiceTokenTests(TestCase):
    """Token serviço→serviço (Fase 10.8): só com o segredo compartilhado; carrega
    tenant + módulo pedidos e nenhuma identidade de usuário (sem user_id)."""

    def setUp(self):
        self.client = APIClient()

    def _post(self, secret, body):
        headers = {"HTTP_X_SERVICE_SECRET": secret} if secret is not None else {}
        return self.client.post("/auth/service-token/", body, format="json", **headers)

    def test_segredo_correto_emite_token_escopado(self):
        r = self._post("segredo-de-servico-teste", {"tenant_id": "t-123", "audience": "drone"})
        self.assertEqual(r.status_code, 200)
        access = AccessToken(r.data["access"])  # valida assinatura + exp
        self.assertEqual(access["tenant_id"], "t-123")
        self.assertEqual(access["modules"], ["drone"])
        self.assertEqual(access["sub"], "svc-backend")
        self.assertTrue(access["svc"])
        self.assertNotIn("user_id", access)  # não representa um usuário

    def test_segredo_errado_401(self):
        r = self._post("errado", {"tenant_id": "t-123"})
        self.assertEqual(r.status_code, 401)

    def test_sem_segredo_401(self):
        r = self._post(None, {"tenant_id": "t-123"})
        self.assertEqual(r.status_code, 401)

    def test_sem_tenant_id_400(self):
        r = self._post("segredo-de-servico-teste", {"audience": "drone"})
        self.assertEqual(r.status_code, 400)


class SessaoDuracaoTests(TestCase):
    """Duração da sessão SEM 'manter conectado': janela DESLIZANTE de inatividade
    (`SESSION_IDLE`) limitada por um teto absoluto (`SESSION_IDLE_CAP`).

    Antes a janela e o teto eram o MESMO valor, então o `exp` ficava preso a
    `sst + janela`: renovar não estendia nada e quem estava trabalhando caía no
    meio do expediente. Nada travava essa semântica — daí estes testes.
    """

    def setUp(self):
        self.t = Tenant.objects.create(nome="T", slug="t")
        self.user = Usuario.objects.create(username="alice", email="alice@teste.com", tenant=self.t)
        self.user.set_password("segredo123")
        self.user.save()
        self.client = APIClient()

    def _login(self):
        return self.client.post(
            "/auth/login/",
            {"username": "alice", "password": "segredo123", "remember": False},
            format="json",
        )

    def _rotacionar_com_sessao_iniciada_ha(self, segundos):
        """Rotaciona apresentando um refresh cujo início de sessão (`sst`) é antigo."""
        self._login()
        sst = int(timezone.now().timestamp()) - segundos
        token = issue_refresh(self.user, remember=False, sst=sst)
        self.client.cookies[settings.REFRESH_COOKIE_NAME] = str(token)
        return self.client.post("/auth/refresh/")

    def test_login_expira_na_janela_de_inatividade(self):
        # O front agenda o aviso por este instante (não lê o cookie HttpOnly).
        r = self._login()
        esperado = int(timezone.now().timestamp()) + int(settings.SESSION_IDLE.total_seconds())
        self.assertAlmostEqual(r.data["session_expires_at"], esperado, delta=10)
        self.assertEqual(r.data["session_warn_seconds"], settings.SESSION_WARN_SECONDS)

    def test_rotacao_desliza_alem_do_inicio_da_sessao(self):
        # Sessão aberta há 5h (dentro do teto): renovar dá mais uma janela cheia a
        # partir de AGORA. É isto que mantém logado quem está trabalhando.
        r = self._rotacionar_com_sessao_iniciada_ha(5 * 3600)
        self.assertEqual(r.status_code, 200)
        esperado = int(timezone.now().timestamp()) + int(settings.SESSION_IDLE.total_seconds())
        self.assertAlmostEqual(r.data["session_expires_at"], esperado, delta=10)

    def test_teto_absoluto_corta_mesmo_ativo(self):
        # Passou do teto → nem a atividade renova: tem de relogar. Há DUAS barreiras
        # para o mesmo teto: o `exp` do próprio token (aparado na emissão, então um
        # `sst` além do teto já nasce vencido) e a checagem explícita do `sst` na
        # view. Na prática a primeira dispara antes; o invariante é a recusa.
        r = self._rotacionar_com_sessao_iniciada_ha(
            int(settings.SESSION_IDLE_CAP.total_seconds()) + 60
        )
        self.assertEqual(r.status_code, 401)

    def test_com_manter_conectado_usa_a_janela_longa(self):
        # "Manter conectado" é equipamento pessoal: janela longa, teto próprio.
        r = self.client.post(
            "/auth/login/",
            {"username": "alice", "password": "segredo123", "remember": True},
            format="json",
        )
        esperado = int(timezone.now().timestamp()) + int(settings.SESSION_REMEMBER.total_seconds())
        self.assertAlmostEqual(r.data["session_expires_at"], esperado, delta=10)

    def test_teto_do_manter_conectado_corta(self):
        # Mesmo "lembrado", passou do teto absoluto → relogin. É o que garante que
        # uma sessão roubada morre sozinha, sem ninguém precisar notar.
        self._login()
        sst = int(timezone.now().timestamp()) - int(settings.SESSION_ABS_CAP.total_seconds()) - 60
        token = issue_refresh(self.user, remember=True, sst=sst)
        self.client.cookies[settings.REFRESH_COOKIE_NAME] = str(token)
        self.assertEqual(self.client.post("/auth/refresh/").status_code, 401)

    def test_janela_nunca_ultrapassa_o_teto(self):
        # Faltando 10 min para o teto, a janela de inatividade é aparada por ele.
        faltam = 600
        r = self._rotacionar_com_sessao_iniciada_ha(
            int(settings.SESSION_IDLE_CAP.total_seconds()) - faltam
        )
        self.assertEqual(r.status_code, 200)
        self.assertLessEqual(r.data["session_expires_at"], int(timezone.now().timestamp()) + faltam + 10)


# ---------------------------------------------------------------------------
# D11 — recuperação de senha, troca de e-mail e trilha de identidade
# ---------------------------------------------------------------------------
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_HOST="mailpit-de-teste",
    FRONTEND_BASE_URL="http://localhost:8090",
)
class EsqueciSenhaTests(TestCase):
    """Caminho 1 — autoatendimento. O foco é o que o endpoint NÃO revela."""

    def setUp(self):
        self.t = Tenant.objects.create(nome="T", slug="t")
        self.user = Usuario.objects.create(
            username="joao", email="joao@empresa.com", tenant=self.t
        )
        self.user.set_password("antiga-123")
        self.user.save()
        self.client = APIClient()
        mail.outbox = []

    def _pedir(self, identificador):
        return self.client.post(
            "/auth/senha/esqueci/", {"identificador": identificador}, format="json"
        )

    def _link_token(self):
        corpo = mail.outbox[-1].body
        return corpo.split("token=")[1].split()[0]

    def test_envia_link_para_o_proprio_usuario(self):
        r = self._pedir("joao")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["joao@empresa.com"])

    def test_aceita_email_como_identificador(self):
        self._pedir("joao@empresa.com")
        self.assertEqual(len(mail.outbox), 1)

    def test_usuario_inexistente_responde_igual_e_nao_envia(self):
        """Sem oráculo de enumeração: resposta idêntica à do usuário real."""
        real = self._pedir("joao")
        mail.outbox = []
        falso = self._pedir("nao-existe")
        self.assertEqual(falso.status_code, real.status_code)
        self.assertEqual(falso.data, real.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_usuario_inativo_responde_igual_e_nao_envia(self):
        self.user.is_active = False
        self.user.save()
        r = self._pedir("joao")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_token_nao_e_persistido_em_claro(self):
        """Um dump do banco não pode render tokens utilizáveis."""
        self._pedir("joao")
        claro = self._link_token()
        self.assertFalse(
            TokenRecuperacaoSenha.objects.filter(token_hash=claro).exists()
        )
        self.assertTrue(
            TokenRecuperacaoSenha.objects.filter(token_hash=hash_token(claro)).exists()
        )

    def test_nova_solicitacao_invalida_a_anterior(self):
        self._pedir("joao")
        primeiro = self._link_token()
        self._pedir("joao")
        r = self.client.post(
            "/auth/senha/redefinir/",
            {"token": primeiro, "nova_senha": "nova-senha-1"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_teto_por_hora(self):
        for _ in range(settings.PASSWORD_RESET_MAX_POR_HORA):
            self._pedir("joao")
        mail.outbox = []
        self._pedir("joao")
        self.assertEqual(len(mail.outbox), 0)  # bloqueado, mas resposta é a mesma


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_HOST="mailpit-de-teste",
)
class RedefinirComTokenTests(TestCase):
    """Consumo do token: uso único, expiração e encerramento das sessões."""

    def setUp(self):
        self.t = Tenant.objects.create(nome="T", slug="t")
        self.user = Usuario.objects.create(
            username="joao", email="joao@empresa.com", tenant=self.t
        )
        self.user.set_password("antiga-123")
        self.user.save()
        self.client = APIClient()
        mail.outbox = []
        self.client.post("/auth/senha/esqueci/", {"identificador": "joao"}, format="json")
        self.token = mail.outbox[0].body.split("token=")[1].split()[0]
        mail.outbox = []

    def _redefinir(self, token, senha="nova-senha-1"):
        return self.client.post(
            "/auth/senha/redefinir/", {"token": token, "nova_senha": senha}, format="json"
        )

    def test_redefine_sem_saber_a_senha_antiga(self):
        r = self._redefinir(self.token)
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("nova-senha-1"))

    def test_token_e_de_uso_unico(self):
        self._redefinir(self.token)
        r = self._redefinir(self.token, "outra-senha-9")
        self.assertEqual(r.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("nova-senha-1"))

    def test_token_expirado_recusado(self):
        TokenRecuperacaoSenha.objects.filter(usuario=self.user).update(
            expira_em=timezone.now() - timezone.timedelta(minutes=1)
        )
        self.assertEqual(self._redefinir(self.token).status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("antiga-123"))

    def test_token_invalido_recusado(self):
        self.assertEqual(self._redefinir("lixo-inventado").status_code, 400)

    def test_senha_curta_recusada(self):
        self.assertEqual(self._redefinir(self.token, "curta").status_code, 400)

    def test_avisa_o_dono_da_conta(self):
        self._redefinir(self.token)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["joao@empresa.com"])

    def test_registra_na_trilha(self):
        self._redefinir(self.token)
        self.assertTrue(
            EventoSeguranca.objects.filter(
                tipo=EventoSeguranca.Tipo.RESET_CONCLUIDO, alvo=self.user
            ).exists()
        )


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_HOST="mailpit-de-teste",
)
class AdminComprometidoTests(TestCase):
    """O cenário que motivou o D11: admin caído em engenharia social.

    Estes testes são a prova de que a recuperação por e-mail NÃO reabriu o
    caminho que ela deveria fechar. Sem a trava da troca de e-mail, o admin
    comprometido apontaria a conta da vítima para a própria caixa e usaria o
    fluxo público — takeover completo, sem step-up e com rastro parecendo uma
    recuperação legítima feita pelo próprio usuário.
    """

    def setUp(self):
        self.t = Tenant.objects.create(nome="T", slug="t")
        self.admin = Usuario.objects.create(
            username="adm", email="adm@empresa.com", tenant=self.t, is_tenant_admin=True
        )
        self.admin.set_password("senha-do-admin-1")
        self.admin.save()
        self.vitima = Usuario.objects.create(
            username="vitima", email="vitima@empresa.com", tenant=self.t
        )
        self.vitima.set_password("senha-da-vitima-1")
        self.vitima.save()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        mail.outbox = []

    def test_patch_nao_troca_o_email(self):
        """O elo da cadeia de takeover: PATCH banal mudando o e-mail."""
        self.client.patch(
            f"/usuarios/{self.vitima.id}/",
            {"email": "atacante@evil.com"},
            format="json",
        )
        self.vitima.refresh_from_db()
        self.assertEqual(self.vitima.email, "vitima@empresa.com")

    def test_troca_de_email_de_FUNCIONARIO_vale_na_hora(self):
        """O dono administra as contas dos funcionários por direito.

        Exigir confirmação no endereço antigo travaria o caso real que motivou o
        D11: e-mail digitado errado no cadastro, ou caixa que a pessoa não acessa
        mais — a confirmação iria para um endereço morto e ninguém corrigiria.
        """
        r = self.client.post(
            f"/usuarios/{self.vitima.id}/trocar-email/",
            {"email": "novo-correto@empresa.com"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.vitima.refresh_from_db()
        self.assertEqual(self.vitima.email, "novo-correto@empresa.com")

    def test_troca_de_funcionario_avisa_os_DOIS_enderecos(self):
        """Compensação da troca direta: se o endereço antigo ainda estiver vivo
        e a mudança não fizer sentido, a pessoa descobre."""
        self.client.post(
            f"/usuarios/{self.vitima.id}/trocar-email/",
            {"email": "novo-correto@empresa.com"},
            format="json",
        )
        destinos = {c for m in mail.outbox for c in m.to}
        self.assertIn("vitima@empresa.com", destinos)        # antigo
        self.assertIn("novo-correto@empresa.com", destinos)  # novo

    def test_troca_de_funcionario_NAO_arma_cooldown(self):
        """Corrigido o e-mail, a pessoa precisa conseguir recuperar na hora."""
        self.client.post(
            f"/usuarios/{self.vitima.id}/trocar-email/",
            {"email": "novo-correto@empresa.com"},
            format="json",
        )
        mail.outbox = []
        APIClient().post("/auth/senha/esqueci/", {"identificador": "vitima"}, format="json")
        com_link = [m for m in mail.outbox if "token=" in m.body]
        self.assertEqual(len(com_link), 1)
        self.assertEqual(com_link[0].to, ["novo-correto@empresa.com"])

    def test_troca_de_email_de_ADMIN_exige_confirmacao_no_antigo(self):
        """A conta do dono dá acesso à empresa inteira: não muda em silêncio.

        Quem sequestrar a sessão do admin não pode redirecionar o e-mail dele e,
        com isso, herdar a recuperação de senha de tudo.
        """
        r = self.client.post(
            f"/usuarios/{self.admin.id}/trocar-email/",
            {"email": "atacante@evil.com"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        # NÃO mudou...
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.email, "adm@empresa.com")
        # ...e a confirmação foi para a caixa ANTIGA, que o atacante não controla.
        self.assertEqual(mail.outbox[-1].to, ["adm@empresa.com"])

    def test_sessao_de_admin_sequestrada_nao_redireciona_a_conta_dele(self):
        """Cadeia de takeover sobre a conta do DONO: trocar e-mail + recuperar."""
        self.client.post(
            f"/usuarios/{self.admin.id}/trocar-email/",
            {"email": "atacante@evil.com"},
            format="json",
        )
        mail.outbox = []
        APIClient().post("/auth/senha/esqueci/", {"identificador": "adm"}, format="json")
        com_link = [m for m in mail.outbox if "token=" in m.body]
        self.assertEqual(len(com_link), 1)
        self.assertEqual(com_link[0].to, ["adm@empresa.com"])
        self.assertNotIn("atacante@evil.com", [c for m in mail.outbox for c in m.to])

    def test_cooldown_bloqueia_reset_logo_apos_troca_confirmada(self):
        """Mesmo com a troca CONFIRMADA, há carência antes de emitir token."""
        self.vitima.email = "novo@empresa.com"
        self.vitima.email_alterado_em = timezone.now()
        self.vitima.save()
        mail.outbox = []
        anon = APIClient()
        r = anon.post("/auth/senha/esqueci/", {"identificador": "vitima"}, format="json")
        self.assertEqual(r.status_code, 200)  # resposta genérica de sempre
        self.assertEqual(len(mail.outbox), 0)  # mas nenhum token emitido

    def test_admin_recebe_aviso_mas_NUNCA_o_link(self):
        """A regra central do desenho: supervisão sem poder.

        O admin fica sabendo do pedido — pode reagir se não fizer sentido — mas
        não recebe o link. Se recebesse, este endpoint (público, sem autenticação)
        deixaria qualquer anônimo fazer cair um token de takeover na caixa dele.
        """
        anon = APIClient()
        anon.post("/auth/senha/esqueci/", {"identificador": "vitima"}, format="json")

        por_caixa = {m.to[0]: m for m in mail.outbox}
        self.assertIn("vitima@empresa.com", por_caixa)
        self.assertIn("adm@empresa.com", por_caixa)
        # O link (token=) está SÓ no e-mail do usuário.
        self.assertIn("token=", por_caixa["vitima@empresa.com"].body)
        self.assertNotIn("token=", por_caixa["adm@empresa.com"].body)

    def test_admin_nao_consegue_reset_sem_token(self):
        """Não sobrou ação de reset iniciada por admin (a assistida foi removida)."""
        r = self.client.post(
            f"/usuarios/{self.vitima.id}/recuperacao-assistida/",
            {"senha_admin": "senha-do-admin-1"},
            format="json",
        )
        self.assertEqual(r.status_code, 404)

    def test_promocao_a_admin_e_auditada_e_avisada(self):
        self.client.patch(
            f"/usuarios/{self.vitima.id}/", {"is_tenant_admin": True}, format="json"
        )
        self.assertTrue(
            EventoSeguranca.objects.filter(
                tipo=EventoSeguranca.Tipo.PRIVILEGIO_ALTERADO, alvo=self.vitima
            ).exists()
        )
        self.assertIn("vitima@empresa.com", [c for m in mail.outbox for c in m.to])


class EventoSegurancaImutavelTests(TestCase):
    """A trilha existe para atribuir ações a um admin possivelmente comprometido.
    Se ele puder editá-la, não prova nada."""

    def setUp(self):
        self.t = Tenant.objects.create(nome="T", slug="t")
        self.u = Usuario.objects.create(username="u", email="u@teste.com", tenant=self.t)
        self.ev = EventoSeguranca.objects.create(
            tipo=EventoSeguranca.Tipo.RESET_SOLICITADO, alvo=self.u, alvo_username="u"
        )

    def test_update_bloqueado(self):
        self.ev.tipo = EventoSeguranca.Tipo.SENHA_ALTERADA
        with self.assertRaises(ValueError):
            self.ev.save()

    def test_delete_bloqueado(self):
        with self.assertRaises(ValueError):
            self.ev.delete()

    def test_exclusao_de_usuario_nao_derruba_a_trilha(self):
        """FKs congeladas (db_constraint=False): o rastro sobrevive ao usuário."""
        self.u.delete()
        ev = EventoSeguranca.objects.get(pk=self.ev.pk)
        self.assertEqual(ev.alvo_username, "u")


class EmailObrigatorioUnicoTests(TestCase):
    """E-mail deixou de ser contato e virou infraestrutura de recuperação.

    Conta sem e-mail = conta sem caminho de volta (o travamento que o D11 existe
    para eliminar). E-mail repetido = recuperação ambígua.
    """

    def setUp(self):
        # Plano com folga de seats: estes testes são sobre a REGRA DE E-MAIL, e
        # no `free` (1 seat, já ocupado pelo admin) a criação pararia antes, no
        # 402 da quota do D24 — passando a medir outra coisa.
        self.t = Tenant.objects.create(nome="T", slug="t", plano="profissional")
        self.admin = Usuario.objects.create(
            username="adm", email="adm@empresa.com", tenant=self.t, is_tenant_admin=True
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_criacao_sem_email_recusada(self):
        r = self.client.post(
            "/usuarios/", {"username": "novo", "password": "senha-forte-1"}, format="json"
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", r.data)

    def test_criacao_com_email_ok(self):
        r = self.client.post(
            "/usuarios/",
            {"username": "novo", "email": "novo@empresa.com", "password": "senha-forte-1"},
            format="json",
        )
        self.assertEqual(r.status_code, 201)

    def test_email_duplicado_recusado(self):
        r = self.client.post(
            "/usuarios/",
            {"username": "outro", "email": "adm@empresa.com", "password": "senha-forte-1"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_unicidade_vale_entre_tenants(self):
        """Único GLOBAL (decisão 18/07): a mesma pessoa não tem conta em duas empresas."""
        outro_tenant = Tenant.objects.create(nome="Outra", slug="outra")
        with self.assertRaises(Exception):
            Usuario.objects.create(
                username="clone", email="adm@empresa.com", tenant=outro_tenant
            )
