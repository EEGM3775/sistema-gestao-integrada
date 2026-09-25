"""Remodelagem da segurança, fase 1 — o segundo fator na tela, pelo gateway.

  1. O login do admin pede o código depois da senha; o código errado diz o que
     houve na tela, e o certo entra.
  2. Minha conta mostra o fator ativo, a janela de confirmação com a faixa do
     dono, e grava a escolha (o roteiro devolve o valor que encontrou).
  3. A lista de usuários do admin marca quem tem segundo fator.

Rodar (stack de pé, imagem `react` rebuildada):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/seg1_segundo_fator_browser_test.py
"""
import os
import sys

from _segundo_fator import codigo, responder_no_navegador

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright

GW = os.environ.get("SGI_GW", "http://localhost:8090")
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_segundo_fator")
passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


print(f"\n{'='*62}\nSegundo fator na tela (remodelagem, fase 1)\n{'='*62}")
os.makedirs(SHOTS, exist_ok=True)

with sync_playwright() as p:
    nav = p.chromium.launch()
    pagina = nav.new_context(viewport={"width": 1366, "height": 900}).new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))

    print("\n1. O login do admin")
    pagina.goto(f"{GW}/login", wait_until="networkidle")
    pagina.fill("input#username", "admin")
    pagina.fill("input#password", "admin123")
    pagina.click("button[type=submit]")
    pagina.wait_for_selector("input#codigo-segundo-fator", timeout=15_000)
    check("depois da senha, a tela pede o código do celular", pagina.get_by_text("Confirme que é você").count() > 0)
    pagina.screenshot(path=f"{SHOTS}/01_pede_codigo.png")

    certo = codigo(0)
    pagina.fill("input#codigo-segundo-fator", "000000" if certo != "000000" else "111111")
    pagina.click("button[type=submit]")
    pagina.wait_for_timeout(1500)
    check("código errado: a tela diz, em português, o que houve",
          pagina.get_by_text("Código incorreto ou já usado.").count() > 0)
    check("e continua no login", "/login" in pagina.url)
    pagina.screenshot(path=f"{SHOTS}/02_codigo_errado.png")

    responder_no_navegador(pagina)
    check(f"código certo entra ({pagina.url})", "/app" in pagina.url)

    print("\n2. Minha conta")
    pagina.goto(f"{GW}/app/conta", wait_until="networkidle")
    pagina.wait_for_selector("text=Segundo fator", timeout=15_000)
    check("o cartão do segundo fator diz que está ativo", pagina.get_by_text("Ativo desde").count() > 0)
    check("e oferece trocar de celular (o admin não desativa à toa)", pagina.get_by_role("button", name="Trocar de celular").count() > 0)
    check("a janela de confirmação está lá, marcada como em breve",
          pagina.get_by_text("Confirmação de atos graves").count() > 0 and pagina.get_by_text("em breve").count() > 0)
    campo = pagina.locator("input#janela-confirmacao")
    original = campo.input_value()
    campo.fill("500")
    check(f"a caixa não passa do teto do dono (digitado 500 → {campo.input_value()})", campo.input_value() == "120")
    check("e avisa o que isso significa", pagina.get_by_text("quem sentar nele pode").count() > 0)
    campo.fill("30")
    pagina.get_by_role("button", name="Salvar").click()
    pagina.wait_for_selector("text=Salvo.", timeout=10_000)
    pagina.reload(wait_until="networkidle")
    pagina.wait_for_selector("input#janela-confirmacao", timeout=15_000)
    check("a escolha sobrevive ao recarregar", pagina.locator("input#janela-confirmacao").input_value() == "30")
    pagina.screenshot(path=f"{SHOTS}/03_minha_conta.png", full_page=True)
    pagina.locator("input#janela-confirmacao").fill(original)
    if original != "30":
        pagina.get_by_role("button", name="Salvar").click()
        pagina.wait_for_selector("text=Salvo.", timeout=10_000)

    print("\n3. A lista de usuários do admin")
    pagina.goto(f"{GW}/app/admin/usuarios", wait_until="networkidle")
    pagina.wait_for_selector("text=Usuários e Papéis", timeout=15_000)
    check("marca quem entra com segundo fator", pagina.get_by_text("2º fator").count() > 0)
    pagina.screenshot(path=f"{SHOTS}/04_usuarios.png")

    check(f"nenhum erro de JavaScript na página ({len(erros_js)})", not erros_js)
    nav.close()

print(f"\n{'='*62}\nResultado: {sum(passed)}/{len(passed)}\n{'='*62}")
sys.exit(0 if all(passed) else 1)
