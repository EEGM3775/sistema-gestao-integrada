# backend/moduloprancheta/motores/base.py
"""Contrato de um motor de conversão — o que todo adaptador promete.

Um adaptador é um objeto pequeno com três perguntas: **você existe nesta
imagem?** (`disponivel`), **em que versão?** (`versao`) e **converta isto**
(`converter`). Nada mais. Quem decide *o que* converter é o `pipeline`; quem
decide *se o plano permite* é `uploads.py`. Esta camada não sabe de tenant, de
plano nem de banco — recebe um caminho de arquivo e devolve bytes.

**Por que a versão é obrigatória e não um detalhe:** a `DerivadaProjeto` é única
por `(revisão, tipo, motor)` e carimba `motor_versao`. É a comparação dessa
string que decide se um upgrade do `ezdxf` invalida o acervo convertido — sem
flag manual, sem migration de dados (planta §9). Adaptador que devolvesse versão
vazia tornaria toda derivada eternamente atual.

**A taxonomia do erro é a parte que mais importa deste arquivo.** As cinco
subclasses não são detalhe de log: cada uma vira uma frase diferente na tela e
uma decisão diferente do pipeline. Em especial, duas que é fácil confundir e
caro trocar:

- `MotorInsuficiente` — *o arquivo do cliente exige o motor de alta fidelidade*.
  É limite de PLANO, e a resposta certa é oferecer o upgrade. A planta §4.1 é
  explícita: DWG que o LibreDWG não abre precisa dizer isso, e não "falha na
  conversão". Não adianta tentar de novo.
- `MotorIndisponivel` — *o motor não está nesta imagem*. É problema NOSSO, de
  operação. Mandar o cliente comprar um plano melhor por causa de um binário
  que esquecemos de instalar seria vender uma solução que não resolve o problema
  dele. Não adianta tentar de novo tampouco — mas o que conserta é um deploy,
  não um pagamento.

`retentavel` separa o que uma segunda tentativa pode consertar (rede, memória,
pico de carga) do que não pode (o arquivo é o que é). Sem essa distinção o
Celery repetiria 3× uma conversão que vai falhar exatamente igual, e a DLQ
encheria de erro de plano.

**A PRA.1b acrescentou um terceiro dono.** Até aqui a taxonomia separava o que é
do *plano* do que é *nosso*; a remedição do **D42** mostrou um terceiro grupo que
não é de ninguém — o arquivo não tem desenho (`DesenhoVazio`), a geometria mora
em arquivos que nunca subiram (`ReferenciaAusente`) ou o DWG não carrega a
miniatura que o CAD grava (`SemPreviewEmbutido`). Chamar qualquer um deles de
"falha interna do motor" é confessar um defeito que não existe, e enche a fila do
que *nós* consertamos com linha que ninguém vai consertar. Ver `D45`/`D49`.
"""
from __future__ import annotations

import resource
import shutil
import signal
import subprocess
from abc import ABC, abstractmethod
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

#: Desenhar a hachura como **contorno** em vez do padrão de linhas (D57).
#:
#: A única economia que existe hoje, e ela tem nome próprio em vez de um nível
#: numérico porque o que se abre mão precisa aparecer na frase que o cliente lê:
#: "hachura simplificada" é dizível, "economia 1" não é.
ECONOMIA_HACHURA = "hachura_contorno"

#: Sair do nosso renderizador e usar o do próprio LibreDWG (`dwg2SVG`).
#:
#: **Não é economia de desenho, é troca de estratégia**, e por isso é o último
#: degrau: o nosso caminho expande cada inserção de bloco em geometria completa —
#: é o que faz um DWG de 43 MB custar ~945 MB de memória —, enquanto o `dwg2SVG`
#: emite o bloco uma vez e o referencia. O nome diz o que muda para quem lê a
#: frase: o desenho vem do motor, não do nosso traço.
ECONOMIA_SVG_DIRETO = "svg_do_motor"


@dataclass(frozen=True)
class Parte:
    """Um **desenho** dentro do mesmo arquivo de origem, com a folha dele.

    Nasceu da medição do acervo: o DWG de construtora não traz "uma prancha". O
    `confrontantes.dwg` traz duas poligonais a 8,5 milhões de unidades uma da
    outra (a mesma área desenhada na origem e em UTM), e o *sheet set* montado no
    modelspace traz dezenas de plantas em grade. Emitir tudo numa folha só
    produzia uma página de 469 m × 8,5 km — que nenhum navegador rasteriza e onde
    cada desenho ocupa 0,2% da largura.

    **Uma parte não é um recorte editorial.** Nada é apagado: todo aglomerado
    vira uma parte, inclusive o traço solto (`tracos == 1`). O que muda é que
    cada um ganha a própria folha, e com ela a própria régua — a `caixa` em
    unidades de desenho é o que permite reencontrá-lo na revisão seguinte, e é
    por isso que ela viaja em unidade de desenho e não normalizada: a folha muda
    entre revisões, o lugar no terreno não.
    """

    conteudo: bytes
    #: 1..N, do maior para o menor. É o `Desenho N` que a tela mostra até alguém
    #: dar nome.
    ordem: int
    #: Envolvente em **unidades de desenho**: `{"xmin","ymin","xmax","ymax"}`.
    caixa: dict
    tracos: int
    detalhe: dict
    #: A ponte de volta à coordenada do CAD:
    #: `{"origem_x","origem_y","por_folha"}`, com
    #: `x_desenho = origem_x + x_folha·por_folha` e
    #: `y_desenho = origem_y − y_folha·por_folha`.
    #:
    #: **Medida na emissão, nunca recalculada** (`dxf.py::_mundo_da_folha`), pela
    #: mesma razão que a régua e o snap: quem arbitra margem, arredondamento de
    #: folha e centralização é o `ezdxf`, e refazer a conta erra de um jeito que
    #: cresce com o zoom — foi metade do D90. Vazia quando não dá para medir
    #: (envolvente degenerada, motor que não é de vetor); a tela então mostra as
    #: réguas dela e **não** finge coordenada de desenho.
    mundo: dict = field(default_factory=dict)
    #: Nome que **o arquivo** deu a esta folha, quando ele dá algum.
    #:
    #: Vazio no caso normal — desenho separado por lacuna no modelspace não tem
    #: nome nenhum, e a tela mostra "Desenho N" até uma pessoa batizá-lo. Quem
    #: preenche é o caminho do paperspace (D44): lá cada folha **é** uma aba do
    #: CAD, e "PLANTA BAIXA - PAV TIPO" é nome de gente, escrito por gente. Só
    #: vale para desenho novo: renomear na tela é soberano, como a calibração.
    nome: str = ""
    #: O sidecar de snap desta folha (`motores/snap.py::empacotar`), ou `None`
    #: quando o plano não tem o recurso, o formato não rende geometria (PDF,
    #: imagem) ou a extração falhou.
    #:
    #: **Viaja ao lado do SVG e não dentro dele**, porque a vista mostra a
    #: prancha num `<img>` — decisão de segurança, não de simplicidade (ver
    #: `Vista2D.tsx`). Dentro de `<img>` o DOM não expõe vértice nenhum, então a
    #: mira precisa de uma fonte de geometria própria; embutir no SVG obrigaria a
    #: injetá-lo inline, que é exatamente o que aquela decisão proíbe.
    snap: bytes | None = None
    #: Quantos pontos o índice tem, e se o teto do plano cortou. Ficam fora do
    #: `detalhe` porque a tela decide com eles (mostrar "snap parcial", oferecer
    #: o pacote), e `detalhe` é telemetria de conversão, não contrato de UI.
    snap_pontos: int = 0
    snap_truncado: bool = False


@dataclass(frozen=True)
class Saida:
    """O produto de uma conversão: bytes + como gravá-los.

    Bytes e não caminho de arquivo, de propósito: quem grava é o pipeline, que é
    o único que sabe o `FileField`, o storage e o nome final. Um adaptador que
    escrevesse direto no storage precisaria conhecer o modelo — e aí não daria
    para testá-lo sem banco.
    """

    conteudo: bytes
    extensao: str
    content_type: str
    # Telemetria honesta: o que o motor conseguiu ler. Alimenta a memória de
    # conversão que a planta §5 pede ("+ memória de conversão") e, no DWG, é o
    # que o `medir_cobertura_dwg` agrega para decidir onde fica a fronteira
    # comercial entre os planos (§4.1).
    detalhe: dict | None = None
    #: Os desenhos que o arquivo trouxe, quando o motor sabe separá-los.
    #:
    #: **Vazio é o caso normal** e significa "uma folha só" — é o que PDF, imagem
    #: e IFC devolvem, e é o que o DXF/DWG devolve quando o arquivo tem um desenho
    #: só. Quem consome trata os dois casos pelo mesmo caminho lendo `partes or
    #: [a folha inteira]`, então um motor novo não precisa saber que isto existe.
    #:
    #: Quando há partes, `conteudo` é o da **primeira** — assim qualquer código
    #: que ainda não conheça o conceito continua abrindo o maior desenho, em vez
    #: de abrir nada.
    partes: tuple[Parte, ...] = ()
    #: Onde esta passada parou, quando ela **não terminou o arquivo** (PRA.11).
    #:
    #: `None` é o caso normal e significa "acabou": o motor emitiu todas as
    #: folhas. Preenchido, é o marcador que o pipeline usa para gravar o que veio
    #: e devolver o arquivo ao fim da fila — ver `Retomada`.
    retomada: "Retomada | None" = None


@dataclass(frozen=True)
class Retomada:
    """Onde a conversão parou, para a próxima passada continuar dali (PRA.11).

    **Por que o marcador é do MOTOR e a decisão é do pipeline.** Só o motor sabe
    o que é uma unidade de trabalho retomável no formato dele (aqui, a folha); só
    o pipeline sabe se ainda há orçamento, se vale reenfileirar e o que dizer ao
    cliente. Misturar os dois poria política comercial dentro do `ezdxf`.

    **O que NÃO é retomado, e é honesto declarar:** a gravação da geometria
    (`Recorder`) roda inteira em toda passada — ela é o que expande o DWG em
    memória, e não há como serializá-la mais barato do que refazê-la. O que a
    retomada economiza é a **emissão das folhas**, que num arquivo de dezenas de
    desenhos é a maior parte do relógio. Num arquivo de folha única ela não
    economiza nada, e por isso o pipeline nem tenta: sem folha seguinte, o
    estouro continua sendo `recurso_excedido` na hora, como sempre foi.
    """

    #: Quantos **grupos** (aglomerados) já foram processados, incluindo os que
    #: não desenharam nada. É por onde a passada seguinte começa.
    grupos_feitos: int
    #: Quantas folhas com traço já foram emitidas — o `ordem` da próxima é este
    #: número + 1. Separado de `grupos_feitos` porque a numeração pula o
    #: aglomerado vazio, e recontá-la do zero renomearia as folhas já gravadas.
    desenhos_feitos: int
    #: Quantos grupos ainda faltam. Zero aqui seria `retomada = None`.
    restam: int
    #: Aglomerados sem traço já descartados, e quantos registros havia neles.
    #: Viajam porque o censo final (`desenhos_sem_traco`) soma o arquivo inteiro,
    #: e a passada que o fecha não viu as passadas anteriores.
    vazios_feitos: int = 0
    registros_vazios_feitos: int = 0


class ErroDeConversao(Exception):
    """Base de toda falha de motor. `motivo` casa com `DerivadaProjeto.MotivoErro`."""

    motivo = "falha_motor"
    retentavel = False

    def __init__(self, detalhe: str = "", **extra):
        super().__init__(detalhe or self.motivo)
        self.detalhe = detalhe
        self.extra = extra


class MotorInsuficiente(ErroDeConversao):
    """Limite de PLANO — o arquivo exige o motor premium. Upsell, não defeito."""

    motivo = "motor_insuficiente"


class MotorIndisponivel(ErroDeConversao):
    """Limite NOSSO — o motor não está instalado nesta imagem.

    Separado do `MotorInsuficiente` porque a saída é oposta: aqui o cliente não
    tem o que comprar, e quem tem de agir somos nós. Ver a nota do módulo.
    """

    motivo = "motor_indisponivel"


class ArquivoCorrompido(ErroDeConversao):
    motivo = "arquivo_corrompido"


class VersaoNaoSuportada(ErroDeConversao):
    """O formato é o certo, a versão dele é mais nova que o motor livre alcança."""

    motivo = "versao_nao_suportada"


class TempoExcedido(ErroDeConversao):
    motivo = "tempo_excedido"
    retentavel = True


class FalhaMotor(ErroDeConversao):
    motivo = "falha_motor"
    retentavel = True


class FalhaDoIntermediario(ErroDeConversao):
    """Falhou na **ponte entre dois motores** — e o arquivo ilegível é nosso.

    Nasceu do **D42**: quando um motor converte para um formato intermediário e
    entrega a outro (o `dwg2dxf` produz um DXF que o `ezdxf` desenha), a falha do
    segundo estava sendo relatada como `arquivo_corrompido` — uma frase sobre o
    arquivo do cliente, quando o inválido é o intermediário que **nós** geramos a
    partir de um DWG que o primeiro motor abriu sem reclamar. Na medição sobre 73
    DWGs reais, 13 clientes leriam *"O arquivo não é um DXF válido"* sobre um DXF
    que nunca viram.

    `motivo` é `falha_motor` porque a fila de decisão do cockpit separa o que o
    cliente resolve comprando do que nós resolvemos consertando — e isto é nosso.
    `retentavel` é **False**, ao contrário do `FalhaMotor`: o intermediário é
    determinístico (mesmo DWG, mesmo binário, mesmo DXF quebrado), então repetir
    reproduz o defeito idêntico e só enche a DLQ.
    """

    motivo = "falha_motor"
    retentavel = False


class DesenhoVazio(ErroDeConversao):
    """O arquivo abriu, está íntegro e **não tem desenho dentro**.

    Cinco dos 150 DWGs da remedição do **D42** são assim — `Desenho1_recover.dwg`
    e parentes, sem uma entidade sequer no modelspace nem em layout nenhum. Até a
    PRA.1b eles liam *"falha interna do motor"*, que é confessar um defeito nosso
    inexistente e mandar o cliente abrir chamado sobre um arquivo que ele mesmo
    salvou vazio.

    Não é retentável e não é upsell: **nenhum motor desenha o que não existe**, e
    é por isso que este motivo não pode escalar para a APS.
    """

    motivo = "desenho_vazio"
    retentavel = False


class ReferenciaAusente(ErroDeConversao):
    """A geometria está em arquivos externos (XREF) que nunca foram enviados.

    Dois dos 150 da remedição. O DWG referencia por caminho absoluto da máquina
    do projetista (`C:\\Users\\…\\DATA\\28 08\\…dwg`) e traz só a inserção vazia.

    **É o único motivo desta família que é acionável pelo cliente** — e é por isso
    que ele carrega a lista de caminhos: a frase útil é *"esta prancha referencia
    3 arquivos que não foram enviados"* seguida dos nomes, não um erro genérico.
    Também é o motivo que **jamais** pode virar upsell: nenhum motor, livre ou
    premium, desenha o que não está no arquivo.
    """

    motivo = "referencia_ausente"
    retentavel = False


class RecursoExcedido(ErroDeConversao):
    """A conversão passou do teto de memória ou de relógio que NÓS impusemos.

    **É nosso, e não pode virar upsell** (D57). O arquivo provavelmente converte
    — só não dentro do orçamento que este servidor dá a uma conversão. Vender o
    motor premium aqui seria cobrar do cliente por um limite nosso, e nada
    garante que a APS aguente o mesmo desenho.

    Existe como motivo próprio porque os dois vizinhos mentiriam: `falha_motor`
    diz que o motor quebrou (não quebrou, foi interrompido) e `tempo_excedido`
    é `retentavel`, e repetir uma conversão que estourou o teto reproduz o
    estouro — três vezes, por conta da DLQ.

    O que produziu o teto: um DWG do acervo expandiu hachura até **62 GB de RAM**
    na medição de 06/08/2026, num caminho que roda em worker compartilhado e, em
    produção, em máquina paga. Ver `D57`.
    """

    motivo = "recurso_excedido"
    retentavel = False


class SemPreviewEmbutido(ErroDeConversao):
    """O DWG não carrega a miniatura que o CAD grava ao salvar.

    Estado normal, não avaria: o *thumbnail* depende de o escritório ter salvo com
    `RASTERPREVIEW` ligado, e arquivo gerado por script ou por conversor costuma
    sair sem ele. Existe como motivo próprio para a ausência **não** aparecer na
    fila do que nós consertamos — é a mesma lição do `DesenhoVazio`, aplicada ao
    cartão do acervo (planta §4.4).
    """

    motivo = "sem_preview"
    retentavel = False


#: O que **nenhum motor** pode reescrever como falha sua. Contrato, não detalhe.
#:
#: Achado pelo E2E vivo da PRA.1d, e é um defeito que só arquivo pesado revela: o
#: teto de memória do D57 age levantando `MemoryError` (é assim que o `RLIMIT_AS`
#: se manifesta no CPython), e `MemoryError` **é** `Exception`. Os `except
#: Exception` que traduzem falha de leitura e de desenho o capturavam primeiro,
#: então o estouro do orçamento chegava ao pipeline como `falha_motor` — "o motor
#: quebrou" — ou, pior, como `arquivo_corrompido`, acusando o arquivo do cliente
#: por um limite **nosso**. Duas consequências caras: a escada da PRA.1d nunca
#: descia (ela espera `RecursoExcedido`), e o `FalhaMotor` é `retentavel`, então a
#: DLQ repetia três vezes uma conversão que reproduz o mesmo estouro.
#:
#: **Mora aqui, e não no `dxf.py`, porque a regra é do contrato de motor.** A
#: correção nasceu no `ezdxf` — que é onde a medição doeu — e ficou só lá: PDF,
#: imagem, IFC e o preview embutido do DWG seguiram embrulhando `MemoryError`,
#: cada um com a frase errada. O caso mais caro era o do IFC, cuja metade cara (a
#: tesselação do OpenCascade) traduzia para `FalhaMotor`, **retentável**; o mais
#: invisível era o do preview do DWG, que virava `SemPreviewEmbutido` — motivo da
#: família "ninguém age", ou seja, o teto agindo sem aparecer em fila nenhuma.
#: Estando na base, motor novo herda a regra; quem esquecer o `except
#: NAO_EMBRULHAR` reabre o buraco, e é isso que a regressão por motor cobre.
#:
#: `ErroDeConversao` entra na mesma lista por já ser falha classificada: embrulhá-la
#: trocaria um motivo específico por um genérico — e é o que subsume os `except
#: ArquivoCorrompido: raise` / `except FalhaMotor: raise` que os motores tinham
#: antes, cada um relembrando só a subclasse que o autor tinha em mente.
NAO_EMBRULHAR = (MemoryError, ErroDeConversao)


class Adaptador(ABC):
    """Um motor. Registrado em `motores/__init__.py` pelo `codigo`, que é o mesmo
    de `formatos.py::MOTORES` — o teste `RegistryDeMotoresTests` falha se os dois
    lados divergirem, porque um motor declarado sem adaptador viraria derivada
    presa em `pendente` para sempre."""

    codigo: str = ""
    #: Tipos de `DerivadaProjeto.Tipo` que este motor sabe produzir.
    tipos: tuple[str, ...] = ()
    #: O que este motor sabe **abrir mão** quando a conversão fiel não coube no
    #: orçamento de recurso (D57), da menor perda para a maior. O pipeline desce
    #: esta escada um degrau por vez, cada degrau com orçamento novo.
    #:
    #: **Vazio é o caso normal**, e significa "não há o que economizar": a falha
    #: fica de pé em vez de o pipeline repetir a mesma conversão esperando outro
    #: resultado. Só o `ezdxf` declara alguma coisa aqui — PDF, imagem e IFC não
    #: têm nenhum knob cujo custo seja da ordem do que estoura.
    economias: tuple[str, ...] = ()
    _versao_cache: str | None = None

    @abstractmethod
    def _detectar_versao(self) -> str:
        """Versão do motor, como string estável. `""` quando indisponível."""

    def versao(self) -> str:
        """A versão, detectada **uma vez por processo**.

        O cache não é micro-otimização: `estado_dos_motores()` roda a cada
        `GET /api/prancheta/status/`, e a detecção do LibreDWG dispara um
        subprocesso. Sem cache, uma tela que faz *polling* do estado da conversão
        forkaria um processo por segundo por usuário.

        Consequência aceita: motor instalado **depois** do boot só aparece no
        próximo restart. Como instalar motor é deploy, e deploy reinicia o
        processo, o caso não existe na prática — e a alternativa (TTL) pagaria
        complexidade por um cenário que ninguém tem.
        """
        if self._versao_cache is None:
            self._versao_cache = self._detectar_versao()
        return self._versao_cache

    def disponivel(self) -> bool:
        return bool(self.versao())

    #: Este motor sabe parar no meio e continuar depois (PRA.11)?
    #:
    #: **`False` é o caso normal e é uma resposta**, não uma pendência: PDF,
    #: imagem e IFC convertem numa unidade indivisível, e prometer retomada onde
    #: ela não existe faria o pipeline reenfileirar um arquivo para refazer
    #: exatamente o mesmo trabalho — gastando mais máquina para chegar ao mesmo
    #: `recurso_excedido`, que é a armadilha que o registro do D98 já descrevia.
    #: Quem declara `False` mantém o comportamento de sempre: estoura, para tudo
    #: e explica.
    retomavel: bool = False

    @abstractmethod
    def converter(self, caminho: str, *, formato: str, tipo: str, economia: str = "",
                  teto_snap: int | None = 0, retomada: "Retomada | None" = None,
                  prazo=None, ceder=None) -> Saida:
        """Converte e devolve os bytes, ou levanta `ErroDeConversao`.

        `economia` é um dos valores que este motor declarou em `economias`, ou
        `""` para a conversão fiel — que é sempre a primeira tentativa. Motor que
        não declara economia nenhuma recebe sempre `""` e pode ignorar o
        parâmetro; ele está na assinatura de todos por ser **contrato**, e não
        detalhe do `ezdxf`: um motor futuro que saiba degradar entra na escada
        sem o pipeline saber o que ele faz lá dentro.

        `retomada` e `prazo` são o par da PRA.11, e valem só para quem declara
        `retomavel = True`:

        - **`retomada`** — onde a passada anterior parou, ou `None` na primeira.
          Quem a recebe deve pular o trabalho já feito e continuar a numeração de
          onde ela indica, nunca do zero: renumerar apagaria o nome que alguém
          deu à folha 3 na passada de ontem.
        - **`prazo`** — um `time.monotonic()` limite. O motor o confere entre
          unidades de trabalho e devolve `Saida.retomada` quando o alcança, em vez
          de levantar. **Não substitui os tetos de `limites.py`**: aqueles são a
          rede que age quando o motor não consegue ceder (preso em extensão C);
          este é a parada **negociada**, que é a única que consegue gravar o que
          já ficou pronto.
        - **`ceder`** — pergunta de zero argumentos, consultada **só depois** de o
          `prazo` vencer: "há alguém esperando?". `True` cede a vez; `False`
          continua trabalhando e volta a perguntar na unidade seguinte. `None`
          (o padrão) cede sempre, que é o comportamento de quem chama sem fila.

          *(decisão do dono, 16/08/2026: "não precisa ceder a cada arquivo que
          chegar, pode ser por tempo, mas isso se tiverem arquivos na fila; se não
          tiver não precisa ir para o final da fila".)* Sem esta pergunta, o
          arquivo pesado se interrompia aos 240 s **para dar lugar a uma fila
          vazia** — e pagava de novo o custo fixo, que a medição de 16/08 pôs em
          56% do relógio. Ceder sem ninguém para receber é desperdício puro.
        """


# ---------------------------------------------------------------------------
# O orçamento de memória do SUBPROCESSO, que agora varia por plano (D101)
# ---------------------------------------------------------------------------
#: **Por que uma variável de contexto e não mais um parâmetro de `converter`.**
#: O teto do subprocesso é consultado lá no fundo — `_para_dxf` e `_para_svg`, em
#: quatro pontos —, e levá-lo por argumento exigiria atravessá-lo por toda a
#: cadeia de chamada de cada motor, inclusive de motores que não têm subprocesso
#: nenhum. A régua do D57 vale aqui igual: recurso opcional não pode virar
#: defeito de quem não o pediu.
#:
#: **E por que isto não quebra a regra de os motores não conhecerem Django:** o
#: que atravessa é um inteiro em Python puro. Quem sabe traduzir plano em número
#: é o `pipeline`, que é código de aplicação e já tem o plano congelado na fila.
#:
#: `ContextVar` e não global de módulo porque o worker pode rodar conversões em
#: threads, e um global vazaria o teto de um tenant para o do vizinho — que é
#: exatamente o tipo de vazamento que a plataforma inteira existe para não ter.
#: `None` significa "use o padrão do módulo", que é o comportamento de sempre.
orcamento_do_subprocesso: ContextVar[int | None] = ContextVar(
    "prancheta_orcamento_do_subprocesso", default=None,
)


def teto_do_subprocesso(padrao: int) -> int:
    """O teto de memória do subprocesso desta conversão, em MB.

    Devolve o do plano quando o pipeline o definiu; `padrao` (a constante do
    módulo) quando ninguém definiu — teste, comando de bancada, medição.
    """
    return orcamento_do_subprocesso.get() or padrao


@contextmanager
def orcamento_de_subprocesso(memoria_mb: int | None):
    """Vale enquanto durar o bloco, e é restaurado mesmo se a conversão estourar."""
    marca = orcamento_do_subprocesso.set(memoria_mb or None)
    try:
        yield
    finally:
        orcamento_do_subprocesso.reset(marca)


# ---------------------------------------------------------------------------
# Utilitários compartilhados pelos adaptadores
# ---------------------------------------------------------------------------
def versao_de_modulo(nome: str) -> str:
    """Versão de uma dependência Python **com import tardio**.

    Import tardio é o idioma já estabelecido no repositório (o `pdfplumber` da
    ORC.5b faz o mesmo, e o comentário do `requirements.txt` explica por quê): a
    ausência de uma biblioteca pesada não pode derrubar o processo no boot nem
    quebrar `manage.py check`. Aqui ela só torna aquele motor indisponível — e
    isso aparece declarado em `GET /api/prancheta/status/`, não como 500 na cara
    de quem subiu o arquivo.
    """
    try:
        modulo = __import__(nome)
    except Exception:  # ImportError, mas também erro de binding compilado
        return ""
    return str(getattr(modulo, "__version__", "") or "desconhecida")


def executavel(nome: str, env_override: str | None = None) -> str | None:
    """Caminho de um binário externo, com override por variável de ambiente.

    O override existe porque **o LibreDWG não é empacotado pelo Debian** — não
    há `libredwg` em nenhuma suíte (bookworm/trixie/sid), então ele entra na
    imagem por build stage e pode acabar fora do `PATH` padrão dependendo de como
    o operador o instalou. Deixar o caminho configurável é mais barato que supor
    um prefixo.
    """
    import os

    if env_override:
        caminho = os.environ.get(env_override)
        if caminho:
            return caminho if os.path.exists(caminho) else None
    return shutil.which(nome)


#: Sinais com que um programa em C morre quando não consegue mais alocar.
#:
#: **`SIGSEGV` lidera a lista, e isso é contraintuitivo** (D78): o esperado seria
#: o processo terminar com erro, mas bibliotecas que não conferem o retorno do
#: `malloc` — o LibreDWG é uma — desreferenciam o ponteiro nulo e **quebram**.
#: `SIGABRT` é a outra metade (glibc abortando em `malloc` falho ou corrupção de
#: heap) e `SIGKILL` é o OOM killer do cgroup chegando antes do nosso teto.
#:
#: Montada com `getattr` porque `SIGBUS` não existe no Windows, e um erro de
#: importação aqui derrubaria o módulo inteiro por causa de um sinal que aquela
#: plataforma nunca vai entregar.
SINAIS_DE_FALTA_DE_MEMORIA = tuple(
    -getattr(signal, nome)
    for nome in ("SIGSEGV", "SIGABRT", "SIGBUS", "SIGKILL")
    if hasattr(signal, nome)
)


def orcamento_armado() -> bool:
    """Existe um `RLIMIT_AS` finito valendo agora — ou seja, um teto NOSSO.

    O `subprocess` herda o `RLIMIT_AS` do pai, então quando `orcamento_de_conversao()`
    está armado o filho corre sob um teto que **nós** escolhemos.
    """
    try:
        return resource.getrlimit(resource.RLIMIT_AS)[0] != resource.RLIM_INFINITY
    except (AttributeError, ValueError, OSError):  # pragma: no cover - Windows
        return False


def morreu_por_falta_de_memoria(returncode: int, *, teto_do_filho_mb: int = 0) -> bool:
    """O subprocesso morreu de sinal **e** havia teto nosso armado (D78).

    **Dois tetos contam, e esquecer o segundo reabriria o buraco.** O do pai, que
    o filho herda; e o `teto_do_filho_mb`, que passamos a armar nele de propósito
    (opção 1). Se só o primeiro contasse, um `dwg2dxf` morto pelo limite que
    **nós** demos a ele — com o pai sem orçamento, como acontece fora do
    pipeline — voltaria a ser lido como insuficiência de motor, que é exatamente
    a mentira que este achado veio tirar da tela.

    **Por que a conclusão é "nosso teto" e não "motor quebrado".** Medido em
    09/08/2026: três DWGs que o `dwg2dxf` converte com código 0 e `EOF` válido
    quando roda solto morrem com `SIGSEGV` sob o `RLIMIT_AS` de 1536 MB — os três,
    de forma reprodutível, com e sem `ulimit -v`. Os intermediários que eles
    produzem têm 705 MB, 1,05 GB e 952 MB; não cabem, o `malloc` falha, e o
    LibreDWG não confere o retorno.

    **Não dá para distinguir com certeza**, e a escolha de qual erro assumir é
    deliberada: um `SIGSEGV` sob teto armado pode, em tese, ser um defeito do
    LibreDWG que nada tem a ver com memória. Na dúvida a plataforma assume a
    culpa — porque a alternativa é `MotorInsuficiente`, que **manda o cliente
    pagar** por um erro que talvez seja nosso. Errar para o lado de pedir
    desculpa custa uma conversão; errar para o outro custa a confiança de quem
    paga. Sem teto armado nada muda: ali o sinal é do motor, e a classificação
    antiga vale.
    """
    if returncode not in SINAIS_DE_FALTA_DE_MEMORIA:
        return False
    return bool(teto_do_filho_mb) or orcamento_armado()


def rodar(argumentos: list[str], *, timeout: int,
          memoria_mb: int = 0) -> subprocess.CompletedProcess:
    """Subprocesso com timeout obrigatório, traduzindo falha em `ErroDeConversao`.

    Timeout é parâmetro sem default de propósito: um motor externo travado
    segura um worker do Celery indefinidamente, e o worker que some é o mesmo
    que atenderia os outros tenants. Quem chama tem de ter pensado no número.

    **`memoria_mb` dá ao filho um teto PRÓPRIO** (D78, opção 1). Sem ele o filho
    herda o `RLIMIT_AS` do pai, e aí duas coisas ruins acontecem juntas: o teto
    que foi dimensionado para o trabalho **em processo** passa a valer para um
    programa em C que tem outro perfil de alocação, e o estouro chega até nós
    como morte por sinal — sem `MemoryError`, sem motivo, indistinguível de um
    defeito do motor. Com teto próprio o filho cai sozinho, no seu próprio
    limite, e o pai continua com o orçamento que orçou.

    `preexec_fn` roda no filho depois do `fork` e antes do `exec`: ali o processo
    ainda pode **subir** o limite flexível até o duro, que `teto_de_memoria`
    preserva de propósito. Fora do Linux (ou sem `RLIMIT_AS`) o parâmetro é
    ignorado, como o resto dos tetos.
    """
    def _armar_no_filho() -> None:
        # Roda no filho, entre `fork` e `exec`. Silencioso ao falhar **aqui e só
        # aqui**: levantar mataria a conversão por causa do guarda-corpo, e o
        # ruído da lição do D21 já sai do lado do pai, que sabe logar. Sem o
        # teto, o filho volta a correr sob o limite herdado — o comportamento
        # anterior, não um buraco novo.
        try:
            duro = resource.getrlimit(resource.RLIMIT_AS)[1]
            teto = memoria_mb * 1024 * 1024
            if duro != resource.RLIM_INFINITY:
                teto = min(teto, duro)
            resource.setrlimit(resource.RLIMIT_AS, (teto, duro))
        except (ValueError, OSError):  # pragma: no cover - sem permissão
            pass

    limitar = _armar_no_filho if (memoria_mb and hasattr(resource, "RLIMIT_AS")) else None

    try:
        return subprocess.run(  # noqa: S603 - argumentos montados por nós, sem shell
            argumentos, capture_output=True, timeout=timeout, check=False,
            preexec_fn=limitar,  # noqa: PLW1509 - thread principal, como o teto do D57
        )
    except subprocess.TimeoutExpired as exc:
        raise TempoExcedido(f"O motor excedeu {timeout}s.") from exc
    except OSError as exc:
        raise MotorIndisponivel(f"Não consegui executar o motor: {exc}") from exc
