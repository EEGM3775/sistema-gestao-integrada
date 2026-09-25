"""
Teste de browser: simula um usuário comum navegando pelo Sistema de Gestão.
Fluxo: Login → Lista de Clientes → Verifica dados tenant-scoped
"""
import os, sys
from playwright.sync_api import sync_playwright, expect

from _segundo_fator import responder_no_navegador

FRONTEND = "http://localhost:5173"
ERP_API  = "http://localhost:8000/api"

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        shots_dir = "/tmp/sgi_screenshots"
        os.makedirs(shots_dir, exist_ok=True)

        # ── 1. Página de Login ────────────────────────────────────────────────
        print("→ Abrindo login...")
        page.goto(f"{FRONTEND}/login")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"{shots_dir}/01_login.png")
        print(f"  Screenshot salvo: {shots_dir}/01_login.png")

        # ── 2. Autenticar como admin (superusuário backend) ───────────────────────
        print("→ Fazendo login como admin...")
        page.fill("input#username", "admin")
        page.fill("input#password", "admin123")
        page.screenshot(path=f"{shots_dir}/02_login_preenchido.png")
        page.click("button[type=submit]")
        responder_no_navegador(page)
        page.wait_for_url("**/clientes", timeout=10000)
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"{shots_dir}/03_clientes.png")
        print(f"  Redirecionado para: {page.url}")
        print(f"  Screenshot: {shots_dir}/03_clientes.png")

        # ── 3. Verificar dados na lista de clientes ───────────────────────────
        print("→ Verificando clientes na tabela...")
        page.wait_for_selector("table", timeout=5000)
        rows = page.query_selector_all("tbody tr")
        print(f"  Clientes exibidos: {len(rows)}")
        for r in rows:
            cells = r.query_selector_all("td")
            if cells:
                print(f"    • {cells[0].inner_text()} | {cells[2].inner_text()}")

        # ── 4. Abrir modal de adição ──────────────────────────────────────────
        print("→ Abrindo modal 'Adicionar Cliente'...")
        page.click("button:has-text('Adicionar Cliente')")
        page.wait_for_selector(".modal-content", timeout=3000)
        page.screenshot(path=f"{shots_dir}/04_modal_adicionar.png")
        print(f"  Screenshot: {shots_dir}/04_modal_adicionar.png")
        page.keyboard.press("Escape")

        # ── 5. Navegar para Empreendimentos ───────────────────────────────────
        print("→ Navegando para Empreendimentos...")
        page.click("text=Empreendimentos")
        page.wait_for_url("**/empreendimentos", timeout=5000)
        page.screenshot(path=f"{shots_dir}/05_empreendimentos.png")
        print(f"  Screenshot: {shots_dir}/05_empreendimentos.png")

        browser.close()
        print("\n✓ Teste concluído. Screenshots em:", shots_dir)
        return shots_dir

if __name__ == "__main__":
    run()
