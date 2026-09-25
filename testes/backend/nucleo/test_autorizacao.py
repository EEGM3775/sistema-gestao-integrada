"""Remodelagem, fases 2 e 3 — a decisão única, a sombra e a virada por módulo.

O que se cobra aqui, em ordem:

1. **A semântica não mudou** — cada pergunta de `nucleo/autorizacao.py` pelo token
   responde o que a leitura espalhada respondia antes.
2. **Uma decisão, um lugar** (§10.3, princípio 2): ninguém fora de
   `autorizacao.py` lê claim de permissão, módulo ou papel.
3. **Os códigos e módulos que as views exigem existem no catálogo** — senão o
   PDP negaria o que o token concede, e a virada quebraria a tela.
4. **O PDP decide com o modo de falha da planta** (§10.8): cache por classe, C
   sem cache, PDP fora nega, versão nova aposenta a decisão velha.
5. **A virada é por módulo** e a volta é imediata.
6. **A sombra classifica** a divergência — token velho não é defeito.
7. **Contra um SpiceDB de verdade** (com `SPICEDB_TESTES_URL`): revogar vale na
   próxima pergunta, mesmo com a decisão anterior no cache.

A metade "o que o PDP responde para cada papel" está na IAM
(`testes/iam/identity/test_pdp.py`), que é quem escreve as relações.
"""
from __future__ import annotations

import ast
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock, skipUnless

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.exceptions import ValidationError

import funcoesautorizacao
from funcoesautorizacao import chaves, classes
from funcoesautorizacao.cliente import ClienteSpiceDB, PdpIndisponivel, PerguntaInvalida, Rel
from funcoesautorizacao.esquema import permissao_do_codigo, relacao_de_concessao
from nucleo import autorizacao, autorizacao_pdp, autorizacao_sombra
from nucleo.aprovacao_views import NivelAprovacaoSerializer
from nucleo.management.commands.vigiar_pdp import versoes_a_subir
from nucleo.models import DivergenciaAutorizacao, ModoAutorizacao

SPICEDB_TESTES_URL = os.getenv("SPICEDB_TESTES_URL", "")
TENANT = str(uuid.uuid4())


def pessoa(*, perms=(), modulos=(), admin=False, plataforma=False, superuser=False,
           iam=True, iat=None):
    """O `user` como a autenticação o monta. `iam=False` é o token de serviço."""
    u = SimpleNamespace(
        is_authenticated=True, is_tenant_admin=admin, is_platform_admin=plataforma,
        is_superuser=superuser, iam_permissions=list(perms), iam_modules=list(modulos),
        iam_user_id=str(uuid.uuid4()) if iam else None,
        iam_tenant_id=TENANT if iam else None, iam_token_iat=iat,
    )
    return u


class RedisDeMentira:
    """O pedaço do Redis que a autorização usa, em memória."""

    def __init__(self):
        self.d: dict = {}
        self.h: dict = {}

    def mget(self, *ks):
        return [self.d.get(k) for k in ks]

    def get(self, k):
        return self.d.get(k)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.d:
            return None
        self.d[k] = str(v)
        return True

    def setex(self, k, ttl, v):
        self.d[k] = str(v)

    def incr(self, k):
        self.d[k] = str(int(self.d.get(k) or 0) + 1)
        return int(self.d[k])

    def delete(self, k):
        self.d.pop(k, None)

    def expire(self, *_):
        return True

    def hincrby(self, h, f, n):
        self.h.setdefault(h, {})
        self.h[h][f] = self.h[h].get(f, 0) + n

    def hgetall(self, h):
        return self.h.get(h, {})

    def pipeline(self):
        return self

    def execute(self):
        return []


class PdpDeMentira:
    """Responde por um dicionário ``(pergunta do PDP, pessoa) → bool``."""

    def __init__(self, respostas=None, erro=None):
        self.respostas = respostas or {}
        self.erro = erro
        self.perguntas = []

    def checar(self, tipo, id_, permissao, usuario_id, consistencia):
        self.perguntas.append((tipo, permissao, consistencia))
        if self.erro:
            raise self.erro
        return self.respostas.get((tipo, permissao, usuario_id), False), "zed"


# --- 1. A semântica pelo token ----------------------------------------------


class PeloTokenNadaMudouTests(SimpleTestCase):
    def test_pode_e_admin_ou_codigo_na_claim(self):
        self.assertTrue(autorizacao.pode(pessoa(perms=["pdca.nc.view"]), "pdca.nc.view"))
        self.assertFalse(autorizacao.pode(pessoa(perms=["pdca.nc.view"]), "pdca.nc.tratar"))
        self.assertTrue(autorizacao.pode(pessoa(admin=True), "pdca.medicao.atestar"))
        self.assertTrue(autorizacao.pode(pessoa(superuser=True), "rh.cpf.view"))
        self.assertFalse(autorizacao.pode(pessoa(plataforma=True), "rh.cpf.view"))

    def test_quem_nao_esta_autenticado_nao_passa_em_nada(self):
        anonimo = SimpleNamespace(is_authenticated=False, is_superuser=False)
        self.assertFalse(autorizacao.pode(anonimo, "pdca.nc.view"))
        self.assertFalse(autorizacao.usa_modulo(anonimo, "pdca"))
        self.assertFalse(autorizacao.administra(anonimo))

    def test_usa_modulo_e_so_a_claim_modules(self):
        self.assertTrue(autorizacao.usa_modulo(pessoa(modulos=["pdca"]), "pdca"))
        self.assertFalse(autorizacao.usa_modulo(pessoa(admin=True), "pdca"))

    def test_papeis(self):
        self.assertTrue(autorizacao.administra(pessoa(admin=True)))
        self.assertTrue(autorizacao.administra(pessoa(superuser=True)))
        self.assertFalse(autorizacao.administra(pessoa(plataforma=True)))
        self.assertTrue(autorizacao.supervisiona(pessoa(plataforma=True)))
        self.assertFalse(autorizacao.supervisiona(pessoa(admin=True)))

    def test_tem_na_lista_nao_da_passe_ao_admin_fora_do_modulo(self):
        self.assertFalse(autorizacao.tem_na_lista(pessoa(admin=True), "prancheta.documento.edit"))
        self.assertTrue(autorizacao.tem_na_lista(
            pessoa(admin=True, modulos=["prancheta"]), "prancheta.documento.edit"))
        self.assertTrue(autorizacao.tem_na_lista(pessoa(admin=True), "cadastro.cliente.edit"))
        self.assertFalse(autorizacao.tem_na_lista(pessoa(superuser=True), "prancheta.documento.edit"))

    def test_permitidos(self):
        u = pessoa(perms=["pdca.nc.view", "pdca.nc.abrir"])
        self.assertEqual(
            autorizacao.permitidos(u, ["pdca.nc.view", "pdca.nc.tratar", "pdca.nc.abrir"]),
            {"pdca.nc.view", "pdca.nc.abrir"},
        )

    def test_uma_resposta_por_requisicao(self):
        u = pessoa(perms=["pdca.nc.view"])
        with mock.patch.object(autorizacao, "_pelo_token", wraps=autorizacao._pelo_token) as m:
            for _ in range(20):  # a máscara de campo pergunta o mesmo a cada linha
                self.assertTrue(autorizacao.pode(u, "pdca.nc.view"))
        self.assertEqual(m.call_count, 1)

    def test_claim_trocada_no_mesmo_objeto_nao_herda_a_resposta_velha(self):
        # O `force_authenticate` dos testes reusa o objeto entre requisições.
        u = pessoa(perms=["pdca.nc.view"])
        self.assertFalse(autorizacao.pode(u, "pdca.nc.abrir"))
        u.iam_permissions = ["pdca.nc.view", "pdca.nc.abrir"]
        self.assertTrue(autorizacao.pode(u, "pdca.nc.abrir"))


# --- 2. Uma decisão, um lugar -----------------------------------------------

_CLAIMS = {"iam_permissions", "iam_modules", "iam_roles", "is_platform_admin", "is_tenant_admin"}
_PODEM_LER = {"nucleo/autorizacao.py", "nucleo/authentication.py"}


class UmaDecisaoUmLugarTests(SimpleTestCase):
    def test_ninguem_le_claim_de_acesso_fora_da_autorizacao(self):
        raiz = Path(settings.BASE_DIR)
        leituras = []
        for arquivo in raiz.rglob("*.py"):
            rel = arquivo.relative_to(raiz).as_posix()
            if "/migrations/" in rel or rel in _PODEM_LER or rel.startswith("testes/"):
                continue
            try:
                arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for no in ast.walk(arvore):
                if (isinstance(no, ast.Attribute) and no.attr in _CLAIMS
                        and isinstance(no.ctx, ast.Load)):
                    leituras.append(f"{rel}:{no.lineno} .{no.attr}")
                elif (isinstance(no, ast.Call) and getattr(no.func, "id", None) == "getattr"
                      and len(no.args) >= 2 and isinstance(no.args[1], ast.Constant)
                      and no.args[1].value in _CLAIMS):
                    leituras.append(f"{rel}:{no.lineno} getattr(..., {no.args[1].value!r})")
        self.assertEqual(
            leituras, [],
            "Pergunte a `nucleo.autorizacao` (pode, usa_modulo, administra, supervisiona) — "
            "ler a claim direto é decidir fora do PDP.",
        )


# --- 3. O que as views exigem existe no catálogo -----------------------------


def _views():
    from django.urls import URLPattern, URLResolver, get_resolver

    def andar(padroes):
        for p in padroes:
            if isinstance(p, URLResolver):
                yield from andar(p.url_patterns)
            elif isinstance(p, URLPattern):
                cls = getattr(p.callback, "cls", None) or getattr(p.callback, "view_class", None)
                if cls is not None:
                    yield cls

    return set(andar(get_resolver().url_patterns))


_SEGUROS = {"get", "head", "options"}


def _acoes(cls):
    """``(ação, é_leitura)`` que a view de fato atende — só o que tem handler."""
    from rest_framework import mixins, viewsets

    if issubclass(cls, viewsets.ViewSetMixin):
        padrao = [
            (mixins.ListModelMixin, "list", True), (mixins.RetrieveModelMixin, "retrieve", True),
            (mixins.CreateModelMixin, "create", False), (mixins.UpdateModelMixin, "update", False),
            (mixins.UpdateModelMixin, "partial_update", False),
            (mixins.DestroyModelMixin, "destroy", False),
        ]
        acoes = [(nome, leitura) for mixin, nome, leitura in padrao if issubclass(cls, mixin)]
        for extra in cls.get_extra_actions():
            for metodo in extra.mapping:
                acoes.append((extra.__name__, metodo in _SEGUROS))
        return acoes
    return [(None, m in _SEGUROS) for m in ("get", "post", "put", "patch", "delete")
            if hasattr(cls, m)]


def _codigos_alcancaveis(cls):
    """O código que o `RequirePermission` pediria em cada ação, pela mesma ordem."""
    por_acao = getattr(cls, "action_permission_map", None) or {}
    por_metodo = getattr(cls, "permission_map", None)
    recurso = getattr(cls, "required_resource", None)
    fixo = getattr(cls, "required_permission", None)
    for acao, leitura in _acoes(cls):
        if acao in por_acao:
            yield por_acao[acao]
        elif por_metodo:
            yield por_metodo.get("view" if leitura else "write")
        elif recurso:
            yield f"{recurso}.{'view' if leitura else 'edit'}"
        else:
            yield fixo


#: Vazio desde o D204 (histórico, 25/09/2026): o ledger e as cobranças viraram
#: somente leitura. Um caso novo quebra o teste.
_CODIGO_INEXISTENTE_CONHECIDO: set[str] = set()


class ViewsFalamOCatalogoTests(SimpleTestCase):
    def test_todo_codigo_que_uma_view_pode_pedir_esta_no_catalogo(self):
        """Pelo token, o admin passa em qualquer código — até no que não existe.
        Pelo PDP, código fora do catálogo nega para todo mundo. Uma ação que
        pede um código inexistente funciona hoje só para o admin e deixaria de
        funcionar para ele na virada; aqui ela aparece antes."""
        codigos = funcoesautorizacao.catalogo()["codigos"]
        fora = {
            f"{cls.__module__}.{cls.__name__}: {c}"
            for cls in _views()
            for c in _codigos_alcancaveis(cls)
            if c and c not in codigos
        }
        self.assertEqual(sorted(fora - _CODIGO_INEXISTENTE_CONHECIDO), [])
        self.assertEqual(
            sorted(_CODIGO_INEXISTENTE_CONHECIDO - fora), [],
            "Corrigido — tire da lista `_CODIGO_INEXISTENTE_CONHECIDO`.",
        )

    def test_todo_modulo_exigido_por_view_esta_no_esquema(self):
        conhecidos = set(funcoesautorizacao.catalogo()["modulos_vendaveis"])
        fora = {
            f"{cls.__module__}.{cls.__name__}: {cls.required_module}"
            for cls in _views()
            if getattr(cls, "required_module", None) and cls.required_module not in conhecidos
        }
        self.assertEqual(sorted(fora), [])


# --- 4. O PDP decide com o modo de falha da planta ---------------------------


class DecisaoPeloPdpTests(SimpleTestCase):
    def setUp(self):
        self.r = RedisDeMentira()
        self.quem = autorizacao_pdp.Quem(TENANT, "u1")
        self._p = [mock.patch.object(autorizacao_pdp, "redis", return_value=self.r)]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()

    def _com(self, pdp):
        return mock.patch.object(autorizacao_pdp, "cliente", return_value=pdp)

    def test_leitura_comum_vai_para_o_cache_e_volta_dele(self):
        p = autorizacao._pergunta_de_codigo("pdca.cronograma.view")
        pdp = PdpDeMentira({("modulo_pdca", "pdca__cronograma__view", "u1"): True})
        with self._com(pdp):
            self.assertEqual(autorizacao_pdp.decidir(self.quem, p), (True, "pdp"))
            self.assertEqual(autorizacao_pdp.decidir(self.quem, p), (True, "cache"))
        self.assertEqual(len(pdp.perguntas), 1)
        self.assertEqual(pdp.perguntas[0][2], {"minimizeLatency": True})

    def test_ato_critico_nunca_usa_cache_e_pede_consistencia_total(self):
        p = autorizacao._pergunta_de_codigo("pdca.medicao.atestar")
        self.assertEqual(p.classe, classes.C)
        pdp = PdpDeMentira({("modulo_pdca", "pdca__medicao__atestar", "u1"): True})
        with self._com(pdp):
            autorizacao_pdp.decidir(self.quem, p)
            self.assertEqual(autorizacao_pdp.decidir(self.quem, p), (True, "pdp"))
        self.assertEqual(len(pdp.perguntas), 2)
        self.assertEqual(pdp.perguntas[0][2], {"fullyConsistent": True})

    def test_classe_A_tambem_espera_a_ultima_mudanca(self):
        """Com a rápida pura, a primeira pergunta depois da revogação recebia o
        estado de antes e o guardava por 60 s — medido na E2E da virada."""
        self.r.set(chaves.zedtoken_do_tenant(TENANT), "zed-da-revogacao")
        pdp = PdpDeMentira()
        with self._com(pdp):
            autorizacao_pdp.decidir(self.quem, autorizacao._pergunta_de_codigo("pdca.cronograma.view"))
        self.assertEqual(pdp.perguntas[0][2], {"atLeastAsFresh": {"token": "zed-da-revogacao"}})

    def test_classe_B_espera_a_ultima_mudanca_do_tenant(self):
        self.r.set(chaves.zedtoken_do_tenant(TENANT), "zed-da-iam")
        pdp = PdpDeMentira()
        with self._com(pdp):
            autorizacao_pdp.decidir(self.quem, autorizacao._pergunta_de_codigo("rh.cpf.view"))
        self.assertEqual(pdp.perguntas[0][2], {"atLeastAsFresh": {"token": "zed-da-iam"}})

    def test_versao_nova_aposenta_a_decisao_guardada(self):
        p = autorizacao._pergunta_de_codigo("pdca.cronograma.view")
        pdp = PdpDeMentira({("modulo_pdca", "pdca__cronograma__view", "u1"): True})
        with self._com(pdp):
            autorizacao_pdp.decidir(self.quem, p)
            pdp.respostas.clear()  # revogado no PDP…
            self.r.incr(chaves.versao_do_usuario(TENANT, "u1"))  # …e o evento chegou
            self.assertEqual(autorizacao_pdp.decidir(self.quem, p), (False, "pdp"))

    def test_pdp_fora_nega_mas_serve_o_cache_ainda_valido(self):
        p = autorizacao._pergunta_de_codigo("pdca.cronograma.view")
        with self._com(PdpDeMentira({("modulo_pdca", "pdca__cronograma__view", "u1"): True})):
            autorizacao_pdp.decidir(self.quem, p)
        with self._com(PdpDeMentira(erro=PdpIndisponivel("fora"))):
            self.assertEqual(autorizacao_pdp.decidir(self.quem, p), (True, "cache"))
            outra = autorizacao._pergunta_de_codigo("pdca.nc.view")
            self.assertEqual(autorizacao_pdp.decidir(self.quem, outra), (False, "falha"))
            critica = autorizacao._pergunta_de_codigo("pdca.medicao.atestar")
            self.assertEqual(autorizacao_pdp.decidir(self.quem, critica), (False, "falha"))

    def test_pergunta_fora_do_esquema_nega(self):
        with self._com(PdpDeMentira(erro=PerguntaInvalida("não existe"))):
            p = autorizacao._pergunta_de_codigo("pdca.nc.view")
            self.assertEqual(autorizacao_pdp.decidir(self.quem, p), (False, "fora_do_esquema"))
        desconhecido = autorizacao._pergunta_de_codigo("nada.disso.existe")
        self.assertEqual(autorizacao_pdp.decidir(self.quem, desconhecido), (False, "fora_do_esquema"))

    def test_redis_fora_pergunta_direto_ao_pdp(self):
        quebrado = mock.Mock(mget=mock.Mock(side_effect=ConnectionError("fora")))
        pdp = PdpDeMentira({("modulo_pdca", "pdca__nc__view", "u1"): True})
        with mock.patch.object(autorizacao_pdp, "redis", return_value=quebrado), self._com(pdp):
            p = autorizacao._pergunta_de_codigo("pdca.nc.view")
            self.assertEqual(autorizacao_pdp.decidir(self.quem, p), (True, "pdp"))
        autorizacao_pdp._redis_parado_ate = 0.0

    def test_chave_sem_tenant_e_recusada(self):
        with self.assertRaises(ValueError):
            chaves.decisao("", "u1", (1, 1, 1), "c:x")


# --- 5. A virada por módulo e a volta ---------------------------------------


@override_settings(SPICEDB_URL="http://pdp-de-mentira", AUTORIZACAO_SOMBRA=False)
class ViradaPorModuloTests(TestCase):
    def setUp(self):
        autorizacao.esquecer_modos()
        self.addCleanup(autorizacao.esquecer_modos)
        self.decidir = mock.patch.object(autorizacao_pdp, "decidir", return_value=(False, "pdp"))
        self.pdp = self.decidir.start()
        self.addCleanup(self.decidir.stop)

    def test_sem_linha_o_token_decide(self):
        self.assertTrue(autorizacao.pode(pessoa(perms=["pdca.nc.view"]), "pdca.nc.view"))
        self.pdp.assert_not_called()

    def test_virado_o_pdp_decide_so_naquele_modulo(self):
        ModoAutorizacao.objects.create(modulo="pdca", modo=ModoAutorizacao.Modo.PDP)
        u = pessoa(perms=["pdca.nc.view", "rh.cargo.view"])
        self.assertFalse(autorizacao.pode(u, "pdca.nc.view"))   # o PDP disse não
        self.assertTrue(autorizacao.pode(u, "rh.cargo.view"))   # o RH segue no token
        self.assertEqual(self.pdp.call_count, 1)

    def test_a_volta_vale_na_proxima_leitura(self):
        ModoAutorizacao.objects.create(modulo="pdca", modo=ModoAutorizacao.Modo.PDP)
        self.assertFalse(autorizacao.pode(pessoa(perms=["pdca.nc.view"]), "pdca.nc.view"))
        ModoAutorizacao.objects.filter(modulo="pdca").update(modo=ModoAutorizacao.Modo.TOKEN)
        autorizacao.esquecer_modos()
        self.assertTrue(autorizacao.pode(pessoa(perms=["pdca.nc.view"]), "pdca.nc.view"))

    def test_token_de_servico_sempre_pelo_token(self):
        ModoAutorizacao.objects.create(modulo="pdca", modo=ModoAutorizacao.Modo.PDP)
        self.assertTrue(autorizacao.usa_modulo(pessoa(modulos=["pdca"], iam=False), "pdca"))
        self.pdp.assert_not_called()

    def test_perguntas_de_papel_seguem_o_modulo_plataforma(self):
        ModoAutorizacao.objects.create(modulo="plataforma", modo=ModoAutorizacao.Modo.PDP)
        self.assertFalse(autorizacao.administra(pessoa(admin=True)))
        self.assertTrue(autorizacao.administra(pessoa(admin=True, superuser=True)))  # local passa


# --- 6. A sombra -------------------------------------------------------------


class SombraTests(TestCase):
    def setUp(self):
        self.r = RedisDeMentira()
        p = mock.patch.object(autorizacao_pdp, "redis", return_value=self.r)
        p.start()
        self.addCleanup(p.stop)

    def _comparar(self, *, token, pdp, origem="pdp", iat=None, pergunta="pdca.nc.view"):
        c = autorizacao_sombra.Comparacao(
            quem=autorizacao_pdp.Quem(TENANT, "u1"), iat=iat,
            pergunta=autorizacao._pergunta_de_codigo(pergunta), modo="token",
            decisao_token=token, decisao_pdp=pdp, origem_pdp=origem,
        )
        return autorizacao_sombra.executar(c)

    def test_concordancia_nao_registra_nada_mas_conta(self):
        self.assertIsNone(self._comparar(token=True, pdp=True))
        self.assertEqual(DivergenciaAutorizacao.objects.count(), 0)
        dia = autorizacao_sombra._dia()
        self.assertEqual(self.r.get(chaves.comparacoes_do_dia(dia)), "1")
        self.assertEqual(self.r.hgetall(chaves.volume_do_dia(dia)), {f"{TENANT}|u1": 1})

    def test_token_nascido_antes_da_mudanca_e_defasado_nao_defeito(self):
        self.r.set(chaves.mudanca_do_tenant(TENANT), 2000)
        self.assertEqual(self._comparar(token=True, pdp=False, iat=1000), "token_defasado")
        self.assertEqual(self._comparar(token=False, pdp=True, iat=3000, pergunta="pdca.nc.abrir"),
                         "real")
        tipos = set(DivergenciaAutorizacao.objects.values_list("tipo", flat=True))
        self.assertEqual(tipos, {"token_defasado", "real"})

    def test_pdp_fora_e_registrado_como_tal(self):
        self.assertEqual(self._comparar(token=True, pdp=False, origem="falha"), "pdp_indisponivel")

    def test_fora_do_esquema_que_o_token_tambem_nega_nao_e_divergencia(self):
        self.assertIsNone(self._comparar(token=False, pdp=False, origem="fora_do_esquema"))

    def test_a_mesma_divergencia_entra_uma_vez_por_janela(self):
        for _ in range(5):
            self._comparar(token=True, pdp=False)
        self.assertEqual(DivergenciaAutorizacao.objects.count(), 1)

    def test_a_divergencia_e_imutavel(self):
        self._comparar(token=True, pdp=False)
        d = DivergenciaAutorizacao.objects.get()
        with self.assertRaises(ValueError):
            d.save()
        with self.assertRaises(ValueError):
            d.delete()

    def test_fila_cheia_descarta_e_conta(self):
        with mock.patch.object(autorizacao_sombra, "_vagas") as vagas:
            vagas.acquire.return_value = False
            autorizacao_sombra.submeter(mock.Mock())
        self.assertEqual(self.r.get(chaves.descartes_do_dia(autorizacao_sombra._dia())), "1")

    @override_settings(SPICEDB_URL="http://pdp-de-mentira", AUTORIZACAO_SOMBRA=True)
    def test_com_a_sombra_ligada_cada_pergunta_e_conferida_uma_vez(self):
        autorizacao.esquecer_modos()
        with mock.patch.object(autorizacao_sombra, "submeter") as submeter:
            u = pessoa(perms=["pdca.nc.view"])
            for _ in range(10):
                autorizacao.pode(u, "pdca.nc.view")
        self.assertEqual(submeter.call_count, 1)
        c = submeter.call_args.args[0]
        self.assertEqual((c.modo, c.decisao_token, c.decisao_pdp), ("token", True, None))


# --- O invalidador e a escada -------------------------------------------------


class InvalidadorTests(SimpleTestCase):
    def test_cada_mudanca_aposenta_o_que_ela_afeta(self):
        t = TENANT
        alvo = versoes_a_subir([
            ("remover", Rel("papel", f"{t}_p3", "portador", "usuario", "ana")),
            ("tocar", Rel("modulo_pdca", t, relacao_de_concessao("pdca.nc.view"), "papel", f"{t}_p3", "portador")),
            ("tocar", Rel("plataforma", "sgi", "supervisor", "usuario", "dono")),
        ])
        self.assertEqual(alvo, {
            chaves.versao_do_usuario(t, "ana"), chaves.versao_do_tenant(t), chaves.VERSAO_GLOBAL,
        })


class EscadaFalaOCatalogoTests(SimpleTestCase):
    def test_degrau_com_codigo_inventado_e_recusado(self):
        s = NivelAprovacaoSerializer()
        self.assertEqual(s.validate_permissao_exigida("pdca.medicao.atestar"), "pdca.medicao.atestar")
        with self.assertRaises(ValidationError):
            s.validate_permissao_exigida("pdca.medicao.atesta")


# --- 7. Contra um SpiceDB de verdade -----------------------------------------


@skipUnless(SPICEDB_TESTES_URL, "SPICEDB_TESTES_URL não definida (o spicedb-testes do dev.yml)")
@override_settings(SPICEDB_URL="definido-no-setUp", AUTORIZACAO_SOMBRA=False)
class RevogacaoEmSegundosTests(TestCase):
    """A fase 3 de ponta a ponta no backend: PDP decide, cache no meio, revogação."""

    def setUp(self):
        self.cli = ClienteSpiceDB(SPICEDB_TESTES_URL, f"teste-{uuid.uuid4()}", timeout_s=5)
        self.cli.escrever_esquema(funcoesautorizacao.texto_do_esquema())
        self.r = RedisDeMentira()
        for alvo, valor in ((autorizacao_pdp, "cliente"), (autorizacao_pdp, "redis")):
            p = mock.patch.object(alvo, valor, return_value=self.cli if valor == "cliente" else self.r)
            p.start()
            self.addCleanup(p.stop)
        autorizacao.esquecer_modos()
        self.addCleanup(autorizacao.esquecer_modos)
        ModoAutorizacao.objects.create(modulo="pdca", modo=ModoAutorizacao.Modo.PDP)
        self.ana = pessoa(perms=["pdca.contrato.view"], modulos=["pdca"])
        uid, papel = self.ana.iam_user_id, f"{TENANT}_p1"
        self.rels = [
            Rel("empresa", TENANT, "membro", "usuario", uid),
            Rel("modulo_pdca", TENANT, "empresa", "empresa", TENANT),
            Rel("modulo_pdca", TENANT, "assinatura", "empresa", TENANT),
            Rel("modulo_pdca", TENANT, "liberado", "usuario", uid),
            Rel("papel", papel, "portador", "usuario", uid),
            Rel("modulo_pdca", TENANT, relacao_de_concessao("pdca.contrato.view"), "papel", papel, "portador"),
        ]
        self.cli.escrever(tocar=self.rels)

    def _nova_requisicao(self):
        self.ana.__dict__.pop("_authz_memo", None)

    def test_o_pdp_decide_e_revogar_vale_na_proxima_pergunta(self):
        # `pdca.contrato.view` é classe B (saldo de contrato): cache de segundos e
        # resposta pelo menos tão nova quanto a última mudança do tenant. (A
        # classe A também espera a mudança; a E2E da virada cobre ela.)
        self.assertTrue(autorizacao.pode(self.ana, "pdca.contrato.view"))
        self.assertTrue(autorizacao.usa_modulo(self.ana, "pdca"))
        self.assertFalse(autorizacao.pode(self.ana, "pdca.medicao.atestar"))
        # A decisão ficou no cache (classe A, 60 s).
        self.assertTrue(any(k.startswith("authz:d:") for k in self.r.d))

        # A IAM tira o papel e anota a mudança — o que `identity/pdp.py` faz.
        token = self.cli.escrever(remover=[self.rels[4]])
        chaves.marcar_mudanca(self.r, TENANT, token, 0)

        self._nova_requisicao()
        self.assertFalse(autorizacao.pode(self.ana, "pdca.contrato.view"),
                         "a decisão velha do cache foi servida depois da revogação")
        # O token dela ainda carrega a permissão: é a janela que a fase 4 fecha.
        self.assertIn("pdca.contrato.view", self.ana.iam_permissions)

    def test_o_ato_critico_pergunta_sempre(self):
        papel = f"{TENANT}_p1"
        self.cli.escrever(tocar=[Rel("modulo_pdca", TENANT, relacao_de_concessao("pdca.medicao.atestar"),
                                     "papel", papel, "portador")])
        self.assertTrue(autorizacao.pode(self.ana, "pdca.medicao.atestar"))
        self.cli.escrever(remover=[self.rels[4]])  # sem anotar nada no Redis
        self._nova_requisicao()
        self.assertFalse(autorizacao.pode(self.ana, "pdca.medicao.atestar"))

    def test_o_invalidador_le_a_remocao_no_watch(self):
        cursor = self.cli.revisao_atual()
        self.cli.escrever(remover=[self.rels[4]])
        for operacoes, _ in self.cli.vigiar(cursor, timeout_s=5):
            if operacoes:
                self.assertIn(chaves.versao_do_usuario(TENANT, self.ana.iam_user_id),
                              versoes_a_subir(operacoes))
                break
        else:
            self.fail("o Watch não entregou a remoção")
