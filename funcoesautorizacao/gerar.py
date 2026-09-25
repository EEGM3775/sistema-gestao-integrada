"""Regera `gerado/` — o schema e o mapa do catálogo da IAM, e os tetos do drone.

    python funcoesautorizacao/gerar.py            # regrava os dois arquivos
    python funcoesautorizacao/gerar.py --conferir # só diz se estão em dia (sai 1 se não)

Roda da raiz do repositório, sem Django: o catálogo é Python puro. Dentro da
imagem da IAM o mesmo trabalho é do teste `identity.test_pdp`, que reprova a
esteira quando o arquivo gravado não é o que o catálogo produz.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def artefatos() -> dict[Path, str]:
    sys.path.insert(0, str(RAIZ))
    sys.path.insert(0, str(RAIZ / "iam"))
    from identity.catalog import CATALOGO

    from funcoesautorizacao import ARQUIVO_CATALOGO, ARQUIVO_ESQUEMA, ARQUIVO_LIMITES_DO_DRONE
    from funcoesautorizacao.classes import classe_do_codigo
    from funcoesautorizacao.esquema import gerar_catalogo, gerar_esquema, gerar_limites_do_drone
    from payment.planos import AUTORIZACAO_PDP_TIMEOUT_MS

    return {
        ARQUIVO_ESQUEMA: gerar_esquema(CATALOGO),
        ARQUIVO_CATALOGO: gerar_catalogo(CATALOGO, classe_do_codigo),
        ARQUIVO_LIMITES_DO_DRONE: gerar_limites_do_drone(AUTORIZACAO_PDP_TIMEOUT_MS),
    }


def main(argv: list[str]) -> int:
    conferir = "--conferir" in argv
    atrasados = []
    for caminho, texto in artefatos().items():
        atual = caminho.read_text(encoding="utf-8") if caminho.exists() else None
        if atual == texto:
            continue
        atrasados.append(caminho.name)
        if not conferir:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_text(texto, encoding="utf-8", newline="\n")
    if conferir and atrasados:
        print("Fora de dia com o catálogo:", ", ".join(atrasados))
        return 1
    print("Regerados:" if atrasados else "Em dia.", ", ".join(atrasados))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
