# backend/clientes/vencimento.py
"""Onde o vencimento do carnê e do boleto encontra o calendário bancário.

`modulocalendar.dias_uteis` sabe **o que** é dia útil; este arquivo sabe **de
onde** vêm a UF e o município que definem os feriados de uma venda. São duas
responsabilidades, e separá-las é o que mantém o motor de cálculo
(`plano_pagamento`) puro: ele recebe um ajustador pronto e não conhece
empreendimento, banco nem feriado.

**A localidade é a do imóvel, não a do comprador.** O boleto de um lote em
Palhoça compensa pelo feriado de Palhoça, ainda que quem paga more em São Paulo:
quem define o dia é a praça do título. Por isso a UF sai de
`Empreendimento.estado` e nunca de `Cliente.estado`.

**O código IBGE vem do Maps.** `Empreendimento` guarda cidade e UF em texto, e
feriado municipal exige o código — nome de cidade não é chave (existem quatro
"Bom Jesus"). O `Local` do empreendimento já tem esse código: a cascata de
geocodificação o preenche (`modulomaps.services.completar_localidade`). Ler dali
é a integração entre módulos aparecendo onde ela vale dinheiro — e quando o
`Local` não existe ou ainda não resolveu o município, o ajuste segue com
nacional + estadual e **diz** que não conhece o municipal, em vez de fingir.
"""
from __future__ import annotations

from modulocalendar.dias_uteis import SEM_AJUSTE, AjusteDeVencimento


def localidade_do_empreendimento(empreendimento) -> tuple[str, str]:
    """`(uf, ibge)` do imóvel. Qualquer uma pode vir vazia — e vazia é honesta."""
    if empreendimento is None:
        return "", ""
    uf = (getattr(empreendimento, "estado", "") or "").upper()[:2]
    ibge = ""
    try:
        from modulomaps.models import Local

        local = (
            Local.objects.filter(empreendimento_id=empreendimento.pk)
            .exclude(ibge="")
            .values_list("ibge", "uf")
            .first()
        )
        if local:
            ibge = local[0] or ""
            uf = uf or (local[1] or "").upper()[:2]
    except Exception:  # pragma: no cover - Maps ausente não pode derrubar a venda
        # O Maps é fundação, mas um erro dele não pode impedir a emissão de um
        # carnê: sem município, o ajuste cai para nacional + estadual.
        ibge = ""
    return uf, ibge


def ajuste_do_empreendimento(empreendimento, *, ativo: bool = True) -> AjusteDeVencimento:
    """O ajustador de vencimento desta venda, pronto para injetar no motor."""
    if not ativo:
        return SEM_AJUSTE
    uf, ibge = localidade_do_empreendimento(empreendimento)
    # O vencimento é de banco: Carnaval e Corpus Christi também empurram.
    return AjusteDeVencimento(uf=uf, ibge=ibge, bancario=True)


def ajuste_da_aquisicao(aquisicao) -> AjusteDeVencimento:
    return ajuste_do_empreendimento(getattr(aquisicao, "empreendimento", None))


def ajuste_da_conta(conta) -> AjusteDeVencimento:
    """O ajustador de um título do ERP.

    A praça sai do empreendimento do título; quando ele não tem (título avulso,
    lançado à mão no financeiro), sai do da aquisição. Sem nenhum dos dois, o
    ajuste é só fim de semana + feriado nacional — que continua sendo melhor que
    um boleto vencendo no domingo.
    """
    empreendimento = getattr(conta, "empreendimento", None)
    if empreendimento is None:
        aquisicao = getattr(conta, "cliente_empreendimento", None)
        empreendimento = getattr(aquisicao, "empreendimento", None)
    return ajuste_do_empreendimento(empreendimento)
