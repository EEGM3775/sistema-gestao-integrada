# backend/funcoesimpexp/limites.py
"""Os limites de uma operação de import/export — todos vindos do plano.

**A regra que este arquivo materializa** (decisão do dono, 07/08/2026): nenhum
teto do motor é constante de engenharia. Tamanho de arquivo, formato aceito,
orçamento de memória e de relógio saem de `payment/planos.py`, por plano, onde o
dono os vê e os edita. Antes disto o teto de tamanho vinha de
`ConfiguracaoArquivos` do tenant (invisível ao dono, e uma lista de MIMEs que não
aceitava CSV) e memória/relógio não existiam.

**O método é o do assinador gov.br**, e ele tem três partes que aqui viram três
funções:

1. **a capacidade é atributo do nível** — conta bronze não assina, prata e ouro
   assinam. Aqui, `limites_do_plano`: o `free` não lê PDF de tabela;
2. **allowlist publicada, nunca denylist** — o gov.br lista as seis extensões que
   aceita. Aqui, o registry de formatos + `detectar_formato`, e o que não casa com
   nenhuma assinatura conhecida é recusado, não "tentado";
3. **o teto é dito antes, não descoberto no erro** — `descrever()` alimenta a
   tela, e o 402 traz o número junto.

**Por que a detecção não confia no nome do arquivo.** O despacho era por sufixo
do nome que o cliente mandou, e sufixo é dado do atacante: `payload.exe`
renomeado para `.xlsx` entrava pela porta, era **gravado em disco** no caminho de
job e só falhava ao ser parseado. Aqui a assinatura de bytes decide; o sufixo só
desempata entre formatos que compartilham assinatura (todo XLSX é um ZIP).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from payment.planos import (
    IMPEXP_TETO_INFRA_ARQUIVO_MB,
    IMPEXP_TETO_INFRA_MB,
    IMPEXP_TETO_INFRA_MEMORIA_MB,
    IMPEXP_TETO_INFRA_SEGUNDOS,
    PLANOS,
)

# Declaração torta de formato é o mesmo erro que declaração torta de recurso —
# programação, não uso —, então reusa a exceção que já falha no boot em vez de
# criar uma segunda com o mesmo papel. `registro` não importa este módulo, então
# não há ciclo.
from .registro import RecursoInvalido

logger = logging.getLogger(__name__)


class FormatoDesconhecido(Exception):
    """Os bytes não são de nenhum formato que ESTE destino receba. → 400.

    Cobre dois casos que o cliente vive igual (o arquivo não entra, e não há o
    que comprar) e que o chamador às vezes precisa distinguir:

    - a plataforma **não reconheceu** os bytes — `formato` fica `None`;
    - reconheceu, e **este recurso não recebe** aquele formato — `formato` traz o
      código.

    O segundo caso é o que permite ao módulo dizer mais do que a porta genérica
    sabe. A porta conhece a allowlist; ela não sabe que um `.bcfzip` na Prancheta
    não é arquivo errado, é **arquivo na porta errada** — tem a sua, a de
    marcações. Sem o código aqui, a única mensagem possível seria listar
    formatos aceitos, que manda o cliente procurar o que ele já tem.
    """

    def __init__(self, mensagem: str, *, formato: str | None = None):
        super().__init__(mensagem)
        self.formato = formato


class FormatoNaoContratado(Exception):
    """Formato existe e o plano não o inclui. → 402, com o nome do formato."""

    def __init__(self, mensagem: str, *, formato: str, disponiveis: list[str]):
        super().__init__(mensagem)
        self.formato = formato
        self.disponiveis = disponiveis


class ArquivoGrandeDemais(Exception):
    """Passou do teto de tamanho do plano. → 402, com o teto e o tamanho."""

    def __init__(self, mensagem: str, *, limite_mb: int, tamanho_mb: float):
        super().__init__(mensagem)
        self.limite_mb = limite_mb
        self.tamanho_mb = tamanho_mb


# ---------------------------------------------------------------------------
# 1. Registry de formatos de ENTRADA — a allowlist publicada
# ---------------------------------------------------------------------------


#: As duas naturezas de formato de entrada (IE.3).
#:
#: `TABELA` — o motor **abre** o arquivo e lê linhas de dentro dele. É o que o
#: IE.0 sempre fez: a unidade de decisão é a linha, e o binário é lido e
#: descartado.
#: `ARQUIVO` — o arquivo **é** a unidade de decisão, e o motor nunca o abre. É a
#: prancha, a foto do diário, o ASO do funcionário. O que se confere é o
#: arquivo (nome, caminho, tamanho, hash) e o que se grava é ele próprio.
#:
#: A distinção mora aqui, e não no recurso, porque é o que decide se
#: `detectar_formato` entrega o arquivo a um parser (`openpyxl`, `pdfplumber`)
#: ou apenas o reconhece e o deixa passar. Confundir as duas é entregar um DWG
#: ao leitor de planilha.
NATUREZA_TABELA = "tabela"
NATUREZA_ARQUIVO = "arquivo"


@dataclass(frozen=True)
class FormatoEntrada:
    codigo: str
    rotulo: str
    extensoes: tuple[str, ...]
    #: Assinatura de bytes do formato. Vazia = formato sem assinatura binária,
    #: e aí a prova é `marcadores_texto` ou, na falta dele, a ausência de sinal
    #: binário (tem de decodificar e não ter byte nulo).
    assinaturas: tuple[bytes, ...] = ()
    natureza: str = NATUREZA_TABELA
    #: Trecho que precisa aparecer perto do começo de um formato de TEXTO.
    #: Existe porque metade dos formatos de projeto é texto estruturado — DXF
    #: começa com `SECTION`, IFC com `ISO-10303-21` — e para eles a prova certa
    #: não é uma assinatura binária (não têm) nem "parece texto" (fraco demais
    #: para uma porta que aceita 300 MB), e sim o marcador do próprio formato.
    marcadores_texto: tuple[bytes, ...] = ()
    #: Teto próprio deste formato, em MB. 0 = vale o teto do plano.
    #:
    #: Existe porque um número só não serve às duas naturezas: `impexp_max_mb`
    #: vai de 5 a 50 MB (planilha), e um IFC de projeto executivo passa de 200.
    #: O teto efetivo é sempre o **menor** entre este e o do plano quando os dois
    #: falam da mesma coisa — ver `Limites.max_mb_de`.
    max_mb: int = 0
    #: Módulo que declarou este formato. Vazio = é do motor (planilha/PDF/CSV).
    #: Serve ao diagnóstico: com seis módulos registrando, "quem trouxe o .dwg
    #: para a allowlist" tem de ter resposta sem `git blame`.
    origem: str = ""


#: Os formatos que o **motor** conhece por si — os tabulares do IE.0.
#: Formato de natureza `ARQUIVO` não entra aqui: quem o declara é o módulo dono,
#: por `registrar_formato`, porque é ele que sabe o que faz com aquele binário.
_FORMATOS_DO_MOTOR: tuple[FormatoEntrada, ...] = (
    # ZIP é a assinatura do XLSX inteiro (OOXML é um zip). Só isso não basta —
    # um .docx e um .jar têm a mesma —, por isso a extensão desempata: a
    # assinatura prova que NÃO é executável renomeado, e o sufixo diz qual dos
    # formatos-zip o cliente afirma ter mandado.
    FormatoEntrada("xlsx", "Planilha Excel", (".xlsx",), (b"PK\x03\x04",)),
    FormatoEntrada("pdf", "PDF com tabela", (".pdf",), (b"%PDF-",)),
    # Sem assinatura por natureza. A prova aqui é a ausência de sinal binário:
    # texto de verdade decodifica e não tem byte nulo no meio.
    FormatoEntrada("csv", "CSV / texto delimitado", (".csv", ".txt")),
)

#: Registry vivo. Começa com os do motor e cresce com o que os módulos declaram.
_REGISTRO_FORMATOS: dict[str, FormatoEntrada] = {f.codigo: f for f in _FORMATOS_DO_MOTOR}


def registrar_formato(formato: FormatoEntrada) -> FormatoEntrada:
    """Acrescenta um formato de entrada à allowlist da plataforma (IE.3).

    **É por aqui que a porta única cresce.** Antes do IE.3 a allowlist era uma
    tupla fechada com três formatos tabulares, e todo módulo que precisava
    receber outra coisa — a Prancheta com CAD/BIM, o diário com foto, o RH com
    ASO — abria uma porta própria. O [D75](../../docs/historico-correcoes.md) mostrou o
    preço: a porta da Prancheta decidia o formato pelo **nome do arquivo**, e o
    D65 já tinha registrado que sufixo é dado do atacante.

    Registrar aqui em vez de validar lá é o que mantém **uma** allowlist, **uma**
    detecção por bytes e **um** lugar onde o antivírus entra quando entrar
    ([D74](../../docs/modulos/funcoesimpexp.md)).

    Idempotente para o mesmo código com a mesma declaração (o `apps.py` de um
    módulo pode ser importado duas vezes em teste); colisão com declaração
    diferente é erro de programação e falha no boot, como no registry de recursos.
    """
    anterior = _REGISTRO_FORMATOS.get(formato.codigo)
    if anterior is not None and anterior != formato:
        raise RecursoInvalido(
            f"Formato de entrada '{formato.codigo}' já registrado por "
            f"'{anterior.origem or 'motor'}' com outra declaração. O código é a "
            "chave da allowlist — duas declarações fariam a detecção depender da "
            "ordem de import."
        )
    if not formato.extensoes:
        raise RecursoInvalido(f"Formato '{formato.codigo}': falta `extensoes`.")
    if formato.natureza not in (NATUREZA_TABELA, NATUREZA_ARQUIVO):
        raise RecursoInvalido(
            f"Formato '{formato.codigo}': natureza {formato.natureza!r} "
            f"desconhecida (use {NATUREZA_TABELA!r} ou {NATUREZA_ARQUIVO!r})."
        )
    if formato.natureza == NATUREZA_TABELA and formato.codigo not in _REGISTRO_FORMATOS:
        raise RecursoInvalido(
            f"Formato '{formato.codigo}': natureza {NATUREZA_TABELA!r} significa que o "
            "MOTOR abre o arquivo e lê linhas de dentro — e ele só sabe fazer isso "
            "com os formatos que implementa em `formatos/leitura.py`. Módulo declara "
            f"formato de natureza {NATUREZA_ARQUIVO!r}."
        )
    _REGISTRO_FORMATOS[formato.codigo] = formato
    return formato


def formatos_registrados() -> tuple[FormatoEntrada, ...]:
    """A allowlist inteira, em ordem estável."""
    return tuple(_REGISTRO_FORMATOS[c] for c in sorted(_REGISTRO_FORMATOS))


class _VistaPorCodigo(dict):
    """`FORMATOS_POR_CODIGO` continua funcionando, agora sobre o registry vivo.

    Existe para não quebrar quem já lê este nome (o motor, os testes do IE.0):
    era um dict montado no import, e um dict montado no import ficaria cego para
    todo formato que um módulo registrar depois.
    """

    def __getitem__(self, chave):
        return _REGISTRO_FORMATOS[chave]

    def __contains__(self, chave):
        return chave in _REGISTRO_FORMATOS

    def get(self, chave, padrao=None):
        return _REGISTRO_FORMATOS.get(chave, padrao)

    def __iter__(self):
        return iter(_REGISTRO_FORMATOS)

    def keys(self):
        return _REGISTRO_FORMATOS.keys()

    def values(self):
        return _REGISTRO_FORMATOS.values()

    def items(self):
        return _REGISTRO_FORMATOS.items()

    def __len__(self):
        return len(_REGISTRO_FORMATOS)


FORMATOS_POR_CODIGO = _VistaPorCodigo()

#: Quanto do arquivo basta olhar para decidir o formato.
_AMOSTRA = 4096


def _casa_assinatura(formato: FormatoEntrada, amostra: bytes) -> bool:
    if formato.assinaturas and any(amostra.startswith(a) for a in formato.assinaturas):
        return True
    # Marcador de texto não é ancorado no byte 0 de propósito: DXF real começa
    # com comentário ou BOM antes do `SECTION`, e exigir posição zero recusaria
    # arquivo legítimo — que é o defeito oposto, e mais caro, do que aceitar.
    if formato.marcadores_texto and any(m in amostra for m in formato.marcadores_texto):
        return True
    return False


def _extensao_casada(formato: FormatoEntrada, nome_baixo: str) -> str:
    """A extensão declarada mais LONGA com que este nome termina, ou `""`.

    O comprimento é o critério porque **extensão composta tem de ganhar da
    simples**: `nuvem.copc.laz` termina em `.laz` (LAS) e em `.copc.laz` (COPC),
    os dois formatos carregam a mesma assinatura `LASF`, e olhar só o último
    segmento devolve o formato errado — o arquivo entra rotulado como LAS.

    Isto existia no `formato_da_extensao` da Prancheta e se perdeu quando a
    PRA.5a trouxe a decisão para a porta única: a regra veio junto com os
    formatos, o teste que a provava ficou do outro lado, e o módulo dele nem
    importava mais. É a única regra da mudança que não sobreviveu à mudança.

    Comparar com o ponto incluído (`.laz`, e não `laz`) é o que dispensa uma
    checagem de fronteira: `xcopc.laz` não termina em `.copc.laz`.
    """
    casadas = [e for e in formato.extensoes if nome_baixo.endswith(e)]
    return max(casadas, key=len) if casadas else ""


def detectar_formato(nome: str, conteudo: bytes) -> FormatoEntrada:
    """Assinatura de bytes → formato. Levanta `FormatoDesconhecido` se nenhum casa.

    Allowlist: só passa o que é reconhecido. É o oposto do que havia antes, em
    que qualquer coisa passava a porta e o `ler_bytes` decidia pelo sufixo lá
    dentro — depois de o arquivo já ter sido gravado no servidor.

    **A extensão nunca decide sozinha, e nunca é a primeira pergunta.** Ela
    desempata entre formatos que compartilham assinatura (todo XLSX é um ZIP;
    todo DWG começa com `AC10`) e, no caso de texto sem marcador próprio, diz
    qual dos formatos-texto o cliente afirma ter mandado. É a correção do
    [D75](../../docs/historico-correcoes.md): a porta da Prancheta perguntava só o nome.
    """
    nome_baixo = (nome or "").lower()
    amostra = conteudo[:_AMOSTRA]
    registrados = formatos_registrados()

    candidatos = [f for f in registrados if _casa_assinatura(f, amostra)]
    if candidatos:
        # Entre os que a assinatura aprovou, ganha o de extensão declarada mais
        # longa — e só entre eles. A extensão continua não decidindo nada
        # sozinha: quem não passou pela assinatura nem chega aqui.
        melhor, comprimento = None, 0
        for candidato in candidatos:
            extensao = _extensao_casada(candidato, nome_baixo)
            if len(extensao) > comprimento:
                melhor, comprimento = candidato, len(extensao)
        return melhor if melhor is not None else candidatos[0]

    if _parece_texto(amostra):
        # Formato-texto sem marcador próprio: a extensão desempata entre eles, e
        # o CSV é o padrão porque é o formato-texto do motor.
        for formato in registrados:
            if (
                not formato.assinaturas
                and not formato.marcadores_texto
                and _extensao_casada(formato, nome_baixo)
            ):
                return formato
        return _REGISTRO_FORMATOS["csv"]

    aceitos = ", ".join(sorted({e for f in registrados for e in f.extensoes}))
    raise FormatoDesconhecido(
        "Não reconheci este arquivo. Aceitos hoje: "
        f"{aceitos} — e o formato é decidido pelo conteúdo, não pelo nome, "
        "então renomear a extensão não ajuda."
    )


def _parece_texto(amostra: bytes) -> bool:
    """Texto de verdade decodifica e não tem byte nulo.

    O byte nulo é o separador barato entre "planilha em CSV" e "binário com
    sufixo trocado": formato executável tem `\\x00` nos primeiros blocos, texto
    de planilha não tem nenhum, em nenhuma codificação que nos interessa.
    """
    if not amostra:
        return False
    if b"\x00" in amostra:
        return False
    try:
        amostra.decode("utf-8")
    except UnicodeDecodeError:
        try:
            amostra.decode("latin-1")
        except UnicodeDecodeError:
            return False
    return True


# ---------------------------------------------------------------------------
# 2. Os limites deste usuário — resolvidos do plano
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Limites:
    """O que este plano permite numa operação de import/export."""

    max_mb: int
    formatos: tuple[str, ...]
    memoria_mb: int
    segundos: int
    plano: str

    @property
    def max_bytes(self) -> int:
        return self.max_mb * 1024 * 1024

    @classmethod
    def de_json(cls, dados: dict | None) -> "Limites":
        """Reconstrói o orçamento a partir do que viajou no argumento da task.

        Só memória e relógio atravessam: tamanho e formato já foram decididos no
        request, sobre o arquivo. Reenviá-los seria carregar o broker com número
        que ninguém vai reler — e convidaria alguém a "revalidar" no worker um
        arquivo que já entrou.
        """
        dados = dados or {}
        return cls(
            max_mb=IMPEXP_TETO_INFRA_MB,
            formatos=tuple(f.codigo for f in formatos_registrados()),
            memoria_mb=int(dados.get("memoria_mb") or IMPEXP_TETO_INFRA_MEMORIA_MB),
            segundos=int(dados.get("segundos") or IMPEXP_TETO_INFRA_SEGUNDOS),
            plano=str(dados.get("plano") or ""),
        )

    def max_mb_de(self, formato: FormatoEntrada) -> int:
        """Teto efetivo deste formato — IE.3, e é aqui que as duas naturezas divergem.

        **Formato tabular** (`xlsx`/`csv`/`pdf`) vale o teto do plano e nada mais:
        `impexp_max_mb` foi dimensionado para planilha e é o número que o dono
        edita para vender mais.

        **Formato de arquivo** (`dwg`, `ifc`, `jpg`) não cabe nesse número — o
        plano mais caro dá 50 MB e um IFC de executivo passa de 200. Para ele o
        teto é o **do formato**, declarado por quem o registrou e medido contra o
        que aquele caminho aguenta; o do plano não se aplica porque descreve outra
        coisa. Quem quiser vender tamanho de prancha por plano tem o knob próprio
        do módulo (`formatos_prancheta`), que já existe.

        O teto de infraestrutura fica por cima dos dois, sempre — pela mesma razão
        de `limites_do_plano`: contrato negociado não compra o direito de derrubar
        o worker compartilhado.
        """
        if formato.natureza == NATUREZA_ARQUIVO and formato.max_mb:
            return min(formato.max_mb, IMPEXP_TETO_INFRA_ARQUIVO_MB)
        return self.max_mb

    def descrever(self) -> dict:
        """O que a tela mostra ANTES do envio (parte 3 do método gov.br)."""
        return {
            "max_mb": self.max_mb,
            "formatos": [
                {
                    "codigo": c,
                    "rotulo": FORMATOS_POR_CODIGO[c].rotulo,
                    "extensoes": list(FORMATOS_POR_CODIGO[c].extensoes),
                    "natureza": FORMATOS_POR_CODIGO[c].natureza,
                    # O teto vai por formato porque agora ele VARIA por formato:
                    # publicar só o `max_mb` do plano faria a tela prometer 50 MB
                    # para um DWG cujo teto real é 300.
                    "max_mb": self.max_mb_de(FORMATOS_POR_CODIGO[c]),
                }
                for c in self.formatos if c in FORMATOS_POR_CODIGO
            ],
            "plano": self.plano,
        }


def _plano_do_usuario(user) -> tuple[dict | None, str]:
    """Configuração do plano, ou `None` quando não dá para saber.

    Fail-open **logado**, pela mesma razão de `moduloprancheta/uploads.py` e de
    `nucleo/quotas.py`: token de serviço ou legado não deve virar
    indisponibilidade. O D21 ensinou que protetor fail-open silencioso fica
    indistinguível de um protetor funcionando — daí o `warning`. E note que o
    fail-open aqui NÃO é ilimitado: cai nos tetos de infraestrutura abaixo.
    """
    slug = getattr(user, "iam_plano", None)
    if not slug or slug not in PLANOS:
        logger.warning(
            "impexp_limite_sem_plano",
            extra={"usuario": getattr(user, "username", None), "plano": slug},
        )
        return None, slug or ""
    return PLANOS[slug], slug


def limites_do_plano(user) -> Limites:
    """Os quatro números desta operação, do plano ou do teto de infraestrutura.

    `None` no plano ("Sob Medida") **não** vira ilimitado: cai no teto duro, pelo
    mesmo motivo de `RATE_TETO_INFRA_HORA` existir por cima da fórmula de
    requisições — contrato negociado não compra o direito de derrubar o worker
    compartilhado, onde também rodam cobrança, NF-e e lembrete.
    """
    plano, slug = _plano_do_usuario(user)
    plano = plano or {}

    def _num(chave: str, teto: int) -> int:
        valor = plano.get(chave)
        if not isinstance(valor, int) or valor <= 0:
            return teto
        return min(valor, teto)

    # `impexp_formatos` governa só os TABULARES (IE.3). Formato de arquivo é
    # vendido pelo knob do módulo dono — `formatos_prancheta` já faz isso, e
    # duplicar a venda em dois lugares faria o cliente que comprou DWG na
    # Prancheta descobrir que o impexp não o aceita.
    tabulares = tuple(
        f.codigo for f in formatos_registrados() if f.natureza == NATUREZA_TABELA
    )
    de_arquivo = tuple(
        f.codigo for f in formatos_registrados() if f.natureza == NATUREZA_ARQUIVO
    )
    declarados = plano.get("impexp_formatos")
    if declarados is None:
        formatos = tabulares + de_arquivo
    else:
        formatos = tuple(c for c in declarados if c in FORMATOS_POR_CODIGO) + de_arquivo

    return Limites(
        max_mb=_num("impexp_max_mb", IMPEXP_TETO_INFRA_MB),
        formatos=formatos,
        memoria_mb=_num("impexp_memoria_mb", IMPEXP_TETO_INFRA_MEMORIA_MB),
        segundos=_num("impexp_segundos", IMPEXP_TETO_INFRA_SEGUNDOS),
        plano=slug,
    )


# ---------------------------------------------------------------------------
# 3. A porta — tamanho e formato, nesta ordem
# ---------------------------------------------------------------------------


def _aceitos_pelo_recurso(recurso) -> frozenset[str] | None:
    """O que ESTE destino recebe. `None` = sem recurso, ou recurso de linha."""
    if recurso is None or not getattr(recurso, "de_arquivo", False):
        return None
    return frozenset(recurso.formatos_arquivo or ())


def _contratados_pelo_recurso(recurso, limites: Limites, user) -> tuple[str, ...]:
    """A parede comercial: o plano do módulo dono, ou o da plataforma.

    Recurso de arquivo vende pelo knob do módulo (`formatos_contratados`);
    recurso de linha, e recurso que não vende por formato, caem no
    `impexp_formatos` do plano, que é o da plataforma.
    """
    if recurso is not None and getattr(recurso, "de_arquivo", False):
        proprios = recurso.formatos_contratados(user)
        if proprios is not None:
            return tuple(proprios)
    return limites.formatos


def teto_do_formato(recurso, formato: FormatoEntrada, limites: Limites) -> int:
    """Teto efetivo: o do recurso quando declarado, senão o do plano/formato.

    O teto de infraestrutura fica por cima em qualquer caminho — é a mesma razão
    de `RATE_TETO_INFRA_HORA` existir por cima da fórmula de requisições.

    **Público desde o D83, e é por isso que ele importa.** Quem responde "cabe?"
    na porta e quem responde "até quanto cabe?" no catálogo tinham de ser a mesma
    função, e não eram: `descrever()` publicava o `max_mb` do plano — 25 MB no
    `profissional` — para formatos cujo teto real, declarado pelo recurso, é
    150 MB de DWG e 300 de IFC. A tela acreditou no catálogo, como manda o método
    do assinador gov.br, e recusou sozinha um DWG de 64,9 MB que o servidor
    aceitaria. Nenhum teste pegou porque nenhuma tela lia o campo até a PRA.5c.
    """
    if recurso is not None:
        proprio = recurso.teto_mb_do_formato(formato.codigo)
        if proprio:
            return min(proprio, IMPEXP_TETO_INFRA_ARQUIVO_MB)
    return limites.max_mb_de(formato)


def validar_entrada(
    *, tamanho: int, nome: str, conteudo: bytes, limites: Limites, recurso=None, user=None,
):
    """Tamanho → formato → contratado. Devolve o `FormatoEntrada` reconhecido.

    **A ordem é a economia:** tamanho primeiro porque é o único que se sabe sem
    olhar um byte; formato depois, sobre a amostra; contratado por último, porque
    negar por plano exige antes saber QUAL formato é — sem isso a mensagem seria
    "seu plano não inclui este arquivo", que não diz nada a ninguém.

    **IE.3 partiu a checagem de tamanho em duas**, e a ordem não pôde ser
    mantida inteira: o teto agora depende do formato (um DWG vale 300 MB, uma
    planilha 50), e o formato só se sabe olhando os bytes. Então o teto do plano
    barra primeiro o que já é grande demais **para qualquer formato** — que é a
    recusa barata, e a que protege de gastar memória com um arquivo absurdo —, e
    o teto do formato confere depois, com o formato na mão.
    """
    teto_absoluto = max(limites.max_bytes, IMPEXP_TETO_INFRA_ARQUIVO_MB * 1024 * 1024)
    if tamanho > teto_absoluto:
        raise ArquivoGrandeDemais(
            f"Arquivo de {tamanho / 1048576:.1f} MB acima do limite de "
            f"{teto_absoluto // (1024 * 1024)} MB que esta plataforma aceita em "
            "qualquer formato. Divida o arquivo.",
            limite_mb=teto_absoluto // (1024 * 1024), tamanho_mb=tamanho / 1048576,
        )

    formato = detectar_formato(nome, conteudo)

    # **PRA.5a — quando há recurso, é ele quem diz o que aceita e o que vende.**
    # O `limites.formatos` do plano governa os TABULARES, que são da plataforma;
    # formato de arquivo é vendido pelo módulo dono (a Prancheta vende "abrir
    # DWG"), e era exatamente isso que estava repartido em seis portas. As duas
    # perguntas são distintas e vêm nesta ordem: *este recurso recebe este
    # formato?* (400 — acidente, um DWG no campo do ASO) e *o plano o inclui?*
    # (402 — parede comercial, com o que comprar).
    aceitos = _aceitos_pelo_recurso(recurso)
    if aceitos is not None and formato.codigo not in aceitos:
        raise FormatoDesconhecido(
            f"{formato.rotulo} não é um arquivo que este destino receba. "
            f"Aceitos aqui: {', '.join(sorted(aceitos)) or 'nenhum'}.",
            # O código vai junto para o módulo poder apontar a porta certa em vez
            # de só listar o que ele aceita — ver o docstring da exceção.
            formato=formato.codigo,
        )

    contratados = _contratados_pelo_recurso(recurso, limites, user)
    if formato.codigo not in contratados:
        disponiveis = [
            FORMATOS_POR_CODIGO[c].rotulo for c in contratados
            if c in FORMATOS_POR_CODIGO
        ]
        raise FormatoNaoContratado(
            f"O plano contratado não importa {formato.rotulo}. "
            f"Disponíveis hoje: {', '.join(disponiveis) or 'nenhum'}.",
            formato=formato.codigo, disponiveis=list(contratados),
        )

    # Agora sim, o teto DESTE formato — do recurso quando ele declara, do plano
    # quando não. Vem depois da parede comercial de propósito: dizer "seu DWG tem
    # 310 MB" a quem não contratou DWG seria responder a pergunta errada.
    limite_mb = teto_do_formato(recurso, formato, limites)
    if tamanho > limite_mb * 1024 * 1024:
        raise ArquivoGrandeDemais(
            f"{formato.rotulo} de {tamanho / 1048576:.1f} MB acima do limite de "
            f"{limite_mb} MB. Divida o arquivo ou faça upgrade do plano.",
            limite_mb=limite_mb, tamanho_mb=tamanho / 1048576,
        )
    return formato
