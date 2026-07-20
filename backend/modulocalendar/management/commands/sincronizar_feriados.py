# backend/modulocalendar/management/commands/sincronizar_feriados.py
"""Sincroniza a tabela de referência de feriados (Fatia F).

- **Federal + estadual:** `python-holidays` (offline, nomes em pt-BR; o estadual é
  o que a subdivisão da UF acrescenta sobre o nacional).
- **Municipal:** dataset MIT `joaopbini/feriados-brasil` (um JSON por ano), baixado
  pela API raw do GitHub; o nome da cidade vem do IBGE (via `nucleo.geo`).

Idempotente: apaga os feriados dos anos pedidos e recarrega. Registra o carimbo
em `FeriadoSync` (a mensagem que o superuser vê). Rodar no boot e agendado.
"""
from datetime import datetime

import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

import holidays

from nucleo import geo
from modulocalendar.models import Feriado, FeriadoSync

# API raw do GitHub — estável mesmo p/ arquivos grandes (o raw.githubusercontent
# se mostrou instável em alguns ambientes). Um JSON por ano.
DATASET_URL = (
    "https://api.github.com/repos/joaopbini/feriados-brasil/contents/"
    "dados/feriados/municipal/json/{ano}.json"
)
DATASET_HEADERS = {"Accept": "application/vnd.github.raw"}
TIMEOUT = (5, 60)


def baixar_municipais(ano):
    """Lista de registros municipais do dataset p/ o ano, ou `[]` em falha."""
    try:
        resp = requests.get(DATASET_URL.format(ano=ano), headers=DATASET_HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError):
        return []


class Command(BaseCommand):
    help = "Sincroniza feriados nacionais/estaduais (python-holidays) e municipais (dataset MIT)."

    def add_arguments(self, parser):
        ano_atual = timezone.now().year
        parser.add_argument(
            "--anos", nargs="+", type=int,
            default=list(range(ano_atual - 1, ano_atual + 3)),
            help="Anos a sincronizar (padrão: ano-1 .. ano+2).",
        )
        parser.add_argument(
            "--sem-municipal", action="store_true",
            help="Pula os municipais (sem acesso ao dataset — só federal/estadual).",
        )

    def handle(self, *args, **options):
        anos = sorted(set(options["anos"]))
        incluir_municipal = not options["sem_municipal"]
        registros = []
        contagem = {"nacional": 0, "estadual": 0, "municipal": 0}
        ibge_nome = {}  # uf -> {ibge_str: nome} (cache local do IBGE)

        def nome_cidade(uf, ibge):
            if uf not in ibge_nome:
                ibge_nome[uf] = {str(m["id"]): m["nome"] for m in geo._municipios_uf(uf)}
            return ibge_nome[uf].get(str(ibge), "")

        for ano in anos:
            nacional = holidays.Brazil(years=ano)
            for data, nome in nacional.items():
                registros.append(Feriado(data=data, nome=nome, escopo="nacional"))
                contagem["nacional"] += 1

            for uf in sorted(geo.UFS):
                estadual = holidays.Brazil(subdiv=uf, years=ano)
                for data, nome in estadual.items():
                    if data in nacional:  # o que a UF acrescenta sobre o nacional
                        continue
                    registros.append(Feriado(data=data, nome=nome, escopo="estadual", uf=uf))
                    contagem["estadual"] += 1

            if incluir_municipal:
                for rec in baixar_municipais(ano):
                    try:
                        data = datetime.strptime(rec["data"], "%d/%m/%Y").date()
                    except (KeyError, ValueError):
                        continue
                    uf = (rec.get("uf") or "").upper()
                    ibge = str(rec.get("codigo_ibge") or "")
                    registros.append(Feriado(
                        data=data,
                        nome=rec.get("nome") or rec.get("descricao") or "Feriado Municipal",
                        escopo="municipal", uf=uf, ibge=ibge,
                        cidade=nome_cidade(uf, ibge) if uf and ibge else "",
                    ))
                    contagem["municipal"] += 1

        with transaction.atomic():
            Feriado.objects.filter(data__year__in=anos).delete()
            Feriado.objects.bulk_create(registros, batch_size=2000, ignore_conflicts=True)
            sync, _ = FeriadoSync.objects.get_or_create(pk=1)
            sync.anos = ", ".join(str(a) for a in anos)
            sync.total = len(registros)
            sync.detalhes = contagem
            sync.save()

        self.stdout.write(self.style.SUCCESS(
            f"Feriados sincronizados ({sync.anos}): "
            f"{contagem['nacional']} nacionais, {contagem['estadual']} estaduais, "
            f"{contagem['municipal']} municipais."
        ))
