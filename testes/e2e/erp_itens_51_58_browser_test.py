"""
Itens 51–58 do dono no navegador — ERP: a grade das contas, o boleto, a conta
paga que se edita e a cobrança bancária.

Não emite nada no Asaas nem no banco: abre a prévia do boleto e fecha. A única
escrita é a descrição de uma conta a pagar já paga (o caso do item 57), que o
roteiro devolve ao texto original no fim.

Rodar (stack de pé):  ~/sgi_e2e_venv.sh erp_itens_51_58_browser_test.py
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

from _segundo_fator import responder_no_navegador

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_screenshots/erp_51_58")
passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def esperar_grade(page, timeout=20000):
    page.wait_for_selector("[role=grid] [role=row] >> nth=1", timeout=timeout)


def run():
    os.makedirs(SHOTS, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        erros_js = []
        page.on("pageerror", lambda e: erros_js.append(str(e)))

        page.goto(f"{GW}/login")
        page.fill("input#username", "admin")
        page.fill("input#password", "admin123")
        page.click("button[type=submit]")
        responder_no_navegador(page)
        page.wait_for_url("**/app/**", timeout=20000)

        # ── 51/53: a grade de contas a receber ────────────────────────────────
        print("→ Contas a receber")
        t0 = time.perf_counter()
        page.goto(f"{GW}/app/erp/contas-a-receber")
        esperar_grade(page)
        abrir = time.perf_counter() - t0
        page.screenshot(path=f"{SHOTS}/01_receber.png")
        check(f"a grade abre com as contas ({abrir:.1f} s, com o login do app)", abrir < 8)
        corpo = page.inner_text("body")
        check("os totais aparecem (contas · em aberto)", " contas" in corpo and "em aberto" in corpo)
        check("nenhuma linha diz 'Cliente #' no lugar do nome", "Cliente #" not in corpo)

        primeiro_nome = page.locator("[role=grid] [role=row] >> nth=1").locator("a").first.inner_text().strip()
        termo = primeiro_nome.split()[0]
        print(f"→ Buscando '{termo}'")
        t0 = time.perf_counter()
        page.fill("input[type=search]", termo.lower())
        page.wait_for_function(
            "(t) => [...document.querySelectorAll('[role=grid] [role=row] a')].slice(0, 5).every(a => a.textContent.toLowerCase().includes(t))",
            arg=termo.lower(), timeout=10000,
        )
        busca = time.perf_counter() - t0
        page.screenshot(path=f"{SHOTS}/02_busca.png")
        check(f"a busca pelo nome do cliente responde enquanto se digita ({busca:.2f} s)", busca < 3)

        page.fill("input[type=search]", "")
        page.wait_for_timeout(700)
        page.select_option("select[aria-label='Agrupar por']", label="Empreendimento")
        page.wait_for_selector("[role=row][aria-expanded]", timeout=10000)
        page.screenshot(path=f"{SHOTS}/03_agrupado.png")
        grupos = page.locator("[role=row][aria-expanded]").count()
        check(f"agrupar por empreendimento mostra os grupos com subtotal ({grupos})", grupos > 0 and "em aberto" in page.locator("[role=row][aria-expanded]").first.inner_text())
        page.locator("[role=row][aria-expanded]").first.click()
        page.wait_for_timeout(1500)
        check("abrir um grupo traz as linhas dele", page.locator("[role=row][aria-selected]").count() > 0)
        page.get_by_role("button", name="Parar de agrupar por Empreendimento").click()
        esperar_grade(page)

        # ── 55/56: o painel da conta e a prévia do boleto ────────────────────
        print("→ Painel da conta e prévia do boleto")
        page.get_by_role("radio", name="Vencidas").click()
        page.wait_for_timeout(1200)
        page.locator("[role=grid] [role=row] >> nth=1").click()
        page.wait_for_selector("text=abrir a ficha do cliente", timeout=10000)
        botao = page.get_by_role("button", name="Emitir segunda via")
        check("conta vencida oferece 'Emitir segunda via'", botao.count() == 1)
        if botao.count():
            botao.click()
            page.wait_for_selector("text=Vencimento do boleto", timeout=10000)
            dialogo = page.get_by_role("dialog", name="Gerar boleto").inner_text()
            page.screenshot(path=f"{SHOTS}/04_segunda_via.png")
            check("a prévia diz que a parcela venceu", "venceu em" in dialogo)
            check("e mostra multa e juros do contrato", "Multa" in dialogo and "Juros" in dialogo)
            page.get_by_role("button", name="Cancelar").click()
        page.keyboard.press("Escape")

        # ── 57: conta a pagar já paga ─────────────────────────────────────────
        print("→ Conta a pagar paga: editar")
        page.goto(f"{GW}/app/erp/contas-a-pagar")
        esperar_grade(page)
        page.get_by_role("radio", name="Pagas e canceladas").click()
        page.wait_for_timeout(1200)
        linhas = page.locator("[role=grid] [role=row]")
        if linhas.count() < 2:
            check("há conta a pagar paga no dev para o teste", False)
        else:
            linhas.nth(1).click()
            page.get_by_role("button", name="Editar").click()
            page.wait_for_selector("text=estorne a baixa primeiro", timeout=10000)
            page.screenshot(path=f"{SHOTS}/05_editar_paga.png")
            check("o formulário diz o que está travado e qual é a saída", True)
            campo = page.locator("input[placeholder^='Ex.: Compra de cimento']")
            original = campo.input_value()
            campo.fill(original + " (conferido)")
            page.get_by_role("button", name="Salvar alterações").click()
            page.wait_for_selector("text=(conferido)", timeout=10000)
            check("editar a descrição de uma conta paga salva e volta ao detalhe", page.get_by_role("button", name="Editar").count() == 1)
            page.get_by_role("button", name="Editar").click()
            page.locator("input[placeholder^='Ex.: Compra de cimento']").fill(original)
            page.get_by_role("button", name="Salvar alterações").click()
            page.wait_for_timeout(1500)
            check("o botão de estornar aparece para quem pode", page.get_by_role("button", name="Estornar baixa").count() == 1)
            page.keyboard.press("Escape")

        # ── 54: boletos com origem ────────────────────────────────────────────
        print("→ Boletos")
        page.goto(f"{GW}/app/erp/boletos")
        page.wait_for_selector("text=Pagador", timeout=15000)
        page.wait_for_timeout(1500)
        page.screenshot(path=f"{SHOTS}/06_boletos.png")
        corpo = page.inner_text("body")
        check("a lista de boletos não mostra mais 'Conta a receber #'", "Conta a receber #" not in corpo)

        # ── 52: cobrança bancária ─────────────────────────────────────────────
        print("→ Cobrança bancária")
        page.goto(f"{GW}/app/erp/cobranca-bancaria")
        page.wait_for_selector("text=Carteiras de cobrança", timeout=15000)
        page.get_by_role("button", name="Nova carteira").click()
        page.wait_for_selector("[role=dialog] option:has-text('Sicoob')", state="attached", timeout=10000)
        opcoes = page.locator("[role=dialog] select").first.inner_text()
        page.screenshot(path=f"{SHOTS}/07_carteira.png")
        check("os sete bancos aparecem no cadastro da carteira",
              all(b in opcoes for b in ("Banco do Brasil", "Santander", "Caixa", "Bradesco", "Itaú", "Sicredi", "Sicoob")))

        check("nenhum erro de JavaScript na página", not erros_js)
        for e in erros_js[:5]:
            print("   JS:", e)
        browser.close()

    total, ok = len(passed), sum(passed)
    print(f"\nRESULTADO: {ok}/{total}")
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    run()
