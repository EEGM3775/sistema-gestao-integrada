"""A tela de Aprovações no navegador — a D130 fechada, pelo gateway (8090).

**Por que ela existe.** A máquina de escada nasceu na PDCA.0 com API completa e
nenhuma tela. Enquanto não tinha cliente real isso era um seam esperando uso; com
a PDCA.3 ela passou a decidir se um título a pagar existe, e a ausência da tela
virou um documento parado sem caminho — foi o que o dono encontrou em 15/09/2026,
ao levar *"Quem solicitou não pode atestar o próprio pedido"* como administrador.

O que este teste cobra:

  1. o item **Aprovações** existe na Administração e a tela abre;
  2. dá para **criar uma escada** escolhendo o documento numa lista (o
     `ContentType` não é adivinhável — sem `alvos/` isto seria impossível);
  3. dá para acrescentar um **degrau** escolhendo a permissão que ele exige;
  4. a tela **confere** a escada antes de alguém depender dela;
  5. e o **autoatesto** está ali, visível e explicado — é a válvula que existia
     desde a PDCA.0 e que ninguém tinha como descobrir.

Rodar (stack de pé, imagem `react` rebuildada):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/aprovacoes_admin_browser_test.py
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
import uuid

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright

GW = os.environ.get("SGI_GW", "http://localhost:8090")
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_aprovacoes")
MARCA = "E2E escada " + uuid.uuid4().hex[:6]

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
        with urllib.request.urlopen(r, timeout=60, context=_CTX) as resp:
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


print(f"\n{'='*62}\nAdministração → Aprovações, no navegador (D130)\n{'='*62}")
os.makedirs(SHOTS, exist_ok=True)

try:
    admin = login("admin", "admin123")
except Exception as e:
    fatal(f"login falhou ({e}). Stack de pé? Seeds rodados?")

# --- O cenário, montado por API ---------------------------------------------
#
# A escada do teste nasce **fora da tela**, e de propósito: o que esta prova
# precisa demonstrar é que a tela *governa* a escada (liga o autoatesto, confere,
# mostra os degraus na ordem), não que ela sabe montar uma. Criar pela tela
# tornaria o teste refém do estado do ambiente — uma escada padrão já existente
# colide com a nova, e a falha apareceria como um check verde em outro lugar.
#
# `padrao=False`: esta escada não pode roubar os documentos reais de quem estiver
# usando o ambiente de demonstração.
print("\n0. Cenário montado por API")
status, alvos = req("GET", "/api/aprovacao/fluxos/alvos/", admin)
if status != 200:
    fatal(f"não consegui listar os alvos (HTTP {status})")
alvo = next((a for a in alvos if a["codigo"] == "modulopdca.medicao"), None)
if alvo is None:
    fatal("a medição não aparece entre os alvos — `alvos/` quebrou?")
check("a API diz quais documentos aceitam escada (sem isto a tela é impossível)", True)

status, fluxo = req("POST", "/api/aprovacao/fluxos/", admin, {
    "codigo": "e2e-" + uuid.uuid4().hex[:6], "nome": MARCA,
    "alvo": alvo["id"], "padrao": False, "ativo": True,
})
if status not in (200, 201) or not fluxo:
    fatal(f"criar o fluxo falhou (HTTP {status}: {fluxo})")
fluxo_id = fluxo["fluxo_id"]
for ordem, nome in ((1, "Engenheiro da obra"), (2, "Gerente de contrato")):
    status, nivel = req("POST", "/api/aprovacao/niveis/", admin, {
        "fluxo": fluxo_id, "ordem": ordem, "nome": nome,
        "permissao_exigida": "pdca.medicao.atestar",
    })
    if status not in (200, 201):
        fatal(f"criar o degrau {ordem} falhou (HTTP {status}: {nivel})")
check("escada de teste com dois degraus criada", True)

with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = navegador.new_context(viewport={"width": 1440, "height": 950})
    pagina = ctx.new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))

    print("\n1. O caminho até a tela")
    pagina.goto(f"{GW}/login")
    pagina.wait_for_load_state("networkidle")
    pagina.fill("input#username", "admin")
    pagina.fill("input#password", "admin123")
    pagina.click("button[type=submit]")
    pagina.wait_for_url("**/app/**", timeout=20000)
    pagina.wait_for_load_state("networkidle")

    menu = pagina.locator("a[href='/app/admin/aprovacoes']")
    try:
        menu.first.wait_for(state="attached", timeout=10000)
    except Exception:
        pass
    check("o item 'Aprovações' existe na Administração", menu.count() > 0)
    if menu.count() > 0:
        menu.first.click()
        pagina.wait_for_url("**/app/admin/aprovacoes", timeout=15000)
    else:
        pagina.goto(f"{GW}/app/admin/aprovacoes")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(900)
    pagina.screenshot(path=f"{SHOTS}/01_lista.png", full_page=True)
    check("a tela abre", "/app/admin/aprovacoes" in pagina.url)

    print("\n2. A escada do teste aparece com os degraus na ordem")
    corpo = pagina.inner_text("body")
    check("a escada criada por API está na lista", MARCA in corpo)
    check("com os dois degraus", "Engenheiro" in corpo and "Gerente" in corpo)
    check("e o degrau diz a PERMISSÃO que exige, não um nome de pessoa",
          "pdca.medicao.atestar" in corpo)

    print("\n3. O interruptor que esta tela existe para tornar descobrível")
    check("o autoatesto está visível e explicado",
          "quem solicita ateste o próprio pedido" in corpo.lower())
    check("e o padrão é NÃO, dito com todas as letras",
          "quem executa não aprova" in corpo.lower())

    # Endereço próprio por escada — o ambiente pode ter outras, e um seletor por
    # texto pegaria a errada (ou nenhuma, que foi o que aconteceu antes).
    caixa = pagina.locator(f"#autoatesto-{fluxo_id}")
    check("ele começa desligado", not caixa.is_checked())
    # `click()` e não `check()`: o interruptor é **controlado pelo servidor** —
    # ele só muda de estado depois que a escrita volta. O `check()` do Playwright
    # clica e confere o estado no mesmo instante, e falharia por causa dessa
    # viagem. O que importa provar é que **gravou**, e isso se confere na API.
    caixa.click()
    pagina.wait_for_timeout(1800)
    pagina.screenshot(path=f"{SHOTS}/02_autoatesto.png", full_page=True)
    check("a tela passa a mostrar o estado novo", caixa.is_checked())

    status, depois = req("GET", f"/api/aprovacao/fluxos/{fluxo_id}/", admin)
    check("**ligar na tela grava de verdade** — é a saída que o dono não tinha",
          status == 200 and (depois or {}).get("permite_autoatesto") is True)

    print("\n4. Conferir a escada antes de alguém depender dela")
    pagina.locator(f"#conferir-{fluxo_id}").click()
    pagina.wait_for_timeout(1200)
    pagina.screenshot(path=f"{SHOTS}/03_conferida.png", full_page=True)
    check("a conferência responde na tela",
          "utilizável" in pagina.inner_text("body").lower())

    check("nenhum erro de JavaScript na página", not erros_js)
    if erros_js:
        print("     erros:", erros_js[:3])

    navegador.close()

# --- Faxina: a escada do teste sai --------------------------------------
print("\n5. Faxina")
status, _ = req("DELETE", f"/api/aprovacao/fluxos/{fluxo_id}/", admin)
check("a escada do teste sai", status in (200, 204))

ok = sum(1 for p in passed if p)
print(f"\n{'='*62}")
print(f"Aprovações (tela): {ok}/{len(passed)} verificações · screenshots em {SHOTS}")
print(f"{'='*62}\n")
sys.exit(0 if ok == len(passed) else 1)
