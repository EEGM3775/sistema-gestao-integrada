"""A porta por papel do PDCA **na tela** — §3.3 da planta do frontend.

Abrir a obra sem nomear posto (`/app/pdca/o/<id>`) cai no posto do papel, e o
rail continua com os seis: a porta escolhe onde se entra, não o que existe.

  1. `demo` — acumula `gestor_contratos`, `engenharia`, `tecnico_qualidade` e
     `planejador`: a precedência (dinheiro antes do compromisso) o põe em MEDIÇÃO;
  2. `gerente` — `diretoria`, quem assina: cai em HOJE, a fila de decisão;
  3. `campo` — só o papel de canteiro: a carteira mostra a passagem para a
     superfície de campo, e abrir a obra cai em HOJE (o campo não tira ninguém
     da obra que pediu).

Também cobra que clicar no **nome** da obra na carteira passa pela porta.

Rodar (stack de dev de pé, bundle novo no `sgi-react`):

    ~/sgi_e2e_venv.sh pdca_porta_por_papel_browser_test.py
"""
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright
from _segundo_fator import responder_no_navegador

GW = os.environ.get("SGI_GW", "http://localhost:8090")
SHOTS = os.environ.get("SGI_SHOTS", "/tmp")
ESPERA = 15_000
#: O gateway limita o login a 10/min por IP (burst 5): três entradas cabem,
#: mas espaçar não custa e evita o 429 quando o roteiro roda depois de outro.
INTERVALO_S = 8

passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")
    return bool(cond)


def fatal(msg):
    print(f"\n  !! {msg}")
    print(f"     Parcial: {sum(1 for p in passed if p)}/{len(passed)}")
    sys.exit(2)


def entrar(navegador, usuario, senha):
    ctx = navegador.new_context(viewport={"width": 1500, "height": 900})
    pagina = ctx.new_page()
    pagina.goto(f"{GW}/login", wait_until="networkidle")
    pagina.fill("input#username", usuario)
    pagina.fill("input#password", senha)
    pagina.click("button[type=submit]")
    try:
        responder_no_navegador(pagina)
        pagina.wait_for_url("**/app/**", timeout=25_000)
    except Exception as e:
        pagina.screenshot(path=f"{SHOTS}/e2e_porta_login_{usuario}.png")
        fatal(f"`{usuario}` não entrou ({str(e).splitlines()[0]}) — rode o seed da demo.")
    return ctx, pagina


def uma_obra(ctx):
    r = ctx.request.get(f"{GW}/api/pdca/carteira/")
    if r.status != 200 or not r.json().get("obras"):
        fatal(f"a carteira não respondeu com obras ({r.status}) — rode os seeds do PDCA.")
    return r.json()["obras"][0]


def abre_em(pagina, obra_id, posto):
    pagina.goto(f"{GW}/app/pdca/o/{obra_id}", wait_until="networkidle")
    try:
        pagina.wait_for_url(f"**/app/pdca/o/{obra_id}/{posto}", timeout=ESPERA)
    except Exception:
        pass
    return pagina.url.rstrip("/").endswith(f"/o/{obra_id}/{posto}")


print(f"\n{'='*62}\nPDCA — a porta por papel\n{'='*62}\nGateway: {GW}")

with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])

    print("\n1. `demo` (gestor de contratos, engenharia, qualidade, planejador)")
    ctx, pagina = entrar(navegador, "demo", "demo123")
    obra = uma_obra(ctx)
    obra_id = obra["obra"]
    check("abrir a obra sem posto cai em MEDIÇÃO", abre_em(pagina, obra_id, "medicao"))
    rail = pagina.locator("nav[aria-label='Postos de trabalho da obra']")
    check("o rail continua com os seis postos",
          rail.locator("a, div[title^='Requer']").count() == 6)
    pagina.goto(f"{GW}/app/pdca", wait_until="networkidle")
    pagina.get_by_text(obra["nome"][:18], exact=False).first.click()
    try:
        pagina.wait_for_url(f"**/app/pdca/o/{obra_id}/medicao", timeout=ESPERA)
    except Exception:
        pass
    check("o nome da obra na carteira entra pela porta", pagina.url.endswith("/medicao"))
    pagina.goto(f"{GW}/app/pdca", wait_until="networkidle")
    pagina.get_by_text(obra["nome"][:18], exact=False).first.wait_for(timeout=ESPERA)
    check("sem passagem para o campo (não é a porta dele)",
          pagina.get_by_text("A sua frente de hoje").count() == 0)
    pagina.screenshot(path=f"{SHOTS}/e2e_porta_demo.png")
    ctx.close()
    time.sleep(INTERVALO_S)

    print("\n2. `gerente` (diretoria)")
    ctx, pagina = entrar(navegador, "gerente", "gerente123")
    check("abrir a obra sem posto cai em HOJE", abre_em(pagina, obra_id, "hoje"))
    ctx.close()
    time.sleep(INTERVALO_S)

    print("\n3. `campo` (só o papel de canteiro)")
    ctx, pagina = entrar(navegador, "campo", "campo123")
    pagina.goto(f"{GW}/app/pdca", wait_until="networkidle")
    passagem = pagina.locator("a[href='/campo']", has_text="A sua frente de hoje")
    try:
        passagem.wait_for(timeout=ESPERA)
    except Exception:
        pass
    check("a carteira mostra a passagem para o campo", passagem.count() == 1)
    pagina.screenshot(path=f"{SHOTS}/e2e_porta_campo_carteira.png")
    if passagem.count():
        passagem.click()
        try:
            pagina.wait_for_url("**/campo", timeout=ESPERA)
        except Exception:
            pass
        check("a passagem leva à superfície de campo", pagina.url.rstrip("/").endswith("/campo"))
    check("abrir a obra sem posto cai em HOJE, sem sair da obra", abre_em(pagina, obra_id, "hoje"))
    ctx.close()

    navegador.close()

ok = sum(1 for x in passed if x)
print(f"\nResultado: {ok}/{len(passed)}")
sys.exit(0 if ok == len(passed) else 1)
