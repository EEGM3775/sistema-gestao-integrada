"""D194 — o token prova quem é, não o que pode (fase 4 da remodelagem).

O access levava a lista de permissões; o catálogo cresceu, o token do admin
passou dos 8.190 B da linha `Authorization` e **toda** chamada autenticada da
plataforma caiu — no nginx, no gunicorn e no Tomcat do drone. A cura é a fase 4
(acesso-e-permissoes.md §10.6 e §10.12): o token leva identidade e sessão, e o
"pode?" é do PDP. É isto que se cobra aqui:

- nenhuma lista de acesso, papel, flag de admin, plano ou e-mail no token;
- tamanho **constante** e pequeno para qualquer persona, com o catálogo inteiro
  — o que fecha o D194 de vez, e não só até a próxima leva de permissões;
- a volta atrás (`AUTORIZACAO_TOKEN_COM_LISTAS`) reemite as listas, exatas e sem
  curinga — o curinga concederia o que ninguém concedeu;
- o `/auth/me/` segue dando à tela a lista exata, lida das tabelas.
"""
import base64
import json

from django.core.management import call_command
from django.test import TestCase, override_settings

from identity import catalog
from identity.models import AcessoUsuarioModulo, AssinaturaTenant, Modulo, Perfil, Tenant, Usuario
from identity.tokens import access_with_claims, claims_de_acesso, issue_refresh

#: O teto do token enxuto. A §10.6 fala em "perto de 600 bytes"; 1 KB dá folga
#: para nomes longos e continua ~8× abaixo da linha padrão de 8 KB de toda borda.
TETO_DO_TOKEN_ENXUTO = 1024
PREFIXO_DA_LINHA = "Authorization: Bearer "

#: O que saiu do token na fase 4 (§10.6, "Sai do token").
CLAIMS_QUE_SAIRAM = {
    "permissions", "roles", "modules", "is_tenant_admin", "is_platform_admin",
    "email", "tenant_slug", "plano", "rate_hora", "quotas",
}


def _carga(token) -> dict:
    parte = str(token).split(".")[1]
    return json.loads(base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4)))


def _tenant_com_tudo(slug):
    t = Tenant.objects.create(nome="Construtora de Nome Comprido Ltda", slug=slug)
    modulos = []
    for cod in sorted({p.modulo for p in catalog.CATALOGO} - {"base", "plataforma"}):
        m = Modulo.objects.create(codigo=cod, nome=cod)
        AssinaturaTenant.objects.create(tenant=t, modulo=m)
        modulos.append(m)
    call_command("sync_authz", tenant=slug)
    return t, modulos


class TokenEnxutoTests(TestCase):
    def setUp(self):
        self.t, _ = _tenant_com_tudo("t")
        self.admin = Usuario.objects.create(
            username="adm", email="adm@teste.com", tenant=self.t, is_tenant_admin=True
        )

    def _access(self, u):
        return access_with_claims(issue_refresh(u, remember=False), u)

    def test_o_access_nao_leva_lista_nem_papel_nem_plano(self):
        carga = _carga(self._access(self.admin))
        self.assertEqual(sorted(CLAIMS_QUE_SAIRAM & set(carga)), [])

    def test_o_access_leva_quem_e_e_qual_sessao(self):
        carga = _carga(self._access(self.admin))
        self.assertEqual(carga["sub"], "adm")
        self.assertEqual(carga["tenant_id"], str(self.t.id))
        self.assertEqual(carga["user_id"], str(self.admin.id))
        for claim in ("sid", "amr", "auth_time", "sst", "aud", "iss", "jti", "exp", "iat"):
            self.assertIn(claim, carga)

    def test_cada_login_abre_uma_sessao_e_a_rotacao_a_preserva(self):
        primeiro = issue_refresh(self.admin, remember=False)
        segundo = issue_refresh(self.admin, remember=False)
        self.assertNotEqual(primeiro["sid"], segundo["sid"])
        rotacao = issue_refresh(self.admin, remember=False, sid=primeiro["sid"],
                                auth_time=primeiro["auth_time"])
        self.assertEqual(rotacao["sid"], primeiro["sid"])
        self.assertEqual(rotacao["auth_time"], primeiro["auth_time"])

    def test_o_me_da_a_lista_exata_das_tabelas(self):
        self.assertEqual(claims_de_acesso(self.admin)["permissions"], self.admin.permissoes_efetivas())
        self.assertFalse(any("*" in c for c in claims_de_acesso(self.admin)["permissions"]))

    @override_settings(AUTORIZACAO_TOKEN_COM_LISTAS=True)
    def test_a_volta_atras_reemite_a_lista_exata_sem_curinga(self):
        carga = _carga(self._access(self.admin))
        self.assertEqual(carga["permissions"], self.admin.permissoes_efetivas())
        self.assertFalse(any("*" in c for c in carga["permissions"]))
        self.assertTrue(carga["is_tenant_admin"])


class TamanhoConstanteDoTokenTests(TestCase):
    """O tamanho não depende mais do catálogo nem dos papéis: toda persona, com o
    catálogo inteiro assinado e liberado, cabe no teto do token enxuto."""

    def setUp(self):
        self.t, self.modulos = _tenant_com_tudo("t-guarda")

    def _linha(self, u) -> int:
        access = access_with_claims(issue_refresh(u, remember=False), u)
        return len(PREFIXO_DA_LINHA) + len(str(access))

    def _usuario(self, username, **extra):
        u = Usuario.objects.create(
            username=username, email=f"{username}.com.email.longo@empresa-exemplo.com.br",
            tenant=self.t, **extra,
        )
        for m in self.modulos:
            AcessoUsuarioModulo.objects.create(usuario=u, modulo=m)
        return u

    def _cabe(self, u, rotulo):
        linha = self._linha(u)
        self.assertLess(
            linha, TETO_DO_TOKEN_ENXUTO,
            f"{rotulo}: a linha Authorization tem {linha} B. O token voltou a carregar "
            "o que não é identidade — é o D194 voltando.",
        )
        return linha

    def test_admin_supervisor_e_quem_acumula_todas_as_personas(self):
        linhas = [
            self._cabe(self._usuario("admin", is_tenant_admin=True), "admin do tenant"),
            self._cabe(self._usuario("dono", is_superuser=True), "supervisor da plataforma"),
        ]
        acumula = self._usuario("acumula")
        acumula.perfis.set(Perfil.objects.filter(tenant=self.t))
        linhas.append(self._cabe(acumula, "todas as personas somadas"))
        # Constante: o que varia é só o comprimento do nome de usuário.
        self.assertLess(max(linhas) - min(linhas), 16)

    def test_cada_persona_de_fabrica(self):
        for nome in catalog.TEMPLATES_PAPEL:
            with self.subTest(persona=nome):
                u = self._usuario(f"p-{nome}")
                u.perfis.set(Perfil.objects.filter(tenant=self.t, nome=nome))
                self._cabe(u, f"persona {nome}")
