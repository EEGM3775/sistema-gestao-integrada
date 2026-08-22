# backend/moduloprancheta/porta.py
"""PRA.5b — como a Prancheta **chama** a porta única, e traduz o que ela recusa.

A porta é uma só e é do `funcoesimpexp` ([entrada.py](../funcoesimpexp/entrada.py)).
O que este arquivo faz é o pedaço que sobra para quem atende HTTP, e que o
`admitir` documenta como contrato: *ele levanta exceção **comum**, e quem chama
traduz* — a mesma porta roda no worker, fora de HTTP, onde `APIException` não
significa nada.

**Por que isso virou arquivo em vez de ficar onde estava.** Na PRA.5a a tradução
nasceu dentro do serializer da revisão, que era o único chamador. A PRA.5b traz
mais dois (o snapshot do ponto de vista e o `importar-bcf`), e copiá-la para
cada um seria a **terceira e quarta cópia do mesmo guarda-corpo** — exatamente o
defeito que o [D75](../../docs/historico-correcoes.md) descreve do lado da entrada e o
[D75.1](../../docs/historico-correcoes.md) provou caro: quando as três recusas
saíam como 500, saíam nos três lugares de uma vez, porque a tradução estava em um
só. Um lugar para acertar, um lugar para errar.

**O que este módulo sabe e a porta genérica não:** onde fica a porta certa. A
recusa do motor é correta e genérica — *"este destino não recebe isto; aceita X,
Y, Z"* —, e para um arquivo que a plataforma reconhece essa lista é a resposta
errada: o cliente não mandou o arquivo errado, mandou o **certo na porta errada**.
Um `.bcfzip` no acervo pertence às marcações; um `.dwg` no importar-BCF pertence
ao acervo. A diferença entre "não aceitamos" e "não é aqui" é a diferença entre um
chamado de suporte e um clique.
"""
from __future__ import annotations

from rest_framework import serializers

from funcoesimpexp import entrada
from funcoesimpexp.limites import (
    ArquivoGrandeDemais,
    FormatoDesconhecido,
    FormatoNaoContratado,
)
from funcoesimpexp.registro import obter

from .entrega import RECURSO_ACERVO, RECURSO_MARCACAO
from .formatos import FORMATO_POR_CODIGO
from .planos import ArquivoAcimaDoTeto
from .planos import FormatoNaoContratado as FormatoNaoContratadoHTTP

#: Onde cada arquivo que a plataforma reconhece **deveria** ter entrado, dito na
#: voz de quem está na tela. O eixo é o `interop` do registry (§3 da planta):
#: formato de interoperabilidade carrega marcação sobre um desenho que já está
#: aqui; todo o resto É o desenho.
_ONDE_ELE_ENTRA = {
    RECURSO_ACERVO: (
        "suba-o como uma revisão do documento, no acervo da obra"
    ),
    RECURSO_MARCACAO: (
        "importe por 'marcações → importar BCF', dentro da revisão que ele comenta"
    ),
}


def porta_do_formato(codigo: str) -> str:
    """Qual dos dois recursos do módulo recebe este formato. `""` se nenhum sabe.

    Deriva do registry e não de uma segunda lista de propósito: um formato novo
    aparece na porta certa por já declarar o que é, sem ninguém lembrar de
    atualizar um mapa aqui.
    """
    formato = FORMATO_POR_CODIGO.get(codigo)
    if formato is None:
        return ""
    return RECURSO_MARCACAO if formato.interop else RECURSO_ACERVO


def _recusa(exc: FormatoDesconhecido, recurso_id: str) -> str:
    """A mensagem do 400, com o que só a Prancheta sabe acrescentar.

    Dois casos chegam aqui pela mesma exceção e merecem respostas diferentes:

    - a plataforma **não reconheceu** os bytes (`exc.formato is None`) — a
      mensagem do motor já é a certa, e não há endereço melhor a dar;
    - reconheceu, e **este destino não recebe** — aí há endereço, e dizê-lo é o
      ponto. Só quando a porta certa é *outra*: um formato reconhecido que este
      recurso também não recebe (um GeoTIFF nas marcações, digamos) cai na
      mensagem do motor, que lista o que passa.
    """
    formato = FORMATO_POR_CODIGO.get(exc.formato) if exc.formato else None
    if formato is None:
        return str(exc)
    destino = porta_do_formato(formato.codigo)
    if not destino or destino == recurso_id:
        return str(exc)
    return f"{formato.nome} não entra por aqui — {_ONDE_ELE_ENTRA[destino]}."


def admitir(arquivo, *, recurso_id: str, user, campo: str = "arquivo"):
    """Passa este arquivo pela porta única e devolve o que se sabe dele.

    Levanta, já no vocabulário do HTTP:

    - **402** `FormatoNaoContratado` / `ArquivoAcimaDoTeto` — parede comercial,
      com o formato, os aceitos e o teto no corpo, que é do que a tela monta o
      CTA. São as duas do módulo ([planos.py](planos.py)), reusadas para o corpo
      não divergir entre uma recusa vinda daqui e uma vinda do wizard do motor;
    - **400** `ValidationError` no campo que a tela enviou — não há o que
      comprar, e o campo importa: o snapshot chega em `snapshot` e o BCF em
      `arquivo`, e um erro pendurado no campo errado não aparece ao lado do
      seletor que o causou.
    """
    try:
        return entrada.admitir(arquivo, recurso=obter(recurso_id), user=user)
    except FormatoNaoContratado as exc:
        formato = FORMATO_POR_CODIGO.get(exc.formato)
        if formato is None:
            raise serializers.ValidationError({campo: str(exc)}) from exc
        raise FormatoNaoContratadoHTTP(
            formato=formato,
            aceitos=[c for c in exc.disponiveis if c in FORMATO_POR_CODIGO],
            plano=getattr(user, "iam_plano", None),
        ) from exc
    except ArquivoGrandeDemais as exc:
        raise ArquivoAcimaDoTeto(
            mensagem=str(exc), limite_mb=exc.limite_mb, tamanho_mb=exc.tamanho_mb,
        ) from exc
    except FormatoDesconhecido as exc:
        raise serializers.ValidationError({campo: _recusa(exc, recurso_id)}) from exc
