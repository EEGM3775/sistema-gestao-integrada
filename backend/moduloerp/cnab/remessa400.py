"""Remessa de cobrança em CNAB 400 — Bradesco e Itaú.

O 400 não é padrão FEBRABAN: cada banco tem o seu. Estes dois são os que as
carteiras mais antigas ainda usam. Posições no comentário, numeradas de 1.
"""
from __future__ import annotations

from datetime import datetime

from .bancos import banco_de, so_digitos
from .titulo import Titulo, data6, dinheiro, numero, texto

FIM = "\r\n"


def _linha(partes: list[str]) -> str:
    linha = "".join(partes)
    if len(linha) != 400:
        raise ValueError(f"Linha CNAB 400 com {len(linha)} posições.")
    return linha


def gerar(carteira, titulos: list[Titulo], sequencial: int, agora: datetime) -> str:
    banco = banco_de(carteira)
    if banco.codigo == "237":
        return _bradesco(carteira, titulos, sequencial, agora)
    if banco.codigo == "341":
        return _itau(carteira, titulos, agora)
    raise ValueError(f"CNAB 400 do {banco.nome} não está disponível — use CNAB 240.")


def _bradesco(c, titulos, sequencial, agora):
    linhas = [_linha([
        "0", "1", "REMESSA", "01", texto("COBRANCA", 15),       # 1-26
        numero(c.convenio, 20), texto(c.beneficiario_nome, 30), # 27-76
        "237", texto("BRADESCO", 15), data6(agora.date()),      # 77-100
        " " * 8, "MX", f"{sequencial:07d}",                     # 101-117
        " " * 277, "000001",                                    # 118-400
    ])]
    for i, t in enumerate(titulos, start=2):
        pag = t.pagador
        identificacao = "0" + numero(c.carteira, 3) + numero(c.agencia, 5) + numero(c.conta, 7) + (c.conta_dv or "0")[:1]
        linhas.append(_linha([
            "1", "0" * 5, "0", "0" * 5, "0" * 7, "0",               # 1-20: débito automático
            identificacao,                                         # 21-37
            texto(t.boleto_id, 25),                                # 38-62: controle do participante
            "000",                                                 # 63-65
            "2" if t.multa_percentual else "0",                    # 66
            dinheiro(t.multa_percentual, 4),                       # 67-70
            t.nosso_numero.numero, t.nosso_numero.dv,              # 71-82
            "0" * 10, "2", "N", " " * 10, " ", "2", "  ",           # 83-108
            "01", texto(t.seu_numero, 10), data6(t.vencimento),     # 109-126
            dinheiro(t.valor, 13), "000", "00000", "01", "N",       # 127-150
            data6(t.emissao), "00", "00",                           # 151-160
            dinheiro(t.juros_dia, 13), "0" * 6, "0" * 13,           # 161-192
            "0" * 13, "0" * 13,                                     # 193-218
            "02" if pag.tipo == "2" else "01", numero(pag.documento, 14),  # 219-234
            texto(pag.nome, 40), texto(pag.endereco, 40),           # 235-314
            " " * 12, pag.cep[:5], pag.cep[5:8],                    # 315-334
            texto(f"{pag.cidade} {pag.uf}", 60),                    # 335-394
            f"{i:06d}",                                             # 395-400
        ]))
    linhas.append(_linha(["9", " " * 393, f"{len(linhas) + 1:06d}"]))
    return FIM.join(linhas) + FIM


def _itau(c, titulos, agora):
    doc = so_digitos(c.beneficiario_documento)
    agencia, conta, dac = numero(c.agencia, 4), numero(c.conta, 5), (c.conta_dv or "0")[:1]
    linhas = [_linha([
        "0", "1", "REMESSA", "01", texto("COBRANCA", 15),       # 1-26
        agencia, "00", conta, dac, " " * 8,                     # 27-46
        texto(c.beneficiario_nome, 30), "341",                  # 47-79
        texto("BANCO ITAU SA", 15), data6(agora.date()),        # 80-100
        " " * 294, "000001",                                    # 101-400
    ])]
    for i, t in enumerate(titulos, start=2):
        pag = t.pagador
        linhas.append(_linha([
            "1", "02" if len(doc) == 14 else "01", numero(doc, 14), # 1-17
            agencia, "00", conta, dac, " " * 4, "0000",             # 18-37
            texto(t.boleto_id, 25),                                 # 38-62
            t.nosso_numero.numero, "0" * 13,                        # 63-83
            numero(c.carteira, 3), " " * 21, "I",                   # 84-108
            "01", texto(t.seu_numero, 10), data6(t.vencimento),     # 109-126
            dinheiro(t.valor, 13), "341", "00000", "01", "N",       # 127-150
            data6(t.emissao), "00", "00",                           # 151-160
            dinheiro(t.juros_dia, 13), "0" * 6, "0" * 13,           # 161-192
            "0" * 13, "0" * 13,                                     # 193-218
            "02" if pag.tipo == "2" else "01", numero(pag.documento, 14),  # 219-234
            texto(pag.nome, 30), " " * 10,                          # 235-274
            texto(pag.endereco, 40), texto(pag.bairro, 12),         # 275-326
            pag.cep, texto(pag.cidade, 15), texto(pag.uf, 2),       # 327-351
            " " * 30, " " * 4, "000000", "00", " ",                 # 352-394
            f"{i:06d}",                                             # 395-400
        ]))
    linhas.append(_linha(["9", " " * 393, f"{len(linhas) + 1:06d}"]))
    return FIM.join(linhas) + FIM
