# backend/moduloprancheta/motores/__init__.py
"""Registry de motores — quem sabe converter o quê, e o que já está ligado.

**A separação que este pacote materializa:** `formatos.py` declara o
*vocabulário* (que motores existem, sob que licença, que formato cada um abre) e
`payment/planos.py` declara o *comercial* (que tiers o plano habilita). Nenhum
dos dois sabe se o motor está **implementado** — e essa é a terceira pergunta,
que só este pacote responde.

Ela importa porque a resposta honesta muda com ela. Um formato cujo motor é
vendido, habilitado pelo plano e **sem adaptador** não pode virar uma
`DerivadaProjeto` em `pendente`: ficaria pendurada para sempre, e "aguardando
conversão" viraria mentira permanente na tela. O `planejar()` só devolve o que
alguém sabe converter de fato, e o que sobra aparece declarado no
`GET /api/prancheta/status/` — dado honesto vale para a ausência também.

**Ordem de preferência é ordem de custo, não de qualidade.** `formatos.py` lista
o DWG como `("libredwg", "aps")`, e o pipeline usa o primeiro cujo tier o plano
habilita — ou seja, o **livre** ganha até para quem paga o premium. É de
propósito: a APS cobra por tradução (COGS), e queimar token num arquivo que o
motor livre abriria seria gastar o dinheiro do cliente sem entregar nada a mais.
O premium se paga onde importa — quando o livre levanta `MotorInsuficiente`,
é ali que a escalada da PRA.4 entra.
"""
from __future__ import annotations

from ..formatos import FORMATO_POR_CODIGO, MOTOR_POR_CODIGO
from .base import (
    Adaptador,
    ArquivoCorrompido,
    DesenhoVazio,
    ErroDeConversao,
    FalhaDoIntermediario,
    FalhaMotor,
    MotorIndisponivel,
    MotorInsuficiente,
    Parte,
    ReferenciaAusente,
    Retomada,
    Saida,
    SemPreviewEmbutido,
    TempoExcedido,
    VersaoNaoSuportada,
)
from .documento import MotorDocumento
from .dwg import MotorDwg
from .dxf import MotorDxf
from .ifc import MotorIfc

__all__ = [
    "Adaptador", "ErroDeConversao", "MotorInsuficiente", "MotorIndisponivel",
    "ArquivoCorrompido", "VersaoNaoSuportada", "TempoExcedido", "FalhaMotor",
    "FalhaDoIntermediario", "DesenhoVazio", "ReferenciaAusente",
    "SemPreviewEmbutido", "Parte", "Saida", "Retomada", "ADAPTADORES", "adaptador_de",
    "planejar", "estado_dos_motores",
]

#: Um adaptador por motor. `aps` (premium) chega na PRA.4; `gdal` e `pdal` são
#: dos módulos donos daquele dado (Maps e drone — planta §3), e a Prancheta os
#: **abre** sem convertê-los aqui: o seam é a PRA.7. Ausência aqui é declarada,
#: nunca silenciosa.
ADAPTADORES: dict[str, Adaptador] = {
    motor.codigo: motor
    for motor in (MotorDocumento(), MotorDxf(), MotorDwg(), MotorIfc())
}


def adaptador_de(codigo: str) -> Adaptador | None:
    return ADAPTADORES.get(codigo)


def planejar(codigo_formato: str, tiers: list[str] | set[str]) -> list[tuple[str, str]]:
    """`[(tipo_de_derivada, codigo_do_motor)]` que este plano consegue produzir.

    Vazio é resposta legítima e comum: KMZ, LAS e RVT passam por aqui sem gerar
    nada — os dois primeiros porque o dono do dado é outro módulo, o terceiro
    porque o motor dele ainda não existe. Quem explica o vazio para a tela é o
    `estado_dos_motores()`; inventar uma derivada aqui só para a lista não ficar
    vazia seria fabricar dado.
    """
    formato = FORMATO_POR_CODIGO.get(codigo_formato)
    if formato is None:
        return []

    tiers = set(tiers)
    for codigo_motor in formato.motores:
        motor = MOTOR_POR_CODIGO.get(codigo_motor)
        if motor is None or motor.tier not in tiers:
            continue
        adaptador = ADAPTADORES.get(codigo_motor)
        if adaptador is None or not adaptador.disponivel():
            continue
        return [(tipo, codigo_motor) for tipo in adaptador.tipos]
    return []


def estado_dos_motores() -> list[dict]:
    """O que cada motor declarado em `formatos.py` é hoje, de fato.

    Alimenta o `GET /api/prancheta/status/`. As três colunas respondem perguntas
    diferentes e é útil que não se confundam: `implementado` é "existe adaptador
    no código", `disponivel` é "a dependência está nesta imagem" e `versao` é o
    carimbo que invalida derivada por comparação. Um motor implementado e
    indisponível é problema de deploy; um não implementado é fatia futura.
    """
    saida = []
    for motor in MOTOR_POR_CODIGO.values():
        adaptador = ADAPTADORES.get(motor.codigo)
        versao = adaptador.versao() if adaptador else ""
        saida.append({
            "codigo": motor.codigo,
            "nome": motor.nome,
            "tier": motor.tier,
            "licenca": motor.licenca,
            "custo_por_traducao": motor.custo_por_traducao,
            "implementado": adaptador is not None,
            "disponivel": bool(versao),
            "versao": versao,
        })
    return saida
