# backend/funcoesimpexp/formatos/__init__.py
"""Leitores e escritores de arquivo. Nada aqui conhece domínio."""
from .escrita import EscritaIndisponivel, escrever
from .leitura import (
    LeituraInvalida,
    detectar_delimitador,
    ler_bytes,
    mapear_colunas,
    normalizar,
    para_decimal,
)

__all__ = [
    "EscritaIndisponivel",
    "LeituraInvalida",
    "detectar_delimitador",
    "escrever",
    "ler_bytes",
    "mapear_colunas",
    "normalizar",
    "para_decimal",
]
