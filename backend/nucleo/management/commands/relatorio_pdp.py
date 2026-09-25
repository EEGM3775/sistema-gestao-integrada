"""O que a sombra viu — o critério de saída da fase 2 e a medida da auditoria.

    python manage.py relatorio_pdp            # a janela do critério (payment/planos.py §5.5p)
    python manage.py relatorio_pdp --dias 30

Responde as duas perguntas que a planta deixa para a medida (acesso-e-permissoes.md):

1. **Pode virar?** (§10.12) — quantos dias a sombra esteve ligada, quantas
   comparações fez, quantas descartou por fila cheia, e as divergências por tipo
   e por módulo. Só a `real` conta; o módulo sem nenhuma, numa janela inteira
   com a sombra ligada, cumpriu a fase 2.
2. **Quanto pesa a auditoria?** (§10.9) — o volume de decisões por empresa e por
   dia, que é de onde o dono tira as janelas de retenção de cada plano. O
   tamanho por evento é o do evento de campos fixos da §10.9, medido aqui.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from funcoesautorizacao import chaves
from nucleo import autorizacao_pdp
from nucleo.models import DivergenciaAutorizacao
from payment.planos import AUTORIZACAO_SOMBRA_DIAS_SEM_DIVERGENCIA

#: O evento de decisão da §10.9, com campos fixos e valores de tamanho real —
#: é ele que a fase 4 grava; aqui serve para medir o peso de cada decisão.
EVENTO_TIPICO = {
    "instante": "2026-09-25T14:03:11.482Z",
    "requisicao": "5f0c2b1e9a7d4c3b8e6f1a2b3c4d5e6f",
    "tenant": "0f8fad5b-d9cb-469f-a165-70867728950e",
    "pessoa": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "sid": "3b241101-e2bb-4255-8caf-4136c566a962",
    "acao": "pdca.medicao.atestar",
    "recurso": "modulo_pdca:0f8fad5b-d9cb-469f-a165-70867728950e",
    "decisao": True,
    "classe": "C",
    "origem": "pdp",
    "zedtoken": "GhUKEzE3OTAzNDY4NjMyMTE1NTI5MDI=",
}
BYTES_POR_EVENTO = len(json.dumps(EVENTO_TIPICO, separators=(",", ":")))


def _dias(n: int) -> list[str]:
    hoje = timezone.now().date()
    return [(hoje - timedelta(days=i)).strftime("%Y%m%d") for i in range(n)]


def contadores_do_redis(n: int) -> dict[str, dict]:
    """Por dia: comparações, descartes e o volume por `tenant|pessoa`."""
    r = autorizacao_pdp.redis()
    saida: dict[str, dict] = {}
    if r is None:
        return saida
    for dia in _dias(n):
        saida[dia] = {
            "comparacoes": int(r.get(chaves.comparacoes_do_dia(dia)) or 0),
            "descartes": int(r.get(chaves.descartes_do_dia(dia)) or 0),
            "volume": {k: int(v) for k, v in (r.hgetall(chaves.volume_do_dia(dia)) or {}).items()},
        }
    return saida


def dias_com_sombra(n: int) -> int:
    """Dias da janela em que a sombra comparou alguma coisa e não descartou nada."""
    return sum(
        1 for d in contadores_do_redis(n).values() if d["comparacoes"] and not d["descartes"]
    )


class Command(BaseCommand):
    help = "Relatório da sombra do PDP: critério de saída da fase 2 e volume para a auditoria."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=AUTORIZACAO_SOMBRA_DIAS_SEM_DIVERGENCIA)

    def handle(self, *args, **opts):
        n = opts["dias"]
        desde = timezone.now() - timedelta(days=n)
        div = DivergenciaAutorizacao.objects.filter(criado_em__gte=desde)
        contadores = contadores_do_redis(n)
        com_sombra = sum(1 for d in contadores.values() if d["comparacoes"] and not d["descartes"])

        self.stdout.write(f"Janela: últimos {n} dias · sombra ligada e completa em {com_sombra} dia(s)")
        for dia in sorted(contadores):
            d = contadores[dia]
            self.stdout.write(
                f"  {dia}: {d['comparacoes']} comparações, {d['descartes']} descartadas"
            )

        self.stdout.write("\nDivergências por tipo:")
        for linha in div.values("tipo").annotate(n=Count("id")).order_by("tipo"):
            self.stdout.write(f"  {linha['tipo']:<18} {linha['n']}")

        reais = Counter(div.filter(tipo=DivergenciaAutorizacao.Tipo.REAL).values_list("modulo", flat=True))
        self.stdout.write("\nCritério da fase 2 (zero divergência real com a sombra ligada a janela inteira):")
        vistos = set(div.values_list("modulo", flat=True))
        for modulo in sorted(vistos | {"pdca", "rh", "erp_financeiro", "base", "plataforma"}):
            ok = com_sombra >= n and not reais.get(modulo)
            self.stdout.write(
                f"  {modulo:<16} {'pode virar' if ok else 'ainda não'}"
                f" ({reais.get(modulo, 0)} real(is))"
            )

        por_tenant: dict[str, list[int]] = defaultdict(list)
        pessoas: set[str] = set()
        for d in contadores.values():
            soma: Counter = Counter()
            for chave, qtd in d["volume"].items():
                tenant, _, pessoa = chave.partition("|")
                soma[tenant] += qtd
                pessoas.add(chave)
            for tenant, qtd in soma.items():
                por_tenant[tenant].append(qtd)
        self.stdout.write(
            f"\nVolume de decisões (§10.9) — {BYTES_POR_EVENTO} bytes por evento de campos fixos:"
        )
        for tenant, diario in sorted(por_tenant.items()):
            media = sum(diario) / max(len(diario), 1)
            ano_mb = media * 365 * BYTES_POR_EVENTO / 1_000_000
            self.stdout.write(
                f"  {tenant}: {media:,.0f} decisões/dia em {len(diario)} dia(s) medido(s)"
                f" → ~{ano_mb:,.1f} MB/ano sem compressão"
            )
        if not por_tenant:
            self.stdout.write("  (nenhuma medida ainda — a sombra está ligada?)")
