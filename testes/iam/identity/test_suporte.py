"""Fase 6 da remodelagem — o suporte da plataforma só entra com consentimento (§10.7).

Até aqui o supervisor da plataforma via e mudava as pessoas, os papéis e os
acessos de toda empresa. Agora, fora da própria, só enquanto o admin dela deixa
— e com data de fim. As duas exceções que evitam uma empresa trancada para
sempre (o primeiro admin e o resgate do segundo fator do admin) seguem abertas.
"""
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from identity import suporte
from identity.models import (
    AcessoUsuarioModulo, ConsentimentoSuporte, EventoSeguranca, Modulo, Perfil, Tenant, Usuario,
)
from payment.planos import SUPORTE_CONSENTIMENTO_MAX_DIAS

from .bff_de_teste import confirmado_agora


class BaseSuporte(TestCase):
    def setUp(self):
        call_command("sync_authz")
        self.plataforma = Tenant.objects.create(nome="Plataforma", slug="plat")
        self.cliente = Tenant.objects.create(nome="Construtora X", slug="x")
        self.dono = Usuario.objects.create(
            username="dono", email="dono@p.com", tenant=self.plataforma, is_superuser=True,
        )
        self.admin_x = Usuario.objects.create(
            username="adm-x", email="adm@x.com", tenant=self.cliente, is_tenant_admin=True,
        )
        self.ana_x = Usuario.objects.create(username="ana-x", email="ana@x.com", tenant=self.cliente)
        self.papel_x = Perfil.objects.create(tenant=self.cliente, nome="fiscal")
        rh = Modulo.objects.create(codigo="rh", nome="RH")
        AcessoUsuarioModulo.objects.create(usuario=self.ana_x, modulo=rh)
        self.sup = APIClient()
        confirmado_agora(self.sup, self.dono)
        self.adm = APIClient()
        confirmado_agora(self.adm, self.admin_x)

    def _usernames(self):
        r = self.sup.get("/usuarios/")
        dados = r.data.get("results", r.data) if isinstance(r.data, dict) else r.data
        return {u["username"] for u in dados}

    def _liberar(self, dias=1):
        return self.adm.post("/suporte/", {"dias": dias, "motivo": "chamado 123"}, format="json")


class SemConsentimentoTests(BaseSuporte):
    def test_o_supervisor_so_ve_a_propria_empresa(self):
        self.assertEqual(self._usernames(), {"dono"})

    def test_nem_papeis_nem_acessos_de_outra_empresa(self):
        r = self.sup.get("/perfis/")
        dados = r.data.get("results", r.data) if isinstance(r.data, dict) else r.data
        self.assertNotIn(self.papel_x.id, {p["id"] for p in dados})
        r = self.sup.get("/acessos-modulo/")
        dados = r.data.get("results", r.data) if isinstance(r.data, dict) else r.data
        self.assertEqual(len(dados), 0)

    def test_nao_mexe_em_quem_nao_ve(self):
        r = self.sup.patch(f"/usuarios/{self.ana_x.id}/", {"first_name": "Outra"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_nao_cria_gente_na_empresa_alheia(self):
        r = self.sup.post("/usuarios/", {
            "username": "intruso", "email": "i@x.com", "tenant": str(self.cliente.id), "password": "senha-forte-1",
        }, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Usuario.objects.filter(username="intruso").exists())

    def test_cria_o_primeiro_admin_de_empresa_sem_nenhum(self):
        nova = Tenant.objects.create(nome="Nova", slug="nova")
        r = self.sup.post("/usuarios/", {
            "username": "adm-nova", "email": "a@nova.com", "tenant": str(nova.id),
            "is_tenant_admin": True, "password": "senha-forte-1",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)

    def test_o_resgate_do_segundo_fator_do_admin_continua(self):
        """Sem ele, o admin que perdeu o celular trancaria a empresa: não há
        quem consinta. Continua registrado e avisado."""
        r = self.sup.post(f"/usuarios/{self.admin_x.id}/redefinir-segundo-fator/", {}, format="json")
        self.assertNotEqual(r.status_code, 404)  # 400: ele não tem fator — mas o supervisor chegou
        r = self.sup.post(f"/usuarios/{self.ana_x.id}/redefinir-segundo-fator/", {}, format="json")
        self.assertEqual(r.status_code, 404)  # quem não é admin continua fora


class ComConsentimentoTests(BaseSuporte):
    def test_o_admin_libera_e_o_supervisor_passa_a_ver(self):
        r = self._liberar(dias=2)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["vigente"])
        self.assertEqual(self._usernames(), {"dono", "adm-x", "ana-x"})
        self.assertTrue(EventoSeguranca.objects.filter(tipo=EventoSeguranca.Tipo.SUPORTE_CONSENTIDO).exists())

    def test_o_supervisor_ve_quais_empresas_liberaram(self):
        self._liberar()
        empresas = self.sup.get("/suporte/").data["empresas"]
        self.assertEqual([e["nome"] for e in empresas], ["Construtora X"])

    def test_vencido_o_prazo_o_acesso_acaba_sozinho(self):
        self._liberar()
        ConsentimentoSuporte.objects.update(ate=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self._usernames(), {"dono"})

    def test_o_admin_encerra_quando_quiser(self):
        self._liberar()
        r = self.adm.delete("/suporte/")
        self.assertEqual(r.data["encerrados"], 1)
        self.assertEqual(self._usernames(), {"dono"})
        self.assertTrue(EventoSeguranca.objects.filter(tipo=EventoSeguranca.Tipo.SUPORTE_ENCERRADO).exists())

    def test_prazo_acima_do_teto_do_dono_e_recusado(self):
        self.assertEqual(self._liberar(dias=SUPORTE_CONSENTIMENTO_MAX_DIAS + 1).status_code, 400)
        self.assertIsNone(suporte.vigente(self.cliente.id))

    def test_liberar_de_novo_substitui(self):
        self._liberar(dias=1)
        self._liberar(dias=3)
        self.assertEqual(
            ConsentimentoSuporte.objects.filter(tenant=self.cliente, encerrado_em__isnull=True).count(), 1,
        )

    def test_o_supervisor_nao_libera_para_si(self):
        r = self.sup.post("/suporte/", {"dias": 1}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_liberar_e_ato_grave(self):
        velho = APIClient()
        velho.force_authenticate(self.admin_x, token={"auth_time": 0})
        r = velho.post("/suporte/", {"dias": 1}, format="json")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.data["codigo"], "confirmacao_necessaria")

    def test_encerrar_nao_pede_confirmacao(self):
        self._liberar()
        velho = APIClient()
        velho.force_authenticate(self.admin_x, token={"auth_time": 0})
        self.assertEqual(velho.delete("/suporte/").status_code, 200)

    def test_quem_nao_e_admin_nao_libera(self):
        comum = APIClient()
        confirmado_agora(comum, self.ana_x)
        self.assertEqual(comum.post("/suporte/", {"dias": 1}, format="json").status_code, 403)
