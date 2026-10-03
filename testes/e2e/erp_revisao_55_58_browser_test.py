"""
Revisão do dono dos itens 55, 57 e 58 (01/10/2026) no navegador.

O caso é o do print do dono: a parcela 46/48 (QD 6 · LT 14) do dev, cujo boleto
vence em 01/01/2030 — feriado — e cuja conta foi corrigida para 02/01. O roteiro
confere que o boleto mostra a linha digitável, que avisa que ficou para trás e
oferece o boleto atualizado, que o formulário avisa a reemissão antes de salvar
e que as notas em lote mostram a prévia.

**Não emite nada** (nem boleto, nem nota) e não salva: abre e cancela.

Rodar (stack de pé):  ~/sgi_e2e_venv.sh erp_revisao_55_58_browser_test.py
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
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_screenshots/erp_revisao_55_58")
USUARIO = os.environ.get("SGI_USUARIO", "demo")
SENHA = os.environ.get("SGI_SENHA", "demo123")
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
        # O `demo` (financeiro, tesouraria, fiscal): o `admin` tem 2FA com o
        # aparelho do dono desde 01/10/2026, e o roteiro não mexe nele.
        page.fill("input#username", USUARIO)
        page.fill("input#password", SENHA)
        page.click("button[type=submit]")
        responder_no_navegador(page)
        page.wait_for_url("**/app/**", timeout=20000)

        # ── 55/57: o boleto do print do dono ──────────────────────────────────
        print("→ A parcela 46/48 do QD 6 · LT 14")
        page.goto(f"{GW}/app/erp/contas-a-receber")
        esperar_grade(page)
        page.fill("input[aria-label='Vencimento de']", "2030-01-02")
        page.fill("input[aria-label='Vencimento até']", "2030-01-02")
        page.fill("input[type=search]", "qd 6 lt 14")
        page.wait_for_selector("[role=grid] [role=row]:has-text('46/48')", timeout=15000)
        page.locator("[role=grid] [role=row]:has-text('46/48')").first.click()
        page.wait_for_selector("text=abrir a ficha do cliente", timeout=10000)
        page.wait_for_selector("text=Este boleto foi emitido para o vencimento", timeout=10000)
        page.wait_for_timeout(800)  # o painel termina de deslizar antes da captura
        painel = page.inner_text("body")
        page.screenshot(path=f"{SHOTS}/01_boleto_desatualizado.png")
        check("o boleto mostra a linha digitável (não 'ainda não disponível')",
              "46191.11000" in painel or "46191110000" in painel)
        check("o painel avisa que o boleto ficou para trás (01/01 × 02/01)",
              "01/01/2030" in painel and "02/01/2030" in painel)
        botao = page.get_by_role("button", name="Emitir boleto atualizado")
        check("e oferece o boleto atualizado", botao.count() == 1)
        if botao.count():
            botao.click()
            page.wait_for_selector("text=Vencimento do boleto", timeout=10000)
            dialogo = page.get_by_role("dialog", name="Gerar boleto").inner_text()
            page.screenshot(path=f"{SHOTS}/02_previa_atualizada.png")
            check("a prévia diz que o boleto de 01/01 será cancelado no Asaas",
                  "01/01/2030" in dialogo and "cancelado no Asaas" in dialogo)
            page.get_by_role("dialog", name="Gerar boleto").get_by_role("button", name="Cancelar").click()

        # O formulário: mudar o vencimento avisa a reemissão antes de salvar.
        page.get_by_role("button", name="Editar").click()
        page.wait_for_selector("text=Salvar alterações", timeout=10000)
        page.locator("form input[type=date]").nth(1).fill("2030-01-03")
        page.wait_for_selector("text=Ao salvar, ele é", timeout=5000)
        page.screenshot(path=f"{SHOTS}/03_form_reemite.png")
        check("mudar o vencimento avisa que o boleto será cancelado e reemitido",
              page.get_by_role("button", name="Salvar e reemitir o boleto").count() == 1)
        check("o cliente fica travado enquanto há boleto vivo", "boleto não muda de pagador" in page.inner_text("body"))
        page.get_by_role("button", name="Cancelar").click()
        page.keyboard.press("Escape")

        # ── Notas em lote ─────────────────────────────────────────────────────
        print("→ Notas fiscais em lote")
        page.fill("input[aria-label='Vencimento de']", "")
        page.fill("input[aria-label='Vencimento até']", "")
        page.fill("input[type=search]", "")
        page.wait_for_timeout(800)
        esperar_grade(page)
        page.get_by_role("radio", name="A vencer").click()
        page.wait_for_timeout(1200)
        caixas = page.locator("[role=grid] input[aria-label='Selecionar linha']:not([disabled])")
        caixas.nth(0).check()
        caixas.nth(1).check()
        botao = page.get_by_role("button", name="Emitir notas (2)")
        check("marcar contas oferece 'Emitir notas'", botao.count() == 1)
        if botao.count():
            botao.click()
            page.wait_for_selector("text=Notas a emitir", timeout=15000)
            dialogo = page.get_by_role("dialog", name="Emitir notas fiscais em lote").inner_text()
            page.screenshot(path=f"{SHOTS}/04_notas_lote.png")
            check("a prévia das notas diz quantas saem e quantas já têm nota",
                  "Notas a emitir" in dialogo and "Já têm nota" in dialogo)
            page.get_by_role("dialog", name="Emitir notas fiscais em lote").get_by_role("button", name="Cancelar").click()
        page.get_by_role("button", name="Gerar boletos (2)").click()
        page.wait_for_selector("text=Emitir também a nota fiscal de cada conta", timeout=15000)
        page.get_by_text("Emitir também a nota fiscal de cada conta").click()
        page.wait_for_selector("text=a emitir ·", timeout=15000)
        page.screenshot(path=f"{SHOTS}/05_boletos_com_notas.png")
        check("o lote de boletos oferece emitir as notas junto, com a prévia",
              "e notas" in page.get_by_role("dialog", name="Gerar boletos em lote").inner_text())
        check("o diálogo diz o limite do lote desta empresa",
              "boletos por lote nesta empresa" in page.get_by_role("dialog", name="Gerar boletos em lote").inner_text())
        page.get_by_role("dialog", name="Gerar boletos em lote").get_by_role("button", name="Cancelar").click()

        # ── Limite dos lotes: o plano dá o teto, a empresa escolhe o dela ──────
        print("→ Configurações do financeiro")
        page.goto(f"{GW}/app/erp/configuracoes")
        page.wait_for_selector("text=Limite dos lotes", timeout=15000)
        page.wait_for_timeout(500)
        tela = page.inner_text("body")
        page.screenshot(path=f"{SHOTS}/06_limites.png")
        check("a tela mostra o teto do plano Profissional (500)", "Profissional" in tela and "500" in tela)
        check("quem não tem a permissão especial vê o número e quem pode mudar, sem campo",
              "Quem muda este limite" in tela and page.locator("input[type=number]").count() == 0)

        check("nenhum erro de JavaScript na página", not erros_js)
        for e in erros_js[:5]:
            print("   JS:", e)
        browser.close()

    total, ok = len(passed), sum(passed)
    print(f"\nRESULTADO: {ok}/{total}")
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    run()
