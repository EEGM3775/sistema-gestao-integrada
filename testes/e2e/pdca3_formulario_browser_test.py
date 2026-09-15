"""Os cinco defeitos do "+ novo contrato", achados pelo dono em 15/09/2026.

Ele abriu o formulário e olhou. O que estava errado:

  1. **o valor não se apresentava em real** — `500000` na caixa, e ninguém sabe
     se são quinhentos mil reais ou cinco mil;
  2. **zero à esquerda sobrevivia** no `<input type="number">` — a caixa mostrava
     `012` e o estado guardava `12`; o DOM e o sistema divergiam;
  3. **o select de fornecedores nascia vazio** — o endpoint responde lista crua
     e o código lia `.results`, que é `undefined` num array;
  4. **o rodapé saía da tela** em janela baixa — os botões de salvar ficavam
     inalcançáveis, porque o miolo do diálogo não rolava;
  5. **não havia como cadastrar a planilha contratual** — a API e os hooks
     existiam desde a PDCA.3 e *nenhuma tela os chamava*. Dava para criar o
     contrato, a grade dizia "cadastre os itens para poder medir", e não havia
     onde. A lição da PRA.5c se repetindo.

Rodar (stack de pé, imagem `react` rebuildada):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/pdca3_formulario_browser_test.py
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

GW = os.environ.get("SGI_GW", "http://localhost:8090")
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_form")
MARCA = "E2E form " + uuid.uuid4().hex[:6]

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


def texto_da(pagina) -> str:
    """O texto da página com o espaço **não-quebrável** virando espaço comum.

    `toLocaleString('pt-BR', {style: 'currency'})` separa o `R$` do número com
    U+00A0, não com espaço. Sem esta normalização, `"R$ 80.000,00" in corpo`
    falha sobre uma tela que mostra exatamente isso — e a falha aponta para o
    componente em vez de apontar para a asserção.
    """
    return pagina.inner_text("body").replace(" ", " ").replace(" ", " ")


def login(u, p):
    d = json.dumps({"username": u, "password": p}).encode()
    r = urllib.request.Request(GW + "/auth/login/", data=d, method="POST",
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30, context=_CTX) as resp:
        return json.load(resp)["access"]


print(f"\n{'='*62}\nO formulário de contrato — os 5 achados do dono\n{'='*62}")
os.makedirs(SHOTS, exist_ok=True)

try:
    demo = login("demo", "demo123")
except Exception as e:
    fatal(f"login falhou ({e}). Stack de pé?")

print("\n0. Cenário")
status, obra = req("POST", "/api/obras/", demo, {
    "nome_obra": MARCA, "endereco": "Rua do Formulário", "status_obra": "planejamento",
})
if status not in (200, 201):
    fatal(f"obra falhou ({status}: {obra})")
obra_id = obra["obra_id"]
check("obra do teste criada", True)

with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
    # **Janela baixa de propósito** — 720×620. O achado nº 4 só aparece quando o
    # diálogo é mais alto que a tela, e um viewport confortável o esconderia.
    ctx = navegador.new_context(viewport={"width": 1180, "height": 620})
    pagina = ctx.new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))

    pagina.goto(f"{GW}/login")
    pagina.wait_for_load_state("networkidle")
    pagina.fill("input#username", "demo")
    pagina.fill("input#password", "demo123")
    pagina.click("button[type=submit]")
    pagina.wait_for_url("**/app/**", timeout=20000)

    pagina.goto(f"{GW}/app/pdca/obra/{obra_id}/contratos")
    pagina.wait_for_load_state("networkidle")
    pagina.get_by_role("button", name="Novo contrato").first.click()
    pagina.wait_for_timeout(1200)
    pagina.screenshot(path=f"{SHOTS}/01_form.png", full_page=False)

    # ------------------------------------------------------------ achado 3
    print("\n3. O select de fornecedores (lista crua × página)")
    selects = pagina.locator("select")
    forn = selects.nth(1)
    opcoes = forn.locator("option").all_inner_texts()
    check("o select traz fornecedores de verdade, e não só 'Selecione…'",
          len(opcoes) > 1)
    check("e o nome do fornecedor aparece",
          any(o.strip() and "Selecione" not in o for o in opcoes))

    # ------------------------------------------------------------ achado 2
    print("\n2. Zero à esquerda não sobrevive")
    prazo = pagina.locator("input[inputmode='numeric']").first
    prazo.click()
    prazo.press("Control+a")
    prazo.type("012")
    pagina.wait_for_timeout(300)
    check("digitar '012' no prazo deixa '12' na caixa",
          prazo.input_value() == "12")
    prazo.press("Control+a")
    prazo.type("0")
    check("e o zero sozinho continua sendo zero", prazo.input_value() == "0")
    prazo.press("Control+a")
    prazo.type("30")

    # ------------------------------------------------------------ achado 1
    print("\n1. O valor se apresenta em real")
    # Regime global revela o campo de valor fechado.
    regime = selects.nth(3)
    regime.select_option("global")
    pagina.wait_for_timeout(400)
    moeda = pagina.locator("input[inputmode='decimal']").first
    moeda.click()
    moeda.press("Control+a")
    moeda.type("50000000")           # 500.000,00
    pagina.wait_for_timeout(300)
    valor_na_caixa = moeda.input_value()
    check(f"digitar 50000000 mostra '500.000,00' (veio: '{valor_na_caixa}')",
          valor_na_caixa == "500.000,00")
    pagina.screenshot(path=f"{SHOTS}/02_moeda.png", full_page=False)

    # ------------------------------------------------------------ achado 4
    print("\n4. O rodapé fica na tela, em janela baixa")
    botao_salvar = pagina.get_by_role("button", name="Salvar").first
    caixa = botao_salvar.bounding_box()
    altura = pagina.viewport_size["height"]
    check(f"o botão Salvar está dentro da janela (y={caixa['y']:.0f} < {altura})",
          caixa is not None and caixa["y"] + caixa["height"] <= altura)
    check("e ele é clicável (não está coberto nem fora)", botao_salvar.is_enabled())

    # O miolo rola: o último campo do formulário é alcançável sem a janela
    # inteira rolar por baixo do rodapé.
    pagina.get_by_text("Regime público", exact=False).first.scroll_into_view_if_needed()
    pagina.wait_for_timeout(300)
    pagina.screenshot(path=f"{SHOTS}/03_rodape.png", full_page=False)
    caixa2 = botao_salvar.bounding_box()
    check("e continua na tela depois de rolar o miolo",
          caixa2 is not None and caixa2["y"] + caixa2["height"] <= altura)

    # ---------------------------------------------------- salva o contrato
    print("\n   Salvando o contrato para chegar na planilha")
    regime.select_option("unitario")
    pagina.wait_for_timeout(300)
    numero = "FORM-" + uuid.uuid4().hex[:5]
    forn.select_option(index=1)
    # Campos endereçados por **placeholder**, e não por posição: um campo novo no
    # meio do formulário quebraria o índice, e a falha apareceria como "não
    # salvou" em vez de "o teste mirou errado".
    pagina.get_by_placeholder("001/2026").fill(numero)
    pagina.get_by_placeholder("O que este contrato compra", exact=False).fill(
        "Objeto do teste de formulário"
    )
    pagina.locator("input[type='date']").first.fill(
        (date.today() - timedelta(days=10)).isoformat()
    )
    selects.nth(2).select_option("vigente")          # Situação
    pagina.get_by_role("button", name="Salvar").first.click()
    pagina.wait_for_timeout(2500)
    check("o contrato salva e abre o workspace",
          "/contratos/" in pagina.url)
    if "/contratos/" not in pagina.url:
        pagina.screenshot(path=f"{SHOTS}/99_falhou.png", full_page=True)
        print("     corpo:", pagina.inner_text("body")[:400])

    # ------------------------------------------------------------ achado 5
    print("\n5. A planilha contratual tem onde ser cadastrada")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(800)
    corpo = texto_da(pagina)
    check("a seção 'Planilha contratual' existe na tela",
          "Planilha contratual" in corpo)
    check("e ela diz que sem planilha não há o que medir",
          "Sem planilha não há o que medir" in corpo)

    novo_item = pagina.get_by_role("button", name="Novo item")
    check("existe o botão de cadastrar item", novo_item.count() > 0)
    novo_item.first.click()
    pagina.wait_for_timeout(800)
    pagina.get_by_placeholder("Alvenaria de blocos de concreto").fill("Alvenaria")
    pagina.get_by_placeholder("m2").fill("m2")
    # **Clicar e digitar, sem selecionar antes** — é o que uma pessoa faz, e foi
    # o que expôs o campo de dinheiro somando ao `0,00` que já estava lá. Com o
    # `onFocus` selecionando, digitar substitui, que é o que se espera.
    qtd = pagina.locator("input[inputmode='decimal']").first
    qtd.click(); qtd.type("1000")
    preco = pagina.locator("input[inputmode='decimal']").nth(1)
    preco.click(); preco.type("8000")            # R$ 80,00
    pagina.wait_for_timeout(400)
    check(f"o preço vira R$ 80,00 e não acumula sobre o zero (veio '{preco.input_value()}')",
          preco.input_value() == "80,00")
    corpo_modal = texto_da(pagina)
    check("o total da linha aparece enquanto se digita (1.000 × 80 = R$ 80.000,00)",
          "R$ 80.000,00" in corpo_modal)
    pagina.screenshot(path=f"{SHOTS}/04_item.png", full_page=False)
    pagina.get_by_role("button", name="Salvar").first.click()
    pagina.wait_for_timeout(2200)

    corpo = texto_da(pagina)
    check("o item entra na planilha", "Alvenaria" in corpo)

    # ------------------------------------------------------------ achado 7
    # **D133** — item sem quantidade dava `IntegrityError` → 500 com página de
    # depuração do Django na cara de quem preencheu. A regra do banco estava
    # certa; o que faltava era ela ser dita antes, e no campo.
    print("\n7. Quantidade zero: recusa na tela, não página de erro")
    pagina.get_by_role("button", name="Novo item").first.click()
    pagina.wait_for_timeout(700)
    pagina.get_by_placeholder("Alvenaria de blocos de concreto").fill("Sem quantidade")
    pagina.wait_for_timeout(300)
    salvar_item = pagina.get_by_role("button", name="Salvar").first
    check("o Salvar fica desabilitado com quantidade zero",
          not salvar_item.is_enabled())
    check("e a tela diz por quê, ao lado do botão",
          "quantidade precisa ser maior que zero" in texto_da(pagina).lower())
    pagina.screenshot(path=f"{SHOTS}/06_zero.png", full_page=False)
    pagina.get_by_role("button", name="Cancelar").first.click()
    pagina.wait_for_timeout(500)
    check("nenhum traceback de Django chegou à tela",
          "IntegrityError" not in texto_da(pagina))
    # Exato, e não substring: `80.000,00` também casa dentro de `80.000.000,00`,
    # e foi assim que a primeira escrita deste teste deu verde sobre um número
    # mil vezes maior que o esperado.
    check("com o valor certo somado, e não um múltiplo dele",
          "R$ 80.000,00" in corpo and "80.000.000,00" not in corpo)
    pagina.screenshot(path=f"{SHOTS}/05_planilha.png", full_page=True)

    # E a grade de medição deixa de dizer que não há planilha.
    check("a grade de medição passa a ter linha",
          "ainda não tem planilha contratual" not in corpo)

    check("nenhum erro de JavaScript em todo o percurso", not erros_js)
    if erros_js:
        print("     erros:", erros_js[:3])

    navegador.close()

print("\n6. Faxina")
status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
check("a obra do teste sai", status in (200, 204))
print("     (`manage.py limpar_residuo_e2e --confirmar` devolve o ambiente)")

ok = sum(1 for p in passed if p)
print(f"\n{'='*62}")
print(f"Formulário: {ok}/{len(passed)} verificações · screenshots em {SHOTS}")
print(f"{'='*62}\n")
sys.exit(0 if ok == len(passed) else 1)
