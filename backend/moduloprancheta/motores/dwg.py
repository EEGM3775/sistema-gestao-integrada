# backend/moduloprancheta/motores/dwg.py
"""Motor `libredwg` — DWG pelo caminho livre, e o upsell honesto quando não dá.

Este é o motor que a planta §4.1 chama de **o nó**: DWG é o formato dominante da
construtora brasileira e é onde a licença dói. A decisão registrada lá foi *os
dois motores*, com o degrau do plano sendo o motor — LibreDWG nos básicos, APS
(PRA.4) nos premium. Este arquivo é a metade livre.

**Três fatos operacionais que moldam o código:**

1. **O LibreDWG não é empacotado pelo Debian.** Não há `libredwg` em bookworm,
   trixie nem sid — conferido no `packages.debian.org`. Como a imagem do backend
   é `python:3.12-slim` (Debian), não existe `apt-get install` que resolva: o
   binário entra por *build stage* que compila do fonte (ver `backend/Dockerfile`).
   Consequência para este adaptador: ele **não pode supor que o binário existe**,
   e a ausência dele é `MotorIndisponivel` — nunca `MotorInsuficiente`.
2. **GPLv3.** O `dwg2dxf` é chamado como processo separado, então o nosso código
   segue proprietário; o que a imagem passa a ter é um componente GPL
   redistribuído, com as obrigações registradas em `THIRD-PARTY-LICENSES.md`
   (planta §12.3). Chamar como subprocesso não é detalhe de implementação — é a
   fronteira de licença, e trocá-la por um binding em processo mudaria a
   obrigação.
3. **A cobertura é medida, não suposta.** O LibreDWG declara ler até R2018
   (`AC1032`); acima disso as fontes se contradizem. O `medir_cobertura_dwg`
   existe para transformar isso em número sobre os DWGs reais do cliente — é esse
   número que decide onde fica a fronteira comercial entre os planos.

**O que este motor faz:** DWG → DXF (subprocesso) → entrega ao `MotorDxf`, que
desenha. A renderização mora num lugar só de propósito; ver `dxf.py`.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import replace

from payment.planos import (
    PRANCHETA_SUBPROCESSO_MEMORIA_MB,
    PRANCHETA_TIMEOUT_DWG_SEGUNDOS,
    PRANCHETA_TIMEOUT_PREVIEW_SEGUNDOS,
)

from .base import (
    ECONOMIA_SVG_DIRETO,
    NAO_EMBRULHAR,
    Adaptador,
    ArquivoCorrompido,
    DesenhoVazio,
    FalhaMotor,
    FalhaDoIntermediario,
    MotorIndisponivel,
    MotorInsuficiente,
    Parte,
    RecursoExcedido,
    Saida,
    SemPreviewEmbutido,
    executavel,
    orcamento_armado,
    morreu_por_falta_de_memoria,
    rodar,
    teto_do_subprocesso,
)
from . import svg_do_motor
from .documento import miniatura
from .dxf import MotorDxf

#: Variável para apontar o binário quando ele não está no `PATH` (ver nota 1).
ENV_BINARIO = "LIBREDWG_DWG2DXF"

#: Idem para o extrator de preview — outro binário da mesma tarball (§4.4).
ENV_BINARIO_BMP = "LIBREDWG_DWGBMP"

#: Idem para o desenhista do próprio LibreDWG, usado no último degrau da escada.
ENV_BINARIO_SVG = "LIBREDWG_DWG2SVG"

#: O que conta como traço num SVG vindo do `dwg2SVG`.
#:
#: **Não dá para reusar o critério do `dxf.py`** (que procura só `<path`): aquele
#: vale para o backend do `ezdxf`, que emite tudo como path. O LibreDWG emite
#: `<line>`, `<polyline>`, `<circle>` e `<use>` também — e `<use>` importa mais
#: aqui do que em qualquer outro lugar, porque é justamente por referência que
#: este caminho desenha a repetição.
ELEMENTOS_DE_TRACO = (
    b"<path", b"<line", b"<polyline", b"<polygon", b"<circle", b"<ellipse", b"<use",
)

#: O sentinela de "extensão não calculada" do LibreDWG, em módulo.
#:
#: Quando ele não consegue apurar a envolvente do desenho, os campos `EXTMIN`/
#: `EXTMAX` ficam com ±1e20 — e o `dwg2SVG` os publica assim mesmo, no `viewBox`
#: e em cada coordenada. O resultado é um SVG **sintaticamente perfeito e
#: geometricamente destruído**: sai com `rc=0`, com `<path>` de sobra, e com
#: todos os traços colapsados no mesmo ponto impossível.
#:
#: O valor é folgado de propósito. Coordenada de CAD real vive em milímetro ou
#: metro de obra; mesmo um DWG em UTM com dado de satélite não passa de ~1e7. Um
#: corte em 1e15 não tem como recusar desenho legítimo e pega o sentinela com
#: cinco ordens de grandeza de margem — inclusive se um build futuro do LibreDWG
#: trocar o número por outro da mesma família.
LIMITE_COORDENADA_PLAUSIVEL = 1e15

#: Teto de tempo do `dwgbmp`. Curto de propósito: ele lê só a seção de preview do
#: cabeçalho, não decodifica o desenho. Um minuto já é anomalia.
TIMEOUT_PREVIEW_SEGUNDOS = PRANCHETA_TIMEOUT_PREVIEW_SEGUNDOS

#: Teto de tempo do subprocesso. Uma prancha grande converte em segundos; 3 min
#: é folga generosa e ainda assim libera o worker antes de o Celery desistir.
TIMEOUT_SEGUNDOS = PRANCHETA_TIMEOUT_DWG_SEGUNDOS

#: Teto de MEMÓRIA do subprocesso — o par do de cima, e ele faltava (D78).
#:
#: Lido direto de `payment/planos.py`, como o relógio ao lado, e não via
#: `settings`: os motores não conhecem Django. A consequência declarada é que
#: este número, ao contrário do `PRANCHETA_CONVERSAO_MEMORIA_MB`, **não** tem
#: sobrescrita por variável de ambiente — se a operação precisar apertá-lo numa
#: VM pequena, ele passa a viajar pelo `settings` como o irmão.
MEMORIA_SUBPROCESSO_MB = PRANCHETA_SUBPROCESSO_MEMORIA_MB

#: Onde o `dwg2dxf` corta o valor de texto — medido, não suposto (D43). São 255
#: **bytes**, não caracteres: em `GbDemo/001` o corte cai em 255 bytes = 187
#: caracteres, porque o carimbo é CJK.
CORTE_DO_DWG2DXF = 255

#: Quanto do stderr do `dwg2dxf` viaja dentro do `MotorInsuficiente`.
STDERR_GUARDADO = 1500


def _stderr_util(erro: str) -> str:
    """O stderr sem descartar justamente a parte que diz o que houve.

    **Cortar pela cabeça descartava a causa** (medido em 09/08/2026). O LibreDWG
    escreve os avisos enquanto percorre o arquivo e o erro fatal **no fim**; com
    `erro[:500]`, os três DWGs acima de 40 MB que falharam chegaram ao relatório
    e ao log como ``Warning: Unstable Class object 501 MATERIAL`` — a mesma frase
    para os três, e nenhuma delas era o motivo. Foi preciso rodar o `dwg2dxf` à
    mão para saber por que a conversão parou, e é esse o trabalho que este corte
    criava toda vez.

    Cabeça **e** cauda porque as duas informam: o começo diz em que fase ele
    estava, o fim diz onde parou.
    """
    erro = (erro or "").strip()
    if len(erro) <= STDERR_GUARDADO:
        return erro
    cabeca = 300
    cauda = STDERR_GUARDADO - cabeca
    return f"{erro[:cabeca]}\n…[{len(erro) - STDERR_GUARDADO} caracteres omitidos]…\n{erro[-cauda:]}"


def folha_destruida(svg: bytes) -> str:
    """Por que este SVG não é uma prancha — `""` quando ele é.

    **A outra metade da lição do D52.** O `_svg_direto` já recusava SVG sem
    elemento de traço ("saiu byte não é desenho"), e isso cobre o arquivo vazio;
    não cobre o arquivo **destruído**, que é o modo de falha que o D52 ensinou a
    procurar. Medido em 10/08/2026 sobre `planta-amostra.dwg`: o `dwg2SVG` sai
    com `rc=0`, com 11 `<path>` e com `viewBox="1e20 1e20 -2e20 -2e20"`, cada
    traço colapsado no mesmo ponto impossível. Sem esta checagem o degrau
    entregaria essa folha como conversão bem-sucedida — pior que erro, porque
    ninguém vai investigar uma prancha que o sistema diz estar pronta.

    Duas perguntas, e cada uma pega um estrago diferente:

    - **dimensão não positiva** — largura ou altura ≤ 0 no `viewBox`. É o próprio
      sentinela chegando invertido (`-2e20`), e nenhum desenho legítimo produz
      isso;
    - **coordenada fora do plausível** — o sentinela chegando com o sinal certo,
      que a pergunta anterior deixaria passar.

    **`viewBox` ausente não reprova.** Quem julga aqui é a evidência positiva de
    destruição, não a falta dela: o formato do `dwg2SVG` pode mudar entre builds,
    e um guarda que reprova o que não entende transforma atualização de motor em
    acervo que para de abrir.
    """
    marca = svg[:2048].find(b'viewBox="')
    if marca < 0:
        return ""
    inicio = marca + len(b'viewBox="')
    fim = svg.find(b'"', inicio)
    if fim < 0:
        return ""
    try:
        numeros = [float(n) for n in svg[inicio:fim].split()]
    except ValueError:
        return ""
    if len(numeros) != 4:
        return ""

    _, _, largura, altura = numeros
    if largura <= 0 or altura <= 0:
        return (
            f"a folha saiu com dimensão impossível ({largura:g} × {altura:g}) — "
            "o motor não apurou a extensão do desenho"
        )
    if any(abs(n) >= LIMITE_COORDENADA_PLAUSIVEL for n in numeros):
        return (
            "a folha saiu em coordenadas fora de qualquer escala real "
            f"({largura:g} × {altura:g}) — o motor não apurou a extensão do desenho"
        )
    return ""


def _pedacos_seguros(bruto: bytes, teto: int = CORTE_DO_DWG2DXF) -> list[bytes]:
    """Fatia `bruto` em pedaços de até `teto` bytes **sem partir caractere**.

    Nunca corta imediatamente antes de um byte de continuação UTF-8 (`0b10xxxxxx`,
    ou seja, `0x80`–`0xBF`), recuando até a fronteira. Em página de código legada
    — que o DXF ainda admite via `$DWGCODEPAGE` — todo byte é um caractere e o
    recuo simplesmente não acontece, então a regra é segura nos dois mundos.
    """
    pedacos: list[bytes] = []
    inicio = 0
    while len(bruto) - inicio > teto:
        fim = inicio + teto
        while fim > inicio and 0x80 <= bruto[fim] <= 0xBF:
            fim -= 1
        if fim == inicio:  # pragma: no cover - caractere maior que o teto
            fim = inicio + teto
        pedacos.append(bruto[inicio:fim])
        inicio = fim
    pedacos.append(bruto[inicio:])
    return pedacos


def remendar_continuacoes(bruto: bytes) -> tuple[bytes, int]:
    """Devolve o DXF com as continuações órfãs do `dwg2dxf` remendadas (**D43**).

    **O defeito, medido em 09/08/2026.** O DXF é estritamente pares linha-a-linha
    (código de grupo, valor). Ao emitir texto acima de 255 bytes, o `dwg2dxf` do
    LibreDWG 0.13.3 escreve o primeiro pedaço no código `1` e **joga o resto na
    linha seguinte sem código nenhum**. O parser lê a continuação órfã como se
    fosse um código de grupo e morre::

          1
        图号=FILENAME;文件名称=DWGDESC;…;BY1=LINE14      ← 255 bytes exatos
        ;RD1=LINE15;REV2=LINE16;REV2DET=LINE17;…       ← órfã: faltou o "  3"

    É o **D43** inteiro: 22 dos 160 DWGs do corpus (13,8%) não abriam por isto, e
    o `ezdxf.recover` também não salva porque a quebra é estrutural, não sujeira.
    Não é arquivo do cliente ruim — é defeito do escritor de DXF, e por isso a
    frase de erro dizia a verdade ao chamá-lo de *nosso*.

    **Consertado a montante em 09/08/2026 — e esta função FICA.** Com o motor
    passando ao commit fixado (`0.14.8566`), o corte em 255 bytes não acontece
    mais: `convertido_apos_reparo: continuacao_orfa` sumiu do relatório da
    remedição. Manter o remendo não custa nada porque ele é **auto-limitado**
    (só dispara em valor de exatamente 255 bytes seguido de linha que não é
    código) e porque ele é a rede para dois casos que voltam sozinhos: um DWG
    convertido por versão anterior do binário e um arquivo que já esteja no
    acervo. Apagar código de defesa porque a versão de hoje não precisa dele é
    apostar que ninguém nunca mais vai reconverter nada.

    **A ordem importa, e errá-la corrompe o texto em silêncio.** Pela spec, texto
    longo vai como ``3 <pedaço>`` … ``3 <pedaço>`` **terminado** por
    ``1 <pedaço final>`` — o código original é o **último**. Pôr o `3` depois do
    `1` conserta a estrutura e a geometria sai idêntica, mas o MTEXT remonta com o
    fim na frente (``'7x; 34} 3.4{\\Fmonotxt…'`` em vez de
    ``'{\\Fmonotxt…} 3.4'``): mesmo tamanho, nada perdido, tudo embaralhado — e
    justamente em carimbo, legenda e chamada de cota. Um reparo validado só por
    *"abriu"* passaria por isso; foi preciso comparar o texto remontado.

    **Por que juntar e refatiar em vez de só inserir o código.** Preservar os
    pedaços como vieram bastaria para a quebra estrutural, mas deixaria de pé o
    outro filho do mesmo defeito: o corte é em **bytes**, então pode cair no meio
    de um caractere multibyte, e as duas metades ficariam em linhas separadas,
    decodificadas em separado. Juntando tudo e refatiando por
    `_pedacos_seguros`, os dois somem de uma vez.

    **Dispara estreito, de propósito:** só quando o valor tem *exatamente* o corte
    do `dwg2dxf` e a linha seguinte não é um código de grupo. Em DXF válido essa
    combinação não existe — depois de um par, a próxima linha é sempre um código.
    Por isso a passagem é inofensiva sobre arquivo são, e continuará inofensiva
    quando uma versão corrigida do LibreDWG tornar o remendo desnecessário.
    """
    linhas, quebra = _linhas_e_quebra(bruto)
    reparadas, remendos = _remendar_continuacoes_em_linhas(linhas)
    return (quebra.join(reparadas) if remendos else bruto), remendos


def _remendar_continuacoes_em_linhas(linhas: list[bytes]) -> tuple[list[bytes], int]:
    # **Saída antecipada, e ela é o que torna o reparo barato.** O gatilho é um
    # valor de **exatamente** 255 bytes; sem nenhum, não há o que remendar e não
    # se aloca lista nova. No maior DXF do corpus (84 MB, 2,6 milhões de linhas)
    # reconstruir a lista à toa custa centenas de MB — e foi assim que a 1ª
    # versão desta camada empurrou um arquivo que convertia para fora do
    # orçamento de memória.
    if not any(len(linha) == CORTE_DO_DWG2DXF for linha in linhas):
        return linhas, 0

    saida: list[bytes] = []
    remendos = 0
    indice = 0
    total = len(linhas)
    while indice < total:
        if not _eh_codigo(linhas[indice]):
            # Fora de par (cauda do arquivo, linha em branco): copia como está.
            saida.append(linhas[indice])
            indice += 1
            continue

        codigo = linhas[indice]
        if indice + 1 >= total:
            saida.append(codigo)
            break
        pedacos = [linhas[indice + 1]]
        indice += 2

        # Enquanto o pedaço tiver o tamanho exato do corte e o que vem a seguir
        # não for um código, é continuação órfã.
        while (
            len(pedacos[-1]) == CORTE_DO_DWG2DXF
            and indice < total
            and linhas[indice] != b""
            and not _eh_codigo(linhas[indice])
        ):
            pedacos.append(linhas[indice])
            indice += 1
            remendos += 1

        if len(pedacos) == 1:
            saida.extend([codigo, pedacos[0]])
            continue

        inteiro = _pedacos_seguros(b"".join(pedacos))
        for pedaco in inteiro[:-1]:
            saida.extend([b"  3", pedaco])
        saida.extend([codigo, inteiro[-1]])

    return saida, remendos

#: O que estrutura a seção `TABLES` — não é registro, é moldura.
ESTRUTURA_DA_TABELA = {b"TABLE", b"ENDTAB", b"SECTION", b"ENDSEC"}

#: Os quatro handles de bloco de seta da `DIMSTYLE` (`DIMBLK`, `DIMBLK1`,
#: `DIMBLK2`, `DIMLDRBLK`).
CODIGOS_DE_SETA_DE_COTA = {b"341", b"342", b"343", b"344"}

#: Quem tem `name` no DXF: registro de tabela e definição de bloco. **É esta a
#: fronteira que importa** — a `ezdxf` quebra ao resolver `db[handle].dxf.name`
#: quando o alvo não tem nome, e não quando ele é "o registro errado".
#:
#: Medido: uma regra que exigisse `BLOCK_RECORD` teria mexido em **35** arquivos
#: do corpus que já convertiam — apagando referência que a ezdxf resolve sem
#: reclamar. A regra estreita mexe só no que de fato derruba a carga.
TIPOS_COM_NOME = {
    b"BLOCK_RECORD", b"BLOCK", b"LAYER", b"LTYPE", b"STYLE",
    b"VIEW", b"UCS", b"APPID", b"DIMSTYLE", b"VPORT",
}


def _linhas_e_quebra(bruto: bytes) -> tuple[list[bytes], bytes]:
    quebra = b"\r\n" if bruto.count(b"\r\n") > bruto.count(b"\n") // 2 else b"\n"
    return [linha.rstrip(b"\r") for linha in bruto.split(b"\n")], quebra


def _eh_codigo(linha: bytes) -> bool:
    return linha.strip().lstrip(b"-").isdigit()


def descartar_registros_vazios(bruto: bytes) -> tuple[bytes, int]:
    """Tira da `TABLES` o registro que o `dwg2dxf` abre e não escreve (**D43**).

    **O defeito, medido em 09/08/2026 no `FILE.DWG` (AC1015, 13,8 MB).** O DXF
    sai **completo** — tem a tag `EOF`, então não é o truncamento da 2ª causa —,
    e mesmo assim o `ezdxf` morre com ``DXFTypeError: name has to be a string,
    got NoneType``. A mensagem manda procurar um nome inválido; o que existe é um
    registro **inteiramente vazio**, o último da tabela `BLOCK_RECORD`::

          0
        BLOCK_RECORD     ← abre o registro
          0
        ENDTAB           ← e o próximo par já fecha a tabela

    Sem código `5` (handle) e sem código `2` (nome). Todo registro de tabela
    precisa dos dois; um com zero tags não descreve coisa alguma, e é por isso
    que descartá-lo não perde informação — não há informação ali.

    **Dispara só dentro da `TABLES`** e só quando o par seguinte é outro código
    `0`. Na `BLOCKS` e na `ENTITIES` a mesma forma pode ser entidade legítima sem
    atributo, e apagá-la seria apagar desenho.
    """
    linhas, quebra = _linhas_e_quebra(bruto)
    reparadas, descartados = _descartar_registros_vazios_em_linhas(linhas)
    return (quebra.join(reparadas) if descartados else bruto), descartados


def _descartar_registros_vazios_em_linhas(
        linhas: list[bytes]) -> tuple[list[bytes], int]:
    vazios = _achar_registros_vazios(linhas)
    if not vazios:
        return linhas, 0
    a_pular = set(vazios) | {i + 1 for i in vazios}
    return [l for i, l in enumerate(linhas) if i not in a_pular], len(vazios)


def _achar_registros_vazios(linhas: list[bytes]) -> list[int]:
    """Varre sem alocar cópia — só os índices do que sai (quase sempre nenhum)."""
    achados: list[int] = []
    dentro_de_tabelas = False
    indice, total = 0, len(linhas)

    while indice < total - 1:
        if not _eh_codigo(linhas[indice]):
            indice += 1  # fora de par: ressincroniza no próximo código
            continue

        codigo, valor = linhas[indice].strip(), linhas[indice + 1].strip()
        if codigo == b"2" and valor == b"TABLES":
            dentro_de_tabelas = True
        elif codigo == b"0" and valor == b"ENDSEC":
            dentro_de_tabelas = False

        if (
            dentro_de_tabelas
            and codigo == b"0"
            and valor not in ESTRUTURA_DA_TABELA
            and indice + 2 < total
            and linhas[indice + 2].strip() == b"0"
        ):
            achados.append(indice)
        indice += 2

    return achados


def _tipos_por_handle(linhas: list[bytes]) -> dict[bytes, set[bytes]]:
    """Handle → tipos que o declaram. Conjunto porque **há handle repetido**.

    O `As-Built_REAL CONDOMINIO` traz 1.244 handles usados duas vezes (pares de
    `VERTEX`). Guardar o conjunto, e não o último, é o que permite decidir pelo
    lado seguro: se **algum** dono é `BLOCK_RECORD`, a referência pode resolver.
    """
    tipos: dict[bytes, set[bytes]] = {}
    tipo_atual = b"?"
    indice, total = 0, len(linhas)
    while indice < total - 1:
        if not _eh_codigo(linhas[indice]):
            indice += 1
            continue
        codigo, valor = linhas[indice].strip(), linhas[indice + 1].strip()
        if codigo == b"0":
            tipo_atual = valor
        elif codigo == b"5":
            tipos.setdefault(valor.upper(), set()).add(tipo_atual)
        indice += 2
    return tipos


def descartar_setas_de_cota_orfas(bruto: bytes) -> tuple[bytes, int]:
    """Solta a seta de cota que aponta para um objeto que não é bloco (**D43**).

    **O defeito, medido em 09/08/2026 no `As-Built_REAL CONDOMINIO` (AC1018).** O
    DXF sai completo e o `ezdxf` morre em ``DXFAttributeError: Invalid DXF
    attribute "name" for entity VERTEX`` — mensagem que manda procurar um VERTEX
    com nome, e não existe nenhum. O que existe é isto::

        DIMSTYLE Standard
            342 → #7    e o handle #7, neste arquivo, é um VERTEX

    O código `342` é o bloco da ponta da cota. A `ezdxf` resolve handle→nome no
    2º estágio da carga (`DIMSTYLE.post_load_hook`) fazendo
    ``db[handle].dxf.name``, e ela **prevê o handle que não existe** — captura
    `KeyError` e cai na seta padrão. O que ela não prevê é o handle que **existe
    e aponta para outra coisa**: aí o `.dxf.name` levanta `DXFAttributeError`, que
    não está no `except`, e a carga inteira morre por causa de uma ponta de seta.

    A raiz é o espaço de handles embaralhado do arquivo (1.244 repetidos), que é
    defeito de decodificação do LibreDWG. Aqui não se conserta a raiz: tira-se a
    referência impossível, que é exatamente o que a `ezdxf` faria se o handle
    simplesmente não existisse. O resultado é a seta padrão — perda cosmética
    numa referência que já estava quebrada.

    **Só descarta o que a `ezdxf` não sabe resolver, e a fronteira é ter `name`.**
    Handle `0` é "nenhum" e ela já o trata; handle não declarado, idem; handle que
    aponta para outro **registro de tabela** (um `STYLE`, um `LTYPE`) resolve sem
    reclamar — dá um nome de seta sem sentido, que ela depois não acha e troca
    pela padrão, sem quebrar nada. Só o alvo **sem nome** derruba a carga.

    Isso não é preciosismo: a 1ª versão exigia `BLOCK_RECORD` e teria mexido em
    **35 arquivos do corpus que já convertiam**, apagando referência que ninguém
    pediu para apagar. A regra estreita mexe em 1.
    """
    linhas, quebra = _linhas_e_quebra(bruto)
    reparadas, descartadas = _descartar_setas_de_cota_orfas_em_linhas(linhas)
    return (quebra.join(reparadas) if descartadas else bruto), descartadas


def _descartar_setas_de_cota_orfas_em_linhas(
        linhas: list[bytes]) -> tuple[list[bytes], int]:
    orfas = _achar_setas_orfas(linhas)
    if not orfas:
        return linhas, 0
    a_pular = set(orfas) | {i + 1 for i in orfas}
    return [l for i, l in enumerate(linhas) if i not in a_pular], len(orfas)


def _achar_setas_orfas(linhas: list[bytes]) -> list[int]:
    """Os índices das referências impossíveis — e nada é alocado sem elas.

    O mapa de handles é caro (um dicionário do tamanho do desenho), então ele só
    é construído depois de a 1ª varredura provar que **existe** `DIMSTYLE` com
    referência de bloco. Sem essa guarda, todo DXF pagaria o mapa para descobrir
    que não tinha nada a consertar — no maior arquivo do corpus isso é memória
    que o orçamento de conversão não tem para dar.
    """
    candidatos: list[int] = []
    em_dimstyle = False
    indice, total = 0, len(linhas)
    while indice < total - 1:
        if not _eh_codigo(linhas[indice]):
            indice += 1
            continue
        codigo, valor = linhas[indice].strip(), linhas[indice + 1].strip()
        if codigo == b"0":
            em_dimstyle = valor == b"DIMSTYLE"
        elif em_dimstyle and codigo in CODIGOS_DE_SETA_DE_COTA and valor not in (b"", b"0"):
            candidatos.append(indice)
        indice += 2

    if not candidatos:
        return []

    tipos = _tipos_por_handle(linhas)
    return [
        indice for indice in candidatos
        if (donos := tipos.get(linhas[indice + 1].strip().upper()))
        and not (donos & TIPOS_COM_NOME)
    ]


#: Os reparos do intermediário, na ordem em que rodam. Todos têm a mesma forma —
#: `bytes → (bytes, quantos)` — e a mesma disciplina: disparam contra uma
#: construção que **não existe em DXF são**, para serem inofensivos no arquivo
#: bom e desnecessários no dia em que o LibreDWG for corrigido.
REPAROS = (
    ("continuacao_orfa", _remendar_continuacoes_em_linhas),
    ("registro_vazio", _descartar_registros_vazios_em_linhas),
    ("seta_de_cota_orfa", _descartar_setas_de_cota_orfas_em_linhas),
)


#: Assinatura do DXF binário, nos 22 primeiros bytes do arquivo (`-b`).
ASSINATURA_BINARIA = b"AutoCAD Binary DXF\r\n\x1a\x00"


def eh_dxf_binario(bruto: bytes) -> bool:
    """O intermediário é o DXF binário do `-b`, e não texto com códigos de grupo."""
    return bruto[:len(ASSINATURA_BINARIA)] == ASSINATURA_BINARIA


def reparar_intermediario(bruto: bytes) -> tuple[bytes, dict[str, int]]:
    """Aplica os reparos do D43 e devolve o que cada um fez.

    **Não se aplica ao intermediário binário, e sair cedo aqui é metade da
    economia do `-b`** (10/08/2026). Os três reparos são cirurgia sobre pares
    *(código de grupo, valor)* em **linhas de texto**: no arquivo binário não há
    linha, e rodá-los seria, no melhor caso, ruído — no pior, corrupção. O
    ganho de recurso é grande porque a primeira coisa que esta função faz é
    partir o arquivo inteiro numa lista de linhas: num DXF de 84 MB isso são 2,6
    milhões de objetos Python, e a própria docstring abaixo registra um arquivo
    que passou a estourar o orçamento por causa dessa lista.

    Um só ponto de entrada porque a lista tende a crescer: cada defeito novo do
    escritor de DXF entra aqui como mais uma função pequena e testável, em vez de
    virar mais um `if` no meio da conversão.

    **Divide as linhas uma vez e junta uma vez — e não junta se ninguém mexeu.**
    A 1ª versão encadeava as três funções públicas, cada uma fazendo `split` e
    `join` do arquivo inteiro. Num DXF de 84 MB (o maior do corpus, 2,6 milhões
    de linhas) isso são três listas de centenas de MB para, quase sempre, não
    mudar um byte — e o efeito foi medido: um arquivo que convertia passou a
    estourar o orçamento de 1.536 MB e virou `recurso_excedido`. Reparo que custa
    conversão não é reparo; é o [D57](../../../docs/historico-correcoes.md) voltando pela porta dos fundos.
    """
    if eh_dxf_binario(bruto):
        return bruto, {}

    linhas, quebra = _linhas_e_quebra(bruto)
    contagem: dict[str, int] = {}
    for nome, reparo in REPAROS:
        linhas, quantos = reparo(linhas)
        if quantos:
            contagem[nome] = quantos
    if not contagem:
        return bruto, {}
    return quebra.join(linhas), contagem


# Código de versão no cabeçalho do DWG — os 6 primeiros bytes do arquivo, em
# ASCII. É a leitura mais barata que existe (não abre o arquivo de verdade) e
# responde a pergunta que decide tudo: o motor livre alcança esta versão?
VERSOES_DWG = {
    "AC1009": "R11/R12",
    "AC1012": "R13",
    "AC1014": "R14",
    "AC1015": "R2000",
    "AC1018": "R2004",
    "AC1021": "R2007",
    "AC1024": "R2010",
    "AC1027": "R2013",
    "AC1032": "R2018",
    "AC1037": "R2024",
}

#: Até onde o LibreDWG declara ler. Acima daqui a resposta certa é o upsell, e
#: **antes** de gastar o subprocesso: falhar rápido com a frase certa é melhor
#: que falhar devagar com a errada.
ALCANCE_LIVRE = {
    "AC1009", "AC1012", "AC1014", "AC1015", "AC1018",
    "AC1021", "AC1024", "AC1027", "AC1032",
}


def ler_versao_dwg(caminho: str) -> tuple[str, str]:
    """`(codigo, rotulo)` do cabeçalho — `("", "")` se não parecer um DWG."""
    try:
        with open(caminho, "rb") as arquivo:
            marca = arquivo.read(6).decode("ascii", errors="ignore")
    except OSError:
        return "", ""
    if not marca.startswith("AC"):
        return "", ""
    return marca, VERSOES_DWG.get(marca, "desconhecida")


class MotorDwg(Adaptador):
    codigo = "libredwg"
    #: **Duas saídas do mesmo arquivo, e independentes de propósito.** O
    #: `vetor_2d` é a prancha (redesenho nosso); a `miniatura` é o raster que o
    #: AutoCAD gravou ao salvar, extraído pelo `dwgbmp` — a única figura do
    #: acervo que não depende do nosso conversor (planta §4.4). Linhas separadas
    #: no banco significam que **uma sobrevive à falha da outra**, que é
    #: exatamente onde a miniatura mais vale: quando a conversão falhou, o cartão
    #: hoje fica sem imagem alguma embora o arquivo carregue uma.
    tipos = ("vetor_2d", "miniatura")
    #: A metade cara deste motor **é** o `ezdxf` (o `dwg2dxf` é subprocesso com
    #: teto próprio desde o PRA.1), então a escada é a mesma dele — declarada
    #: aqui em vez de herdada porque `MotorDwg` não estende `MotorDxf`: ele o
    #: usa. Um `economias` vazio faria o DWG, que é o formato onde o D57 foi
    #: medido, ser o único sem a segunda passada.
    #: **O último degrau é trocar de renderizador, não economizar dentro do
    #: nosso** (10/08/2026, §4.1). Os degraus herdados do `MotorDxf` reduzem o
    #: que o `ezdxf` desenha; quando nem isso cabe, o `ECONOMIA_SVG_DIRETO` sai
    #: do nosso caminho e usa o `dwg2SVG` do próprio LibreDWG — um processo só,
    #: sem intermediário e **sem expandir a repetição**: ele emite cada bloco uma
    #: vez (`<g id="symbol-…">`) e o referencia (`<use>`), que é exatamente o que
    #: torna o nosso caminho caro. Medido: onde o nosso pede ~1.520 MB e 17,2 s,
    #: ele pede 416 MB e 1,7 s; e três dos arquivos que hoje só sabem responder
    #: `recurso_excedido` convertem.
    #:
    #: **Fica em último de propósito.** A saída dele tem outra convenção — folha
    #: em coordenada de mundo, *paper space*, geometria por referência —, e a
    #: escala por folha e a âncora de marcação (§13.2) leem a nossa. Como degrau
    #: final, ele só entra onde hoje não há prancha nenhuma: prancha com outra
    #: convenção é melhor que erro, e nada do que já converte muda de aparência.
    economias = (*MotorDxf.economias, ECONOMIA_SVG_DIRETO)
    #: PRA.11 — retomável porque a metade cara é o `MotorDxf`, que é. O que a
    #: passada seguinte **repete** é o `dwg2dxf` (segundos de subprocesso) e a
    #: gravação da geometria; o que ela pula é a emissão das folhas já prontas.
    #: Só o caminho normal retoma: o `_svg_direto` (último degrau da escada) e a
    #: miniatura produzem um arquivo indivisível, e ali `prazo` não é oferecido.
    retomavel = True

    def _detectar_versao(self) -> str:
        caminho = executavel("dwg2dxf", ENV_BINARIO)
        if not caminho:
            return ""
        resultado = rodar([caminho, "--version"], timeout=15)
        # O `dwg2dxf` escreve a versão na primeira linha; alguns builds usam
        # stderr em vez de stdout. Ler as duas evita depender de qual — e o
        # binário existir já basta para o motor contar como disponível, então
        # nem uma versão ilegível o derruba.
        saida = (resultado.stdout or b"") + (resultado.stderr or b"")
        linhas = [l.strip() for l in saida.decode("utf-8", errors="ignore").splitlines() if l.strip()]
        return f"libredwg-{linhas[0]}" if linhas else "libredwg-desconhecida"

    def converter(self, caminho: str, *, formato: str, tipo: str, economia: str = "",
                  teto_snap: int | None = 0, retomada=None, prazo=None,
                  ceder=None) -> Saida:
        codigo, rotulo = ler_versao_dwg(caminho)
        if not codigo:
            raise ArquivoCorrompido(
                "O arquivo não começa com um cabeçalho DWG reconhecível."
            )
        if tipo == "miniatura":
            return self._preview_embutido(caminho, codigo=codigo, rotulo=rotulo)
        if codigo not in ALCANCE_LIVRE:
            # A frase da planta §4.1, literal: não é "falha na conversão".
            raise MotorInsuficiente(
                f"Este DWG está na versão {rotulo} ({codigo}), acima do que o motor "
                "livre alcança. Abrir este arquivo exige o motor de alta fidelidade.",
                versao_dwg=codigo,
            )

        if economia == ECONOMIA_SVG_DIRETO:
            return self._svg_direto(caminho, codigo=codigo)

        binario = executavel("dwg2dxf", ENV_BINARIO)
        if not binario:
            raise MotorIndisponivel(
                "O conversor de DWG (dwg2dxf, do LibreDWG) não está instalado nesta "
                "imagem. É instalação do servidor, não limite do seu plano."
            )

        dxf, reparos = self._para_dxf(binario, caminho)
        try:
            # `origem="dwg"` não é enfeite: sem ela, toda falha da segunda metade
            # é relatada como se o cliente tivesse subido um DXF quebrado. O DXF
            # aqui é intermediário **nosso**, e é o que o D42 mediu — ver
            # `MotorDxf._ilegivel`.
            #
            # `retomada`/`prazo` atravessam: quem tem folha é o `MotorDxf`, e é
            # ele que sabe parar entre uma e outra. O `dwg2dxf` acima já rodou
            # inteiro — é o custo que toda passada repete, e está declarado no
            # `retomavel` desta classe.
            saida = MotorDxf(origem="dwg").converter(
                dxf, formato="dxf", tipo=tipo, economia=economia, teto_snap=teto_snap,
                retomada=retomada, prazo=prazo, ceder=ceder,
            )
        finally:
            self._apagar(dxf)

        # A procedência do DWG entra em **cada** desenho, não só no primeiro: a
        # parte é o que vira linha no banco, e uma que não soubesse de que versão
        # de DWG veio ficaria sem resposta na tela de conversões — além de sumir
        # do `medir_cobertura_dwg`, que agrega por versão.
        # **Os reparos entram na memória de conversão** (D43). Sem isto, o número
        # de arquivos que só abrem porque foram remendados é invisível: some no
        # sucesso, e ninguém sabe o tamanho da dívida que o LibreDWG nos deixa —
        # nem quando ela some, no dia em que ele for corrigido.
        carimbo = {"versao_dwg": codigo, "versao_dwg_rotulo": rotulo}
        if reparos:
            carimbo["reparos"] = reparos
        partes = tuple(
            replace(parte, detalhe={**parte.detalhe, **carimbo})
            for parte in saida.partes
        )
        return Saida(
            conteudo=saida.conteudo,
            extensao=saida.extensao,
            content_type=saida.content_type,
            detalhe={**(saida.detalhe or {}), **carimbo},
            partes=partes,
            # O marcador é do `MotorDxf` e atravessa intacto: quem decide o que
            # fazer com ele é o pipeline, e reconstruí-lo aqui só criaria uma
            # segunda contagem de folhas para divergir da primeira.
            retomada=saida.retomada,
        )

    # -- o preview que o CAD gravou (§4.4, D49) ------------------------------
    def _preview_embutido(self, caminho: str, *, codigo: str, rotulo: str) -> Saida:
        """Extrai o *thumbnail* embutido no DWG e o entrega como miniatura.

        **Não é conversão: é a figura que o AutoCAD fez.** Todo DWG pode carregar
        um raster gravado no salvamento (`RASTERPREVIEW`), e o `dwgbmp` — da
        mesma tarball que o build stage já compila — o extrai sem decodificar o
        desenho. O limite é o que ele é: raster de baixa resolução, bom para
        reconhecer a prancha e **nunca** para zoom ou medição, e é por isso que
        alimenta só o cartão do acervo.

        **A ausência não é falha, e o código de saída não a denuncia.** Medido
        no binário 0.13.3 e reconferido no 0.14.8566: sem preview no arquivo o
        `dwgbmp` imprime *"No
        thumbnail image"*, **sai com 0** e não escreve arquivo nenhum — a mesma
        armadilha do `-y` que o D34 pagou caro. Quem responde a pergunta é o
        arquivo de destino existir e ter tamanho.

        **Toda falha daqui vira `SemPreviewEmbutido`**, inclusive a do arquivo
        corrompido e a da versão fora do alcance livre. É deliberado: a linha do
        `vetor_2d` já carrega a mensagem comercial e o diagnóstico do arquivo, e
        uma segunda linha vermelha dizendo o mesmo sobre a imagem do cartão só
        duplicaria a má notícia. O motivo real viaja na memória de conversão.
        """
        binario = executavel("dwgbmp", ENV_BINARIO_BMP)
        if not binario:
            # Distinto de "não tem preview": aqui a imagem pode existir e nós é
            # que não temos como lê-la. É instalação do servidor — a mesma
            # separação que o `dwg2dxf` faz logo acima.
            raise MotorIndisponivel(
                "O extrator de preview de DWG (dwgbmp, do LibreDWG) não está "
                "instalado nesta imagem. É instalação do servidor, não limite do "
                "seu plano."
            )

        descritor, destino = tempfile.mkstemp(suffix=".preview", prefix="prancheta-")
        os.close(descritor)
        try:
            resultado = rodar(
                [binario, caminho, destino], timeout=TIMEOUT_PREVIEW_SEGUNDOS,
            )
            saida = ((resultado.stdout or b"") + (resultado.stderr or b"")).decode(
                "utf-8", errors="ignore"
            ).strip()
            if not os.path.exists(destino) or not os.path.getsize(destino):
                raise SemPreviewEmbutido(
                    "Este DWG não traz a miniatura que o CAD grava ao salvar — o "
                    "acervo mostra o cartão sem imagem, e a prancha convertida "
                    "continua disponível.",
                    versao_dwg=codigo, motivo_real=saida[:300],
                )
            return self._miniatura_do_raster(destino, codigo=codigo, rotulo=rotulo)
        finally:
            self._apagar(destino)

    def _miniatura_do_raster(self, destino: str, *, codigo: str, rotulo: str) -> Saida:
        """Lê o raster que o `dwgbmp` escreveu e o encolhe para o cartão.

        O `dwgbmp` entrega **o que estava lá dentro** — BMP, PNG ou WMF —, e não
        converte entre eles: o formato é escolha de quem salvou o arquivo. Pillow
        lê os dois primeiros; **WMF é vetorial do Windows e não abre sem um
        renderizador externo**, então esse caso é ausência declarada, e não um
        traceback. A assinatura vai para a memória de conversão para a estatística
        existir antes de alguém decidir se vale um renderizador de WMF.
        """
        with open(destino, "rb") as arquivo:
            assinatura = arquivo.read(4)
        if assinatura.startswith(b"BM"):
            formato = "bmp"
        elif assinatura.startswith(b"\x89PNG"):
            formato = "png"
        else:
            formato = "desconhecido"

        try:
            from PIL import Image

            imagem = Image.open(destino)
            imagem.load()
        except NAO_EMBRULHAR:
            # **O mais invisível dos cinco.** `SemPreviewEmbutido` é da família
            # "ninguém age" (D45/D49): existe para a ausência de miniatura sair
            # da fila do que nós consertamos. O teto do D57 caindo aqui saía da
            # fila também — um limite nosso agindo sem aparecer em lugar nenhum,
            # e o cliente lendo que o formato do preview dele é exótico.
            raise
        except Exception as exc:
            raise SemPreviewEmbutido(
                "Este DWG traz uma miniatura embutida num formato que não sabemos "
                "abrir; a prancha convertida continua disponível.",
                versao_dwg=codigo, preview_formato=formato, motivo_real=str(exc)[:200],
            ) from exc

        return miniatura(
            imagem,
            procedencia="preview_embutido",
            preview_formato=formato,
            versao_dwg=codigo,
            versao_dwg_rotulo=rotulo,
        )

    # -- subprocesso ---------------------------------------------------------
    def _para_dxf(self, binario: str, caminho: str) -> tuple[str, dict[str, int]]:
        """Roda o `dwg2dxf` e devolve o DXF gerado e o que foi preciso reparar.

        `-o` explícito com arquivo temporário nosso: sem ele o `dwg2dxf` escreve
        ao lado da entrada, que é o diretório do storage — poluí-lo com DXF
        intermediário faria a quota de acervo contar arquivo que o cliente nunca
        subiu.

        **`-y` é obrigatório junto do `mkstemp`, e a ausência dele custava caro.**
        O `mkstemp` **cria** o arquivo (é daí que vem a garantia de nome exclusivo);
        o `dwg2dxf` se recusa a sobrescrever arquivo existente e aborta com
        `ERROR: File not overwritten: …, use -y`, saindo com código 1 e destino
        vazio. Pelo teste logo abaixo isso é indistinguível de "o motor livre não
        deu conta", então **todo** DWG virava `MotorInsuficiente` — a plataforma
        mandava o cliente comprar o plano premium para resolver um bug nosso, que
        é exatamente a confusão que a planta §4.2 separa em dois motivos de erro.
        A alternativa (apagar o temporário antes de chamar) devolveria a corrida
        de nome que o `mkstemp` existe para evitar.

        **O DXF sai remendado (D43).** O `dwg2dxf` termina com código 0 e arquivo
        cheio mesmo quando escreveu texto longo sem o código de continuação, e
        13,8% do corpus morria aí. `remendar_continuacoes` conserta isso **antes**
        de o `MotorDxf` ver o arquivo — de modo que a prancha volta pelo caminho
        normal, com folha, escala e âncora, em vez de por um modo de resgate.
        """
        descritor, destino = tempfile.mkstemp(suffix=".dxf", prefix="prancheta-")
        os.close(descritor)

        # **Sem `-b`, e isso é medido** (10/08/2026). O DXF binário do `dwg2dxf`
        # tem metade dos bytes e converte em metade do tempo — e **quebra o
        # desenho**: o escritor binário do LibreDWG trunca o nome das entradas de
        # tabela no primeiro caractere, e o `ezdxf` morre em
        # `DXFTableEntryError: S` ao procurar o estilo de texto "Standard". Os 3
        # arquivos do corpus dos grandes que convertem em texto falharam em
        # binário, com 2 modos distintos. É a metade fraca do LibreDWG de novo —
        # a mesma que o [D43](../../../docs/historico-correcoes.md) mapeou. Ver a
        # planta §4.1 antes de tentar de novo.
        resultado = rodar(
            [binario, "-y", "-o", destino, caminho],
            timeout=TIMEOUT_SEGUNDOS,
            # Teto PRÓPRIO, e não o do pai herdado (D78, opção 1). O `dwg2dxf`
            # tem perfil de alocação diferente do `ezdxf`, e cair no limite dele
            # é falha atribuível — cair no do pai era morte por sinal, que a
            # camada de cima não sabia ler.
            memoria_mb=teto_do_subprocesso(MEMORIA_SUBPROCESSO_MB),
        )
        erro = (resultado.stderr or b"").decode("utf-8", errors="ignore").strip()

        if resultado.returncode != 0 or not os.path.getsize(destino):
            self._apagar(destino)
            # **Antes de chamar de insuficiência de motor, perguntar se o teto é
            # nosso** (D78). O `dwg2dxf` morto por sinal sob orçamento armado é a
            # nossa própria memória acabando dentro dele — três DWGs do acervo
            # provaram isso em 09/08/2026, convertendo limpos quando soltos e
            # morrendo com SIGSEGV sob `RLIMIT_AS`. Sem esta pergunta, o teto que
            # a PRA.1d criou para PROTEGER a plataforma virava argumento de venda
            # contra o cliente.
            if morreu_por_falta_de_memoria(
                resultado.returncode, teto_do_filho_mb=teto_do_subprocesso(MEMORIA_SUBPROCESSO_MB),
            ):
                raise RecursoExcedido(
                    "A conversão passou do limite de memória e foi interrompida. "
                    "O arquivo continua disponível para download.",
                    teto="memoria_do_subprocesso",
                    sinal=-resultado.returncode,
                    # **Pular direto para a troca de renderizador.** Quem estourou
                    # foi o `dwg2dxf`, e os degraus intermediários economizam no
                    # `ezdxf` — estágio que este arquivo nem alcança; passar por
                    # eles repetiria a decodificação inteira (9 s a 110 s) para
                    # falhar igual, que era o `degradavel=False` do D78. O degrau
                    # do `dwg2SVG` é o único que não usa o `dwg2dxf`, então é o
                    # único que pode dar outro resultado.
                    pular_para=ECONOMIA_SVG_DIRETO,
                    stderr=_stderr_util(erro),
                )
            # Chegou aqui com versão dentro do alcance declarado, sem teto nosso
            # pela frente, e ainda assim falhou: é a fronteira real do motor
            # livre, que a planta §4.1 diz ser medida e não suposta. Para o
            # cliente a saída continua sendo o motor melhor — mas o log guarda o
            # `stderr`, que é o insumo do `medir_cobertura_dwg`.
            raise MotorInsuficiente(
                "O motor livre não conseguiu abrir este DWG. Ele exige o motor de "
                "alta fidelidade.",
                stderr=_stderr_util(erro),
            )

        self._conferir_decodificacao(destino, erro)
        return destino, self._remendar(destino)

    #: Linhas de erro do decodificador. Servem para **nomear a causa** na
    #: mensagem — nunca para dar o veredito (ver `_conferir_decodificacao`).
    MARCA_DE_ERRO = "ERROR:"

    def _conferir_decodificacao(self, destino: str, stderr: str) -> None:
        """Recusa o intermediário que o `dwg2dxf` produziu **sem ter conseguido
        ler o DWG** — mesmo tendo saído com código 0 (**D43**, 2ª causa).

        **O defeito, medido em 09/08/2026 sobre 15 DWGs do corpus.** Em ~13 deles
        o `dwg2dxf` falha na decodificação, **grita no stderr** e retorna **0**::

            ERROR: bit_read_BD: unexpected 2-bit code: '11'
            ERROR: Some section size or address out of bounds
            ERROR: BLOCK_HEADER *Model_Space first_owned_entity missing

        O resultado é um DXF truncado — em `aerhetg.DWG`, 59 KB vindos de um DWG
        de 1,9 MB, terminando em `ENDSEC` **sem a tag `EOF`**. Como o teste de
        cima só olhava `returncode` e tamanho do arquivo, esse intermediário
        seguia adiante e morria lá na frente, no `ezdxf`, com
        ``DXFTypeError: name has to be a string, got NoneType`` — um registro de
        tabela sem `name`, porque a tabela nunca foi escrita inteira.

        **Por que isto é conserto mesmo sem recuperar nenhum arquivo.** A frase
        que o cliente e o suporte liam falava de `name` e `NoneType`, e mandava
        investigar o leitor de DXF quando o defeito estava no decodificador de
        DWG, dois passos antes. O `stderr` que nomeia a causa já estava na mão —
        era capturado e usado **só** quando o código era diferente de zero. A
        ferramenta avisava e nós não ouvíamos.

        **O veredito é a tag `EOF`, e só ela — o `stderr` nomeia, não julga.** A
        primeira versão deste método também reprovava quando havia linha `ERROR:`
        no stderr, e a medição derrubou a regra antes de ela sair daqui: numa
        amostra de 30 DWGs que **convertem hoje**, **25 emitem `ERROR:`**. O
        LibreDWG grita por problema recuperável o tempo todo, então aquele
        critério teria reprovado 83% das conversões que funcionam — estrago muitas
        vezes maior que os 12 arquivos que ele consertaria. A ausência da tag
        `EOF`, ao contrário, é **definicional**: DXF sem ela está incompleto. E a
        medida confirma — **0 falsos positivos** em 35 arquivos que convertem.

        `Warning:` não entra nem para nomear: ele aparece em praticamente toda
        prancha moderna (classe instável) e afogaria a causa real.

        **Continua sendo `falha_motor`, e isso é deliberado.** É tentador chamar
        de `MotorInsuficiente` — "o LibreDWG não deu conta, compre o premium" —,
        mas ninguém mediu se o motor de alta fidelidade abre estes arquivos. Sem
        essa prova, o upsell seria o [D34] ao contrário: vender solução que talvez
        não resolva. Enquanto a medida não existir, a linha fica na fila do que
        **nós** consertamos.

        **A frase mudou em 09/08/2026, porque a antiga estava errada.** Ela dizia
        *"reexportar do CAD não resolve"* — e resolve. O dono abriu o
        `Planta Projeto Impressão Final` (1.719 erros de decodificador, o 2º pior
        do corpus) no AutoCAD, que o recuperou na abertura (*"15 erros corrigidos,
        1 objeto apagado"*), salvou, e o arquivo salvo **converteu**: 16.391
        traços, modelspace, sem recuperação nossa. O ida-e-volta pelo CAD reescreve
        o DWG numa forma que o LibreDWG lê.

        Por isso a mensagem passou a oferecer a ação em vez de negá-la — dizendo
        *"costuma"*, e não *"resolve"*: a prova é de **um** arquivo, e a lição das
        6 amostras homogêneas do próprio D43 é que uma amostra pequena e parecida
        superestima. O defeito continua nosso; o que o cliente ganha é uma saída
        enquanto ele não é consertado.
        """
        with open(destino, "rb") as arquivo:
            if arquivo.seek(0, os.SEEK_END) > 512:
                arquivo.seek(-512, os.SEEK_END)
            else:
                arquivo.seek(0)
            rabo = arquivo.read()

        # A tag de fim, nas últimas linhas. É o ÚNICO critério de recusa.
        if b"EOF" in rabo.split(b"ENDSEC")[-1]:
            return

        linhas = [
            linha.strip()
            for linha in stderr.splitlines()
            if linha.strip().startswith("ERROR:")
        ]
        causa = linhas[0][len("ERROR:"):].strip() if linhas else "arquivo truncado"
        self._apagar(destino)
        raise FalhaDoIntermediario(
            "O seu DWG foi lido pela metade: o conversor não conseguiu "
            f"decodificá-lo por inteiro ({causa}), e o desenho que sairia daí "
            "estaria incompleto. O arquivo com problema é o nosso, não o seu. "
            "Enquanto consertamos: abrir o desenho no AutoCAD e salvá-lo de novo "
            "costuma gerar um DWG que conseguimos ler.",
            stderr=stderr[:500],
            sem_eof=True,
            erros_do_decodificador=len(linhas),
        )

    def _svg_direto(self, caminho: str, *, codigo: str) -> Saida:
        """Último degrau: o `dwg2SVG` desenha, no lugar do nosso caminho.

        **Por que existe** (§4.1, 10/08/2026): o caminho normal materializa cada
        inserção de bloco como geometria própria, e é isso — não o tamanho do
        arquivo — que faz a memória explodir. Um desenho com 858 inserções de 250
        blocos vira 47.610 traços no nosso SVG; o `dwg2SVG` emite os 250 uma vez
        e referencia. Medido: 416 MB contra ~1.520 MB, 1,7 s contra 17,2 s.

        **Só é alcançado depois de o orçamento estourar nos degraus anteriores**,
        e a diferença que isso faz é toda: aqui a alternativa não é uma prancha
        melhor, é `recurso_excedido` — nenhuma prancha. Uma folha com a convenção
        do LibreDWG (coordenada de mundo, *paper space*, geometria por
        referência) é melhor que erro, e quem já converte pelo caminho normal
        nunca chega neste degrau, então **nada muda de aparência no que funciona**.

        **O que o degrau declara**, para não virar melhora silenciosa: `detalhe`
        carrega `renderizador="dwg2SVG"` e `convencao="mundo"`, que é o que a
        tela precisa para não aplicar a normalização de folha por cima.

        **O pós-processamento é obrigatório, e ficou desligado até 16/08/2026.**
        O `svg_do_motor` existe para consertar três defeitos que a saída crua do
        `dwg2SVG` tem — texto em código de escape, símbolo com origem deslocada e
        desenhos distantes na mesma folha — e **nada o chamava**: este método
        devolvia `svg` cru. Medido sobre 18 DWGs do acervo (16/08/2026), a
        fração de geometria que cai dentro do `viewBox` que o próprio arquivo
        declara, antes e depois do conserto de origem::

            família AutoCAD Electrical (5 arquivos)   50–61 %  →  99–100 %
            arquivos sem `<use>` nenhum (7)           inalterada (não há símbolo)
            arquivos já corretos crus (2)             inalterada

        Ou seja: onde há bloco por referência — que é justamente por que este
        degrau existe —, metade do desenho estava fora da folha. Onde não há, a
        correção é inerte por construção, porque a decisão é **por símbolo**
        (`_caixa_do_simbolo`) e não em bloco.
        """
        binario = executavel("dwg2SVG", ENV_BINARIO_SVG)
        if not binario:
            raise MotorIndisponivel(
                "O desenhista de DWG (dwg2SVG, do LibreDWG) não está instalado "
                "nesta imagem. É instalação do servidor, não limite do seu plano."
            )

        resultado = rodar(
            [binario, caminho],
            timeout=TIMEOUT_SEGUNDOS,
            memoria_mb=teto_do_subprocesso(MEMORIA_SUBPROCESSO_MB),
        )
        erro = (resultado.stderr or b"").decode("utf-8", errors="ignore").strip()
        svg = resultado.stdout or b""

        if resultado.returncode != 0 or not svg:
            # A mesma pergunta do `_para_dxf`: o teto é nosso antes de ser do
            # motor (D78).
            if morreu_por_falta_de_memoria(
                resultado.returncode, teto_do_filho_mb=teto_do_subprocesso(MEMORIA_SUBPROCESSO_MB),
            ):
                raise RecursoExcedido(
                    "A conversão passou do limite de memória e foi interrompida. "
                    "O arquivo continua disponível para download.",
                    teto="memoria_do_subprocesso", degradavel=False,
                    stderr=_stderr_util(erro),
                )
            raise FalhaMotor(
                "O desenhista do motor livre não conseguiu desenhar este DWG.",
                stderr=_stderr_util(erro),
            )

        # **"Saiu byte" não é desenho** — a lição do D52/D43 aplicada a este
        # degrau: um SVG só com carimbo e moldura passaria por prancha.
        if not any(marca in svg for marca in ELEMENTOS_DE_TRACO):
            raise DesenhoVazio(
                "O arquivo não tem desenho que este motor saiba traçar."
            )

        # **E "saiu traço" também não é desenho.** A pergunta acima só sabe dizer
        # que existe elemento; a de baixo diz se ele caiu em algum lugar. Ordem
        # importa: um SVG destruído tem traço de sobra, então checar a geometria
        # antes faria toda folha vazia ser relatada como destruída.
        if estrago := folha_destruida(svg):
            # `FalhaMotor`, e não `DesenhoVazio`: pela taxonomia da fila do
            # cockpit (planta §11), desenho vazio é a coluna do "ninguém resolve"
            # — o arquivo não tinha nada dentro. Aqui o arquivo tem, e quem tem
            # de agir somos **nós**. Contá-lo como vazio o subtrairia justamente
            # da conta que mede o nosso trabalho.
            raise FalhaMotor(
                f"O desenhista do motor livre devolveu uma folha inválida: {estrago}.",
                stderr=_stderr_util(erro),
            )

        # Os três consertos do `svg_do_motor`, na ordem em que ele os pede: o
        # texto primeiro (substituição byte a byte, uma vez sobre o documento
        # inteiro) e a separação depois, que é a que lê coordenada.
        svg = svg_do_motor.corrigir_texto(svg)
        detalhe = {
            "versao_dwg": codigo,
            "renderizador": "dwg2SVG",
            # A tela lê isto para NÃO aplicar a normalização de folha: as
            # coordenadas aqui são as do desenho, não as nossas.
            "convencao": "mundo",
        }
        try:
            separadas, truncados = svg_do_motor.folhas(svg)
        except Exception:  # noqa: BLE001
            # **A separação não pode derrubar o degrau.** Aqui a alternativa não
            # é uma prancha melhor, é `recurso_excedido` — nenhuma prancha. Um
            # documento com forma que o leitor não previu vale mais inteiro e sem
            # separar do que como erro, e `separacao_falhou` no detalhe é o que
            # impede isso de virar melhora silenciosa.
            detalhe["separacao_falhou"] = True
            separadas, truncados = [], 0
        if truncados:
            detalhe["folhas_truncadas"] = truncados

        partes = tuple(
            Parte(
                conteudo=folha.conteudo,
                ordem=indice,
                caixa={
                    "xmin": round(folha.caixa[0], 6), "ymin": round(folha.caixa[1], 6),
                    "xmax": round(folha.caixa[2], 6), "ymax": round(folha.caixa[3], 6),
                },
                tracos=folha.tracos,
                # `mundo` fica vazio de propósito: a ponte de volta à coordenada
                # do CAD é **medida na emissão** pelo `ezdxf` (`_mundo_da_folha`),
                # e aqui não há emissão nossa para medir. Vazia, a tela mostra as
                # réguas dela e não finge coordenada de desenho — que é a regra do
                # D90, e o motivo de não deduzi-la do `viewBox` do LibreDWG.
                detalhe={**detalhe, "ordem": indice},
            )
            for indice, folha in enumerate(separadas, start=1)
        )

        return Saida(
            # A primeira parte é a maior (o `_agrupar` ordena), então quem ainda
            # não conhece `partes` continua abrindo o maior desenho — o contrato
            # que o `Saida.partes` declara. Sem separação, o documento inteiro.
            conteudo=partes[0].conteudo if partes else svg,
            extensao="svg",
            content_type="image/svg+xml",
            detalhe=detalhe,
            partes=partes,
        )

    def _remendar(self, destino: str) -> dict[str, int]:
        """Aplica os reparos do D43 no lugar, se houver o que reparar.

        Reescreve o arquivo só quando **algum** reparo achou o que consertar: em
        DXF são o conteúdo não muda um byte, e a passagem custa uma leitura. A
        contagem por reparo volta para quem quiser instrumentá-la (é o que o
        `medir_cobertura_dwg` agrega).
        """
        # **Espia a assinatura antes de carregar o arquivo inteiro.** Com o `-b`
        # o intermediário é binário e não há reparo a fazer; ler 338 MB para
        # concluir isso seria pagar o pico de memória que o `-b` veio eliminar.
        with open(destino, "rb") as arquivo:
            if eh_dxf_binario(arquivo.read(len(ASSINATURA_BINARIA))):
                return {}
            arquivo.seek(0)
            bruto = arquivo.read()
        conteudo, contagem = reparar_intermediario(bruto)
        if contagem:
            with open(destino, "wb") as arquivo:
                arquivo.write(conteudo)
        return contagem

    def _apagar(self, caminho: str) -> None:
        try:
            os.unlink(caminho)
        except OSError:  # pragma: no cover - temp já removido
            pass
