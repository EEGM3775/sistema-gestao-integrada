# backend/modulocalendar/management/commands/sincronizar_feriados.py
"""Sincroniza a tabela de referência de feriados (Fatia F).

- **Federal + estadual:** `python-holidays` (offline, nomes em pt-BR; o estadual é
  o que a subdivisão da UF acrescenta sobre o nacional). Cobre **toda a faixa do
  calendário, de 1900 a 2100** (`CALENDARIO_ANO_*` do `planos.py` — decisão do
  dono, 01/10/2026): a biblioteca aplica a lei de cada época, então 1900 tem o
  "Descobrimento do Brasil" e não tem 1º de maio. Antes a sincronização cobria
  só ano-1..ano+2, e o boleto de uma parcela de 2030 saiu num 1º de janeiro.
- **Municipal:** dataset MIT `joaopbini/feriados-brasil` (um JSON por ano), baixado
  pela API raw do GitHub; o nome da cidade vem do IBGE (via `nucleo.geo`). O
  dataset só publica alguns anos; fora deles, o vencimento projeta o feriado
  municipal pela regra (`modulocalendar.feriados`), sem gravar linha inventada.

Idempotente: apaga os feriados dos anos pedidos e recarrega. **O municipal de um
ano só é trocado se o download daquele ano trouxe alguma coisa** — rede fora do
ar não pode apagar o que já estava certo. Registra o carimbo em `FeriadoSync` (a
mensagem que o superuser vê). Rodar no boot e agendado.
"""
from datetime import datetime

import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

import holidays

from nucleo import geo
from modulocalendar.models import Feriado, FeriadoSync
from payment.planos import CALENDARIO_ANO_FINAL, CALENDARIO_ANO_INICIAL

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


def feriados_de_lei(anos):
    """`[Feriado]` nacionais e estaduais dos anos — sem rede, uma chamada por UF."""
    registros = []
    nacional = holidays.Brazil(years=anos)
    for data, nome in nacional.items():
        registros.append(Feriado(data=data, nome=nome, escopo="nacional"))
    for uf in sorted(geo.UFS):
        for data, nome in holidays.Brazil(subdiv=uf, years=anos).items():
            if data in nacional:  # o que a UF acrescenta sobre o nacional
                continue
            registros.append(Feriado(data=data, nome=nome, escopo="estadual", uf=uf))
    return registros


class Command(BaseCommand):
    help = (
        "Sincroniza feriados nacionais/estaduais (python-holidays, 1900–2100) "
        "e municipais (dataset MIT, anos publicados)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--anos", nargs="+", type=int, default=None,
            help=(
                "Restringe a sincronização a estes anos (nacional, estadual e municipal). "
                f"Sem ele: nacional/estadual de {CALENDARIO_ANO_INICIAL} a {CALENDARIO_ANO_FINAL} "
                "e municipal de ano-1 a ano+2."
            ),
        )
        parser.add_argument(
            "--anos-municipais", nargs="+", type=int, default=None,
            help="Anos do dataset municipal a baixar (padrão: ano-1 .. ano+2).",
        )
        parser.add_argument(
            "--sem-municipal", action="store_true",
            help="Pula os municipais (sem acesso ao dataset — só federal/estadual).",
        )

    def handle(self, *args, **options):
        ano_atual = timezone.now().year
        if options["anos"]:
            anos_lei = sorted(set(options["anos"]))
            anos_mun = anos_lei
        else:
            anos_lei = list(range(CALENDARIO_ANO_INICIAL, CALENDARIO_ANO_FINAL + 1))
            anos_mun = list(range(ano_atual - 1, ano_atual + 3))
        if options["anos_municipais"]:
            anos_mun = sorted(set(options["anos_municipais"]))
        if options["sem_municipal"]:
            anos_mun = []

        registros = feriados_de_lei(anos_lei)
        contagem = {
            "nacional": sum(1 for r in registros if r.escopo == "nacional"),
            "estadual": sum(1 for r in registros if r.escopo == "estadual"),
            "municipal": 0,
        }
        ibge_nome = {}  # uf -> {ibge_str: nome} (cache local do IBGE)

        def nome_cidade(uf, ibge):
            if uf not in ibge_nome:
                ibge_nome[uf] = {str(m["id"]): m["nome"] for m in geo._municipios_uf(uf)}
            return ibge_nome[uf].get(str(ibge), "")

        anos_mun_baixados = []
        for ano in anos_mun:
            lidos = 0
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
                lidos += 1
            if lidos:
                anos_mun_baixados.append(ano)
                contagem["municipal"] += lidos

        with transaction.atomic():
            Feriado.objects.filter(escopo__in=("nacional", "estadual"), data__year__in=anos_lei).delete()
            if anos_mun_baixados:
                Feriado.objects.filter(escopo="municipal", data__year__in=anos_mun_baixados).delete()
            Feriado.objects.bulk_create(registros, batch_size=2000, ignore_conflicts=True)
            sync, _ = FeriadoSync.objects.get_or_create(pk=1)
            sync.anos = _faixa(anos_lei)
            sync.total = len(registros)
            sync.detalhes = contagem | {"anos_municipais": anos_mun_baixados}
            sync.save()

        self.stdout.write(self.style.SUCCESS(
            f"Feriados sincronizados ({sync.anos}): "
            f"{contagem['nacional']} nacionais, {contagem['estadual']} estaduais, "
            f"{contagem['municipal']} municipais"
            f"{' (' + ', '.join(map(str, anos_mun_baixados)) + ')' if anos_mun_baixados else ''}."
        ))


def _faixa(anos):
    """`1900–2100` para a faixa contínua; a lista, se não for (o campo tem 100 posições)."""
    if len(anos) > 2 and anos == list(range(anos[0], anos[-1] + 1)):
        return f"{anos[0]}–{anos[-1]}"
    return ", ".join(str(a) for a in anos)[:100]
