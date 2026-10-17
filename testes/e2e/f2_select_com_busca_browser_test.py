"""F2 — o cliente se escolhe pela BUSCA no servidor, e o nº 301 existe.

Antes: o campo "Cliente" da conta a receber (ERP) e do contrato com o cliente
(PDCA) era um `<select>` montado com uma página só de `/api/clientes/` — no
máximo 300 (`PAGINA_MAXIMA["clientes"]`). No tenant demo do dev, com 2.003
clientes, a lista parava em "Carla Lima": quem vinha depois no alfabeto **não
existia** para o formulário, e não havia erro nenhum na tela.

Agora os dois usam o `SelectComBusca` da Malha. Este roteiro prova:

  1. o campo diz quantos há e quantos mostra, e **rolar a lista traz o resto**:
     buscando "Paulo", todos os resultados aparecem, uma vez cada, até o último
     (decisão do dono, 15/10/2026 — a busca refina, mas não é obrigatória);
  2. um cliente do fim do alfabeto (o último do tenant) se acha pela busca;
  3. a conta lançada com ele **grava o cliente certo** (lido de volta na API);
  4. reaberta, a conta mostra o nome do cliente — o escolhido nunca some, mesmo
     fora da primeira página;
  5. Enter no campo escolhe, e não envia o formulário;
  6. no contrato com o cliente do PDCA, o mesmo cliente se escolhe e o formulário
     fica completo (o botão de cadastrar acende) — sem gravar o contrato;
  7. e a tela fica sem erro de JS.

A conta criada é apagada no fim (vai para a lixeira, que é o desenho), e a obra
do item 6 também.

Rodar (stack de pé, imagem `react` rebuildada):

    ~/sgi_e2e_venv.sh f2_select_com_busca_browser_test.py
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
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_f2")
MARCA = "E2E F2 " + uuid.uuid4().hex[:6]

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


def escolher_cliente(escopo, pagina, nome):
    campo = escopo.get_by_role("combobox", name="Cliente")
    campo.click()
    campo.fill(nome)
    pagina.wait_for_timeout(1200)
    #: O demo tem homônimos. A lista vem por nome e, no empate, por id — o
    #: alvo (o maior id entre os homônimos) é sempre o ÚLTIMO de mesmo nome.
    opcao = pagina.get_by_role("option", name=nome).last
    achou = opcao.count() > 0
    if achou:
        opcao.click()
        pagina.wait_for_timeout(400)
    return campo, achou


print(f"\n{'='*62}\nF2 — o cliente se escolhe pela busca\n{'='*62}")
os.makedirs(SHOTS, exist_ok=True)

try:
    demo = login("demo", "demo123")
except Exception as e:
    fatal(f"login falhou ({e}). Stack de pé? Seeds rodados?")

#: O alvo é o ÚLTIMO cliente do alfabeto — o que mais longe fica da primeira
#: página. Com mais de 300 clientes, é exatamente quem o select antigo perdia.
status, primeira = req("GET", "/api/clientes/?page_size=1&ordering=-nome_completo,-cliente_id", demo)
if status != 200 or not primeira.get("results"):
    fatal(f"/api/clientes/ respondeu {status}")
total = primeira["count"]
alvo = primeira["results"][0]
print(f"     {total} clientes; alvo: {alvo['nome_completo']} (#{alvo['cliente_id']})")
if total <= 300:
    print("     (o tenant tem até 300 clientes: o corte antigo não apareceria aqui,"
          " mas a busca continua sendo provada)")

conta_id = None
obra_id = None
with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = navegador.new_context(viewport={"width": 1500, "height": 950})
    pagina = ctx.new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))

    print("\n1. Login")
    pagina.goto(f"{GW}/login")
    pagina.wait_for_load_state("networkidle")
    pagina.fill("input#username", "demo")
    pagina.fill("input#password", "demo123")
    pagina.click("button[type=submit]")
    pagina.wait_for_url("**/app/**", timeout=25000)
    check("`demo` entrou", "/app" in pagina.url)

    try:
        print("\n2. ERP › Nova conta a receber — o campo declara a página curta")
        pagina.goto(f"{GW}/app/erp/contas-a-receber")
        pagina.wait_for_load_state("networkidle")
        pagina.get_by_role("button", name="Nova conta").first.click()
        pagina.wait_for_timeout(1500)
        campo = pagina.get_by_role("combobox", name="Cliente")
        check("o campo Cliente é uma busca, não uma lista fechada", campo.count() == 1)
        campo.click()
        pagina.wait_for_timeout(1500)
        rodape = pagina.locator("[role=status]").filter(has_text="role para ver mais").first
        texto_rodape = rodape.inner_text() if rodape.count() else ""
        check("aberto sem busca, diz quantos mostra de quantos há, e que rolar traz mais",
              f"{total:,}".replace(",", ".") in texto_rodape if total > 50 else True)
        opcoes = pagina.get_by_role("listbox").get_by_role("option")
        check("e começa por uma página, não pela tabela inteira",
              0 < opcoes.count() < total)

        print("\n2b. Rolar a lista até o fim mostra TODOS os resultados da busca")
        #: Decisão do dono (15/10/2026): se há 21 nomes parecidos e a pessoa
        #: quer o 21º, rolar o encontra — a busca refina, mas não é obrigatória.
        campo.fill("Paulo")
        pagina.wait_for_timeout(1500)
        status, pauls = req("GET", "/api/clientes/?search=Paulo&page_size=1", demo)
        esperado = pauls["count"]
        lista = pagina.get_by_role("listbox")
        for _ in range(60):
            if opcoes.count() >= esperado:
                break
            lista.evaluate("ul => ul.scrollTop = ul.scrollHeight")
            pagina.wait_for_timeout(700)
        nomes = opcoes.all_text_contents()
        print(f"     'Paulo': {esperado} na API, {len(nomes)} na lista")
        check(f"todos os {esperado} resultados aparecem rolando (mais de uma página)",
              esperado > 50 and len(nomes) == esperado)
        ids_vistos = pagina.locator("[role=option]").evaluate_all("els => els.map(e => e.id)")
        check("cada um uma vez só — homônimos não repetem entre páginas",
              len(set(ids_vistos)) == len(ids_vistos))
        check("e o rodapé diz que acabou, sem 'role para ver mais'",
              "role para ver mais" not in pagina.locator("[role=status]").last.inner_text())
        ultimo = opcoes.last
        ultimo.click()
        pagina.wait_for_timeout(400)
        check("o último da lista rolada se escolhe com um clique",
              campo.input_value() != "" and campo.input_value().lower().startswith("paulo"))

        print("\n3. O cliente do fim do alfabeto se acha pela busca")
        campo, achou = escolher_cliente(pagina, pagina, alvo["nome_completo"])
        check(f"'{alvo['nome_completo']}' aparece ao buscar", achou)
        check("e, escolhido, o campo mostra o nome", campo.input_value() == alvo["nome_completo"])

        print("\n4. Enter escolhe, não envia o formulário")
        campo.click()
        campo.fill(alvo["nome_completo"])
        pagina.wait_for_timeout(1200)
        campo.press("Enter")
        pagina.wait_for_timeout(800)
        check("Enter escolheu e o formulário continua aberto (nada foi lançado)",
              campo.count() == 1 and campo.input_value() == alvo["nome_completo"]
              and pagina.get_by_role("button", name="Lançar conta").count() == 1)
        #: Enter escolheu o PRIMEIRO homônimo; o alvo é o último — escolhido de
        #: novo, para o passo seguinte gravar quem a pessoa quis.
        escolher_cliente(pagina, pagina, alvo["nome_completo"])

        print("\n5. Lançar a conta — e o cliente gravado é o escolhido")
        pagina.get_by_placeholder("Ex.: Medição 03 — contrato 2025/014").fill(MARCA)
        dinheiro = pagina.locator("form input[inputmode]").first
        dinheiro.click()
        dinheiro.fill("123,45")
        vencimento = (date.today() + timedelta(days=30)).isoformat()
        pagina.locator("form input[type=date]").nth(1).fill(vencimento)
        pagina.get_by_role("button", name="Lançar conta").click()
        pagina.wait_for_timeout(3000)
        status, achadas = req("GET", f"/api/erp/contas-a-receber/?search={MARCA.replace(' ', '%20')}", demo)
        linhas = [c for c in (achadas or {}).get("results", []) if c.get("descricao") == MARCA]
        conta = linhas[0] if linhas else None
        conta_id = conta and conta.get("id", conta.get("conta_receber_id"))
        check("a conta foi lançada", conta is not None)
        check("com o cliente do fim do alfabeto", bool(conta) and conta["cliente"] == alvo["cliente_id"])
        pagina.screenshot(path=f"{SHOTS}/01_conta_lancada.png", full_page=True)

        print("\n6. Reaberta, a conta mostra o cliente — o escolhido nunca some")
        if conta:
            pagina.goto(f"{GW}/app/erp/contas-a-receber")
            pagina.wait_for_load_state("networkidle")
            pagina.wait_for_timeout(1500)
            #: A grade rola infinita por vencimento e o demo tem homônimos com
            #: centenas de parcelas: a conta nova se acha pelo cliente **e** pelo
            #: vencimento exato, que são os filtros da própria grade.
            pagina.get_by_placeholder("Buscar por cliente, CPF, empreendimento, quadra, lote ou parcela") \
                .fill(alvo["nome_completo"])
            datas = pagina.locator("input[type=date]")
            datas.nth(0).fill(vencimento)
            datas.nth(1).fill(vencimento)
            pagina.wait_for_timeout(2500)
            pagina.get_by_text(MARCA, exact=True).first.click()
            pagina.wait_for_timeout(1500)
            editar = pagina.get_by_role("button", name="Editar")
            if editar.count():
                editar.first.click()
                pagina.wait_for_timeout(1500)
            campo = pagina.get_by_role("combobox", name="Cliente")
            check("o campo da conta reaberta traz o nome do cliente",
                  campo.count() == 1 and campo.input_value() == alvo["nome_completo"])
            pagina.screenshot(path=f"{SHOTS}/02_conta_reaberta.png", full_page=True)

        print("\n7. PDCA › contrato com o cliente — o mesmo campo")
        status, obra = req("POST", "/api/obras/", demo, {
            "nome_obra": MARCA, "endereco": "Rua da Busca, s/n", "status_obra": "planejamento",
        })
        if status not in (200, 201):
            fatal(f"obra falhou ({status}: {obra})")
        obra_id = obra["obra_id"]
        pagina.goto(f"{GW}/app/pdca/o/{obra_id}/medicao")
        pagina.wait_for_load_state("networkidle")
        pagina.wait_for_timeout(1800)
        pagina.get_by_role("button", name="Novo contrato").first.click()
        pagina.wait_for_timeout(1000)
        dialogo = pagina.locator("div[role=dialog]")
        dialogo.locator("input[type=radio]").nth(1).check()
        pagina.wait_for_timeout(500)
        campo, achou = escolher_cliente(dialogo, pagina, alvo["nome_completo"])
        check(f"no contrato, '{alvo['nome_completo']}' também se acha", achou)
        check("e fica escolhido", campo.input_value() == alvo["nome_completo"])
        dialogo.locator("div:has(> label:text-is('Número do contrato')) input").fill("E2E-F2")
        dialogo.locator("textarea").first.fill("Contrato de teste da F2 — não gravado")
        dialogo.locator("input[type=date]").first.fill(date.today().isoformat())
        pagina.wait_for_timeout(400)
        check("com cliente, número, objeto e início, o cadastro acende",
              dialogo.get_by_role("button", name="Cadastrar contrato").is_enabled())
        pagina.screenshot(path=f"{SHOTS}/03_contrato.png", full_page=True)
        dialogo.get_by_role("button", name="Voltar").click()

        check("nenhum erro de JavaScript", not erros_js)
        if erros_js:
            print("     erros:", erros_js[:3])
    finally:
        navegador.close()
        print("\n8. Faxina")
        if conta_id:
            status, _ = req("DELETE", f"/api/erp/contas-a-receber/{conta_id}/", demo)
            print(f"     conta {conta_id}: {status}")
        if obra_id:
            status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
            print(f"     obra {obra_id}: {status}")

ok = sum(1 for p in passed if p)
print(f"\n{'='*62}\nF2 (tela): {ok}/{len(passed)} verificações\n{'='*62}")
sys.exit(0 if ok == len(passed) else 1)
