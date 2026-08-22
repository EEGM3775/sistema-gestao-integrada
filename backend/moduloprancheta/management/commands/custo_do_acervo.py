# backend/moduloprancheta/management/commands/custo_do_acervo.py
"""Quanto de máquina custou **cada arquivo** de um acervo já convertido.

**O irmão de produção do [`medir_cobertura_dwg`](medir_cobertura_dwg.py), e a
diferença entre os dois é a pergunta.** Aquele é bancada: aponta-se para uma
pasta, ele roda o motor e não grava nada — serve para decidir preço antes de o
cliente existir. Este lê o que **já aconteceu** no caminho real: o acervo que
subiu pela tela, convertido pelo worker, com o custo que o pipeline gravou em
`DerivadaProjeto.memoria["custo"]`. Nenhum arquivo é reprocessado.

    manage.py custo_do_acervo --obra 12
    manage.py custo_do_acervo --obra 12 --tenant demo --limite 20 --csv custo.csv

**Toda coluna aqui é por arquivo, e nenhuma é acumulada.** É a correção que o
[D82](../../../../docs/historico-correcoes.md) pede pelo nome: o instrumento
anterior lia `getrusage(RUSAGE_CHILDREN).ru_maxrss`, que é marca d'água de todos
os filhos que o processo já teve — o segundo arquivo herdava o pico do primeiro,
e a soma estourava a conta. Um worker Celery de vida longa faz isso pior que
qualquer bancada: ele converte centenas de arquivos no mesmo processo.

O que se lê em cada coluna:

| Coluna | Grandeza | Cuidado |
|---|---|---|
| `entrada` | o DWG/IFC em disco | — |
| `filho` | pico de RSS **do subprocesso**, do `VmHWM` dele | `n/d` = não medido, e nunca 0 |
| `em proc.` | pico de VA **da janela** desta conversão, menos a base | é a grandeza que o `RLIMIT_AS` governa |
| `cpu` | CPU de verdade (pai + filhos), por diferença | tempo acumulado **pode** ser subtraído; marca d'água não |
| `tempo` | relógio de parede | inclui espera de I/O |
| `MB/MB` | pico sobre peso de entrada | quanto mais disperso, menos o tamanho prevê o custo |
"""
from __future__ import annotations

import csv
import sys

from django.core.management.base import BaseCommand, CommandError

from nucleo.models import Tenant
from nucleo.tenancy import tenant_context

from moduloprancheta.models import DerivadaProjeto


def _mb(valor) -> str:
    """`None` vira `n/d`. Zero aqui se leria como 'não custou nada' — a lição do D82."""
    return "n/d" if valor is None else f"{valor}M"


class Command(BaseCommand):
    help = "Custo de máquina por arquivo de um acervo já convertido (PRA.5c)."

    def add_arguments(self, parser):
        parser.add_argument("--obra", type=int, required=True)
        parser.add_argument("--tenant", default="demo", help="slug do tenant")
        parser.add_argument("--limite", type=int, default=0,
                            help="mostra só os N mais caros (0 = todos)")
        parser.add_argument("--csv", default="", help="grava a tabela inteira aqui")

    def handle(self, *_args, **opcoes):
        try:
            tenant = Tenant.objects.get(slug=opcoes["tenant"])
        except Tenant.DoesNotExist:
            raise CommandError(f"Tenant '{opcoes['tenant']}' não existe.")

        with tenant_context(tenant.pk):
            linhas = self._coletar(opcoes["obra"])

        if not linhas:
            raise CommandError(
                f"Nenhuma derivada com custo na obra {opcoes['obra']}. "
                "Conversões anteriores ao D82 não gravaram a coluna."
            )
        self._imprimir(linhas, opcoes["limite"])
        if opcoes["csv"]:
            self._csv(linhas, opcoes["csv"])

    # ------------------------------------------------------------------
    def _coletar(self, obra: int) -> list[dict]:
        """Uma linha por CONVERSÃO — e a conversão é do arquivo, não da folha.

        O filtro por `custo` presente é o que separa a folha #1 (que carrega o
        custo da passada inteira) das outras folhas do mesmo arquivo, que nascem
        da mesma leitura e não têm custo próprio. Sem ele, um DWG multifolha
        entraria N vezes e a soma multiplicaria a conta pelo número de folhas.
        """
        consulta = (
            DerivadaProjeto.objects
            .filter(revisao__documento__obra_id=obra)
            .select_related("revisao", "revisao__documento")
            .order_by("pk")
        )
        linhas = []
        for derivada in consulta:
            custo = (derivada.memoria or {}).get("custo")
            if not custo:
                continue
            entrada_mb = (derivada.revisao.tamanho_bytes or 0) / 1048576
            # **`None` quando nada mediu — e não 0** (D84). O `memory.peak` do
            # cgroup vem primeiro porque conta pai e subprocesso no MESMO
            # instante; o maior das duas colunas de amostragem é piso, e piso de
            # metades tomadas em separado não é o pico da operação.
            exato = custo.get("pico_cgroup_mb")
            if exato is not None:
                pico = exato
            else:
                amostrados = [
                    v for v in (custo.get("pico_va_mb"), custo.get("pico_filho_mb")) if v
                ]
                pico = max(amostrados) if amostrados else None
            linhas.append({
                "arquivo": derivada.revisao.nome_original,
                "codigo": derivada.revisao.documento.codigo,
                "tipo": derivada.tipo,
                "motor": derivada.motor,
                "estado": derivada.estado,
                "motivo": derivada.erro_motivo,
                "entrada_mb": entrada_mb,
                "filho_mb": custo.get("pico_filho_mb"),
                "va_mb": custo.get("pico_va_mb") or 0,
                "rss_mb": custo.get("pico_rss_mb") or 0,
                "cpu_s": custo.get("cpu_s") or 0.0,
                "segundos": custo.get("segundos") or 0.0,
                "filhos": custo.get("filhos") or 0,
                "pico": pico,
                "fonte": custo.get("fonte") or "amostragem",
                "razao": (pico / entrada_mb) if (pico and entrada_mb) else None,
                # A ordem de CONCLUSÃO é o eixo do teste de acumulação: é ela que
                # diz quem passou pelo worker depois de quem.
                "concluido_em": derivada.concluido_em,
            })
        return linhas

    def _imprimir(self, linhas: list[dict], limite: int) -> None:
        ordenadas = sorted(linhas, key=lambda l: l["pico"] or 0, reverse=True)
        mostradas = ordenadas[:limite] if limite else ordenadas

        self.stdout.write(f"Conversões com custo medido: {len(linhas)}")
        self.stdout.write("")
        self.stdout.write(
            f"  {'entrada':>9} {'filho':>7} {'em proc.':>9} {'cpu':>7} {'tempo':>7} "
            f"{'MB/MB':>7}  arquivo"
        )
        for linha in mostradas:
            razao = "n/d" if linha["razao"] is None else f"{linha['razao']:.1f}"
            self.stdout.write(
                f"  {linha['entrada_mb']:8.1f}M {_mb(linha['filho_mb']):>7} "
                f"{linha['va_mb']:8}M {linha['cpu_s']:6.1f}s {linha['segundos']:6.1f}s "
                f"{razao:>7}  {linha['arquivo'][:52]}"
            )
        if limite and len(ordenadas) > limite:
            self.stdout.write(f"  … e mais {len(ordenadas) - limite} (use --csv para a lista inteira)")

        self.stdout.write("")
        self._agregados(linhas)

    def _agregados(self, linhas: list[dict]) -> None:
        """Os números que respondem 'quanto custa converter um acervo destes'.

        **A soma e o pior caso são coisas diferentes, e é a distinção que
        dimensiona a máquina.** A soma diz quanto de CPU o acervo inteiro pediu —
        é conta de custo. O pior caso diz quanta memória precisa existir **ao
        mesmo tempo** — é conta de dimensionamento, e é ela que decide o
        `mem_limit` do worker. Somar memória de arquivos que rodaram em série
        seria o erro do D82 de novo, agora feito à mão no relatório.
        """
        medidos = [l for l in linhas if l["pico"] is not None]
        picos = [l["pico"] for l in medidos]
        razoes = [l["razao"] for l in linhas if l["razao"] is not None]
        por_cgroup = [l for l in linhas if l["fonte"] == "cgroup"]
        cpu = sum(l["cpu_s"] for l in linhas)
        relogio = sum(l["segundos"] for l in linhas)
        entrada = sum(l["entrada_mb"] for l in linhas)

        self.stdout.write("Somado — o custo do acervo (grandezas que SE somam)")
        self.stdout.write(f"  entrada          {entrada:9.1f} MB em {len(linhas)} conversões")
        self.stdout.write(f"  CPU              {cpu:9.1f} s")
        self.stdout.write(f"  relógio          {relogio:9.1f} s")
        self.stdout.write("")
        self.stdout.write("Pior caso — o que dimensiona a máquina (NÃO se soma)")
        if picos:
            picos_ordenados = sorted(picos)
            meio = picos_ordenados[len(picos_ordenados) // 2]
            self.stdout.write(f"  pico de um arquivo, o maior      {max(picos):6} MB")
            self.stdout.write(f"  pico de um arquivo, a mediana    {meio:6} MB")
        # **A mediana é dos medidos, e dizer o denominador faz parte** (D84):
        # contar como zero quem não foi medido faz a mediana descrever a
        # cobertura do instrumento em vez do custo do acervo.
        self.stdout.write(
            f"  pico medido em {len(medidos)} de {len(linhas)} conversões"
            f" ({len(por_cgroup)} por cgroup, exatas)"
        )
        if razoes:
            self.stdout.write("")
            self.stdout.write(
                f"  MB de pico por MB de arquivo: menor {min(razoes):.1f} · "
                f"maior {max(razoes):.1f} — quanto mais longe de constante, "
                f"menos o tamanho prevê o custo"
            )

        self._acumulacao(linhas)

        falharam = [l for l in linhas if l["estado"] == "erro"]
        if falharam:
            self.stdout.write("")
            self.stdout.write(f"Não converteram: {len(falharam)}")
            for linha in falharam[:20]:
                self.stdout.write(
                    f"  {linha['motivo'] or '?':22} {linha['entrada_mb']:7.1f}M "
                    f"{_mb(linha['filho_mb']):>7}  {linha['arquivo'][:52]}"
                )

    def _acumulacao(self, linhas: list[dict]) -> None:
        """A prova de que o número é do arquivo, e não a soma dos anteriores.

        **É o teste que o [D82](../../../../docs/historico-correcoes.md) pede, e
        ele é grátis:** um worker Celery converte centenas de arquivos no mesmo
        processo, então um instrumento que lesse marca d'água produziria uma série
        **monotônica** — cada arquivo relataria pelo menos o pico de todos os que
        vieram antes, e o último relataria o acervo inteiro. Um medidor por
        arquivo produz uma série que sobe e desce com os arquivos.

        Por isso a leitura é na **ordem de conclusão**, em quartos: se a média do
        último quarto for múltiplo da do primeiro, e a mediana nunca descer, o
        número voltou a acumular. Duas linhas de aritmética que teriam pego o D82
        no dia em que ele nasceu.
        """
        # Só quem tem pico: a série é sobre a **grandeza que acumularia**, e
        # incluir os não medidos como zero afunda o quarto que por acaso reuniu
        # mais arquivos curtos — foi assim que um quarto saiu com "1 MB" de
        # média num acervo cuja mediana é 32 (D84).
        ordenadas = [l for l in linhas if l.get("concluido_em") and l["pico"] is not None]
        ordenadas.sort(key=lambda l: l["concluido_em"])
        if len(ordenadas) < 8:
            return
        tamanho = len(ordenadas) // 4
        self.stdout.write("")
        self.stdout.write("O custo acumula com a fila? (na ordem de conclusão, em quartos)")
        medias = []
        for indice in range(4):
            corte = (
                ordenadas[indice * tamanho:(indice + 1) * tamanho] if indice < 3
                else ordenadas[3 * tamanho:]
            )
            picos = sorted(l["pico"] for l in corte)
            media = sum(picos) // len(picos)
            medias.append(media)
            self.stdout.write(
                f"  quarto {indice + 1}   mediana {picos[len(picos) // 2]:6} MB · "
                f"média {media:6} MB · maior {max(picos):6} MB"
            )
        if medias[0] and medias[3] > medias[0] * 3:
            self.stdout.write(self.style.WARNING(
                "  ⚠ a média do último quarto é 3× a do primeiro — CONFERIR se o "
                "pico voltou a ser marca d'água acumulada (D82)"
            ))
        else:
            self.stdout.write(
                "  série sem tendência de alta: o pico é do arquivo, não da fila"
            )

    def _csv(self, linhas: list[dict], destino: str) -> None:
        campos = list(linhas[0].keys())
        with open(destino, "w", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=campos)
            escritor.writeheader()
            escritor.writerows(linhas)
        print(f"\nTabela inteira em {destino}", file=sys.stderr)
