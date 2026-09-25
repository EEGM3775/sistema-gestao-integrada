# testes/backend/funcoesimpexp/test_ie3b_entrega.py
"""IE.3b — a porta única também é de saída.

O que se prova aqui é a **outra metade** da natureza `arquivo`: o binário que o
recurso guarda saindo pelo motor, com os guarda-corpos que a
`moduloprancheta/entrega.py` implementava sozinha. Como no `test_ie3_arquivo.py`,
não se reexercita o que já é coberto — a máquina de conferência não participa de
um download. O que estes testes cobrem é onde a saída de binário tem regra
própria:

1. a **régua invertida** — recurso de arquivo pode agora só entregar;
2. o **gate próprio** (`permissoes_entrega`), que é de leitura e não o do §3 —
   sem ele o `campo` da Prancheta perderia o visualizador;
3. os guarda-corpos de resposta: `nosniff`, `attachment`, tipo declarado por nós
   e cache que só promete o que a URL sustenta;
4. o **rastro declarado**: dado do cliente saindo vai para o `AuditLog` (R12/D67),
   derivada que nós geramos não.
"""
from __future__ import annotations

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied

from nucleo.models import AuditLog, Tenant, Usuario

from funcoesimpexp import entrega as motor_entrega
from funcoesimpexp.acesso import exigir_entrega
from funcoesimpexp.registro import (
    NATUREZA_ARQUIVO,
    RASTRO_AUDITADO,
    RASTRO_INTERNO,
    ArquivoEntregue,
    Coluna,
    EntregaInvalida,
    Recurso,
    RecursoInvalido,
)
from .tests import PERMS, ItemDeTeste

#: O "acervo" — caminho no storage por chave. Um FileField real exigiria um model
#: de teste e uma migration só para provar cabeçalho de resposta.
GUARDADOS: dict[str, str] = {}


class AcervoQueEntrega(Recurso):
    """Recurso de arquivo que **só entrega** — o caso que a régua antiga proibia."""

    id = "teste.entrega"
    rotulo = "Acervo que entrega"
    modulo = "teste"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = PERMS
    # O gate da saída é MENOR que o do §3, e é o ponto da fatia: quem abre o
    # desenho no canteiro tem leitura, não escrita.
    permissoes_entrega = (PERMS[0],)

    colunas = (Coluna("hash", "Hash", obrigatoria=True),)
    chave = "hash"

    def entregar_arquivo(self, especie: str, chave: str, tenant_id):
        caminho = GUARDADOS.get(f"{especie}:{chave}")
        if caminho is None:
            raise EntregaInvalida("Não encontrado neste tenant.")
        return ArquivoEntregue(
            campo=_Campo(caminho),
            nome="prancha da torre A.dwg",
            tipo="image/vnd.dwg",
            objeto=None,
            rastro=RASTRO_AUDITADO if especie == "revisao" else RASTRO_INTERNO,
            cache=motor_entrega.CACHE_IMUTAVEL if especie == "derivada" else "",
        )


class _Campo:
    """O mínimo de um `FileField` que a entrega toca: `open`, `size`, verdade."""

    def __init__(self, caminho: str):
        self.caminho = caminho

    def __bool__(self) -> bool:
        return bool(self.caminho)

    def open(self, modo="rb"):
        return default_storage.open(self.caminho, modo)

    @property
    def size(self) -> int:
        return default_storage.size(self.caminho)


# ---------------------------------------------------------------------------
# 1. A régua invertida
# ---------------------------------------------------------------------------


class ReguaDaEntregaTests(TestCase):
    def test_recurso_de_arquivo_que_so_entrega_e_valido(self):
        """O que a IE.3 recusava e a IE.3b passou a aceitar.

        Até 08/08/2026 o `validar()` dizia que exportar arquivo do acervo era a
        porta de leitura do módulo dono. A porta única passou a ser de entrada e
        de saída, e este é o teste que segura a inversão: sem ele, um refactor
        que "restaurasse" a regra antiga voltaria a expulsar a saída para os
        módulos, que é o estado do D75.
        """
        AcervoQueEntrega().validar()
        self.assertTrue(AcervoQueEntrega().entrega)
        self.assertFalse(AcervoQueEntrega().importa)

    def test_recurso_de_arquivo_que_so_entrega_dispensa_allowlist(self):
        """`formatos_arquivo` descreve o que ENTRA — quem só entrega não recebe nada."""
        self.assertEqual(AcervoQueEntrega().formatos_arquivo, ())

    def test_entregar_arquivo_em_recurso_de_linha_falha(self):
        """Recurso de linha não guarda binário: o que ele tem é o `queryset`."""
        class LinhaQueEntrega(ItemDeTeste):
            def entregar_arquivo(self, especie, chave, tenant_id):
                return None

        LinhaQueEntrega.id = "teste.linhaentrega"
        with self.assertRaisesMessage(RecursoInvalido, "natureza 'linha'"):
            LinhaQueEntrega().validar()

    def test_descrever_publica_a_entrega_separada_da_exportacao(self):
        """A tela escolhe gesto diferente para cada uma — um campo só as fundiria."""
        descrito = AcervoQueEntrega().descrever()
        self.assertTrue(descrito["entrega"])
        self.assertFalse(descrito["exporta"])


# ---------------------------------------------------------------------------
# 2. O gate próprio da saída
# ---------------------------------------------------------------------------


class _User:
    is_authenticated = True

    def __init__(self, permissoes=(), admin=False, modulos=()):
        self.iam_permissions = list(permissoes)
        self.iam_modules = list(modulos)
        self.is_tenant_admin = admin
        self.username = "u"


class GateDaEntregaTests(TestCase):
    def _com_modulo(self, permissoes):
        return _User(permissoes, modulos=["teste"])

    def test_quem_so_le_baixa_o_arquivo(self):
        """O caso que motivou `permissoes_entrega`.

        O `campo` da Prancheta tem `documento.view` e não tem `edit` — por
        desenho da PRA.3. Se a saída usasse o conjunto do §3 (que inclui a
        escrita, porque o recurso também importa o acervo histórico), abrir a
        prancha no canteiro passaria a dar 403: uma tela que funciona hoje
        fecharia por causa de uma regra escrita para a exportação tabular.
        """
        exigir_entrega(self._com_modulo([PERMS[0]]), AcervoQueEntrega())

    def test_quem_nao_tem_a_permissao_de_leitura_leva_403_nomeado(self):
        with self.assertRaisesMessage(PermissionDenied, PERMS[0]):
            exigir_entrega(self._com_modulo([]), AcervoQueEntrega())

    def test_sem_o_modulo_ninguem_baixa_nem_com_a_permissao(self):
        """Esta função substitui um `RequireModule` que valia para TODOS.

        Cobrar o entitlement só do privilegiado (como faz
        `exigir_entitlement_de_escrita`) deixaria a garantia por conta de um
        filtro que acontece na IAM, noutro serviço. Se um dia a claim vier larga,
        o acervo inteiro sai pela URL — o fail-open silencioso que a planta
        recusa.
        """
        with self.assertRaisesMessage(PermissionDenied, "contratado"):
            exigir_entrega(_User([PERMS[0]]), AcervoQueEntrega())

    def test_anonimo_nao_baixa(self):
        class Anon:
            is_authenticated = False

        with self.assertRaises(PermissionDenied):
            exigir_entrega(Anon(), AcervoQueEntrega())

    def test_admin_sem_o_modulo_nao_baixa_o_binario(self):
        """A assimetria com o D66, e ela é de propósito.

        Exportar tabular segue aberto ao admin depois do cancelamento
        (portabilidade). Baixar o binário do acervo não: ali o arquivo **é** o
        produto, e servi-lo a quem não assina é entregar a mercadoria. Sem esta
        checagem o `_privilegiado` passaria por cima do conjunto de permissões —
        o mesmo buraco que o D66 fechou do lado da entrada.
        """
        with self.assertRaisesMessage(PermissionDenied, "contratado"):
            exigir_entrega(_User([], admin=True), AcervoQueEntrega())

    def test_admin_com_o_modulo_baixa(self):
        exigir_entrega(_User([], admin=True, modulos=["teste"]), AcervoQueEntrega())

    def test_recurso_sem_gate_proprio_cai_no_conjunto_do_paragrafo_3(self):
        """Não declarar é herdar o conservador, nunca abrir."""
        class SemGateProprio(AcervoQueEntrega):
            permissoes_entrega = ()

        self.assertEqual(SemGateProprio().permissoes_da_entrega, PERMS)

    def test_recurso_de_fundacao_nao_cobra_modulo(self):
        """`entitlement = None` (o `maps.local`) não tem módulo a cobrar."""
        class Fundacao(AcervoQueEntrega):
            entitlement = None

        exigir_entrega(_User([PERMS[0]]), Fundacao())


# ---------------------------------------------------------------------------
# 3. Os guarda-corpos da resposta
# ---------------------------------------------------------------------------


class RespostaDaEntregaTests(TestCase):
    def setUp(self):
        self.caminho = default_storage.save(
            "impexp_teste/prancha.dwg", ContentFile(b"AC1015conteudo"),
        )
        self.addCleanup(default_storage.delete, self.caminho)
        self.entregue = ArquivoEntregue(
            campo=_Campo(self.caminho),
            nome="../../etc/prancha da torre.dwg",
            tipo="image/vnd.dwg",
        )

    def test_nunca_serve_como_pagina(self):
        """`nosniff` + `attachment` são guarda-corpo, não knob.

        Nenhum recurso pode pedir `inline`: o SVG que os nossos motores geram é
        documento executável, e um DXF com `<script>` no texto viraria XSS na
        nossa origem **depois** de passar pelo nosso próprio conversor.
        """
        resposta = motor_entrega.servir(self.entregue)
        self.addCleanup(resposta.close)
        self.assertEqual(resposta["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", resposta["Content-Disposition"])

    def test_o_nome_e_saneado_antes_de_virar_header(self):
        """Separador de caminho não é problema de codificação — é nome mentindo."""
        resposta = motor_entrega.servir(self.entregue)
        self.addCleanup(resposta.close)
        self.assertNotIn("..", resposta["Content-Disposition"])
        self.assertNotIn("/etc/", resposta["Content-Disposition"])
        self.assertIn("prancha da torre.dwg", resposta["Content-Disposition"])

    def test_o_tipo_vem_do_recurso_e_nao_do_nome(self):
        """Quem enviou não escolhe como o browser interpreta o próprio upload."""
        resposta = motor_entrega.servir(
            ArquivoEntregue(campo=_Campo(self.caminho), nome="x.html", tipo="image/vnd.dwg"),
        )
        self.addCleanup(resposta.close)
        self.assertEqual(resposta["Content-Type"], "image/vnd.dwg")

    def test_sem_cache_declarado_nao_promete_nada(self):
        """A lição do D51: `immutable` só é verdade se a URL identifica o conteúdo."""
        resposta = motor_entrega.servir(self.entregue)
        self.addCleanup(resposta.close)
        self.assertEqual(resposta["Cache-Control"], motor_entrega.CACHE_NENHUM)

    def test_cache_imutavel_quando_o_recurso_o_declara(self):
        resposta = motor_entrega.servir(
            ArquivoEntregue(
                campo=_Campo(self.caminho), nome="x.svg", tipo="image/svg+xml",
                cache=motor_entrega.CACHE_IMUTAVEL,
            ),
        )
        self.addCleanup(resposta.close)
        self.assertIn("immutable", resposta["Cache-Control"])

    def test_linha_sem_binario_nao_vira_500(self):
        """Derivada em erro, derivada convertendo, volume trocado — 404, não traceback."""
        with self.assertRaises(FileNotFoundError):
            motor_entrega.servir(ArquivoEntregue(campo=None, nome="x", tipo="text/plain"))


# ---------------------------------------------------------------------------
# 4. O rastro declarado
# ---------------------------------------------------------------------------


class RastroDaEntregaTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Acme", slug="acme-ie3b")
        self.user = Usuario.objects.create(username="ie3b", tenant=self.tenant)
        self.caminho = default_storage.save(
            "impexp_teste/rastro.dwg", ContentFile(b"AC1015x"),
        )
        self.addCleanup(default_storage.delete, self.caminho)

    def _entregar(self, rastro):
        # `objeto` faz o papel da linha do acervo (a revisão, a derivada). Aqui é
        # o `Usuario` porque o que a trilha precisa dele é só o `.tenant` — e todo
        # acervo real é `TenantScopedModel`, então a derivação é a mesma.
        motor_entrega.auditar(
            AcervoQueEntrega(),
            ArquivoEntregue(
                campo=_Campo(self.caminho), nome="p.dwg", tipo="image/vnd.dwg",
                objeto=self.user, rastro=rastro,
            ),
            usuario=self.user,
            especie="revisao",
        )

    def test_arquivo_do_cliente_saindo_entra_na_trilha(self):
        """R12/D67: exportação é O evento de LGPD, e o binário do cliente é dado."""
        self._entregar(RASTRO_AUDITADO)
        log = AuditLog.objects.get(acao=AuditLog.Acao.EXPORTAR_DADOS)
        self.assertEqual(log.detalhes["recurso"], "teste.entrega")
        self.assertTrue(log.detalhes["entrega"])

    def test_derivada_que_nos_geramos_nao_polui_a_trilha(self):
        """A mesma distinção que a R17 já faz na entrada: registro ≠ importação.

        Auditar o visualizador abrindo a nossa própria conversão encheria a
        trilha do D67 de "abriu uma prancha" e afogaria "levou a base de
        clientes", que é o evento para o qual ela existe.
        """
        self._entregar(RASTRO_INTERNO)
        self.assertFalse(AuditLog.objects.filter(acao=AuditLog.Acao.EXPORTAR_DADOS).exists())

    def test_a_trilha_nao_guarda_o_nome_do_arquivo(self):
        """`ARQ/laudo-fulano.pdf` é conteúdo — a trilha não recria o que a 9.C mascara."""
        self._entregar(RASTRO_AUDITADO)
        log = AuditLog.objects.get(acao=AuditLog.Acao.EXPORTAR_DADOS)
        self.assertNotIn("p.dwg", str(log.detalhes))
