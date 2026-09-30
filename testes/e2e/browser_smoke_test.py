"""
Teste de browser: simula um usuário comum navegando pelo Sistema de Gestão.
Fluxo: Login → Clientes → formulário de novo cliente → Empreendimentos

Entra pelo gateway (:8090), como qualquer pessoa: o stack não sobe o Vite
(:5173), e desde a fase 5 (BFF) a sessão é um cookie do gateway — pelo Vite não
haveria sessão para testar (D223).

Rodar (stack de pé):  ~/sgi_e2e_venv.sh testes/e2e/browser_smoke_test.py
"""
import os
import sys

from playwright.sync_api import sync_playwright

from _segundo_fator import responder_no_navegador

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")

passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def run():
    shots_dir = os.environ.get("SGI_SHOTS", "/tmp/sgi_screenshots")
    os.makedirs(shots_dir, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        erros_js = []
        page.on("pageerror", lambda e: erros_js.append(str(e)))

        # ── 1. Página de Login ────────────────────────────────────────────────
        print("→ Abrindo login...")
        page.goto(f"{GW}/login")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"{shots_dir}/01_login.png")
        check("a tela de login abre", page.locator("input#username").count() == 1)

        # ── 2. Autenticar como admin (tem segundo fator) ──────────────────────
        print("→ Fazendo login como admin...")
        page.fill("input#username", "admin")
        page.fill("input#password", "admin123")
        page.click("button[type=submit]")
        responder_no_navegador(page)
        page.wait_for_url("**/app/**", timeout=20000)
        check("entrou e caiu dentro do /app", "/app" in page.url)

        # ── 3. Clientes ───────────────────────────────────────────────────────
        print("→ Abrindo Clientes...")
        page.goto(f"{GW}/app/clientes")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path=f"{shots_dir}/02_clientes.png")
        check("a carteira de clientes abre", page.get_by_role("heading", name="Clientes").count() > 0)
        corpo = page.inner_text("body").lower()
        check("e não fica presa no carregando", "carregando" not in corpo)

        # ── 4. Formulário de novo cliente ─────────────────────────────────────
        print("→ Abrindo 'Novo cliente'...")
        page.get_by_role("button", name="Novo cliente").click()
        titulo = page.get_by_role("heading", name="Novo Cliente")
        titulo.wait_for(timeout=5000)
        page.screenshot(path=f"{shots_dir}/03_novo_cliente.png")
        check("o formulário de novo cliente abre", titulo.count() == 1)
        page.get_by_role("button", name="Cancelar").click()
        check("e fecha no Cancelar", page.get_by_role("heading", name="Novo Cliente").count() == 0)

        # ── 5. Navegar para Empreendimentos pela barra lateral ────────────────
        print("→ Navegando para Empreendimentos...")
        page.locator("a[href='/app/empreendimentos']").first.click()
        page.wait_for_url("**/app/empreendimentos", timeout=10000)
        page.screenshot(path=f"{shots_dir}/04_empreendimentos.png")
        check("a barra lateral leva a Empreendimentos", page.url.endswith("/app/empreendimentos"))

        check(f"nenhum erro de JavaScript ({len(erros_js)})", not erros_js)
        for e in erros_js[:4]:
            print(f"       · {e[:160]}")

        browser.close()
    print(f"\nScreenshots em: {shots_dir}")
    ok = sum(passed)
    print(f"Smoke: {ok}/{len(passed)}")
    return ok == len(passed)


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
