# backend/moduloorcamento/management/commands/importar_indices.py
"""Importa a série de um índice econômico (INCC-M, IPCA, IGP-M, CUB).

Irmão do `importar_base_referencial`, e pelo mesmo motivo: `IndiceEconomico` e
`ValorIndice` são tabelas **de plataforma** (§11.1) — dado público de terceiro,
gravado só por comando, read-only na API. Quem opera a plataforma alimenta; o
tenant lê.

    manage.py importar_indices --codigo INCC-M --nome "INCC-M (FGV)" \\
        --fonte FGV serie.csv

O arquivo precisa de duas colunas: competência e número-índice. A variação é
opcional — quando ausente, é **calculada** a partir da série, que é mais
confiável que a publicada (a imprensa arredonda em duas casas).

**Idempotente:** reimportar atualiza o valor da competência em vez de duplicar,
porque índice é revisado — a FGV publica prévia e depois fecha o mês, e o
comando precisa aceitar o fechamento por cima da prévia.
"""
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from moduloorcamento.models import IndiceEconomico, ValorIndice

# Sinônimos de cabeçalho — arquivos oficiais mudam de rótulo entre publicações,
# e exigir um layout exato faria o comando falhar por causa de um acento.
_ALIAS_COMPETENCIA = {"competencia", "competência", "mes", "mês", "data", "periodo", "período"}
_ALIAS_NUMERO = {"numero_indice", "número-índice", "numero", "indice", "índice", "valor", "n_indice"}
_ALIAS_VARIACAO = {"variacao", "variação", "var", "variacao_percentual", "variação (%)", "%"}


def _decimal(bruto: str) -> Decimal | None:
    """Número brasileiro: `1.234,56` vira `1234.56`."""
    texto = (bruto or "").strip()
    if not texto:
        return None
    texto = texto.replace(".", "").replace(",", ".") if "," in texto else texto
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def _competencia(bruto: str):
    """Aceita `2026-07-01`, `2026-07`, `07/2026`. Sempre normaliza para o dia 1º."""
    from datetime import date

    texto = (bruto or "").strip()
    if not texto:
        return None
    if "/" in texto:
        partes = texto.split("/")
        if len(partes) == 2:
            mes, ano = partes
            return date(int(ano), int(mes), 1)
        dia, mes, ano = partes
        return date(int(ano), int(mes), 1)
    partes = texto.split("-")
    if len(partes) == 2:
        return date(int(partes[0]), int(partes[1]), 1)
    return date(int(partes[0]), int(partes[1]), 1)


class Command(BaseCommand):
    help = "Importa a série de um índice econômico a partir de CSV/XLSX."

    def add_arguments(self, parser):
        parser.add_argument("arquivo")
        parser.add_argument("--codigo", required=True, help="INCC-M, IPCA, IGP-M, CUB-SP…")
        parser.add_argument("--nome", default="", help="Nome de exibição; usa o código se ausente.")
        parser.add_argument("--fonte", default="", help="FGV, IBGE, Sinduscon/SP…")
        parser.add_argument("--uf", default="", help="Só para índice regional (CUB).")
        parser.add_argument("--dry-run", action="store_true", help="Lê e relata sem gravar.")

    def handle(self, *args, **opcoes):
        linhas = self._ler(opcoes["arquivo"])
        if not linhas:
            raise CommandError("Nenhuma linha legível no arquivo.")

        codigo = opcoes["codigo"].strip().upper()
        pontos = []
        for numero_linha, linha in enumerate(linhas, start=2):
            competencia = _competencia(linha.get("competencia", ""))
            numero = _decimal(linha.get("numero", ""))
            if competencia is None or numero is None:
                self.stderr.write(f"  linha {numero_linha}: competência ou número-índice ilegível — pulada")
                continue
            pontos.append((competencia, numero, _decimal(linha.get("variacao", ""))))

        if not pontos:
            raise CommandError("Nenhum ponto de série válido — confira as colunas do arquivo.")
        pontos.sort(key=lambda p: p[0])

        if opcoes["dry_run"]:
            self.stdout.write(
                f"[dry-run] {codigo}: {len(pontos)} pontos, de "
                f"{pontos[0][0]:%m/%Y} a {pontos[-1][0]:%m/%Y}."
            )
            return

        with transaction.atomic():
            indice, criado = IndiceEconomico.objects.update_or_create(
                codigo=codigo,
                defaults={
                    "nome": opcoes["nome"] or codigo,
                    "fonte": opcoes["fonte"],
                    "uf": opcoes["uf"].upper()[:2],
                    "ativo": True,
                },
            )
            gravados = 0
            anterior = None
            for competencia, numero, variacao in pontos:
                # Variação ausente vira calculada a partir do ponto anterior da
                # própria série — mais fiel que a publicada, que vem arredondada.
                if variacao is None and anterior is not None and anterior != 0:
                    variacao = ((numero / anterior - 1) * 100).quantize(Decimal("0.0001"))
                ValorIndice.objects.update_or_create(
                    indice=indice, competencia=competencia,
                    defaults={"numero_indice": numero, "variacao_percentual": variacao},
                )
                anterior = numero
                gravados += 1

        self.stdout.write(self.style.SUCCESS(
            f"{'Criado' if criado else 'Atualizado'} {codigo}: {gravados} competências "
            f"({pontos[0][0]:%m/%Y}–{pontos[-1][0]:%m/%Y})."
        ))

    # -- leitura -----------------------------------------------------------

    def _ler(self, caminho: str) -> list[dict]:
        if caminho.lower().endswith((".xlsx", ".xlsm")):
            return self._ler_xlsx(caminho)
        return self._ler_csv(caminho)

    def _ler_csv(self, caminho: str) -> list[dict]:
        import csv

        # `;` fixo por preferência, não por detecção: o `csv.Sniffer` elege a
        # **vírgula decimal** como separador em arquivo brasileiro e parte a
        # coluna de valor em duas sem erro nenhum. É a mesma armadilha já
        # registrada no `importar_base_referencial`.
        with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
            amostra = arquivo.readline()
            arquivo.seek(0)
            delimitador = ";" if ";" in amostra else ","
            return self._mapear(list(csv.reader(arquivo, delimiter=delimitador)))

    def _ler_xlsx(self, caminho: str) -> list[dict]:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise CommandError("openpyxl não instalado — necessário para ler XLSX.") from exc

        planilha = load_workbook(caminho, read_only=True, data_only=True).active
        return self._mapear([
            ["" if c is None else str(c) for c in linha]
            for linha in planilha.iter_rows(values_only=True)
        ])

    def _mapear(self, linhas: list[list]) -> list[dict]:
        if not linhas:
            return []
        cabecalho = [str(c or "").strip().lower() for c in linhas[0]]
        indices = {}
        for posicao, rotulo in enumerate(cabecalho):
            if rotulo in _ALIAS_COMPETENCIA:
                indices["competencia"] = posicao
            elif rotulo in _ALIAS_NUMERO:
                indices["numero"] = posicao
            elif rotulo in _ALIAS_VARIACAO:
                indices["variacao"] = posicao

        if "competencia" not in indices or "numero" not in indices:
            raise CommandError(
                "Não achei as colunas de competência e número-índice. "
                f"Cabeçalho lido: {cabecalho}"
            )

        return [
            {chave: str(linha[posicao]) if posicao < len(linha) else ""
             for chave, posicao in indices.items()}
            for linha in linhas[1:] if any(str(c).strip() for c in linha)
        ]
