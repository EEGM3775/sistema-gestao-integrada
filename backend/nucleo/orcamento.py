# backend/nucleo/orcamento.py
"""Orçamento de recurso de uma operação — memória e relógio, com erro legível.

**Promovido do `moduloprancheta/limites.py` (D57) para a fundação**, porque o
segundo consumidor apareceu: o parse de planilha do `funcoesimpexp` tem
exatamente o mesmo problema que a conversão de DWG teve — trabalho pesado, em
processo, sobre arquivo que **qualquer cliente sobe**, num worker compartilhado
entre tenants e, em produção, numa VM paga. A planta do impexp diz que o segundo
módulo a precisar da mesma coisa copia, e que a partir da cópia as duas versões
divergem; aqui a cópia seria de um guarda-corpo, e guarda-corpo divergente é o
tipo de defeito que só aparece no dia em que ele precisava funcionar.

**Dois tetos, e a ordem entre eles é o desenho.** O Celery sabe reciclar o filho
que passou de RSS e matar a task que passou do relógio, mas as duas coisas
produzem *processo morto* — e processo morto não explica nada a ninguém: a
operação fica pendurada e a tela mente "processando" para sempre. Os tetos daqui
são **mais apertados de propósito**, para quem estoura primeiro ser o limite que
sabe transformar o estouro em `RecursoExcedido` — que é estado, motivo e frase.
Os limites do Celery e o `mem_limit` do container ficam como rede do que escapar.

**Quem escolhe os números não é este arquivo.** Eles vêm de `payment/planos.py`,
por plano, e quem os resolve é o módulo que chama. Aqui mora só o mecanismo.
"""
from __future__ import annotations

import logging
import resource
import signal
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def _va_do_processo_mb() -> int:
    """Espaço de endereçamento virtual JÁ reservado por este processo, em MB.

    É a linha de base sobre a qual o orçamento é somado, e existe por uma medição
    (08/08/2026, [D76](../../docs/pendencias.md)): um worker Celery de vida longa
    chega a **1152 MB de VA** usando ~110 MB de memória real, e o gunicorn a
    **1491 MB** — tudo isso reservado por Django, psycopg2 e os leitores de
    planilha ANTES de qualquer orçamento ser armado. Armar `RLIMIT_AS` no valor
    cru do plano punha o teto abaixo do que o processo já tinha, e a primeira
    alocação seguinte falhava com arquivo de qualquer tamanho.

    `VmSize` do `/proc` é a mesma grandeza que o `RLIMIT_AS` governa — por isso a
    conta fecha. Fora do Linux (ou sem `/proc`) devolve 0, e o chamador cai no
    comportamento antigo: teto absoluto, que é o conservador.
    """
    try:
        with open("/proc/self/status", encoding="ascii") as arquivo:
            for linha in arquivo:
                if linha.startswith("VmSize:"):
                    return int(linha.split()[1]) // 1024  # kB → MB
    except (OSError, ValueError, IndexError):  # pragma: no cover - fora do Linux
        pass
    return 0


class RecursoExcedido(Exception):
    """A operação passou do orçamento — limite NOSSO, não defeito do arquivo.

    A distinção é a razão de a exceção existir com nome próprio: `MemoryError`
    cru sobe até o `except Exception` de quem chama e vira "falha interna", que
    acusa defeito onde houve **teto**. São frases diferentes para o cliente
    (uma pede upgrade, a outra pede desculpa) e filas diferentes no cockpit.
    """

    def __init__(self, mensagem: str, *, teto: str = "", **detalhes):
        super().__init__(mensagem)
        self.teto = teto
        self.detalhes = detalhes


@contextmanager
def teto_de_memoria(megabytes: int):
    """Faz a alocação além do teto virar `MemoryError` em vez de OOM do kernel.

    `RLIMIT_AS` limita o **espaço de endereçamento virtual**, que é o que o
    CPython consulta ao alocar: passando do teto, o `malloc` falha e o Python
    levanta `MemoryError` — exceção comum, que sobe pela pilha e vira motivo de
    erro. A alternativa (deixar o cgroup agir) mata o processo sem deixar rastro.

    **Limite honesto do mecanismo:** VA reservada não é memória usada.
    Alocadores e bibliotecas compiladas reservam faixas grandes sem tocá-las,
    então um teto muito baixo recusa operação que caberia. Por isso o número é
    comercial e folgado: ele existe para barrar a explosão, não para espremer.

    Sem `RLIMIT_AS` na plataforma (Windows de desenvolvimento) vira no-op
    silencioso — falhar alto aqui impediria rodar fora do container, e o teto
    que importa é o do servidor.

    **Só na thread principal**, pelo mesmo motivo do relógio e por um a mais:
    `RLIMIT_AS` é do PROCESSO, não da thread. Armá-lo dentro de um servidor com
    pool de threads estrangularia requisições vizinhas que ninguém orçou — e o
    estouro apareceria na operação errada. Onde o teto precisa valer (worker
    Celery e gunicorn com worker síncrono) o trabalho roda na principal.
    """
    if not megabytes or threading.current_thread() is not threading.main_thread():
        yield
        return

    try:
        anterior = resource.getrlimit(resource.RLIMIT_AS)
    except (AttributeError, ValueError, OSError):  # pragma: no cover - Windows
        yield
        return

    # **O orçamento é da OPERAÇÃO, e `RLIMIT_AS` é do PROCESSO** — somar a linha
    # de base é o que reconcilia os dois (D76). Sem isto, "512 MB" não queria
    # dizer "esta importação pode alocar 512 MB": queria dizer "este processo,
    # que já reservou 1,1 GB, não pode passar de 512 MB" — ou seja, nada.
    #
    # O teto continua sendo teto: quem estoura o orçamento leva `MemoryError` no
    # ponto da alocação e vira `RecursoExcedido`, com a frase certa. O que muda é
    # que agora o número publicado no plano é o que o cliente de fato recebe.
    #
    # A rede de baixo permanece e é ela que protege a máquina: `mem_limit` do
    # container mata antes de o host sofrer, e o `max-memory-per-child` do Celery
    # recicla o filho que incha. Este teto é o mais apertado dos três de
    # propósito — é o único que sabe dizer POR QUE parou.
    base_mb = _va_do_processo_mb()
    limite = (base_mb + megabytes) * 1024 * 1024

    teto_duro = anterior[1]
    if teto_duro != resource.RLIM_INFINITY:
        # Nunca subir acima do teto duro herdado: o kernel recusaria, e a
        # exceção mataria a operação por causa do próprio guarda-corpo.
        limite = min(limite, teto_duro)
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limite, teto_duro))
    except (ValueError, OSError):  # pragma: no cover - ambiente sem permissão
        # Ruidoso, pela lição do D21: guarda-corpo que não conseguiu se armar e
        # não diz nada fica indistinguível de um guarda-corpo funcionando — e
        # aqui o que segue sem teto é trabalho pesado sobre arquivo do cliente.
        logger.warning(
            "orcamento_memoria_nao_armado",
            extra={"orcamento_mb": megabytes, "base_mb": base_mb},
        )
        yield
        return
    try:
        yield
    finally:
        try:
            resource.setrlimit(resource.RLIMIT_AS, anterior)
        except (ValueError, OSError):  # pragma: no cover
            pass


@contextmanager
def teto_de_relogio(segundos: int, *, mensagem: str = ""):
    """Interrompe o que passar do tempo, inclusive código rodando em processo.

    `SIGALRM` e não o `soft_time_limit` do Celery: o do Celery mata a **task**, e
    aqui o objetivo é o oposto — interromper só a operação e deixar o `except` de
    quem chama gravar o motivo. O do Celery continua armado como rede.

    **Dois limites declarados:** o sinal só é entregue entre bytecodes, então
    chamada presa dentro de extensão C pode demorar a ceder (é o caso que o teto
    de memória cobre); e sinal só funciona na thread principal, então sob pool de
    threads — ou dentro de um request servido por thread — isto vira no-op. A
    checagem existe justamente para não levantar `ValueError` no meio do trabalho.
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
            mensagem or f"A operação passou de {segundos}s e foi interrompida.",
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
def orcamento(
    *,
    memoria_mb: int = 0,
    segundos: int = 0,
    mensagem_memoria: str = "",
    mensagem_relogio: str = "",
):
    """Os dois tetos juntos, traduzindo o estouro em `RecursoExcedido`.

    A tradução é a razão de o envelope existir, e o E2E da PRA.1d provou que ela
    não é detalhe: **`MemoryError` é `Exception`**, então qualquer `except
    Exception` no caminho o captura primeiro e o estouro chega ao chamador como
    "o motor quebrou" ou "o arquivo está corrompido" — acusando o arquivo do
    cliente por um limite nosso, e impedindo qualquer degradação que dependa de
    reconhecer o estouro. Quem usar isto e tiver `except Exception` no meio
    precisa deixar `RecursoExcedido` passar.
    """
    try:
        with teto_de_memoria(memoria_mb), teto_de_relogio(
            segundos, mensagem=mensagem_relogio,
        ):
            yield
    except MemoryError as exc:
        raise RecursoExcedido(
            mensagem_memoria
            or f"A operação passou do limite de {memoria_mb} MB de memória.",
            teto="memoria", memoria_mb=memoria_mb,
        ) from exc
