"""A rede de baixo do tratador de exceções — `nucleo/excecoes.py`.

**O que estes testes protegem.** Uma regra do banco recusando uma escrita é
comportamento correto; o que não pode é essa recusa chegar como **500 com página
de depuração**. O arquivo nasceu do `ProtectedError` (PDCA.1) e ganhou o
`IntegrityError` no [D133](../../docs/historico-correcoes.md) — o dono cadastrou
um item de contrato sem quantidade e recebeu um traceback de Django na tela.

**Estes testes são a rede, não a validação.** O caminho que importa é o
serializer dizendo *qual campo* na língua de quem preenche (isso é testado no
módulo dono). Aqui se prova que o caminho **que ninguém previu** — comando de
bancada, importação, constraint nova ainda não espelhada — termina em 4xx com o
nome da regra, e não em 500.
"""
from django.db.utils import IntegrityError
from django.test import TestCase
from rest_framework import status

from .excecoes import _nome_da_constraint, tratador


class _ViewFalsa:
    pass


def _contexto():
    return {"view": _ViewFalsa(), "request": None, "args": (), "kwargs": {}}


class NomeDaConstraintTests(TestCase):
    def test_extrai_a_REGRA_e_nao_a_tabela(self):
        """**Há dois pares de aspas na mensagem, e o primeiro é a tabela.**

        Pegar a primeira aspa devolve `modulopdca_itemcontrato` — que o suporte
        já sabe pela rota — em vez de `pdca_item_contrato_quantidade_positiva`,
        que é a informação que falta. A primeira escrita deste extrator fazia
        exatamente isso, e foi este teste que mostrou.
        """
        msg = (
            'new row for relation "modulopdca_itemcontrato" violates check '
            'constraint "pdca_item_contrato_quantidade_positiva"'
        )
        self.assertEqual(
            _nome_da_constraint(msg), "pdca_item_contrato_quantidade_positiva",
        )

    def test_extrai_de_uma_violacao_de_unicidade(self):
        msg = (
            'duplicate key value violates unique constraint '
            '"pdca_contrato_numero_unico_por_obra"'
        )
        self.assertEqual(
            _nome_da_constraint(msg), "pdca_contrato_numero_unico_por_obra",
        )

    def test_mensagem_sem_aspas_nao_quebra(self):
        self.assertEqual(_nome_da_constraint("erro sem aspas"), "")


class CheckConstraintVira400Tests(TestCase):
    """Violar uma regra de faixa é **dado do usuário fora do permitido** — 400."""

    def test_check_constraint_vira_400_com_a_regra_nomeada(self):
        exc = IntegrityError(
            'new row for relation "modulopdca_itemcontrato" violates check '
            'constraint "pdca_item_contrato_quantidade_positiva"\n'
        )
        resposta = tratador(exc, _contexto())
        self.assertIsNotNone(resposta)
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("regra de integridade", resposta.data["detail"])
        self.assertIn("regra", resposta.data)

    def test_a_mensagem_nao_inventa_qual_campo_errou(self):
        """**O tratador não sabe o campo, e não finge saber.**

        Ele vê o nome da constraint, não o formulário. Traduzir
        `pdca_item_contrato_quantidade_positiva` para "a quantidade está errada"
        acertaria neste caso e erraria no próximo — e uma mensagem específica e
        errada é pior que uma genérica e honesta. Quem diz o campo é o
        serializer, que tem os dados na mão.
        """
        exc = IntegrityError(
            'violates check constraint "pdca_contrato_vigencia_coerente"\n'
        )
        resposta = tratador(exc, _contexto())
        texto = resposta.data["detail"].lower()
        self.assertNotIn("quantidade", texto)
        self.assertNotIn("vigência", texto)


class UniqueViolationVira409Tests(TestCase):
    def test_duplicata_vira_409(self):
        """Conflito, e não erro de preenchimento: o valor está certo, só já
        pertence a outro registro."""
        exc = IntegrityError(
            'duplicate key value violates unique constraint '
            '"pdca_contrato_numero_unico_por_obra"\n'
        )
        resposta = tratador(exc, _contexto())
        self.assertEqual(resposta.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("único", resposta.data["detail"])


class OQueContinua500Tests(TestCase):
    """**O que NÃO é traduzido, e por quê.**

    FK inexistente e `NOT NULL` sem valor não são dado do usuário fora de faixa
    — são bug de quem escreveu o caminho. Devolver 400 os esconderia atrás de
    uma mensagem de formulário, e o defeito ficaria invisível até alguém
    reclamar de dado faltando.
    """

    def test_fk_violada_nao_vira_400(self):
        exc = IntegrityError(
            'insert or update on table "x" violates foreign key constraint "y"\n'
        )
        self.assertIsNone(tratador(exc, _contexto()))

    def test_not_null_nao_vira_400(self):
        exc = IntegrityError('null value in column "tenant_id" violates not-null\n')
        self.assertIsNone(tratador(exc, _contexto()))
