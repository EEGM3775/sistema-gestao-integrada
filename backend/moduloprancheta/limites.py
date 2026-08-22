# backend/moduloprancheta/limites.py
"""O orçamento de uma conversão — memória e relógio, com erro legível no fim.

**Por que este arquivo existe.** Até a medição de 06/08/2026 a conversão não
tinha teto de recurso nenhum: os `TIMEOUT_SEGUNDOS` do `dwg.py` cobrem os
*subprocessos* (`dwg2dxf`, `dwgbmp`), e a metade cara — o `ezdxf` desenhando —
roda **em processo**, sem limite. Um DWG do acervo, com hachura de padrão fino
sobre área grande, expandiu para **62 GB de RAM**. O mesmo caminho roda em worker
compartilhado entre tenants e, em produção, em máquina paga: o custo de um upload
era ilimitado e imprevisível. Ver `D57`.

**Dois tetos, e a ordem entre eles é o desenho.** O Celery já sabe reciclar um
filho que passou de tanto RSS (`CELERY_WORKER_MAX_MEMORY_PER_CHILD`) e matar
task que passou do relógio — mas as duas coisas produzem *processo morto*, e
processo morto não explica nada a ninguém: a derivada ficaria presa em
`convertendo` e a tela do canteiro diria "aguardando" para sempre. Os tetos daqui
são **mais apertados de propósito**, para quem estoura primeiro ser o limite que
sabe transformar o estouro em `RecursoExcedido` — que é estado, motivo e frase na
tela. Os limites do Celery ficam como rede de segurança do que escapar daqui.

**O que este módulo NÃO faz:** decidir o que mostrar ao cliente. Ele só produz a
falha honesta. A degradação em camadas (miniatura embutida → render simplificado
→ folha completa) mora no motor e no pipeline, e é o que faz o teto virar uma
prancha pior em vez de prancha nenhuma.
"""
from __future__ import annotations

import signal
import threading
from contextlib import contextmanager

from django.conf import settings

from nucleo import orcamento as orcamento_da_plataforma

from .motores.base import RecursoExcedido


def _memoria_mb() -> int:
    return int(getattr(settings, "PRANCHETA_CONVERSAO_MEMORIA_MB", 0) or 0)


def _segundos() -> int:
    return int(getattr(settings, "PRANCHETA_CONVERSAO_SEGUNDOS", 0) or 0)


# **O mecanismo é o do `nucleo`, e não uma cópia daqui** (D76). Esta função foi
# o original — o D57 a escreveu para a conversão, e o D63 a promoveu à fundação
# quando o impexp precisou da mesma coisa. O que ficou para trás foi a cópia
# local, e ela divergiu no dia em que a fundação aprendeu a somar a linha de base
# do processo: o teto de 1536 MB entregava, aqui, ~384 MB reais de folga, porque
# o `worker-conversao` já nasce com 1152 MB de VA reservada.
#
# A **tradução** continua sendo daqui, e é por isso que não se importa o
# `orcamento()` inteiro: o `RecursoExcedido` da conversão é da taxonomia dos
# motores (`ErroDeConversao`), com `retentavel` e motivo próprios no cockpit — o
# da fundação é outra classe, e trocá-la mudaria a fila que o pipeline alimenta.
# Mecanismo compartilhado, vocabulário de cada módulo.
teto_de_memoria = orcamento_da_plataforma.teto_de_memoria


@contextmanager
def teto_de_relogio(segundos: int):
    """Interrompe o que passar do tempo, inclusive código rodando em processo.

    `SIGALRM` e não o `soft_time_limit` do Celery: o do Celery mata a **task**, e
    aqui o objetivo é o oposto — interromper só a conversão e deixar o `except`
    do pipeline gravar o motivo. O do Celery continua armado como rede.

    **Dois limites declarados:** o sinal só é entregue entre bytecodes, então
    chamada presa dentro de extensão C pode demorar a ceder (é o caso que o teto
    de memória cobre); e sinal só funciona na thread principal, então em pool de
    threads isto vira no-op — e é por isso que a checagem existe em vez de um
    `ValueError` no meio de uma conversão.
    """
    if (
        not segundos
        or not hasattr(signal, "SIGALRM")
        or threading.current_thread() is not threading.main_thread()
    ):
        yield
        return

    def _bateu(_sinal, _quadro):
        raise RecursoExcedido(
            f"A conversão passou de {segundos}s de processamento e foi "
            "interrompida. O arquivo continua disponível para download.",
            teto="relogio", segundos=segundos,
        )

    anterior = signal.signal(signal.SIGALRM, _bateu)
    signal.alarm(segundos)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, anterior)


@contextmanager
def orcamento_de_conversao(*, memoria_mb: int | None = None, segundos: int | None = None):
    """Os dois tetos juntos, traduzindo o estouro em `RecursoExcedido`.

    A tradução é a razão de este envelope existir: `MemoryError` cru subiria até
    o `except Exception` do pipeline e viraria `falha_motor` — "falha interna do
    motor" —, que acusa um defeito nosso onde houve um **limite** nosso. São
    coisas diferentes na fila do cockpit e na frase que o cliente lê.
    """
    memoria = _memoria_mb() if memoria_mb is None else memoria_mb
    tempo = _segundos() if segundos is None else segundos
    try:
        with teto_de_memoria(memoria), teto_de_relogio(tempo):
            yield
    except MemoryError as exc:
        raise RecursoExcedido(
            f"A conversão passou do limite de {memoria} MB de memória e foi "
            "interrompida. O arquivo continua disponível para download.",
            teto="memoria", memoria_mb=memoria,
        ) from exc
