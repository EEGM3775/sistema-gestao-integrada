"""Autorização da plataforma — a parte comum à IAM e ao backend.

Remodelagem da segurança, fases 2 e 3 (docs/acesso-e-permissoes.md §10.12): o
"pode?" passa a ter uma resposta fora do token, no PDP (SpiceDB). Este pacote
guarda o que os dois serviços precisam dizer **do mesmo jeito**: o cliente do
PDP, o schema gerado do catálogo, a classe de cada ação e o formato das chaves de
cache. Quem decide continua sendo cada serviço (`nucleo/autorizacao.py` no
backend); quem escreve relação é só a IAM (`identity/pdp.py`).

Vive na raiz pelo mesmo motivo do `funcoesemail/` e do `payment/`: IAM e backend
são imagens separadas, e as duas copiam esta pasta.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

GERADO = Path(__file__).resolve().parent / "gerado"
ARQUIVO_ESQUEMA = GERADO / "esquema.zed"
ARQUIVO_CATALOGO = GERADO / "catalogo.json"
#: Os tetos do `payment/planos.py` que o PEP do drone (Java) precisa — ele não
#: importa Python, e o número não pode ter uma segunda casa (CLAUDE.md).
ARQUIVO_LIMITES_DO_DRONE = GERADO / "limites-drone.properties"


@lru_cache(maxsize=1)
def catalogo() -> dict:
    """O catálogo como o backend o enxerga: código → módulo e classe."""
    return json.loads(ARQUIVO_CATALOGO.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def texto_do_esquema() -> str:
    return ARQUIVO_ESQUEMA.read_text(encoding="utf-8")
