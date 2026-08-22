# backend/moduloprancheta/bcf.py
"""BCF 2.1 — ler e escrever o formato que leva a marcação do canteiro ao escritório.

**Por que este arquivo existe.** A marcação só vale se sair daqui. O mestre de
obras aponta a interferência no tablet; quem a resolve abre o modelo no Revit,
no Navisworks, no Solibri ou no BIMcollab. O BCF (BuildingSMART Collaboration
Format) é o que todos eles leem — um ZIP com XML por tópico. Sem ele, a
Prancheta teria uma caixa de recados que só ela mesma abre, e o laço com o
projetista continuaria sendo WhatsApp e foto de tela.

**Escrito à mão, sem biblioteca.** O formato é um zip com dois XML pequenos por
tópico; a alternativa seria uma dependência a mais na imagem — que já carrega o
OpenCascade do `ifcopenshell` — para montar 40 linhas de `ElementTree`. Como o
esquema é estável desde 2015 e o que consumimos dele é o subconjunto que os
visualizadores de mercado de fato preenchem, o custo de manter isto aqui é menor
que o de carregar mais um pacote.

**Fidelidade acima de elegância.** A `camera` é guardada com os nomes do padrão
(`CameraViewPoint`, `ViewToWorldScale`) e não traduzida para um dicionário
"limpo" nosso. Um de-para de nomes teria de ser mantido nos dois sentidos e
perderia exatamente o que ainda não sabemos desenhar — que é justamente o que
precisa atravessar intacto para o software do projetista.

**O que o BCF 2.1 NÃO carrega, e por isso não prometemos:** o padrão é centrado
em modelo 3D — o tópico aponta para componente IFC e para uma câmera no espaço.
Marcação feita sobre prancha 2D não tem nem um nem outro. O que atravessa é o
tópico inteiro (título, descrição, tipo, situação, prioridade, responsável,
prazo, rótulos), os comentários e o **snapshot**; a coordenada na folha
(`Marcacao.ancora`) fica de fora do padrão e viaja como a imagem mais o
`ReferenceLink` de volta para cá. Reimportar o mesmo arquivo reencontra a
marcação pelo GUID e **não** perde a âncora, porque ela nunca sai da nossa linha.

**Segurança na leitura — o arquivo vem de fora.** Três guardas, e cada uma fecha
uma classe inteira:

1. **DOCTYPE é recusado.** É o que mata *billion laughs* e entidade externa de
   uma vez; o `ElementTree` não resolve entidade externa (não tem resolver), mas
   entidade interna declarada em DTD ele expande. Nenhum BCF legítimo traz DTD,
   então recusar não custa compatibilidade — e é mais sólido que confiar no
   parser.
2. **Teto de tamanho descomprimido**, lido do cabeçalho do zip antes de
   descomprimir qualquer coisa: um `.bcfzip` de 2 MB pode declarar 40 GB.
3. **Nada é extraído para disco.** Lê-se por nome, em memória, com o teto acima.
   Sem `extractall`, o *path traversal* (`../../etc/...`) não tem por onde
   acontecer — e o snapshot só vira arquivo depois de o Django validar que é
   imagem.
"""
from __future__ import annotations

import io
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from xml.etree import ElementTree

from django.utils.dateparse import parse_datetime

from payment.planos import (
    PRANCHETA_TETO_BCF_DESCOMPRIMIDO_MB,
    PRANCHETA_TETO_BCF_TOPICOS,
    PRANCHETA_TETO_BCF_XML_MB,
    PRANCHETA_TETO_SNAPSHOT_MB,
)

VERSAO = "2.1"

# Tetos da importação. Todos recusam com mensagem em vez de truncar em silêncio:
# um lote que entra pela metade é pior que um que não entra, porque ninguém fica
# sabendo do que faltou.
#
# **Os números saíram daqui** (decisão do dono, 08/08/2026 — *todo teto ou limite
# vive em `payment/`*). Estes eram os últimos escritos em código de engenharia, e
# o do snapshot foi o que denunciou a turma: a recusa por tamanho é sempre 402 e
# oferece "faça upgrade do plano", que era mentira enquanto o número não fosse do
# dono. O que ficou aqui é a **unidade** — o zip fala em bytes, o dono pensa em
# MB, e converter num lugar só evita o erro de fator de mil.
MAX_DESCOMPRIMIDO_BYTES = PRANCHETA_TETO_BCF_DESCOMPRIMIDO_MB * 1024 * 1024
MAX_XML_BYTES = PRANCHETA_TETO_BCF_XML_MB * 1024 * 1024
MAX_TOPICOS = PRANCHETA_TETO_BCF_TOPICOS
MAX_SNAPSHOT_BYTES = PRANCHETA_TETO_SNAPSHOT_MB * 1024 * 1024


class BcfInvalido(Exception):
    """Arquivo que não é um BCF utilizável. A mensagem vai para o usuário, então
    diz o que está errado no arquivo dele — não o nome da exceção interna."""


# ---------------------------------------------------------------------------
# Estruturas de transporte — o que atravessa entre o zip e o ORM
# ---------------------------------------------------------------------------
@dataclass
class ComentarioBcf:
    guid: str
    texto: str
    autor: str = ""
    data: datetime | None = None
    ponto_de_vista_guid: str = ""


@dataclass
class PontoDeVistaBcf:
    guid: str
    camera: dict = field(default_factory=dict)
    snapshot: bytes | None = None
    snapshot_nome: str = ""


@dataclass
class TopicoBcf:
    guid: str
    titulo: str
    descricao: str = ""
    tipo: str = "Issue"
    situacao: str = "Open"
    prioridade: str = "Normal"
    rotulos: list[str] = field(default_factory=list)
    prazo: date | None = None
    autor: str = ""
    data_criacao: datetime | None = None
    responsavel_email: str = ""
    comentarios: list[ComentarioBcf] = field(default_factory=list)
    pontos_de_vista: list[PontoDeVistaBcf] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def _xml_seguro(dados: bytes, *, onde: str) -> ElementTree.Element:
    """Analisa o XML recusando DTD e tamanho abusivo. Ver o cabeçalho (guarda 1)."""
    if len(dados) > MAX_XML_BYTES:
        raise BcfInvalido(
            f"O arquivo interno '{onde}' tem {len(dados) // 1024} KB, acima do "
            f"limite de {MAX_XML_BYTES // 1024} KB para um XML de marcação."
        )
    # A checagem é sobre os bytes crus e antes de analisar: depois de o parser
    # ver o DOCTYPE, a expansão já aconteceu.
    cabeca = dados[:2048].lstrip().lower()
    if b"<!doctype" in cabeca or b"<!entity" in dados[:8192].lower():
        raise BcfInvalido(
            f"O arquivo interno '{onde}' declara DTD ou entidades, o que um BCF "
            "não usa. Recusado por segurança."
        )
    try:
        return ElementTree.fromstring(dados)
    except ElementTree.ParseError as erro:
        raise BcfInvalido(f"XML inválido em '{onde}': {erro}") from erro


def _texto(no: ElementTree.Element | None, caminho: str, padrao: str = "") -> str:
    if no is None:
        return padrao
    achado = no.find(caminho)
    if achado is None or achado.text is None:
        return padrao
    return achado.text.strip()


def _data(no: ElementTree.Element | None, caminho: str) -> datetime | None:
    bruto = _texto(no, caminho)
    return parse_datetime(bruto) if bruto else None


def _camera(visualizacao: ElementTree.Element) -> dict:
    """Extrai a câmera preservando os nomes do padrão (ver o cabeçalho).

    Devolve `{}` quando o ponto de vista não tem câmera — o caso normal de uma
    marcação 2D, e o motivo de o campo ser opcional no modelo.
    """
    for tipo in ("OrthogonalCamera", "PerspectiveCamera"):
        no = visualizacao.find(tipo)
        if no is None:
            continue
        dados: dict = {"tipo": tipo}
        for vetor in ("CameraViewPoint", "CameraDirection", "CameraUpVector"):
            sub = no.find(vetor)
            if sub is not None:
                dados[vetor] = {
                    eixo: _numero(_texto(sub, eixo)) for eixo in ("X", "Y", "Z")
                }
        escalar = "ViewToWorldScale" if tipo == "OrthogonalCamera" else "FieldOfView"
        valor = _texto(no, escalar)
        if valor:
            dados[escalar] = _numero(valor)
        return dados
    return {}


def _numero(bruto: str) -> float | None:
    try:
        return float(bruto)
    except (TypeError, ValueError):
        return None


def _guid_valido(bruto: str) -> str:
    """Normaliza o GUID vindo de fora, ou gera um.

    O GUID é a identidade da marcação entre sistemas, e um arquivo com GUID
    malformado não pode derrubar a importação inteira: a marcação entra com um
    novo, e a única consequência é que a próxima volta dela não reencontrará o
    tópico do software de origem — o que já era verdade com o GUID quebrado.
    """
    try:
        return str(uuid.UUID(bruto.strip()))
    except (AttributeError, ValueError):
        return str(uuid.uuid4())


def ler(conteudo: bytes) -> list[TopicoBcf]:
    """Lê um `.bcfzip`/`.bcf` e devolve os tópicos.

    Tolera o que o mercado produz de fato: pasta com nome que não é o GUID (o
    GUID vale é o do atributo do `<Topic>`), viewpoint sem snapshot, comentário
    sem autor. Não tolera o que indica arquivo hostil ou quebrado — aí levanta
    `BcfInvalido` com o motivo, porque um lote que entra pela metade é pior que
    um recusado.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile as erro:
        raise BcfInvalido(
            "O arquivo não é um ZIP válido — um BCF é um pacote compactado "
            "(.bcf/.bcfzip) exportado pelo seu visualizador."
        ) from erro

    # Guarda 2: soma o tamanho DECLARADO antes de descomprimir qualquer byte.
    total = sum(item.file_size for item in zf.infolist())
    if total > MAX_DESCOMPRIMIDO_BYTES:
        raise BcfInvalido(
            f"O conteúdo descomprimido chega a {total // (1024 * 1024)} MB, acima "
            f"do limite de {MAX_DESCOMPRIMIDO_BYTES // (1024 * 1024)} MB."
        )

    nomes = zf.namelist()
    marcacoes = [n for n in nomes if n.rsplit("/", 1)[-1].lower() == "markup.bcf"]
    if not marcacoes:
        raise BcfInvalido(
            "Nenhum 'markup.bcf' encontrado no pacote. O arquivo pode ser um BCF "
            "em outra versão do formato, ou um ZIP comum."
        )
    if len(marcacoes) > MAX_TOPICOS:
        raise BcfInvalido(
            f"O pacote traz {len(marcacoes)} tópicos, acima do limite de "
            f"{MAX_TOPICOS} por importação."
        )

    topicos: list[TopicoBcf] = []
    for caminho in marcacoes:
        pasta = caminho.rsplit("/", 1)[0] if "/" in caminho else ""
        topicos.append(_ler_topico(zf, caminho, pasta, nomes))
    return topicos


def _ler_topico(zf: zipfile.ZipFile, caminho: str, pasta: str, nomes: list[str]) -> TopicoBcf:
    raiz = _xml_seguro(zf.read(caminho), onde=caminho)
    no_topico = raiz.find("Topic")
    if no_topico is None:
        raise BcfInvalido(f"'{caminho}' não tem o elemento <Topic>.")

    rotulos = [n.text.strip() for n in no_topico.findall("Labels") if n.text and n.text.strip()]
    prazo_bruto = _data(no_topico, "DueDate")

    topico = TopicoBcf(
        guid=_guid_valido(no_topico.get("Guid", "")),
        titulo=_texto(no_topico, "Title", "(sem título)")[:200],
        descricao=_texto(no_topico, "Description"),
        tipo=no_topico.get("TopicType", "") or "Issue",
        situacao=no_topico.get("TopicStatus", "") or "Open",
        prioridade=_texto(no_topico, "Priority", "Normal"),
        rotulos=rotulos,
        prazo=prazo_bruto.date() if prazo_bruto else None,
        autor=_texto(no_topico, "CreationAuthor")[:180],
        data_criacao=_data(no_topico, "CreationDate"),
        responsavel_email=_texto(no_topico, "AssignedTo")[:254],
    )

    # Em BCF 2.1 <Comment> e <Viewpoints> são irmãos de <Topic> dentro de
    # <Markup>, não filhos dele — erro fácil de cometer e que faz a importação
    # trazer tópicos mudos, sem nenhum aviso.
    for no in raiz.findall("Comment"):
        texto = _texto(no, "Comment")
        if not texto:
            continue
        referencia = no.find("Viewpoint")
        topico.comentarios.append(ComentarioBcf(
            guid=_guid_valido(no.get("Guid", "")),
            texto=texto,
            autor=_texto(no, "Author")[:180],
            data=_data(no, "Date"),
            ponto_de_vista_guid=(referencia.get("Guid", "") if referencia is not None else ""),
        ))

    for no in raiz.findall("Viewpoints"):
        topico.pontos_de_vista.append(
            _ler_ponto_de_vista(zf, no, pasta, nomes)
        )
    return topico


def _ler_ponto_de_vista(
    zf: zipfile.ZipFile, no: ElementTree.Element, pasta: str, nomes: list[str]
) -> PontoDeVistaBcf:
    ponto = PontoDeVistaBcf(guid=_guid_valido(no.get("Guid", "")))

    arquivo_vp = _texto(no, "Viewpoint")
    if arquivo_vp:
        alvo = f"{pasta}/{arquivo_vp}" if pasta else arquivo_vp
        if alvo in nomes:
            ponto.camera = _camera(_xml_seguro(zf.read(alvo), onde=alvo))

    arquivo_snap = _texto(no, "Snapshot")
    if arquivo_snap:
        alvo = f"{pasta}/{arquivo_snap}" if pasta else arquivo_snap
        if alvo in nomes:
            info = zf.getinfo(alvo)
            # Snapshot fora do teto é descartado, mas o tópico entra: perder a
            # imagem é aceitável, perder o apontamento não.
            if info.file_size <= MAX_SNAPSHOT_BYTES:
                ponto.snapshot = zf.read(alvo)
                ponto.snapshot_nome = arquivo_snap.rsplit("/", 1)[-1]
    return ponto


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
def _iso(valor) -> str:
    if valor is None:
        return ""
    return valor.isoformat()


def _sub(pai: ElementTree.Element, tag: str, texto: str = "") -> ElementTree.Element:
    no = ElementTree.SubElement(pai, tag)
    if texto:
        no.text = texto
    return no


def _bytes_do_xml(raiz: ElementTree.Element) -> bytes:
    """Com declaração XML: parte dos visualizadores recusa o `.bcfv` sem ela."""
    return ElementTree.tostring(raiz, encoding="utf-8", xml_declaration=True)


def escrever(topicos: list[TopicoBcf], *, snapshots: dict[str, bytes] | None = None) -> bytes:
    """Monta o `.bcfzip` a partir dos tópicos.

    `snapshots` mapeia GUID de ponto de vista para os bytes da imagem — vem de
    fora porque quem tem os arquivos é o campo `ImageField`, e este módulo não
    fala com o ORM de propósito: é o que permite testá-lo sem banco.
    """
    snapshots = snapshots or {}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        versao = ElementTree.Element("Version", {"VersionId": VERSAO})
        _sub(versao, "DetailedVersion", VERSAO)
        zf.writestr("bcf.version", _bytes_do_xml(versao))

        for indice, topico in enumerate(topicos):
            pasta = topico.guid
            raiz = ElementTree.Element("Markup")

            no = ElementTree.SubElement(raiz, "Topic", {
                "Guid": topico.guid,
                "TopicType": topico.tipo,
                "TopicStatus": topico.situacao,
            })
            _sub(no, "Title", topico.titulo)
            _sub(no, "Priority", topico.prioridade)
            _sub(no, "Index", str(indice))
            for rotulo in topico.rotulos:
                _sub(no, "Labels", str(rotulo))
            _sub(no, "CreationDate", _iso(topico.data_criacao))
            _sub(no, "CreationAuthor", topico.autor)
            if topico.prazo:
                _sub(no, "DueDate", _iso(topico.prazo))
            if topico.responsavel_email:
                _sub(no, "AssignedTo", topico.responsavel_email)
            if topico.descricao:
                _sub(no, "Description", topico.descricao)

            for comentario in topico.comentarios:
                no_c = ElementTree.SubElement(raiz, "Comment", {"Guid": comentario.guid})
                _sub(no_c, "Date", _iso(comentario.data))
                _sub(no_c, "Author", comentario.autor)
                _sub(no_c, "Comment", comentario.texto)
                if comentario.ponto_de_vista_guid:
                    ElementTree.SubElement(
                        no_c, "Viewpoint", {"Guid": comentario.ponto_de_vista_guid}
                    )

            for ordem, ponto in enumerate(topico.pontos_de_vista):
                imagem = snapshots.get(ponto.guid)
                no_v = ElementTree.SubElement(raiz, "Viewpoints", {"Guid": ponto.guid})
                nome_vp = f"{ponto.guid}.bcfv"
                _sub(no_v, "Viewpoint", nome_vp)
                if imagem:
                    nome_snap = f"{ponto.guid}.png"
                    _sub(no_v, "Snapshot", nome_snap)
                    zf.writestr(f"{pasta}/{nome_snap}", imagem)
                _sub(no_v, "Index", str(ordem))
                zf.writestr(f"{pasta}/{nome_vp}", _bytes_do_xml(_visualizacao(ponto)))

            zf.writestr(f"{pasta}/markup.bcf", _bytes_do_xml(raiz))

    return buffer.getvalue()


def _visualizacao(ponto: PontoDeVistaBcf) -> ElementTree.Element:
    """O `.bcfv`. Sai válido mesmo sem câmera — que é o caso da marcação 2D.

    Um `<VisualizationInfo>` só com o GUID é o mínimo que o padrão aceita, e é a
    resposta honesta: não havia câmera porque não havia modelo 3D. Inventar uma
    faria o visualizador do projetista abrir um ponto de vista arbitrário e
    parecer que a marcação aponta para outro lugar.
    """
    raiz = ElementTree.Element("VisualizationInfo", {"Guid": ponto.guid})
    camera = ponto.camera or {}
    tipo = camera.get("tipo")
    if tipo in ("OrthogonalCamera", "PerspectiveCamera"):
        no = ElementTree.SubElement(raiz, tipo)
        for vetor in ("CameraViewPoint", "CameraDirection", "CameraUpVector"):
            valores = camera.get(vetor) or {}
            if not valores:
                continue
            sub = ElementTree.SubElement(no, vetor)
            for eixo in ("X", "Y", "Z"):
                _sub(sub, eixo, str(valores.get(eixo, 0)))
        escalar = "ViewToWorldScale" if tipo == "OrthogonalCamera" else "FieldOfView"
        if camera.get(escalar) is not None:
            _sub(no, escalar, str(camera[escalar]))
    return raiz
