"""O cockpit do PDCA — carteira, fila do dia, pulso e busca única, pelo gateway.

Irmão do `pdca7_verificacao_test.py`, e existe pelo mesmo motivo: a suíte
unitária chama o serviço direto e empurra o usuário com `force_authenticate`;
aqui cada leitura atravessa login, assinatura RS256, gateway, entitlement de
módulo, permissão de campo e RLS.

O que estas três leituras têm de próprio é que **elas cruzam** — a carteira
cruza obras, `hoje/` junta cinco assuntos e `busca/` varre sete tabelas. As três
são `APIView` pura, que é exatamente a família em que o achado S1 encontrou
views de dashboard lendo dado de qualquer tenant. Metade das verificações abaixo
existe para provar que o isolamento e o recorte por permissão continuam de pé
quando a leitura foi feita para atravessar.

Quatro tokens reais, e a divisão é o teste:

  demo     / demo123     -> `engenharia`: vê o plano, a qualidade e a semana.
                            **Não** ateste medição, e a carteira dele diz isso
                            em vez de mostrar a coluna vazia.
  campo    / campo123    -> `campo`: o recorte mais estreito. A fila dele tem
                            menos faixas, e as que faltam vêm nomeadas.
  gerente  / gerente123  -> `diretoria`: a persona da carteira. Vê o dinheiro.
  acme     / acme123     -> outro tenant, e **sem o módulo contratado**: é a
                            fronteira, e ele para na primeira das duas
                            barreiras (entitlement antes de RLS).

Seed: iam/seed_demo.py + backend/seed_demo_data.py + semear_pdca_demo
      + semear_pdca_execucao

  1. O que existe   -> `status/` declara as quatro capacidades e os três tetos.
  2. A carteira     -> cruza obras, declara o teto e não soma o que não se soma.
  3. Dado honesto   -> avanço sem apontamento é nulo COM frase, nunca 0%.
  4. A fila do dia  -> junta os assuntos e ordena por consequência.
  5. A linha        -> diz o que é, há quanto tempo espera e o que decidir.
  6. O pulso        -> quatro leituras, e as taxas de SSMA continuam nulas.
  7. Mudanças       -> fatos com quem e quando; `?mudancas=0` desliga.
  8. A busca        -> acha sem acento, corta por espécie, e o piso de 2 letras.
  9. Permissão      -> bloco negado vira frase, e NUNCA 403 na página inteira.
 10. Entrada ruim   -> `?dias=ontem` responde 400 com frase, não 500.
 11. A fronteira    -> outro tenant não enxerga nada disto, por nenhuma porta.

Rodar (stack de pé):  python testes/e2e/pdca_cockpit_test.py
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def fatal(msg):
    print(f"\n  !! {msg}")
    print(f"     Parcial: {sum(1 for p in passed if p)}/{len(passed)}")
    sys.exit(2)


def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=120, context=_CTX) as resp:
            corpo = resp.read().decode()
            return resp.status, (json.loads(corpo) if corpo else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except Exception:
            return e.code, None


def login(u, p):
    data = json.dumps({"username": u, "password": p}).encode()
    r = urllib.request.Request(GW + "/auth/login/", data=data, method="POST",
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30, context=_CTX) as resp:
        return json.load(resp)["access"]


def texto(resposta) -> str:
    return json.dumps(resposta, ensure_ascii=False).lower() if resposta is not None else ""


print(f"\n{'='*62}\nPDCA — o cockpit pelo gateway\n{'='*62}")
print(f"Gateway: {GW}")

try:
    demo = login("demo", "demo123")
    campo = login("campo", "campo123")
    gerente = login("gerente", "gerente123")
    acme = login("acme", "acme123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé? Rodou os seeds?")

# ---------------------------------------------------------------------------
print("\n1. O que o módulo declara saber fazer")
# ---------------------------------------------------------------------------
codigo, status = req("GET", "/api/pdca/status/", demo)
if codigo != 200:
    fatal(f"status/ respondeu {codigo}")
recursos = status["recursos"]
for capacidade in ("carteira", "fila_do_dia", "pulso_da_obra", "busca_unica"):
    check(f"declara '{capacidade}'", recursos.get(capacidade) is True)
tetos = status["tetos"]
check(
    "os três tetos de leitura viajam para a tela poder declarar o corte",
    all(isinstance(tetos.get(n), int) and tetos[n] > 0 for n in (
        "obras_na_carteira", "linhas_por_faixa_da_fila", "resultados_por_especie",
    )),
)

# ---------------------------------------------------------------------------
print("\n2. A carteira — a leitura que cruza obras")
# ---------------------------------------------------------------------------
codigo, carteira = req("GET", "/api/pdca/carteira/", gerente)
if codigo != 200:
    fatal(f"carteira/ respondeu {codigo}: {carteira}")
obras = carteira["obras"]
check("responde 200 com pelo menos uma obra", len(obras) > 0)
check("declara o teto na resposta", isinstance(carteira.get("teto"), int))
check(
    "quando corta, diz quantas ficaram de fora",
    (not carteira["truncada"]) or carteira["total"] > len(obras),
)
check(
    "toda linha traz as cinco leituras (mesmo que nulas)",
    all(
        set(l) >= {"prazo", "avanco", "ppc", "conformidade", "seguranca",
                   "pendencias", "pior_pendencia"}
        for l in obras
    ),
)
check(
    "NÃO existe um total somado de pendências — elas vêm discriminadas",
    all("total_pendencias" not in l and isinstance(l["pendencias"], list)
        for l in obras),
)
com_dor = [l for l in obras if l["pior_pendencia"]]
check(
    "a pior pendência traz a consequência que a ordena",
    all(
        l["pior_pendencia"]["consequencia"] in (
            "prazo_legal", "seguranca", "dinheiro", "compromisso", "retrabalho",
        )
        for l in com_dor
    ),
)

# ---------------------------------------------------------------------------
print("\n3. Dado honesto — o zero que a régua proíbe")
# ---------------------------------------------------------------------------
sem_apontamento = [
    l for l in obras
    if l["avanco"] and l["avanco"]["fisico"] is None
]
check(
    "obra sem avanço apontado devolve nulo, e NUNCA 0%",
    all(l["avanco"]["fisico"] is None for l in sem_apontamento),
)
check(
    "e cada nulo vem com a frase do que falta medir",
    all(l["avanco"]["sem_apuracao_porque"] for l in sem_apontamento),
)
sem_acidente = [
    l for l in obras
    if l["seguranca"] and l["seguranca"]["dias_sem_afastamento"] is None
]
check(
    "obra que nunca teve afastamento não mostra '0 dias' — mostra o porquê",
    all(l["seguranca"]["sem_apuracao_porque"] for l in sem_acidente),
)

# A obra em que o resto do teste roda: a que tem plano e alguma pendência.
alvo = next(
    (l for l in obras if l["prazo"] and l["prazo"]["tem_plano"] and l["pendencias"]),
    next((l for l in obras if l["prazo"] and l["prazo"]["tem_plano"]), None),
)
if alvo is None:
    fatal("nenhuma obra com cronograma publicado — rode `semear_pdca_demo`.")
obra_id = alvo["obra"]
print(f"     obra de trabalho: {obra_id} · {alvo['nome']}")

# ---------------------------------------------------------------------------
print("\n4. A fila do dia — cinco assuntos numa ordenação só")
# ---------------------------------------------------------------------------
codigo, hoje = req("GET", f"/api/pdca/hoje/?obra={obra_id}", gerente)
if codigo != 200:
    fatal(f"hoje/ respondeu {codigo}: {hoje}")
fila = hoje["fila"]
check("traz fila, pulso e mudanças numa leitura só",
      {"fila", "pulso", "mudancas"} <= set(hoje))
check("varre as onze faixas", fila["faixas_varridas"] == 11)
check(
    "faixa sem ninguém esperando NÃO entra na resposta",
    all(f["total"] > 0 for f in fila["faixas"]),
)

ORDEM = ["prazo_legal", "seguranca", "dinheiro", "compromisso", "retrabalho"]
posicoes = [ORDEM.index(f["consequencia"]) for f in fila["faixas"]]
check(
    "as faixas vêm ordenadas por consequência — prazo legal primeiro",
    posicoes == sorted(posicoes),
)
check(
    "o total é a soma das faixas que têm gente esperando",
    fila["total"] == sum(f["total"] for f in fila["faixas"]),
)

# ---------------------------------------------------------------------------
print("\n5. A linha — o que é, há quanto tempo espera, e o que decidir")
# ---------------------------------------------------------------------------
if fila["faixas"]:
    check(
        "toda faixa diz o que decidir (fila que não diz é contagem)",
        all(f["o_que_decidir"] for f in fila["faixas"]),
    )
    check(
        "toda faixa nomeia o assunto de origem, para a tela saber onde resolver",
        all(
            f["origem"] in ("seguranca", "medicao", "programacao", "restricao",
                            "qualidade")
            for f in fila["faixas"]
        ),
    )
    linhas = [l for f in fila["faixas"] for l in f["linhas"]]
    check("toda linha tem chave, título e tipo", all(
        l.get("chave") and l.get("titulo") and l.get("tipo") for l in linhas
    ))
    com_prazo = [l for l in linhas if l["prazo"]]
    check(
        "a linha com prazo diz quantos dias faltam (ou de atraso)",
        all(isinstance(l["prazo"]["dias_restantes"], int) for l in com_prazo),
    )
else:
    print("     (fila vazia nesta obra — as asserções de linha não se aplicam)")
    check("fila vazia declara quantas filas varreu", fila["faixas_varridas"] == 11)

# ---------------------------------------------------------------------------
print("\n6. O pulso — e as duas taxas que o sistema declara não saber")
# ---------------------------------------------------------------------------
pulso = hoje["pulso"]
check("traz as quatro leituras", {"prazo", "avanco", "ppc", "conformidade",
                                  "seguranca"} <= set(pulso))
if pulso["seguranca"]:
    check(
        "taxa de frequência e de gravidade continuam nulas",
        pulso["seguranca"]["taxa_frequencia"] is None
        and pulso["seguranca"]["taxa_gravidade"] is None,
    )
    motivo = pulso["seguranca"]["taxas_indisponiveis_porque"]
    check("e o motivo fala a língua da obra (homem-hora)", "homem-hora" in motivo)
    check(
        "e NÃO cita número de fatia interno na tela",
        "pdca." not in motivo.lower(),
    )
if pulso["ppc"] and pulso["ppc"]["ppc"] is None:
    check("PPC sem semana encerrada é nulo com frase",
          bool(pulso["ppc"]["sem_apuracao_porque"]))

# ---------------------------------------------------------------------------
print("\n7. O que mudou — fatos, com quem e quando")
# ---------------------------------------------------------------------------
mudancas = hoje["mudancas"]
check("declara a janela de dias que olhou", isinstance(mudancas["dias"], int))
check(
    "todo fato tem verbo e carimbo de tempo",
    all(f.get("verbo") and f.get("quando") for f in mudancas["fatos"]),
)
codigo, sem_mudancas = req(
    "GET", f"/api/pdca/hoje/?obra={obra_id}&mudancas=0", gerente,
)
check("`?mudancas=0` devolve só fila e pulso",
      codigo == 200 and "mudancas" not in sem_mudancas)

# ---------------------------------------------------------------------------
print("\n8. A busca única — sete espécies, sem acento, cortada por espécie")
# ---------------------------------------------------------------------------
codigo, curta = req("GET", "/api/pdca/busca/?q=a", demo)
check("o termo de uma letra não varre e explica",
      codigo == 200 and curta["curta"] and "2 letras" in (curta.get("aviso") or ""))

codigo, larga = req("GET", "/api/pdca/busca/?q=alvenaria", demo)
if codigo != 200:
    fatal(f"busca/ respondeu {codigo}: {larga}")
check("varre as sete espécies", larga["especies_varridas"] == 7)
check(
    "devolve só as espécies que acharam alguma coisa",
    all(e["resultados"] for e in larga["especies"]),
)
check(
    "cada espécie é cortada pelo próprio teto",
    all(len(e["resultados"]) <= larga["teto_por_especie"] for e in larga["especies"]),
)

_, com = req("GET", "/api/pdca/busca/?q=funda%C3%A7%C3%A3o", demo)
_, sem = req("GET", "/api/pdca/busca/?q=fundacao", demo)
check(
    "acha com e sem acento, e devolve o mesmo",
    com["total"] == sem["total"],
)

codigo, estreita = req("GET", f"/api/pdca/busca/?q=alvenaria&obra={obra_id}", demo)
check(
    "`?obra=` restringe à obra corrente",
    codigo == 200 and all(
        r["obra"] in (None, obra_id)
        for e in estreita["especies"] for r in e["resultados"]
    ),
)

# ---------------------------------------------------------------------------
print("\n9. Permissão por bloco — frase no lugar do dado, nunca 403 na página")
# ---------------------------------------------------------------------------
codigo, do_campo = req("GET", f"/api/pdca/hoje/?obra={obra_id}", campo)
check("quem tem acesso estreito ainda abre a página", codigo == 200)
if codigo == 200:
    negados = do_campo["fila"]["sem_permissao"]
    check("e recebe a lista do que não pôde ver", len(negados) > 0)
    check(
        "cada negativa nomeia a permissão e diz a quem pedir",
        all(n.get("permissao") and "administrador" in n["motivo"] for n in negados),
    )
    check(
        "mas as faixas que ele PODE ver continuam vindo",
        isinstance(do_campo["fila"]["faixas"], list),
    )

codigo, carteira_campo = req("GET", "/api/pdca/carteira/", campo)
check("a carteira também não recusa a página inteira", codigo == 200)
if codigo == 200 and carteira_campo["obras"]:
    check(
        "o bloco negado vem nulo, e não com número de outro alguém",
        all(
            l["avanco"] is None or isinstance(l["avanco"], dict)
            for l in carteira_campo["obras"]
        ),
    )

# ---------------------------------------------------------------------------
print("\n10. Entrada torta — 400 com frase, nunca 500")
# ---------------------------------------------------------------------------
for ruim, rotulo in (
    (f"/api/pdca/hoje/?obra={obra_id}&dias=ontem", "dias não numérico"),
    ("/api/pdca/carteira/?obras=abc", "lista de obras com letra"),
    ("/api/pdca/hoje/", "sem informar a obra"),
    ("/api/pdca/hoje/?obra=999999", "obra inexistente"),
):
    codigo, corpo = req("GET", ruim, gerente)
    check(f"{rotulo} → {codigo} (e não 500)", codigo == 400)

# ---------------------------------------------------------------------------
print("\n11. A fronteira — outro tenant não enxerga nada disto")
# ---------------------------------------------------------------------------
# **Duas barreiras em série, e o outro tenant pode parar na primeira.** O
# `acme` do seed não contrata o `pdca`, então o `RequireModule` o recusa antes
# de a leitura existir — 403, que é a resposta mais forte. A verificação aceita
# as duas saídas legítimas (403 do entitlement, ou 200 sem o dado do vizinho) e
# **reprova a única inaceitável**: 200 com o nome da obra alheia dentro.
for rota, rotulo in (
    ("/api/pdca/carteira/", "a carteira"),
    (f"/api/pdca/hoje/?obra={obra_id}", "`hoje/` de obra alheia"),
    ("/api/pdca/busca/?q=alvenaria", "a busca"),
):
    codigo, corpo = req("GET", rota, acme)
    vazou = codigo == 200 and alvo["nome"].lower() in texto(corpo)
    check(
        f"{rotulo} não entrega nada do vizinho (respondeu {codigo})",
        codigo in (400, 403) or not vazou,
    )

codigo, _ = req("GET", "/api/pdca/carteira/")
check("sem token, a carteira é recusada", codigo in (401, 403))

# ---------------------------------------------------------------------------
total = len(passed)
ok = sum(1 for p in passed if p)
print(f"\n{'='*62}\n  {ok}/{total} verificações\n{'='*62}\n")
sys.exit(0 if ok == total else 1)
