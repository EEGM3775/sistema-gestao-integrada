# backend/moduloerp/nfe_xml.py
"""Ler o XML de uma NF-e de entrada — o que o fornecedor mandou.

*Pergunta do dono, 10/10/2026:* "como adiciono minhas NF-e sem API?". O XML da
NF-e é o documento fiscal completo e legível por máquina: chave, número, data,
emitente (CNPJ e nome), valor total e as duplicatas (vencimento e valor de cada
parcela). Ler isso é o que dispensa digitar a nota — e o que deixa a conta a
pagar nascer do que a nota diz.

Só a biblioteca padrão, e com o namespace descartado (o mesmo jeito do
`modulomaps.deteccao`): o layout 4.00 da SEFAZ declara `xmlns` em quase todo
nó, e casar caminho com namespace em cada busca deixaria o código ilegível sem
ganho nenhum — a NF-e não mistura vocabulários.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation


class XmlNaoEhNfe(ValueError):
    """O arquivo não é um XML de NF-e que se consiga ler."""


def _sem_namespace(raiz: ET.Element) -> ET.Element:
    for no in raiz.iter():
        if isinstance(no.tag, str) and "}" in no.tag:
            no.tag = no.tag.split("}", 1)[1]
    return raiz


def _texto(no: ET.Element | None, caminho: str) -> str:
    if no is None:
        return ""
    achado = no.find(caminho)
    return (achado.text or "").strip() if achado is not None and achado.text else ""


def _data(valor: str) -> date | None:
    """`2026-10-09T14:03:00-03:00` ou `2026-10-09` → data."""
    if not valor:
        return None
    try:
        return date.fromisoformat(valor[:10])
    except ValueError:
        return None


def _decimal(valor: str) -> Decimal | None:
    try:
        return Decimal(valor) if valor else None
    except InvalidOperation:
        return None


def so_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def ler_nfe(conteudo: bytes) -> dict:
    """Os campos que a nota de entrada e a conta a pagar precisam.

    Levanta `XmlNaoEhNfe` quando não há `infNFe` — é XML, mas não de NF-e (uma
    NFS-e municipal, um CT-e), e gravar metade de um documento que não se
    entendeu seria pior do que recusar com o motivo.
    """
    try:
        raiz = _sem_namespace(ET.fromstring(conteudo))
    except ET.ParseError as erro:
        raise XmlNaoEhNfe(f"O arquivo não é um XML válido ({erro}).") from erro

    inf = raiz if raiz.tag == "infNFe" else raiz.find(".//infNFe")
    if inf is None:
        raise XmlNaoEhNfe("O XML não é de NF-e (não tem o bloco infNFe).")

    chave = so_digitos(inf.get("Id") or "")
    if len(chave) != 44:
        chave = so_digitos(_texto(raiz, ".//protNFe/infProt/chNFe"))
    ide = inf.find("ide")
    emit = inf.find("emit")
    total = inf.find("total/ICMSTot")
    duplicatas = []
    for dup in inf.findall("cobr/dup"):
        vencimento = _data(_texto(dup, "dVenc"))
        valor = _decimal(_texto(dup, "vDup"))
        if vencimento and valor is not None:
            duplicatas.append({"numero": _texto(dup, "nDup"), "vencimento": vencimento, "valor": valor})

    return {
        "chave_acesso": chave,
        "numero": _texto(ide, "nNF"),
        "serie": _texto(ide, "serie"),
        "data_emissao": _data(_texto(ide, "dhEmi") or _texto(ide, "dEmi")),
        "emitente_cnpj": so_digitos(_texto(emit, "CNPJ") or _texto(emit, "CPF")),
        "emitente_nome": _texto(emit, "xNome"),
        "valor_total": _decimal(_texto(total, "vNF")),
        "duplicatas": duplicatas,
    }
