"""Índice de snap — os pontos notáveis do desenho, para a mira grudar no traço.

**Por que existe.** Medir clicando "por cima" da linha entrega o número errado com
cara de certo: dois cliques a três pixels de distância do canto real, numa folha
onde 1 px vale 4 cm, viram 8 cm de erro numa cota que ninguém confere. O CAD
resolveu isso há trinta anos com o OSNAP, e é isso que este módulo reconstrói —
a mira gruda na extremidade, no meio, no centro e no cruzamento.

**De onde sai a geometria, e por que não das entidades.** O `MotorDxf` já grava
todo o desenho num `Recorder` antes de emitir o SVG (ver `dxf.py::_gravar`), e é
desse gravador — não do `modelspace` cru — que este índice sai. A diferença não é
de gosto: o gravador guarda a geometria **já achatada**, com transformação de
bloco, XREF e escala de inserção aplicadas. Percorrer as entidades cruas daria
pontos no sistema de coordenadas do bloco, e a mira grudaria a metros do traço
que a pessoa está vendo — o pior defeito possível numa ferramenta cujo produto é
apontar *onde*.

**O espaço de coordenadas é o da folha, não o do desenho.** A saída já vem
normalizada na mesma convenção do `Ponto` do frontend (os dois eixos divididos
pela LARGURA, Y invertido), porque quem consome é a tela.

**E a geometria entra já no espaço do SVG emitido — foi o que fechou o D90.**
Ver `do_svg()` e o chamador em `dxf.py::_folha`. O índice é tirado do gravador do
próprio `SVGBackend` DEPOIS de o arquivo sair, então os números que ele indexa
são literalmente os que estão escritos nos `<path>`, e normalizar é uma divisão
pela largura do `viewBox`. Não há página recalculada em lugar nenhum, e é isso
que mata as duas metades do achado:

1. **a página deduzida não é a emitida.** `largura_do_desenho + 2·MARGEM_MM`
   parece a conta do `ezdxf` e não é: ele arredonda a página para 0,1 mm,
   reescala o conteúdo para caber (`fit_page`) e centraliza a sobra dentro das
   margens. Sobra um erro de escala que some no enquadramento, cresce com o zoom
   e **muda a cada prancha** — medido em 15/08/2026, 0,04 px na `001` (folha
   861×614 mm, redonda) e 8,7 px de mediana na `Banco` (112,7×65,5 mm), a 81×;
2. **emitir o SVG destrói a geometria de quem a emprestou.** `Player.replay()`
   repassa `PathRecord` e `FilledPathsRecord` **por referência** ao gravador do
   backend, e o `get_string()` transforma esses registros *in place* para o
   espaço do `viewBox`. Indexar o player de origem depois disso lê um espaço
   misto — linha em milímetro, arco em unidade de `viewBox` — e a segunda metade
   cai inteira no filtro de "fora da folha". Na `01_02-DETALHE_DAS_SAPATAS`, 1.699
   de 3.214 registros: todo arco, círculo, polilinha, hachura e texto da prancha
   sumiam do índice **em silêncio**, e a mira ia grudar no vértice de linha mais
   próximo, que é outro lugar.

O ponto 2 é também o "fantasma" que a medição de 15/08/2026 viu: os ~516 mil
pontos fora da folha na `001` não eram geometria inventada, eram o desenho dela
em coordenada de `viewBox` — e, antes do filtro, comiam o teto do plano.

**O que este índice deliberadamente não indexa: hachura, sólido e texto.** É a
regra do AutoCAD, onde OSNAP não pega em hachura nem em contorno de letra, e aqui
ela foi *medida* antes de virar regra. O `FilledPathsRecord` — que é hachura,
sólido e glifo de texto renderizado em contorno — rendia **95% do índice** da
prancha `001` (61.257 de 64.264 pontos), e no navegador, a 81×:

| origem | mediana até o traço | p90 | sobre o traço |
| --- | ---: | ---: | ---: |
| reta, arco, polilinha | 0,0 px | 0,0 px | **95%** |
| preenchimento | 1,0 px | 25 px | **52%** |

Metade dos pontos de preenchimento **não tem tinta embaixo**: o contorno de uma
hachura é a fronteira de um `<pattern>`, não um traço desenhado. E como eles
entravam como `EXTREMIDADE`, caíam na faixa 0 do desempate — ganhavam da parede
que a pessoa estava mirando. O resultado era a mira acender a dezenas de pixels
do que se queria medir, em cima de nada.

Não é economia (embora o índice caia de 64.264 para 3.007 pontos e o sidecar de
7,8 MB para ~30 KB): é a diferença entre oferecer ponto onde há desenho e
oferecer ponto onde há preenchimento. Ninguém mede até o contorno de uma letra.
"""
from __future__ import annotations

import math
import struct
import sys
from array import array
from typing import Callable, NamedTuple

#: Margem da folha, em mm. Espelha `dxf.MARGEM_MM` — importar de lá criaria ciclo
#: (o `dxf` é quem chama este módulo), e o valor é geometria de página, não teto
#: de plano: fica fora do `payment/planos.py` pela §5.6 da planta.
MARGEM_MM = 10

#: Os tipos de ponto, no fio do que o AutoCAD chama de OSNAP. O número viaja no
#: sidecar como um byte — o nome é do lado da tela.
EXTREMIDADE = 0
MEIO = 1
CENTRO = 2
QUADRANTE = 3
NO = 4
INTERSECAO = 5

NOME_DO_TIPO = {
    EXTREMIDADE: "extremidade",
    MEIO: "meio",
    CENTRO: "centro",
    QUADRANTE: "quadrante",
    NO: "no",
    INTERSECAO: "intersecao",
}

#: Achatamento das curvas, em fração da largura da folha. Uma curva vira
#: polilinha para poder cruzar e para ter "meio"; abaixo disto o erro do
#: achatamento é menor que o pixel da tela em qualquer zoom praticável.
#:
#: **Relativo, e não fixo**, porque fixo seria grosseiro numa peça de 1 m e
#: ruinosamente caro num levantamento de 8,5 km — a mesma armadilha que o recorte
#: do `_folha` já resolve do mesmo jeito. Quem o converte para a unidade certa é
#: o construtor da `Folha`, porque é ele que sabe em que espaço o player fala.
ACHATAMENTO_RELATIVO = 1e-4

#: Dois pontos mais perto que isto (em fração da largura) são o mesmo ponto.
#: Existe porque o desenho real repete vértice: a parede desenhada como quatro
#: linhas soltas tem quatro extremidades coincidentes em cada canto, e sem a
#: fusão o índice cresce ~4x sem ganhar um único lugar novo onde grudar.
#:
#: **É só o piso de quem não emite SVG** (a bancada, o teste). Quem emite usa
#: uma unidade da grade que de fato saiu (`do_svg`), porque abaixo dela dois
#: pontos são indistinguíveis **no arquivo** — e porque 1e-6 da largura vale
#: 0,00086 unidade de desenho numa folha A1: mais grosso que a quinta casa
#: decimal, e portanto capaz de fundir dois vértices que o projeto distingue.
TOLERANCIA_FUSAO = 1e-6

#: Lado da célula da grade de varredura, em fração da largura. A interseção só é
#: procurada entre segmentos que dividem célula — é o que troca o O(n²) do
#: todos-contra-todos por O(n log n + k). 1/512 deixa a célula média com poucos
#: segmentos em prancha de arquitetura.
CELULAS_POR_LARGURA = 512

#: O "sem teto" do Sob Medida. Não é infinito de verdade: é o maior índice que
#: ainda cabe num navegador (~2 GB de sidecar seriam recusados muito antes).
#: Existir como número, e não como `None` circulando pelo laço quente, evita um
#: `if` por ponto no caminho mais executado do módulo.
SEM_TETO = 100_000_000

#: Quantas células um único segmento pode tocar antes de a travessia desistir.
#: Com a grade de 512, a diagonal da folha toca ~1.024 — nada legítimo passa
#: disto. É rede contra coordenada corrompida virar laço infinito no worker.
TETO_DE_CELULAS_POR_SEGMENTO = 4096

#: Teto de segmentos numa célula antes de desistir de cruzar aquela célula.
#: Célula com mais que isto é hachura, pontilhado ou nuvem de revisão que
#: escapou do filtro — cruzar ali gasta o orçamento inteiro para produzir
#: interseção que ninguém vai querer. Registrado no relatório, não silenciado.
TETO_DE_SEGMENTOS_POR_CELULA = 256


#: Precedência na fusão: dois pontos no mesmo lugar viram o mais útil. Entre
#: "extremidade" e "meio" coincidentes, a extremidade é a que a pessoa quis.
PRECEDENCIA = {EXTREMIDADE: 0, INTERSECAO: 1, CENTRO: 2, QUADRANTE: 3, NO: 4, MEIO: 5}


class Indice:
    """O índice de uma folha, pronto para virar sidecar.

    **Guarda em `array` e funde na inserção, e isso é medido.** A primeira versão
    acumulava tuplas Python e fundia no fim: 0,35 KB por ponto, 281 MB para a
    prancha de 971 mil pontos — memória que é objeto do interpretador, não
    geometria. O desenho real repete muito vértice (a parede feita de quatro
    linhas soltas tem quatro extremidades em cada canto), então segurar as
    duplicatas até o fim é pagar pelo que vai ser jogado fora. Fundindo na
    entrada, o pico passa a ser o do resultado, não o do bruto.

    A chave da fusão é **um inteiro**, não a tupla `(cx, cy)`: são dois objetos a
    menos por ponto num dicionário que chega a centenas de milhares de entradas.
    """

    __slots__ = ("_x", "_y", "_tipo", "_onde", "segmentos", "truncado", "censo",
                 "_limite_y", "_fora", "fusao")

    def __init__(self) -> None:
        #: Teto do Y da folha. Começa generoso e é apertado por
        #: `descartar_fora()` assim que a envolvente é conhecida.
        self._limite_y = float("inf")
        self._fora = 0
        #: Quem constrói a partir de uma `Folha` sobrescreve com a régua dela.
        self.fusao = TOLERANCIA_FUSAO
        # **`d` e não `f`.** Em coordenada normalizada, o float32 dá degrau de
        # 6e-8 — que numa folha A1 vale 0,00005 unidade de desenho, mais grosso
        # que a quinta casa decimal que o sistema promete. O float64 dá 1e-13 na
        # mesma folha. Custa o dobro de sidecar (51 KB → 100 KB na `001`), e o
        # que ele compra é a coordenada chegar à tela sem ser truncada.
        self._x = array("d")
        self._y = array("d")
        self._tipo = array("B")
        #: chave espacial -> índice em `_x`/`_y`/`_tipo`
        self._onde: dict[int, int] = {}
        #: (x1, y1, x2, y2) achatados — alimenta perpendicular e próximo na tela.
        self.segmentos = array("d")
        #: Verdadeiro quando o teto cortou: a tela precisa dizer "snap parcial".
        self.truncado = False
        self.censo: dict = {}

    #: Fora deste retângulo (em coordenada de folha) o ponto não é desta prancha.
    #: A folha vai de 0 a 1 em X e de 0 a `altura/largura` em Y; a folga cobre o
    #: `FOLGA_RECORTE` e o arredondamento da emissão.
    FOLGA = 0.02

    def descartar_fora(self, altura_da_folha: float) -> int:
        """Marca o limite da folha. Devolve quantos pontos já entraram fora.

        **Hoje é rede, e o que ela pega é NOTÍCIA.** A geometria vem do gravador
        do `SVGBackend`, e o que o `ezdxf` colocou na página que ele mesmo
        dimensionou está na página por construção. Ponto fora daqui significa que
        o índice recebeu coordenada de outro espaço — sai na memória de conversão
        como `snap_fora_da_folha` para ser investigado, não para virar paisagem.

        **E "paisagem" é literalmente o que ele já foi.** Em 15/08/2026 este
        filtro nasceu para matar um "fantasma": o índice da `001` saía com X indo
        até 1126 e Y até −794, e ele cortou 516.587 dos 517.214 pontos. A leitura
        da época foi que o extrator colhia registros que o SVG não desenha. Era o
        contrário: `1126 ≈ 10⁶/861` é a folha inteira em unidade de `viewBox`
        dividida pela largura da página em mm — o desenho **de verdade**, no
        espaço errado, porque a emissão do SVG transformava a geometria por baixo
        de quem a emprestara (D90). O filtro estava jogando fora todo arco,
        círculo, polilinha, hachura e texto da prancha, e o "conserto" de então
        apenas escondeu isso melhor.

        Fica a lição, que é do tamanho do módulo: **descarte em massa não é
        limpeza, é sintoma.** Um filtro que corta 99,9% do que recebe está
        descrevendo um defeito a montante, e silenciá-lo custou três tentativas.
        """
        self._limite_y = altura_da_folha + self.FOLGA
        return self._fora

    def adicionar(self, x: float, y: float, tipo: int) -> None:
        """Registra um ponto notável, fundindo com o que já ocupa o lugar."""
        if not (math.isfinite(x) and math.isfinite(y)):
            return
        if not (-self.FOLGA <= x <= 1 + self.FOLGA
                and -self.FOLGA <= y <= self._limite_y):
            self._fora += 1
            return
        # `& 0xFFFFFFF` prende a chave a 28 bits por eixo: a folha normalizada
        # vive em [0, ~1] no X, e o Y estoura 1,0 só no retrato extremo. Sem a
        # máscara, coordenada absurda vinda de desenho corrompido geraria chave
        # gigante e o dicionário viraria o custo que ele existe para evitar.
        chave = ((int(x / self.fusao) & 0xFFFFFFF) << 28) | (
            int(y / self.fusao) & 0xFFFFFFF)
        onde = self._onde.get(chave)
        if onde is None:
            self._onde[chave] = len(self._tipo)
            self._x.append(x)
            self._y.append(y)
            self._tipo.append(tipo)
        elif PRECEDENCIA[tipo] < PRECEDENCIA[self._tipo[onde]]:
            # **A coordenada vai junto com o tipo.** Guardar só o tipo novo
            # deixava o ponto na posição do PRIMEIRO que caiu no balde: o meio de
            # um segmento virava "extremidade" sem sair do meio. O erro é de até
            # uma tolerância de fusão — invisível no enquadramento, mas a mira
            # existe justamente para quem amplia até o ponto de o fio de cabelo
            # importar, e ali ele aparece.
            self._x[onde] = x
            self._y[onde] = y
            self._tipo[onde] = tipo

    def _na_folha(self, x: float, y: float) -> bool:
        return (math.isfinite(x) and math.isfinite(y)
                and -self.FOLGA <= x <= 1 + self.FOLGA
                and -self.FOLGA <= y <= self._limite_y)

    def segmento(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Só entra o segmento inteiramente na folha.

        A mesma razão dos pontos: o "próximo sobre o traço" tem de cair sobre
        traço que existe na tela. Um segmento com uma ponta fora arrastaria a
        mira para fora da prancha, e ali não há desenho para conferir.
        """
        if not (self._na_folha(x1, y1) and self._na_folha(x2, y2)):
            self._fora += 1
            return
        self.segmentos.extend((x1, y1, x2, y2))

    def total(self) -> int:
        return len(self._tipo)

    def total_de_segmentos(self) -> int:
        return len(self.segmentos) // 4

    def ponto(self, i: int) -> tuple[float, float, int]:
        return (self._x[i], self._y[i], self._tipo[i])

    def censo_por_tipo(self) -> dict:
        contagem: dict[str, int] = {}
        for t in self._tipo:
            nome = NOME_DO_TIPO[t]
            contagem[nome] = contagem.get(nome, 0) + 1
        return contagem


class Folha(NamedTuple):
    """A régua da folha — e, com ela, **em que espaço o `player` fala**.

    `para_folha` leva a coordenada do player à normalizada da tela; `altura` é
    onde a folha acaba no eixo Y na mesma normalização (os dois eixos pela
    LARGURA), e é o limite do `descartar_fora`. No retrato ela passa de 1,0, e
    está certo. `achatamento` é a tolerância de achatamento de curva **nas
    unidades do player** — anda junto porque é a mesma escolha de espaço: separá-la
    foi o que deixou o D90 achatar curva com tolerância de milímetro sobre
    geometria já em unidade de `viewBox`.

    Os dois construtores abaixo são as duas respostas possíveis, e o par
    `(player, folha)` tem de vir do mesmo.
    """

    para_folha: Callable[[float, float], tuple[float, float]]
    altura: float
    achatamento: float
    #: Distância abaixo da qual dois pontos são o mesmo, **em coordenada de
    #: folha**. Sai daqui e não de uma constante global pela mesma razão que o
    #: achatamento: fundir por um número fixo é grosseiro numa folha e fino
    #: demais noutra. Ver `TOLERANCIA_FUSAO`.
    fusao: float = TOLERANCIA_FUSAO


def do_svg(viewbox_largura: float, viewbox_altura: float) -> Folha | None:
    """A folha de um player que já está **no espaço do SVG emitido**.

    É o caminho de produção, e a razão de o D90 fechar: quem indexa é o gravador
    do próprio `SVGBackend` depois de o arquivo sair, então os números do índice
    são os mesmos que estão escritos nos `<path>` e não há transformação nenhuma
    a reproduzir — só uma divisão.

    **Dividir os dois eixos pela largura do `viewBox` é exatamente o que a tela
    faz.** O `<img>` recebe `width = largura_natural` e `height = largura_natural
    · vbH/vbW` (ver `espessura.ts::aspecto`), então um pixel vale
    `vbW/largura_natural` unidades de `viewBox` nos DOIS eixos. Normalizar por
    `vbW` é a mesma conta, do outro lado do fio.
    """
    if viewbox_largura <= 0 or not math.isfinite(viewbox_largura):
        return None
    if viewbox_altura <= 0 or not math.isfinite(viewbox_altura):
        return None

    escala = 1.0 / viewbox_largura

    def para_folha(x: float, y: float) -> tuple[float, float]:
        return (x * escala, y * escala)

    # **Fundir por UMA unidade da grade emitida.** Abaixo disso os dois pontos
    # ocupam o mesmo inteiro no `<path>` — são o mesmo lugar no arquivo, e
    # distingui-los seria inventar informação que o SVG não carrega. Acima
    # disso, fundir apaga vértice que o projeto separa: com a grade dimensionada
    # para a quinta casa decimal, uma unidade **é** a quinta casa decimal.
    return Folha(para_folha, viewbox_altura * escala,
                 max(viewbox_largura * ACHATAMENTO_RELATIVO, 1e-9),
                 escala)


def normalizador(envolvente) -> Folha | None:
    """A folha **deduzida** da envolvente, para um player em unidade de desenho.

    Reproduz a página que o `ezdxf` monta com `Page(0, 0, …,
    Margins.all(MARGEM_MM))` e `scale=1`: `largura_do_desenho + 2·MARGEM_MM`, com
    os dois eixos divididos pela largura e o Y invertido.

    **É aproximada, e serve a quem não emite SVG** — a bancada que mede custo, o
    teste que só quer contar pontos. O D90 mediu o preço: o `ezdxf` arredonda a
    página para 0,1 mm, reescala o conteúdo para caber e centraliza a sobra, e
    nada disso cabe nesta conta. Sobra um erro de escala que some no
    enquadramento e chega a dezenas de pixels no zoom alto — tolerável para
    contar, inaceitável para grudar a mira. Quem emite SVG usa `do_svg()`.
    """
    xmin, ymin, xmax, ymax = envolvente
    largura = (xmax - xmin) + 2 * MARGEM_MM
    if largura <= 0 or not math.isfinite(largura):
        return None

    def para_folha(x: float, y: float) -> tuple[float, float]:
        return ((MARGEM_MM + (x - xmin)) / largura,
                (MARGEM_MM + (ymax - y)) / largura)

    return Folha(para_folha, ((ymax - ymin) + 2 * MARGEM_MM) / largura,
                 max(largura * ACHATAMENTO_RELATIVO, 1e-9))


def indice_de_snap(player, envolvente=None, *, teto: int,
                   folha: Folha | None = None) -> Indice:
    """Extrai os pontos notáveis de uma folha já gravada.

    **`player` e `folha` têm de falar o mesmo espaço**, e essa é a única regra
    difícil deste módulo. Em produção os dois vêm do SVG emitido: o gravador do
    `SVGBackend` e o `do_svg()` do `viewBox` dele. Fora dela — bancada de medição,
    teste de contagem — vêm em unidade de desenho, e aí basta `envolvente`, de
    onde sai um `normalizador()`. Misturar os dois é o D90.

    `envolvente` é a caixa do grupo em unidades de desenho, a mesma que vai para
    `Parte.caixa`; só é lida quando `folha` não vem. `teto` é o número de pontos
    que o plano do tenant paga; passou disso, corta e marca `truncado`.

    Entra o que se mede — reta, arco, polilinha e ponto solto. Preenchimento
    (hachura, sólido, texto) fica de fora inteiro; ver `_snapavel` e o cabeçalho.

    **O teto é MOLE, e de propósito.** Ele é conferido entre registros, não entre
    pontos: uma polilinha longa soma milhares de vértices numa chamada só, então
    o índice pode passar do teto pela cauda do registro que o cruzou. Medido no
    acervo, o excesso ficou entre 98 e 13.186 pontos sobre 600.000 — 2,2% no pior
    caso, ~143 KB de sidecar. Conferir a cada ponto custaria um `if` no laço mais
    executado do módulo para economizar o que cabe numa margem de erro, e erraria
    para o lado ERRADO: entregaria menos do que o cliente pagou. `truncado`
    continua verdade em todos eles, que é o que a tela precisa saber.
    """
    indice = Indice()
    if folha is None and envolvente is not None:
        folha = normalizador(envolvente)
    if folha is None:
        return indice
    indice.fusao = folha.fusao
    para_folha = folha.para_folha
    # A folha vai de 0 a 1 em X; em Y vai até a altura, normalizada pela mesma
    # LARGURA. Daqui em diante, ponto fora disso é descartado — ver o método.
    indice.descartar_fora(folha.altura)

    achatamento = folha.achatamento
    censo = {"linhas": 0, "caminhos": 0, "preenchimentos": 0, "pontos_soltos": 0,
             "celulas_densas": 0}

    magros, ignorados = _snapavel(player)
    if ignorados:
        censo["preenchimentos_ignorados"] = ignorados

    for registro, _props in magros:
        _colher(registro, indice, para_folha, achatamento, censo, cruzavel=True)
        if indice.total() >= teto:
            indice.truncado = True
            break

    if not indice.truncado:
        _cruzar(indice, teto, censo)

    # Sem truncamento silencioso: quem lê a memória de conversão precisa saber
    # que houve geometria fora da folha, e quanta.
    fora = indice.descartar_fora(indice._limite_y - Indice.FOLGA)
    if fora:
        censo["pontos_fora_da_folha"] = fora
    indice.censo = censo
    return indice


def _snapavel(player):
    """Os registros em que se mede — e quantos ficaram de fora.

    O preenchimento (`FilledPathsRecord`) é hachura, sólido e texto renderizado
    em contorno, e **não entra**: é a regra do AutoCAD e o resultado da medição
    do cabeçalho deste módulo. Já entrou; era 95% do índice e metade dos pontos
    não tinha traço embaixo.

    O descartado é **contado**, não silenciado — é o número que diz se uma
    prancha ficou sem mira por ser só hachura, em vez de o cliente descobrir
    isso mirando.
    """
    magros, ignorados = [], 0
    for registro, props in getattr(player, "recordings", lambda: [])():
        if type(registro).__name__ == "FilledPathsRecord":
            ignorados += 1
            continue
        magros.append((registro, props))
    return magros, ignorados


def _colher(registro, indice: Indice, para_folha, achatamento, censo, *, cruzavel: bool):
    """Tira de um registro os pontos e segmentos que ele rende."""
    nome = type(registro).__name__

    if nome == "PointsRecord":
        vertices = registro.points.vertices()
        if len(vertices) == 1:
            censo["pontos_soltos"] += 1
            indice.adicionar(*para_folha(*vertices[0]), NO)
        elif len(vertices) == 2:
            censo["linhas"] += 1
            _colher_polilinha(vertices, indice, para_folha, fechada=False,
                              cruzavel=cruzavel)
        elif len(vertices) > 2:
            censo["preenchimentos"] += 1
            _colher_polilinha(vertices, indice, para_folha, fechada=True,
                              cruzavel=cruzavel)
        return

    if nome == "SolidLinesRecord":
        vertices = registro.lines.vertices()
        censo["linhas"] += len(vertices) // 2
        for i in range(0, len(vertices) - 1, 2):
            _colher_polilinha(vertices[i:i + 2], indice, para_folha,
                              fechada=False, cruzavel=cruzavel)
        return

    if nome != "PathRecord":
        # `ImageRecord` e o que vier depois: sem geometria de traço. O
        # `FilledPathsRecord` também cai aqui, mas nem chega — o `_snapavel` o
        # barra antes, e é de propósito (hachura, sólido e texto não têm OSNAP).
        return

    censo["caminhos"] += 1
    for sub in registro.path.sub_paths():
        _colher_caminho(sub, indice, para_folha, achatamento, cruzavel=cruzavel)


def _colher_caminho(sub, indice: Indice, para_folha, achatamento, *, cruzavel: bool):
    """Um sub-caminho: achata, e reconhece círculo quando é círculo."""
    try:
        vertices = [(v.x, v.y) for v in sub.flattening(achatamento)]
    except Exception:
        try:
            vertices = [(v[0], v[1]) for v in sub.vertices()]
        except Exception:
            return
    if len(vertices) < 2:
        return

    fechada = bool(getattr(sub, "is_closed", False))

    # **Centro e quadrante só em curva FECHADA, e isso é honestidade.** Num
    # círculo ou elipse o centro da envolvente É o centro da figura, e os meios
    # das arestas da envolvente são os quadrantes — exato. Num ARCO aberto a
    # envolvente não contém o centro, e publicá-lo daria uma mira que gruda no
    # vazio. Arco aberto entrega extremidade e meio-do-arco, que são verdade.
    if fechada and bool(getattr(sub, "has_curves", False)):
        xs = [v[0] for v in vertices]
        ys = [v[1] for v in vertices]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        indice.adicionar(*para_folha(cx, cy), CENTRO)
        for qx, qy in ((x1, cy), (x0, cy), (cx, y1), (cx, y0)):
            indice.adicionar(*para_folha(qx, qy), QUADRANTE)

    _colher_polilinha(vertices, indice, para_folha, fechada=fechada, cruzavel=cruzavel)


def _colher_polilinha(vertices, indice: Indice, para_folha, *, fechada: bool,
                      cruzavel: bool):
    """Extremidades, meios e segmentos de uma sequência de vértices."""
    pares = list(vertices)
    if fechada and len(pares) > 2 and pares[0] != pares[-1]:
        pares.append(pares[0])

    # Extremidade em TODO vértice, não só nas pontas: o vértice interno de uma
    # polilinha é canto de parede, e é nele que se mede.
    for x, y in pares:
        indice.adicionar(*para_folha(x, y), EXTREMIDADE)

    for i in range(len(pares) - 1):
        (ax, ay), (bx, by) = pares[i], pares[i + 1]
        if ax == bx and ay == by:
            continue
        indice.adicionar(*para_folha((ax + bx) / 2, (ay + by) / 2), MEIO)
        if cruzavel:
            na, nb = para_folha(ax, ay), para_folha(bx, by)
            indice.segmento(na[0], na[1], nb[0], nb[1])


def _cruzar(indice: Indice, teto: int, censo: dict):
    """Interseções por varredura em grade.

    Todos-contra-todos numa planta de 300 mil segmentos são 4,5×10¹⁰ pares — a
    mesma classe do estouro de 62 GB do D57. A grade só compara segmentos que
    dividem célula: o par que cruza necessariamente divide pelo menos uma, então
    nada verdadeiro se perde, e o custo cai para o número de pares plausíveis.
    """
    total = indice.total_de_segmentos()
    if total < 2:
        return
    segs = indice.segmentos

    grade: dict[int, list[int]] = {}
    lado = 1.0 / CELULAS_POR_LARGURA
    for i in range(total):
        x1, y1, x2, y2 = segs[4 * i:4 * i + 4]
        # **A máscara não é enfeite.** A célula pode ser NEGATIVA: a folha é
        # recortada pela envolvente do seu grupo, mas o traço na borda do recorte
        # e o `FOLGA_RECORTE` põem coordenada um fio acima de `ymax`, e ali `ny`
        # fica abaixo de zero. Sem mascarar, `cy = -1` invade os bits do `cx` e
        # células distantes colidem — o sintoma foi 626 "células densas" e o
        # tempo triplicando, porque a colisão empilha segmento que não se toca.
        for cx, cy in _celulas_do_segmento(x1, y1, x2, y2, lado):
            grade.setdefault(_celula(cx, cy), []).append(i)

    # O par já conferido não se reconfere: dois segmentos longos dividem várias
    # células, e sem isto o mesmo cruzamento seria calculado uma vez por célula.
    vistos: set[int] = set()
    for indices in grade.values():
        if len(indices) < 2:
            continue
        if len(indices) > TETO_DE_SEGMENTOS_POR_CELULA:
            censo["celulas_densas"] += 1
            continue
        for a in range(len(indices)):
            i = indices[a]
            # Desempacotado uma vez por segmento, não uma por par: fatiar o
            # `array` cria um objeto novo a cada comparação, e numa célula cheia
            # isso é o dobro do custo da conta de interseção em si.
            p = 4 * i
            x1, y1, x2, y2 = segs[p], segs[p + 1], segs[p + 2], segs[p + 3]
            for b in range(a + 1, len(indices)):
                j = indices[b]
                par = (i << 32) | j
                if par in vistos:
                    continue
                vistos.add(par)
                q = 4 * j
                ponto = _intersecao(x1, y1, x2, y2,
                                    segs[q], segs[q + 1], segs[q + 2], segs[q + 3])
                if ponto is not None:
                    indice.adicionar(ponto[0], ponto[1], INTERSECAO)
                    if indice.total() >= teto:
                        indice.truncado = True
                        return


def _celula(cx: int, cy: int) -> int:
    """Chave da célula, à prova de coordenada negativa (ver `_cruzar`)."""
    return ((cx & 0xFFFFF) << 20) | (cy & 0xFFFFF)


def _celulas_do_segmento(x1, y1, x2, y2, lado):
    """As células que o segmento REALMENTE atravessa (Amanatides & Woo).

    **Percorrer a caixa do segmento é a armadilha, e ela custa duas coisas.** Uma
    diagonal que cruza a folha tem caixa de ~430×430 células — 185 mil — quando a
    linha toca só ~860. A primeira versão fugia disso registrando o segmento
    longo apenas pelas duas pontas, e o preço foi silencioso e pior: dois eixos
    que atravessam a prancha **nunca dividiam célula**, então o cruzamento deles
    não existia. Justamente o caso que mais importa — quem mede de um eixo de
    pilar até outro está medindo exatamente ali.

    A travessia exata resolve os dois: custo proporcional ao comprimento, e a
    garantia de que dois segmentos que se cruzam compartilham a célula onde o
    cruzamento cai — que é o que faz a varredura não perder par verdadeiro.
    """
    cx, cy = _piso(x1, lado), _piso(y1, lado)
    cxf, cyf = _piso(x2, lado), _piso(y2, lado)
    yield cx, cy
    if cx == cxf and cy == cyf:
        return

    dx, dy = x2 - x1, y2 - y1
    passo_x = 1 if dx > 0 else -1
    passo_y = 1 if dy > 0 else -1
    infinito = float("inf")
    if dx:
        prox_x = ((cx + (1 if dx > 0 else 0)) * lado - x1) / dx
        salto_x = lado / abs(dx)
    else:
        prox_x = salto_x = infinito
    if dy:
        prox_y = ((cy + (1 if dy > 0 else 0)) * lado - y1) / dy
        salto_y = lado / abs(dy)
    else:
        prox_y = salto_y = infinito

    # Rede de segurança: com a grade de 512 uma diagonal toca ~1.024 células, e
    # nada legítimo passa disto. O teto existe para que coordenada corrompida
    # (NaN que escapou, envolvente degenerada) não vire laço infinito no worker.
    for _ in range(TETO_DE_CELULAS_POR_SEGMENTO):
        if prox_x < prox_y:
            if prox_x > 1.0:
                return
            cx += passo_x
            prox_x += salto_x
        else:
            if prox_y > 1.0:
                return
            cy += passo_y
            prox_y += salto_y
        yield cx, cy
        if cx == cxf and cy == cyf:
            return


def _piso(valor: float, lado: float) -> int:
    """Índice da célula. `//` e não `int()`: em coordenada negativa o `int()`
    trunca para zero e faz `-0,5` e `+0,5` caírem na mesma célula."""
    return int(valor // lado)


def _intersecao(x1, y1, x2, y2, x3, y3, x4, y4):
    """O ponto onde dois segmentos se cruzam, ou `None`.

    Cruzamento **próprio**: encostar na ponta já virou extremidade, e devolver o
    mesmo lugar como interseção só engorda o índice.
    """
    dx1, dy1 = x2 - x1, y2 - y1
    dx2, dy2 = x4 - x3, y4 - y3
    denominador = dx1 * dy2 - dy1 * dx2
    if denominador == 0.0:
        return None  # paralelos ou colineares
    t = ((x3 - x1) * dy2 - (y3 - y1) * dx2) / denominador
    u = ((x3 - x1) * dy1 - (y3 - y1) * dx1) / denominador
    folga = 1e-9
    if not (folga < t < 1 - folga and folga < u < 1 - folga):
        return None
    return (x1 + t * dx1, y1 + t * dy1)


def empacotar(indice: Indice) -> bytes:
    """Serializa o índice no sidecar binário que a tela baixa.

    **Binário e não JSON**, e a diferença não é estética: o mesmo milhão de
    pontos sai a 9 MB em JSON de texto e a 9 MB em binário, mas o JSON custa um
    parse que trava a aba por segundos no celular, enquanto o binário vira
    `Float64Array` com uma cópia de memória.

    Formato: `SNAP2` · uint32 n_pontos · uint32 n_segmentos · uint8 truncado ·
    float64[n] x · float64[n] y · uint8[n] tipos · float64[4m] segmentos.

    **`SNAP2` porque o `SNAP1` era float32, e float32 não chega à quinta casa
    decimal.** Em coordenada normalizada o degrau do 32 bits é 6×10⁻⁸, que numa
    folha A1 (861 unidades de desenho de largura) vale **0,00005 unidade** — a
    quarta casa, não a quinta. A frase antiga dizia que 32 bits eram "mais finos
    que o pixel em qualquer zoom", e ela envelheceu junto com o teto de zoom: a
    20.000× do enquadramento aquele degrau **é** visível. O dobro de bytes é o
    preço de a coordenada chegar à tela como está no projeto.

    O leitor da tela aceita os dois marcadores: sidecar antigo continua abrindo,
    com a precisão que ele tem — o que não se faz é reescrever a precisão de um
    arquivo que não a tem.

    **X e Y em blocos separados, não intercalados**, porque a busca do ponto mais
    próximo varre X primeiro para descartar candidatos: percorrer um bloco
    contíguo aproveita a linha de cache, e intercalar faria cada leitura puxar um
    Y que não vai ser usado.
    """
    n, m = indice.total(), indice.total_de_segmentos()
    # `tobytes()` e não `struct.pack`: o `array` já está no layout final
    # (float32 little-endian), então a serialização é uma cópia de memória em vez
    # de um milhão de conversões de objeto — e é o mesmo layout que o
    # `Float32Array` do navegador espera do outro lado.
    def octetos(vetor):
        # O `array` usa a ordem NATIVA da máquina; o `Float64Array` do navegador
        # também. Iguais no x86 e no ARM que servem hoje — mas um worker
        # big-endian entregaria coordenada embaralhada, e o defeito apareceria
        # como mira em lugar aleatório, longe daqui. Uma cópia só no caso raro.
        if sys.byteorder != "little":
            vetor = array(vetor.typecode, vetor)
            vetor.byteswap()
        return vetor.tobytes()

    return b"".join((
        b"SNAP2",
        struct.pack("<IIB", n, m, 1 if indice.truncado else 0),
        octetos(indice._x),
        octetos(indice._y),
        indice._tipo.tobytes(),  # uint8 não tem ordem de bytes
        octetos(indice.segmentos),
    ))
