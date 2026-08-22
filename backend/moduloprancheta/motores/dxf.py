# backend/moduloprancheta/motores/dxf.py
"""Motor `ezdxf` — DXF para SVG, e a base sobre a qual o DWG também cai.

**Por que SVG e não uma imagem:** a pergunta do canteiro é sobre *cota*. Uma
prancha A0 rasterizada em PNG obriga a escolher entre um arquivo enorme e uma
linha que some no zoom; em SVG a mesma prancha tem alguns MB, amplia sem perder
e o browser desenha. De quebra resolve a miniatura de graça — o mesmo SVG
encolhido é o card do acervo, então este motor não precisa produzir um segundo
tipo de derivada só para a lista (é o caminho oposto ao do `pdf_nativo`, e pela
razão oposta).

**`ezdxf` é MIT e Python puro** — sem binário externo, sem licença a carregar.
É o único motor da Prancheta que não tem asterisco, e por isso é o degrau de
entrada do plano `essencial` em `payment/planos.py`.

Este módulo também é a **segunda metade do motor de DWG**: o `dwg2dxf` do
LibreDWG converte DWG→DXF e entrega aqui. Manter a renderização num lugar só
significa que melhorar o traço melhora os dois formatos.

**A escala real sai daqui (PRA.3b).** Diferente do PDF e da foto, um DXF/DWG
*sabe* quanto mede: as coordenadas estão em unidades de desenho e o cabeçalho
declara qual é a unidade (`$INSUNITS`). É a mesma informação que faz o AutoCAD
responder "3,50 m" sem ninguém calibrar nada — e é por isso que a régua desta
prancha não precisa começar em pixel. Ver `escala_do_desenho`.
"""
from __future__ import annotations

import logging
import re
import time
from math import ceil, isfinite
from dataclasses import replace
from xml.etree import ElementTree as ET

from payment.planos import PRANCHETA_TETO_FOLHAS_POR_ARQUIVO

from . import hachura

from .base import (
    ECONOMIA_HACHURA,
    NAO_EMBRULHAR,
    Adaptador,
    ArquivoCorrompido,
    DesenhoVazio,
    ErroDeConversao,
    FalhaDoIntermediario,
    FalhaMotor,
    MotorIndisponivel,
    Parte,
    RecursoExcedido,
    ReferenciaAusente,
    Retomada,
    Saida,
    versao_de_modulo,
)

# Margem da folha, em mm. Não é estética: o `Frontend` do ezdxf desenha até a
# borda da extensão do desenho, e sem margem o carimbo do canto encosta no
# limite do viewport e some no visualizador.
logger = logging.getLogger(__name__)

MARGEM_MM = 10

#: Folga da caixa de recorte, em unidades de desenho.
#:
#: O recorte é feito na envolvente do próprio aglomerado, então nada dele está
#: fora por construção. A folga existe contra o empate de ponto flutuante: um
#: vértice exatamente na borda pode cair do lado errado da comparação e sumir —
#: e o vértice da borda é justamente o extremo do desenho.
FOLGA_RECORTE = 1e-6

#: Fator de saída do `ezdxf`: **1 unidade de desenho = 1 mm de página**.
#:
#: Passado explicitamente (e não deixado no default) porque a conversão de
#: unidade real depende dele: é este 1.0 que autoriza ler a largura da página em
#: mm como largura em unidades de desenho. Deixá-lo implícito faria uma mudança
#: de default do ezdxf virar erro silencioso de metro — o pior tipo de erro que
#: este módulo pode ter, porque vira parede no lugar errado. `EscalaDaPaginaTests`
#: prende o valor com um desenho de tamanho conhecido.
ESCALA_SAIDA_MM_POR_UNIDADE = 1.0

#: `$INSUNITS` → (metros por unidade de desenho, rótulo).
#:
#: Só as unidades que uma prancha de obra usa de verdade. As exóticas da tabela
#: do DXF (anos-luz, parsecs, angstroms) ficam **de fora de propósito**: num
#: arquivo de construtora elas são cabeçalho corrompido, não desenho, e derivar
#: metro a partir delas seria exatamente o "inventar metro em cima de pixel" que
#: a planta proíbe. Fora desta tabela a prancha simplesmente segue sem escala,
#: que é estado normal e visível.
METROS_POR_UNIDADE: dict[int, tuple[float, str]] = {
    1: (0.0254, "polegadas"),
    2: (0.3048, "pés"),
    3: (1609.344, "milhas"),
    4: (0.001, "milímetros"),
    5: (0.01, "centímetros"),
    6: (1.0, "metros"),
    7: (1000.0, "quilômetros"),
    10: (0.9144, "jardas"),
    14: (0.1, "decímetros"),
    21: (1200 / 3937, "pés (US survey)"),
}

#: Janela de plausibilidade da largura real, em metros. Um desenho declarado em
#: metros mas modelado em milímetros dá uma prancha de 42 km — número que, se
#: aceito, faria a tela escrever "1.400 m" para uma parede. Fora da janela a
#: escala não é publicada e a calibração humana continua sendo o caminho; é
#: preferível não ter régua a ter uma errada com cara de certa.
LARGURA_PLAUSIVEL_M = (0.05, 50_000.0)

#: Quantas vezes o **maior dos dois vizinhos** um vazio precisa valer para ser
#: lido como separação entre desenhos, e não como respiro dentro de um.
#:
#: O critério é "a lacuna é maior que o próprio desenho", e a referência é o
#: **maior** dos dois lados de propósito. Com o menor, um ponto solto a 5 cm de
#: uma planta (tamanho ~0) separaria por qualquer vazio, e uma folha normal se
#: estilhaçaria em dezenas de entradas — cada símbolo isolado viraria "outro
#: desenho". Com o maior, o comportamento é o que a mão espera:
#:
#: | Caso | Lacuna | Maior vizinho | Separa? |
#: |---|---|---|---|
#: | planta + corte lado a lado numa A0 | 100 mm | 800 mm | não — é uma folha só |
#: | símbolo solto dentro da planta | 50 mm | 800 mm | não |
#: | legenda afastada | 3.000 mm | 800 mm | sim |
#: | 50 plantas em grade no modelspace | 1.000 mm | 800 mm | sim — são 50 |
#: | as duas poligonais do `confrontantes` | 8.564.000 un | 1.089 un | sim |
#:
#: Não é número calibrado em cima de um arquivo: é a definição de "longe" que o
#: dono do acervo escolheu, e a tabela acima é o que ela produz.
FATOR_SEPARACAO = 1.0

#: Teto de desenhos por revisão. Alto porque um acervo real traz o *sheet set*
#: inteiro montado no modelspace — dezenas de plantas em grade —, e recusar-se a
#: listá-las seria esconder o acervo do cliente. Existe mesmo assim porque cada
#: desenho vira **um arquivo** no storage: sem teto, um DXF patológico geraria
#: milhares de derivadas e a conta de armazenamento seria do dono.
#:
#: Estourar o teto **não** é silencioso: o excedente fica no último desenho e a
#: memória de conversão registra `desenhos_truncados`.
#:
#: **O número mora em [payment/planos.py](../../../payment/planos.py) §5.4**
#: (decisão do dono, 08/08/2026 — todo teto ou limite vive lá). Faz sentido
#: justamente pelo argumento que já estava escrito acima: *a conta de
#: armazenamento é do dono*, então o número é dele.
MAX_DESENHOS = PRANCHETA_TETO_FOLHAS_POR_ARQUIVO

#: Janela de coordenada UTM — o que denuncia um desenho **georreferenciado**.
#:
#: É a correção mais importante desta leva, e vem de medir o acervo: o
#: `confrontantes` declara `$INSUNITS = 2` (**pés**) e tem `$EXTMAX` em
#: `(469.347 , 8.564.841)`. Isso não é desenho em pés — é *easting* e *northing*
#: de UTM no hemisfério sul, que **por definição estão em metros**. O cabeçalho é
#: o template que ninguém trocou; a coordenada é a evidência.
#:
#: Sem esta checagem, separar as folhas pioraria o defeito em vez de consertá-lo:
#: hoje a prancha fica sem régua (a largura de 143 km é recusada), mas com a
#: folha certa a conta cairia **dentro** da janela de plausibilidade e o módulo
#: publicaria 338 m para um desenho de 1.109 m — errado por 3,28× e com cara de
#: certo. Escala errada com aparência de certa é o pior desfecho possível aqui.
#:
#: Os limites são folgados de propósito: o UTM válido vai de 166.000 a 834.000 de
#: *easting*, e o *northing* do hemisfério sul de ~1.100.000 (o equador é
#: 10.000.000 e decresce para o sul). Fora desta janela nada é suposto.
UTM_ESTE = (100_000.0, 1_000_000.0)
UTM_NORTE = (1_000_000.0, 10_000_000.0)

#: **Quantas unidades de grade o menor desenho precisa ter para sobreviver.**
#:
#: O `SVGBackend` do ezdxf emite coordenadas **inteiras** numa grade fixa
#: (`output_coordinate_space`, 1.000.000 por padrão) esticada sobre a folha
#: inteira. Quando o desenho ocupa uma fração ínfima da folha, ele recebe uma
#: fração ínfima da grade — e é **destruído na emissão**, não apenas mostrado
#: pequeno. Medido no arquivo das duas poligonais: 861 mm de desenho numa folha
#: de 8,5 km sobravam ~100 unidades, **34% dos segmentos viravam deslocamento
#: zero** (`l -0 -0`) e o `stroke-width` arredondava para **0** — nenhuma linha,
#: hachura ou ponto aparecia, em zoom nenhum, porque não havia mais o que mostrar.
#:
#: A grade passa a ser dimensionada para o **desenho**, não para a folha. Zoom
#: nenhum recupera informação que não foi emitida, e por isso este é o degrau
#: anterior a todos os outros.
RESOLUCAO_ALVO = 100_000

#: Grade de saída: o padrão do ezdxf como piso, e o teto que a medição mostrou
#: bastar (com 1e9 os segmentos zerados caem de 7.268 para 4). Subir mais engorda
#: o SVG sem devolver desenho.
GRADE_PADRAO = 1_000_000
GRADE_MAXIMA = 1_000_000_000

#: **A quinta casa decimal, em unidade de desenho — decisão do dono (15/08/2026).**
#:
#: "Todos os projetos terão 5 casas decimais": o que o CAD mostra, o que o índice
#: guarda e o que a tela lê têm de concordar até aqui. Não é arredondamento — é
#: *resolução*: cada etapa do caminho precisa **carregar** 1e-5, e a que não
#: carregar é a que manda.
#:
#: Fica no código de engenharia e **não** em `payment/planos.py` por causa da
#: fronteira da §5.6 de lá: número que não diz *até onde o cliente vai* não é
#: limite, é fato. Este muda o **acerto** do sistema, como a janela do extrator
#: de CEP — não o quanto alguém pode usar.
#:
#: Medido em 15/08/2026, antes de existir, os três funis mais grossos que a
#: violavam numa folha A1 (861 unidades de largura):
#:
#: ==============================  ====================  ===============
#: funil                           passo em desenho      versus 1e-5
#: ==============================  ====================  ===============
#: grade do SVG (inteiros, 1e6)    0,000861              86× grosso
#: `float32` do sidecar            0,0000513             5× grosso
#: `TOLERANCIA_FUSAO` (1e-6)       0,000861              86× grosso
#: ==============================  ====================  ===============
PRECISAO_DE_DESENHO = 1e-5

#: O passo em que o `ezdxf` arredonda a folha (`layout.Page.width_in_mm`).
#: Não é escolha nossa — é o comportamento dele, e quem estima o tamanho da
#: página antes de emitir precisa reproduzi-lo ou a estimativa sai curta.
PASSO_DA_PAGINA_MM = 0.1

#: Folga da grade sobre a folha ESTIMADA, porque ela não é a folha emitida.
#:
#: É a lição do D90 escrita como número: além do arredondamento de 0,1 mm, o
#: `ezdxf` ainda reescala com `fit_page` e centraliza a sobra, e a folha real sai
#: um fio maior que a conta. Medido sem folga, a precisão obtida encostava em
#: 1,0000007e-5 — sétimo dígito acima do alvo, o bastante para o contrato não
#: valer. Modelar a página inteira seria refazer exatamente o erro que o D90
#: ensinou a não cometer; dar 0,1% de folga custa 0,1% de dígito no SVG e deixa
#: a **conferência pós-emissão** (`detalhe["precisao_desenho"]`) ser o veredito.
FOLGA_DA_GRADE = 1.001

#: **A folha de papel de referência**, em mm — o lado maior de uma A1.
#:
#: Serve a uma pergunta só: *"que espessura de traço este desenho teria se fosse
#: plotado?"*. Espessura de linha em CAD é propriedade do **papel** (0,25 mm de
#: tinta), não do modelo — e é por isso que a política de fábrica do `ezdxf`
#: (`ABSOLUTE`, que preserva o milímetro de tinta) produz resultado oposto em
#: arquivos equivalentes: a folha é auto-dimensionada, então o mesmo 0,25 mm vale
#: 1/160 da largura num modelo em metros e 1/6.600 num modelo em milímetros.
#: Medido nesta imagem, o traço saía **41× mais grosso** no primeiro caso — o
#: sintoma que o cliente relatou no D48 ("as linhas ficam muito grandes").
#:
#: A1 e não A0/A3 porque é a prancha corrente da construção brasileira; o valor
#: exato importa pouco (ele só fixa a razão tinta/folha), o que importa é ser
#: **um** tamanho para todos os desenhos — é o que faz o traço ficar igual venha
#: o arquivo em metro ou em milímetro.
FOLHA_REFERENCIA_MM = 841.0

#: A espessura máxima que o próprio DXF define (o `lineweight` vai até 211, em
#: centésimos de mm). É o topo da faixa que o `ezdxf` mapeia linearmente.
ESPESSURA_MAXIMA_DXF_MM = 2.11

#: Espessura do traço mais grosso como fração da folha — o que a política
#: `RELATIVE` do `ezdxf` consome em `Settings.max_stroke_width`.
#:
#: **A PRA.1c é o que tornou `RELATIVE` utilizável**, e é por isso que o D46
#: chegou a registrá-la como inviável: até ali a "folha" era o arquivo inteiro
#: (469 m × 8,5 km no caso medido), então 0,1% dela — o padrão do ezdxf — dava um
#: traço de metros. Com cada desenho na sua própria folha, a folha voltou a ser
#: do tamanho do desenho e a fração passou a significar o que diz.
#:
#: A faixa de espessuras do arquivo é preservada (o mapa é linear de 0,05 mm a
#: 2,11 mm): a hierarquia de penas que o projetista escolheu — corte grosso,
#: hachura fina — continua legível. Uma espessura fixa para tudo
#: (`RELATIVE_FIXED`) a destruiria.
ESPESSURA_RELATIVA = ESPESSURA_MAXIMA_DXF_MM / FOLHA_REFERENCIA_MM

#: A largura da folha declarada pelo SVG.
#:
#: Aceita **notação científica** porque o ezdxf a emite assim a partir de ~7
#: dígitos (`width="4.00002e+06mm"`), e a versão antiga do padrão — `[0-9.]+` —
#: simplesmente não casava: toda prancha com folha acima de ~1 km perdia a régua
#: **em silêncio**, caindo no mesmo `{}` de quem não declara unidade. Achado ao
#: testar a grade de saída; é da família de erro que a §13.2 chama de pior, o que
#: vira parede no lugar errado — aqui, parede nenhuma.
_LARGURA_SVG = re.compile(r'width="([0-9.]+(?:[eE][+-]?\d+)?)mm"')

#: O `viewBox` da folha emitida, que é o sistema de coordenadas em que o `<img>`
#: da tela desenha. O `SVGBackend` sempre o escreve com origem em `0 0` e lados
#: inteiros (`make_view_box` arredonda), no cabeçalho — daí buscar só o começo do
#: arquivo, que pode ter 10 MB. É metade da fonte do snap (a outra é o
#: `transformation_matrix`); ver `_folha_emitida`.
_CAIXA_DE_VISAO = re.compile(r'viewBox="\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*"')


def _folha_emitida(svg_texto: str):
    """A régua do SVG que **acabou de sair**, para o snap normalizar por ela.

    **Existe porque recalcular a página erra, e o erro cresce com o zoom (D90).**
    A conta óbvia — `largura_do_desenho + 2·MARGEM_MM`, com os dois eixos
    divididos pela largura — parece a mesma que o `ezdxf` faz e não é: ele
    arredonda a página para 0,1 mm (`Page.width_in_mm`), reescala o conteúdo para
    caber nela (`fit_page`) e centraliza a sobra dentro das margens
    (`MIDDLE_CENTER`). Sobra um erro de escala que some no enquadramento e
    aparece ampliado, **diferente em cada prancha**: medido em 15/08/2026, 0,04 px
    de mediana na `001` (folha 861×614 mm, que não sofre arredondamento) e 8,7 px
    na `Banco` (112,7×65,5 mm), a 81×.

    Ler do arquivo emitido é a mesma política que o `escala_do_desenho` já segue
    para a régua: **quem arbitra margem e extensão é o `ezdxf`, e a resposta se
    pergunta a ele**. Aqui isso sai de graça, porque a geometria que o snap
    indexa já está no espaço do `viewBox` — ver `_folha`.

    Devolve `None` se o SVG não tem a forma esperada; aí o snap fica de fora,
    porque a alternativa seria indexar geometria de `viewBox` com régua de
    milímetro, que é pior que não ter mira.
    """
    from . import snap as snapmod

    caixa = _CAIXA_DE_VISAO.search(svg_texto[:600])
    if not caixa:
        return None
    try:
        largura, altura = float(caixa.group(1)), float(caixa.group(2))
    except ValueError:
        return None
    return snapmod.do_svg(largura, altura)


#: O retângulo de fundo que o `SVGBackend` emite como primeiro elemento da folha.
#:
#: Ele vem sempre com origem `0 0` e lados **iguais aos do `viewBox`** — é o papel
#: sobre o qual o desenho é pintado, e não geometria do desenho. Casar os lados
#: contra o `viewBox` (em `_fundo_em_porcentagem`) é o que garante que só ele seja
#: reescrito: um `<rect>` que o projetista desenhou tem outro tamanho.
_RECT_DE_FUNDO = re.compile(
    r'<rect\b(?P<antes>[^>]*?)\bwidth="(?P<w>[\d.]+)"\s+height="(?P<h>[\d.]+)"'
    r'(?P<depois>[^>]*?)/>'
)


def _fundo_em_porcentagem(svg_texto: str) -> str:
    """O fundo da folha em `100%`, porque acima de 2²⁵ o Chromium para de pintá-lo.

    **O defeito.** O `SVGBackend` emite o papel como um `<rect>` com os lados em
    unidade de `viewBox` — `width="86186100"` na `001`. O Chromium **não pinta
    esse retângulo inteiro**: ele preenche até ~33,5 milhões de unidades e para,
    deixando o resto da folha sem fundo. O desenho continua todo lá (o traço é
    feito de segmentos curtos, que não esbarram no limite), mas ele passa a ser
    linha clara sobre o fundo claro da vista — ilegível na maior parte da prancha.

    Medido em 16/08/2026, `001.dwg` num `<img>` de 1250 px de largura: o fundo
    cobria 486 px dos 1250. A conta fecha em ``86.186.100 × 486/1250 ≈ 3,35×10⁷``,
    que é **2²⁵ = 33.554.432** — o teto de coordenada do rasterizador de caminho
    do Skia. O `librsvg` pinta a mesma folha inteira, e é por isso que a miniatura
    e o PDF nunca denunciaram nada: **o defeito só existe no navegador**, que é
    justamente onde a prancha é lida.

    **Por que agora.** Até a decisão das cinco casas (`PRECISAO_DE_DESENHO`,
    15/08/2026) a grade era o padrão do `ezdxf`, 10⁶ — trinta e três vezes abaixo
    do teto, e nenhuma folha chegava perto dele. Dimensionar a grade pelo desenho
    subiu a `001` para 8,6×10⁷ e cruzou a linha. O sintoma que se viu — "o fundo
    cinza está só em parte do desenho, e começou depois das cinco casas" — é
    exatamente isto, e não erro de escala nem de recorte.

    **O conserto.** `width="100%" height="100%"` cobre a mesma área (a
    porcentagem resolve contra a viewport, que é o `viewBox`), e o navegador a
    resolve sem construir um caminho de 8,6×10⁷ unidades. Conferido nos dois
    rasterizadores que o produto usa: Chromium passa a cobrir a folha inteira e o
    `librsvg` segue idêntico. **Não se mexe na grade**, que é o que carrega a
    quinta casa — o fundo não precisa de precisão nenhuma, e é só ele que sai do
    espaço grande.

    Devolve o texto intocado quando o primeiro `<rect>` não tem exatamente os
    lados do `viewBox`: aí ele não é o papel, é desenho, e reescrevê-lo apagaria
    geometria do projetista.
    """
    caixa = _CAIXA_DE_VISAO.search(svg_texto[:600])
    if not caixa:
        return svg_texto
    # A busca começa no `</defs>` e para logo depois: o fundo é o **primeiro**
    # elemento da folha, e limitar a janela é o que impede a varredura de um corpo
    # de 10 MB atrás de um retângulo que já se sabe onde está. Sem `</defs>` o
    # começo do arquivo serve — a folha sem estilo nenhum é curta.
    inicio = svg_texto.find("</defs>", 0, 200_000)
    inicio = 0 if inicio < 0 else inicio
    achado = _RECT_DE_FUNDO.search(svg_texto, inicio, inicio + 2000)
    if not achado:
        return svg_texto
    # Comparação exata de texto, e não de float: o `SVGBackend` escreve os dois
    # números com o mesmo formatador, então o fundo bate dígito a dígito. Tolerar
    # diferença aqui abriria a porta para reescrever um retângulo do desenho que
    # por acaso quase enche a folha.
    if (achado.group("w"), achado.group("h")) != (caixa.group(1), caixa.group(2)):
        return svg_texto
    trocado = (
        f'<rect{achado.group("antes")}width="100%" height="100%"'
        f'{achado.group("depois")}/>'
    )
    return svg_texto[:achado.start()] + trocado + svg_texto[achado.end():]


def _mundo_da_folha(antes, depois, svg_texto: str) -> dict:
    """A coordenada **do CAD** de volta, a partir da coordenada de folha.

    **Existe porque o desenho já vinha com coordenada e a conversão a trocou.**
    O que a tela mostra é fração de folha, milímetro de papel e unidade de
    `viewBox` — três réguas nossas. A planta traz a dela, a mesma que o AutoCAD
    exibe na barra de status, e é contra essa que se confere um vértice. Sem esta
    ponte, quem abre a prancha aqui perde o único número que dá para comparar
    com o arquivo de origem.

    **É medida, não deduzida** — a lição do D90. Refazer a conta da página
    (`envolvente + 2·MARGEM_MM`) erra, porque o `ezdxf` ainda arredonda a folha,
    reescala com `fit_page` e centraliza a sobra. Aqui os dois retratos são da
    **mesma geometria**: `antes` é a envolvente do gravador do backend em unidade
    de desenho, `depois` é a dela já no espaço do `viewBox` (o `get_string`
    transforma os registros *in place*, que foi o defeito que o D90 ensinou e é
    agora o instrumento). Duas envolventes do mesmo conteúdo dão a afinidade
    inteira, sem tocar em interno do `ezdxf`.

    A transformação é escala uniforme com **Y invertido** (o SVG cresce para
    baixo, o CAD para cima), então bastam três números::

        x_desenho = origem_x + x_folha · por_folha
        y_desenho = origem_y − y_folha · por_folha

    `por_folha` é "quantas unidades de desenho cabem na largura inteira da
    folha", a mesma grandeza que `escala_valor` guarda — e `origem` é o **canto
    superior-esquerdo da folha** em coordenada de desenho, margem incluída.

    Devolve `{}` — e não um número aproximado — quando a envolvente é degenerada
    (folha de um traço vertical) ou o `viewBox` não foi lido: coordenada errada
    com cara de certa é o que este módulo inteiro existe para não fazer.
    """
    caixa = _CAIXA_DE_VISAO.search(svg_texto[:600])
    if caixa is None or antes is None or depois is None:
        return {}
    try:
        viewbox_largura = float(caixa.group(1))
        largura_desenho = antes.extmax.x - antes.extmin.x
        largura_folha = depois.extmax.x - depois.extmin.x
        if largura_desenho <= 0 or largura_folha <= 0 or viewbox_largura <= 0:
            return {}
        # unidades de `viewBox` por unidade de desenho
        escala = largura_folha / largura_desenho
        por_folha = viewbox_largura / escala
        origem_x = antes.extmin.x - depois.extmin.x / escala
        # O topo da folha corresponde ao MAIOR y do desenho — é o Y invertido.
        origem_y = antes.extmax.y + depois.extmin.y / escala
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        return {}
    if not all(map(isfinite, (por_folha, origem_x, origem_y))) or por_folha <= 0:
        return {}
    # **Sem `round`.** A coordenada é o produto; arredondá-la aqui seria repor,
    # na saída, o truncamento que o resto desta mudança foi feito para tirar do
    # caminho — e num levantamento em UTM (10⁷) seis casas já é a quinta casa
    # decimal encostando no limite. JSON guarda `double`: cabe inteiro.
    return {"origem_x": origem_x, "origem_y": origem_y, "por_folha": por_folha}


class MotorDxf(Adaptador):
    codigo = "ezdxf"
    tipos = ("vetor_2d",)
    #: A hachura é **o** gerador do consumo deste motor (D57): o `Frontend`
    #: expande cada `HATCH` em linhas de padrão, e cada linha vira registro vivo
    #: no `Recorder` até a folha ser emitida. Padrão fino sobre área grande dá
    #: milhões de segmentos — foi assim que uma prancha do acervo chegou a 62 GB.
    economias = (ECONOMIA_HACHURA,)
    #: PRA.11 — a folha é a unidade retomável, e este é o motor que tem folhas.
    #: O que a retomada NÃO evita é a gravação da geometria (`_gravar`), que roda
    #: inteira em toda passada; o que ela evita é reemitir as folhas já prontas,
    #: que num arquivo de dezenas de desenhos é a maior parte do relógio.
    retomavel = True

    def __init__(self, origem: str = "dxf"):
        """`origem` é o formato que **o cliente subiu**, não o que este motor lê.

        Quase sempre são o mesmo (`dxf`), e aí o default serve — é assim que o
        registry instancia o adaptador. O caso que existe é o DWG: o `MotorDwg`
        roda o `dwg2dxf` e entrega aqui um DXF **intermediário**, que o cliente
        nunca viu. Sem saber disso, toda frase de erro deste motor acusa o
        arquivo errado — o defeito que o **D42** mediu. Ver `_ilegivel`.
        """
        self.origem = origem

    def _detectar_versao(self) -> str:
        versao = versao_de_modulo("ezdxf")
        return f"ezdxf-{versao}" if versao else ""

    def converter(self, caminho: str, *, formato: str, tipo: str, economia: str = "",
                  teto_snap: int | None = 0, retomada=None, prazo=None,
                  ceder=None) -> Saida:
        documento, recuperado = self._ler(caminho)
        if economia == ECONOMIA_HACHURA and not _tem_hachura(documento):
            # **Descer a escada sem ter o que economizar é queimar um orçamento
            # inteiro para chegar ao mesmo lugar.** Desenhar sem hachura um
            # arquivo que não tem hachura é a conversão idêntica à que acabou de
            # estourar, e a resposta honesta é a que o pipeline já tinha na mão.
            # A consulta é sobre o documento já lido, não um segundo desenho:
            # custa uma varredura da tabela de entidades, não a expansão delas.
            raise RecursoExcedido(
                "A conversão passou do limite de processamento, e este desenho "
                "não tem hachura que possa ser simplificada para caber.",
                teto="sem_economia",
            )
        return self._para_svg(documento, recuperado=recuperado, economia=economia,
                              teto_snap=teto_snap, retomada=retomada, prazo=prazo,
                              ceder=ceder)

    # -- de quem é o arquivo que falhou --------------------------------------
    def _ilegivel(self, *, cliente: str, nosso: str) -> ErroDeConversao:
        """A mesma falha de leitura, com o **dono certo**.

        Lendo o DXF que o cliente subiu, "ilegível" é uma frase sobre o arquivo
        **dele**: `arquivo_corrompido`, e a saída é reexportar do CAD. Lendo o DXF
        que o nosso `dwg2dxf` acabou de produzir — a partir de um DWG que ele
        abriu, dentro do alcance declarado, sem erro nenhum —, a mesma frase
        culpa o arquivo do cliente por um defeito da nossa conversão.

        É a regra da planta §4.2 (separar "seu plano não abre" de "o servidor não
        deu conta") aplicada um degrau adiante, e o **D42** mostrou o custo de não
        a aplicar: dos 73 DWGs reais medidos, 13 falhavam exatamente aqui e liam
        *"O arquivo não é um DXF válido"* sobre um arquivo que nunca existiu para
        eles.

        As duas frases vêm escritas pelo chamador em vez de uma ser derivada da
        outra: a do cliente e a nossa falam de **arquivos diferentes**, e montar a
        segunda concatenando a primeira reintroduziria no texto exatamente a frase
        que acusa o arquivo errado.
        """
        if self.origem == "dxf":
            return ArquivoCorrompido(cliente)
        return FalhaDoIntermediario(
            f"O seu {self.origem.upper()} foi convertido, mas o DXF intermediário que "
            f"geramos a partir dele {nosso}. O arquivo com problema é o nosso, não o "
            f"seu — reexportar do CAD não resolve."
        )

    # -- leitura -------------------------------------------------------------
    def _ler(self, caminho: str):
        """Lê o DXF, com o modo de recuperação como segunda tentativa.

        DXF de campo vem torto com frequência banal — exportador antigo, arquivo
        truncado no e-mail, encoding trocado. O `ezdxf.recover` existe exatamente
        para isso e recupera a maioria deles. Tentar o caminho rápido primeiro e
        cair no lento só quando falha é mais barato que sempre recuperar, e o
        fato de ter sido recuperado vai na **memória de conversão**: um desenho
        que precisou de reparo é informação que o projetista quer ter.
        """
        try:
            import ezdxf
            from ezdxf import recover
        except Exception as exc:
            raise MotorIndisponivel("A biblioteca `ezdxf` não está instalada.") from exc

        try:
            return ezdxf.readfile(caminho), False
        except NAO_EMBRULHAR:
            # Ler um DXF de 40 MB cabe folgado no teto de memória — mas cabe, e
            # quando não couber a frase não pode ser "o seu arquivo está
            # corrompido". Ele não está: nós é que não demos memória.
            raise
        except OSError as exc:
            # Não é o conteúdo, é o arquivo: o `recover` abriria o mesmo caminho
            # e falharia igual. Único caso em que pular a 2ª tentativa é certo.
            raise self._ilegivel(
                cliente=f"Não consegui ler o arquivo: {exc}",
                nosso=f"não pôde ser aberto ({exc})",
            ) from exc
        except Exception as exc:
            # **Toda falha de conteúdo merece a 2ª tentativa, e não só a
            # `DXFStructureError` (D43).** Até 09/08/2026 só aquela caía no
            # `recover`; qualquer outra virava "ilegível" na hora, com o `recover`
            # ali do lado sem ser chamado. O `JAMYLLE E PAULO_plantas executivas`
            # morria assim: `readfile` levantava `KeyError: '00 - CADASTRO'` — um
            # `LAYOUT` que a `ezdxf` não registrou e que uma entidade aponta como
            # dono — e o mesmo arquivo, pelo `recover`, abre com **25.727
            # entidades**. O desenho estava inteiro; a porta é que era estreita.
            primeiro = exc

        try:
            documento, auditoria = recover.readfile(caminho)
        except NAO_EMBRULHAR:
            raise
        except Exception as exc:
            raise self._ilegivel(
                cliente="O arquivo não é um DXF válido, nem depois da tentativa de reparo.",
                nosso=(
                    "não é um DXF válido, nem depois da tentativa de reparo "
                    # O erro da 1ª leitura é o que descreve o defeito; o da 2ª só
                    # diz que o reparo não deu conta. Guardar os dois é o que
                    # permite achar o padrão entre arquivos.
                    f"({type(primeiro).__name__}: {primeiro} → {type(exc).__name__})"
                ),
            ) from exc
        if auditoria.has_errors:
            # Recuperado com erros ainda desenha — o que não se pode é fingir que
            # veio limpo. O detalhe sobe para a derivada e aparece na tela.
            return documento, True
        return documento, True

    # -- renderização --------------------------------------------------------
    def _sanear_blocos(self, documento) -> tuple[list[str], int]:
        """Conserta as duas formas de `INSERT` órfão que abortam a prancha inteira.

        **Era a maior causa isolada de falha do motor livre.** O `dwg2dxf` emite
        `INSERT`s apontando para blocos anônimos — `*U3`, `*X7`, os que o AutoCAD
        cria sozinho — e nem sempre escreve a definição correspondente. O
        `Frontend` do `ezdxf` trata isso como erro de estrutura e **aborta a
        prancha inteira**: `DXFStructureError: Required block definition for
        "*U3" does not exist`. Uma planta de 4.000 linhas era perdida por causa de
        um carimbo de dois traços.

        São **duas** avarias, e a segunda só apareceu na medição do acervo:

        1. **nome conhecido, definição ausente** — cria-se a definição **vazia**.
           Troca "nada é desenhado" por "aquela inserção é desenhada vazia", que é
           estritamente mais informação e é o que qualquer CAD faz com referência
           quebrada;
        2. **nome vazio** (`Required block definition for "" does not exist`) — não
           há o que definir, porque um `INSERT` sem nome não referencia coisa
           alguma. A entidade é **descartada**: ela já não desenhava nada, e é só
           ela que separa a prancha inteira de ser desenhada.

        O que **não** se faz, nos dois casos, é fingir que o desenho veio
        completo: as duas contagens sobem para a memória de conversão.

        Varrer `documento.blocks` cobre tudo porque no DXF o modelspace e cada
        paperspace **são** block layouts (`*Model_Space`, `*Paper_Space`) — e por
        isso pega também o `INSERT` aninhado dentro de outro bloco, que uma
        varredura só do modelspace deixaria passar. `DIMENSION` fica de fora de
        propósito: quando o bloco de geometria dela some, o `ezdxf` a redesenha
        sozinho, sem levantar nada.
        """
        try:
            existentes = {bloco.name for bloco in documento.blocks}
        except Exception:  # pragma: no cover - documento sem seção de blocos
            return [], 0

        ausentes: set[str] = set()
        orfas: list[tuple] = []
        for bloco in documento.blocks:
            for entidade in bloco:
                if entidade.dxftype() != "INSERT":
                    continue
                nome = entidade.dxf.get("name", "")
                if not nome:
                    orfas.append((bloco, entidade))
                elif nome not in existentes:
                    ausentes.add(nome)

        criados: list[str] = []
        for nome in sorted(ausentes):
            try:
                documento.blocks.new(nome)
            except Exception:
                # Nome que o próprio ezdxf recusa (o DXF veio torto o bastante
                # para inventar um). Segue sem ele: no pior caso a prancha falha
                # como falhava antes, e nunca pior que isso.
                continue
            criados.append(nome)

        descartadas = 0
        # Fora do laço de varredura: apagar entidade enquanto se itera sobre o
        # layout que a contém é a receita clássica de pular a entidade seguinte.
        for bloco, entidade in orfas:
            try:
                bloco.delete_entity(entidade)
            except Exception:
                continue
            descartadas += 1

        return criados, descartadas

    def _configuracao(self, economia: str = ""):
        """Os knobs de render que o PRA.1 deixou no default (D48, D57).

        `Frontend(ctx, backend)` **sem `config=`** desenha tudo de fábrica, e a
        política de fábrica é `ABSOLUTE`: 0,25 mm de tinta continuam 0,25 mm
        qualquer que seja o tamanho da folha. Como a folha aqui é
        auto-dimensionada pelo desenho, isso faz o mesmo traço sair 41× mais
        grosso num modelo em metros do que no mesmo desenho em milímetros —
        medido nesta imagem, e é o que o cliente viu.

        `RELATIVE` amarra o traço à folha (ver `ESPESSURA_RELATIVA`), que é a
        grandeza certa: espessura de linha é propriedade do papel.

        A configuração viaja até o `SVGBackend` **pelo gravador** — o
        `Player.replay` reaplica o `configure()` do `Frontend` no backend de
        destino —, então não há uma segunda cópia para manter em dia.

        **`SHOW_OUTLINE` é o degrau da escada, e a escolha foi medida** (D57).
        Lendo o dispatch do `ezdxf 1.4.4` (`frontend.draw_hatch_entity`), ele
        troca o preenchimento por sólido e liga `show_only_outline`, o que faz o
        `draw_hatch_pattern` inteiro ser **pulado**: o custo cai de "uma linha
        por passada do padrão sobre a área" para "o contorno do bordo", que é
        O(bordo) e converge sempre. É essa garantia que o degrau precisa ter —
        um degrau que ainda possa estourar não é degrau.

        **Por que não `SHOW_SOLID`**, que custa o mesmo: ele pinta a área inteira
        de uma cor só, e hachura preta de parede vira um bloco preto por cima de
        cota, texto e traço que estão embaixo. É a mesma classe de defeito que a
        tarja preta do **D46** — a folha abre, parece pronta e esconde desenho. O
        contorno não esconde nada: a área hachurada fica com o bordo desenhado e
        vazia por dentro, e quem olha vê que tem uma área ali.

        **`SHOW_APPROXIMATE_PATTERN` não existe de fato nesta versão.** Está no
        enum, mas nenhum ramo do dispatch o trata: cair nele deixa o
        preenchimento em `PATTERN` e desenha **igual ao `NORMAL`**, com o custo
        do `NORMAL`. Fica registrado aqui para ninguém "melhorar" a escada
        trocando o degrau por ele e medir depois que nada mudou.
        """
        from ezdxf.addons.drawing.config import Configuration, HatchPolicy, LineweightPolicy

        return Configuration(
            lineweight_policy=LineweightPolicy.RELATIVE,
            hatch_policy=(
                HatchPolicy.SHOW_OUTLINE if economia == ECONOMIA_HACHURA
                else HatchPolicy.NORMAL
            ),
        )

    def _gravar(self, documento, espaco, *, Frontend, RenderContext, Recorder, config):
        """Desenha um espaço no gravador e devolve `(player, caixas)`.

        **Gravar em vez de desenhar direto** é o que permite descobrir *quantos
        desenhos* o arquivo traz antes de emitir folha nenhuma. Mandando o
        `Frontend` direto ao `SVGBackend`, como era antes da PRA.1c, as
        coordenadas de cada traço se perdiam e sobrava uma folha só — que no
        acervo real sai com 469 m × 8,5 km porque o arquivo tem duas áreas
        distantes, não porque tem lixo.
        """
        gravador = Recorder()
        Frontend(RenderContext(documento), gravador, config=config).draw_layout(espaco)
        player = gravador.player()
        return player, _caixas(getattr(player, "records", []))

    def _para_svg(self, documento, *, recuperado: bool, economia: str = "",
                  teto_snap: int | None = 0, retomada=None, prazo=None,
                  ceder=None) -> Saida:
        try:
            from ezdxf.addons.drawing import Frontend, RenderContext, layout, svg
            from ezdxf.addons.drawing.recorder import Recorder
        except Exception as exc:
            raise MotorIndisponivel(
                "Este `ezdxf` não traz o backend de desenho (`addons.drawing.svg`) "
                "ou o gravador (`addons.drawing.recorder`); é preciso a versão 1.4 "
                "ou maior."
            ) from exc

        ausentes, descartadas = self._sanear_blocos(documento)
        config = self._configuracao(economia)
        censo = {"hachuras": 0, "hachuras_truncadas": 0, "hachuras_nativas": 0}
        # O registro das hachuras vive na conversão, não no motor: ele guarda
        # marcas que só valem para as folhas desta passada, e um resíduo da
        # anterior pintaria área com padrão de outro desenho.
        self._padroes = {}
        maquinario = {
            "Frontend": _frontend_que_conta_hachura(
                Frontend, censo, config, self._padroes),
            "RenderContext": RenderContext,
            "Recorder": Recorder, "config": config,
        }

        try:
            player, caixas = self._gravar(documento, documento.modelspace(), **maquinario)
        except NAO_EMBRULHAR:
            raise  # o teto agindo, ou falha já classificada — ver `NAO_EMBRULHAR`
        except Exception as exc:
            raise FalhaMotor(
                f"Falha ao desenhar o {self.origem.upper()}: {exc}"
            ) from exc

        truncados = 0
        if caixas:
            espaco = "modelspace"
            grupos, truncados = _agrupar(caixas)
            unidades, georreferencia = _unidade_efetiva(documento, grupos)
            pranchas = [(player, grupo, len(grupos) == 1, "") for grupo in grupos]
        else:
            # **D44 — a prancha está na aba de layout.** Em 8 dos 150 DWGs da
            # remedição a folha é composta no paperspace (moldura, carimbo,
            # legendas) e o modelspace fica vazio; até aqui isso virava erro.
            espaco = "paperspace"
            pranchas = self._pranchas_do_paperspace(documento, **maquinario)
            if not pranchas:
                raise self._nada_a_desenhar(documento)
            # **A régua não vem do paperspace, e essa é a armadilha da fatia.**
            # Lá a unidade é a da FOLHA (milímetro de papel), não a do modelo:
            # publicar aquela largura como escala faria a tela responder "0,9 m"
            # para uma fachada de 30 m — e o valor cairia dentro da janela de
            # plausibilidade sem disparar nada. Quem cai aqui mede em fração da
            # largura, e a calibração humana segue sendo o caminho.
            unidades, georreferencia = 0, {"georreferenciado": False}

        # O que vale para o arquivo inteiro, repetido em cada parte porque é a
        # parte que vira linha no banco — e uma memória de conversão que só
        # existisse na primeira deixaria as outras sem procedência.
        comum = {
            "dxfversion": getattr(documento, "dxfversion", ""),
            "recuperado": recuperado,
            # Quantos blocos o desenho referenciava sem definir, e quantas
            # inserções sem nome foram descartadas. Vão para a memória de
            # conversão porque **a prancha saiu incompleta**: aquelas inserções
            # desenharam vazio. Zero é o caso normal e fica declarado do mesmo
            # jeito, para a diferença ser legível sem adivinhação.
            "blocos_ausentes": len(ausentes),
            "insercoes_descartadas": descartadas,
            "registros": sum(len(grupo) for _p, grupo, _s, _n in pranchas),
            # De onde a prancha foi desenhada. Vale como procedência e como
            # explicação de por que esta folha não tem régua.
            "espaco": espaco,
            # Com que fidelidade a hachura saiu, sempre declarado — inclusive
            # quando é `completa`, que é o caso normal. Um campo que só aparece
            # no caso ruim obriga quem lê a saber que ele podia ter aparecido.
            **_censo_da_hachura(censo, economia),
            **georreferencia,
        }
        # XREF referenciado é prancha incompleta mesmo quando algo desenhou —
        # a mesma lógica de `blocos_ausentes`, e a resposta de por que falta
        # metade do desenho numa folha que abriu.
        xrefs = _xrefs_inseridas(documento)
        if xrefs:
            comum["xrefs_ausentes"] = len(xrefs)
            comum["xrefs"] = xrefs[:10]
        if truncados:
            # Sem truncamento silencioso: quem lê a memória tem de saber que a
            # lista parou no teto, senão "64 desenhos" se lê como "são 64".
            comum["desenhos_truncados"] = truncados

        # **A emissão é um laço com prazo, e não uma compreensão de lista**
        # (PRA.11). Era `[self._folha(...) for ... in pranchas]`, e a diferença é
        # o que torna o arquivo de 40 MB terminável: emitir folha a folha permite
        # conferir o relógio **entre** folhas e devolver o que já ficou pronto,
        # em vez de perder a passada inteira ao estourar na trigésima.
        #
        # Quem já foi feito é pulado pelo índice do grupo — `_agrupar` é
        # determinístico sobre as mesmas caixas, então o grupo 7 de hoje é o
        # grupo 7 de ontem. Recontar do zero renumeraria as folhas e apagaria o
        # nome que alguém deu à "Desenho 3" na passada anterior.
        feitos = getattr(retomada, "grupos_feitos", 0) or 0
        proxima_ordem = (getattr(retomada, "desenhos_feitos", 0) or 0) + 1
        vazias_antes = getattr(retomada, "vazios_feitos", 0) or 0
        registros_vazios_antes = getattr(retomada, "registros_vazios_feitos", 0) or 0

        partes: list[Parte] = []
        vazias: list[Parte] = []
        processados = feitos
        for prancha, grupo, sozinho, nome in pranchas[feitos:]:
            folha = self._folha(
                prancha, grupo, ordem=0, unidades=unidades, comum=comum,
                sozinho=sozinho, nome=nome, espaco=espaco, layout=layout, svg=svg,
                teto_snap=teto_snap,
            )
            processados += 1
            # Aglomerado que não desenhou nada não é desenho. Acontece de verdade:
            # o MaxPlast traz **513 registros de extensão zero exatamente na
            # origem**, que produzem SVG sem um traço sequer e ainda assim
            # esticavam a folha do arquivo inteiro de UTM até (0,0). Descartá-los
            # é o oposto de esconder geometria — não há geometria. E o número fica
            # declarado, porque um descarte silencioso é indistinguível de um
            # desenho perdido.
            if _tem_traco(folha.conteudo):
                # A numeração é atribuída **depois** do descarte, para o
                # "Desenho 2" da tela ser o segundo que existe e não o segundo
                # que houve. Ela é incremental por isso: só quem tem traço anda.
                partes.append(replace(folha, ordem=proxima_ordem))
                proxima_ordem += 1
            else:
                vazias.append(folha)
            # **O prazo é conferido DEPOIS de emitir, nunca antes.** Antes, uma
            # passada que chegasse aqui com o relógio no fim devolveria zero
            # folhas e reenfileiraria — e o arquivo giraria a fila sem avançar
            # um milímetro, gastando o teto acumulado inteiro em passadas
            # estéreis. Emitindo primeiro, toda passada que roda produz pelo
            # menos uma folha, e o progresso é monótono por construção.
            #
            # **E o prazo vencido não basta: tem de haver alguém para receber a
            # vez** *(decisão do dono, 16/08/2026)*. Ceder com a fila vazia
            # devolvia a cadeira a ninguém e cobrava o custo fixo de novo na
            # passada seguinte — 56% do relógio, medido. A pergunta fica **depois**
            # do relógio na condição de propósito: enquanto o prazo não vence ela
            # não é feita, e por isso não custa uma consulta por folha no caso
            # normal, que é o arquivo que termina dentro do turno.
            if (
                prazo is not None
                and processados < len(pranchas)
                and time.monotonic() >= prazo
                and (ceder is None or ceder())
            ):
                break

        restam = len(pranchas) - processados
        vazias_total = vazias_antes + len(vazias)
        registros_vazios_total = registros_vazios_antes + sum(v.tracos for v in vazias)

        if not partes and not restam and not vazias_antes:
            # Nenhum aglomerado do arquivo inteiro desenhou coisa alguma.
            raise self._nada_a_desenhar(documento)

        # `desenhos` é o total **conhecido até aqui**, e ele cresce a cada
        # passada. A última é quem escreve o número final; o pipeline reescreve o
        # censo das folhas anteriores quando fecha, para a frase "este arquivo
        # traz N desenhos" não sair menor do que o arquivo é.
        censo = {"desenhos": proxima_ordem - 1}
        if vazias_total:
            censo["desenhos_sem_traco"] = vazias_total
            censo["registros_sem_traco"] = registros_vazios_total
        partes = [
            replace(p, detalhe={**p.detalhe, **censo, "ordem": p.ordem})
            for p in partes
        ]

        pendente = Retomada(
            grupos_feitos=processados,
            desenhos_feitos=proxima_ordem - 1,
            restam=restam,
            vazios_feitos=vazias_total,
            registros_vazios_feitos=registros_vazios_total,
        ) if restam else None

        return Saida(
            # `partes[0]` e não "a folha 1": numa passada de retomada a primeira
            # deste lote é a folha 12, e é ela que representa o que esta passada
            # produziu. Quem abre a prancha continua abrindo a folha 1, que já
            # está gravada desde a primeira passada.
            conteudo=partes[0].conteudo if partes else b"",
            extensao="svg",
            content_type="image/svg+xml",
            detalhe=partes[0].detalhe if partes else dict(comum),
            partes=tuple(partes),
            retomada=pendente,
        )

    def _folha(self, player, grupo, *, ordem, unidades, comum, sozinho, nome,
               espaco, layout, svg, teto_snap: int | None = 0) -> Parte:
        """Emite a folha de **um** desenho, com a régua dele.

        O recorte é o oposto de amputar: cada aglomerado ganha a folha que lhe
        cabe e **nenhum é descartado** — o traço solto vira a sua própria folha,
        de uma linha, e quem julga se aquilo é lixo ou é o marco topográfico que
        alguém foi a campo levantar continua sendo o dono do arquivo.

        **Desenho sozinho não passa pelo recorte**, e isso é garantia, não
        economia: a folha sai byte a byte igual à de antes desta mudança, então
        as pranchas normais do acervo — a esmagadora maioria — não têm como
        regredir. Marcação e medição já feitas nelas continuam sobre exatamente a
        mesma geometria de página.
        """
        envolvente = _envolvente(grupo)
        recortado = player
        if not sozinho:
            largura = envolvente[2] - envolvente[0]
            altura = envolvente[3] - envolvente[1]
            # Tolerância de achatamento das curvas que o recorte precisa
            # aproximar. Relativa ao desenho: um valor fixo seria grosseiro numa
            # peça de 1 m e caríssimo num levantamento de 1 km.
            tolerancia = max(largura, altura) / 10_000 or 1e-9
            recortado = player.copy()
            recortado.crop_rect(
                (envolvente[0] - FOLGA_RECORTE, envolvente[1] - FOLGA_RECORTE),
                (envolvente[2] + FOLGA_RECORTE, envolvente[3] + FOLGA_RECORTE),
                tolerancia,
            )

        backend = _backend_svg_com_hachura(svg, getattr(self, "_padroes", {}))
        recortado.replay(backend)
        # A envolvente do que virou `<path>`, **em unidade de desenho**, lida
        # antes de o `get_string` transformar os registros para o espaço do
        # `viewBox`. Junto com a leitura de depois, é o que devolve a coordenada
        # original do CAD ao leitor de tela — ver `_mundo_da_folha`.
        mundo_antes = backend.player().bbox()
        # Página 0×0 = o ezdxf deduz o tamanho da extensão do que sobrou. É o
        # certo aqui: quem define a folha é o desenho, não nós — arbitrar A1
        # cortaria um desenho A0 pela metade. E é o que mantém a regra "1 unidade
        # = 1 mm" válida, de que a régua depende.
        pagina = layout.Page(0, 0, layout.Units.mm, layout.Margins.all(MARGEM_MM))
        # Depois do recorte a ocupação é ~1 por construção, então a grade volta ao
        # padrão do ezdxf e o SVG emagrece. O cálculo fica como rede de segurança:
        # é ele que impede o desenho de ser **destruído na emissão** (segmentos
        # arredondados para `l -0 -0`) se um aglomerado ainda sair esparso.
        ocupacao = _ocupacao(envolvente)
        # O lado maior da folha em unidade de desenho, estimado: o `ezdxf` monta
        # a página com `scale=1` e `MARGEM_MM` de cada lado, então é o lado maior
        # do desenho mais duas margens. A folha real difere por arredondamento de
        # 0,1 mm — irrelevante para *dimensionar* a grade, e conferido de fato
        # logo abaixo, contra a folha que saiu.
        lado_maior = max(envolvente[2] - envolvente[0],
                         envolvente[3] - envolvente[1]) + 2 * MARGEM_MM
        # **Para cima, no passo de 0,1 mm** — é o que o `Page.width_in_mm` faz, e
        # sem reproduzi-lo a estimativa sai curta pelo arredondamento: medido,
        # 93,48512 vira 93,5 e a precisão obtida ficava 0,016% acima do alvo,
        # falhando o teste pelo próprio fio que ele existe para prender.
        lado_maior = ceil(lado_maior / PASSO_DA_PAGINA_MM) * PASSO_DA_PAGINA_MM
        grade = _grade_de_saida(ocupacao, lado_maior)
        conteudo = backend.get_string(pagina, settings=layout.Settings(
            scale=ESCALA_SAIDA_MM_POR_UNIDADE,
            output_coordinate_space=grade,
            # A espessura do traço como fração da folha (D48). Fica aqui e não na
            # `Configuration` porque é **por folha**: a política `RELATIVE` mora
            # no `Frontend`, mas o número que ela consome é da página, e página é
            # o que a PRA.1c passou a haver uma por desenho. Escala junto com a
            # grade por ser fração de `output_coordinate_space`.
            #
            # **Multiplicado pela ocupação**, e sem isso o conserto ficava pela
            # metade. `MARGEM_MM` é absoluta (10 mm), então ela é 1,2% de uma
            # folha de 841 mm e 40% de uma de 30 mm — a folha do MESMO desenho
            # modelado em metros. Como a `RELATIVE` do ezdxf mede a fração da
            # PÁGINA, o desenho pequeno na página ainda receberia traço ~1,7×
            # mais grosso em relação a si mesmo. Corrigir a margem seria o
            # caminho direto e está proibido: a largura da página é a régua
            # (`escala_do_desenho` a lê do SVG emitido), e mexer nela mudaria o
            # valor de toda medida já anotada no canteiro. Compensar aqui é
            # gratuito — `ocupacao` já está calculada — e deixa o traço constante
            # em relação ao DESENHO, que é o que a vista mostra. Prancha normal
            # tem ocupação ~1 e não paga nada.
            max_stroke_width=ESPESSURA_RELATIVA * (ocupacao or 1.0),
        ))
        conteudo = _fundo_em_porcentagem(conteudo)

        mundo = _mundo_da_folha(mundo_antes, backend.player().bbox(), conteudo)

        detalhe = {
            **comum,
            "ordem": ordem,
            "tracos": len(grupo),
            "ocupacao": ocupacao,
            "grade": grade,
        }
        if not mundo:
            # Silêncio aqui seria o defeito do D90 de novo: a tela mostraria
            # coordenada de folha achando que é coordenada de desenho.
            detalhe["mundo_erro"] = "envolvente degenerada ou sem viewBox"
        else:
            # **A precisão obtida, medida e não prometida.** `por_folha` são as
            # unidades de desenho na largura da folha e o `viewBox` são os
            # inteiros na mesma largura: a divisão é exatamente o passo em que a
            # tinta pode existir. Quando ela não alcança a quinta casa (folha
            # gigante contra o teto da grade), quem lê a memória de conversão
            # descobre — em vez de o sistema anunciar cinco casas e entregar
            # três.
            caixa_de_visao = _CAIXA_DE_VISAO.search(conteudo[:600])
            if caixa_de_visao:
                passo = mundo["por_folha"] / float(caixa_de_visao.group(1))
                detalhe["precisao_desenho"] = passo
                if passo > PRECISAO_DE_DESENHO:
                    detalhe["precisao_insuficiente"] = True
        if espaco == "paperspace":
            # A folha do paperspace mede papel, não obra (ver `_para_svg`). Sem
            # régua, e **dizendo** que é sem régua: a tela precisa distinguir
            # "este desenho não declara unidade" de "esta folha não pode declarar".
            detalhe["escala_indisponivel"] = "paperspace"
        else:
            # A régua sai do SVG **desta folha**, e é o que conserta a medida: as
            # duas grandezas vêm da mesma página emitida. Medida sobre a folha
            # antiga, a largura do `confrontantes` dava 143 km e a escala era
            # recusada; sobre a folha do desenho, dá o que o desenho mede.
            detalhe.update(escala_do_desenho(conteudo, unidades))

        # **O snap sai do gravador do BACKEND, e não do `recortado`** — é o
        # conserto do D90, e é contraintuitivo o bastante para não sobreviver sem
        # esta nota.
        #
        # O caminho óbvio é indexar o mesmo `recortado` que virou o SVG, e ele
        # está errado por dentro: o `Player.replay()` repassa `PathRecord` e
        # `FilledPathsRecord` **por referência** ao gravador do backend, e o
        # `get_string()` acima transforma esses registros *in place* para o
        # espaço do `viewBox`. Depois desta linha o `recortado` fala dois
        # idiomas — linha em milímetro, arco em unidade de `viewBox` —, e medir
        # isso é o que a bbox dele denuncia: `2,97 … 892.968` na
        # `01_02-DETALHE_DAS_SAPATAS`. Indexá-lo mandava 1.699 dos 3.214
        # registros da prancha (todo arco, círculo, polilinha, hachura e texto)
        # para o filtro de "fora da folha", **em silêncio**, e a mira ia grudar
        # no vértice de linha mais próximo — outro lugar.
        #
        # O gravador do backend não tem esse problema: ele guarda exatamente a
        # geometria que virou `<path>`, e depois do `get_string` está **inteiro**
        # no espaço do `viewBox`. Indexá-lo é indexar o desenho que está na tela,
        # e normalizar vira uma divisão pela largura do `viewBox`.
        #
        # (O recorte continua importando, e é por isso que ele vem antes: com o
        # player inteiro, cada folha indexaria o desenho todo e a mira grudaria
        # em traço de outra folha.)
        indice = self._snap_da_folha(backend.player(), teto_snap, detalhe,
                                     folha=_folha_emitida(conteudo))

        return Parte(
            conteudo=conteudo.encode("utf-8"),
            ordem=ordem,
            caixa={
                "xmin": round(envolvente[0], 6), "ymin": round(envolvente[1], 6),
                "xmax": round(envolvente[2], 6), "ymax": round(envolvente[3], 6),
            },
            mundo=mundo,
            tracos=len(grupo),
            detalhe=detalhe,
            nome=nome,
            snap=indice[0],
            snap_pontos=indice[1],
            snap_truncado=indice[2],
        )

    def _snap_da_folha(self, emitido, teto_snap, detalhe, *, folha):
        """O índice de snap desta folha — ou nada, sem derrubar a prancha.

        `emitido` é o gravador do `SVGBackend` **depois** do `get_string`, e
        `folha` é a régua do `viewBox` desse mesmo SVG: os dois falam o espaço do
        arquivo emitido, e é essa concordância que faz a mira grudar no traço
        (D90). Ver a nota no `_folha`, que é onde o par se forma.

        **Falha aqui nunca leva o SVG junto**, e essa é a decisão de produto: o
        snap é um extra pago, a prancha é o produto. Cliente que perde a
        visualização porque o índice estourou abriria chamado dizendo que o
        sistema quebrou — e estaria certo. Estourou, sai sem mira, e a memória de
        conversão diz por quê.
        """
        if not teto_snap:
            return None, 0, False
        if folha is None:
            # Sem a régua do arquivo emitido não há como normalizar a geometria
            # que ele contém, e chutar uma é o próprio D90. Melhor sem mira.
            logger.warning("prancheta: SVG sem viewBox legível; folha sem snap")
            detalhe["snap_erro"] = "sem_viewbox"
            return None, 0, False
        from . import snap as snapmod

        try:
            indice = snapmod.indice_de_snap(
                emitido,
                teto=teto_snap if teto_snap is not None else snapmod.SEM_TETO,
                folha=folha,
            )
            octetos = snapmod.empacotar(indice)
        except Exception as exc:
            # Sem `raise`: ver a docstring. Fica registrado para virar número, e
            # não para virar mistério — é o que permite descobrir que uma família
            # de desenho não indexa sem esperar o cliente reclamar.
            logger.warning("prancheta: índice de snap falhou (%s)", exc, exc_info=True)
            detalhe["snap_erro"] = type(exc).__name__
            return None, 0, False

        detalhe["snap_pontos"] = indice.total()
        detalhe["snap_truncado"] = indice.truncado
        # **Ponto fora da folha agora é notícia, não rotina.** Antes do D90 este
        # contador media o próprio desenho sendo descartado (a geometria que o
        # `get_string` já tinha levado para o espaço do `viewBox`), e por isso
        # marcar centenas de milhares era normal. Indexando o gravador do
        # backend, o que ele conta é geometria que o `ezdxf` colocou fora da
        # página que ele mesmo dimensionou — o que não deveria acontecer. Sai na
        # memória de conversão para ser investigado, não para virar paisagem.
        if indice.censo.get("pontos_fora_da_folha"):
            detalhe["snap_fora_da_folha"] = indice.censo["pontos_fora_da_folha"]
        if indice.censo.get("celulas_densas"):
            # Região onde a varredura desistiu de cruzar. Não é erro — é hachura
            # ou pontilhado que escapou do filtro —, mas explica interseção que
            # falta num canto específico da prancha.
            detalhe["snap_celulas_densas"] = indice.censo["celulas_densas"]
        return octetos, indice.total(), indice.truncado

    # -- o paperspace, e o que fazer quando não há desenho nenhum -------------
    def _pranchas_do_paperspace(self, documento, *, Frontend, RenderContext,
                                Recorder, config) -> list[tuple]:
        """Uma folha por aba de layout que tenha o que desenhar (D44).

        **A aba do CAD já É a unidade que a PRA.1c inventou.** Boa parte da
        prancha de projeto é composta no paperspace — moldura, carimbo, legendas
        e *viewports* apontando para o modelo —, e nesses arquivos o modelspace
        fica vazio: o `ezdxf` não acha extensão, levanta `empty bounding box` e a
        prancha inteira virava `falha_motor`. Medido no acervo, as mesmas folhas
        rendem de 66 a 217 KB de SVG quando se desenha o `Layout1`.

        **Sem separação por lacuna aqui, de propósito.** No modelspace a lacuna
        distingue desenhos que só por acaso moram no mesmo arquivo; um layout é
        uma folha física, e partir moldura de carimbo por causa do vazio entre
        eles inventaria duas pranchas onde o projetista vê uma.

        Ordem de aba, não de área: é assim que ele as conhece — e o nome da aba
        vira o nome da folha, que é a única vez em que este módulo recebe um nome
        escrito por gente sem pedir a ninguém.
        """
        pranchas = []
        for nome in documento.layout_names_in_taborder():
            if nome.lower() == "model":
                continue
            try:
                player, caixas = self._gravar(documento, documento.layout(nome), **{
                    "Frontend": Frontend, "RenderContext": RenderContext,
                    "Recorder": Recorder, "config": config,
                })
            except NAO_EMBRULHAR:
                # O teto de recurso **precisa** derrubar as outras: seguir para a
                # aba seguinte depois de estourar a memória entregaria uma prancha
                # incompleta em silêncio, e o cliente não teria como saber que
                # falta folha. É o oposto exato do caso abaixo.
                raise
            except Exception:
                # Uma aba quebrada não pode derrubar as outras: a prancha do
                # cliente costuma ter várias, e entregar 3 de 4 é estritamente
                # melhor que entregar nenhuma.
                continue
            if caixas:
                pranchas.append((player, caixas, True, nome))
        return pranchas

    def _nada_a_desenhar(self, documento) -> ErroDeConversao:
        """Nada saiu — e a resposta honesta depende de **por quê** (D45).

        Três desfechos, e até a PRA.1b os três liam a mesma frase de defeito:

        1. **XREF inserido e não enviado** — a geometria mora em arquivo externo,
           referenciado por caminho absoluto da máquina do projetista. É o único
           acionável, e por quem enviou: reenviar com as referências. Nenhum
           motor desenha o que não está no arquivo, então **não** pode virar
           upsell;
        2. **arquivo sem nenhuma entidade** — 5 dos 150 da remedição. Não há
           defeito a confessar nem plano a vender;
        3. **o resto é nosso** — havia entidade e mesmo assim não desenhou. Cai
           no `_ilegivel`, que já sabe se o arquivo ilegível é o do cliente ou o
           DXF intermediário que geramos (D42).

        A ordem importa: o XREF vem primeiro porque um arquivo que só insere
        referências externas *tem* entidades (as inserções vazias) e cairia no
        terceiro balde, acusando-nos de um defeito que é ausência de anexo.
        """
        xrefs = _xrefs_inseridas(documento)
        if xrefs:
            lista = ", ".join(xrefs[:3])
            resto = f" (e mais {len(xrefs) - 3})" if len(xrefs) > 3 else ""
            return ReferenciaAusente(
                f"Esta prancha referencia {len(xrefs)} arquivo(s) externo(s) que não "
                f"foram enviados: {lista}{resto}. Envie-os junto — a geometria está "
                "neles, e nenhum conversor desenha o que não veio no arquivo.",
                xrefs=xrefs[:10],
            )
        if not _tem_entidade(documento):
            return DesenhoVazio(
                "O desenho está vazio — o arquivo não traz nenhuma entidade, nem no "
                "modelspace nem nas abas de layout."
            )
        return self._ilegivel(
            cliente="O desenho tem entidades, mas nenhuma delas produziu traço.",
            nosso="saiu com entidades que não produziram traço nenhum",
        )


def _tem_traco(conteudo: bytes) -> bool:
    """Se esta folha desenhou alguma coisa.

    O `SVGBackend` do ezdxf emite **tudo** como `<path>` — linha, polilinha,
    hachura e até o glifo do texto, que é preenchimento. Então a presença de um
    `<path>` é a pergunta certa, e é mais confiável que olhar o tamanho do
    arquivo: o cabeçalho e o bloco de estilos sozinhos já dão alguns KB, e uma
    folha em branco pesaria como uma folha desenhada.
    """
    return b"<path" in conteudo


def _ocupacao(envolvente) -> float:
    """Quanto o desenho ocupa do maior lado da folha que ele mesmo gerou.

    Depois do recorte isto é ~1 por construção, e é justamente por isso que
    continua sendo calculado: se algum dia um aglomerado sair esparso, é este
    número que dimensiona a grade de saída e impede o desenho de ser destruído
    na emissão (ver `_grade_de_saida`).
    """
    largura = envolvente[2] - envolvente[0]
    altura = envolvente[3] - envolvente[1]
    lado_folha = max(largura + 2 * MARGEM_MM, altura + 2 * MARGEM_MM)
    if lado_folha <= 0:
        return 0.0
    return round(max(largura, altura) / lado_folha, 6)


def _grade_de_saida(ocupacao, lado_maior_da_folha: float = 0.0) -> int:
    """A grade de coordenadas do SVG, dimensionada pelo **desenho** e não pela folha.

    O `SVGBackend` estica uma grade de inteiros sobre a folha inteira; quem ocupa
    pouco da folha recebe pouco da grade, e some — não por estar pequeno na tela,
    mas por ter sido **arredondado para zero na emissão**. Este é o único degrau
    do D46 que o zoom não substitui: ele decide se a informação existe.

    Três exigências, e vence a maior:

    1. o padrão do `ezdxf` como piso — prancha que já ocupa a folha não paga
       nada, e é a esmagadora maioria do acervo;
    2. `RESOLUCAO_ALVO` unidades para o menor desenho da folha (o D46);
    3. **uma unidade de grade não pode valer mais que `PRECISAO_DE_DESENHO`.**
       As coordenadas do SVG são inteiras, então elas *são* o passo em que a
       tinta pode existir: com 1e6 numa folha A1, o traço só pode estar em
       múltiplos de 0,000861 unidade de desenho — a quarta casa. Era isto que
       fazia a mira "travar na casa decimal mais próxima" e o desvio crescer com
       o zoom, porque o índice guarda o valor **antes** do arredondamento e a
       tinta fica no inteiro depois dele.

    `lado_maior_da_folha` vem em unidade de desenho e é o lado que recebe a grade
    inteira (o `ezdxf` normaliza o maior). É estimado a partir da envolvente,
    porque a folha só existe depois de emitir — e por isso o `_folha` **confere**
    a precisão obtida contra a folha real e registra em `detalhe`. Estimar aqui é
    seguro: erra no tamanho da margem, e a conferência é que vale.

    O teto continua: a grade maior engorda o SVG, e num levantamento de milhões
    de unidades a quinta casa decimal pediria uma grade que ele não comporta —
    caso em que `precisao_insuficiente` diz isso em vez de o sistema fingir.
    """
    alvos = [float(GRADE_PADRAO)]
    if ocupacao and ocupacao > 0:
        alvos.append(RESOLUCAO_ALVO / ocupacao)
    if lado_maior_da_folha > 0:
        alvos.append(lado_maior_da_folha * FOLGA_DA_GRADE / PRECISAO_DE_DESENHO)
    # `ceil` e não `int`: truncar tira uma fração de unidade da grade, e essa
    # fração vira precisão pior que a pedida — no oitavo dígito, mas o contrato
    # é "≤ 1e-5", não "≈ 1e-5".
    return min(GRADE_MAXIMA, ceil(max(alvos)))


def _agrupar(caixas) -> tuple[list[list], int]:
    """Separa os traços em desenhos, cortando onde o vazio é maior que o desenho.

    **O caso real que define o critério:** `confrontantes.dwg` traz a mesma área
    desenhada duas vezes — uma na origem e uma em coordenada UTM —, a 8,5 milhões
    de unidades de distância, com 169 traços cada. E o acervo traz também o
    *sheet set* montado no modelspace: dezenas de plantas em grade, que o
    projetista enxerga como dezenas de pranchas e o sistema via como uma folha
    quilométrica.

    Corta recursivamente, sempre pela lacuna que mais folgadamente satisfaz
    `FATOR_SEPARACAO`, em qualquer dos dois eixos. Devolve os grupos de caixas
    (não as envolventes: quem chama precisa da contagem e do recorte) já
    ordenados do maior para o menor, mais quantos cortes o teto impediu.

    **A varredura é linear por nível**, com envolventes acumuladas de cada lado —
    a versão ingênua (recalcular a envolvente dos dois lados a cada lacuna
    candidata) seria quadrática, e o acervo tem prancha de 36 mil traços.
    """
    pendentes = [list(caixas)]
    finais: list[list] = []
    truncados = 0

    while pendentes:
        grupo = pendentes.pop()
        if len(finais) + len(pendentes) + 1 >= MAX_DESENHOS:
            # Teto alcançado: o que resta fica junto, e o chamador é avisado.
            finais.append(grupo)
            truncados += len(pendentes)
            finais.extend(pendentes)
            break
        corte = _melhor_corte(grupo)
        if corte is None:
            finais.append(grupo)
            continue
        eixo, limite = corte
        # O vazio é vazio por construção (`limite` é o fim corrido do último traço
        # antes dele), então nenhuma caixa atravessa o corte.
        pendentes.append([c for c in grupo if c[eixo] <= limite])
        pendentes.append([c for c in grupo if c[eixo] > limite])

    # Do maior para o menor: quem abre a prancha quer o desenho, não o traço
    # solto. O empate (duas poligonais idênticas) desempata pela posição, para a
    # ordem ser estável entre conversões — se ela dançasse, o nome que o usuário
    # deu ao "Desenho 2" mudaria de desenho no reprocessamento.
    def chave(grupo):
        e = _envolvente(grupo)
        return (-(e[2] - e[0]) * (e[3] - e[1]), -len(grupo), e[1], e[0])

    return sorted((g for g in finais if g), key=chave), truncados


def _melhor_corte(grupo) -> tuple[int, float] | None:
    """Onde partir este grupo, ou `None` se ele já é um desenho só.

    Avalia toda lacuna dos dois eixos e escolhe a que mais supera o próprio
    desenho — não a maior em valor absoluto. A diferença importa numa folha com
    escalas mistas: um vazio de 2 m entre dois levantamentos de 1 km é respiro, e
    um de 2 m entre dois detalhes de 20 cm são dois desenhos.
    """
    if len(grupo) < 2:
        return None

    melhor = None
    for eixo in (0, 1):
        ordenadas = sorted(grupo, key=lambda c: c[eixo])
        # Envolventes acumuladas: `prefixo[i]` cobre `ordenadas[:i+1]` e
        # `sufixo[i]` cobre `ordenadas[i:]`. É o que torna a varredura linear.
        prefixo = list(_acumular(ordenadas))
        sufixo = list(_acumular(reversed(ordenadas)))[::-1]

        fim = ordenadas[0][eixo + 2]
        for i in range(len(ordenadas) - 1):
            fim = max(fim, ordenadas[i][eixo + 2])
            lacuna = ordenadas[i + 1][eixo] - fim
            if lacuna <= 0:
                continue
            # O **maior** dos dois vizinhos é a referência — ver `FATOR_SEPARACAO`.
            referencia = max(_lado(prefixo[i]), _lado(sufixo[i + 1]))
            if referencia <= 0:
                continue
            folga = lacuna / (referencia * FATOR_SEPARACAO)
            if folga > 1.0 and (melhor is None or folga > melhor[0]):
                melhor = (folga, eixo, fim)

    return (melhor[1], melhor[2]) if melhor else None


def _acumular(caixas):
    """Envolvente acumulada, uma por caixa lida, na ordem em que vierem."""
    atual = None
    for c in caixas:
        atual = c if atual is None else (
            min(atual[0], c[0]), min(atual[1], c[1]),
            max(atual[2], c[2]), max(atual[3], c[3]),
        )
        yield atual


def _lado(envolvente) -> float:
    """O maior lado da envolvente — o "tamanho do desenho" do critério."""
    return max(envolvente[2] - envolvente[0], envolvente[3] - envolvente[1])


def _unidade_efetiva(documento, grupos) -> tuple[int, dict]:
    """A unidade de desenho que vale, e o que a evidência disse sobre ela.

    **O cabeçalho mente com frequência, e o acervo prova.** O `confrontantes.dwg`
    declara `$INSUNITS = 2` (pés) e desenha em `(469.347 , 8.564.841)` — *easting*
    e *northing* de UTM, que por definição estão em **metros**. Aceitar o
    cabeçalho daria uma folha de 143 km (que a janela de plausibilidade recusa,
    e a prancha fica sem régua) ou, depois que cada desenho ganhou a folha certa,
    daria 338 m para um desenho de 1.109 m — **errado por 3,28× e dentro da
    janela**, que é o desfecho pior: número com cara de certo.

    Por isso a coordenada tem precedência sobre o cabeçalho quando ela é
    inequívoca. Não é adivinhação: um desenho cujo aglomerado tem o centro dentro
    da janela UTM está georreferenciado, e UTM não tem unidade opcional.

    O contrário — cabeçalho ausente e coordenada UTM — também é resolvido aqui, e
    é o ganho que passa despercebido: o levantamento topográfico que não declara
    `$INSUNITS` (o caso mais comum da §13.2) **passa a ter régua** em vez de
    exigir que alguém calibre com o dedo o que o arquivo já sabia.
    """
    declarada = _unidades(documento)
    if not _parece_utm(grupos):
        return declarada, {"georreferenciado": False}

    georreferencia = {
        "georreferenciado": True,
        "sistema_provavel": "UTM",
        "unidades_declaradas": declarada,
    }
    # 6 = metros na tabela do DXF. Sobrepõe o cabeçalho, e diz que sobrepôs.
    if declarada != 6:
        georreferencia["unidade_corrigida"] = (
            "O cabeçalho declara "
            f"{METROS_POR_UNIDADE.get(declarada, (0, 'nada'))[1]}, mas as coordenadas "
            "são UTM — que é métrico. Usada a unidade da coordenada."
        )
    return 6, georreferencia


def _parece_utm(grupos) -> bool:
    """Se algum desenho tem o centro dentro da janela de coordenada UTM.

    Por **desenho** e não pela envolvente do arquivo, porque o caso real é
    justamente misto: o `confrontantes` tem uma cópia na origem `(0,0)` e outra em
    UTM. Testar a envolvente inteira (que vai de 0 a 8,5 milhões) não responderia
    nada — o centro dela não cai em lugar nenhum reconhecível.
    """
    for grupo in grupos:
        e = _envolvente(grupo)
        centro_x = (e[0] + e[2]) / 2
        centro_y = (e[1] + e[3]) / 2
        if (UTM_ESTE[0] <= centro_x <= UTM_ESTE[1]
                and UTM_NORTE[0] <= centro_y <= UTM_NORTE[1]):
            return True
    return False


def _caixas(registros) -> list[tuple[float, float, float, float]]:
    """Envolvente de cada traço gravado, sem os vazios.

    Uma varredura só: `Player.bbox()` faria a dela por dentro, e num desenho de
    35 mil traços o segundo passeio custa tanto quanto o primeiro.
    """
    caixas = []
    for registro in registros:
        caixa = registro.bbox()
        if caixa.has_data:
            caixas.append((caixa.extmin.x, caixa.extmin.y, caixa.extmax.x, caixa.extmax.y))
    return caixas


def _envolvente(caixas) -> tuple[float, float, float, float]:
    """O extremo — a folha que o ezdxf emitiria sozinho."""
    return (
        min(c[0] for c in caixas), min(c[1] for c in caixas),
        max(c[2] for c in caixas), max(c[3] for c in caixas),
    )


def _xrefs_inseridas(documento) -> list[str]:
    """Caminhos das referências externas que o desenho **insere** e não tem.

    XREF é sempre ausente por construção: o DWG/DXF guarda o caminho na máquina
    de quem desenhou (`C:\\Users\\…\\ESTRUTURA.dwg`) e a definição do bloco vem
    vazia. Nunca recebemos o arquivo apontado.

    **Só conta a que está inserida.** Um XREF descarregado ou desanexado deixa a
    definição para trás sem que nada dela apareça na prancha — e nesse caso a
    resposta certa é "o desenho está vazio", não "faltam anexos", que mandaria o
    cliente procurar arquivo que ele não precisa enviar.
    """
    try:
        definicoes = {
            bloco.name: bloco.block.dxf.get("xref_path", "")
            for bloco in documento.blocks
            if getattr(bloco.block_record, "is_xref", False)
        }
    except Exception:  # pragma: no cover - documento sem seção de blocos
        return []
    if not definicoes:
        return []

    inseridas: list[str] = []
    vistos: set[str] = set()
    for bloco in documento.blocks:
        for entidade in bloco:
            if entidade.dxftype() != "INSERT":
                continue
            nome = entidade.dxf.get("name", "")
            caminho = definicoes.get(nome)
            if caminho and caminho not in vistos:
                vistos.add(caminho)
                inseridas.append(caminho)
    return inseridas


def _tem_entidade(documento) -> bool:
    """Se há **qualquer** entidade no arquivo — modelspace ou aba de layout.

    A pergunta que separa "não desenhou" de "não tem desenho". Varrer os layouts
    junto do modelspace não é zelo: o arquivo cuja prancha mora só no paperspace
    (D44) tem modelspace vazio e não é, de forma alguma, um desenho vazio.
    """
    try:
        for nome in documento.layout_names():
            if len(documento.layout(nome)):
                return True
    except Exception:  # pragma: no cover - documento sem seção de layouts
        return False
    return False


def _tem_hachura(documento) -> bool:
    """Se há `HATCH`/`MPOLYGON` em qualquer lugar do arquivo.

    Varre `documento.blocks` e não os layouts: a coleção de blocos inclui os
    *block records* do modelspace e de cada paperspace **além** das definições de
    bloco, então é o único lugar que pega a hachura que só existe dentro de um
    bloco inserido — e é justamente o bloco repetido que multiplica o custo.

    Na dúvida responde `True`: errar para "tem hachura" gasta uma segunda
    passada, e errar para "não tem" nega ao cliente a única folha que ele
    conseguiria abrir.
    """
    try:
        return any(len(bloco.query("HATCH MPOLYGON")) for bloco in documento.blocks)
    except Exception:  # pragma: no cover - documento sem seção de blocos
        return True


def _frontend_que_conta_hachura(Frontend, censo: dict, config, padroes: dict | None = None):
    """`Frontend` que conta as hachuras desenhadas — e as que saíram pela metade.

    **A hachura truncada é o defeito silencioso que esta fatia encontrou.** O
    `ezdxf` tem um teto próprio por hachura (`hatching_timeout`, 30 s de fábrica)
    e, ao batê-lo, ele **para no meio, desenha as linhas que já acumulou** e
    avisa por `print()` no stdout do worker. O resultado é uma área hachurada até
    a metade numa folha que se declara pronta — e ninguém fica sabendo, porque
    `print` não é log e não chega a lugar nenhum.

    Herdar do `Frontend` é o ponto de extensão que o próprio `ezdxf` oferece
    (`draw_hatch_pattern` é método público e sobrescrevível), então isto não é
    gancho torto: é a API. Medir o relógio em volta da chamada é o que revela o
    truncamento, já que o abort acontece exatamente no teto e não levanta nada.

    O censo é um dicionário de fora, e de propósito: quando a conversão estoura,
    a exceção leva embora o objeto do `Frontend`, mas os números ficam com quem
    os pediu.
    """
    teto = float(getattr(config, "hatching_timeout", 0) or 0)

    class _FrontendComCenso(Frontend):
        def draw_hatch_pattern(self, polygon, paths, properties):
            familias = hachura.capturar(polygon) if padroes is not None else None
            if familias and self._contorno_da_hachura(polygon, properties, familias):
                censo["hachuras"] += 1
                censo["hachuras_nativas"] += 1
                return

            inicio = time.perf_counter()
            try:
                super().draw_hatch_pattern(polygon, paths, properties)
            finally:
                censo["hachuras"] += 1
                if teto and time.perf_counter() - inicio >= teto:
                    censo["hachuras_truncadas"] += 1

        def _contorno_da_hachura(self, polygon, properties, familias) -> bool:
            """Grava só o **contorno**, marcado para receber o padrão no SVG.

            O contorno é montado pelo mesmo caminho que o `ezdxf` usa no
            preenchimento sólido (`rendering_paths` + `closed_loops`), e não
            pelos `paths` que chegam ao `draw_hatch_pattern`: aqueles estão em
            OCS, porque quem os consome converte para WCS linha a linha. Reusar
            o caminho pronto é o que faz ilha, estilo de contorno e caixa de
            texto continuarem valendo sem reimplementação.

            **A identidade viaja pelo `handle`,** que é o único campo por
            registro que o `Recorder` preserva até a reprodução. Ele é
            sintético e único por hachura desenhada — o `handle` real seria o da
            **entidade de topo**, ou seja, o do `INSERT` quando a hachura está
            dentro de um bloco: duas inserções do mesmo bloco com rotações
            diferentes se sobrescreveriam, e todo o resto do bloco herdaria o
            preenchimento por engano.
            """
            try:
                from ezdxf.addons.drawing.frontend import closed_loops, ignore_text_boxes
            except ImportError:
                return False

            try:
                caminhos = closed_loops(
                    list(polygon.paths.rendering_paths(polygon.dxf.hatch_style)),
                    polygon.ocs(), polygon.dxf.elevation.z,
                )
                caminhos = [p for p in ignore_text_boxes(caminhos) if len(p)]
            except Exception:
                # Contorno que não se monta é hachura que não sabemos desenhar
                # barato — e aí o certo é pagar caro, não errar.
                return False
            if not caminhos:
                return False

            marca = f"\x00hachura:{len(padroes)}"
            padroes[marca] = (familias, properties.color)
            # `set_current_entity_handle` é a API pública do `pipeline` para
            # isto; o valor anterior sai de um atributo privado porque o
            # `ezdxf 1.4.4` não publica leitor. Restaurar é obrigatório: dentro
            # de um bloco o handle não é reposto por sub-entidade, e deixá-lo
            # trocado faria as entidades seguintes do mesmo `INSERT` caírem no
            # registro de padrões.
            anterior = getattr(self.pipeline, "_current_entity_handle", "")
            self.pipeline.set_current_entity_handle(marca)
            try:
                self.pipeline.draw_filled_paths(caminhos, properties)
            finally:
                self.pipeline.set_current_entity_handle(anterior)
            return True

    return _FrontendComCenso


def _backend_svg_com_hachura(svg, padroes: dict):
    """`SVGBackend` que resolve as marcas de hachura em `<pattern>` de verdade.

    **Por que o preenchimento vira atributo e não classe.** O `SVGRenderBackend`
    põe a cor de preenchimento numa regra CSS (`.C1 {fill: …}`) e regra de folha
    de estilo **vence** atributo de apresentação. Um `fill="url(#…)"` ao lado da
    classe seria simplesmente ignorado, e a área sairia da cor sólida da
    hachura — pior que o problema original, porque parece certo. Aqui a classe
    não é aplicada: o `fill` é o atributo, e ele é o único que fala.

    O `<defs>` dos padrões é próprio e não o do `Styles`, que é privado. SVG não
    exige ordem para resolver `url(#id)`, então um segundo `<defs>` no fim vale
    tanto quanto o primeiro.
    """
    from ezdxf.addons.drawing.svg import SVGRenderBackend

    class _RenderComHachura(SVGRenderBackend):
        def __init__(self, page, settings, matriz):
            super().__init__(page, settings)
            self._matriz = matriz
            self._defs = ET.SubElement(self.root, "defs")
            self._ids: dict = {}

        def add_filling(self, d: str, properties):
            registro = padroes.get(properties.handle)
            if not registro or not d:
                return super().add_filling(d, properties)
            identificadores = self._padroes(registro, properties)
            if not identificadores:
                # Reticulado degenerado depois da transformação: melhor a área
                # sólida do ezdxf do que uma referência quebrada, que o
                # navegador desenha como NADA.
                return super().add_filling(d, properties)
            # **Uma cópia do contorno por família de linhas.** Cada família tem
            # o seu próprio reticulado — o `AR-SAND` do acervo tem quatro, e há
            # padrões com 41 —, e um `<pattern>` só ladrilha um. Empilhar
            # preenchimentos é o que preserva o padrão inteiro; e é barato
            # porque o que se repete é o contorno, que tem dezenas de comandos,
            # não a área expandida, que tinha milhões.
            for ident in identificadores:
                elemento = ET.SubElement(self.entities, "path", d=d)
                elemento.set("fill", f"url(#{ident})")

        def _padroes(self, registro, properties) -> list[str]:
            familias, cor = registro
            espessura = self.resolve_stroke_width(properties.lineweight)
            chave = hachura.chave(familias, cor, espessura)
            if chave in self._ids:
                return self._ids[chave]
            elementos = hachura.elemento(
                familias, self._matriz,
                ident=f"h{len(self._ids) + 1}", cor=cor[:7], espessura=espessura,
            )
            if not elementos:
                self._ids[chave] = []
                return []
            for elemento in elementos:
                self._defs.append(elemento)
            identificadores = [e.get("id") for e in elementos]
            self._ids[chave] = identificadores
            return identificadores

    class _BackendComHachura(svg.SVGBackend):
        def make_backend(self, page, settings):
            return _RenderComHachura(page, settings, self.transformation_matrix)

    return _BackendComHachura()


def _censo_da_hachura(censo: dict, economia: str) -> dict:
    """Como a hachura saiu, em uma palavra, mais os números que a sustentam.

    Três estados, e cada um é uma frase diferente para quem abre a prancha:

    - `contorno` — a conversão fiel não coube no orçamento e esta folha é a
      segunda passada. As áreas hachuradas têm o bordo desenhado e o interior
      vazio. **Nada foi omitido**, e é isso que a tela precisa dizer;
    - `parcial` — o padrão de N hachuras era denso demais para o teto por
      entidade do `ezdxf`, e elas saíram até onde deu. É o único dos três em que
      a folha mostra menos do que o arquivo tem;
    - `completa` — o caso normal, declarado do mesmo jeito.
    """
    if economia == ECONOMIA_HACHURA:
        # Sob `SHOW_OUTLINE` o `draw_hatch_pattern` nem é chamado, então o censo
        # fica zerado por construção e contá-lo aqui diria "0 hachuras" sobre um
        # desenho cheio delas. Quem responde é a política, não o contador.
        return {"hachura": "contorno"}
    if censo.get("hachuras_truncadas"):
        return {
            "hachura": "parcial",
            "hachuras": censo["hachuras"],
            "hachuras_truncadas": censo["hachuras_truncadas"],
            "hachuras_nativas": censo.get("hachuras_nativas", 0),
        }
    # `hachuras_nativas` é declarado sempre, inclusive zero: é a diferença entre
    # a folha cujo padrão o navegador ladrilha e a que veio expandida em traço,
    # e quem lê a memória de conversão não tem como deduzir isso do resto.
    return {
        "hachura": "completa",
        "hachuras": censo.get("hachuras", 0),
        "hachuras_nativas": censo.get("hachuras_nativas", 0),
    }


def _unidades(documento) -> int:
    """`$INSUNITS` do cabeçalho, ou 0 (não declarada) se o arquivo não o traz."""
    try:
        return int(documento.units or 0)
    except (AttributeError, TypeError, ValueError):
        return 0


def escala_do_desenho(svg_texto: str, unidades: int) -> dict:
    """Quantos metros o desenho ocupa na largura inteira da folha renderizada.

    **É a diferença entre medir em pixel e medir como o AutoCAD.** O CAD responde
    "3,50 m" porque as coordenadas dele já estão em unidades de desenho e o
    cabeçalho diz qual é a unidade; um SVG não carrega nada disso, e por isso a
    PRA.3 nasceu exigindo calibração humana. Só que a informação **existe na
    origem** — jogá-la fora na conversão e depois pedir para uma pessoa redescobri-la
    com o dedo é perder precisão de graça.

    A conta tem duas metades, e as duas são medidas, não supostas:

    1. **quantas unidades de desenho cabem na largura da folha** — é a largura da
       página que o próprio ezdxf emitiu (`width="1020mm"`), lida do SVG e não
       recalculada por nós, porque quem arbitra margem e extensão é ele. Vale como
       unidade de desenho por causa do `scale=1.0` acima;
    2. **quanto vale uma unidade de desenho em metros** — `$INSUNITS`.

    Devolve `{}` quando o desenho não declara unidade (`$INSUNITS = 0`, muito
    comum), quando a unidade está fora da tabela ou quando o resultado cai fora da
    janela de plausibilidade. `{}` é resposta boa: a prancha segue sem régua, a
    tela diz isso e a calibração humana continua disponível. O que não se faz é
    escrever metro sem saber de onde ele veio.
    """
    fator, rotulo = METROS_POR_UNIDADE.get(unidades, (0.0, ""))
    if not fator:
        return {"unidades_desenho": unidades}

    achado = _LARGURA_SVG.search(svg_texto[:600])
    if not achado:
        return {"unidades_desenho": unidades}

    largura_m = float(achado.group(1)) * ESCALA_SAIDA_MM_POR_UNIDADE * fator
    minimo, maximo = LARGURA_PLAUSIVEL_M
    if not (minimo <= largura_m <= maximo):
        return {
            "unidades_desenho": unidades,
            "unidades_rotulo": rotulo,
            "escala_recusada": round(largura_m, 4),
        }

    return {
        "unidades_desenho": unidades,
        "unidades_rotulo": rotulo,
        # A grandeza que `RevisaoDocumento.escala_valor` guarda: unidades reais
        # na largura INTEIRA do desenho — não a escala da prancha (1:50), que é
        # outra coisa e não sobrevive ao zoom da tela.
        "escala_largura_m": round(largura_m, 6),
    }
