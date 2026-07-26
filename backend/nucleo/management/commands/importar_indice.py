"""Carrega a série mensal de um índice econômico (IPCA, INCC, IGP-M, INPC).

    python manage.py importar_indice --codigo ipca --arquivo ipca.csv
    python manage.py importar_indice --codigo incc --arquivo incc.csv --dry-run

O arquivo é CSV com duas colunas — competência e variação do mês em pontos
percentuais:

    competencia;variacao
    2026-01;0.42
    2026-02;-0.05

Aceita `AAAA-MM` e `MM/AAAA`, e vírgula como separador decimal — os três
formatos em que as séries saem do IBGE e da FGV. **Idempotente:** rodar duas
vezes com o mesmo arquivo não duplica nem soma; a competência é chave.

A série é **dado de plataforma**, não do tenant: um IPCA por empresa seria N
verdades para um número que tem uma só.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nucleo.models import IndiceEconomico, ValorIndice

NOMES = {
    "ipca": ("IPCA", "IBGE"),
    "inpc": ("INPC", "IBGE"),
    "incc": ("INCC", "FGV"),
    "igpm": ("IGP-M", "FGV"),
}


def parse_competencia(bruto: str) -> date:
    """`AAAA-MM`, `AAAA-MM-DD` ou `MM/AAAA` → dia 1 do mês."""
    texto = (bruto or "").strip()
    if "/" in texto:
        mes, ano = texto.split("/")[-2:]
        return date(int(ano), int(mes), 1)
    partes = texto.split("-")
    if len(partes) < 2:
        raise ValueError(f"Competência ilegível: {bruto!r}")
    return date(int(partes[0]), int(partes[1]), 1)


def parse_variacao(bruto: str) -> Decimal:
    texto = (bruto or "").strip().replace("%", "").replace(",", ".")
    if not texto:
        raise ValueError("Variação vazia")
    return Decimal(texto)


class Command(BaseCommand):
    help = "Importa a série mensal de um índice econômico a partir de um CSV."

    def add_arguments(self, parser):
        parser.add_argument("--codigo", required=True, choices=sorted(NOMES))
        parser.add_argument("--arquivo", required=True, help="CSV competência;variação")
        parser.add_argument("--delimitador", default=";")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Confere o arquivo e relata, sem gravar nada.",
        )

    def handle(self, *args, **opts):
        caminho = Path(opts["arquivo"])
        if not caminho.exists():
            raise CommandError(f"Arquivo não encontrado: {caminho}")

        nome, fonte = NOMES[opts["codigo"]]
        linhas, problemas = self._ler(caminho, opts["delimitador"])
        for numero, erro in problemas:
            self.stderr.write(f"  linha {numero}: {erro}")
        if not linhas:
            raise CommandError("Nenhuma linha válida no arquivo.")

        if opts["dry_run"]:
            primeira, ultima = min(linhas), max(linhas)
            self.stdout.write(
                f"[dry-run] {len(linhas)} competências de {primeira:%m/%Y} a {ultima:%m/%Y}"
                f" · {len(problemas)} linha(s) recusada(s). Nada gravado."
            )
            return

        with transaction.atomic():
            indice, _ = IndiceEconomico.objects.update_or_create(
                codigo=opts["codigo"], defaults={"nome": nome, "fonte": fonte},
            )
            criadas = atualizadas = 0
            for competencia, variacao in sorted(linhas.items()):
                _, novo = ValorIndice.objects.update_or_create(
                    indice=indice, competencia=competencia,
                    defaults={"variacao_percentual": variacao},
                )
                criadas += int(novo)
                atualizadas += int(not novo)

        self.stdout.write(self.style.SUCCESS(
            f"{nome}: {criadas} competências criadas, {atualizadas} atualizadas"
            f" ({len(problemas)} recusadas)."
        ))

    def _ler(self, caminho: Path, delimitador: str):
        linhas: dict[date, Decimal] = {}
        problemas: list[tuple[int, str]] = []
        with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
            for numero, campos in enumerate(csv.reader(arquivo, delimiter=delimitador), start=1):
                if not campos or not campos[0].strip():
                    continue
                if len(campos) < 2:
                    problemas.append((numero, "menos de duas colunas"))
                    continue
                try:
                    linhas[parse_competencia(campos[0])] = parse_variacao(campos[1])
                except (ValueError, InvalidOperation, IndexError) as erro:
                    # A primeira linha costuma ser cabeçalho — recusar em
                    # silêncio esconderia um arquivo inteiro mal formatado.
                    if numero > 1:
                        problemas.append((numero, str(erro)))
        return linhas, problemas
