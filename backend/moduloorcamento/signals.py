# backend/moduloorcamento/signals.py
"""O que o Orçamento faz quando a plataforma vai apagar uma obra de verdade.

Cliente do sinal `antes_de_purgar` do `nucleo/lixo.py` (D116).

**O impasse.** `Orcamento.obra` é `PROTECT` — de propósito: ninguém apaga uma
obra e leva junto, sem perceber, a planilha orçamentária que a empresa levou
semanas montando. Mas o dono decidiu que a lixeira esvazia em 15 dias, e uma obra
que tem orçamento **nunca** venceria esse prazo: toda varredura tentaria, o banco
recusaria, e ela ficaria na lixeira para sempre acumulando o custo que a decisão
dele queria justamente cortar.

**A saída, e por que ela não enfraquece o `PROTECT`.** O `PROTECT` continua
inteiro para todo caminho normal: excluir uma obra pela API não apaga orçamento
nenhum — agora nem apaga a obra, só marca a lápide. O que este receptor libera é
**um** caminho, e ele é o mais deliberado que existe na casa: alguém excluiu,
teve 15 dias para voltar atrás, não voltou, e a varredura chegou. Aí o orçamento
é parte da obra e vai com ela.

**Como reverter, se o dono discordar.** Apague este arquivo e tire o
`import` do `apps.py`. Nada quebra: a purga passa a ser **recusada** pelo banco,
o `nucleo/lixo.py` escreve o motivo em `Lixo.falha_na_purga`, e a obra fica
visível na lixeira dizendo por que não saiu. É por isso que aquele campo existe.
"""
from __future__ import annotations

import logging

from django.dispatch import receiver

from nucleo.lixo import antes_de_purgar
from obras.models import Obra

from .models import Orcamento

logger = logging.getLogger(__name__)


@receiver(antes_de_purgar, sender=Obra, dispatch_uid="orcamento_purga_com_a_obra")
def apagar_orcamentos_da_obra(sender, alvo, item, **kwargs):
    """Solta o `PROTECT` apagando os orçamentos da obra, na mesma transação.

    Roda **dentro** da transação da purga: se o `DELETE` da obra falhar depois
    disto por qualquer outro motivo, o orçamento volta junto. Não há janela em
    que a empresa fique sem o orçamento e com a obra.

    O que morre aqui morre por `CASCADE` do próprio orçamento — itens, revisões,
    composições adotadas. O que **não** morre é o que já é `SET_NULL` para a
    obra: título no ERP, nota fiscal, movimentação de estoque. Dinheiro que
    entrou ou saiu não é dado de projeto, e continua na contabilidade sem a obra
    — que é o desenho que o `moduloerp` já tinha antes desta fatia existir.
    """
    # `todos`, e não `objects`: desde que o `Orcamento` entrou na lixeira, o
    # gerente padrão filtra a lápide — e um orçamento que já estava na lixeira
    # ficaria de fora deste `DELETE`, mantendo de pé o `PROTECT` que ele existe
    # para soltar. A obra seria recusada na purga por causa de um documento que
    # o próprio usuário já tinha mandado para o lixo.
    apagados, _ = Orcamento.todos.filter(obra=alvo).delete()
    if apagados:
        logger.info(
            "orcamento_purgado_com_a_obra",
            extra={"obra_id": alvo.pk, "linhas": apagados},
        )
