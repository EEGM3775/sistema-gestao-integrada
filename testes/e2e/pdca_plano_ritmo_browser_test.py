"""PDCA › PLANO, vista Ritmo — a linha de balanço no NAVEGADOR, pelo gateway (8090).

**Substitui o `pdca6_ritmo_browser_test.py`** (D195): aquele dirigia
`/app/pdca/obra/{id}/cronograma/{id}`, a tela apagada no redesenho de
20/09/2026. A linha de balanço mora hoje no posto `PLANO`, como a vista *Ritmo*
(`/app/pdca/o/{id}/plano?vista=ritmo`, planta §5.3), e este roteiro carrega a
régua do antigo para lá.

O [pdca6_linha_de_balanco_test.py](pdca6_linha_de_balanco_test.py) prova a API
inteira. Este prova o que só existe na tela:

  1. a vista **Ritmo** está ao lado do Cronograma, no mesmo posto, e mora no
     endereço — o link colado abre nela;
  2. **o gráfico é desenhado de verdade** — uma faixa por serviço no `<svg>`, e
     é a inclinação dela que é a informação;
  3. o eixo Y traz os pavimentos, e a legenda diz o ritmo em **número**;
  4. **o gargalo é apontado**, com o que isso significa para a entrega — a
     leitura que a linha de balanço tem e o Gantt não;
  5. **o choque de equipe é dito por escrito**, com o lugar e os dias — só o
     desenho obrigaria a medir a tela com o dedo;
  6. a vista e as faixas **sobrevivem ao F5**;
  7. a barra e a reta contam a **mesma história**: o Cronograma mostra as
     atividades que o traço criou;
  8. e a tela fica **parada** — sem laço de renderização, sem erro de JS.

**O que o antigo cobrava e não veio, e por quê:** "desenhar um serviço pela tela"
e "simular antes de gravar" (§5–§6 do `pdca6_ritmo`). A vista nova é de
**leitura** — a planta §5.3 a descreve como "retas local × tempo, ritmo,
sincronia, gargalo", e o plano se monta pela grade e pelo Gantt do mesmo posto.
O traço por ritmo continua na API (`POST cronogramas/{id}/ritmo/`), coberto pelo
roteiro de API; é por ela que este cenário é montado.

Rodar (stack de pé, imagens `erp` e `react` rebuildadas):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/pdca_plano_ritmo_browser_test.py
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
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_plano_ritmo")
MARCA = "E2E Ritmo " + uuid.uuid4().hex[:6]

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


def faixas(pagina):
    """Uma faixa por serviço: o `<g>` de cada uma carrega o `<title>` com o ritmo."""
    return pagina.locator("svg g:has(> title)")


print(f"\n{'='*62}\nPDCA › PLANO — a vista Ritmo no navegador\n{'='*62}")
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

#: Dois serviços que sobem a torre em ritmos diferentes: a alvenaria rápida na
#: frente, a elétrica lenta atrás e começando junto — a rápida alcança a lenta
#: e as duas equipes se encontram no mesmo pavimento (o choque), e a lenta dita
#: o ritmo da torre (o gargalo).
for corpo in (
    {"nome": "Alvenaria", "codigo": "1", "inicio": segunda.isoformat(),
     "duracao_por_local": 2, "ritmo_dias": 2},
    {"nome": "Elétrica", "codigo": "2", "inicio": segunda.isoformat(),
     "duracao_por_local": 6, "ritmo_dias": 6},
):
    status, resposta = req("POST", f"/api/pdca/cronogramas/{crono_id}/ritmo/", demo,
                           {**corpo, "locais": pavimentos})
    if status not in (200, 201):
        fatal(f"traço de {corpo['nome']} falhou ({status}: {resposta})")

status, balanco = req("GET", f"/api/pdca/cronogramas/{crono_id}/linha-de-balanco/", demo)
if status != 200:
    fatal(f"linha-de-balanco/ respondeu {status}")
gargalo = next((l for l in balanco["linhas"] if l["servico"] == balanco["gargalo"]), None)
check("obra, torre de 4 pavimentos, plano e dois serviços traçados", True)
check("o servidor vê o choque e o gargalo (é o que a tela tem de mostrar)",
      bool(balanco["conflitos"]) and gargalo is not None)

# --- A tela -----------------------------------------------------------------
with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = navegador.new_context(viewport={"width": 1500, "height": 950})
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

    print("\n2. A vista Ritmo, ao lado do Cronograma, no mesmo posto")
    pagina.goto(f"{GW}/app/pdca/o/{obra_id}/plano")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(2000)
    check("o posto PLANO abre", f"/o/{obra_id}/plano" in pagina.url)
    ritmo = pagina.get_by_role("button", name="Ritmo", exact=True)
    check("a vista **Ritmo** está entre as vistas do plano", ritmo.count() > 0)
    check("e o Cronograma continua sendo a vista de abertura",
          "vista=" not in pagina.url)
    ritmo.first.click()
    pagina.wait_for_timeout(2200)
    pagina.wait_for_load_state("networkidle")
    check("a vista mora no endereço — o link colado abre nela",
          "vista=ritmo" in pagina.url)

    print("\n3. O gráfico é DESENHADO — não é uma tabela com cara de gráfico")
    check("existe o SVG da linha de balanço", pagina.locator("svg g:has(> title)").count() > 0)
    check("com uma faixa por serviço — é a INCLINAÇÃO que informa",
          faixas(pagina).count() == 2)
    corpo = pagina.inner_text("body")
    baixo = corpo.lower()
    check("o eixo Y traz os pavimentos, na ordem em que a obra sobe",
          "1º pavimento" in corpo and "4º pavimento" in corpo)
    #: `<title>` de SVG não tem `innerText` — o texto sai por `textContent`.
    titulos = " ".join((t or "").lower() for t in pagina.locator("svg g > title").all_text_contents())
    check("e cada faixa diz o ritmo em NÚMERO ('mais inclinado' não é medida)",
          "locais por semana" in titulos)
    check("cada faixa leva o nome do serviço escrito ao lado (rótulo direto, não legenda de cor)",
          "alvenaria" in baixo and "elétrica" in baixo)
    pagina.screenshot(path=f"{SHOTS}/01_ritmo.png", full_page=True)

    print("\n4. O gargalo — a leitura que o Gantt não tem")
    check("o gargalo é apontado", "gargalo — dita o ritmo de todos" in baixo)
    check("pelo nome do serviço que segura a torre",
          gargalo is not None and gargalo["nome"].lower() in baixo)
    check("e a tela diz o que isso significa para a entrega",
          "acelerar qualquer outro serviço não adianta" in baixo)

    print("\n5. O choque de equipe é dito POR ESCRITO")
    check("o painel diz que há duas equipes no mesmo lugar",
          "duas equipes no mesmo lugar" in baixo)
    conflito = balanco["conflitos"][0]
    check("nomeando o lugar do encontro",
          conflito["local_rotulo"].lower() in baixo)
    check("e quantos dias as equipes se sobrepõem",
          f"{conflito['dias']} dia" in baixo)

    print("\n6. F5 — a vista e as faixas continuam lá")
    pagina.reload()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(2200)
    check("depois do F5 a tela continua na vista Ritmo", "vista=ritmo" in pagina.url)
    check("e as duas faixas continuam desenhadas", faixas(pagina).count() == 2)

    print("\n7. A barra e a reta contam a MESMA história (planta §5.3)")
    pagina.get_by_role("button", name="Cronograma", exact=True).first.click()
    pagina.wait_for_timeout(2200)
    corpo = pagina.inner_text("body")
    check("o Cronograma mostra as atividades que o traço criou",
          "Elétrica" in corpo and "Alvenaria" in corpo)

    print("\n8. Com a tela parada não pode haver requisição")
    pagina.get_by_role("button", name="Ritmo", exact=True).first.click()
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
print("\n9. Faxina")
status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
check("a obra do teste sai (vai para a lixeira, que é o desenho)",
      status in (200, 204))
print(
    "\n     O cronograma fica em rascunho e sai com a obra. Para devolver o\n"
    "     ambiente ao estado anterior:\n"
    "       docker exec sgi-erp python manage.py limpar_residuo_e2e --confirmar"
)

ok = sum(1 for p in passed if p)
print(f"\n{'='*62}\nPDCA › PLANO, Ritmo (tela): {ok}/{len(passed)} verificações\n{'='*62}")
sys.exit(0 if ok == len(passed) else 1)
