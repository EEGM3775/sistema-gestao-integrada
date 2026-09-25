"""D194 — o token leva a lista EXATA de permissões, e tem de caber na borda.

O access leva `permissions` crua; o catálogo cresceu, o token do admin passou
dos 8.190 B da linha `Authorization` e **toda** chamada autenticada da
plataforma caiu. O contorno é a janela de 32 KB na borda (nginx + gunicorn); a
cura é o token sem permissão (acesso-e-permissoes.md §10, fase 4). Até lá valem
duas regras, e é isto que se cobra aqui: **nunca curinga** — o curinga
concederia o que ninguém concedeu — e o estouro tem de aparecer na esteira, não
no navegador do dono.
"""
import base64
import json

from django.core.management import call_command
from django.test import TestCase

from identity import catalog
from identity.models import AcessoUsuarioModulo, AssinaturaTenant, Modulo, Perfil, Tenant, Usuario
from identity.tokens import access_with_claims, build_claims, issue_refresh

# A janela de uma linha de cabeçalho que a borda tem hoje: `large_client_header_buffers
# 8 32k` em `infra/gateway/nginx.unified.conf` e `--limit-request-field_size 32768` no
# `erp` e na `iam` (`deploy/compose/base.yml`). Janela de protocolo de terceiro (§5.6 do
# `planos.py`), não teto do produto — e se a borda mudar, muda aqui junto.
JANELA_DA_BORDA = 32768
PREFIXO_DA_LINHA = "Authorization: Bearer "


def _carga(token) -> dict:
    parte = str(token).split(".")[1]
    return json.loads(base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4)))


class TokenLevaAListaExataTests(TestCase):
    def setUp(self):
        self.t = Tenant.objects.create(nome="T", slug="t")
        for cod in sorted({p.modulo for p in catalog.CATALOGO} - {"base", "plataforma"}):
            AssinaturaTenant.objects.create(
                tenant=self.t, modulo=Modulo.objects.create(codigo=cod, nome=cod)
            )
        call_command("sync_authz", tenant="t")
        self.admin = Usuario.objects.create(
            username="adm", email="adm@teste.com", tenant=self.t, is_tenant_admin=True
        )

    def test_o_access_leva_a_lista_exata(self):
        access = access_with_claims(issue_refresh(self.admin, remember=False), self.admin)
        self.assertEqual(_carga(access)["permissions"], self.admin.permissoes_efetivas())

    def test_nenhum_curinga_chega_ao_token(self):
        """A regra que o D194 quase quebrou: o token nunca concede por prefixo."""
        access = access_with_claims(issue_refresh(self.admin, remember=False), self.admin)
        self.assertFalse(any("*" in c for c in _carga(access)["permissions"]))

    def test_me_e_token_dizem_a_mesma_lista(self):
        access = access_with_claims(issue_refresh(self.admin, remember=False), self.admin)
        self.assertEqual(build_claims(self.admin)["permissions"], _carga(access)["permissions"])


class GuardaDoTamanhoDoTokenTests(TestCase):
    """A guarda que o D194 pedia: nenhuma persona pode ter um token que não caiba
    na janela da borda. Falhou aqui? Não suba o buffer da borda de novo, e não
    troque a lista por curinga — é a hora do token sem permissão
    (acesso-e-permissoes.md §10.12, fase 4)."""

    def setUp(self):
        self.t = Tenant.objects.create(nome="Construtora de Nome Comprido Ltda", slug="t-guarda")
        self.modulos = []
        for cod in sorted({p.modulo for p in catalog.CATALOGO} - {"base", "plataforma"}):
            m = Modulo.objects.create(codigo=cod, nome=cod)
            AssinaturaTenant.objects.create(tenant=self.t, modulo=m)
            self.modulos.append(m)
        call_command("sync_authz", tenant="t-guarda")

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
            linha, JANELA_DA_BORDA,
            f"{rotulo}: a linha Authorization tem {linha} B — não cabe na janela da borda "
            f"({JANELA_DA_BORDA} B). É o D194 voltando.",
        )

    def test_admin_do_tenant(self):
        self._cabe(self._usuario("admin", is_tenant_admin=True), "admin do tenant")

    def test_supervisor_da_plataforma(self):
        self._cabe(self._usuario("dono", is_superuser=True), "supervisor da plataforma")

    def test_cada_persona_de_fabrica(self):
        for nome in catalog.TEMPLATES_PAPEL:
            with self.subTest(persona=nome):
                u = self._usuario(f"p-{nome}")
                u.perfis.set(Perfil.objects.filter(tenant=self.t, nome=nome))
                self._cabe(u, f"persona {nome}")

    def test_quem_acumula_todas_as_personas(self):
        u = self._usuario("acumula")
        u.perfis.set(Perfil.objects.filter(tenant=self.t))
        self._cabe(u, "todas as personas somadas")
