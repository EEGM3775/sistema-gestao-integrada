"""Remodelagem, fase 4 — o token prova quem é; o PDP decide; toda decisão é registrada.

O que se cobra aqui (docs/acesso-e-permissoes.md §10.5, §10.6, §10.9 e §10.12):

1. **Token sem lista, o PDP decide** — em todo módulo, qualquer que seja o modo
   da tabela; a sombra não compara o que não existe.
2. **A autenticação lê o que saiu do token pelas fichas** (plano, teto, quotas,
   slug, e-mail) e confere o `sid`.
3. **O `sid` segue a classe B**: Redis responde; Redis fora serve o visto há
   segundos e depois pergunta à IAM; ninguém responde → nega.
4. **A auditoria de decisão**: toda decisão vai ao log; negação e classe C vão à
   tabela, que é append-only — só a purga da janela do plano apaga, e nunca
   abaixo do piso legal.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from unittest import mock

from django.db import connection, transaction
from django.db.utils import InternalError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework_simplejwt.exceptions import InvalidToken

from funcoesautorizacao import chaves
from nucleo import auditoria_decisao, autorizacao, autorizacao_pdp, autorizacao_sombra, fichas, revocation
from nucleo.authentication import IamJWTAuthentication
from nucleo.models import DecisaoAcesso, ModoAutorizacao
from payment.planos import AUDITORIA_DECISAO_PISO_DIAS

from .test_autorizacao import TENANT, RedisDeMentira, pessoa


def enxuta(**extra):
    """A pessoa como a autenticação a monta a partir do token enxuto."""
    u = pessoa(**extra)
    u.iam_lista_no_token = False
    u.iam_sid = "sid-1"
    return u


@override_settings(SPICEDB_URL="http://spicedb:8443", AUTORIZACAO_SOMBRA=True)
class TokenSemListaOPdpDecideTests(TestCase):
    def setUp(self):
        autorizacao.esquecer_modos()
        self.addCleanup(autorizacao.esquecer_modos)
        p = mock.patch.object(autorizacao_pdp, "decidir_com_rastro",
                              return_value=autorizacao_pdp.Resposta(True, "pdp", "modulo_pdca:t", "Z"))
        self.pdp = p.start()
        self.addCleanup(p.stop)
        s = mock.patch.object(autorizacao_sombra, "submeter")
        self.sombra = s.start()
        self.addCleanup(s.stop)

    def test_sem_lista_o_pdp_decide_mesmo_com_o_modulo_no_token(self):
        ModoAutorizacao.objects.create(modulo="pdca", modo=ModoAutorizacao.Modo.TOKEN)
        # A pessoa não tem a permissão na lista — e a lista nem veio: quem responde é o PDP.
        self.assertTrue(autorizacao.pode(enxuta(), "pdca.nc.view"))
        self.pdp.assert_called_once()

    def test_sem_lista_a_sombra_nao_compara(self):
        autorizacao.pode(enxuta(), "pdca.nc.view")
        self.sombra.assert_not_called()

    def test_com_lista_a_volta_atras_decide_pelo_modo(self):
        ModoAutorizacao.objects.create(modulo="pdca", modo=ModoAutorizacao.Modo.TOKEN)
        self.assertTrue(autorizacao.pode(pessoa(perms=["pdca.nc.view"]), "pdca.nc.view"))
        self.pdp.assert_not_called()
        self.sombra.assert_called_once()

    def test_o_admin_do_espelho_nao_decide_sozinho(self):
        """Sem lista, `is_tenant_admin` do espelho não é atalho: o PDP diz."""
        self.pdp.return_value = autorizacao_pdp.Resposta(False, "pdp")
        self.assertFalse(autorizacao.pode(enxuta(admin=True), "pdca.nc.view"))


@override_settings(SPICEDB_URL="http://spicedb:8443", AUTORIZACAO_SOMBRA=False)
class AuditoriaDeDecisaoTests(TestCase):
    def setUp(self):
        autorizacao.esquecer_modos()
        self.addCleanup(autorizacao.esquecer_modos)
        p = mock.patch.object(autorizacao_pdp, "decidir_com_rastro")
        self.pdp = p.start()
        self.addCleanup(p.stop)

    def _responde(self, ok):
        self.pdp.return_value = autorizacao_pdp.Resposta(ok, "pdp", f"modulo_pdca:{TENANT}", "ZED")

    def test_negacao_vai_a_tabela_com_o_rastro(self):
        self._responde(False)
        u = enxuta()
        autorizacao.pode(u, "pdca.nc.view")
        d = DecisaoAcesso.objects.get()
        self.assertEqual((d.acao, d.decisao, d.classe, d.origem), ("c:pdca.nc.view", False, "A", "pdp"))
        self.assertEqual((str(d.tenant_id), d.usuario_id, d.sid), (TENANT, u.iam_user_id, "sid-1"))
        self.assertEqual((d.recurso, d.zedtoken), (f"modulo_pdca:{TENANT}", "ZED"))

    def test_concessao_comum_so_vai_ao_log(self):
        self._responde(True)
        with self.assertLogs("sgi.authz.decisao", level="INFO") as log:
            autorizacao.pode(enxuta(), "pdca.nc.view")
        self.assertEqual(DecisaoAcesso.objects.count(), 0)
        evento = json.loads(log.output[0].split("authz.decisao ", 1)[1])
        self.assertEqual(set(evento), {
            "requisicao", "tenant", "pessoa", "sid", "acao", "recurso", "decisao",
            "classe", "origem", "zedtoken",
        })

    def test_concessao_da_classe_c_vai_a_tabela(self):
        self._responde(True)
        autorizacao.pode(enxuta(), "pdca.medicao.atestar")
        self.assertEqual(DecisaoAcesso.objects.get().classe, "C")

    def test_a_mesma_pergunta_na_mesma_requisicao_registra_uma_vez(self):
        self._responde(False)
        u = enxuta()
        for _ in range(3):
            autorizacao.pode(u, "pdca.nc.view")
        self.assertEqual(DecisaoAcesso.objects.count(), 1)

    def test_token_de_servico_nao_e_pessoa_e_nao_e_auditado_como_tal(self):
        autorizacao.usa_modulo(pessoa(modulos=["drone"], iam=False), "drone")
        self.assertEqual(DecisaoAcesso.objects.count(), 0)

    def _linha(self, dias_atras=0, tenant=TENANT):
        d = DecisaoAcesso.objects.create(
            tenant_id=tenant, usuario_id="u", acao="c:x", recurso="r", decisao=False,
            classe="B", origem="pdp",
        )
        # Envelhecer a linha é justamente o que o gatilho proíbe: desligado só aqui.
        with connection.cursor() as cur:
            cur.execute("ALTER TABLE nucleo_decisaoacesso DISABLE TRIGGER nucleo_decisao_imutavel")
            cur.execute("UPDATE nucleo_decisaoacesso SET instante = %s WHERE id = %s",
                        [timezone.now() - timedelta(days=dias_atras), d.pk])
            cur.execute("ALTER TABLE nucleo_decisaoacesso ENABLE TRIGGER nucleo_decisao_imutavel")
        return d

    def test_append_only_no_modelo_e_no_banco(self):
        d = self._linha()
        with self.assertRaises(ValueError):
            d.save()
        with self.assertRaises(ValueError):
            d.delete()
        with self.assertRaises(InternalError), transaction.atomic():
            DecisaoAcesso.objects.filter(pk=d.pk).update(decisao=True)
        with self.assertRaises(InternalError), transaction.atomic():
            DecisaoAcesso.objects.filter(pk=d.pk).delete()

    def test_a_purga_respeita_a_janela_do_plano_e_o_piso(self):
        fichas.esquecer()
        velha = self._linha(dias_atras=AUDITORIA_DECISAO_PISO_DIAS + 1)
        no_piso = self._linha(dias_atras=AUDITORIA_DECISAO_PISO_DIAS - 1)
        outro = str(uuid.uuid4())
        guardada = self._linha(dias_atras=400, tenant=outro)
        r = RedisDeMentira()
        # A empresa `outro` contratou guardar sem prazo; a de TENANT não tem ficha (piso).
        r.set(chaves.ficha_da_empresa(outro), json.dumps({"quotas": {"auditoria_decisao_retencao_dias": None}}))
        with mock.patch.object(autorizacao_pdp, "redis", return_value=r):
            self.assertEqual(auditoria_decisao.purgar(), 1)
        restantes = set(DecisaoAcesso.objects.values_list("pk", flat=True))
        self.assertEqual(restantes, {no_piso.pk, guardada.pk})
        self.assertNotIn(velha.pk, restantes)

    def test_janela_abaixo_do_piso_vira_o_piso(self):
        fichas.esquecer()
        r = RedisDeMentira()
        r.set(chaves.ficha_da_empresa(TENANT), json.dumps({"quotas": {"auditoria_decisao_retencao_dias": 7}}))
        with mock.patch.object(autorizacao_pdp, "redis", return_value=r):
            self.assertEqual(auditoria_decisao.janela_em_dias(TENANT), AUDITORIA_DECISAO_PISO_DIAS)


class SidClasseBTests(TestCase):
    def setUp(self):
        revocation._sids.clear()
        revocation._breaker_until = 0.0
        self.addCleanup(revocation._sids.clear)
        self.r = RedisDeMentira()
        p = mock.patch.object(revocation, "_redis", return_value=self.r)
        self.redis = p.start()
        self.addCleanup(p.stop)

    def _derrubar_o_redis(self):
        self.redis.side_effect = ConnectionError("fora")

    def test_sem_marca_vale_e_com_marca_nao(self):
        self.assertFalse(revocation.is_sid_revoked("s1"))
        self.r.set(chaves.sessao_revogada("s2"), 1)
        self.assertTrue(revocation.is_sid_revoked("s2"))

    def test_sem_sid_nao_ha_sessao_a_conferir(self):
        self.assertFalse(revocation.is_sid_revoked(None))

    def test_redis_fora_serve_o_visto_depois_pergunta_a_iam_e_nega_sem_ninguem(self):
        self.assertFalse(revocation.is_sid_revoked("s1"))       # visto agora
        self._derrubar_o_redis()
        with mock.patch.object(revocation, "_perguntar_a_iam") as iam:
            self.assertFalse(revocation.is_sid_revoked("s1"))   # o visto há menos de 5 s
            iam.assert_not_called()
            iam.return_value = False                            # a IAM diz: encerrada
            self.assertTrue(revocation.is_sid_revoked("s-nova"))
            iam.return_value = None                             # nem a IAM responde
            self.assertTrue(revocation.is_sid_revoked("s-outra"))


class AutenticacaoComTokenEnxutoTests(TestCase):
    def setUp(self):
        fichas.esquecer()
        self.addCleanup(fichas.esquecer)
        self.r = RedisDeMentira()
        self.uid = str(uuid.uuid4())
        self.r.set(chaves.ficha_da_empresa(TENANT), json.dumps({
            "slug": "construtora", "nome": "Construtora", "plano": "profissional",
            "rate_hora": 1234, "quotas": {"obras": 8},
        }))
        self.r.set(chaves.ficha_da_pessoa(self.uid), json.dumps({"email": "ana@teste.com"}))
        for alvo, valor in ((autorizacao_pdp, "redis"),):
            p = mock.patch.object(alvo, valor, return_value=self.r)
            p.start()
            self.addCleanup(p.stop)
        for nome in ("is_session_revoked", "is_sid_revoked"):
            p = mock.patch(f"nucleo.authentication.{nome}", return_value=False)
            p.start()
            self.addCleanup(p.stop)

    def _token(self, **extra):
        return {"sub": "ana", "user_id": self.uid, "tenant_id": TENANT, "sid": "s1",
                "iat": 1, "amr": ["pwd"], **extra}

    def test_o_que_saiu_do_token_chega_pelas_fichas(self):
        u = IamJWTAuthentication().get_user(self._token())
        self.assertFalse(u.iam_lista_no_token)
        self.assertEqual((u.iam_plano, u.iam_rate_hora, u.iam_quotas), ("profissional", 1234, {"obras": 8}))
        self.assertEqual(u.email, "ana@teste.com")
        self.assertEqual(u.tenant.slug, "construtora")
        self.assertEqual(u.iam_sid, "s1")

    def test_o_token_da_volta_atras_vale_pelas_claims(self):
        u = IamJWTAuthentication().get_user(self._token(
            permissions=["pdca.nc.view"], modules=["pdca"], plano="free", tenant_slug="c2",
            email="outra@teste.com", is_tenant_admin=False,
        ))
        self.assertTrue(u.iam_lista_no_token)
        self.assertEqual(u.iam_plano, "free")

    def test_sessao_encerrada_nao_autentica(self):
        with mock.patch("nucleo.authentication.is_sid_revoked", return_value=True):
            with self.assertRaises(InvalidToken):
                IamJWTAuthentication().get_user(self._token())

    def test_sem_ficha_o_espelho_nao_perde_o_admin(self):
        """Sem a claim, "é admin?" é pergunta ao PDP — o espelho não é zerado."""
        u = IamJWTAuthentication().get_user(self._token())
        u.is_tenant_admin = True
        u.save(update_fields=["is_tenant_admin"])
        u2 = IamJWTAuthentication().get_user(self._token())
        self.assertTrue(u2.is_tenant_admin)
