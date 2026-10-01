"""O código de barras e a linha digitável do boleto — padrão FEBRABAN.

Os 44 dígitos são iguais em todo banco:

    banco(3) · moeda(1) · DV(1) · fator de vencimento(4) · valor(10) · campo livre(25)

Só o campo livre é do banco (`bancos.py`). O DV geral é módulo 11, e os três
primeiros campos da linha digitável têm DV módulo 10.

**O fator de vencimento reiniciou em 22/02/2025.** Ele conta dias desde
07/10/1997 em quatro dígitos e chegou a 9999 em 21/02/2025; desde então volta a
1000 e segue (FEBRABAN, Carta-Circular 2024). Quem calcula sem isso gera boleto
que o caixa lê como vencido há 27 anos.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

DATA_BASE = date(1997, 10, 7)
MOEDA_REAL = "9"


def modulo10(numero: str) -> int:
    soma = 0
    peso = 2
    for digito in reversed(numero):
        produto = int(digito) * peso
        soma += produto // 10 + produto % 10
        peso = 1 if peso == 2 else 2
    return (10 - soma % 10) % 10


def soma_modulo11(numero: str, peso_maximo: int = 9) -> int:
    soma = 0
    peso = 2
    for digito in reversed(numero):
        soma += int(digito) * peso
        peso = 2 if peso == peso_maximo else peso + 1
    return soma


def modulo11(numero: str, peso_maximo: int = 9) -> int:
    """DV módulo 11 "comum": 11 - resto, e 10/11 viram 0."""
    dv = 11 - soma_modulo11(numero, peso_maximo) % 11
    return 0 if dv > 9 else dv


def dv_codigo_barras(sem_dv: str) -> int:
    """O DV geral: 11 - resto, e 0, 10 e 11 viram 1 (nunca zero)."""
    dv = 11 - soma_modulo11(sem_dv) % 11
    return 1 if dv in (0, 10, 11) else dv


def fator_vencimento(vencimento: date) -> str:
    dias = (vencimento - DATA_BASE).days
    if dias > 9999:
        dias = (dias - 10000) % 9000 + 1000
    return f"{dias:04d}"


def valor_em_centavos(valor: Decimal, largura: int = 10) -> str:
    centavos = int((Decimal(valor) * 100).quantize(Decimal("1")))
    texto = f"{centavos:0{largura}d}"
    if len(texto) > largura:
        raise ValueError("Valor grande demais para o boleto.")
    return texto


def montar(banco: str, vencimento: date, valor: Decimal, campo_livre: str) -> str:
    if len(campo_livre) != 25 or not campo_livre.isdigit():
        raise ValueError(f"Campo livre precisa de 25 dígitos (veio {len(campo_livre)}).")
    sem_dv = f"{banco}{MOEDA_REAL}{fator_vencimento(vencimento)}{valor_em_centavos(valor)}{campo_livre}"
    dv = dv_codigo_barras(sem_dv)
    return sem_dv[:4] + str(dv) + sem_dv[4:]


def linha_digitavel(codigo: str) -> str:
    """A linha que o pagador digita, com os pontos e espaços do padrão."""
    if len(codigo) != 44:
        raise ValueError("O código de barras tem 44 dígitos.")
    livre = codigo[19:44]
    c1 = codigo[0:4] + livre[0:5]
    c2 = livre[5:15]
    c3 = livre[15:25]
    c1 += str(modulo10(c1))
    c2 += str(modulo10(c2))
    c3 += str(modulo10(c3))
    c4 = codigo[4]
    c5 = codigo[5:19]
    return f"{c1[:5]}.{c1[5:]} {c2[:5]}.{c2[5:]} {c3[:5]}.{c3[5:]} {c4} {c5}"


def de_linha_digitavel(linha: str) -> str:
    """O caminho de volta — para conferir o que o pagador digitou."""
    d = "".join(ch for ch in linha if ch.isdigit())
    if len(d) != 47:
        raise ValueError("A linha digitável tem 47 dígitos.")
    return d[0:4] + d[32] + d[33:47] + d[4:9] + d[10:20] + d[21:31]
