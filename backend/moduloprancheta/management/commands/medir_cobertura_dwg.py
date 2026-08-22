# backend/moduloprancheta/management/commands/medir_cobertura_dwg.py
"""Mede a cobertura real do motor livre de DWG — o número que decide o preço.

A planta §4.1 registra uma incerteza que **não se resolve lendo documentação**:
o LibreDWG declara ler r1.2–r2018 com ~99%, mas as fontes se contradizem sobre o
DWG 2024 (`AC1037`), e nenhuma delas fala dos DWGs que ESTA construtora tem. A
frase da planta é literal: *"a taxa de sucesso real sobre os DWGs do cliente é o
que define onde fica a fronteira entre os planos — se o motor livre cobrir pouco,
o degrau desce; se cobrir quase tudo, o premium fica só com RVT/NWD."*

Este comando é o instrumento dessa medição. Aponte-o para uma pasta de DWGs
reais e ele classifica cada arquivo, agrega por versão do DWG e imprime a taxa.
**Não grava nada** e não precisa de banco: é medição, não importação — rodar num
acervo de cliente não pode deixar rastro no acervo dele.

    manage.py medir_cobertura_dwg /caminho/dos/dwgs
    manage.py medir_cobertura_dwg /caminho --recursivo --amostra 7 \\
        --salvar-lista /saida/amostra.txt --preview --resgate

**Em lotes, um processo por lote** — a forma de medir um acervo grande sem que a
medição segure a memória de todos os arquivos até o fim (ver `_salvar_parcial`):

    manage.py medir_cobertura_dwg /caminho --lista amostra.txt \\
        --pular 0 --limite 10 --parcial /saida/lote-000.json
    ...                                    # um processo por lote
    manage.py medir_cobertura_dwg --consolidar /saida/lote-*.json

Os quatro baldes, e por que são quatro e não dois:

- **convertido** — o motor livre abriu. É o numerador da taxa.
- **acima_do_alcance** — versão que o motor livre declaradamente não alcança
  (`AC1037`). Recusado *antes* do subprocesso, pela leitura do cabeçalho. Não é
  fracasso do motor: é fronteira conhecida, e é o que a APS vende.
- **falhou_no_alcance** — versão dentro do alcance declarado e o motor não abriu
  assim mesmo. **Este é o balde que importa**: é a diferença entre o que o
  LibreDWG promete e o que ele entrega, e é o que uma leitura ingênua da
  documentação esconderia.
- **invalido** — não é DWG (cabeçalho ilegível). Sai da conta: mede o acervo do
  cliente, não o motor.

**A taxa sozinha engana, e a PRA.1b é a prova.** A primeira leitura (55%) foi
lida como limite tecnológico e teria posicionado a fronteira comercial em cima de
defeito nosso: das falhas, ~70% eram bugs deste repositório e ~12% arquivos sem
desenho dentro. Por isso o relatório separa a falha **por causa e por dono** (D42)
— quem resolve é o cliente comprando, quem enviou reenviando, nós consertando, ou
ninguém. Um número que não distingue isso é um número que precifica errado.

**A amostra tem de sobreviver ao relatório.** A remedição de 02/08 sorteou 1 em 7
com um script de rascunho e a lista se perdeu junto do scratchpad; sem ela, a
medição seguinte não é o mesmo corpus e a diferença não pode ser atribuída ao
conserto. Daí `--amostra` (determinística: a lista ordenada, um a cada N) e
`--salvar-lista`/`--lista`, que tornam a comparação repetível em vez de sortear
de novo.

**E o resultado também.** A remedição de 07/08 guardou a amostra e jogou fora o
veredito por arquivo: sobraram os baldes, e nenhum dos 11 que estouraram o
orçamento (D61) nem dos 21 cujo DXF ficou ilegível
([D43](../../../../docs/pendencias.md)) tinha nome em lugar algum. Desde a v2 do
parcial, cada lote grava a linha de cada arquivo — é o que separa um achado que é
lista de trabalho de um achado que é só um número.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
from collections import Counter, defaultdict
from contextlib import contextmanager

from django.core.management.base import BaseCommand, CommandError

from nucleo.consumo import medir

from payment.planos import (
    PRANCHETA_MEDICAO_TETO_SEGUNDOS,
    PRANCHETA_MEDICAO_TIMEOUT_RESGATE_SEGUNDOS,
    PRANCHETA_SUBPROCESSO_MEMORIA_MB,
)

from moduloprancheta import pipeline
from moduloprancheta.models import DerivadaProjeto
from moduloprancheta.motores.base import (
    ErroDeConversao,
    FalhaDoIntermediario,
    MotorIndisponivel,
    MotorInsuficiente,
    RecursoExcedido,
    executavel,
)
from moduloprancheta.motores.dwg import ALCANCE_LIVRE, MotorDwg, ler_versao_dwg

#: Quem age sobre cada causa de falha — a mesma pergunta da fila do cockpit
#: (§11 da planta), aplicada ao acervo inteiro em vez de a um tenant.
#:
#: `motor_insuficiente` é o ÚNICO que o motor premium resolve, e é por isso que a
#: fronteira comercial se lê nesta coluna e não na taxa crua.
DONO_DA_CAUSA = {
    "motor_insuficiente": "o cliente (comprando o motor premium)",
    "motor_indisponivel": "nós (deploy)",
    "referencia_ausente": "quem enviou (reenviar com os XREF)",
    "desenho_vazio": "ninguém (o arquivo não tem desenho)",
    "sem_preview": "ninguém (o CAD salvou sem miniatura)",
    "arquivo_corrompido": "o arquivo",
}
#: O resto (`falha_motor`, `tempo_excedido`, `versao_nao_suportada`) é nosso.
DONO_PADRAO = "nós (conserto de motor)"

#: Rótulo de causa para o que o `medir` decide antes de chamar o motor.
CAUSA_ACIMA = "versao_acima_do_alcance"

#: Teto de tempo do `dwg2SVG` no resgate. Mesmo número do `dwg2dxf`: os dois
#: decodificam o mesmo arquivo, e um teto menor faria o resgate "falhar" por
#: tempo em arquivo que só é grande.
TIMEOUT_RESGATE = PRANCHETA_MEDICAO_TIMEOUT_RESGATE_SEGUNDOS

#: Teto de tempo por arquivo, incluindo o render (D57). Default deliberadamente
#: presente: a medição de 06/08 ocupou a estação de quem a disparou porque a
#: SEGUNDA metade do caminho não tem limite — o `TIMEOUT_SEGUNDOS` do `dwg.py`
#: cobre só o subprocesso `dwg2dxf`, e o `ezdxf` desenha **em processo**. O teto
#: de 30 s que aparece no log é do próprio `ezdxf` e é **por hachura**, então uma
#: prancha com centenas delas multiplica sem limite superior.
TETO_POR_ARQUIVO = PRANCHETA_MEDICAO_TETO_SEGUNDOS


class EstourouOTeto(Exception):
    """O arquivo passou do teto desta medição — nosso limite, não do motor."""


@contextmanager
def teto_de_tempo(segundos: int):
    """Interrompe o que passar de `segundos`, inclusive código em processo.

    `SIGALRM` e não um timeout de subprocesso: o que estoura aqui é o **render**,
    que roda dentro deste processo. Limite declarado: o sinal só é entregue entre
    bytecodes, então uma chamada presa dentro de uma extensão C pode demorar a
    ceder — o que cobre o caso medido (laço de hachura em Python puro) e não
    promete o que não dá.

    Sem `SIGALRM` (Windows) o teto vira no-op silencioso; a medição roda em
    container Linux, e falhar alto aqui atrapalharia quem só quisesse listar.
    """
    if not segundos or not hasattr(signal, "SIGALRM"):
        yield
        return

    def _bateu(_sinal, _quadro):
        raise EstourouOTeto()

    anterior = signal.signal(signal.SIGALRM, _bateu)
    signal.alarm(segundos)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, anterior)


def _mb(valor: int | None) -> str:
    """`None` vira `n/d` — nunca `0`. A diferença é a lição inteira do D82."""
    return "n/d" if valor is None else str(valor)


@contextmanager
def medir_consumo(intervalo: float = 0.05):
    """Pico de memória e relógio **de um arquivo** — não do processo (D76/D82).

    Casca fina sobre [`nucleo.consumo.medir`](../../../nucleo/consumo.py), que é
    onde o mecanismo passou a morar quando o **pipeline de produção** precisou do
    mesmo número: o custo por arquivo deixou de ser coisa de medição de bancada e
    virou campo da derivada (`memoria["custo"]`), visível na tela de Conversões.
    Duas cópias do medidor divergiriam, e divergência aqui é conclusão de produto
    errada — foi assim três vezes (D76, D78, D82).

    **O que mudou em 12/08/2026, e é o D82.** O pico do subprocesso vinha de
    `getrusage(RUSAGE_CHILDREN).ru_maxrss`, que é marca d'água **acumulada de
    todos os filhos** e ainda conta as páginas que o filho herdou do pai por
    copy-on-write no `fork`. Seis arquivos de 1 a 9,6 MB apareceram com um
    "platô de 1.751–1.760 MB" na passada de custo — rodados crus, custam de 23 a
    230 MB. O número não era do filho: era o retrato do pai no instante do fork.
    Agora o filho é medido **por dentro**, pelo `VmHWM` do `/proc` dele, que o
    `exec` zera.

    As chaves antigas seguem no dicionário; `pico_filho_mb` passa a poder ser
    `None` (**não medido**, com `filho_medido: False`) em vez de um 0 que se leria
    como "não custou nada".

    **Limites declarados, porque eles mudam a leitura:**

    1. **pico mais curto que `intervalo` escapa.** A 50 ms, um estouro instantâneo
       pode passar entre duas leituras — o número é piso do pico, nunca teto;
    2. **quando o orçamento estoura, o pico medido é o do momento da falha**, que
       é o teto menos o que não coube. O arquivo exigiria mais do que aparece.
    """
    with medir(intervalo=intervalo) as consumo:
        yield consumo


#: Linhas que o LibreDWG cospe às centenas e que **nunca** são a causa da falha.
#:
#: Elas abrem o stderr, e é por isso que o corte pela **cabeça** (`nota[:120]`,
#: até 09/08/2026) devolvia sempre a mesma frase inútil: os três
#: `motor_insuficiente` da passada dos arquivos acima de 40 MB chegaram ao
#: relatório como `Warning: Unstable Class object 501 MATERIAL`, com o erro real
#: cortado fora. Um instrumento que descarta a causa transforma achado em número,
#: que é exatamente o que o [D43](../../../docs/historico-correcoes.md) levou
#: dias para desfazer.
RUIDO_DO_MOTOR = (
    "Warning:", "warning:", "skipping ", "Proxy graphic error",
    "Please post", "ERROR: Unstable Class",
)

#: Quanto do stderr sobrevive no parcial, por arquivo. Generoso de propósito: é
#: JSON em disco, e o custo de guardar 4 kB é nada perto do custo de remedir o
#: acervo para reconquistar uma frase que se tinha em mãos.
NOTA_MAX = 4000


def _resumo_do_erro(texto: str) -> str:
    """A linha que diz o que houve — e ela é a **última**, não a primeira.

    O LibreDWG escreve os avisos enquanto percorre o arquivo e o erro fatal no
    fim. Agrupar por `texto[:120]` juntava num balde só arquivos que falharam por
    motivos diferentes, porque todos começam igual.
    """
    linhas = [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]
    if not linhas:
        return ""
    uteis = [linha for linha in linhas if not linha.startswith(RUIDO_DO_MOTOR)]
    return (uteis or linhas)[-1][:200]


def _nota_do_arquivo(texto: str) -> str:
    """O stderr guardado no parcial — cabeça **e** cauda quando não cabe inteiro."""
    texto = (texto or "").strip()
    if len(texto) <= NOTA_MAX:
        return texto
    cabeca = 800
    cauda = NOTA_MAX - cabeca
    omitidos = len(texto) - NOTA_MAX
    return f"{texto[:cabeca]}\n…[{omitidos} caracteres omitidos]…\n{texto[-cauda:]}"


#: Elementos que contam como traço num SVG do `dwg2SVG`.
#:
#: **Não dá para reusar o `_tem_traco` do `dxf.py`** (que procura só `<path`):
#: aquele critério vale para o `SVGBackend` do ezdxf, que emite tudo como path,
#: inclusive o glifo do texto. O LibreDWG emite `<line>`, `<polyline>`, `<circle>`
#: e `<text>` também — e contar `<text>` como desenho faria uma folha que só tem
#: carimbo passar por prancha resgatada.
ELEMENTOS_DE_TRACO = (b"<path", b"<line", b"<polyline", b"<polygon", b"<circle", b"<ellipse")


class Command(BaseCommand):
    help = "Mede a taxa de sucesso do motor livre de DWG sobre arquivos reais."

    #: A amostra inteira desta medição, antes de `--pular`/`--limite` a
    #: recortarem em lote. É o que `--salvar-lista` grava.
    _corpus: list[str] = []

    #: Identifica o corpus entre lotes — ver `_escolher`.
    _corpus_hash: str = ""

    #: Versão do arquivo parcial. Existe para uma mudança futura de formato ser
    #: recusada alto, e não somada torto contra lotes antigos.
    #:
    #: **v2 (08/08/2026):** o parcial passou a guardar a linha **por arquivo**
    #: (`arquivos`), e não só os agregados. A passada de 07/08 rodou sem isso e o
    #: resultado é que os 11 arquivos do D61 e os 21 do D43 não têm nome em lugar
    #: nenhum — só o balde tem. O corpus estava versionado justamente para a
    #: amostra sobreviver ao relatório (D41); faltava a outra metade, que é o
    #: resultado por arquivo.
    #:
    #: A subida de versão também **impede somar as duas passadas**, e isso aqui é
    #: acerto e não efeito colateral: os lotes de 07/08 foram medidos quando o
    #: `RLIMIT_AS` media o processo inteiro (D76) e o teto de 1536 MB entregava
    #: ~384 MB reais. Somá-los com os de hoje seria a média de dois orçamentos.
    #:
    #: **v3 (09/08/2026):** cada arquivo passou a gravar `custo` (pico de VA, pico
    #: de RSS, relógio e bytes de entrada) e a `nota` deixou de ser cortada em 120
    #: caracteres **pela cabeça** — que devolvia o aviso e descartava o erro. As
    #: duas mudanças nasceram da mesma passada: a dos 10 arquivos acima de 40 MB
    #: mostrou que o degrau por tamanho não separa os baldes, e para trocá-lo por
    #: um critério de **custo** é preciso ter o custo — que o parcial media e
    #: jogava fora. Parciais v2 não somam com estes, e é correto: eles não têm a
    #: coluna.
    #:
    #: **v4 (12/08/2026, D82):** o `pico_filho_mb` mudou de grandeza. Era
    #: `getrusage(RUSAGE_CHILDREN).ru_maxrss` — marca d'água de **todos** os
    #: filhos, contando ainda as páginas herdadas do pai por copy-on-write no
    #: `fork` —, e passou a ser o `VmHWM` do **próprio subprocesso**, lido no
    #: `/proc` dele. Não é refinamento: é outra medida. Os seis arquivos de 1 a
    #: 9,6 MB que a passada de 12/08 relatou num "platô de 1.751–1.760 MB" custam,
    #: rodados crus, de 23 a 230 MB — o número era o retrato do pai, não do filho.
    #: Somar v3 com v4 misturaria as duas leituras numa faixa só, que é
    #: exatamente o que a versão do parcial existe para impedir. Junto vieram
    #: `cpu_s` e `filhos`, e o `None` que distingue **não medido** de zero.
    FORMATO_PARCIAL = 4

    def add_arguments(self, parser):
        parser.add_argument("pasta", nargs="?", default="",
                            help="Diretório com os arquivos .dwg "
                                 "(dispensável com --consolidar, que só soma)")
        parser.add_argument("--recursivo", action="store_true",
                            help="Desce nos subdiretórios")
        parser.add_argument("--detalhe", action="store_true",
                            help="Lista arquivo a arquivo, não só o agregado")
        parser.add_argument("--limite", type=int, default=0,
                            help="Para depois de N arquivos (amostragem)")
        parser.add_argument("--pular", type=int, default=0, metavar="N",
                            help="Começa no arquivo N+1. Com --limite, parte a "
                                 "medição em lotes que podem ser interrompidos "
                                 "entre um e outro sem refazer o anterior")
        parser.add_argument("--amostra", type=int, default=0, metavar="N",
                            help="Mede 1 a cada N arquivos da lista ordenada "
                                 "(determinístico — mesma pasta, mesma amostra)")
        parser.add_argument("--lista", default="", metavar="ARQUIVO",
                            help="Mede exatamente os caminhos deste arquivo "
                                 "(um por linha, relativos à pasta). Ignora --amostra")
        parser.add_argument("--salvar-lista", default="", metavar="ARQUIVO",
                            help="Grava a amostra medida, para a próxima medição "
                                 "rodar sobre o MESMO corpus")
        parser.add_argument("--preview", action="store_true",
                            help="Mede também o thumbnail embutido (dwgbmp, D49)")
        parser.add_argument("--resgate", action="store_true",
                            help="Nos que falharam, tenta o dwg2SVG (D43) e diz "
                                 "se ele desenha o que o nosso caminho não desenhou")
        parser.add_argument("--parcial", default="", metavar="ARQUIVO",
                            help="Grava o resultado DESTE lote em JSON, para "
                                 "`--consolidar` somar os lotes depois")
        parser.add_argument("--consolidar", nargs="+", default=[], metavar="PARCIAL",
                            help="Soma os parciais e imprime UM relatório do "
                                 "corpus. Não mede nada: recusa lotes de motor ou "
                                 "de corpus diferentes e denuncia buraco e "
                                 "sobreposição na cobertura")
        parser.add_argument("--teto-segundos", type=int, default=TETO_POR_ARQUIVO,
                            metavar="N",
                            help=f"Teto de tempo por arquivo, render incluído "
                                 f"(padrão {TETO_POR_ARQUIVO}s; 0 desliga). "
                                 "Sem ele uma prancha patológica ocupa a máquina "
                                 "indefinidamente — ver D57")

    def handle(self, *args, **opcoes):
        # Antes de tudo: consolidar não mede, então não exige pasta nem motor.
        # Somar os lotes numa máquina que não tem o LibreDWG é legítimo — o
        # trabalho caro já foi feito, e o que sobrou é aritmética.
        if opcoes["consolidar"]:
            return self._consolidar(opcoes["consolidar"])

        pasta = opcoes["pasta"]
        if not pasta:
            raise CommandError("Informe a pasta dos DWGs (ou use --consolidar).")
        if not os.path.isdir(pasta):
            raise CommandError(f"'{pasta}' não é um diretório.")

        motor = MotorDwg()
        versao = motor.versao()
        if not versao:
            # Falhar alto: uma medição que roda sem o motor produziria 0% e
            # alguém tomaria uma decisão de preço com esse número.
            raise CommandError(
                "O `dwg2dxf` (LibreDWG) não está disponível — a medição seria "
                "toda 'motor indisponível' e o resultado, sem sentido. Instale-o "
                "ou aponte LIBREDWG_DWG2DXF para o binário."
            )
        self.stdout.write(f"Motor: {versao}")

        # O `ezdxf` loga em INFO cada entidade que pula ("skipped entity
        # ATTRIB(#41B). Reason: invisible"). Numa conversão isolada é telemetria
        # útil; numa medição de centenas de arquivos são dezenas de milhares de
        # linhas afogando o relatório — que é o produto deste comando. Silenciado
        # só aqui, e só ele: um erro de verdade sobe pelo balde da classificação,
        # não pelo log.
        import logging

        logging.getLogger("ezdxf").setLevel(logging.ERROR)

        arquivos = self._escolher(pasta, opcoes)
        if not arquivos:
            raise CommandError("Nenhum arquivo .dwg encontrado.")
        self.stdout.write(f"Arquivos na medição: {len(arquivos)}")

        resgate = self._preparar_resgate(opcoes["resgate"])

        baldes = Counter()
        causas = Counter()
        por_versao: dict[str, Counter] = defaultdict(Counter)
        motivos = Counter()
        sinais = Counter()          # o que o conserto da PRA.1b explica
        previews = Counter()
        resgatados = Counter()

        # **A linha por arquivo, que o agregado não reconstrói.** Guardada sempre,
        # inclusive para quem converteu: é ela que permite a uma passada seguinte
        # dizer *quais* arquivos mudaram de lado, e não só que a taxa mudou.
        linhas: list[dict] = []

        teto = opcoes["teto_segundos"]
        for caminho in arquivos:
            # A janela de medida abraça a classificação inteira: o que ela inclui
            # a mais (ler a versão do DWG) custa um punhado de bytes, e o que ela
            # garante é que nenhum pedaço da conversão fique fora da conta.
            with medir_consumo() as consumo:
                balde, codigo, causa, nota, sinais_do_arquivo = self._classificar(
                    motor, caminho, sinais=sinais, teto=teto,
                )
            baldes[balde] += 1
            por_versao[codigo or "?"][balde] += 1
            if causa:
                causas[causa] += 1
            if nota:
                motivos[_resumo_do_erro(nota)] += 1
            linha = {
                "arquivo": os.path.relpath(caminho, pasta),
                "balde": balde,
                "versao": codigo,
                "causa": causa,
                "nota": _nota_do_arquivo(nota),
                "sinais": sinais_do_arquivo,
                # **O custo é dado de primeira classe, não anexo do erro.** Ele é
                # gravado para quem CONVERTEU também: a fronteira que se quer
                # desenhar é de custo de processamento, e ela precisa saber
                # quanto custa o que deu certo — sem isso só se conhece o preço
                # do fracasso. Ver `medir_consumo` para o que estes números não
                # cobrem.
                "custo": {
                    "pico_va_mb": consumo["pico_va_mb"],
                    "pico_rss_mb": consumo["pico_rss_mb"],
                    # **`None` = não medido**, e nunca 0 (D82). Desde 12/08/2026 o
                    # número é o `VmHWM` do próprio subprocesso, então ele não
                    # depende mais de `LOTE=1` para ser atribuível — o que ainda
                    # pode faltar é o filho que viveu menos que uma amostra.
                    "pico_filho_mb": consumo["pico_filho_mb"],
                    "filhos": consumo["filhos"],
                    "cpu_s": consumo["cpu_s"],
                    "segundos": consumo["segundos"],
                    "bytes": self._tamanho(caminho),
                },
            }
            if opcoes["preview"] and codigo:
                linha["preview"] = self._medir_preview(motor, caminho)
                previews[linha["preview"]] += 1
            if resgate and balde == "falhou_no_alcance":
                linha["resgate"] = self._tentar_resgate(resgate, caminho)
                resgatados[linha["resgate"]] += 1
            linhas.append(linha)
            if opcoes["detalhe"]:
                # Caminho relativo e não `basename`: o acervo tem subpastas
                # ("Anexos/…") e nomes que se repetem entre elas — o nome curto
                # sozinho não identifica o arquivo a ir buscar depois.
                custo = linha["custo"]
                self.stdout.write(
                    f"  {balde:18} {codigo or '??????':8} {causa:24} "
                    f"{custo['bytes'] / 1048576:7.1f}MB "
                    f"va={custo['pico_va_mb']:5}MB filho={_mb(custo['pico_filho_mb']):>5}MB "
                    f"{custo['segundos']:6.1f}s  {linha['arquivo']}"
                )

        self._salvar_lista(opcoes["salvar_lista"], pasta, self._corpus)
        self._salvar_parcial(
            opcoes["parcial"],
            motor=versao, pular=opcoes["pular"], medidos=len(arquivos),
            baldes=baldes, causas=causas, por_versao=por_versao,
            motivos=motivos, sinais=sinais, arquivos=linhas,
            previews=previews if opcoes["preview"] else None,
            resgatados=resgatados if resgate else None,
        )
        self._relatorio(baldes, causas, por_versao, motivos, sinais,
                        previews if opcoes["preview"] else None,
                        resgatados if resgate else None)
        if opcoes["detalhe"]:
            self._custo_por_arquivo(linhas)

    @staticmethod
    def _tamanho(caminho: str) -> int:
        """Bytes do arquivo de entrada — 0 se ele sumiu no meio da passada."""
        try:
            return os.path.getsize(caminho)
        except OSError:  # pragma: no cover - acervo em rede/nuvem
            return 0

    # -- escolha do corpus ---------------------------------------------------
    def _escolher(self, pasta: str, opcoes: dict) -> list[str]:
        """A lista a medir — e o motivo de ela ser reproduzível.

        Três caminhos, em ordem de precedência: uma lista salva (repete o corpus
        exato), a amostragem 1-em-N (determinística sobre a lista ordenada) ou a
        pasta inteira. `--limite` continua cortando no fim, para uma passada de
        teste não exigir escolher outro modo.
        """
        if opcoes["lista"]:
            encontrados = self._ler_lista(opcoes["lista"], pasta)
        else:
            encontrados = sorted(self._varrer(pasta, recursivo=opcoes["recursivo"]))
            passo = opcoes["amostra"]
            if passo > 1:
                # Um a cada N da lista ORDENADA — não um sorteio. Duas medições
                # da mesma pasta têm de produzir a mesma amostra, senão a
                # comparação antes/depois mistura conserto com sorte.
                encontrados = encontrados[::passo]

        # **O corpus é a amostra inteira, não o lote.** `--salvar-lista` grava
        # daqui: uma lista que registrasse só a janela faria a medição seguinte
        # comparar-se com um pedaço da anterior e chamar isso de "mesmo corpus".
        self._corpus = list(encontrados)
        # **A impressão digital do corpus, e por que ela precede os lotes.**
        # Medir em lotes só é a mesma medição se todos os lotes falarem do mesmo
        # corpus; dois lotes tirados de pastas diferentes somam para uma taxa que
        # não descreve acervo nenhum. O hash é sobre os caminhos RELATIVOS, pela
        # razão do `_salvar_lista`: o mesmo acervo é montado em pontos diferentes
        # no host e no container, e o absoluto acusaria diferença onde não há.
        self._corpus_hash = hashlib.sha256(
            "\n".join(os.path.relpath(c, pasta) for c in encontrados).encode("utf-8")
        ).hexdigest()[:16]

        # A janela vem DEPOIS da amostragem e vale também para a lista salva: é
        # o que permite medir o mesmo corpus em lotes, um de cada vez, sem que a
        # divisão em lotes mude quem está no corpus.
        encontrados = encontrados[opcoes.get("pular", 0):]
        limite = opcoes["limite"]
        return encontrados[:limite] if limite else encontrados

    def _varrer(self, pasta: str, *, recursivo: bool) -> list[str]:
        encontrados: list[str] = []
        for raiz, _dirs, nomes in os.walk(pasta):
            for nome in nomes:
                if nome.lower().endswith(".dwg"):
                    encontrados.append(os.path.join(raiz, nome))
            if not recursivo:
                break
        return encontrados

    def _ler_lista(self, caminho_lista: str, pasta: str) -> list[str]:
        try:
            with open(caminho_lista, encoding="utf-8") as arquivo:
                relativos = [l.strip() for l in arquivo if l.strip()]
        except OSError as exc:
            raise CommandError(f"Não consegui ler a lista: {exc}") from exc

        arquivos, ausentes = [], []
        for relativo in relativos:
            completo = os.path.join(pasta, relativo)
            (arquivos if os.path.exists(completo) else ausentes).append(completo)
        if ausentes:
            # Sem silêncio: uma lista que perdeu arquivos mede outro corpus, e é
            # exatamente essa diferença que invalidaria a comparação.
            self.stdout.write(self.style.WARNING(
                f"  {len(ausentes)} arquivo(s) da lista não estão na pasta — "
                "o corpus NÃO é idêntico ao da medição anterior."
            ))
        return arquivos

    def _salvar_lista(self, destino: str, pasta: str, arquivos: list[str]) -> None:
        """Grava a amostra em caminhos **relativos** à pasta.

        Relativo e não absoluto porque o corpus é montado em lugares diferentes a
        cada medição (pasta de trabalho no host, ponto de montagem no container),
        e uma lista de caminhos absolutos só serviria na máquina que a escreveu —
        que é como a amostra de 02/08 se perdeu.
        """
        if not destino:
            return
        try:
            with open(destino, "w", encoding="utf-8") as arquivo:
                for caminho in arquivos:
                    arquivo.write(os.path.relpath(caminho, pasta) + "\n")
        except OSError as exc:
            raise CommandError(f"Não consegui salvar a lista: {exc}") from exc
        self.stdout.write(f"Amostra salva em {destino} ({len(arquivos)} arquivos)")

    # -- medição em lotes ----------------------------------------------------
    def _salvar_parcial(self, destino: str, *, motor: str, pular: int,
                        medidos: int, baldes, causas, por_versao, motivos,
                        sinais, arquivos, previews, resgatados) -> None:
        """Grava o resultado de UM lote, para a soma vir depois.

        **O motivo de o lote existir é a memória, não o tempo.** Uma passada
        única sobre o corpus inteiro segura num só processo tudo o que o `ezdxf`
        e as extensões C alocaram: o RSS não volta ao sistema operacional só
        porque o Python liberou o objeto. Medindo em lotes, cada um num processo
        próprio, o fim do lote **devolve a memória ao host** — que é a diferença
        entre uma medição que ocupa a estação por horas e uma que a ocupa por
        minutos de cada vez, e pode ser interrompida entre um lote e outro.

        O preço disso é que cada lote conhece só o próprio pedaço, e a taxa que
        interessa é a do corpus. Daí o par com `--consolidar`.

        **E o parcial guarda `arquivos`, não só as somas** (v2). Um agregado
        responde *quantos* e nunca *quais*: depois da passada de 07/08, saber que
        11 arquivos estouraram o orçamento não bastou para ir buscá-los — a
        investigação seguinte começaria remedindo o acervo só para reencontrar a
        amostra. A linha por arquivo custa alguns KB por lote e é o que torna
        cada achado (D43, D61) uma lista de trabalho em vez de um número.
        """
        if not destino:
            return
        conteudo = {
            "versao_formato": self.FORMATO_PARCIAL,
            "motor": motor,
            "corpus_hash": self._corpus_hash,
            "corpus_total": len(self._corpus),
            "janela": {"pular": pular, "medidos": medidos},
            "baldes": dict(baldes),
            "causas": dict(causas),
            "por_versao": {k: dict(v) for k, v in por_versao.items()},
            "motivos": dict(motivos),
            "sinais": dict(sinais),
            "arquivos": arquivos,
            "previews": dict(previews) if previews is not None else None,
            "resgatados": dict(resgatados) if resgatados is not None else None,
        }
        try:
            with open(destino, "w", encoding="utf-8") as arquivo:
                json.dump(conteudo, arquivo, ensure_ascii=False, indent=2)
        except OSError as exc:
            raise CommandError(f"Não consegui salvar o parcial: {exc}") from exc
        self.stdout.write(f"Parcial salvo em {destino}")

    def _consolidar(self, caminhos: list[str]) -> None:
        """Soma os lotes e imprime UM relatório — recusando o que não soma.

        Três recusas, e nenhuma é preciosismo: somar lotes de **motores**
        diferentes mede a média de dois motores; somar lotes de **corpus**
        diferentes produz uma taxa que não descreve acervo nenhum; e somar uma
        cobertura com **buraco** entrega uma taxa sobre menos arquivos do que se
        pensa — que é exatamente o erro que a remedição de 02/08 não pôde evitar,
        quando a lista da amostra se perdeu.

        Buraco e sobreposição são **avisados**, não fatais: um lote que morreu no
        meio é situação real, e é melhor ler a taxa parcial sabendo que ela é
        parcial do que não ter número nenhum.
        """
        parciais = []
        for caminho in caminhos:
            try:
                with open(caminho, encoding="utf-8") as arquivo:
                    parciais.append((caminho, json.load(arquivo)))
            except OSError as exc:
                raise CommandError(f"Não consegui ler '{caminho}': {exc}") from exc
            except json.JSONDecodeError as exc:
                # Lote interrompido no meio da escrita: dizer qual, porque o
                # conserto é rodar aquela janela de novo, não a medição inteira.
                raise CommandError(
                    f"'{caminho}' não é um parcial legível ({exc}) — rode a "
                    "janela dele de novo."
                ) from exc

        for caminho, dados in parciais:
            if dados.get("versao_formato") != self.FORMATO_PARCIAL:
                raise CommandError(
                    f"'{caminho}' é de outro formato de parcial "
                    f"(v{dados.get('versao_formato')} ≠ v{self.FORMATO_PARCIAL}) — "
                    "remeça a janela dele. Lote antigo não é só formato velho: o "
                    "v1 foi medido antes do D76, quando o orçamento de memória "
                    "media o processo inteiro, e somá-lo daria a média de dois "
                    "orçamentos diferentes."
                )

        motores = {d["motor"] for _, d in parciais}
        if len(motores) > 1:
            raise CommandError(
                f"Os lotes foram medidos por motores diferentes ({', '.join(sorted(motores))}) "
                "— a soma seria a média de dois motores."
            )
        corpus = {d["corpus_hash"] for _, d in parciais}
        if len(corpus) > 1:
            raise CommandError(
                "Os lotes não são do mesmo corpus — a taxa somada não "
                "descreveria acervo nenhum."
            )

        baldes, causas, motivos, sinais = Counter(), Counter(), Counter(), Counter()
        por_versao: dict[str, Counter] = defaultdict(Counter)
        previews, resgatados = Counter(), Counter()
        linhas: list[dict] = []
        tem_preview = tem_resgate = False
        todo_preview = todo_resgate = True
        for _caminho, dados in parciais:
            linhas.extend(dados.get("arquivos") or [])
            baldes.update(dados["baldes"])
            causas.update(dados["causas"])
            motivos.update(dados["motivos"])
            sinais.update(dados["sinais"])
            for codigo, contagem in dados["por_versao"].items():
                por_versao[codigo].update(contagem)
            if dados["previews"] is None:
                todo_preview = False
            else:
                tem_preview = True
                previews.update(dados["previews"])
            if dados["resgatados"] is None:
                todo_resgate = False
            else:
                tem_resgate = True
                resgatados.update(dados["resgatados"])

        total = parciais[0][1]["corpus_total"]
        self.stdout.write(f"Motor: {motores.pop()}")
        self.stdout.write(
            f"Lotes somados: {len(parciais)} · corpus de {total} arquivos"
        )
        self._conferir_cobertura([d["janela"] for _, d in parciais], total)

        # Um balde medido só em parte dos lotes é pior que ausente: pareceria uma
        # contagem do corpus. Aparece, mas dizendo sobre o que ele fala.
        if tem_preview and not todo_preview:
            self.stdout.write(self.style.WARNING(
                "  Nem todo lote rodou com --preview: a miniatura abaixo é só "
                "dos lotes que rodaram."
            ))
        if tem_resgate and not todo_resgate:
            self.stdout.write(self.style.WARNING(
                "  Nem todo lote rodou com --resgate: o resgate abaixo é só "
                "dos lotes que rodaram."
            ))

        self._relatorio(baldes, causas, por_versao, motivos, sinais,
                        previews if tem_preview else None,
                        resgatados if tem_resgate else None)
        self._custo_por_arquivo(linhas)
        self._nomear_arquivos(linhas)

    def _custo_por_arquivo(self, linhas: list[dict]) -> None:
        """O que cada arquivo custou — a coluna que sustenta uma fronteira de custo.

        **Existe porque a fronteira por tamanho caiu** (09/08/2026): 87,2 MB
        converteu e quatro arquivos de 62–65 MB estouraram o orçamento, então
        nenhum corte em MB separa os baldes. Trocar o eixo exige ver o custo ao
        lado do peso — que é o que esta seção imprime, e o que o parcial v3 grava.

        Imprime o **pico de VA**, que é a grandeza do `RLIMIT_AS`, e mostra o
        peso em disco na coluna vizinha justamente para o divórcio entre os dois
        ficar visível sem ninguém precisar cruzar planilha.
        """
        com_custo = [linha for linha in linhas if linha.get("custo")]
        if not com_custo:
            return  # parcial v2, ou lote medido antes desta fatia

        # **O custo de um DWG é a soma de duas metades que estouram em lugares
        # diferentes**: o `dwg2dxf` (filho) e o `ezdxf` (este processo). Somar as
        # duas numa coluna só esconderia justamente o que o D78 mostrou —
        # arquivo que custa tudo no filho e nada aqui.
        def _pico(linha: dict) -> int:
            # `pico_filho_mb` pode ser `None` (não medido, D82) — e `None` não é
            # comparável com `int`. Tratar como 0 **aqui** é correto e não repete
            # o erro: é o argumento do `max`, não o número publicado; quem publica
            # imprime `n/d`, logo abaixo.
            return max(linha["custo"]["pico_va_mb"], linha["custo"]["pico_filho_mb"] or 0)

        self.stdout.write("")
        self.stdout.write("Custo de processamento — as duas metades, separadas")
        self.stdout.write(
            f"  {'entrada':>9}  {'filho':>8}  {'em proc.':>9}  {'tempo':>7}  "
            f"{'MB/MB':>7}  arquivo"
        )
        censurados = 0
        for linha in sorted(com_custo, key=_pico, reverse=True):
            custo = linha["custo"]
            entrada_mb = custo["bytes"] / 1048576
            # A razão é o número que mata a fronteira por tamanho: se o custo
            # fosse função do peso, ela seria constante. Ver a dispersão dela é
            # ver o argumento inteiro numa coluna.
            razao = (_pico(linha) / entrada_mb) if entrada_mb else 0
            filho = custo["pico_filho_mb"]
            # **Quem morreu no teto não teve o pico medido — teve o teto medido.**
            # Sem esta marca, `2036 MB` num arquivo que estourou entraria na
            # conta da fronteira como exigência conhecida, quando é só o ponto
            # onde nós o interrompemos. Piso, não medida.
            no_teto = self._parou_no_teto(linha)
            censurados += 1 if no_teto else 0
            marca = "≥" if no_teto else " "
            self.stdout.write(
                f"  {entrada_mb:8.1f}M  "
                f"{(f'{marca}{filho}M' if filho else 'n/d'):>8}  "
                f"{custo['pico_va_mb']:8}M  {custo['segundos']:6.1f}s  "
                f"{marca}{razao:6.1f}  {os.path.basename(linha['arquivo'])}"
            )

        if censurados:
            self.stdout.write(self.style.WARNING(
                f"  ≥ = {censurados} arquivo(s) pararam NO teto: o pico é piso, "
                f"não exigência. Para saber quanto pedem, medir com teto maior "
                f"(decisão de quem paga a máquina — payment/planos.py)"
            ))

        sem_filho = [l for l in com_custo if not l["custo"]["pico_filho_mb"]]
        if sem_filho:
            # Silenciar isto faria `n/d` passar por "não custou nada". O conselho
            # mudou junto com o instrumento (D82): `LOTE=1` já não é o que torna o
            # número atribuível — o `VmHWM` do próprio filho é —, então o que
            # sobra aqui é subprocesso curto demais para cair numa amostra, ou
            # conversão que não abriu subprocesso nenhum.
            self.stdout.write(self.style.WARNING(
                f"  {len(sem_filho)} de {len(com_custo)} sem pico do filho medido "
                f"— subprocesso mais curto que a amostragem, ou nenhum subprocesso"
            ))

        # A dispersão só fala de quem foi medido de verdade: misturar censurado
        # com medido produziria uma faixa achatada pelo teto — e faria o custo
        # parecer mais previsível pelo tamanho do que ele é.
        razoes = [
            _pico(l) / (l["custo"]["bytes"] / 1048576)
            for l in com_custo
            if l["custo"]["bytes"] and _pico(l) and not self._parou_no_teto(l)
        ]
        if razoes:
            self.stdout.write(
                f"  MB de pico por MB de arquivo (só os medidos, {len(razoes)} de "
                f"{len(com_custo)}): menor {min(razoes):.1f} · maior {max(razoes):.1f}"
                f" — quanto mais longe de constante, menos o tamanho prevê o custo"
            )

    @staticmethod
    def _parou_no_teto(linha: dict) -> bool:
        """O pico é o teto, e não a exigência do arquivo.

        A folga de 5% cobre a distância entre a última alocação que coube e o
        limite: o processo morre um pouco *antes* do número redondo, e exigir
        igualdade exata deixaria todo censurado passar por medido.
        """
        if linha.get("causa") != "recurso_excedido":
            return False
        teto = PRANCHETA_SUBPROCESSO_MEMORIA_MB
        return bool(teto) and (linha["custo"]["pico_filho_mb"] or 0) >= teto * 0.95

    #: Quantos arquivos listar por causa antes de cortar. Passar disso vira
    #: parede de texto no terminal — e a lista inteira continua no parcial JSON,
    #: que é o registro; isto aqui é a leitura.
    LIMITE_DA_LISTA = 40

    def _nomear_arquivos(self, linhas: list[dict]) -> None:
        """*Quais* arquivos, e não só quantos — o que faltou em 07/08.

        Sem esta seção, cada achado do relatório é um número que a investigação
        seguinte tem de reconquistar remedindo o acervo. Com ela, cada causa sai do
        relatório como **lista de trabalho** — o `dxf_intermediario_ilegivel` é o
        D43, e são 22 caminhos para abrir um a um.

        Os convertidos ficam de fora da listagem por volume — menos os que
        couberam **descendo a escada**, que são a pergunta em aberto da PRA.1d:
        aquele arquivo perdeu hachura porque é caro mesmo, ou porque o orçamento
        que ele encontrou não era o que o plano declarava?
        """
        if not linhas:
            return

        def _listar(titulo: str, selecionadas: list[dict]) -> None:
            if not selecionadas:
                return
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"{titulo} ({len(selecionadas)})"))
            for linha in selecionadas[:self.LIMITE_DA_LISTA]:
                versao = linha.get("versao") or "??????"
                self.stdout.write(f"  {versao:8} {linha['arquivo']}")
            sobrando = len(selecionadas) - self.LIMITE_DA_LISTA
            if sobrando > 0:
                self.stdout.write(f"  … e mais {sobrando} (a lista inteira está nos parciais)")

        falharam = [l for l in linhas if l["balde"] != "convertido"]
        por_causa: dict[str, list[dict]] = defaultdict(list)
        for linha in falharam:
            por_causa[linha.get("causa") or "sem_causa_registrada"].append(linha)
        for causa, desta in sorted(por_causa.items(), key=lambda i: -len(i[1])):
            _listar(f"Não converteram — {causa} → {self._dono(causa)}", desta)

        _listar(
            "Converteram só descendo a escada (hachura simplificada)",
            [l for l in linhas
             if "convertido_com_hachura_simplificada" in (l.get("sinais") or [])],
        )

    def _conferir_cobertura(self, janelas: list[dict], total: int) -> None:
        """Os lotes cobrem o corpus inteiro, uma vez cada?

        Sem esta conferência, `--consolidar` seria uma soma que **parece**
        completa: 14 lotes de 10 sobre um corpus de 150 dariam uma taxa com cara
        de definitiva sobre 140 arquivos.
        """
        cursor, buracos, sobrepostos = 0, [], []
        for janela in sorted(janelas, key=lambda j: j["pular"]):
            inicio, fim = janela["pular"], janela["pular"] + janela["medidos"]
            if inicio > cursor:
                buracos.append((cursor, inicio))
            elif inicio < cursor:
                sobrepostos.append((inicio, min(cursor, fim)))
            cursor = max(cursor, fim)
        if cursor < total:
            buracos.append((cursor, total))

        if not buracos and not sobrepostos:
            self.stdout.write(self.style.SUCCESS(
                f"  Cobertura: {total} de {total} — o corpus inteiro, uma vez cada."
            ))
            return
        for inicio, fim in buracos:
            self.stdout.write(self.style.ERROR(
                f"  BURACO: os arquivos {inicio}–{fim - 1} não foram medidos por "
                "lote nenhum — a taxa abaixo NÃO é a do corpus."
            ))
        for inicio, fim in sobrepostos:
            self.stdout.write(self.style.ERROR(
                f"  SOBREPOSIÇÃO: os arquivos {inicio}–{fim - 1} foram medidos "
                "por mais de um lote e estão contados em dobro."
            ))

    # -- medição -------------------------------------------------------------
    def _classificar(self, motor: MotorDwg, caminho: str, *,
                     sinais: Counter, teto: int = 0,
                     ) -> tuple[str, str, str, str, list[str]]:
        codigo, _rotulo = ler_versao_dwg(caminho)
        if not codigo:
            return "invalido", "", "", "", []
        if codigo not in ALCANCE_LIVRE:
            return "acima_do_alcance", codigo, CAUSA_ACIMA, "", []
        try:
            with teto_de_tempo(teto):
                saida = self._converter_como_em_producao(motor, caminho)
        except RecursoExcedido as exc:
            # **O teto que impede esta medição de repetir o incidente do D57.**
            # A passada de 06/08 consumiu 62 GB numa estação de 64 e teve de ser
            # interrompida; a tentativa seguinte levou `nice` e teto de tempo — e
            # o que estourava era **memória**. Agora a medição roda pelo mesmo
            # orçamento da produção, então o pior caso é uma linha nesta coluna.
            #
            # Balde próprio, e não `estourou_o_teto_da_medicao`: aquele é o
            # relógio arbitrário desta medição, este é o teto que o cliente vive.
            return ("falhou_no_alcance", codigo, exc.motivo,
                    exc.detalhe or f"teto: {exc.extra.get('teto', '')}", [])
        except EstourouOTeto:
            # **Não é falha do motor livre, e não pode virar upsell.** O arquivo
            # provavelmente converte — só não dentro do teto que ESTA medição
            # impôs. Contá-lo como "exige o premium" venderia plano para resolver
            # um limite nosso; a causa fica separada e a decisão é a do D57.
            return ("falhou_no_alcance", codigo, "estourou_o_teto_da_medicao",
                    f"não terminou em {teto}s", [])
        except MotorInsuficiente as exc:
            # Dentro do alcance declarado e ainda assim não abriu: o balde que
            # mede a distância entre a promessa e a entrega.
            return ("falhou_no_alcance", codigo, exc.motivo,
                    exc.extra.get("stderr") or exc.detalhe, [])
        except MotorIndisponivel as exc:  # pragma: no cover - checado no handle
            return "falhou_no_alcance", codigo, exc.motivo, exc.detalhe, []
        except ErroDeConversao as exc:
            # A CLASSE, não só o motivo: `FalhaDoIntermediario` e `FalhaMotor`
            # compartilham `motivo="falha_motor"`, e são coisas diferentes — a
            # primeira é o DXF que NÓS geramos e o `ezdxf` não lê (D43, o maior
            # resto da remedição), a segunda é falha genérica de render.
            causa = ("dxf_intermediario_ilegivel"
                     if isinstance(exc, FalhaDoIntermediario) else exc.motivo)
            return ("falhou_no_alcance", codigo, causa,
                    f"{exc.motivo}: {exc.detalhe}", [])

        return "convertido", codigo, "", "", self._anotar_sinais(saida, sinais)

    def _converter_como_em_producao(self, motor: MotorDwg, caminho: str):
        """A mesma escada e o mesmo orçamento que o worker usa (D57, PRA.1d).

        **Medir por um caminho diferente do de produção mede a coisa errada.**
        Até esta fatia o comando chamava o motor direto: sem orçamento de memória
        (o `teto_de_tempo` daqui cobre só o relógio) e sem a segunda passada. O
        resultado era uma medição que podia consumir a máquina inteira — foi como
        a passada de 06/08 chegou a 62 GB — e que, por não descer a escada,
        contaria como falha o arquivo que a produção entregaria simplificado.

        Reusar `pipeline._rodar_a_escada` é o que garante que os dois caminhos não
        divirjam no próximo ajuste. Os dois objetos falsos são o mínimo que ele
        lê: o `pk` só aparece na linha de log, e aqui o caminho do arquivo é uma
        identificação melhor que um id que não existe.
        """
        from types import SimpleNamespace

        return pipeline._rodar_a_escada(
            motor, caminho,
            derivada=SimpleNamespace(pk=os.path.basename(caminho), tipo="vetor_2d"),
            revisao=SimpleNamespace(formato="dwg"),
        )

    def _anotar_sinais(self, saida, sinais: Counter) -> list[str]:
        """O que a memória de conversão diz sobre um arquivo que ABRIU.

        Existe para a remedição responder *por que* a taxa subiu, e não só que
        subiu: se os convertidos novos vierem do paperspace, quem os trouxe foi o
        D44; se vierem com `escala_recusada`, o D46 os teria mostrado como tarja.

        Devolve os sinais **deste** arquivo além de somá-los, porque a pergunta
        que a passada de hoje precisa responder é nominal: *quais* arquivos só
        couberam no orçamento com a hachura simplificada, para saber quantos
        deles voltam a converter inteiros agora que o teto é o declarado (D76).
        """
        detalhe = saida.detalhe or {}
        deste: list[str] = []
        if detalhe.get("espaco") == "paperspace":
            deste.append("convertido_pelo_paperspace")
        if detalhe.get("recuperado"):
            deste.append("dxf_lido_via_recover")
        if detalhe.get("blocos_ausentes"):
            deste.append("com_blocos_ausentes")
        if detalhe.get("xrefs_ausentes"):
            deste.append("com_xref_ausente_mas_desenhou")
        if detalhe.get("escala_recusada"):
            deste.append("escala_fora_da_plausibilidade")
        if detalhe.get("escala_indisponivel"):
            deste.append("sem_regua")
        if len(saida.partes) > 1:
            deste.append("multifolha")
        # **Convertido não é mais uma coisa só, e a comparação com o D42 depende
        # disto.** Com a escada da PRA.1d, um arquivo que só cabe no orçamento
        # com a hachura simplificada entra em `convertido` — e somá-lo em silêncio
        # inflaria a taxa contra a linha de base, que foi medida sem escada. Estes
        # dois baldes são o que permite ler a taxa nova pelos dois critérios.
        if detalhe.get("hachura") == "contorno":
            deste.append("convertido_com_hachura_simplificada")
        if detalhe.get("hachura") == "parcial":
            deste.append("com_hachura_desenhada_pela_metade")
        # **Quem só abriu porque foi remendado** (D43). É a medida da dívida que o
        # escritor de DXF do LibreDWG nos deixa: sem esta linha, o arquivo
        # reparado é indistinguível do que nasceu são, e no dia em que o upstream
        # corrigir não haverá como saber que o reparo virou desnecessário.
        for reparo in sorted(detalhe.get("reparos") or {}):
            deste.append(f"convertido_apos_reparo: {reparo}")
        sinais.update(deste)
        return deste

    def _medir_preview(self, motor: MotorDwg, caminho: str) -> str:
        """O caminho feliz do `dwgbmp` sobre arquivo real (D49).

        A PRA.1b provou a **ausência** do preview com binário real e a presença
        só com binário falso — as amostras do repositório são sintéticas e
        nenhuma carrega thumbnail. Este balde fecha isso, e de quebra responde
        uma pergunta de produto: quando a conversão falha, o cartão do acervo
        fica com alguma figura ou fica vazio?
        """
        try:
            motor.converter(caminho, formato="dwg", tipo="miniatura")
        except ErroDeConversao as exc:
            formato = exc.extra.get("preview_formato")
            if formato and formato != "desconhecido":
                return f"preview_ilegivel ({formato})"
            if formato == "desconhecido":
                # Quase sempre WMF: vetorial do Windows, sem renderizador na
                # imagem. É o número que decide se vale um.
                return "preview_em_formato_nao_lido (WMF?)"
            return exc.motivo
        return "com_preview"

    # -- resgate pelo dwg2SVG (D43) ------------------------------------------
    def _preparar_resgate(self, pedido: bool) -> str:
        if not pedido:
            return ""
        binario = executavel("dwg2SVG", "LIBREDWG_DWG2SVG")
        if not binario:
            raise CommandError(
                "O `dwg2SVG` não está nesta imagem — sem ele o --resgate mediria "
                "zero e leríamos isso como 'não há resgate'. Ele sai do mesmo "
                "build stage do `dwg2dxf` (backend/Dockerfile)."
            )
        return binario

    def _tentar_resgate(self, binario: str, caminho: str) -> str:
        """O DWG que o nosso caminho não abriu é ilegível, ou só o DXF é?

        O `dwg2SVG` vai do DWG direto ao SVG, **sem passar pelo `ezdxf`** — é o
        atalho que a §4.1/D43 aponta. Aqui ele é só instrumento: mede se existe
        geometria a resgatar. Promovê-lo a motor é outra conversa (sem `Recorder`,
        não há folha, âncora nem escala).

        O próprio `--help` dele diz *"converts SOME 2D elements"*, então o
        critério não pode ser "gerou arquivo": um SVG com cabeçalho e nenhum traço
        contaria como resgate e não mostraria nada na tela.
        """
        descritor, destino = tempfile.mkstemp(suffix=".svg", prefix="resgate-")
        try:
            with os.fdopen(descritor, "wb") as saida:
                # O dwg2SVG escreve o SVG em stdout (ver --help).
                processo = subprocess.run(  # noqa: S603 - argumentos montados por nós
                    [binario, caminho], stdout=saida, stderr=subprocess.DEVNULL,
                    timeout=TIMEOUT_RESGATE, check=False,
                )
            if processo.returncode != 0 or not os.path.getsize(destino):
                return "resgate_falhou"
            with open(destino, "rb") as arquivo:
                conteudo = arquivo.read()
            tracos = sum(conteudo.count(elemento) for elemento in ELEMENTOS_DE_TRACO)
            if not tracos:
                return "resgate_vazio (abriu, sem traço)"
            return "resgatado (com traço)"
        except subprocess.TimeoutExpired:
            return "resgate_estourou_o_tempo"
        except OSError:
            return "resgate_falhou"
        finally:
            try:
                os.unlink(destino)
            except OSError:
                pass

    # -- saída ---------------------------------------------------------------
    def _dono(self, causa: str) -> str:
        """Quem age sobre esta causa. O default é NOSSO, e é de propósito.

        Causa nova que ninguém mapeou aparece como conserto nosso, não como
        upsell: errar para o lado de "temos trabalho a fazer" custa uma linha na
        nossa fila; errar para o outro cobra do cliente por um defeito nosso.
        """
        if causa == CAUSA_ACIMA:
            return DONO_DA_CAUSA["motor_insuficiente"]
        return DONO_DA_CAUSA.get(causa, DONO_PADRAO)

    def _relatorio(self, baldes, causas, por_versao, motivos, sinais,
                   previews, resgatados) -> None:
        validos = sum(v for k, v in baldes.items() if k != "invalido")
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Cobertura do motor livre"))
        for balde in ("convertido", "falhou_no_alcance", "acima_do_alcance", "invalido"):
            self.stdout.write(f"  {balde:20} {baldes[balde]:5}")

        if validos:
            taxa = 100.0 * baldes["convertido"] / validos
            no_alcance = baldes["convertido"] + baldes["falhou_no_alcance"]
            estilo = self.style.SUCCESS if taxa >= 90 else self.style.WARNING
            self.stdout.write("")
            self.stdout.write(estilo(f"  Taxa sobre TODOS os DWGs válidos: {taxa:.1f}%"))
            if no_alcance:
                dentro = 100.0 * baldes["convertido"] / no_alcance
                # As duas taxas respondem perguntas comerciais diferentes: a
                # primeira é "quantos clientes deste acervo o plano básico
                # atende?", a segunda é "o LibreDWG cumpre o que promete?".
                self.stdout.write(f"  Taxa dentro do alcance declarado:  {dentro:.1f}%")

        if causas:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(
                "Por causa da falha — e de quem é (a tabela do D42)"))
            total = sum(causas.values())
            for causa, quantas in causas.most_common():
                fatia = 100.0 * quantas / validos if validos else 0.0
                self.stdout.write(
                    f"  {causa:28} {quantas:4} ({fatia:4.1f}% do acervo)  "
                    f"→ {self._dono(causa)}"
                )
            # A linha que a planta §4.1 usa para dimensionar a PRA.4: só o
            # `motor_insuficiente` é fronteira de PLANO. Somar tudo como "não
            # abriu" venderia como limite tecnológico o que é lista de conserto.
            do_premium = causas.get("motor_insuficiente", 0) + causas.get(CAUSA_ACIMA, 0)
            if validos:
                self.stdout.write("")
                self.stdout.write(self.style.WARNING(
                    f"  Limite REAL do caminho livre (o que só o premium resolve): "
                    f"{100.0 * do_premium / validos:.1f}%  "
                    f"[{do_premium} de {validos}]"
                ))
                nosso = total - do_premium - sum(
                    q for c, q in causas.items()
                    if c in DerivadaProjeto.MOTIVOS_DO_ARQUIVO
                )
                self.stdout.write(
                    f"  Falhas que são NOSSAS (conserto, não venda): "
                    f"{100.0 * nosso / validos:.1f}%  [{nosso} de {validos}]"
                )

        if sinais:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(
                "O que a memória de conversão diz de quem ABRIU"))
            for sinal, quantas in sinais.most_common():
                self.stdout.write(f"  {sinal:34} {quantas:4}")

        if previews is not None:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(
                "Miniatura embutida — o que o CAD gravou (D49)"))
            for estado, quantas in previews.most_common():
                self.stdout.write(f"  {estado:34} {quantas:4}")

        if resgatados is not None:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(
                "Resgate pelo dwg2SVG, só nos que falharam (D43)"))
            for estado, quantas in resgatados.most_common():
                self.stdout.write(f"  {estado:34} {quantas:4}")

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Por versão do DWG"))
        for codigo in sorted(por_versao):
            contagem = por_versao[codigo]
            resumo = " ".join(f"{k}={v}" for k, v in sorted(contagem.items()))
            self.stdout.write(f"  {codigo:8} {resumo}")

        if motivos:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("Motivos de falha mais comuns"))
            for motivo, quantas in motivos.most_common(10):
                self.stdout.write(f"  {quantas:4}× {motivo}")

        self.stdout.write("")
        self.stdout.write(
            "Registre o resultado em docs/modulos/moduloprancheta.md §4.1 — é ele "
            "que define onde fica a fronteira entre os planos."
        )
