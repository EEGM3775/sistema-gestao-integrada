# backend/nucleo/consumo.py
"""Quanto UMA operação custou de máquina — e por que a conta certa é difícil.

Irmão de [orcamento.py](orcamento.py): lá mora o teto, aqui mora o medidor. Os
dois vivem na fundação pelo mesmo motivo — o `funcoesimpexp` e a Prancheta fazem
trabalho pesado em processo compartilhado, e as duas perguntas ("cabe?" e "quanto
custou?") são a mesma grandeza vista de dois lados.

**O erro que este módulo existe para não cometer.** Todas as três medições de
recurso que este projeto já publicou mediram *outra coisa*, e sempre pela mesma
armadilha: um número **acumulado** lido como se fosse de um arquivo.

- **D76** — o `RLIMIT_AS` contava o processo inteiro, então o teto de 1.536 MB
  entregava ~384 MB reais à conversão;
- **D78** — o `RLIMIT_AS` herdado pelo subprocesso derrubava arquivos que
  convertiam, e a falha foi lida como limite do motor livre;
- **D82** — o `ru_maxrss` de `RUSAGE_CHILDREN` é **marca d'água de todos os
  filhos que o processo já teve**, e ainda conta as páginas que o filho recebeu
  do pai por copy-on-write no instante do `fork`. Provado com controle trivial:
  `subprocess.run(["/bin/true"])` reporta 14 MB com o pai pequeno e **1.714 MB**
  logo depois de o pai alocar 1,7 GB.

As três produziram conclusão de produto errada. Daí as duas regras deste arquivo:

1. **nada de marca d'água de processo.** O custo do pai sai de amostragem numa
   janela, com a linha de base subtraída; o custo do filho sai do `VmHWM` do
   **próprio filho**, lido no `/proc` dele enquanto ele vive — número que o
   `exec` zera, e que portanto é do programa que rodou, não do que o pai já
   tinha;
2. **número não medido não vira zero.** Quando o filho morre antes da primeira
   amostra, o campo sai `None` e `filho_medido` sai `False`. Zero se leria como
   "não custou nada", que é a mentira mais cara que um medidor pode contar.

**O cgroup é a resposta melhor, e é por isso que ele vem primeiro.** A regra 1
resolve a *atribuição*, mas não resolve a *cobertura*: amostrar a 50 ms perde o
pico que dura menos que isso, e foi assim que 76 dos 159 arquivos do acervo
saíram `n/d` — quase metade do corpus sem número. O kernel já mantém essa conta
sem amostrar: um cgroup v2 recém-criado tem `memory.peak` começando em zero, e
como o cgroup v2 **não migra as cobranças** de páginas que o processo já tinha,
o que ele acumula é exatamente a memória nova da janela — pai e subprocessos
juntos, sem linha de base para subtrair e sem herança de `fork` para descontar.
É a mesma grandeza que a amostragem persegue, medida por quem já a tem.

Os dois convivem de propósito e medem coisas diferentes:

| | o que responde | quem usa |
|---|---|---|
| `pico_cgroup_mb` | **quanto a máquina precisou ter** nesta operação, exato | dimensionamento do worker e `mem_limit` |
| `pico_filho_mb` / `pico_va_mb` | **onde** o custo aconteceu (subprocesso × em processo) | decidir qual metade otimizar |

**Ele é opt-in de deploy, e tem de ser.** Um cgroup por operação exige um
diretório `cgroup2` delegado e gravável, e sair procurando um por conta própria
faria o worker se mudar de cgroup sozinho num host que não pediu isso. Quem liga
é `SGI_CGROUP_MEDICAO`, apontando um cgroup preparado pelo host; sem ele, ou se
qualquer passo falhar, a janela cai na amostragem e diz isso em `fonte`. Ver
`deploy/compose/base.yml` no serviço `worker-conversao`.
"""
from __future__ import annotations

import itertools
import logging
import os
import resource
import threading
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

#: De quanto em quanto tempo o amostrador acorda. A 50 ms um pico instantâneo
#: pode escapar entre duas leituras — o que sai daqui é **piso** do pico, nunca
#: teto, e é assim que ele deve ser lido.
INTERVALO_PADRAO = 0.05

#: Variável de ambiente que liga o medidor por cgroup, apontando um diretório
#: `cgroup2` **delegado**: gravável por este processo e sem processos membros
#: (para o kernel deixar habilitar o controlador `memory` na subárvore dele).
#: Vazia = amostragem, que é o comportamento de sempre.
ENV_CGROUP = "SGI_CGROUP_MEDICAO"

#: Onde o processo **volta a ser** ao fim da janela, quando o caminho descoberto
#: pelo `/proc/self/cgroup` não é gravável mas existe um alias que é. É o caso do
#: container que recebe o próprio cgroup por bind rw num ponto de montagem
#: próprio: o kernel continua reportando o caminho namespaced (somente-leitura),
#: e só o deploy sabe o apelido. Vazia = usa o caminho descoberto.
ENV_CGROUP_ORIGEM = "SGI_CGROUP_ORIGEM"

#: Serializa a criação de cgroups de janela dentro do processo. Duas janelas
#: simultâneas na mesma thread group não podem existir — mover o processo para o
#: cgroup da segunda tiraria a primeira de baixo do próprio medidor —, e a que
#: chegar depois cai na amostragem em vez de corromper a que já está medindo.
_trava_cgroup = threading.Lock()
_sequencia = itertools.count(1)


def _escrever(caminho: str, texto: str) -> bool:
    """Grava numa pseudo-arquivo do cgroupfs. `False` em qualquer recusa.

    Sem exceção para o chamador de propósito: **todo** passo do caminho de cgroup
    é opcional, e o desfecho de qualquer falha é o mesmo — cair na amostragem.
    """
    try:
        with open(caminho, "w", encoding="ascii") as arquivo:
            arquivo.write(texto)
        return True
    except OSError:
        return False


def _monte_cgroup2() -> str:
    """Onde a hierarquia cgroup v2 está montada. `/sys/fs/cgroup` como padrão.

    Lido do `mountinfo` e não fixado: o caminho do `/proc/self/cgroup` é
    **relativo ao monte**, e concatenar os dois com o monte errado mandaria o
    processo de volta para um diretório que não existe — que é a única falha
    deste arquivo capaz de deixar o worker num cgroup órfão.
    """
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as arquivo:
            for linha in arquivo:
                campos = linha.split(" - ")
                if len(campos) == 2 and campos[1].split()[0] == "cgroup2":
                    return campos[0].split()[4]
    except (OSError, IndexError):
        pass
    return "/sys/fs/cgroup"


def _cgroup_atual() -> str | None:
    """O cgroup v2 deste processo, como caminho relativo à raiz da hierarquia.

    A linha do `/proc/self/cgroup` que interessa é a de controlador vazio
    (`0::/...`), que é como o v2 se apresenta; as linhas numeradas são v1 e não
    servem. É para cá que o processo **volta** no fim da janela, e por isso é
    lido no começo: sem o endereço de volta, não se sai.
    """
    try:
        with open("/proc/self/cgroup", encoding="ascii") as arquivo:
            for linha in arquivo:
                if linha.startswith("0::"):
                    return linha.strip().split("::", 1)[1]
    except OSError:
        pass
    return None


class _JanelaEmCgroup:
    """Um cgroup v2 descartável por operação — o pico exato, sem amostrar.

    O ciclo é `abrir()` → operação → `pico_mb()` → `fechar()`, e cada passo pode
    falhar sozinho sem levar a medição junto: `abrir()` devolve `False` e o
    chamador segue só com a amostragem.

    **Por que o processo se muda em vez de o cgroup vir até ele.** O que se quer
    medir é a janela, não o worker — e o worker é de vida longa, então o cgroup
    dele carrega o pico de tudo que já converteu (a marca d'água do D82, agora no
    kernel). Um cgroup novo por operação zera a conta, e o v2 **não recobra** as
    páginas que o processo já tinha ao entrar: o que sobe ali é alocação nova da
    janela, que é a definição de "quanto esta conversão custou".
    """

    def __init__(self, raiz: str) -> None:
        self.raiz = raiz
        self.caminho: str | None = None
        #: Diretório absoluto de onde o processo saiu — o endereço de volta.
        self.origem: str | None = None
        self._travado = False

    def abrir(self) -> bool:
        if not _trava_cgroup.acquire(blocking=False):
            # Já há uma janela medindo por cgroup neste processo. A de fora é a
            # dona; esta segue por amostragem.
            return False
        self._travado = True
        try:
            declarada = os.getenv(ENV_CGROUP_ORIGEM, "").strip()
            if declarada:
                self.origem = declarada.rstrip("/") or "/"
            else:
                relativo = _cgroup_atual()
                if relativo is None:
                    return self._desistir()
                self.origem = f"{_monte_cgroup2()}{relativo}".rstrip("/") or "/"
            # **O endereço de volta é testado ANTES da ida, e esta é a trava mais
            # importante do arquivo.** Escrever o próprio pid no cgroup onde já se
            # está é uma mudança nula que o kernel aceita — e que falha, com o
            # mesmo erro, quando o caminho de volta não é gravável. Sem este
            # teste, uma delegação montada fora do cgroup do container mede
            # certo, não consegue voltar, e **deixa o worker fora do cgroup dele
            # para sempre**: o `mem_limit` de 3 GB deixa de valer, e o freio que
            # só mata — o último da fila do §4.6 — simplesmente some. Medir bem
            # não vale perder o freio que protege a máquina.
            if not _escrever(f"{self.origem}/cgroup.procs", str(os.getpid())):
                logger.warning(
                    "medidor: cgroup de origem %s não é gravável; medindo por "
                    "amostragem para não deixar o processo fora dele", self.origem,
                )
                return self._desistir()
            # `+memory` na subárvore da raiz é o que faz `memory.peak` existir
            # nos filhos. Idempotente, e falha se a raiz tiver processos membros
            # — o host que delegou é quem tem de mantê-la vazia.
            _escrever(f"{self.raiz}/cgroup.subtree_control", "+memory")
            caminho = f"{self.raiz}/op-{os.getpid()}-{next(_sequencia)}"
            try:
                os.mkdir(caminho)
            except OSError:
                return self._desistir()
            self.caminho = caminho
            if not os.path.exists(f"{caminho}/memory.peak"):
                # Kernel sem `memory.peak` (< 5.19) ou controlador não habilitado.
                # Sem ele não há o que ler, e amostrar é melhor do que mudar o
                # processo de cgroup para nada.
                return self._desistir()
            if not _escrever(f"{caminho}/cgroup.procs", str(os.getpid())):
                return self._desistir()
            return True
        except Exception:  # pragma: no cover - defensivo; nada aqui deve subir
            logger.warning("medidor: cgroup indisponível, medindo por amostragem", exc_info=True)
            return self._desistir()

    def pico_mb(self) -> int | None:
        """`memory.peak` em MB, lido **antes** de o processo sair do cgroup."""
        if self.caminho is None:
            return None
        try:
            with open(f"{self.caminho}/memory.peak", encoding="ascii") as arquivo:
                return int(arquivo.read().strip()) // 1048576
        except (OSError, ValueError):
            return None

    def fechar(self) -> None:
        """Volta o processo para o cgroup de origem e remove o da janela.

        A ordem importa: `rmdir` de cgroup com processo membro dá `EBUSY`, então
        a mudança de volta vem primeiro. Se ela falhar, o diretório **fica** — um
        cgroup órfão é lixo visível, e remover à força não é possível de qualquer
        forma enquanto o processo estiver dentro.
        """
        try:
            if self.caminho is not None and self.origem is not None:
                voltou = _escrever(f"{self.origem}/cgroup.procs", str(os.getpid()))
                if voltou:
                    try:
                        os.rmdir(self.caminho)
                    except OSError:
                        logger.warning("medidor: cgroup %s ficou para trás", self.caminho)
                else:
                    logger.warning(
                        "medidor: processo não voltou ao cgroup %s; %s fica órfão",
                        self.origem, self.caminho,
                    )
        finally:
            self.caminho = None
            if self._travado:
                _trava_cgroup.release()
                self._travado = False

    def _desistir(self) -> bool:
        """Desfaz o que já foi feito e devolve `False` — sempre `False`."""
        if self.caminho is not None:
            try:
                os.rmdir(self.caminho)
            except OSError:
                pass
            self.caminho = None
        if self._travado:
            _trava_cgroup.release()
            self._travado = False
        return False


def _janela_em_cgroup() -> _JanelaEmCgroup | None:
    """A janela em cgroup, se o deploy pediu uma e ela abriu. `None` = amostrar."""
    raiz = os.getenv(ENV_CGROUP, "").strip()
    if not raiz or not os.path.isdir(raiz):
        return None
    janela = _JanelaEmCgroup(raiz)
    return janela if janela.abrir() else None


def _campos_do_status(pid: str | int, campos: tuple[str, ...]) -> dict[str, int]:
    """Lê linhas `Vm*`/`Ppid` do `/proc/<pid>/status`, em MB (kB no arquivo).

    Devolve só o que achou: processo que morreu no meio da leitura some sem
    exceção, que é o comportamento certo para um amostrador.
    """
    achados: dict[str, int] = {}
    try:
        with open(f"/proc/{pid}/status", encoding="ascii") as arquivo:
            for linha in arquivo:
                nome = linha.split(":", 1)[0]
                if nome in campos:
                    achados[nome] = int(linha.split()[1]) // 1024
                    if len(achados) == len(campos):
                        break
    except (OSError, ValueError, IndexError):
        pass
    return achados


def _memoria_do_processo_mb() -> tuple[int, int]:
    """`(VmSize, VmRSS)` deste processo em MB — `(0, 0)` fora do Linux.

    **`VmSize` primeiro porque é a grandeza que o orçamento governa.** O teto de
    uma operação é um `RLIMIT_AS`, que limita espaço de endereçamento virtual —
    não memória residente. Medir só o RSS responderia pergunta diferente da que o
    `RecursoExcedido` faz, e a conta com o teto não fecharia. O RSS vai junto
    porque é ele que diz quanta máquina a operação de fato ocupou, e os dois
    juntos separam "reservou muito" de "usou muito".
    """
    valores = _campos_do_status("self", ("VmSize", "VmRSS"))
    return valores.get("VmSize", 0), valores.get("VmRSS", 0)


def _filhos_de(pid: str | int) -> list[int]:
    """PIDs dos filhos vivos de `pid`, do `/proc/<pid>/task/<tid>/children`.

    Uma lista por *thread*, e não por processo: o subprocesso nasce da thread que
    o criou, e ler só `task/<pid>/children` perderia todo filho que uma thread
    trabalhadora tenha aberto.
    """
    filhos: list[int] = []
    try:
        for tid in os.listdir(f"/proc/{pid}/task"):
            try:
                with open(f"/proc/{pid}/task/{tid}/children", encoding="ascii") as arquivo:
                    filhos.extend(int(p) for p in arquivo.read().split())
            except (OSError, ValueError):
                continue
    except OSError:
        pass
    return filhos


def _descendentes(raiz: int, profundidade: int = 3) -> list[int]:
    """Filhos, netos e bisnetos vivos. Raso de propósito — o motor não aninha mais."""
    vistos: list[int] = []
    fronteira = [raiz]
    for _ in range(profundidade):
        proxima: list[int] = []
        for pai in fronteira:
            for filho in _filhos_de(pai):
                if filho not in vistos:
                    vistos.append(filho)
                    proxima.append(filho)
        if not proxima:
            break
        fronteira = proxima
    return vistos


def _cpu_acumulada_s() -> float:
    """CPU (user+sys) deste processo **e** dos filhos já colhidos, em segundos.

    Diferente do `ru_maxrss`, somar tempo de CPU acumulado e **subtrair** a base
    é aritmética legítima: tempo é contador que só cresce, então a diferença é
    exatamente o que se gastou na janela. Marca d'água não tem essa propriedade —
    é por confundir as duas que o D82 aconteceu.
    """
    try:
        eu = resource.getrusage(resource.RUSAGE_SELF)
        deles = resource.getrusage(resource.RUSAGE_CHILDREN)
    except (AttributeError, ValueError, OSError):  # pragma: no cover - Windows
        return 0.0
    return eu.ru_utime + eu.ru_stime + deles.ru_utime + deles.ru_stime


@contextmanager
def medir(intervalo: float = INTERVALO_PADRAO):
    """O custo de máquina **desta** operação. Rende um dict preenchido no fim.

    ```python
    with medir() as custo:
        converter(arquivo)
    derivada.memoria["custo"] = custo
    ```

    Campos, e o que cada um NÃO é:

    | Campo | O que é |
    |---|---|
    | `pico_cgroup_mb` | pico **exato** da janela (pai + subprocessos), do `memory.peak` do cgroup — `None` quando o deploy não delegou um |
    | `fonte` | `"cgroup"` ou `"amostragem"`: qual dos dois medidores produziu a janela |
    | `pico_va_mb` / `pico_rss_mb` | pico **deste processo na janela**, menos a base — não o pico do processo desde que ele subiu |
    | `pico_filho_mb` | maior `VmHWM` visto **em um** subprocesso, medido no `/proc` dele — não a marca d'água somada de todos (D82) |
    | `filho_medido` | `False` quando nenhum filho foi amostrado; aí `pico_filho_mb` é `None`, e não 0 |
    | `filhos` | quantos subprocessos distintos a janela viu |
    | `segundos` | relógio de parede |
    | `cpu_s` | CPU de verdade (pai + filhos colhidos), por diferença |

    **A amostragem continua rodando mesmo com o cgroup ligado**, e não é
    redundância: o `memory.peak` diz *quanto*, e só as colunas de amostragem
    dizem *onde* — subprocesso ou em processo. Quem decide o `mem_limit` é o
    primeiro; quem decide qual metade otimizar são as outras.

    **Um limite que muda a leitura:** quando o orçamento estoura, o pico gravado é
    o do momento da falha — o teto menos o que não coube. O arquivo exigiria mais
    do que aparece aqui, e é por isso que o relatório marca esses casos com `≥`.
    """
    custo: dict[str, object] = {
        "pico_cgroup_mb": None, "fonte": "amostragem",
        "pico_va_mb": 0, "pico_rss_mb": 0,
        "pico_filho_mb": None, "filho_medido": False, "filhos": 0,
        "segundos": 0.0, "cpu_s": 0.0,
    }
    janela = _janela_em_cgroup()
    base_va, base_rss = _memoria_do_processo_mb()
    base_cpu = _cpu_acumulada_s()
    eu = os.getpid()

    picos = [base_va, base_rss]
    #: `pid → maior VmHWM visto`. Por pid, e não um máximo global, para o
    #: relatório poder dizer "foram 3 subprocessos, o pior custou X" em vez de
    #: um número sem dono — que é a forma do achado que o D43 levou dias para
    #: desfazer.
    por_filho: dict[int, int] = {}
    parar = threading.Event()

    def _amostrar() -> None:
        while not parar.wait(intervalo):
            va, rss = _memoria_do_processo_mb()
            picos[0] = max(picos[0], va)
            picos[1] = max(picos[1], rss)
            for filho in _descendentes(eu):
                # `VmHWM` é o pico de RSS **daquele** processo, e o `exec` o
                # zera: o `dwg2dxf` nasce por fork+exec, então o número que se lê
                # aqui é do decodificador, sem as páginas que o pai tinha no
                # instante do fork. É essa distinção que o `ru_maxrss` não faz.
                marca = _campos_do_status(filho, ("VmHWM",)).get("VmHWM")
                if marca is not None:
                    por_filho[filho] = max(por_filho.get(filho, 0), marca)

    amostrador = threading.Thread(target=_amostrar, daemon=True, name="medidor-de-consumo")
    comeco = time.monotonic()
    amostrador.start()
    try:
        yield custo
    finally:
        parar.set()
        amostrador.join(timeout=1.0)
        if janela is not None:
            # Ler ANTES de fechar: `fechar()` tira o processo do cgroup e remove
            # o diretório, e depois disso não há `memory.peak` para ler.
            pico_cgroup = janela.pico_mb()
            janela.fechar()
            if pico_cgroup is not None:
                custo["pico_cgroup_mb"] = pico_cgroup
                custo["fonte"] = "cgroup"
        va, rss = _memoria_do_processo_mb()
        custo["segundos"] = round(time.monotonic() - comeco, 2)
        custo["cpu_s"] = round(max(0.0, _cpu_acumulada_s() - base_cpu), 2)
        custo["pico_va_mb"] = max(0, max(picos[0], va) - base_va)
        custo["pico_rss_mb"] = max(0, max(picos[1], rss) - base_rss)
        custo["filhos"] = len(por_filho)
        if por_filho:
            custo["pico_filho_mb"] = max(por_filho.values())
            custo["filho_medido"] = True
        # Sem `else`: o dict já nasce com `None`/`False`. Subprocesso curto demais
        # para cair numa amostra sai como **não medido**, e é a leitura honesta —
        # 0 aqui viraria "de graça" no relatório.
