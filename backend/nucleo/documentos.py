"""CPF e CNPJ: validação e geração determinística para demonstração.

Existe porque **documento aleatório não passa no gateway**. O Asaas — mesmo em
sandbox — valida o dígito verificador ao criar o cliente da cobrança, então uma
base semeada com `9000000001` gera uma carteira inteira que parece certa na tela
e não emite um boleto sequer. Os números daqui são sintéticos, mas **válidos**:
passam no cálculo do módulo 11, que é o que o gateway confere.

Sintético não é o mesmo que livre: um CPF válido pode pertencer a uma pessoa
real. Estes são gerados a partir de uma base fixa e de um índice sequencial, o
que os torna reprodutíveis e concentrados numa faixa previsível — para
demonstração e teste, nunca para preencher cadastro de gente de verdade.
"""
from __future__ import annotations


def _digito(numeros: list[int], pesos: list[int]) -> int:
    soma = sum(n * p for n, p in zip(numeros, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def digitos(valor: str) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


# ─── CPF ──────────────────────────────────────────────────────────────────────

def cpf_valido(valor: str) -> bool:
    numero = digitos(valor)
    if len(numero) != 11 or len(set(numero)) == 1:
        return False
    base = [int(c) for c in numero[:9]]
    d1 = _digito(base, list(range(10, 1, -1)))
    d2 = _digito(base + [d1], list(range(11, 1, -1)))
    return numero[9:] == f"{d1}{d2}"


def gerar_cpf(indice: int) -> str:
    """CPF válido e reprodutível a partir de um índice (0 → o primeiro da série)."""
    base = [int(c) for c in f"{100_000_000 + indice % 800_000_000:09d}"]
    d1 = _digito(base, list(range(10, 1, -1)))
    d2 = _digito(base + [d1], list(range(11, 1, -1)))
    return "".join(str(n) for n in base) + f"{d1}{d2}"


# ─── CNPJ ─────────────────────────────────────────────────────────────────────

_PESOS_CNPJ = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def cnpj_valido(valor: str) -> bool:
    numero = digitos(valor)
    if len(numero) != 14 or len(set(numero)) == 1:
        return False
    base = [int(c) for c in numero[:12]]
    d1 = _digito(base, _PESOS_CNPJ)
    d2 = _digito(base + [d1], [6] + _PESOS_CNPJ)
    return numero[12:] == f"{d1}{d2}"


def gerar_cnpj(indice: int, filial: int = 1) -> str:
    """CNPJ válido e reprodutível. `filial` vira a ordem (0001, 0002…)."""
    raiz = f"{10_000_000 + indice % 80_000_000:08d}"
    base = [int(c) for c in raiz + f"{filial:04d}"]
    d1 = _digito(base, _PESOS_CNPJ)
    d2 = _digito(base + [d1], [6] + _PESOS_CNPJ)
    return "".join(str(n) for n in base) + f"{d1}{d2}"
