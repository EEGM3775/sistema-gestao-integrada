"""Ler, consertar e separar o SVG que o `dwg2SVG` emite — o caminho do DWG (PRA.1e).

**Por que este módulo existe.** O caminho anterior (`dwg2dxf` → `ezdxf` → SVG)
**expandia cada inserção de bloco em geometria própria**: um desenho com 858
inserções de 250 blocos virava 47.610 traços, e o `ezdxf` materializava tudo na
memória — 945 MB e 13,9 s para um DWG de 43 MB (planta §4.1). O `dwg2SVG` emite
cada bloco **uma vez** (`<g id="symbol-…">`) e o referencia (`<use>`), e custa
**220 MB e 0,9 s** no mesmo arquivo. A diferença não é ajuste: é o modelo de
representação certo contra o errado.

**O que a troca exige, e é tudo o que este arquivo faz.** A saída do `dwg2SVG`
não é uma prancha — é matéria-prima, e em quatro sentidos, os quatro medidos em
10/08/2026:

1. **ela desenha o *paper space* por padrão.** Sem `--mspace` o SVG traz uma
   *vista* do modelo, não o modelo: no arquivo de referência, 5,1 MB e 13.060
   `<path>` contra 10,3 MB e 27.729 com a flag. O custo em RAM é o mesmo (os
   bytes vão para o stdout), então a flag é grátis — e obrigatória. Quem a passa
   é o `dwg.py`; fica registrado aqui porque é premissa do que se lê;
2. **o `viewBox` dela não contém o desenho.** Ele declara a caixa de um
   aglomerado e **0,3%** da geometria cai dentro (65 de 18.774 pontos no arquivo
   de referência). Por isso a envolvente é sempre **recalculada** aqui, nunca
   lida do cabeçalho;
3. **o texto sai com dois defeitos**, e nos piores lugares — carimbo, cota e
   legenda: os `%%`-códigos do CAD não são decodificados (`N.%%D` literal, onde
   `%%D` é o grau) e o `font-family` vem **cravado em `Courier`**, que é
   monoespaçada — a largura de glifo errada é justamente a causa de carimbo
   desalinhado e cota vazando da caixa (§4.3);
4. **ela não separa folha.** É o mesmo problema que a PRA.1c resolveu para o
   caminho anterior, e a solução é a mesma — literalmente: o agrupamento por
   lacuna vem de `dxf._agrupar`, importado, e **não** reimplementado. Ver a nota
   de `folhas()` sobre por que isso é contrato e não economia de código.

**O que este módulo NÃO faz:** não decide nada de plano, não fala com o banco e
não conhece `Saida`/`Parte` — recebe bytes e devolve bytes com a caixa de cada
um. Quem traduz para o vocabulário do motor é o `dwg.py`.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .dxf import MARGEM_MM, _agrupar, _envolvente

#: Os `%%`-códigos do CAD, que o `dwg2SVG` repassa crus para dentro do `<text>`.
#:
#: São três, e os três aparecem em cota e carimbo de prancha brasileira: grau em
#: ângulo e temperatura, ± em tolerância, ⌀ em diâmetro de tubo e de ferro. A
#: quarta entrada (`%%%` → `%`) é o escape do próprio código e vem **por último**
#: na aplicação, senão ela comeria o `%%` das outras.
#:
#: Maiúscula e minúscula porque o AutoCAD aceita as duas e o acervo tem as duas.
CODIGOS_DE_TEXTO = (
    (b"%%D", "°"), (b"%%d", "°"),
    (b"%%P", "±"), (b"%%p", "±"),
    (b"%%C", "⌀"), (b"%%c", "⌀"),
    (b"%%%", "%"),
)

#: A pilha de fontes que substitui o `Courier` cravado pelo `dwg2SVG`.
#:
#: **Não é escolha estética.** O texto de CAD brasileiro é escrito em SHX
#: (`txt`, `romans`, `isocp`) — traço fino, largura estreita e variável. Courier
#: é monoespaçada e larga: cada string ocupa mais que o dobro do avanço previsto,
#: o que estoura a caixa da cota e desalinha a coluna do carimbo. Nenhuma fonte
#: livre reproduz o SHX (é a decisão de licença em aberto na §12.10 da planta) —
#: o que se pode fazer sem essa decisão é **parar de errar para o lado largo**, e
#: uma sans condensada erra muito menos que uma monoespaçada.
#:
#: A ordem é a de disponibilidade decrescente no aparelho do canteiro; o
#: `sans-serif` final garante que nunca caia de volta na monoespaçada do
#: navegador.
FONTE_DO_CAD = "'Arial Narrow','Liberation Sans Narrow','Helvetica Neue',Arial,sans-serif"

_FONT_FAMILY = re.compile(rb'font-family="[^"]*"')

#: Os elementos de topo que carregam desenho. `<use>` está aqui e é o que faz
#: este caminho ser barato: ele é uma **referência**, não geometria.
_TAGS = rb"path|polygon|polyline|line|circle|ellipse|use|text"
_ELEMENTO = re.compile(rb"<(" + _TAGS + rb")\b", re.I)

_NUMERO = re.compile(rb"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_ATRIBUTO = re.compile(rb'([\w:-]+)\s*=\s*"([^"]*)"')

#: Teto de recursão ao resolver símbolo que referencia símbolo.
#:
#: O formato permite (um bloco insere outro), e um DWG corrompido pode fechar o
#: ciclo. Sem teto isso é recursão infinita dentro do worker — a família de
#: defeito que o D57 ensinou a não deixar sem freio. 32 é folgado: bloco aninhado
#: de verdade raramente passa de três níveis.
PROFUNDIDADE_MAXIMA = 32


@dataclass(frozen=True)
class Folha:
    """Um desenho separado, já como SVG que abre sozinho."""

    conteudo: bytes
    #: Envolvente em **unidade de desenho**, `(xmin, ymin, xmax, ymax)` — a mesma
    #: convenção do `Parte.caixa`, porque é ela que atravessa revisões (§4.5).
    caixa: tuple[float, float, float, float]
    tracos: int


def corrigir_texto(svg: bytes) -> bytes:
    """Os dois defeitos de texto do `dwg2SVG`, consertados na saída.

    Roda **antes** da separação, uma vez sobre o documento inteiro: os dois
    consertos são substituição byte a byte e não mexem em coordenada, então
    fazê-los depois seria repeti-los por folha sem ganho nenhum.
    """
    for codigo, letra in CODIGOS_DE_TEXTO:
        svg = svg.replace(codigo, letra.encode("utf-8"))
    return _FONT_FAMILY.sub(f'font-family="{FONTE_DO_CAD}"'.encode("utf-8"), svg)


def folhas(svg: bytes) -> tuple[list[Folha], int]:
    """Separa o SVG do motor nos desenhos que ele traz. `(folhas, truncados)`.

    **O agrupamento é o da PRA.1c, importado e não reescrito** — `dxf._agrupar`.
    Não é economia de código, é o que preserva a marcação: a âncora de uma
    marcação é normalizada pela largura da folha em que foi fincada, então uma
    folha que caia em lugar diferente do que o caminho anterior produzia deixaria
    o pino órfão (a família do D54). Mesmo critério sobre as mesmas envolventes →
    mesmos cortes → âncora intacta na virada de caminho.

    Devolve também quantos cortes o teto de folhas impediu, que é o número que o
    chamador precisa para avisar em vez de truncar em silêncio.
    """
    corpo, defs, simbolos = _partir_documento(svg)
    desloc = deslocamento_dos_simbolos(svg)
    cache: dict = {}
    elementos = _ler_elementos(corpo, simbolos, desloc, cache)
    if not elementos:
        return [], 0
    deslocados = cache.get(_MARCA_DESLOCADO, set())

    caixas = [e.caixa for e in elementos]
    # `_agrupar` devolve grupos de caixas; precisamos dos elementos. O índice
    # amarra os dois — comparar caixas por valor casaria traços coincidentes.
    por_caixa: dict[int, list[_Elemento]] = {}
    for elemento in elementos:
        por_caixa.setdefault(id(elemento.caixa), []).append(elemento)

    grupos, truncados = _agrupar(caixas)
    saida = []
    for grupo in grupos:
        do_grupo = [e for c in grupo for e in por_caixa[id(c)]]
        if not do_grupo:
            continue
        saida.append(_emitir(do_grupo, simbolos, desloc, deslocados))
    return saida, truncados


# ---------------------------------------------------------------------------
# Leitura


@dataclass
class _Elemento:
    tag: bytes
    trecho: bytes
    caixa: tuple[float, float, float, float]
    #: Símbolos que este elemento referencia (só `<use>` tem).
    simbolos: tuple[str, ...] = ()


def deslocamento_dos_simbolos(svg: bytes) -> tuple[float, float]:
    """O erro de origem que o `dwg2SVG` embute no `<defs>` — medido, não suposto.

    **O defeito.** O conteúdo de cada `<g id="symbol-…">` sai com um deslocamento
    somado, enquanto o `<use>` que o insere supõe o símbolo na **origem local**.
    As duas convenções juntas mandam o bloco para longe: um `scale(109)` sobre
    uma coordenada de 8,5 milhões coloca a peça a **936 milhões** de unidades do
    desenho. É por isso que a saída crua do motor tem só 0,3% da geometria dentro
    do `viewBox` que ela mesma declara, e é metade do que o `--help` do LibreDWG
    admite ao dizer que converte *"some 2D elements"*.

    **Por que dá para consertar: o deslocamento é exatamente o cabeçalho.**
    Medido em 10/08/2026 sobre o arquivo de referência, com três símbolos
    conferidos um a um:

    | Símbolo | Como sai | Descontado o deslocamento | O que é |
    |---|---|---|---|
    | `4B9` | x = −487789,713947 | 0,00 … 0,18 | bico de seta |
    | `4BF` | x = −487792,507797 | −2,79 … +2,79 | símbolo centrado |
    | `4C4` | y = 8581521,924998 | −1,00 … +1,00 | barra de 2 unidades |

    E os dois números batem com o `viewBox` **sem sobra**: o de x é `-x0`, e o de
    y é `y0 + altura`. Então a correção é `(x0, -(y0 + altura))`, derivada do
    próprio documento — nada de constante calibrada à mão, que envelheceria no
    primeiro build novo do motor.

    Devolve `(0, 0)` quando não há `viewBox` legível: sem o cabeçalho não há como
    derivar o deslocamento, e **chutá-lo seria pior que não corrigir** — erraria
    o lugar de todo bloco em vez de deixá-los onde o motor os pôs.
    """
    achado = re.search(rb'viewBox="([^"]+)"', svg[:4096])
    if not achado:
        return 0.0, 0.0
    try:
        x0, y0, _largura, altura = (float(n) for n in achado.group(1).split())
    except ValueError:
        return 0.0, 0.0
    return x0, -(y0 + altura)


def _partir_documento(svg: bytes) -> tuple[bytes, bytes, dict[str, bytes]]:
    """`(corpo, defs, simbolos)` — a geometria de topo, o bloco de defs e o mapa.

    O `dwg2SVG` põe o `<defs>` **depois** do corpo, o que é SVG válido e é
    contraintuitivo o bastante para justificar a nota: quem procurar os símbolos
    no começo do arquivo não os acha.
    """
    inicio = svg.find(b"<defs")
    if inicio < 0:
        return svg, b"", {}
    fim = svg.find(b"</defs>", inicio)
    if fim < 0:  # `defs` sem fecho: documento truncado, trata como sem símbolo
        return svg[:inicio], b"", {}
    defs = svg[inicio:fim + len(b"</defs>")]
    corpo = svg[:inicio] + svg[fim + len(b"</defs>"):]

    simbolos = {}
    for achado in re.finditer(rb'<g\s+id="(symbol-[^"]+)"', defs):
        nome = achado.group(1).decode("ascii", "ignore")
        # O `</g>` correspondente: os símbolos do `dwg2SVG` não aninham `<g>`,
        # então o primeiro fecho é o certo. Se um build passar a aninhar, a
        # consequência é um símbolo lido a menos — nunca geometria trocada.
        fecho = defs.find(b"</g>", achado.end())
        simbolos[nome] = defs[achado.end():fecho if fecho > 0 else len(defs)]
    return corpo, defs, simbolos


def _ler_elementos(corpo: bytes, simbolos: dict[str, bytes], desloc, cache) -> list[_Elemento]:
    """Os elementos de topo, cada um com a envolvente já calculada."""
    elementos = []
    for achado in _ELEMENTO.finditer(corpo):
        tag = achado.group(1).lower()
        trecho, atributos = _trecho_completo(corpo, achado.start(), tag)
        if trecho is None:
            continue
        caixa, usados = _caixa_do_elemento(tag, atributos, trecho, simbolos, cache, desloc)
        if caixa is None:
            continue
        elementos.append(_Elemento(tag, trecho, caixa, usados))
    return elementos


def _trecho_completo(corpo: bytes, inicio: int, tag: bytes):
    """O elemento inteiro + seus atributos. `(None, None)` se estiver truncado."""
    fim_tag = corpo.find(b">", inicio)
    if fim_tag < 0:
        return None, None
    cabeca = corpo[inicio:fim_tag + 1]
    atributos = dict(_ATRIBUTO.findall(cabeca))
    if tag == b"text" and not cabeca.rstrip().endswith(b"/>"):
        # `<text>` é o único com conteúdo; o resto é auto-fechado.
        fecho = corpo.find(b"</text>", fim_tag)
        if fecho < 0:
            return None, None
        return corpo[inicio:fecho + len(b"</text>")], atributos
    return cabeca, atributos


def _caixa_do_elemento(tag, atributos, trecho, simbolos, cache, desloc=(0.0, 0.0)):
    """Envolvente do elemento, em unidade de desenho. `(None, ())` se não tem."""
    if tag == b"use":
        alvo = atributos.get(b"xlink:href") or atributos.get(b"href") or b""
        nome = alvo.decode("ascii", "ignore").lstrip("#")
        caixa = _caixa_do_simbolo(nome, simbolos, cache, 0, desloc)
        if caixa is None:
            return None, ()
        # A caixa já vem **normalizada** (ver `_caixa_do_simbolo`): quem decide se
        # este símbolo carregava o deslocamento é ele, símbolo a símbolo. Aqui só
        # se aplica a transformação do `<use>`, que é o que ela sempre esperou —
        # um símbolo na origem local.
        matriz = _transformacao(atributos.get(b"transform", b""))
        return _aplicar(matriz, caixa), (nome,)

    if tag == b"circle" or tag == b"ellipse":
        try:
            cx = float(atributos.get(b"cx", b"0"))
            cy = float(atributos.get(b"cy", b"0"))
            rx = float(atributos.get(b"r") or atributos.get(b"rx") or 0)
            ry = float(atributos.get(b"r") or atributos.get(b"ry") or 0)
        except ValueError:
            return None, ()
        return (cx - rx, cy - ry, cx + rx, cy + ry), ()

    if tag == b"text":
        try:
            x, y = float(atributos.get(b"x", b"0")), float(atributos.get(b"y", b"0"))
        except ValueError:
            return None, ()
        # **A âncora do texto é um ponto, e é de propósito.** Medir a largura
        # renderizada exigiria métrica de fonte que o servidor não tem, e chutá-la
        # inflaria a envolvente da folha — que é justamente o número que decide o
        # corte por lacuna. Um rótulo mal medido moveria a fronteira entre dois
        # desenhos; o ponto de inserção não move nada.
        return (x, y, x, y), ()

    pontos = _pontos(tag, atributos)
    if not pontos:
        return None, ()
    xs = [p[0] for p in pontos]
    ys = [p[1] for p in pontos]
    return (min(xs), min(ys), max(xs), max(ys)), ()


def _pontos(tag, atributos) -> list[tuple[float, float]]:
    """Os vértices de `path`/`polygon`/`polyline`/`line`."""
    if tag == b"line":
        try:
            return [
                (float(atributos.get(b"x1", b"0")), float(atributos.get(b"y1", b"0"))),
                (float(atributos.get(b"x2", b"0")), float(atributos.get(b"y2", b"0"))),
            ]
        except ValueError:
            return []
    if tag in (b"polygon", b"polyline"):
        numeros = [float(n) for n in _NUMERO.findall(atributos.get(b"points", b""))]
        return list(zip(numeros[::2], numeros[1::2]))
    return _pontos_do_path(atributos.get(b"d", b""))


def _pontos_do_path(d: bytes) -> list[tuple[float, float]]:
    """Vértices de um `d`, tratando o arco pelo que ele é.

    **O arco é o motivo de isto não ser "pegue todos os números aos pares".** O
    comando `A` leva sete parâmetros (`rx ry rotação arco-grande varredura x y`),
    e só os **dois últimos** são coordenada — ler os sete aos pares poria os
    raios e as duas *flags* dentro da envolvente, inflando a folha com pontos que
    não existem no desenho. Num acervo de CAD isso não é caso de borda: arco é
    metade do que uma planta hidráulica tem.

    A envolvente do arco é aproximada pelos **extremos**, não pela curva — pode
    faltar a barriga de um arco muito aberto. É aceitável aqui porque este número
    serve para *agrupar* desenhos separados por lacunas de milhares de unidades,
    não para recortar a folha final.
    """
    pontos: list[tuple[float, float]] = []
    for pedaco in re.finditer(rb"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)", d):
        comando = pedaco.group(1)
        numeros = [float(n) for n in _NUMERO.findall(pedaco.group(2))]
        if comando in b"Aa":
            # 7 por elipse; a coordenada são os dois últimos de cada bloco.
            for i in range(0, len(numeros) - 6, 7):
                pontos.append((numeros[i + 5], numeros[i + 6]))
        elif comando in b"HhVv":
            continue  # eixo único: não move a envolvente do outro, e é raro aqui
        else:
            pontos.extend(zip(numeros[::2], numeros[1::2]))
    return pontos


#: Quais símbolos precisaram do conserto de origem — preenchido pela leitura e
#: lido pela emissão, para o `translate` ir só onde é devido.
#:
#: Chave é o nome do símbolo; vive no mesmo `cache` da envolvente para não
#: duplicar estado que precisa concordar.
_MARCA_DESLOCADO = "__deslocados__"


def _caixa_do_simbolo(nome, simbolos, cache, profundidade, desloc=(0.0, 0.0)):
    """Envolvente **normalizada** de um símbolo, calculada uma vez e memorizada.

    A memória é o que mantém este caminho barato: um símbolo referenciado 858
    vezes é lido **uma**. Sem ela, resolver as referências custaria o mesmo que
    expandir a geometria — que é o defeito que a troca de renderizador veio
    eliminar.

    **A decisão de deslocar é por símbolo, e é medida — não aplicada em bloco.**
    A primeira versão desta função corrigia todos, e a medição reprovou: de 721
    `<use>` do arquivo de referência, **403 já estavam certos crus** e só 3
    melhoravam com o deslocamento. Consertar todos teria quebrado 403 para
    arrumar 3. O `dwg2SVG` escreve o `<defs>` em duas convenções misturadas, e
    qual é qual só o próprio símbolo diz.

    **O teste que decide** não precisa de tolerância nem de página: um símbolo é
    geometria pequena em torno da própria origem, então **a interpretação certa é
    a que fica mais perto de zero**. O que carrega o erro tem centro em
    ~(−487.789, 8.581.522) e vai para ~0 ao ser deslocado; o que já está local
    tem centro em ~0 e iria para ~(487.789, −8.581.522). A diferença é de seis
    ordens de grandeza — não há empate a arbitrar.
    """
    deslocados = cache.setdefault(_MARCA_DESLOCADO, set())
    if nome in cache:
        return cache[nome]
    if profundidade >= PROFUNDIDADE_MAXIMA or nome not in simbolos:
        return None
    cache[nome] = None  # trava o ciclo antes de descer
    conteudo = simbolos[nome]
    caixas = []
    for achado in _ELEMENTO.finditer(conteudo):
        tag = achado.group(1).lower()
        trecho, atributos = _trecho_completo(conteudo, achado.start(), tag)
        if trecho is None:
            continue
        if tag == b"use":
            alvo = atributos.get(b"xlink:href") or atributos.get(b"href") or b""
            interna = _caixa_do_simbolo(
                alvo.decode("ascii", "ignore").lstrip("#"),
                simbolos, cache, profundidade + 1, desloc,
            )
            if interna:
                caixas.append(_aplicar(_transformacao(atributos.get(b"transform", b"")), interna))
            continue
        caixa, _ = _caixa_do_elemento(tag, atributos, trecho, simbolos, cache, (0.0, 0.0))
        if caixa:
            caixas.append(caixa)

    if not caixas:
        cache[nome] = None
        return None

    crua = _envolvente(caixas)
    moviada = _mover(crua, desloc)
    if _longe_de_zero(moviada) < _longe_de_zero(crua):
        deslocados.add(nome)
        resultado = moviada
    else:
        resultado = crua
    cache[nome] = resultado
    return resultado


def _longe_de_zero(caixa) -> float:
    """Quão longe da origem está o centro desta caixa."""
    return abs(caixa[0] + caixa[2]) / 2 + abs(caixa[1] + caixa[3]) / 2


# ---------------------------------------------------------------------------
# Transformação


def _transformacao(bruto: bytes) -> tuple[float, float, float, float, float, float]:
    """`transform="translate(…) rotate(…) scale(…)"` como matriz `(a,b,c,d,e,f)`.

    A ordem de composição do SVG é da **direita para a esquerda** — o último
    listado age primeiro no ponto. Inverter isso rodaria o bloco em torno do
    lugar errado, e o erro seria de metros num desenho em UTM.
    """
    matriz = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    operacoes = re.findall(rb"(\w+)\s*\(([^)]*)\)", bruto)
    for nome, argumentos in operacoes:
        valores = [float(n) for n in _NUMERO.findall(argumentos)]
        matriz = _multiplicar(matriz, _uma(nome.lower(), valores))
    return matriz


def _uma(nome: bytes, v: list[float]):
    if nome == b"translate":
        return (1.0, 0.0, 0.0, 1.0, v[0] if v else 0.0, v[1] if len(v) > 1 else 0.0)
    if nome == b"scale":
        sx = v[0] if v else 1.0
        return (sx, 0.0, 0.0, v[1] if len(v) > 1 else sx, 0.0, 0.0)
    if nome == b"rotate" and v:
        r = math.radians(v[0])
        cos, sen = math.cos(r), math.sin(r)
        if len(v) >= 3:  # rotate(a cx cy) = translate(c) rotate(a) translate(-c)
            cx, cy = v[1], v[2]
            return _multiplicar(
                (1.0, 0.0, 0.0, 1.0, cx, cy),
                _multiplicar((cos, sen, -sen, cos, 0.0, 0.0),
                             (1.0, 0.0, 0.0, 1.0, -cx, -cy)),
            )
        return (cos, sen, -sen, cos, 0.0, 0.0)
    if nome == b"matrix" and len(v) >= 6:
        return tuple(v[:6])
    return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mover(caixa, desloc):
    """A caixa deslocada — o conserto do erro de origem do `dwg2SVG`."""
    dx, dy = desloc
    return (caixa[0] + dx, caixa[1] + dy, caixa[2] + dx, caixa[3] + dy)


def _multiplicar(m, n):
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1,
    )


def _aplicar(m, caixa):
    """Envolvente da caixa **depois** da transformação.

    Os quatro cantos, e não os dois extremos: sob rotação o canto que era mínimo
    deixa de ser, e usar dois pontos encolheria a caixa do bloco girado — que é o
    caso comum de seta de cota e de símbolo de peça hidráulica.
    """
    a, b, c, d, e, f = m
    x0, y0, x1, y1 = caixa
    xs, ys = [], []
    for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        xs.append(a * x + c * y + e)
        ys.append(b * x + d * y + f)
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# Emissão


def _emitir(elementos: list[_Elemento], simbolos: dict[str, bytes], desloc, deslocados) -> Folha:
    """Um SVG por folha: `viewBox` calculado + só os símbolos que ela usa.

    **Os símbolos são filtrados por folha**, e é o que impede a separação de
    inchar o acervo: repetir o `<defs>` inteiro em cada uma das 50 folhas de um
    *sheet set* multiplicaria por 50 a parte pesada do arquivo — a folha ficaria
    barata de desenhar e cara de baixar, trocando o problema de lugar (§4.5 e o
    D53).
    """
    caixa = _envolvente([e.caixa for e in elementos])
    x0, y0, x1, y1 = caixa
    largura = max(x1 - x0, 1e-9) + 2 * MARGEM_MM
    altura = max(y1 - y0, 1e-9) + 2 * MARGEM_MM

    usados: set[str] = set()
    for elemento in elementos:
        for nome in elemento.simbolos:
            _coletar(nome, simbolos, usados, 0)

    partes = [
        b'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" '
        b'xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" '
        b'width="100%" height="100%" viewBox="'
        + f"{x0 - MARGEM_MM:.6f} {y0 - MARGEM_MM:.6f} {largura:.6f} {altura:.6f}".encode()
        + b'">\n',
    ]
    if usados:
        partes.append(b"<defs>\n")
        for nome in sorted(usados):
            # **O `translate` no grupo é o conserto, no lugar certo.** Pondo-o
            # aqui, ele age antes da transformação do `<use>` (que é aplicada por
            # fora), que é exatamente a ordem que o formato exige — e faz o
            # navegador desenhar o bloco onde a envolvente calculada disse que
            # ele está. Reescrever as coordenadas dentro do símbolo daria o mesmo
            # resultado custando uma varredura de megabytes por folha.
            if nome in deslocados:
                abertura = (
                    b'<g id="' + nome.encode("ascii")
                    + f'" transform="translate({desloc[0]:.6f} {desloc[1]:.6f})">'.encode()
                )
            else:
                abertura = b'<g id="' + nome.encode("ascii") + b'">'
            partes.append(abertura)
            partes.append(simbolos[nome])
            partes.append(b"</g>\n")
        partes.append(b"</defs>\n")
    partes.extend(e.trecho + b"\n" for e in elementos)
    partes.append(b"</svg>\n")

    return Folha(conteudo=b"".join(partes), caixa=caixa, tracos=len(elementos))


def _coletar(nome: str, simbolos: dict[str, bytes], achados: set[str], profundidade: int):
    """`nome` e tudo o que ele referencia — o fecho transitivo do símbolo.

    Precisa ser transitivo porque bloco insere bloco: emitir só o de primeiro
    nível deixaria a folha com um `<use>` apontando para um `id` que não está
    nela, e o navegador desenharia um buraco em silêncio.
    """
    if nome in achados or profundidade >= PROFUNDIDADE_MAXIMA or nome not in simbolos:
        return
    achados.add(nome)
    for achado in re.finditer(rb'(?:xlink:)?href="#([^"]+)"', simbolos[nome]):
        _coletar(achado.group(1).decode("ascii", "ignore"), simbolos, achados, profundidade + 1)
