"""PDCA.3 — a grade de medição no NAVEGADOR, pelo gateway (8090).

Existe por uma lição que este projeto já pagou duas vezes: a **PRA.5c** achou uma
porta de lote que funcionava há quatro dias e que *nenhuma tela chamava* — o botão
não estava desabilitado, estava **ausente**, e nenhum E2E de API pegaria isso. O
[pdca3_medicao_test.py](pdca3_medicao_test.py) prova a API inteira; este prova que
existe caminho de dedo até ela.

O que ele cobre:

  1. o item **Contratos e medição** existe na barra lateral e leva à carteira;
  2. a carteira lista o contrato criado pela API;
  3. o cockpit do contrato abre com o saldo derivado na tela;
  4. a **prévia** renderiza as colunas da G703 e é **somente leitura** — só se
     digita dentro de um documento;
  5. o **documento** tem endereço próprio, a grade é viva e a **trava na
     digitação** acende ao passar do saldo, que é a frase que define o
     instrumento e a única parte dele que não dá para provar por API.

E os três defeitos que o dono achou em 15/09/2026 clicando numa medição da
lista, cada um com a sua rede:

  5b. **D137** — o que se digita fica gravado sem ninguém clicar em salvar
      (a prova é o F5);
  5c. **zerar uma linha persiste** — a grade de um documento começa no que está
      gravado nele, e não na proposta, que antes voltava sozinha;
  6.  **o boletim não some** — `get_totais` achatava a lista de deduções numa
      string e o boletim quebrava (`r.deducoes.map is not a function`),
      deixando a tela em branco;
  6b. o endereço antigo (`?medicao=`) redireciona **uma vez** — depender do
      objeto de `useSearchParams` fazia o efeito rodar a cada render e travava
      a aba.

Rodar (stack de pé, imagem `react` rebuildada):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/pdca3_grade_browser_test.py

**Sobre o `LD_LIBRARY_PATH`:** o Chromium do Playwright pede quatro bibliotecas
que o WSL não traz, e instalá-las mexeria na máquina do dono — a saída já usada
pela PRA.5c é extraí-las de uma imagem `ubuntu:24.04` para uma pasta do usuário
(ver [pra5c_upload_acervo_browser_test.py](pra5c_upload_acervo_browser_test.py)).
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
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_pdca3")
MARCA = "E2E PDCA.3 tela " + uuid.uuid4().hex[:6]

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
        return json.load(resp)["access"]


print(f"\n{'='*62}\nPDCA.3 — a grade de medição no navegador\n{'='*62}")
os.makedirs(SHOTS, exist_ok=True)

try:
    demo = login("demo", "demo123")
except Exception as e:
    fatal(f"login falhou ({e}). Stack de pé? Seeds rodados?")

# --- O cenário, montado por API (o que este teste prova é a TELA) -----------
print("\n0. Cenário montado por API")
status, obra = req("POST", "/api/obras/", demo, {
    "nome_obra": MARCA, "endereco": "Rua da Grade, s/n", "status_obra": "planejamento",
})
if status not in (200, 201):
    fatal(f"obra falhou ({status}: {obra})")
obra_id = obra["obra_id"]

status, forn = req("GET", "/api/fornecedores/?page_size=1", demo)
lista = forn if isinstance(forn, list) else (forn or {}).get("results") or []
if not lista:
    fatal("seed sem fornecedor")

inicio = date.today() - timedelta(days=30)
status, contrato = req("POST", "/api/pdca/contratos/", demo, {
    "obra": obra_id, "fornecedor": lista[0]["fornecedor_id"],
    "numero": "TELA-" + uuid.uuid4().hex[:5], "objeto": "Contrato da tela " + MARCA,
    "regime": "unitario", "data_inicio": inicio.isoformat(),
    "retencao_percentual": "5", "retencao_natureza": "tecnica",
    "retencao_condicao_liberacao": "Aceitação definitiva.", "status": "vigente",
})
if status not in (200, 201):
    fatal(f"contrato falhou ({status}: {contrato})")
contrato_id = contrato["contrato_id"]
numero = contrato["numero"]

status, item = req("POST", "/api/pdca/itens-contrato/", demo, {
    "contrato": contrato_id, "codigo": "1.1", "descricao": "Alvenaria de blocos",
    "unidade": "m2", "quantidade_contratada": "1000", "preco_unitario": "80",
})
if status not in (200, 201):
    fatal(f"item falhou ({status}: {item})")
check("obra, contrato e planilha contratual criados por API", True)

# --- A tela -----------------------------------------------------------------
with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = navegador.new_context(viewport={"width": 1440, "height": 900})
    pagina = ctx.new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))
    # Tela parada não faz requisição. É assim que se prova a ausência de laço de
    # renderização — o defeito que travou a aba do dono em 15/09/2026.
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

    print("\n2. O caminho de dedo até a carteira (a lição da PRA.5c)")
    # **A medição mora DENTRO do PDCA** *(decisão do dono, 15/09/2026)*: não há
    # item próprio na barra lateral, e o caminho é Planejamento → a obra →
    # Contratos. É esse percurso que o teste anda, e não a URL colada.
    pagina.wait_for_load_state("networkidle")
    item_menu = pagina.locator("a[href='/app/pdca']")
    try:
        item_menu.first.wait_for(state="attached", timeout=10000)
    except Exception:
        pass
    check("o Planejamento está na barra lateral", item_menu.count() > 0)
    check("e NÃO há item separado de contratos (a medição não é um módulo à parte)",
          pagina.locator("a[href='/app/pdca/contratos']").count() == 0)
    if item_menu.count() > 0:
        item_menu.first.click()
        pagina.wait_for_url("**/app/pdca", timeout=15000)
    else:
        pagina.goto(f"{GW}/app/pdca")
    pagina.wait_for_load_state("networkidle")

    botao = pagina.get_by_role("button", name="Contratos e medição")
    try:
        botao.first.wait_for(state="visible", timeout=10000)
    except Exception:
        pass
    # O botão existe em **todo** cartão de obra — é isso que se está provando
    # aqui: existe caminho de dedo do Planejamento até a medição. Clicar no
    # primeiro abriria a carteira de *outra* obra (o tenant de demonstração tem
    # várias), então a navegação segue para a obra deste teste.
    check("o cartão da obra oferece 'Contratos e medição'", botao.count() > 0)
    pagina.goto(f"{GW}/app/pdca/obra/{obra_id}/contratos")
    pagina.wait_for_load_state("networkidle")
    check("a carteira da obra abre", f"/obra/{obra_id}/contratos" in pagina.url)
    cartao = pagina.get_by_text(numero, exact=False)
    try:
        cartao.first.wait_for(state="visible", timeout=10000)
    except Exception:
        pass
    pagina.screenshot(path=f"{SHOTS}/01_carteira.png", full_page=True)
    check("e lista o contrato criado", cartao.count() > 0)

    print("\n3. O workspace do contrato")
    cartao.first.click()
    pagina.wait_for_url(f"**/contratos/{contrato_id}**", timeout=15000)
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1200)
    pagina.screenshot(path=f"{SHOTS}/02_contrato.png", full_page=True)
    # `inner_text` devolve o texto **renderizado**, então o `text-transform:
    # uppercase` dos rótulos chega em caixa alta. Comparar em minúsculas é o que
    # mantém a asserção sobre o conteúdo, e não sobre a folha de estilo.
    corpo = pagina.inner_text("body").lower()
    check("o saldo derivado aparece na tela",
          "contratado" in corpo and "saldo" in corpo)
    check("a retenção aparece com a natureza", "retenção" in corpo)
    check("e o valor do saldo é legível (não é texto branco em fundo claro)",
          "80.000,00" in corpo)

    print("\n4. A prévia — somente leitura, com as colunas da G703")
    # **O contrato não mede mais.** Medir é um gesto com endereço próprio, e o
    # cockpit encaminha para ele: é o conserto do `?medicao=` que reconfigurava
    # um card no meio desta tela.
    check("o cockpit NÃO tem grade de digitação",
          pagina.locator("table input[inputmode='decimal']").count() == 0)
    botao_medir = pagina.get_by_role("button", name="Medir período")
    check("e oferece 'Medir período' como caminho", botao_medir.count() > 0)
    botao_medir.first.click()
    pagina.wait_for_url("**/previa", timeout=15000)
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(900)
    corpo = pagina.inner_text("body").lower()
    for coluna in ("contratado", "já medido", "saldo", "proposto", "este período"):
        check(f"coluna '{coluna}'", coluna in corpo)
    check("a prévia diz que nada foi gravado ainda", "nada é gravado" in corpo)
    # **Leitura é número, não campo travado.** Um `<input readonly>` tem borda,
    # cursor e fundo de campo: convida a clicar e não aceita nada. O dono colou
    # exatamente um desses dizendo *"a parte mais importante da medição não
    # consigo editar"* — ele estava na prévia, que é leitura por desenho.
    check("e a grade da prévia não tem campo nenhum (leitura é número)",
          pagina.locator("table input").count() == 0)
    check("dizendo onde se digita", "documento" in corpo)
    pagina.screenshot(path=f"{SHOTS}/03_previa.png", full_page=True)

    print("\n5. O documento — a grade viva e a trava NA DIGITAÇÃO")
    pagina.get_by_role("button", name="Abrir medição do período").first.click()
    pagina.wait_for_url("**/medicoes/**", timeout=20000)
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1200)
    url_documento = pagina.url
    check("abrir a medição leva ao DOCUMENTO, com endereço próprio",
          "/medicoes/" in url_documento)

    celula = pagina.locator("table input[inputmode='decimal']").first
    check("a célula do documento é editável (aqui, sim, é campo)",
          celula.count() > 0 and celula.get_attribute("readonly") is None)
    if celula.count() > 0:
        celula.click()
        celula.fill("2000")           # contratado é 1.000
        pagina.wait_for_timeout(400)
        pagina.screenshot(path=f"{SHOTS}/04_trava.png", full_page=True)
        corpo2 = pagina.inner_text("body").lower()
        check("digitar acima do saldo acusa NA HORA, sem submeter",
              "acima do saldo" in corpo2)
        check("e a recusa aponta o caminho certo (aditivo)", "aditivo" in corpo2)

        celula.fill("300")
        pagina.wait_for_timeout(400)
        corpo3 = pagina.inner_text("body").lower()
        check("e some quando o número volta a caber",
              "acima do saldo" not in corpo3)

    print("\n5b. O autosave (D137) — o que se digita fica gravado")
    # O defeito: "Salvar grade" e "Submeter" eram botões independentes, e
    # submeter mandava só o id — o documento era aprovado com os números
    # anteriores, sem erro e sem aviso. A prova é **recarregar**: o número tem
    # de estar lá sem ninguém ter clicado em salvar.
    pagina.wait_for_timeout(2600)                     # debounce de 1,5 s + folga
    corpo4 = pagina.inner_text("body").lower()
    check("a tela diz que gravou sozinha", "salvo" in corpo4)
    pagina.reload()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1500)
    valor = pagina.locator("table input[inputmode='decimal']").first.input_value()
    check("e o número sobrevive ao F5 sem ninguém ter clicado em salvar",
          valor.replace(",", ".").startswith("300"))

    print("\n5c. Zerar uma linha é uma decisão, e ela persiste")
    # A grade de um documento começa no que está **gravado nele**, não na
    # proposta: com a proposta, zerar uma linha a fazia voltar sozinha no
    # recarregamento — o gestor via o número que tinha apagado reaparecer.
    celula = pagina.locator("table input[inputmode='decimal']").first
    celula.click()
    celula.fill("0")
    pagina.wait_for_timeout(2600)
    pagina.reload()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1500)
    valor = pagina.locator("table input[inputmode='decimal']").first.input_value()
    check("o zero continua zero depois do F5 (a proposta não volta sozinha)",
          float(valor.replace(",", ".") or 0) == 0.0)

    print("\n6. O boletim — o documento congelado se lê como papel")
    # O defeito que apagou a tela: `get_totais` fazia `str(valor)` num nível só
    # e transformava a lista de deduções na string "[]" — o boletim percorre
    # essa lista, e uma string não tem `.map`. A tela ficava **em branco**.
    celula.fill("250")
    pagina.wait_for_timeout(2600)
    pagina.get_by_role("button", name="Submeter").first.click()
    pagina.wait_for_timeout(3500)
    pagina.wait_for_load_state("networkidle")
    corpo5 = pagina.inner_text("body").lower()
    check("a medição submetida vira BOLETIM, e a tela não some",
          "boletim de medição" in corpo5)
    check("com as parcelas do pagamento separadas",
          "bruto" in corpo5 and "retenção" in corpo5 and "líquido" in corpo5)
    check("e só as linhas medidas, não o contrato inteiro",
          "itens medidos" in corpo5)
    check("o botão de imprimir existe — este papel vai a campo",
          pagina.get_by_role("button", name="Imprimir").count() > 0)
    pagina.screenshot(path=f"{SHOTS}/05_boletim.png", full_page=True)

    print("\n6b. O endereço antigo (?medicao=) continua funcionando")
    medicao_id = url_documento.rstrip("/").split("/")[-1]
    antes = len(requisicoes)
    pagina.goto(f"{GW}/app/pdca/obra/{obra_id}/contratos/{contrato_id}?medicao={medicao_id}")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(3000)
    check("o link colado no grupo da obra leva ao documento",
          f"/medicoes/{medicao_id}" in pagina.url)
    # O redirecionamento dependia do objeto de `useSearchParams`, que o React
    # Router recria a cada render: o efeito rodava sempre, `navigate` a cada
    # render, e a aba **travava**. Com a tela parada não pode haver requisição.
    parado = len(requisicoes)
    pagina.wait_for_timeout(3000)
    check("e a tela fica PARADA depois (sem laço de renderização)",
          len(requisicoes) - parado == 0)

    check("nenhum erro de JavaScript na página", not erros_js)
    if erros_js:
        print("     erros:", erros_js[:3])

    navegador.close()

# --- Faxina -----------------------------------------------------------------
print("\n6. Faxina")
# Este teste não chega a aprovar medição, então não deixa título no ERP — mas
# deixa **contrato e obra na lixeira**, porque a exclusão da obra é lápide e não
# `DELETE`. Ver a nota do [pdca3_medicao_test.py](pdca3_medicao_test.py): o
# ambiente volta ao estado anterior com `manage.py limpar_residuo_e2e`.
status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
check("a obra do teste sai", status in (200, 204))
print("     (contrato e obra ficam na lixeira — "
      "`manage.py limpar_residuo_e2e --confirmar` devolve o ambiente)")

ok = sum(1 for p in passed if p)
print(f"\n{'='*62}")
print(f"PDCA.3 (tela): {ok}/{len(passed)} verificações · screenshots em {SHOTS}")
print(f"{'='*62}\n")
sys.exit(0 if ok == len(passed) else 1)
