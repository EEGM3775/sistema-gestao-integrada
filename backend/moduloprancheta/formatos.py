# backend/moduloprancheta/formatos.py
"""Registry de formatos e motores da Prancheta — o **vocabulário** do módulo.

Este arquivo é ENGENHARIA: quais formatos existem, por quais extensões chegam,
que motor sabe abrir cada um e até que tamanho o caminho de upload aguenta.
**Quais** formatos cada plano aceita é decisão COMERCIAL e mora em
`payment/planos.py` (`formatos_prancheta`/`motores_prancheta`), onde o dono do
software os enxerga junto dos preços — a mesma separação que `nucleo/quotas.py`
(`RECURSOS_CONTADOS`) faz com `QUOTAS_DE_OBJETO`.

Os dois lados precisam casar, e é isso que `tests.py::RegistryEPlanosTests`
verifica. Duas divergências possíveis, ambas caras:

- formato vendido num plano e ausente daqui → o cliente contrata o que ninguém
  sabe ler;
- formato vendido num plano cujo **tier de motor** não está habilitado → pior
  ainda: o upload passa, o arquivo ocupa storage e a conversão nunca vai rodar.
  É o caso do RVT, que só a APS traduz (planta §4).

Licença anda junto do motor de propósito. O `libredwg` é **GPLv3** e entra como
subprocesso: o nosso código continua proprietário, mas a imagem passa a
distribuir GPL, o que exige ship da licença e oferta de fonte daquele componente
(planta §12.3). Deixar esse fato num comentário de Dockerfile seria perdê-lo na
primeira refatoração; aqui ele está ao lado de quem o causa.
"""
from __future__ import annotations

from dataclasses import dataclass

from payment.planos import IMPEXP_TETO_INFRA_ARQUIVO_MB, PRANCHETA_MB_POR_FORMATO

# ---------------------------------------------------------------------------
# 1. Tiers de motor — é o que o plano vende (planta §4.1)
# ---------------------------------------------------------------------------
# A decisão do §4.1 foi **os dois**: motor livre nos planos básicos, APS nos
# premium. O degrau não arbitra o dilema do DWG, ele o resolve — o cliente de
# entrada abre DWG sem que a plataforma pague por arquivo, e quem precisa de
# fidelidade de referência (ou de RVT) paga por ela.
TIER_LIVRE = "livre"
TIER_PREMIUM = "premium"


@dataclass(frozen=True)
class Motor:
    codigo: str
    nome: str
    tier: str
    licenca: str
    # COGS por arquivo traduzido. Só a APS cobra; os livres custam CPU nossa.
    custo_por_traducao: bool = False


MOTORES: tuple[Motor, ...] = (
    Motor("pdf_nativo", "Render nativo do browser", TIER_LIVRE, "—"),
    Motor("ezdxf", "ezdxf (DXF → SVG)", TIER_LIVRE, "MIT"),
    # GPLv3: chamado como binário separado. Ver planta §12.3 — obrigação de
    # distribuição pendente, a fechar no PRA.1 junto do adaptador.
    Motor("libredwg", "LibreDWG (dwg2dxf)", TIER_LIVRE, "GPLv3 (subprocesso)"),
    Motor("ifcopenshell", "IfcOpenShell + That Open/Fragments", TIER_LIVRE, "LGPL / MIT"),
    Motor("gdal", "GDAL/OGR", TIER_LIVRE, "MIT"),
    Motor("pdal", "PDAL/Potree", TIER_LIVRE, "BSD"),
    Motor("aps", "Autodesk Platform Services (Model Derivative)", TIER_PREMIUM, "comercial", True),
)

MOTOR_POR_CODIGO: dict[str, Motor] = {m.codigo: m for m in MOTORES}


# ---------------------------------------------------------------------------
# 2. Teto do caminho de upload direto
# ---------------------------------------------------------------------------
# O multipart do request é o único caminho de entrada do PRA.0, e ele carrega o
# arquivo inteiro numa requisição. O gateway já aceita corpo ilimitado
# (`client_max_body_size 0` — o limite é da app, por desenho), mas 2 GB de nuvem
# de pontos numa requisição só travam um worker e morrem no timeout.
#
# **O número não é daqui, e deixou de ser copiado** (08/08/2026). Ele descreve o
# que a *plataforma* aguarda receber por multipart, não algo da Prancheta, e já
# vivia em `payment/planos.py` como `IMPEXP_TETO_INFRA_ARQUIVO_MB` — a nota de lá
# dizia inclusive que subira "para não haver dois números dizendo a mesma coisa",
# e o 300 tinha ficado aqui também. O alias fica porque é por este nome que a
# planta, o `/status/` e o teste o chamam.
TETO_UPLOAD_DIRETO_MB = IMPEXP_TETO_INFRA_ARQUIVO_MB


@dataclass(frozen=True)
class Formato:
    codigo: str
    nome: str
    familia: str
    extensoes: tuple[str, ...]
    mimes: tuple[str, ...]
    # Motores capazes de abrir, em ordem de preferência. O primeiro cujo tier o
    # plano habilita é o que o pipeline (PRA.1) usa.
    motores: tuple[str, ...]
    # PRA.5a — **como este formato é reconhecido pelos BYTES**, para a allowlist
    # da plataforma ([funcoesimpexp/limites.py](../funcoesimpexp/limites.py)).
    #
    # É o que fecha o [D75](../../docs/historico-correcoes.md): até aqui a porta decidia
    # pela extensão do nome, e o D65 já tinha registrado que sufixo é dado do
    # atacante. Quem declara é este registry porque é o módulo que sabe o que é
    # um DWG; quem *aplica* é o motor, uma vez só, para todas as portas.
    #
    # `assinaturas` são prefixos binários; `marcadores_texto` são trechos que
    # aparecem perto do começo de formatos que são TEXTO estruturado — metade do
    # mundo CAD é assim (DXF abre com `SECTION`, IFC com `ISO-10303-21`), e para
    # eles a prova certa não é assinatura binária (não têm) nem "parece texto"
    # (fraco demais para uma porta que aceita centenas de MB).
    #
    # **Vazio nos dois = a plataforma não sabe reconhecer este formato**, e ele
    # não entra na allowlist. Ver `SEM_ASSINATURA_CONHECIDA` abaixo.
    assinaturas: tuple[bytes, ...] = ()
    marcadores_texto: tuple[bytes, ...] = ()
    # Quem é dono do DADO depois de aberto (planta §3). A Prancheta **abre**;
    # nem todo formato fica guardado nela. O seam que materializa isso é o PRA.7
    # (prancha georreferenciada → camada no Maps) — aqui a intenção fica
    # registrada para não se perder no meio do pipeline.
    dono: str = "prancheta"
    # PRA.3 — formato que NÃO é desenho e por isso não passa pelo acervo.
    #
    # O BCF é o caso, e ele estava declarado errado até aqui: figurava com motor
    # `ifcopenshell`, como se fosse um arquivo a converter em derivada. Não é —
    # um `.bcfzip` não tem geometria nenhuma, ele carrega **marcações** sobre um
    # desenho que já está no acervo. Subi-lo como revisão gastaria storage e
    # terminaria em `arquivo_corrompido` quando o motor de IFC tentasse abri-lo.
    #
    # Formato de interoperabilidade entra e sai por endpoint próprio
    # (`marcacoes/importar-bcf/` e `.../bcf/`), continua vivendo no registry
    # porque é ele que o plano vende, e é `validar_arquivo` quem recusa a porta
    # errada — dizendo qual é a certa.
    interop: bool = False

    @property
    def max_mb(self) -> int:
        """Até que tamanho este formato entra — e o número **não mora aqui**.

        Era um campo do dataclass, escrito ao lado da assinatura de bytes e do
        motor. Saiu para [payment/planos.py](../../payment/planos.py) §5.3 por
        decisão do dono (08/08/2026): *todo teto ou limite vive em `payment/`*.
        A linha que separa os dois arquivos ficou mais nítida — aqui é o que a
        plataforma **sabe fazer** com o formato (reconhecer, abrir, com que
        motor); lá é o que ela **vende** dele, e tamanho é venda: é a resposta a
        "até que tamanho o meu plano aceita uma prancha".

        `0` para formato sem número declarado, que faz o motor cair no teto do
        plano — errado para prancha, e por isso `tests.py::RegistryEPlanosTests`
        cobra a lista completa em vez de deixar o silêncio passar.
        """
        return PRANCHETA_MB_POR_FORMATO.get(self.codigo, 0)


# Famílias — o agrupamento que a tela usa e que o §3 da planta nomeia.
FAMILIA_DOCUMENTO = "documento"
FAMILIA_CAD2D = "cad2d"
FAMILIA_BIM = "bim"
FAMILIA_GEO = "geo"
FAMILIA_NUVEM = "nuvem"
FAMILIA_COLABORACAO = "colaboracao"

# Assinaturas compartilhadas por vários formatos — o sufixo é que desempata
# entre eles, e é para isso que a extensão serve depois do D75: não para decidir,
# para escolher entre candidatos que os bytes já aprovaram.
ZIP = (b"PK\x03\x04",)
#: Compound File Binary (OLE2) — o contêiner da Microsoft. RVT e DGN V8 o usam.
OLE2 = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)

#: Formatos que a plataforma **vende e não sabe reconhecer pelos bytes** (PRA.5a).
#:
#: Não é preguiça de pesquisa: o autor do formato Navisworks descreve o contêiner
#: como *"em vez de simplesmente adotar ZIP, criei o meu"*, sem assinatura
#: publicada; e o SKP não tem número mágico estável — o cabeçalho muda entre
#: versões, e do SketchUp 2021 em diante o contêiner é outro (VFF).
#:
#: **Consequência, decidida em 08/08/2026:** eles saem de `formatos_prancheta`
#: até a PRA.4. Ninguém perde função — o motor deles (`aps`) não existe, então
#: hoje um NWD entra pelo nome, gasta storage e gera zero derivadas. Recusar na
#: porta dizendo a verdade é mais honesto do que aceitar bytes que não sabemos
#: identificar e entregá-los a nada.
#:
#: **Gatilho de reabertura:** com um `.nwd` e um `.skp` reais em mãos, a
#: assinatura sai medida — como a PRA.1d fez com os 160 DWGs — e eles voltam ao
#: plano junto com o motor que os abre.
SEM_ASSINATURA_CONHECIDA: frozenset[str] = frozenset({"nwd", "skp"})

FORMATOS: tuple[Formato, ...] = (
    # --- Documento: o que já se abre hoje, e por isso o degrau de entrada ---
    Formato("pdf", "PDF", FAMILIA_DOCUMENTO, (".pdf",), ("application/pdf",), ("pdf_nativo",),
            assinaturas=(b"%PDF-",), dono="modulodms"),
    Formato(
        "imagem", "Imagem (JPG/PNG/WebP)", FAMILIA_DOCUMENTO,
        (".jpg", ".jpeg", ".png", ".webp"),
        ("image/jpeg", "image/png", "image/webp"),
        ("pdf_nativo",),
        # RIFF é o contêiner do WebP (e de AVI/WAV, que o sufixo descarta).
        assinaturas=(b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF"),
        dono="modulodms",
    ),
    # --- CAD 2D ---
    # DXF é TEXTO — a prova é o marcador do próprio formato, não uma assinatura
    # binária que ele não tem. O DXF binário (raro) tem cabeçalho próprio.
    Formato("dxf", "AutoCAD DXF", FAMILIA_CAD2D, (".dxf",), ("image/vnd.dxf", "application/dxf"), ("ezdxf", "aps"),
            assinaturas=(b"AutoCAD Binary DXF",), marcadores_texto=(b"SECTION",)),
    # DWG abre nos DOIS motores, com fidelidade diferente. É o desenho do §4.1
    # em uma linha: o degrau do plano é o motor, não o formato.
    # `AC10` cobre R13 a 2018 inteiro (AC1012…AC1032) — a versão vem depois.
    Formato("dwg", "AutoCAD DWG", FAMILIA_CAD2D, (".dwg",), ("image/vnd.dwg", "application/acad"), ("libredwg", "aps"),
            assinaturas=(b"AC10",)),
    # DWF clássico tem cabeçalho próprio; DWFx é OPC, que é zip.
    Formato("dwf", "Autodesk DWF", FAMILIA_CAD2D, (".dwf", ".dwfx"), ("model/vnd.dwf",), ("aps",),
            assinaturas=(b"(DWF ", *ZIP)),
    # --- BIM 3D ---
    # IFC é STEP: texto que abre com o cabeçalho ISO. `.ifczip` é o mesmo zipado.
    Formato("ifc", "IFC (2x3/4/4.3)", FAMILIA_BIM, (".ifc", ".ifczip"), ("application/x-step",), ("ifcopenshell", "aps"),
            assinaturas=ZIP, marcadores_texto=(b"ISO-10303-21",)),
    Formato("rvt", "Autodesk Revit", FAMILIA_BIM, (".rvt", ".rfa"), (), ("aps",),
            assinaturas=OLE2),
    # Sem assinatura: ver `SEM_ASSINATURA_CONHECIDA`.
    Formato("nwd", "Navisworks", FAMILIA_BIM, (".nwd", ".nwc"), (), ("aps",)),
    # DGN V8 é OLE2; o V7 da Intergraph tem cabeçalho próprio.
    Formato("dgn", "MicroStation DGN", FAMILIA_BIM, (".dgn",), (), ("aps",),
            assinaturas=(*OLE2, b"\x08\x09\xfe")),
    # Sem assinatura estável: ver `SEM_ASSINATURA_CONHECIDA`.
    Formato("skp", "SketchUp", FAMILIA_BIM, (".skp",), (), ("aps",)),
    # --- Geo: a Prancheta abre, o Maps guarda (planta §3) ---
    Formato("kmz", "KML/KMZ", FAMILIA_GEO, (".kml", ".kmz"), ("application/vnd.google-earth.kmz",), ("gdal",),
            assinaturas=ZIP, marcadores_texto=(b"<kml",), dono="modulomaps"),
    Formato("shp", "Shapefile (ZIP)", FAMILIA_GEO, (".zip",), ("application/zip",), ("gdal",),
            assinaturas=ZIP, dono="modulomaps"),
    Formato("geojson", "GeoJSON", FAMILIA_GEO, (".geojson", ".json"), ("application/geo+json",), ("gdal",),
            marcadores_texto=(b'"type"',), dono="modulomaps"),
    Formato("gpkg", "GeoPackage", FAMILIA_GEO, (".gpkg",), (), ("gdal",),
            assinaturas=(b"SQLite format 3\x00",), dono="modulomaps"),
    Formato("qgis", "Projeto QGIS", FAMILIA_GEO, (".qgz", ".qgs"), (), ("gdal",),
            assinaturas=ZIP, marcadores_texto=(b"<qgis",), dono="modulomaps"),
    Formato("geotiff", "GeoTIFF", FAMILIA_GEO, (".tif", ".tiff"), ("image/tiff",), ("gdal",),
            assinaturas=(b"II\x2a\x00", b"MM\x00\x2a"), dono="modulomaps"),
    # --- Nuvem de pontos: o pixel continua no drone (planta §3) ---
    # LAZ e COPC mantêm o cabeçalho LAS — a compressão é interna.
    Formato("las", "LAS/LAZ", FAMILIA_NUVEM, (".las", ".laz"), (), ("pdal",),
            assinaturas=(b"LASF",), dono="drone"),
    Formato("copc", "COPC", FAMILIA_NUVEM, (".copc", ".copc.laz"), (), ("pdal",),
            assinaturas=(b"LASF",), dono="drone"),
    Formato("e57", "E57", FAMILIA_NUVEM, (".e57",), (), ("pdal",),
            assinaturas=(b"ASTM-E57",), dono="drone"),
    # --- Colaboração: o que fecha o laço com o escritório (planta §3) ---
    # Sem motor e `interop=True`: BCF não vira derivada, vira marcação. É o
    # canal de ida e volta com o software do projetista (PRA.3), e o plano que o
    # contrata está comprando a INTEROPERABILIDADE — marcar dentro do sistema
    # continua incluído no módulo.
    Formato("bcf", "BCF (marcação)", FAMILIA_COLABORACAO, (".bcf", ".bcfzip"), (), (),
            assinaturas=ZIP, interop=True),
)

FORMATO_POR_CODIGO: dict[str, Formato] = {f.codigo: f for f in FORMATOS}
CODIGOS_FORMATO: frozenset[str] = frozenset(FORMATO_POR_CODIGO)

# Escolhas para o campo `formato` do modelo. Derivadas do registry para não
# existir um segundo lugar onde a lista possa envelhecer.
FORMATO_CHOICES: tuple[tuple[str, str], ...] = tuple((f.codigo, f.nome) for f in FORMATOS)
MOTOR_CHOICES: tuple[tuple[str, str], ...] = tuple((m.codigo, m.nome) for m in MOTORES)


def registrar_formatos_na_plataforma() -> tuple[str, ...]:
    """PRA.5a — entrega os formatos deste módulo à allowlist do `funcoesimpexp`.

    **Isto substitui o `formato_da_extensao`, que era o [D75](../../docs/historico-correcoes.md).**
    A função antiga escolhia o formato pelo sufixo do nome que o cliente mandou e
    era o que a porta de upload consultava: `payload.exe` renomeado para `.dwg`
    passava, era gravado, contava storage e ia parar no LibreDWG — parser em C no
    worker. Agora quem decide são os **bytes**, e quem os lê é o motor: aqui só se
    declara qual é a assinatura de cada formato.

    Devolve os códigos registrados. Os de `SEM_ASSINATURA_CONHECIDA` ficam de
    fora — a plataforma não admite o que não sabe identificar, e uma allowlist que
    aceita "qualquer coisa com este sufixo" é uma denylist com outro nome.

    Idempotente: `registrar_formato` aceita a mesma declaração duas vezes (o
    `impexp.py` de um módulo pode ser importado de novo em teste) e recusa duas
    declarações **diferentes** para o mesmo código.
    """
    from funcoesimpexp.limites import (
        NATUREZA_ARQUIVO,
        FORMATOS_POR_CODIGO,
        FormatoEntrada,
        registrar_formato,
    )

    registrados: list[str] = []
    for formato in FORMATOS:
        if formato.codigo in SEM_ASSINATURA_CONHECIDA:
            continue
        # **`pdf` o motor já conhece, e como TABELA** — é dele que o Orçamento lê
        # planilha de preço de prefeitura. Não se re-registra: o mesmo arquivo
        # pode ser tabela lá e desenho aqui, e quem decide isso é a natureza do
        # RECURSO, não a do formato. Re-declarar derrubaria o boot, e com razão:
        # duas declarações fariam a detecção depender da ordem de import.
        if formato.codigo in FORMATOS_POR_CODIGO:
            registrados.append(formato.codigo)
            continue
        registrar_formato(FormatoEntrada(
            codigo=formato.codigo,
            rotulo=formato.nome,
            extensoes=formato.extensoes,
            assinaturas=formato.assinaturas,
            natureza=NATUREZA_ARQUIVO,
            marcadores_texto=formato.marcadores_texto,
            # O teto NÃO viaja com o formato: o mesmo PDF é planilha de preço no
            # Orçamento (dezenas de MB) e prancha aqui (100 MB), e um número só
            # serviria mal aos dois. Quem declara o teto é o RECURSO —
            # `Recurso.teto_mb_do_formato`, que a PRA.5a acrescentou ao motor.
            max_mb=0,
            origem="moduloprancheta",
        ))
        registrados.append(formato.codigo)
    return tuple(registrados)


def sem_assinatura(codigo: str) -> bool:
    """Este formato é vendido e a plataforma ainda não sabe reconhecê-lo?"""
    return codigo in SEM_ASSINATURA_CONHECIDA


def motores_do_formato(codigo_formato: str) -> tuple[Motor, ...]:
    formato = FORMATO_POR_CODIGO[codigo_formato]
    return tuple(MOTOR_POR_CODIGO[c] for c in formato.motores)


def tiers_do_formato(codigo_formato: str) -> frozenset[str]:
    """Tiers de motor que conseguem abrir este formato.

    **Vazio para formato de interoperabilidade** (`interop=True`), e isso não é
    lacuna: não há motor porque não há o que converter. Quem consome este
    conjunto para decidir cadeado precisa tratar o caso — é o que
    `uploads.formatos_declarados` faz, sob pena de um BCF contratado aparecer na
    tela como "exige motor de alta fidelidade" e virar um upsell inventado.
    """
    return frozenset(m.tier for m in motores_do_formato(codigo_formato))
