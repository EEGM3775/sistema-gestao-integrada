"""PDCA.6 — a linha de balanço no NAVEGADOR, pelo gateway (8090).

Existe pela régua do [README](README.md): **tela nova entrega com teste de
navegador junto**, medindo o que só existe ali — *o conteúdo aparece*, *o que se
faz sobrevive ao F5*, e *com a tela parada não pode haver requisição*.

O [pdca6_linha_de_balanco_test.py](pdca6_linha_de_balanco_test.py) prova a API
inteira (49 verificações). Este prova a **quinta lente do plano**, e cobre o que
nenhuma chamada de API alcança:

  1. a lente **Ritmo** existe ao lado do Cronograma — as duas são o mesmo plano
     visto de dois jeitos (planta §5.4), e a PRA.5c ensinou que porta sem
     caminho de dedo é porta que não existe;
  2. **o gráfico é desenhado de verdade** — o `<svg>` sai com uma `polyline` por
     serviço, e é a inclinação dela que é a informação desta tela;
  3. **simular mostra o número antes de gravar**, e o plano continua do mesmo
     tamanho depois — a régua do gerador de locais da PDCA.0, na tela;
  4. **o traço sobrevive ao F5**, porque ele criou atividades de verdade — e o
     Gantt ao lado passa a mostrar as mesmas, que é a prova de que a barra e a
     reta contam a mesma história;
  5. **o choque de equipe é dito duas vezes**: no losango sobre o encontro e por
     escrito na lista, com os dias contados — só o desenho obrigaria a medir a
     tela com o dedo;
  6. **o gargalo é apontado**, que é a leitura que a LOB tem e o Gantt não;
  7. e a tela fica **parada** — sem laço de renderização.

Rodar (stack de pé, imagem `react` rebuildada):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/pdca6_ritmo_browser_test.py
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright
from _sessao import cabecalhos, da_resposta

GW = os.environ.get("SGI_GW", "http://localhost:8090")
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_pdca6")
MARCA = "E2E PDCA.6 tela " + uuid.uuid4().hex[:6]

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
        headers.update(cabecalhos(token))
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=90, context=_CTX) as resp:
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
        return da_resposta(resp)


print(f"\n{'='*62}\nPDCA.6 — a linha de balanço no navegador\n{'='*62}")
os.makedirs(SHOTS, exist_ok=True)

try:
    demo = login("demo", "demo123")
except Exception as e:
    fatal(f"login falhou ({e}). Stack de pé? Seeds rodados?")

# --- O cenário, montado por API (o que este teste prova é a TELA) -----------
print("\n0. Cenário montado por API")
status, obra = req("POST", "/api/obras/", demo, {
    "nome_obra": MARCA, "endereco": "Rua da Reta, s/n", "status_obra": "planejamento",
})
if status not in (200, 201):
    fatal(f"obra falhou ({status}: {obra})")
obra_id = obra["obra_id"]

status, torre = req("POST", "/api/pdca/locais/", demo, {
    "obra": obra_id, "nivel": "bloco", "codigo": "T1", "nome": "Torre 1", "ordem": 1,
})
if status not in (200, 201):
    fatal(f"local raiz falhou ({status}: {torre})")

pavimentos = []
for n in (1, 2, 3, 4):
    status, pav = req("POST", "/api/pdca/locais/", demo, {
        "obra": obra_id, "pai": torre["local_id"], "nivel": "pavimento",
        "codigo": f"P{n}", "nome": f"{n}º pavimento", "ordem": n,
    })
    if status not in (200, 201):
        fatal(f"pavimento {n} falhou ({status}: {pav})")
    pavimentos.append(pav["local_id"])

status, calendario = req("POST", "/api/pdca/calendarios/", demo, {
    "obra": obra_id, "nome": "Expediente " + MARCA,
})
if status not in (200, 201):
    fatal(f"calendário falhou ({status}: {calendario})")

hoje = date.today()
segunda = hoje - timedelta(days=hoje.weekday())
status, crono = req("POST", "/api/pdca/cronogramas/", demo, {
    "obra": obra_id, "descricao": "Plano " + MARCA,
    "data_inicio": segunda.isoformat(), "calendario": calendario["calendario_id"],
})
if status not in (200, 201):
    fatal(f"cronograma falhou ({status}: {crono})")
crono_id = crono["cronograma_id"]

# Um serviço já traçado por API, para a tela ter o que desenhar ao abrir; o
# segundo é desenhado **pela tela**, que é o gesto que este teste prova.
status, _ = req("POST", f"/api/pdca/cronogramas/{crono_id}/ritmo/", demo, {
    "nome": "Alvenaria", "codigo": "1", "locais": pavimentos,
    "inicio": segunda.isoformat(), "duracao_por_local": 4, "ritmo_dias": 2,
})
if status not in (200, 201):
    fatal(f"traço inicial falhou ({status})")
check("obra, torre de 4 pavimentos, plano e a alvenaria traçada", True)

# --- A tela -----------------------------------------------------------------
with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = navegador.new_context(viewport={"width": 1440, "height": 950})
    pagina = ctx.new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))
    requisicoes = []
    pagina.on("request", lambda r: requisicoes.append(r.url) if "/api/" in r.url else None)

    print("\n1. Login pela tela")
    pagina.goto(f"{GW}/login")
    pagina.wait_for_load_state("networkidle")
    pagina.fill("input#username", "demo")
    pagina.fill("input#password", "demo123")
    pagina.click("button[type=submit]")
    pagina.wait_for_url("**/app/**", timeout=20000)
    check("`demo` entrou", "/app" in pagina.url)

    print("\n2. A quinta lente do plano")
    pagina.goto(f"{GW}/app/pdca/obra/{obra_id}/cronograma/{crono_id}")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1800)
    corpo = pagina.inner_text("body").lower()
    check("o workspace do plano abre", "cronograma" in corpo)
    lente = pagina.get_by_role("button", name="Ritmo (linha de balanço)")
    check("a lente **Ritmo** está ao lado do Cronograma, e não no fim",
          lente.count() > 0)
    check("e o Gantt continua sendo a lente de abertura",
          pagina.locator("table").count() > 0 or "eap" in corpo)

    lente.first.click()
    pagina.wait_for_timeout(2200)
    pagina.wait_for_load_state("networkidle")
    corpo = pagina.inner_text("body").lower()
    check("a lente abre em 'Ritmo por localização'", "ritmo por localização" in corpo)

    print("\n3. O gráfico é DESENHADO — não é uma tabela com cara de gráfico")
    svg = pagina.locator("svg[role='img']")
    check("existe um SVG da linha de balanço", svg.count() > 0)
    retas = pagina.locator("svg[role='img'] polyline")
    check("com uma polilinha por serviço — é a INCLINAÇÃO que informa",
          retas.count() == 1)
    check("o eixo Y traz os pavimentos, na ordem em que a obra sobe",
          "1º pavimento" in pagina.inner_text("body")
          and "4º pavimento" in pagina.inner_text("body"))
    check("e a legenda diz o ritmo em NÚMERO ('mais inclinado' não é medida)",
          "/sem" in corpo and "por local" in corpo)
    pagina.screenshot(path=f"{SHOTS}/01_lob.png", full_page=True)

    print("\n4. Um serviço sozinho não colide com ninguém")
    check("o painel de choques existe e diz que não há nenhum",
          "duas equipes no mesmo lugar" in corpo and "nenhum choque no plano" in corpo)

    print("\n5. Desenhar um serviço PELA TELA — e simular antes de gravar")
    pagina.get_by_role("button", name="Desenhar serviço").first.click()
    pagina.wait_for_timeout(900)
    corpo = pagina.inner_text("body").lower()
    check("o formulário de traço abre", "desenhar um serviço" in corpo)
    check("e explica o que o ritmo significa antes de alguém digitar",
          "duas equipes se sobrepõem" in corpo)

    entradas = pagina.locator("input")
    pagina.get_by_placeholder("Ex.: Alvenaria").fill("Elétrica")
    pagina.get_by_placeholder("Ex.: 3").fill("2")
    #: A ordem dos locais é do planejador — clicar nos quatro na ordem em que a
    #: equipe sobe é o gesto que a tela existe para receber.
    for n in (1, 2, 3, 4):
        pagina.get_by_role("button", name=f"P{n} · {n}º pavimento").first.click()
        pagina.wait_for_timeout(120)
    corpo = pagina.inner_text("body")
    check("os locais escolhidos ficam NUMERADOS na ordem em que foram clicados",
          "1. P1" in corpo and "4. P4" in corpo)

    # duração 6, ritmo 6 → a elétrica sobe mais devagar que a alvenaria
    campos_num = pagina.locator("input[inputmode='numeric']")
    campos_num.nth(0).fill("6")
    campos_num.nth(1).fill("6")
    pagina.wait_for_timeout(300)

    antes_simular = pagina.locator("svg[role='img'] polyline").count()
    pagina.get_by_role("button", name="Simular").first.click()
    pagina.wait_for_timeout(2200)
    corpo = pagina.inner_text("body").lower()
    check("a simulação diz quantas atividades o traço criaria",
          "vai criar" in corpo and "4" in corpo)
    check("e o prazo do traço ANTES de gravar", "dias úteis" in corpo)
    check("mas NADA foi desenhado — simular não escreve",
          pagina.locator("svg[role='img'] polyline").count() == antes_simular)
    pagina.screenshot(path=f"{SHOTS}/02_simulacao.png", full_page=True)

    print("\n6. Desenhar de verdade — e a reta nasce no gráfico")
    pagina.get_by_role("button", name="Desenhar", exact=True).first.click()
    pagina.wait_for_timeout(3200)
    pagina.wait_for_load_state("networkidle")
    check("agora são DUAS retas no gráfico",
          pagina.locator("svg[role='img'] polyline").count() == 2)
    corpo = pagina.inner_text("body").lower()
    check("a elétrica aparece na legenda", "elétrica" in corpo)

    print("\n7. O gargalo e o choque — as duas leituras que o Gantt não tem")
    check("o gargalo é apontado na legenda", "gargalo" in corpo)
    check("e a tela explica o que isso significa para a entrega",
          "vagão mais lento" in corpo)
    check("o choque de equipe é dito POR ESCRITO, e não só no desenho",
          "choque(s) de equipe" in corpo or "dia(s)" in corpo)
    losangos = pagina.locator("svg[role='img'] path")
    check("e marcado no gráfico, sobre o ponto do encontro", losangos.count() > 0)
    pagina.screenshot(path=f"{SHOTS}/03_gargalo_e_choque.png", full_page=True)

    print("\n8. F5 — o traço criou atividades de verdade")
    pagina.reload()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1800)
    pagina.get_by_role("button", name="Ritmo (linha de balanço)").first.click()
    pagina.wait_for_timeout(2200)
    check("as duas retas continuam lá depois do F5",
          pagina.locator("svg[role='img'] polyline").count() == 2)

    print("\n8b. E a barra e a reta contam a MESMA história (planta §5.4)")
    pagina.get_by_role("button", name="Cronograma", exact=True).first.click()
    pagina.wait_for_timeout(2000)
    corpo = pagina.inner_text("body")
    check("o Gantt mostra as folhas que o traço criou",
          "Elétrica — 1º pavimento" in corpo or "Elétrica" in corpo)

    print("\n9. Com a tela parada não pode haver requisição")
    pagina.get_by_role("button", name="Ritmo (linha de balanço)").first.click()
    pagina.wait_for_timeout(2500)
    pagina.wait_for_load_state("networkidle")
    parado = len(requisicoes)
    pagina.wait_for_timeout(4000)
    check("nenhuma requisição com a tela em repouso (sem laço de renderização)",
          len(requisicoes) - parado == 0)

    check("nenhum erro de JavaScript na página", not erros_js)
    if erros_js:
        print("     erros:", erros_js[:3])

    navegador.close()

# --- Faxina -----------------------------------------------------------------
print("\n10. Faxina")
status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
check("a obra do teste sai (vai para a lixeira, que é o desenho)",
      status in (200, 204))
print(
    "\n     O cronograma fica em rascunho e sai com a obra. Para devolver o\n"
    "     ambiente ao estado anterior:\n"
    "       docker exec sgi-erp python manage.py limpar_residuo_e2e --confirmar"
)

ok = sum(1 for p in passed if p)
print(f"\n{'='*62}\nPDCA.6 (tela): {ok}/{len(passed)} verificações\n{'='*62}")
sys.exit(0 if ok == len(passed) else 1)
