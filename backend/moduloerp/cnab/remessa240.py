"""Remessa de cobrança em CNAB 240 — o layout FEBRABAN.

Um arquivo = header de arquivo, um lote (header, segmentos P/Q/R de cada
título, trailer) e trailer de arquivo. Toda linha tem 240 posições; a posição
de cada campo está no comentário, na numeração do manual (começando em 1).
O que é de cada banco vem de `bancos.py`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .bancos import banco_de, so_digitos
from .titulo import Titulo, data8, dinheiro, numero, texto

FIM = "\r\n"


def _dia_seguinte(d: date) -> date:
    """Juros e multa contam **depois** do vencimento: o banco recusa a data de
    juros (P 119-126) ou de multa (R 67-74) igual à do vencimento."""
    return d + timedelta(days=1)


def _linha(partes: list[str]) -> str:
    linha = "".join(partes)
    if len(linha) != 240:
        raise ValueError(f"Linha CNAB 240 com {len(linha)} posições.")
    return linha


def gerar(carteira, titulos: list[Titulo], sequencial: int, agora: datetime) -> str:
    banco = banco_de(carteira)
    b = banco.codigo
    doc = so_digitos(carteira.beneficiario_documento)
    tipo_insc = "2" if len(doc) == 14 else "1"
    conta = banco.conta_240(carteira)          # 20 posições: agência..DV ag/conta
    convenio = banco.convenio_240(carteira)    # 20 posições

    linhas = [_linha([
        b, "0000", "0", " " * 9,                          # 1-17
        tipo_insc, numero(doc, 14),                       # 18-32
        convenio,                                         # 33-52
        banco.conta_header_arquivo_240(carteira),         # 53-72
        texto(carteira.beneficiario_nome, 30),            # 73-102
        texto(banco.nome, 30),                            # 103-132
        " " * 10,                                         # 133-142
        "1", agora.strftime("%d%m%Y"), agora.strftime("%H%M%S"),  # 143-157
        f"{sequencial:06d}", banco.versao_arquivo_240, "00000",   # 158-171
        " " * 20, " " * 20, " " * 29,                     # 172-240
    ])]

    linhas.append(_linha([
        b, "0001", "1", "R", "01", banco.reservado_lote_240, banco.versao_lote_240, " ",   # 1-17
        tipo_insc, numero(doc, 15),                                   # 18-33
        banco.convenio_lote_240(carteira),                            # 34-53
        conta,                                                        # 54-73
        texto(carteira.beneficiario_nome, 30),                        # 74-103
        " " * 40, " " * 40,                                           # 104-183
        f"{sequencial:08d}", agora.strftime("%d%m%Y"), "0" * 8,       # 184-207
        " " * 33,                                                     # 208-240
    ]))

    registro = 0
    valor_total = 0
    for t in titulos:
        pag = t.pagador
        for segmento in ("P", "Q", "R"):
            registro += 1
            comum = [b, "0001", "3", f"{registro:05d}", segmento, " ", "01"]   # 1-17
            if segmento == "P":
                corpo = [
                    conta,                                   # 18-37 (20)
                    banco.identificacao_240(carteira, t.nosso_numero),  # 38-57
                    "1", banco.cadastro_e_documento_240,     # 58-60: carteira, cadastro, documento
                    "2", "2",                                # 61-62: emissão e distribuição pelo cliente
                    texto(t.seu_numero, 15),                 # 63-77
                    data8(t.vencimento),                     # 78-85
                    dinheiro(t.valor, 15),                   # 86-100
                    "00000", " ",                            # 101-106: agência cobradora e DV (do banco)
                    "02", "N",                               # 107-109: espécie DM, aceite
                    data8(t.emissao),                        # 110-117
                    "1" if t.juros_dia else "3",             # 118: juros por dia / isento
                    data8(_dia_seguinte(t.vencimento)) if t.juros_dia else "0" * 8,  # 119-126
                    dinheiro(t.juros_dia, 15),               # 127-141
                    "0", "0" * 8, "0" * 15,                  # 142-165: desconto
                    "0" * 15, "0" * 15,                      # 166-195: IOF, abatimento
                    texto(t.boleto_id, 25),                  # 196-220: uso da empresa
                    "3", "00",                               # 221-223: não protestar
                    "0", "   ",                              # 224-227: baixa (dias em branco)
                    "09", "0" * 10, " ",                     # 228-240
                ]
                valor_total += t.valor
            elif segmento == "Q":
                corpo = [
                    pag.tipo, numero(pag.documento, 15),     # 18-33
                    texto(pag.nome, 40),                     # 34-73
                    texto(pag.endereco, 40),                 # 74-113
                    texto(pag.bairro, 15),                   # 114-128
                    pag.cep[:5], pag.cep[5:8],               # 129-136
                    texto(pag.cidade, 15), texto(pag.uf, 2), # 137-153
                    "0", "0" * 15, " " * 40,                 # 154-209: sacador/avalista
                    "000", " " * 20, " " * 8,                # 210-240
                ]
            else:
                multa = t.multa_percentual
                corpo = [
                    "0", "0" * 8, "0" * 15,                  # 18-41: desconto 2
                    "0", "0" * 8, "0" * 15,                  # 42-65: desconto 3
                    "2" if multa else "0",                   # 66: multa percentual
                    data8(_dia_seguinte(t.vencimento)) if multa else "0" * 8,   # 67-74
                    dinheiro(multa, 15),                     # 75-89
                    " " * 10, " " * 40, " " * 40,            # 90-179
                    " " * 20, "0" * 8,                       # 180-207
                    "000", "00000", " ", "0" * 12, " ", " ", "0",  # 208-231
                    " " * 9,                                 # 232-240
                ]
            linhas.append(_linha(comum + corpo))

    qtd_titulos = len(titulos)
    linhas.append(_linha([
        b, "0001", "5", " " * 9,                             # 1-17
        f"{registro + 2:06d}",                               # 18-23: registros do lote
        f"{qtd_titulos:06d}", dinheiro(valor_total, 17),     # 24-46: cobrança simples
        "0" * 6, "0" * 17, "0" * 6, "0" * 17, "0" * 6, "0" * 17,  # 47-115
        " " * 8, " " * 117,                                  # 116-240
    ]))
    linhas.append(_linha([
        b, "9999", "9", " " * 9,                             # 1-17
        "000001", f"{len(linhas) + 1:06d}", "000000",        # 18-35
        " " * 205,                                           # 36-240
    ]))
    return FIM.join(linhas) + FIM
