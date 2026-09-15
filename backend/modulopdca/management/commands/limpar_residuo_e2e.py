"""Remove o resíduo que os E2E da PDCA.3 deixaram no ambiente.

**Por que este comando existe.** Os testes de ponta a ponta criavam obra,
contrato, medição e — na aprovação — **título no ERP**, e a faxina deles apagava
só a obra. Como a exclusão da obra é a lixeira (lápide, não `DELETE`), tudo o que
pendurava nela sobrevivia: em 15/09/2026 o ambiente de demonstração tinha 14
obras, 12 contratos, 6 medições e 3 `ContaPagar` de teste — e o dono esbarrou num
deles achando que era dado seu.

**A ordem das exclusões não é arbitrária**, e é o que torna isto um comando em
vez de um `delete()` no shell: `Medicao.contrato` e `ItemMedicao.item_contrato`
são `PROTECT`, e o `PedidoAprovacao` aponta para a medição por `ContentType`
(genérico, sem cascata). Apagar na ordem errada devolve `ProtectedError` no meio
e deixa metade do resíduo de pé.

Rodar:
    python manage.py limpar_residuo_e2e --confirmar
"""
from django.core.management.base import BaseCommand
from django.db import transaction

#: A marca que os testes deixam na **obra**. Nenhum dado real nasce com ela, e é
#: essa convenção que torna a limpeza segura.
PREFIXOS_OBRA = ("E2E ",)

#: Prefixos de **número de contrato**, só para o contrato órfão — aquele cuja
#: obra já foi apagada por outro caminho.
#:
#: **A regra principal não é esta**, e confiar nela foi um defeito: cada teste
#: novo inventa o seu prefixo (`E2E-`, `TELA-`, `FORM-`), e um que faltasse na
#: lista deixava o contrato de pé — que então **protegia a obra** (`ContratoObra.obra`
#: é `PROTECT`) e derrubava a limpeza inteira com um `ProtectedError`. O critério
#: que vale é o de baixo: contrato **de uma obra de teste** é resíduo, qualquer
#: que seja o número que alguém lhe deu.
PREFIXOS_CONTRATO = ("E2E-", "TELA-", "FORM-")


class Command(BaseCommand):
    help = "Remove obras, contratos, medições e títulos criados pelos testes E2E."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmar", action="store_true",
            help="Sem isto o comando apenas mostra o que apagaria.",
        )

    def handle(self, *args, **opcoes):
        from django.contrib.contenttypes.models import ContentType

        from modulopdca.models import (
            ContratoObra, ItemContrato, ItemMedicao, LiberacaoRetencao, Medicao,
        )
        from moduloerp.models import ContaPagar
        from nucleo.models import Atesto, Lixo, PedidoAprovacao
        from nucleo.tenancy import rls_bypass
        from obras.models import Obra

        seco = not opcoes["confirmar"]

        with rls_bypass():
            obras = [
                o for o in Obra.todos.all()
                if any(o.nome_obra.startswith(p) for p in PREFIXOS_OBRA)
            ]
            ids_obra = {o.pk for o in obras}
            # **A obra manda.** Todo contrato de uma obra de teste sai, qualquer
            # que seja o número — senão um prefixo esquecido deixa o contrato de
            # pé, e ele protege a obra (`PROTECT`), derrubando a limpeza inteira.
            # A lista de prefixos cobre só o órfão, cuja obra já se foi.
            contratos = [
                c for c in ContratoObra.todos.all()
                if c.obra_id in ids_obra
                or any(c.numero.startswith(p) for p in PREFIXOS_CONTRATO)
            ]
            medicoes = list(Medicao.todos.filter(contrato__in=contratos))
            liberacoes = list(LiberacaoRetencao.todos.filter(contrato__in=contratos))

            # Os títulos que a aprovação gerou. O seam é frouxo (id, sem FK),
            # então eles não morrem por cascata — é preciso colhê-los pelo id
            # que a medição guardou, antes de a medição sumir.
            ids_titulo = [
                m.conta_pagar_ref for m in medicoes if m.conta_pagar_ref
            ] + [
                liberacao.conta_pagar_ref for liberacao in liberacoes
                if liberacao.conta_pagar_ref
            ]

            self.stdout.write(
                f"obras: {len(obras)} · contratos: {len(contratos)} · "
                f"medições: {len(medicoes)} · liberações: {len(liberacoes)} · "
                f"títulos no ERP: {len(ids_titulo)}"
            )
            if seco:
                for c in contratos:
                    self.stdout.write(f"  contrato {c.numero} ({c.obra.nome_obra})")
                self.stdout.write(
                    self.style.WARNING("\nNada foi apagado. Use --confirmar.")
                )
                return

            with transaction.atomic():
                # 1. A escada, que aponta para a medição por ContentType.
                for modelo in (Medicao, LiberacaoRetencao):
                    ct = ContentType.objects.get_for_model(modelo)
                    alvos = [
                        m.pk for m in (medicoes if modelo is Medicao else liberacoes)
                    ]
                    pedidos = PedidoAprovacao.objects.filter(
                        alvo_tipo=ct, alvo_id__in=alvos,
                    )
                    Atesto.objects.filter(pedido__in=pedidos).delete()
                    pedidos.delete()

                # 2. As linhas filhas, depois os documentos (PROTECT acima).
                ItemMedicao.objects.filter(medicao__in=medicoes).delete()
                # `Medicao.retifica` é `PROTECT`: a retificadora **protege a
                # original**, que é exatamente o desenho — a correção não pode
                # apagar o documento que ela corrige. Soltar o vínculo é o único
                # jeito de apagar o par inteiro, e só faz sentido aqui, onde os
                # dois lados vão embora juntos.
                Medicao.todos.filter(
                    pk__in=[m.pk for m in medicoes], retifica__isnull=False,
                ).update(retifica=None)
                Medicao.todos.filter(pk__in=[m.pk for m in medicoes]).delete()
                LiberacaoRetencao.todos.filter(
                    pk__in=[liberacao.pk for liberacao in liberacoes]
                ).delete()
                ItemContrato.objects.filter(contrato__in=contratos).delete()

                # 3. O índice da lixeira — a lápide dos que foram "excluídos".
                for modelo, itens in ((ContratoObra, contratos), (Obra, obras)):
                    ct = ContentType.objects.get_for_model(modelo)
                    Lixo.objects.filter(
                        alvo_tipo=ct, alvo_id__in=[i.pk for i in itens],
                    ).delete()

                ContratoObra.todos.filter(
                    pk__in=[c.pk for c in contratos]
                ).delete()

                # 4. Os títulos no ERP, colhidos antes de a medição sumir.
                apagados = ContaPagar.todos.filter(pk__in=ids_titulo).delete()

                # 5. As obras, por último — e **pelo mesmo caminho da purga**.
                #
                # Apagar a obra direto esbarra no nó do D116:
                # `CalendarioTrabalho.obra` é `CASCADE` e `Cronograma.calendario`
                # é `PROTECT`, os dois entram na mesma fila de exclusão, e o
                # coletor do Django recusa o `DELETE` inteiro. O módulo já tem a
                # resposta — o receptor de `antes_de_purgar` em
                # `modulopdca/signals.py` —, e emiti-la aqui reusa essa resposta
                # em vez de escrever uma segunda que envelheceria em paralelo.
                from nucleo.lixo import antes_de_purgar

                from modulopdca.models import (
                    ApontamentoAvanco, Atividade, Cronograma,
                )

                for obra in obras:
                    antes_de_purgar.send(sender=Obra, alvo=obra, item=None)

                # E o plano de tempo, de baixo para cima. O **apontamento** é
                # `PROTECT` sobre a atividade de propósito (excluir a atividade
                # apagaria em silêncio o histórico de execução dela), então ele
                # sai primeiro — aqui, onde a obra inteira é resíduo de teste e
                # não existe histórico a preservar.
                planos = list(
                    Cronograma.objects.filter(obra__in=obras).values_list("pk", flat=True)
                )
                if planos:
                    ApontamentoAvanco.objects.filter(
                        atividade__cronograma_id__in=planos,
                    ).delete()
                    Atividade.objects.filter(cronograma_id__in=planos).delete()
                    Cronograma.objects.filter(pk__in=planos).delete()

                Obra.todos.filter(pk__in=[o.pk for o in obras]).delete()

        self.stdout.write(self.style.SUCCESS(
            f"Resíduo removido. Títulos apagados no ERP: {apagados}"
        ))
