"""Remodelagem, fase 2 — o PDP responde o que o token responde.

Três camadas:

1. **O schema é o catálogo** (sem SpiceDB): o arquivo gerado em
   `funcoesautorizacao/gerado/` é exatamente o que o catálogo de hoje produz, e
   todo código cabe num identificador do SpiceDB. Código novo no catálogo sem
   regerar quebra aqui — é a cobrança da §10.4.
2. **As relações** que as tabelas implicam (sem SpiceDB).
3. **A equivalência** (com SpiceDB de teste): num tenant com todos os casos de
   borda, para cada pessoa, cada um dos códigos do catálogo, cada módulo e as
   perguntas de papel, o PDP responde **igual** ao token. É o "zero divergência"
   da §10.12 provado antes de a sombra ir para uso real — e é também o que prova
   que a troca de papel chega ao PDP na hora, enquanto o token ainda não soube.

A camada 3 precisa de `SPICEDB_TESTES_URL` (o `spicedb-testes` do dev.yml, que
é em memória e isola cada chave). Sem ela, a classe é pulada **com o motivo
escrito** — e a E2E `seg2_pdp_sombra_test.py` cobre o mesmo contra o stack.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import timedelta
from unittest import mock, skipUnless

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

import funcoesautorizacao
from funcoesautorizacao import classes
from funcoesautorizacao.cliente import ClienteSpiceDB, Rel, consistencia_total
from funcoesautorizacao.esquema import (
    ID_PLATAFORMA,
    gerar_catalogo,
    gerar_esquema,
    gerar_limites_do_drone,
    id_do_papel,
    identificador_valido,
    permissao_do_codigo,
    relacao_de_concessao,
    tipo_do_modulo,
)
from identity import catalog, equivalencia, pdp
from identity.models import (
    AcessoUsuarioModulo,
    AssinaturaTenant,
    Modulo,
    Perfil,
    Permissao,
    Tenant,
    Usuario,
)

SPICEDB_TESTES_URL = os.getenv("SPICEDB_TESTES_URL", "")


class EsquemaEhOCatalogoTests(SimpleTestCase):
    def test_o_esquema_gravado_e_o_que_o_catalogo_produz(self):
        self.assertEqual(
            funcoesautorizacao.ARQUIVO_ESQUEMA.read_text(encoding="utf-8"),
            gerar_esquema(catalog.CATALOGO),
            "Catálogo mudou sem regerar o schema: python funcoesautorizacao/gerar.py",
        )

    def test_o_catalogo_do_backend_e_o_que_o_catalogo_produz(self):
        self.assertEqual(
            funcoesautorizacao.ARQUIVO_CATALOGO.read_text(encoding="utf-8"),
            gerar_catalogo(catalog.CATALOGO, classes.classe_do_codigo),
            "Catálogo mudou sem regerar: python funcoesautorizacao/gerar.py",
        )

    def test_o_teto_do_drone_e_o_do_payment(self):
        from payment.planos import AUTORIZACAO_PDP_TIMEOUT_MS

        self.assertEqual(
            funcoesautorizacao.ARQUIVO_LIMITES_DO_DRONE.read_text(encoding="utf-8"),
            gerar_limites_do_drone(AUTORIZACAO_PDP_TIMEOUT_MS),
            "payment/planos.py mudou sem regerar: python funcoesautorizacao/gerar.py",
        )

    def test_todo_codigo_vira_nome_valido_e_a_volta_e_univoca(self):
        for p in catalog.CATALOGO:
            self.assertNotIn("__", p.code, f"{p.code}: '__' tornaria o nome ambíguo")
            self.assertTrue(identificador_valido(relacao_de_concessao(p.code)), p.code)
            self.assertTrue(identificador_valido(permissao_do_codigo(p.code)), p.code)
        nomes = [permissao_do_codigo(p.code) for p in catalog.CATALOGO]
        self.assertEqual(len(nomes), len(set(nomes)))

    def test_todo_codigo_tem_permissao_no_esquema_e_nada_sobra(self):
        texto = funcoesautorizacao.texto_do_esquema()
        no_esquema = set(re.findall(r"permission (\w+) = empresa->administrador", texto))
        do_catalogo = {permissao_do_codigo(p.code) for p in catalog.CATALOGO}
        self.assertEqual(no_esquema, do_catalogo)

    def test_as_listas_das_classes_so_citam_codigo_do_catalogo(self):
        # Um código com erro de digitação na lista de críticos deixaria o ato
        # verdadeiro em B, com cache — o erro que esta cobrança evita.
        codigos = set(catalog.CODIGOS)
        self.assertEqual(classes.CRITICOS - codigos, set())
        self.assertEqual(classes.LEITURAS_SENSIVEIS - codigos, set())

    def test_a_volta_periodica_le_o_periodo_do_payment(self):
        """Todo teto vive em `payment/planos.py` (§5.5p) — e o de 300 s é inteiro
        grande o bastante para a identidade provar algo (D190)."""
        from identity.management.commands import sincronizar_pdp
        from payment import planos

        self.assertIs(sincronizar_pdp.AUTORIZACAO_SINCRONIA_PERIODO_S,
                      planos.AUTORIZACAO_SINCRONIA_PERIODO_S)
        self.assertIs(pdp.AUTORIZACAO_PDP_TIMEOUT_MS, planos.AUTORIZACAO_PDP_TIMEOUT_MS)

    def test_os_atos_criticos_da_planta_estao_em_C(self):
        for codigo in ("pdca.medicao.atestar", "pdca.aditivo.aprovar", "erp.conta_pagar.baixar",
                       "plataforma.papel.gerir", "plataforma.fluxo_aprovacao.edit",
                       "plataforma.lgpd.exportar", "plataforma.lixo.purgar",
                       "pdca.ocorrencia.emitir_cat"):
            self.assertEqual(classes.classe_do_codigo(codigo), classes.C, codigo)
        self.assertEqual(classes.classe_do_codigo("pdca.cronograma.view"), classes.A)
        self.assertEqual(classes.classe_do_codigo("rh.cpf.view"), classes.B)
        self.assertEqual(classes.classe_do_codigo("pdca.avanco.apontar"), classes.B)


def _cenario(testcase):
    """Um tenant com cada caso de borda da régua de hoje, e um segundo tenant."""
    hoje = timezone.now().date()
    t = Tenant.objects.create(nome="Construtora", slug=f"c-{uuid.uuid4().hex[:6]}")
    outro = Tenant.objects.create(nome="Outra", slug=f"o-{uuid.uuid4().hex[:6]}")
    # `maps` fica FORA da tabela de módulos: o supervisor não o alcança.
    modulos = {
        cod: Modulo.objects.get_or_create(codigo=cod, defaults={"nome": cod})[0]
        for cod in ("pdca", "rh", "erp_financeiro", "crm", "drone", "prancheta", "orcamento")
    }
    Modulo.objects.filter(codigo="maps").delete()
    A = AssinaturaTenant
    A.objects.create(tenant=t, modulo=modulos["pdca"])
    A.objects.create(tenant=t, modulo=modulos["rh"])
    A.objects.create(tenant=t, modulo=modulos["prancheta"], fim=hoje)          # vence hoje: vale
    A.objects.create(tenant=t, modulo=modulos["erp_financeiro"], fim=hoje - timedelta(days=1))
    A.objects.create(tenant=t, modulo=modulos["crm"], inicio=hoje + timedelta(days=1))
    A.objects.create(tenant=t, modulo=modulos["drone"], status=A.Status.SUSPENSA)
    A.objects.create(tenant=outro, modulo=modulos["pdca"])

    def perm(code):
        return Permissao.objects.get_or_create(codename=code, defaults={"nome": code})[0]

    fiscal = Perfil.objects.create(tenant=t, nome="fiscal")
    fiscal.permissoes.set([perm(c) for c in (
        "pdca.medicao.atestar", "pdca.contrato.view", "rh.funcionario.view",
        "cadastro.cliente.view", "plataforma.lixo.restaurar", "erp.nf.view", "crm.lead.view",
        "prancheta.documento.view", "codigo.fora.do_catalogo",
    )])
    campo = Perfil.objects.create(tenant=t, nome="campo")
    campo.permissoes.set([perm(c) for c in (
        "pdca.avanco.apontar", "mapa.local.view", "mapa.feicao.view", "drone.projeto.view",
    )])
    papel_do_outro = Perfil.objects.create(tenant=outro, nome="fiscal")
    papel_do_outro.permissoes.set([perm("pdca.medicao.atestar")])

    def pessoa(nome, tenant=t, perfis=(), modulos_=(), **extra):
        u = Usuario.objects.create(username=f"{nome}-{uuid.uuid4().hex[:6]}",
                                   email=f"{nome}-{uuid.uuid4().hex[:6]}@x.com",
                                   tenant=tenant, **extra)
        u.perfis.set(perfis)
        for cod in modulos_:
            AcessoUsuarioModulo.objects.create(usuario=u, modulo=modulos[cod])
        return u

    testcase.t, testcase.outro = t, outro
    testcase.fiscal, testcase.campo = fiscal, campo
    testcase.pessoas = {
        "admin": pessoa("admin", is_tenant_admin=True),
        "ana": pessoa("ana", perfis=[fiscal, campo],
                      modulos_=["pdca", "rh", "erp_financeiro", "crm", "prancheta", "drone"]),
        "beto": pessoa("beto", perfis=[campo], modulos_=["pdca"]),
        "carla": pessoa("carla", perfis=[fiscal]),            # papel sem acesso a módulo
        "super": pessoa("super", is_superuser=True),
        "super_admin": pessoa("superadm", is_superuser=True, is_tenant_admin=True),
        "do_outro": pessoa("dooutro", tenant=outro, perfis=[papel_do_outro], modulos_=["pdca"]),
    }
    testcase.inativo = pessoa("inativo", perfis=[fiscal], modulos_=["pdca"], is_active=False)


class AgendamentoTests(TestCase):
    """A escrita da tela vai ao PDP no fim da transação, uma vez por tenant."""

    def setUp(self):
        p = mock.patch.object(pdp, "ativo", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def test_uma_vez_por_tenant_por_transacao(self):
        with self.captureOnCommitCallbacks() as callbacks:
            for _ in range(5):
                pdp.agendar("t-1")
            pdp.agendar("t-2")
        self.assertEqual(len(callbacks), 2)

    def test_rollback_nao_deixa_o_tenant_preso(self):
        """A primeira versão guardava o tenant num conjunto por thread que só o
        callback esvaziava; o rollback descarta o callback, e o tenant nunca
        mais era agendado naquela thread."""
        from django.db import transaction

        try:
            with transaction.atomic():
                pdp.agendar("t-1")
                raise RuntimeError("a requisição falhou no meio")
        except RuntimeError:
            pass
        with self.captureOnCommitCallbacks() as callbacks:
            pdp.agendar("t-1")
        self.assertEqual(len(callbacks), 1)


class RelacoesDoTenantTests(TestCase):
    def setUp(self):
        _cenario(self)
        self.rels = pdp.relacoes_do_tenant(self.t.id)
        self.tid = str(self.t.id)

    def _tem(self, *args):
        return Rel(*args) in self.rels

    def test_assinatura_so_enquanto_vale(self):
        for modulo, vale in (("pdca", True), ("prancheta", True), ("erp_financeiro", False),
                             ("crm", False), ("drone", False), ("maps", False)):
            self.assertEqual(
                self._tem(tipo_do_modulo(modulo), self.tid, "assinatura", "empresa", self.tid),
                vale, modulo,
            )

    def test_catalogado_segue_a_tabela_de_modulos(self):
        self.assertTrue(self._tem("modulo_pdca", self.tid, "catalogado", "empresa", self.tid))
        self.assertFalse(self._tem("modulo_maps", self.tid, "catalogado", "empresa", self.tid))
        # O objeto do módulo existe mesmo sem catálogo: a pergunta do admin por
        # código não pode virar erro no PDP.
        self.assertTrue(self._tem("modulo_maps", self.tid, "empresa", "empresa", self.tid))

    def test_conta_desativada_nao_entra(self):
        uid = str(self.inativo.id)
        self.assertFalse(any(r.sujeito_id == uid for r in self.rels))

    def test_codigo_fora_do_catalogo_nao_vira_relacao(self):
        self.assertFalse(any("fora" in r.relacao for r in self.rels))

    def test_nada_de_outra_empresa(self):
        self.assertTrue(all(r.id.startswith(self.tid) for r in self.rels))
        uid = str(self.pessoas["do_outro"].id)
        self.assertFalse(any(r.sujeito_id == uid for r in self.rels))

    def test_o_papel_concede_pelo_portador(self):
        pid = id_do_papel(self.tid, self.fiscal.id)
        self.assertTrue(self._tem("modulo_pdca", self.tid,
                                  relacao_de_concessao("pdca.medicao.atestar"),
                                  "papel", pid, "portador"))
        self.assertTrue(self._tem("papel", pid, "portador", "usuario",
                                  str(self.pessoas["ana"].id)))


# A régua mora em `identity/equivalencia.py`, compartilhada com o comando
# `conferir_equivalencia` — o teste e quem opera medem a mesma coisa.
_pelo_token = equivalencia.pelo_token
_no_pdp = equivalencia.no_pdp
_perguntas = equivalencia.perguntas


@skipUnless(SPICEDB_TESTES_URL, "SPICEDB_TESTES_URL não definida (o spicedb-testes do dev.yml)")
class PdpRespondeOQueOTokenRespondeTests(TestCase):
    """A prova da fase 2, antes do uso real: nenhuma pergunta diverge."""

    def setUp(self):
        self.cli = ClienteSpiceDB(SPICEDB_TESTES_URL, f"teste-{uuid.uuid4()}", timeout_s=5)
        self.cli.escrever_esquema(funcoesautorizacao.texto_do_esquema())
        # O cenário nasce com o PDP desligado: senão os sinais já deixariam um
        # callback por tenant na transação do teste, e a deduplicação (correta)
        # não registraria o da troca que cada teste faz dentro do capture.
        with mock.patch.object(pdp, "ativo", return_value=False):
            _cenario(self)
        # Os sinais da IAM não escrevem sem SPICEDB_URL; aqui eles escrevem no
        # PDP de teste, e o Redis de anotação não precisa existir.
        self._patches = [
            mock.patch.object(pdp, "ativo", return_value=True),
            mock.patch.object(pdp, "cliente", return_value=self.cli),
            mock.patch.object(pdp, "_anotar_mudanca"),
            # As fichas iriam ao Redis de verdade (o do ambiente), não ao de teste.
            mock.patch.object(pdp, "_publicar_fichas"),
        ]
        for p in self._patches:
            p.start()
        for tid in (self.t.id, self.outro.id):
            pdp.reconciliar_tenant(tid, self.cli)
        pdp.reconciliar_plataforma(self.cli)

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def _divergencias(self, pessoa) -> list[str]:
        pessoa.refresh_from_db()
        return equivalencia.divergencias(self.cli, pessoa).divergencias

    def test_nenhuma_pessoa_diverge_em_nenhuma_pergunta(self):
        for nome, pessoa in self.pessoas.items():
            with self.subTest(pessoa=nome):
                self.assertEqual(self._divergencias(pessoa), [])

    def test_quem_e_de_outra_empresa_nao_passa_em_nada_desta(self):
        uid = str(self.pessoas["do_outro"].id)
        itens = [_no_pdp(p, str(self.t.id)) for p in _perguntas() if p[0] != "supervisiona"]
        respostas = []
        for i in range(0, len(itens), 100):
            respostas += self.cli.checar_em_lote(itens[i:i + 100], uid, consistencia_total())
        self.assertFalse(any(r is True for r in respostas))

    def test_tirar_o_papel_chega_ao_pdp_na_hora_e_o_token_velho_ainda_nao_sabe(self):
        ana = self.pessoas["ana"]
        token_velho = equivalencia.lista_da_pessoa(ana)
        pergunta = ("codigo", "pdca.medicao.atestar")
        with self.captureOnCommitCallbacks(execute=True):
            ana.perfis.remove(self.fiscal)
        ok, _ = self.cli.checar(*_no_pdp(pergunta, str(self.t.id)), str(ana.id),
                                consistencia_total())
        self.assertFalse(ok, "o PDP ainda concede o que o papel removido dava")
        self.assertTrue(_pelo_token(token_velho, pergunta),
                        "o token emitido antes da troca ainda carrega a permissão — é a janela"
                        " que a fase 4 fecha, e o que a sombra classifica como token defasado")
        self.assertEqual(self._divergencias(ana), [])

    def test_desativar_a_conta_tira_tudo_do_pdp(self):
        beto = self.pessoas["beto"]
        with self.captureOnCommitCallbacks(execute=True):
            beto.is_active = False
            beto.save()
        uid = str(beto.id)
        for tipo in pdp._tipos_de_tenant():
            self.assertFalse(
                any(r.sujeito_id == uid for r in self.cli.ler(tipo, str(self.t.id))), tipo
            )

    def test_assinatura_suspensa_fecha_o_modulo_para_o_admin(self):
        admin = self.pessoas["admin"]
        pergunta = ("usa", "pdca")
        with self.captureOnCommitCallbacks(execute=True):
            AssinaturaTenant.objects.filter(tenant=self.t, modulo__codigo="pdca").update(
                status=AssinaturaTenant.Status.SUSPENSA
            )
            # `update()` não dispara sinal — é o caso que a volta periódica cobre.
            pdp.reconciliar_tenant(self.t.id, self.cli)
        ok, _ = self.cli.checar(*_no_pdp(pergunta, str(self.t.id)), str(admin.id),
                                consistencia_total())
        self.assertFalse(ok)
        self.assertEqual(self._divergencias(admin), [])

    def test_reconciliar_de_novo_nao_muda_nada(self):
        r = pdp.reconciliar_tenant(self.t.id, self.cli)
        self.assertEqual((r["tocadas"], r["removidas"]), (0, 0))

    def test_empresa_que_sumiu_da_iam_sai_do_pdp(self):
        tid = str(self.outro.id)
        with self.captureOnCommitCallbacks(execute=True):
            Tenant.objects.filter(pk=self.outro.pk).delete()
        pdp.reconciliar_tudo(self.cli)
        self.assertEqual(self.cli.ler("modulo_base", tid), [])
