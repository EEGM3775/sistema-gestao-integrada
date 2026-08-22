#!/usr/bin/env python3
"""Gera o relatório de custo **por caminho de arquivo** de um acervo convertido.

O [`custo_do_acervo`](../../backend/moduloprancheta/management/commands/custo_do_acervo.py)
responde "quanto custou cada conversão", e é o instrumento de dentro do sistema.
Este script responde a pergunta de fora dele: **"quanto custou o arquivo que está
naquele caminho da minha pasta?"** — que é a pergunta de quem tem o acervo em
disco e quer saber o que esperar antes de subir.

**A pasta virou opcional em 13/08/2026.** O caminho relativo agora é persistido em
`RevisaoDocumento.caminho_origem` — o lote da R18 sempre o leu para adivinhar
disciplina, código e revisão, e passou a guardá-lo. Quando ele está lá, o
relatório o usa e a pasta não é necessária. Para o acervo carregado **antes**
dessa fatia o campo está vazio, e aí vale o pareamento antigo: por **SHA-256**
contra a pasta em disco, que é exato e independe de nome (o corpus tem `006.dwg`
e `AEGS06.DWG` repetidos entre subpastas, então o nome não identifica nada).

    python3 ferramentas/medicao/relatorio_custo_por_caminho.py \\
        --obra 12 --saida docs/medicoes/custo-acervo-160.md [~/acervo-corpus-160]

O custo vem do banco (`DerivadaProjeto.memoria["custo"]`, gravado pelo pipeline);
nada é reprocessado.

**Duas grandezas de pico, e a diferença entre elas é o motivo desta revisão.**
Quando a janela foi medida por cgroup (`custo["fonte"] == "cgroup"`), o
`memory.peak` conta pai e subprocesso **juntos, no mesmo instante** — que é o
número que dimensiona a máquina. As colunas de amostragem continuam separando
*onde* o custo aconteceu, mas o maior das duas **não** é o pico da operação: num
teste controlado (13/08/2026) o cgroup leu 454 MB onde `max(filho, em_processo)`
dava 372, porque as duas metades coexistem. Por isso a coluna "Pico" prefere o
cgroup e diz, no cabeçalho, quantos arquivos o têm.
"""
import argparse
import json
import os
import subprocess
import sys
from hashlib import sha256

#: Uma conversão produz N folhas de uma passada só, e o custo vai só na folha #1
#: — somar as linhas de um arquivo multifolha multiplicaria a conta. Quem filtra
#: é a presença da chave `custo`, e não uma regra sobre `tipo`.
CONSULTA = r"""
import django, json, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings"); django.setup()
from nucleo.models import Tenant
from nucleo.tenancy import tenant_context
from moduloprancheta.models import DerivadaProjeto

tenant = Tenant.objects.get(slug=%(tenant)r)
saida = []
with tenant_context(tenant.pk):
    consulta = (DerivadaProjeto.objects
                .filter(revisao__documento__obra_id=%(obra)d)
                .select_related("revisao", "revisao__documento"))
    for derivada in consulta:
        custo = (derivada.memoria or {}).get("custo")
        if not custo:
            continue
        saida.append({
            "hash": derivada.revisao.hash_sha256,
            "nome": derivada.revisao.nome_original,
            "caminho_origem": derivada.revisao.caminho_origem,
            "codigo": derivada.revisao.documento.codigo,
            "disciplina": derivada.revisao.documento.get_disciplina_display(),
            "bytes": derivada.revisao.tamanho_bytes,
            "tipo": derivada.tipo,
            "estado": derivada.estado,
            "motivo": derivada.erro_motivo,
            "versao_dwg": (derivada.memoria or {}).get("versao"),
            "custo": custo,
        })
print("@@JSON@@" + json.dumps(saida))
"""


def do_banco(tenant: str, obra: int) -> list[dict]:
    """Lê o custo já gravado, pelo `manage.py shell` do container em pé."""
    resultado = subprocess.run(
        ["docker", "compose", "exec", "-T", "erp", "python", "-c",
         CONSULTA % {"tenant": tenant, "obra": obra}],
        capture_output=True, text=True, encoding="utf-8",
    )
    for linha in resultado.stdout.splitlines():
        if linha.startswith("@@JSON@@"):
            return json.loads(linha[len("@@JSON@@"):])
    sys.exit(f"não consegui ler o banco:\n{resultado.stdout[-2000:]}\n{resultado.stderr[-2000:]}")


def hashes_da_pasta(pasta: str) -> dict[str, str]:
    """`sha256 → caminho relativo`. É o que devolve o caminho que o banco não tem."""
    mapa = {}
    for raiz, _dirs, nomes in os.walk(pasta):
        for nome in nomes:
            completo = os.path.join(raiz, nome)
            digest = sha256()
            with open(completo, "rb") as arquivo:
                for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
                    digest.update(bloco)
            mapa[digest.hexdigest()] = os.path.relpath(completo, pasta).replace(os.sep, "/")
    return mapa


def mb(valor) -> str:
    """`None` é **não medido**, e nunca 0 — a lição do D82."""
    return "n/d" if valor is None else f"{valor:,}".replace(",", ".")


def pico_do_arquivo(arquivo: dict) -> int | None:
    """O pico da operação, ou `None` quando nada o mediu.

    **O `None` é o conserto, e ele é o D82 outra vez — cometido no relatório.**
    Este cálculo era `max(a["filho"] or 0, a["va"])`, e aquele `or 0` transformava
    "subprocesso curto demais para amostrar" em **zero**. Custava caro em dois
    lugares: a mediana do acervo saía de uma lista com 76 zeros em 159 posições,
    ou seja, era decidida por onde os zeros acabavam e não pela distribuição de
    custo (9 MB publicados contra 32 MB dos arquivos efetivamente medidos); e a
    coluna `MB/MB` imprimia `0×` justamente nas linhas cuja legenda dizia
    "**não é zero**". O medidor tinha a regra certa e o relatório a desfazia.

    A ordem de preferência é a da confiança: o cgroup mede pai e filho juntos e
    não perde pico entre amostras; a amostragem é piso, e piso de duas metades
    tomadas separadamente não é o pico da operação.
    """
    if arquivo["cgroup"] is not None:
        return arquivo["cgroup"]
    amostrados = [v for v in (arquivo["filho"], arquivo["va"]) if v]
    return max(amostrados) if amostrados else None


def principal():
    analisador = argparse.ArgumentParser(description=__doc__)
    # Opcional desde que `caminho_origem` existe: só o acervo carregado antes
    # dela precisa da pasta em disco para o pareamento por SHA-256.
    analisador.add_argument("pasta", nargs="?", default="")
    analisador.add_argument("--obra", type=int, required=True)
    analisador.add_argument("--tenant", default="demo")
    analisador.add_argument("--saida", required=True)
    opcoes = analisador.parse_args()

    linhas = do_banco(opcoes.tenant, opcoes.obra)
    caminhos = hashes_da_pasta(opcoes.pasta) if opcoes.pasta else {}

    # Um arquivo, N conversões. A memória é o **maior** pico (as conversões
    # rodaram em série, então nunca existiram ao mesmo tempo); CPU e relógio
    # somam, porque tempo é grandeza que se acumula de verdade.
    por_arquivo: dict[str, dict] = {}
    for linha in linhas:
        alvo = por_arquivo.setdefault(linha["hash"], {
            # O campo persistido primeiro; a pasta só quando ele está vazio, que
            # é o caso do acervo carregado antes de o campo existir.
            "caminho": (
                linha.get("caminho_origem")
                or caminhos.get(linha["hash"])
                or f"(caminho não guardado) {linha['nome']}"
            ),
            "nome": linha["nome"], "codigo": linha["codigo"],
            "disciplina": linha["disciplina"], "bytes": linha["bytes"],
            "versao_dwg": linha.get("versao_dwg"),
            "cgroup": None, "fonte": "amostragem",
            "filho": None, "va": 0, "rss": 0, "cpu": 0.0, "segundos": 0.0,
            "conversoes": 0, "vereditos": [],
        })
        custo = linha["custo"]
        exato = custo.get("pico_cgroup_mb")
        if exato is not None:
            alvo["cgroup"] = max(alvo["cgroup"] or 0, exato)
            alvo["fonte"] = "cgroup"
        filho = custo.get("pico_filho_mb")
        if filho is not None:
            alvo["filho"] = max(alvo["filho"] or 0, filho)
        alvo["va"] = max(alvo["va"], custo.get("pico_va_mb") or 0)
        alvo["rss"] = max(alvo["rss"], custo.get("pico_rss_mb") or 0)
        alvo["cpu"] += custo.get("cpu_s") or 0.0
        alvo["segundos"] += custo.get("segundos") or 0.0
        alvo["conversoes"] += 1
        alvo["vereditos"].append(
            f"{linha['tipo']}: {linha['motivo'] or linha['estado']}"
        )
        alvo["versao_dwg"] = alvo["versao_dwg"] or linha.get("versao_dwg")

    arquivos = sorted(por_arquivo.values(), key=lambda a: -(pico_do_arquivo(a) or 0))
    escrever(arquivos, opcoes)
    print(f"{len(arquivos)} arquivos · relatório em {opcoes.saida}")


def escrever(arquivos: list[dict], opcoes) -> None:
    entrada_total = sum(a["bytes"] for a in arquivos) / 1048576
    cpu_total = sum(a["cpu"] for a in arquivos)
    relogio_total = sum(a["segundos"] for a in arquivos)
    # **A mediana é dos arquivos MEDIDOS, e só deles.** Somar `None` como zero
    # faria a mediana do acervo ser decidida por quantos arquivos ficaram sem
    # número, e não por quanto os arquivos custam — foi o que aconteceu na
    # primeira publicação desta tabela.
    picos = [p for p in (pico_do_arquivo(a) for a in arquivos) if p is not None]
    picos_ordenados = sorted(picos)
    medidos = [a for a in arquivos if pico_do_arquivo(a) is not None]
    por_cgroup = [a for a in arquivos if a["cgroup"] is not None]

    with open(opcoes.saida, "w", encoding="utf-8") as saida:
        saida.write(CABECALHO % {
            "n": len(arquivos),
            "entrada": f"{entrada_total:.1f}",
            "cpu": f"{cpu_total:.0f}",
            "relogio": f"{relogio_total:.0f}",
            "maior": mb(max(picos)) if picos else "n/d",
            "mediana": mb(picos_ordenados[len(picos_ordenados) // 2]) if picos else "n/d",
            "medidos": len(medidos),
            "por_cgroup": len(por_cgroup),
            "obra": opcoes.obra,
            "pasta": os.path.basename(opcoes.pasta.rstrip("/")) if opcoes.pasta else "—",
        })
        saida.write(
            "| # | Caminho no acervo | Entrada | Pico | Fonte | Pico subproc. | "
            "Pico em proc. | CPU | Relógio | MB/MB | Veredito |\n"
            "|--:|---|--:|--:|---|--:|--:|--:|--:|--:|---|\n"
        )
        for indice, arquivo in enumerate(arquivos, start=1):
            entrada_mb = arquivo["bytes"] / 1048576
            pico = pico_do_arquivo(arquivo)
            # `n/d` e não `0×`: sem pico não há razão nenhuma para calcular, e
            # imprimir zero diria "não custou nada" na coluna que mais convida a
            # essa leitura.
            razao = f"{pico / entrada_mb:.0f}×" if (pico and entrada_mb) else "n/d"
            # **`≥` quando o teto cortou.** O pico de quem estourou o orçamento é
            # o do instante da interrupção — o arquivo pediria mais, e ninguém
            # sabe quanto. A planta §4.7 já mandava marcar assim; o gerador não
            # marcava, e o número saía com cara de valor exato na única linha da
            # tabela em que ele é piso por construção.
            cortado = "≥ " if "recurso_excedido" in veredito(arquivo) and pico else ""
            saida.write(
                f"| {indice} | `{arquivo['caminho']}` | {entrada_mb:.1f} MB | "
                f"{cortado}{mb(pico)} MB | {arquivo['fonte']} | "
                f"{mb(arquivo['filho'])} MB | {mb(arquivo['va'])} MB | "
                f"{arquivo['cpu']:.1f} s | {arquivo['segundos']:.1f} s | "
                f"{razao} | {veredito(arquivo)} |\n"
            )
        saida.write(RODAPE)


def veredito(arquivo: dict) -> str:
    """O que aconteceu com o arquivo, na linguagem da fila do cockpit."""
    partes = arquivo["vereditos"]
    desenho = next((p for p in partes if p.startswith("vetor_2d")), "")
    if "pronto" in desenho:
        base = "✅ prancha"
    elif "recurso_excedido" in desenho:
        base = "⛔ recurso_excedido"
    elif desenho:
        base = "⚠ " + desenho.split(": ", 1)[-1]
    else:
        base = "—"
    if any("miniatura: pronto" in p for p in partes):
        return base + " + miniatura"
    return base


CABECALHO = """# Custo de conversão por arquivo — acervo de %(n)s DWGs

> **Natureza: medição.** Uma passada, uma data, um corpus. O **desenho** do
> medidor está na [planta §4.7](../modulos/moduloprancheta.md#47-medir-o-custo-de-um-arquivo--e-as-três-vezes-em-que-medimos-outra-coisa);
> o histórico do defeito que ele corrige, no [D82](../historico-correcoes.md).

Gerado por [relatorio_custo_por_caminho.py](../../ferramentas/medicao/relatorio_custo_por_caminho.py) sobre
a obra %(obra)s (pasta `%(pasta)s`), a partir do que o **pipeline de produção** gravou em
`DerivadaProjeto.memoria["custo"]`. Nada foi reprocessado para produzir esta tabela.

## Como ler

Cada linha é **um arquivo**, não uma conversão — um DWG rende duas (a prancha e a
miniatura), e às vezes mais, quando tem várias folhas.

| Coluna | O que é | O que **não** é |
|---|---|---|
| **Pico** | o custo da operação: `memory.peak` do cgroup quando há um, senão o maior das duas colunas de amostragem | não é a soma das duas metades quando a fonte é amostragem — é **piso**, e a coluna `Fonte` diz qual dos dois casos é |
| **Fonte** | `cgroup` (exato, pai e filho no mesmo instante) ou `amostragem` (piso, a 50 ms) | — |
| **Pico subproc.** | maior RSS do `dwg2dxf`, lido no `VmHWM` do `/proc` **dele** | não é marca d'água acumulada, e não conta memória herdada do pai no `fork` — foi o [D82](../historico-correcoes.md) |
| **Pico em proc.** | maior VA da janela da conversão, menos a linha de base | não é o pico do worker, que converte centenas de arquivos no mesmo processo |
| **CPU** / **Relógio** | somados entre as conversões do arquivo | tempo se soma; **memória não** |
| **MB/MB** | pico sobre peso de entrada | — |
| `n/d` | não medido: subprocesso mais curto que a amostragem, e sem cgroup | **não é zero.** Zero se leria como "não custou nada" |

**Memória não se soma; tempo sim.** As conversões rodaram em série **e com
`--concurrency 1`**, então os picos nunca existiram ao mesmo tempo: o que
dimensiona a máquina é o **maior**, não a soma. Isso é propriedade do deploy, não
da medição — com dois processos de conversão simultâneos, dois picos coexistem e
a conta muda.

## O acervo inteiro

| | |
|---|---|
| arquivos | **%(n)s** |
| entrada | **%(entrada)s MB** |
| CPU somada | **%(cpu)s s** |
| relógio somado | **%(relogio)s s** |
| **pico de um arquivo — o maior** | **%(maior)s MB** |
| **pico de um arquivo — a mediana (só os medidos)** | **%(mediana)s MB** |
| pico medido em | %(medidos)s de %(n)s arquivos |
| destes, por cgroup (exatos) | %(por_cgroup)s |

**A distância entre a mediana e o maior é o resultado.** Um acervo destes é barato
na média e caro na cauda: dimensionar o worker pela mediana derruba a conversão de
um punhado de arquivos, e dimensionar pelo maior paga folga ociosa em quase todos.

**A mediana é dos arquivos medidos, e a distinção não é preciosismo.** Contar como
zero o arquivo que não foi medido faz a mediana descrever a *cobertura do medidor*
em vez do *custo do acervo* — e foi exatamente o que a primeira versão desta
tabela publicou.

## Por arquivo

Ordenado pelo pico — o mais caro primeiro.

"""

RODAPE = """
## Duas leituras que a tabela sustenta

**1. O tamanho não prevê o custo, e esta é a terceira medição a dizê-lo.** A coluna
`MB/MB` varia por mais de uma ordem de grandeza sobre o mesmo motor e o mesmo
estágio. O arquivo mais caro do acervo não é o mais pesado — é o que declara mais
trabalho (hachura é *declaração*: área ÷ espaçamento do padrão, grandeza que o
tamanho do arquivo não limita). Qualquer knob comercial em MB — e o
`DWG_MB_MOTOR_LIVRE` é um — está medido contra o eixo errado
([planta §12 item 00](../modulos/moduloprancheta.md)).

**2. O caminho da pasta agora sobrevive à importação — e esta tabela é a última
que precisou reconstruí-lo.** A `RevisaoDocumento` passou a guardar
`caminho_origem` (13/08/2026): o lote da R18 sempre leu o caminho relativo para
adivinhar disciplina, código e revisão, e só o descartava em seguida. As linhas
abaixo ainda vêm de um pareamento por **SHA-256** contra a pasta em disco, porque
este acervo foi carregado antes do campo — e é exatamente esse o custo que o campo
elimina: sem ele, *"de qual pasta do escritório veio esta prancha?"* só tem
resposta enquanto alguém ainda tiver a pasta.

**3. Quase metade do acervo não tem pico medido, e isso é da amostragem, não do
acervo.** São 76 dos 159 arquivos cujo subprocesso viveu menos que o intervalo de
50 ms. Eles saem `n/d`, ficam fora da mediana e não viram zero em lugar nenhum —
e o medidor por cgroup (`nucleo/consumo.py`) existe para que a próxima passada não
tenha essa coluna vazia: `memory.peak` não amostra, e conta pai e subprocesso no
mesmo instante. Ligar depende de o deploy delegar um cgroup; enquanto não ligar, a
coluna `Fonte` dirá `amostragem` em todas as linhas.
"""


if __name__ == "__main__":
    principal()
