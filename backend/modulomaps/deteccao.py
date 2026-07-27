# backend/modulomaps/deteccao.py
"""MAP.5 — endereço achado em texto e no XML da NF-e.

A distinção que faz o desenho (planta §7): **no XML da NF-e o endereço já vem
estruturado** (`xLgr`, `nro`, `xBairro`, `cMun`, `UF`, `CEP`). Ali não há
detecção nenhuma — é *parsing*, e o ganho é ligar fornecedor a coordenada de
graça, com uma nota que a empresa já recebeu. O problema difícil é **texto
livre** (contrato, e-mail, mensagem de WhatsApp), e é onde este módulo trabalha.

Ordem de esforço, também da planta: **regex ancorado no CEP** → LLM local →
NER dedicada. Aqui está o primeiro degrau, e ele é o que paga a maior parte:
endereço brasileiro em documento quase sempre traz o CEP, e o CEP é uma âncora
forte (formato rígido, valida contra o ViaCEP, resolve cidade/UF/IBGE sozinho).
O degrau da LLM **não está ligado** — seria código sem exercício, e o motor de
conferência do `funcoesimpexp` já existe justamente para que a extração possa
ser imperfeita: nada entra sem alguém olhar linha a linha.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from nucleo.geo import buscar_por_cep, parse_endereco

# CEP com ou sem hífen, isolado por limites de palavra.
RE_CEP = re.compile(r"\b(\d{5})-?(\d{3})\b")
# "nº 145", "n. 145", ", 145," — número de porta logo após o logradouro.
RE_NUMERO = re.compile(r"(?:n[º°.]?\s*|,\s*)(\d{1,6})(?:\s|,|$)", re.IGNORECASE)
# Palavras que iniciam logradouro no Brasil. A lista existe para o recorte não
# começar no meio de uma frase — sem ela, "…assinado em Rua X" traria "assinado".
RE_LOGRADOURO = re.compile(
    r"\b(rua|r\.|avenida|av\.?|travessa|tv\.?|alameda|al\.?|praça|praca|rodovia|rod\.?|"
    r"estrada|est\.?|via|largo|viela|quadra|q\.?|loteamento|conjunto|servidão|servidao)\b",
    re.IGNORECASE,
)

# Quanto texto em volta do CEP entra na janela de análise. 180 caracteres cobrem
# "logradouro, número, bairro, cidade - UF, CEP" com folga sem invadir a frase
# seguinte do documento.
JANELA = 180


def _janela(texto: str, inicio: int, fim: int) -> str:
    return texto[max(0, inicio - JANELA):min(len(texto), fim + 40)]


def detectar_enderecos(texto: str, limite: int = 50) -> list[dict]:
    """Endereços candidatos num texto livre.

    Cada candidato traz `confianca` e `metodo` — não porque fique bonito, mas
    porque o destino é a conferência linha a linha do `funcoesimpexp`, e o
    operador decide melhor sabendo se aquilo veio de um CEP validado ou de um
    palpite sobre cidade/UF.
    """
    if not texto:
        return []

    achados, vistos = [], set()

    # 1) Âncora forte: CEP. Valida contra o ViaCEP, que devolve o logradouro
    #    oficial — quando bate, a linha praticamente se preenche sozinha.
    for m in RE_CEP.finditer(texto):
        cep = m.group(1) + m.group(2)
        if cep in vistos:
            continue
        vistos.add(cep)
        trecho = _janela(texto, m.start(), m.end())
        via = buscar_por_cep(cep) or {}
        numero = RE_NUMERO.search(trecho)
        candidato = {
            "cep": f"{m.group(1)}-{m.group(2)}",
            "logradouro": via.get("logradouro") or _logradouro_do_trecho(trecho),
            "numero": numero.group(1) if numero else "",
            "bairro": via.get("bairro") or "",
            "cidade": via.get("localidade") or "",
            "uf": via.get("uf") or "",
            "ibge": str(via.get("ibge") or ""),
            "trecho": trecho.strip(),
            "confianca": "alta" if via else "media",
            "metodo": "cep_validado" if via else "cep_formato",
        }
        if not candidato["cidade"]:
            cidade, uf = parse_endereco(trecho)
            candidato["cidade"], candidato["uf"] = cidade or "", uf or ""
        achados.append(candidato)
        if len(achados) >= limite:
            return achados

    # 2) Sem CEP: só vale se houver marcador de logradouro E cidade/UF
    #    reconhecíveis. Duas evidências fracas juntas; uma sozinha vira ruído,
    #    e ruído numa tela de conferência custa mais atenção do que economiza.
    if not achados:
        for m in RE_LOGRADOURO.finditer(texto):
            trecho = texto[m.start():m.start() + JANELA]
            cidade, uf = parse_endereco(trecho)
            if not uf:
                continue
            chave = (trecho[:40], uf)
            if chave in vistos:
                continue
            vistos.add(chave)
            numero = RE_NUMERO.search(trecho)
            achados.append({
                "cep": "",
                "logradouro": _logradouro_do_trecho(trecho),
                "numero": numero.group(1) if numero else "",
                "bairro": "",
                "cidade": cidade or "",
                "uf": uf,
                "ibge": "",
                "trecho": trecho.strip(),
                "confianca": "baixa",
                "metodo": "logradouro_uf",
            })
            if len(achados) >= limite:
                break

    return achados


def _logradouro_do_trecho(trecho: str) -> str:
    """Do marcador de logradouro até o primeiro separador. Melhor-esforço."""
    m = RE_LOGRADOURO.search(trecho)
    if not m:
        return ""
    resto = trecho[m.start():]
    return re.split(r"[,;\n]", resto)[0].strip()[:255]


# ---------------------------------------------------------------------------
# XML da NF-e — aqui é parsing, não detecção
# ---------------------------------------------------------------------------
# O XML da NF-e usa namespace; `local-name()` não existe no ElementTree, então
# comparamos a tag sem o `{ns}` — mais simples que registrar o namespace, e
# imune a versão do layout (o 4.00 mudou o namespace, não os nomes das tags).
def _tag(elemento) -> str:
    return elemento.tag.rsplit("}", 1)[-1]


def _texto(pai, nome: str) -> str:
    for filho in pai:
        if _tag(filho) == nome:
            return (filho.text or "").strip()
    return ""


def endereco_do_xml(xml_bytes, papel: str = "emit") -> dict | None:
    """Endereço do emitente (`emit`) ou do destinatário (`dest`) de uma NF-e.

    `papel="emit"` é o caso que interessa ao Maps: a nota que o **fornecedor**
    emitiu contra a empresa traz o endereço dele já conferido pela SEFAZ —
    endereço melhor que o do cadastro, e de graça.
    """
    try:
        raiz = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None

    alvo_bloco = "enderEmit" if papel == "emit" else "enderDest"
    alvo_pai = "emit" if papel == "emit" else "dest"

    bloco = nome = documento = None
    for elemento in raiz.iter():
        if _tag(elemento) == alvo_pai:
            nome = _texto(elemento, "xNome")
            documento = _texto(elemento, "CNPJ") or _texto(elemento, "CPF")
        if _tag(elemento) == alvo_bloco:
            bloco = elemento
    if bloco is None:
        return None

    cep = re.sub(r"\D", "", _texto(bloco, "CEP"))
    return {
        "nome": nome or "",
        "documento": documento or "",
        "logradouro": _texto(bloco, "xLgr"),
        "numero": _texto(bloco, "nro"),
        "complemento": _texto(bloco, "xCpl"),
        "bairro": _texto(bloco, "xBairro"),
        "cidade": _texto(bloco, "xMun"),
        "uf": _texto(bloco, "UF"),
        "ibge": _texto(bloco, "cMun"),
        "cep": f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else "",
        "confianca": "alta",
        "metodo": "xml_nfe",
    }
