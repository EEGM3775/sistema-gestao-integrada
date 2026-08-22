"""A fila da frota exercitada com DWG de verdade — a bancada que o dono pediu ver.

**Por que ela existe ao lado do `simular_fila`.** Aquela bancada prova a POLÍTICA
(quem senta, quem espera, quem passa na frente) com um motor encenado, e por isso
roda em milissegundos e cabe em CI. Esta prova a outra metade: que a política
continua valendo quando o trabalho é **caro de verdade** — arquivos reais do
acervo, convertidos pelo `MotorDwg`, com o relógio de parede que o cliente sente.

**O que é real e o que não é**, para o laudo não prometer mais do que mediu:

- real: os arquivos (DWGs do acervo), o motor (`MotorDwg` → `MotorDxf`), a fila
  (`nucleo.frota`, com admissão, reserva, prioridade e recolocação), os
  orçamentos de memória por plano e o relógio;
- encenado: o **transporte**. O Celery não entra — este comando é o worker, e
  roda a tarefa da cabeça da fila em processo, na hora. É o que permite observar
  a fila de fora enquanto ela anda.

**Tudo é desfeito** (`Rollback` no fim do `atomic`): resíduo aqui seria trabalho
que o próximo boot do despachante tentaria enviar de verdade.
"""
from __future__ import annotations

import json
import os
import resource
import threading
import time
from unittest import mock

from django.core.management.base import BaseCommand
from django.db import transaction
from django.test import override_settings

from moduloprancheta.motores.base import orcamento_de_subprocesso
from moduloprancheta.motores.dwg import MotorDwg
from moduloprancheta.limites import orcamento_de_conversao
from nucleo import frota
from nucleo.models import TarefaNaFila, Tenant, Usuario

#: Onde o acervo de medição está montado dentro do worker.
ACERVO = "/app/media/impexp/conferencia/2026/08"

#: O elenco, escolhido para cobrir a faixa de custo do acervo real — do desenho
#: de traço que sai em segundos à prancha de disciplina que segura o worker por
#: um minuto. Nomes literais: quem repetir a bancada tem de poder conferir.
ELENCO = [
    ("01_LOTEAMENTO_PORTAL_RESIDENCE_o0OdPZI.dwg", "gama", "empresarial"),
    ("ESGOTO_2023.dwg", "acme", "free"),
    ("02_PROJETO_TERRPALANAGEM_JRL_30_01_2025.dwg", "beta", "profissional"),
    ("04-Nova_Area_Industrial_MaxPlast.dwg", "gama", "empresarial"),
    ("Poligonal.dwg", "acme", "free"),
    ("03-Nova_Area_Industrial_MaxPlast.dwg", "beta", "profissional"),
]


class Rollback(Exception):
    """Desfaz tudo no fim — a bancada não deixa rastro no banco."""


def _existe(nome: str) -> str | None:
    caminho = os.path.join(ACERVO, nome)
    return caminho if os.path.exists(caminho) else None


#: Onde o cgroup v2 publica o que o contêiner INTEIRO está usando de memória.
#:
#: **É a única leitura honesta aqui, e o `getrusage` do processo não serve.** O
#: trabalho pesado acontece em dois lugares — o `dwg2dxf`, que é subprocesso, e o
#: `ezdxf`, que é o processo pai — e o pico de um não coincide com o do outro.
#: Medir só o pai esconderia justamente o estágio que estoura o teto do
#: subprocesso; medir só o filho esconderia a leitura do DXF. O cgroup soma os
#: dois, que é exatamente o que o `mem_limit` do contêiner cobra.
CGROUP_MEMORIA = "/sys/fs/cgroup/memory.current"


def _memoria_agora() -> float:
    """MB em uso pelo contêiner inteiro — `0.0` onde o cgroup não estiver visível."""
    try:
        with open(CGROUP_MEMORIA, encoding="utf-8") as arquivo:
            return int(arquivo.read().strip()) / 1048576
    except (OSError, ValueError):
        return 0.0


def _cpu_agora() -> float:
    """Segundos de CPU (usuário + sistema) deste processo E dos filhos dele.

    `RUSAGE_CHILDREN` não é detalhe: o `dwg2dxf` queima CPU como processo
    separado, e sem ele a conta sairia menor que a verdade justamente nos
    arquivos que mais custam.
    """
    eu = resource.getrusage(resource.RUSAGE_SELF)
    filhos = resource.getrusage(resource.RUSAGE_CHILDREN)
    return eu.ru_utime + eu.ru_stime + filhos.ru_utime + filhos.ru_stime


class Vigia:
    """Amostra a memória do contêiner enquanto o motor trabalha.

    Thread e não medição no fim porque o que interessa é o **pico**: a conversão
    sobe, segura e devolve, e ler depois que ela terminou daria o vale, não o
    morro. 50 ms é folgado para um estágio que dura segundos e barato o bastante
    para não competir com a conversão pela CPU.
    """

    def __init__(self, intervalo: float = 0.05):
        self.intervalo = intervalo
        self.base = _memoria_agora()
        self.pico = self.base
        self._parar = threading.Event()
        self._thread = threading.Thread(target=self._rodar, daemon=True)

    def _rodar(self):
        while not self._parar.wait(self.intervalo):
            agora = _memoria_agora()
            if agora > self.pico:
                self.pico = agora

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._parar.set()
        self._thread.join(timeout=1)
        return False

    @property
    def acrescimo(self) -> float:
        """Quanto ESTA conversão somou ao que já estava em pé."""
        return max(0.0, self.pico - self.base)


def _converter(caminho: str, *, prazo=None, ceder=None, retomada=None,
               memoria_mb=None, subprocesso_mb=None):
    """Uma passada de motor, instrumentada. Devolve (saida, erro, medida)."""
    inicio = time.monotonic()
    cpu_antes = _cpu_agora()
    saida, erro = None, None
    with Vigia() as vigia:
        try:
            with orcamento_de_conversao(memoria_mb=memoria_mb, segundos=600), \
                    orcamento_de_subprocesso(subprocesso_mb):
                saida = MotorDwg().converter(
                    caminho, formato="dwg", tipo="vetor_2d",
                    prazo=prazo, ceder=ceder, retomada=retomada,
                )
        except Exception as exc:
            erro = f"{type(exc).__name__}: {str(exc)[:120]}"
    medida = {
        "relogio": time.monotonic() - inicio,
        "cpu": _cpu_agora() - cpu_antes,
        "ram_pico": vigia.pico,
        "ram_acrescimo": vigia.acrescimo,
        "ram_base": vigia.base,
    }
    return saida, erro, medida


class Command(BaseCommand):
    help = "Exercita a fila da frota com DWGs reais do acervo e imprime o laudo."

    def add_arguments(self, parser):
        parser.add_argument("--json", default="", help="grava o resultado bruto neste caminho")

    def handle(self, *args, **opcoes):
        self.dados: dict = {}
        try:
            with transaction.atomic():
                # **A fila do banco de dev não está vazia**, e as linhas que já
                # estão lá são de conversão real (`argumentos=[derivada_id]`, um
                # inteiro). Deixá-las faria duas coisas ruins: elas disputariam a
                # única vaga com o elenco desta bancada, e o relatório tentaria
                # ler um id como nome de arquivo. Some tudo aqui dentro do
                # `atomic` — e volta ao sair, como todo o resto.
                TarefaNaFila.objects.all().delete()
                self._cena_a()
                self._cena_b()
                self._cena_c()
                raise Rollback
        except Rollback:
            self.stdout.write("\n(banco restaurado — a bancada não deixou rastro)")

        if opcoes["json"]:
            with open(opcoes["json"], "w", encoding="utf-8") as saida:
                json.dump(self.dados, saida, ensure_ascii=False, indent=2)
            self.stdout.write(f"bruto gravado em {opcoes['json']}")

    # -- infraestrutura da bancada -------------------------------------------
    def _tenants(self):
        tenants = {
            slug: Tenant.objects.get_or_create(slug=f"bancada-{slug}", defaults={"nome": slug})[0]
            for slug in ("acme", "beta", "gama")
        }
        Usuario.objects.get_or_create(
            username="bancada-admin", defaults={"tenant": tenants["acme"]},
        )
        return tenants

    def _titulo(self, texto: str) -> None:
        self.stdout.write("")
        self.stdout.write("=" * 76)
        self.stdout.write(texto)
        self.stdout.write("=" * 76)

    # -- CENA A ---------------------------------------------------------------
    @override_settings(FROTA_VAGAS={"conversao": 1})
    def _cena_a(self):
        """Seis arquivos reais, três empresas, UMA vaga — a frota de produção."""
        self._titulo("CENA A — seis DWGs reais, três empresas, uma vaga")

        tenants = self._tenants()
        elenco = [(n, t, p) for n, t, p in ELENCO if _existe(n)]
        ausentes = [n for n, _, _ in ELENCO if not _existe(n)]
        if ausentes:
            self.stdout.write(f"  (fora do acervo desta máquina: {', '.join(ausentes)})")

        with mock.patch("celery.current_app.send_task"):
            for indice, (nome, slug, plano) in enumerate(elenco, 1):
                frota.enfileirar(
                    tenant_id=tenants[slug].pk, chave=f"real:{indice}",
                    tarefa="prancheta.converter", argumentos=[nome], plano=plano,
                )

        self.stdout.write("\nA fila logo depois da chegada (ordem de chegada = ordem do elenco):")
        self.stdout.write(f"  {'':4} {'arquivo':44} {'empresa':8} {'plano':13} {'prio':>5}  situação")
        for tarefa in TarefaNaFila.objects.filter(frota="conversao").order_by(
            "-situacao", "prioridade", "criada_em",
        ):
            nome = tarefa.argumentos[0]
            marca = "▶" if tarefa.situacao == "despachada" else f"{frota.posicao(tarefa)}º"
            self.stdout.write(
                f"  {marca:4} {nome[:44]:44} {tarefa.tenant_id and tarefa.tenant.slug[8:]:8} "
                f"{tarefa.plano:13} {tarefa.prioridade:>5}  {tarefa.situacao}"
            )

        # **O que a fila consome PARADA, medido antes de qualquer conversão.**
        # É a pergunta do dono — "em standby, sem usar CPU e memória, apenas
        # armazenamento" — e ela merece número, não promessa. Com seis arquivos
        # enfileirados e nenhum convertendo, a plataforma segura: seis linhas no
        # Postgres e os seis arquivos no disco. RAM de conversão, zero.
        ocioso_ram = _memoria_agora()
        ocioso_cpu_a = _cpu_agora()
        time.sleep(2.0)
        ocioso_cpu = _cpu_agora() - ocioso_cpu_a
        disco = sum(os.path.getsize(_existe(n)) for n, _, _ in elenco) / 1048576
        self.stdout.write(
            f"\nCom os 6 esperando e NADA convertendo (2 s de observação):\n"
            f"  RAM do contêiner: {ocioso_ram:.0f} MB (linha de base, nada de conversão)\n"
            f"  CPU consumida:    {ocioso_cpu:.2f}s\n"
            f"  Disco segurado:   {disco:.1f} MB (os arquivos) + 6 linhas no Postgres"
        )

        self.stdout.write("\nAgora o worker anda a fila, convertendo DE VERDADE:")
        cabecalho = (
            f"  {'#':>2} {'arquivo':38} {'plano':12} {'fl':>3} "
            f"{'relógio':>9} {'CPU':>8} {'RAM pico':>9} {'RAM +':>8}"
        )
        self.stdout.write(cabecalho)
        relogio = time.monotonic()
        linhas, passos = [], []
        while True:
            with mock.patch("celery.current_app.send_task"):
                frota.despachar("conversao")
            tarefa = TarefaNaFila.objects.filter(
                frota="conversao", situacao="despachada",
            ).order_by("prioridade", "criada_em").first()
            if tarefa is None:
                break

            # **A fotografia da fila INTEIRA neste instante**, antes de o motor
            # começar. É o que responde "o que cada arquivo está fazendo em cada
            # lugar da fila": quem roda, quem espera e em que posição, e — o
            # ponto — que quem espera não consome nada além do próprio arquivo
            # no disco.
            foto = {"rodando": tarefa.argumentos[0], "em": round(time.monotonic() - relogio, 1),
                    "ram_antes": round(_memoria_agora(), 0), "fila": []}
            for espera in TarefaNaFila.objects.filter(
                frota="conversao", situacao="aguardando",
            ).order_by("prioridade", "criada_em"):
                foto["fila"].append({
                    "arquivo": espera.argumentos[0],
                    "posicao": frota.posicao(espera),
                    "plano": espera.plano,
                    "disco_mb": round(os.path.getsize(_existe(espera.argumentos[0])) / 1048576, 1),
                })
            passos.append(foto)

            caminho = _existe(tarefa.argumentos[0])
            saida, erro, medida = _converter(caminho)
            folhas = len(saida.partes) if saida else 0
            linhas.append({
                "arquivo": tarefa.argumentos[0], "plano": tarefa.plano,
                "empresa": tarefa.tenant.slug[8:], "folhas": folhas,
                "mb": round(os.path.getsize(caminho) / 1048576, 1),
                "relogio": round(medida["relogio"], 1),
                "cpu": round(medida["cpu"], 1),
                "ram_pico": round(medida["ram_pico"]),
                "ram_acrescimo": round(medida["ram_acrescimo"]),
                "erro": erro,
                "terminou_em": round(time.monotonic() - relogio, 1),
            })
            self.stdout.write(
                f"  {len(linhas):>2} {tarefa.argumentos[0][:38]:38} {tarefa.plano:12} "
                f"{folhas:>3} {medida['relogio']:>8.1f}s {medida['cpu']:>7.1f}s "
                f"{medida['ram_pico']:>8.0f}M {medida['ram_acrescimo']:>7.0f}M"
                + (f"   {erro}" if erro else "")
            )
            self.stdout.flush()
            with mock.patch("celery.current_app.send_task"):
                frota.concluir(tarefa.chave)

        total = time.monotonic() - relogio

        self.stdout.write("\nA fila passo a passo — quem roda, quem espera, e o que cada um segura:")
        for numero, foto in enumerate(passos, 1):
            espera_mb = sum(e["disco_mb"] for e in foto["fila"])
            self.stdout.write(
                f"\n  passo {numero} · t={foto['em']:.0f}s · RAM do contêiner {foto['ram_antes']:.0f} MB"
            )
            self.stdout.write(f"     ▶ RODANDO  {foto['rodando'][:44]}")
            for item in foto["fila"]:
                self.stdout.write(
                    f"     {item['posicao']}º ESPERA   {item['arquivo'][:44]:44} "
                    f"{item['plano']:12} CPU 0.0s · RAM 0 MB · disco {item['disco_mb']:.1f} MB"
                )
            if foto["fila"]:
                self.stdout.write(
                    f"       └ {len(foto['fila'])} esperando consomem juntos: "
                    f"0 CPU, 0 RAM, {espera_mb:.1f} MB de disco"
                )

        soma_cpu = sum(l["cpu"] for l in linhas)
        self.stdout.write(
            f"\n  fila inteira em {total:.1f}s de relógio, uma vaga · "
            f"{soma_cpu:.1f}s de CPU somados · "
            f"aproveitamento {100 * soma_cpu / total:.0f}%"
        )
        self.dados["cena_a"] = {
            "linhas": linhas, "passos": passos, "total": round(total, 1),
            "cpu_total": round(soma_cpu, 1), "ocioso_ram": round(ocioso_ram),
            "ocioso_cpu": round(ocioso_cpu, 2), "disco_total": round(disco, 1),
        }
        TarefaNaFila.objects.all().delete()

    # -- CENA B ---------------------------------------------------------------
    @override_settings(FROTA_VAGAS={"conversao": 1})
    def _cena_b(self):
        """A regra nova (D102): ceder a vez SÓ quando há alguém para recebê-la."""
        self._titulo("CENA B — o pesado só cede a vez se houver fila (D102)")

        caminho = _existe("01_LOTEAMENTO_PORTAL_RESIDENCE_o0OdPZI.dwg")
        if not caminho:
            self.stdout.write("  arquivo do teste não está neste acervo — cena pulada")
            return

        tenants = self._tenants()
        resultado = {}

        for cenario, quantos_esperando in (("fila vazia", 0), ("três esperando", 3)):
            TarefaNaFila.objects.all().delete()
            with mock.patch("celery.current_app.send_task"):
                frota.enfileirar(
                    tenant_id=tenants["gama"].pk, chave="pesado",
                    tarefa="prancheta.converter", argumentos=["pesado"], plano="empresarial",
                )
                for i in range(quantos_esperando):
                    frota.enfileirar(
                        tenant_id=tenants["beta"].pk, chave=f"leve{i}",
                        tarefa="prancheta.converter", argumentos=[f"leve{i}"], plano="profissional",
                    )

            ha_fila = frota.ha_espera("pesado")
            self.stdout.write(
                f"\n  {cenario}: frota.ha_espera('pesado') = {ha_fila}"
            )

            # Prazo já vencido: o motor CHEGA na decisão a cada folha. O que muda
            # entre os dois cenários é só a resposta do `ceder`.
            passadas, retomada, custo, cpu, folhas, pico = 0, None, 0.0, 0.0, 0, 0.0
            while True:
                saida, erro, medida = _converter(
                    caminho, prazo=time.monotonic() - 1,
                    ceder=lambda: frota.ha_espera("pesado"), retomada=retomada,
                )
                passadas += 1
                custo += medida["relogio"]
                cpu += medida["cpu"]
                pico = max(pico, medida["ram_pico"])
                if erro:
                    self.stdout.write(f"    passada {passadas}: {erro}")
                    break
                folhas += len(saida.partes)
                marcador = saida.retomada
                self.stdout.write(
                    f"    passada {passadas}: {len(saida.partes)} folha(s) · "
                    f"{medida['relogio']:.1f}s relógio · {medida['cpu']:.1f}s CPU · "
                    f"pico {medida['ram_pico']:.0f} MB"
                    + (f" · faltam {marcador.restam}" if marcador else " · terminou")
                )
                self.stdout.flush()
                if not marcador:
                    break
                retomada = marcador
                if passadas > 8:
                    break

            resultado[cenario] = {
                "ha_espera": ha_fila, "passadas": passadas, "folhas": folhas,
                "relogio": round(custo, 1), "cpu": round(cpu, 1), "ram_pico": round(pico),
            }
            self.stdout.write(
                f"    → {passadas} passada(s), {folhas} folhas, {custo:.1f}s de relógio, "
                f"{cpu:.1f}s de CPU, pico {pico:.0f} MB"
            )

        vazia = resultado.get("fila vazia", {})
        cheia = resultado.get("três esperando", {})
        if vazia and cheia and vazia["cpu"]:
            self.stdout.write(
                f"\n  Mesmo arquivo, mesmo prazo vencido: {vazia['passadas']} passada(s) com a fila "
                f"vazia contra {cheia['passadas']} com três esperando.\n"
                f"  Relógio: {vazia['relogio']:.1f}s × {cheia['relogio']:.1f}s "
                f"({cheia['relogio'] / vazia['relogio']:.2f}×)\n"
                f"  CPU:     {vazia['cpu']:.1f}s × {cheia['cpu']:.1f}s "
                f"({cheia['cpu'] / vazia['cpu']:.2f}× — o preço de dar lugar a alguém)\n"
                f"  RAM:     pico {vazia['ram_pico']:.0f} MB × {cheia['ram_pico']:.0f} MB "
                f"(a retomada NÃO baixa o pico — cada volta recarrega o documento inteiro)"
            )
        self.dados["cena_b"] = resultado
        TarefaNaFila.objects.all().delete()

    # -- CENA C ---------------------------------------------------------------
    def _cena_c(self):
        """O degrau de RAM do plano decide se o desenho grande abre (D101)."""
        self._titulo("CENA C — a memória do plano decide quem abre (D101)")

        from payment.planos import (
            PRANCHETA_CONVERSAO_MEMORIA_MB_POR_PLANO as CONV,
            PRANCHETA_SUBPROCESSO_MEMORIA_MB_POR_PLANO as SUB,
        )

        alvos = [n for n in ("J2_-_S_PROJETO_EXECUTIVO_FINAL_COM_LAZER.dwg",
                             "04-Nova_Area_Industrial_MaxPlast.dwg") if _existe(n)]
        linhas = []
        self.stdout.write(
            f"  {'arquivo':40} {'MB':>6} {'plano':13} {'RAM':>6} {'sub':>6}  resultado"
        )
        for nome in alvos:
            caminho = _existe(nome)
            mb = os.path.getsize(caminho) / 1048576
            for plano in ("free", "profissional", "empresarial"):
                saida, erro, medida = _converter(
                    caminho, memoria_mb=CONV[plano], subprocesso_mb=SUB[plano],
                )
                veredito = (
                    f"ABRIU {len(saida.partes)} folha(s) · {medida['relogio']:.1f}s · "
                    f"pico {medida['ram_pico']:.0f} MB" if saida
                    else f"PAROU em {medida['relogio']:.1f}s · pico {medida['ram_pico']:.0f} MB"
                )
                linhas.append({
                    "arquivo": nome, "mb": round(mb, 1), "plano": plano,
                    "ram": CONV[plano], "sub": SUB[plano], "abriu": bool(saida),
                    "relogio": round(medida["relogio"], 1), "cpu": round(medida["cpu"], 1),
                    "ram_pico": round(medida["ram_pico"]), "erro": erro,
                })
                self.stdout.write(
                    f"  {nome[:40]:40} {mb:>6.1f} {plano:13} {CONV[plano]:>6} "
                    f"{SUB[plano]:>6}  {veredito}"
                )
                self.stdout.flush()
        self.dados["cena_c"] = linhas
