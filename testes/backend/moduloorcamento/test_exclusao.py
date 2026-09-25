"""Excluir orçamento — a trava protege a empresa, não tutela o usuário.

> **Decisão do dono, 13/09/2026:** *"Quero que a trava seja o limite para não
> atrapalhar o usuário em sua empresa, mas também não pode limitar o usuário: um
> orçamento que não pode ser usado também não pode atrapalhar o usuário de ter
> outro orçamento, já que a paywall limita quantidades."*

Duas metades, e o teste cobra as duas:

1. **o que rege a obra não sai** — o aprovado é base contratual;
2. **o que não rege nada sai** — e sempre há saída: nem o aprovado é beco sem
   saída, porque cancelar abre o caminho.

O achado que motivou não foi falta de trava — a trava existia. Foi ela ser a
**régua errada**: `perform_destroy` chamava `_exigir_editavel`, que é a regra da
*escrita* (só rascunho). O aprovado estava protegido, sim; o efeito colateral é
que **cancelado e superado também não saíam** — documentos mortos que o sistema
se recusava a deixar o usuário limpar.

Editar e excluir são réguas diferentes, e é essa a lição: um superado não aceita
escrita (é história de revisão) mas aceita exclusão (não rege nada). Reusar a
régua da escrita para a exclusão foi o que criou a armadilha.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from nucleo.models import Tenant, Usuario
from obras.models import Obra

from moduloorcamento.models import Orcamento
from moduloorcamento.planilha import proxima_versao


class BaseExclusao(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="orc-del", nome="Construtora Orç")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Residencial Del", endereco="Rua 1",
        )
        cls.usuario = Usuario.objects.create(
            username="orcamentista", tenant=cls.tenant, is_tenant_admin=True,
        )

    def setUp(self):
        # Camada 1 (entitlement de módulo) antes da camada 2 (permissão): sem o
        # `orcamento` em `iam_modules` o `RequireModule` barra com 403 e o teste
        # nunca chegaria a exercer a trava de status, que é o que ele existe
        # para cobrar.
        self.usuario.iam_modules = ["orcamento"]
        self.usuario.iam_permissions = []
        self.api = APIClient()
        self.api.force_authenticate(user=self.usuario)

    def _orcamento(self, status, versao):
        return Orcamento.objects.create(
            tenant=self.tenant, obra=self.obra, descricao=f"Planilha {versao}",
            versao=versao, status=status,
        )

    def _excluir(self, orcamento):
        return self.api.delete(f"/api/orcamento/orcamentos/{orcamento.pk}/")


class TravaTests(BaseExclusao):
    def test_aprovado_nao_sai_e_a_recusa_diz_o_caminho(self):
        """409, não 403: não falta permissão — o documento está em vigor."""
        orc = self._orcamento(Orcamento.Status.APROVADO, 1)

        resp = self._excluir(orc)

        self.assertEqual(resp.status_code, 409)
        self.assertIn("cancele-o primeiro", str(resp.data).lower())
        self.assertTrue(Orcamento.objects.filter(pk=orc.pk).exists())

    def test_o_aprovado_nao_e_beco_sem_saida(self):
        """A metade que separa trava de tutela: cancelar abre o caminho.

        É o cenário inteiro do dono — o usuário não fica preso a um documento
        que não serve mais, e não precisa de ninguém para se livrar dele.
        """
        orc = self._orcamento(Orcamento.Status.APROVADO, 1)
        self.assertEqual(self._excluir(orc).status_code, 409)

        orc.status = Orcamento.Status.CANCELADO
        orc.save(update_fields=["status"])

        self.assertEqual(self._excluir(orc).status_code, 204)
        self.assertFalse(Orcamento.objects.filter(pk=orc.pk).exists())

    def test_rascunho_cancelado_e_superado_saem(self):
        for i, status in enumerate(
            [Orcamento.Status.RASCUNHO, Orcamento.Status.CANCELADO,
             Orcamento.Status.SUPERADO],
            start=1,
        ):
            with self.subTest(status=status):
                orc = self._orcamento(status, i)
                self.assertEqual(self._excluir(orc).status_code, 204)


class LixeiraTests(BaseExclusao):
    def test_excluir_manda_para_a_lixeira_em_vez_de_apagar(self):
        orc = self._orcamento(Orcamento.Status.RASCUNHO, 1)

        self._excluir(orc)

        self.assertFalse(Orcamento.objects.filter(pk=orc.pk).exists())
        self.assertTrue(Orcamento.todos.filter(pk=orc.pk).exists())
        orc.refresh_from_db()
        self.assertIsNotNone(orc.excluido_em)

    def test_a_planilha_inteira_sobrevive_a_ida_para_a_lixeira(self):
        """Nada cascateia na exclusão — são 7 tabelas filhas esperando o purge."""
        from moduloorcamento.models import ItemOrcado

        orc = self._orcamento(Orcamento.Status.RASCUNHO, 1)
        item = ItemOrcado.objects.create(
            tenant=self.tenant, orcamento=orc, codigo_eap="1", descricao="Item",
        )

        self._excluir(orc)

        self.assertTrue(ItemOrcado.objects.filter(pk=item.pk).exists())

    def test_restaurar_devolve_o_orcamento_inteiro(self):
        from nucleo.lixo import item_de, restaurar

        orc = self._orcamento(Orcamento.Status.RASCUNHO, 1)
        self._excluir(orc)

        restaurar(item_de(orc), usuario=self.usuario)

        self.assertTrue(Orcamento.objects.filter(pk=orc.pk).exists())


class VersaoTests(BaseExclusao):
    def test_o_numero_da_versao_nao_e_reciclado_pela_lixeira(self):
        """Versão é identidade numa cadeia de revisão, não rótulo.

        Se `proxima_versao` lesse pelo gerente padrão (que filtra a lápide), a
        v3 na lixeira devolveria "3" de novo — e restaurar colidiria com o
        orçamento que nasceu no lugar dela. Pior: "v3" passaria a significar
        duas planilhas diferentes no histórico da obra.
        """
        self._orcamento(Orcamento.Status.RASCUNHO, 1)
        self._orcamento(Orcamento.Status.RASCUNHO, 2)
        terceiro = self._orcamento(Orcamento.Status.RASCUNHO, 3)

        self._excluir(terceiro)

        self.assertEqual(proxima_versao(self.obra.pk), 4)

    def test_restaurar_depois_de_criar_outro_nao_colide(self):
        """A consequência prática do teste acima, exercida ponta a ponta."""
        from nucleo.lixo import item_de, restaurar

        antigo = self._orcamento(Orcamento.Status.RASCUNHO, 1)
        self._excluir(antigo)

        novo = self._orcamento(Orcamento.Status.RASCUNHO, proxima_versao(self.obra.pk))
        self.assertEqual(novo.versao, 2)

        restaurar(item_de(antigo), usuario=self.usuario)
        self.assertEqual(Orcamento.objects.filter(obra=self.obra).count(), 2)
