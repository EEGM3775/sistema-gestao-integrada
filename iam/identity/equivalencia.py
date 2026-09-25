"""Token × PDP, pergunta por pergunta — a régua de "zero divergência" (§10.12).

A fase 2 sai quando o PDP responde **o mesmo** que o token para toda pergunta
que o backend faz. Este módulo guarda as duas metades dessa comparação num lugar
só, para que o teste da IAM (`testes/iam/identity/test_pdp.py`, com SpiceDB de
teste) e o comando de quem opera (`manage.py conferir_equivalencia`, contra o
PDP de verdade) meçam exatamente a mesma coisa:

- `pelo_token` é a decisão que o backend tomava a partir das claims
  (`nucleo/autorizacao._pelo_token`), sem o `is_superuser` do espelho local, que
  não é claim e vale igual nos dois;
- `lista_da_pessoa` é o que as tabelas dizem — o que o token carregava até a
  fase 4 e o que deixou de carregar. A régua compara o PDP com as tabelas, e não
  com o token, para continuar valendo depois que o token ficou enxuto;
- `no_pdp` traduz a pergunta para o objeto e a permissão do schema;
- `perguntas` é o universo: todo código do catálogo, todo módulo vendável e as
  duas perguntas de papel.
"""
from __future__ import annotations

from dataclasses import dataclass

import funcoesautorizacao
from funcoesautorizacao.cliente import ClienteSpiceDB, consistencia_total
from funcoesautorizacao.esquema import ID_PLATAFORMA, permissao_do_codigo, tipo_do_modulo

from . import catalog

#: Perguntas por ida ao PDP — o lote do `checkbulk`, janela de protocolo do
#: SpiceDB e não teto nosso (§5.6 do planos.py).
_LOTE = 100


def perguntas() -> list[tuple[str, str | None]]:
    return (
        [("codigo", p.code) for p in catalog.CATALOGO]
        + [("usa", m) for m in funcoesautorizacao.catalogo()["modulos_vendaveis"]]
        + [("administra", None), ("supervisiona", None)]
    )


def lista_da_pessoa(pessoa) -> dict:
    """As quatro listas que viajavam no token, lidas das tabelas da IAM."""
    return {
        "permissions": pessoa.permissoes_efetivas(),
        "modules": pessoa.modulos_efetivos(),
        "is_tenant_admin": pessoa.is_tenant_admin,
        "is_platform_admin": pessoa.is_superuser,
    }


def pelo_token(claims: dict, pergunta: tuple) -> bool:
    tipo, valor = pergunta
    if tipo == "administra":
        return bool(claims["is_tenant_admin"])
    if tipo == "supervisiona":
        return bool(claims["is_platform_admin"])
    if tipo == "usa":
        return valor in claims["modules"]
    return bool(claims["is_tenant_admin"]) or valor in claims["permissions"]


def no_pdp(pergunta: tuple, tenant_id: str) -> tuple[str, str, str]:
    tipo, valor = pergunta
    if tipo == "administra":
        return "empresa", tenant_id, "administra"
    if tipo == "supervisiona":
        return "plataforma", ID_PLATAFORMA, "supervisiona"
    if tipo == "usa":
        return tipo_do_modulo(valor), tenant_id, "usa"
    modulo = catalog.POR_CODIGO[valor].modulo
    return tipo_do_modulo(modulo), tenant_id, permissao_do_codigo(valor)


@dataclass
class Resultado:
    perguntas: int
    divergencias: list[str]


def divergencias(cli: ClienteSpiceDB, pessoa, claims: dict | None = None) -> Resultado:
    """Todas as perguntas de uma pessoa, com consistência total (o estado de agora)."""
    claims = claims if claims is not None else lista_da_pessoa(pessoa)
    tid = str(pessoa.tenant_id)
    universo = perguntas()
    itens = [no_pdp(p, tid) for p in universo]
    respostas: list = []
    for i in range(0, len(itens), _LOTE):
        respostas += cli.checar_em_lote(itens[i:i + _LOTE], str(pessoa.id), consistencia_total())
    saida = []
    for pergunta, pelo_pdp in zip(universo, respostas):
        if isinstance(pelo_pdp, Exception):
            saida.append(f"{pergunta}: PDP recusou ({pelo_pdp})")
        elif pelo_pdp != pelo_token(claims, pergunta):
            saida.append(f"{pergunta}: token={not pelo_pdp} pdp={pelo_pdp}")
    return Resultado(len(universo), saida)
