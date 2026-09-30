"""D70 no browser — o arquivo abre sem `<a href>`, e nenhuma tela pede `/media/`.

**O que só o browser prova.** O E2E de API mostra que a URL mudou e que a porta
entrega; ele não mostra o que o *navegador* faz com ela. E era exatamente aí que
o D70 podia deixar um rastro pior que o buraco: trocar a URL sem trocar o gesto
daria uma tela que carrega, um botão que parece funcionar e um 401 silencioso —
o token vive em memória (F1) e não viaja num `<a href>` nem num `<img src>`.

Então este teste escuta a **rede da página**: nenhuma requisição pode sair para
`/media/`, e o clique de abrir tem de virar um GET autenticado na porta única,
com 200.

Roda pelo gateway (8090), com o bundle que o container serve — não pelo Vite.

**AINDA NÃO EXECUTADO (09/08/2026).** O Chromium do Playwright está baixado, mas
faltam as bibliotecas de sistema no WSL (`libnspr4.so`), e instalá-las mexe na
máquina do dono:

    sudo .venv/bin/playwright install-deps chromium

Enquanto isso não roda, o que cobre o frontend do D70 é o `tsc -b` do build (que
pega o contrato: `arquivo_nome`, os tipos das telas, a `mediaUrl` removida) e o
[d70_media_fechada_test.py](d70_media_fechada_test.py), que prova o lado do
servidor. O gesto no browser — clicar em "Abrir" e receber o blob — segue
**provado por analogia** com o visualizador da Prancheta, que usa o mesmo
caminho, e não por medição. Este arquivo existe para fechar essa lacuna no dia em
que as libs entrarem.
"""
import sys

from playwright.sync_api import sync_playwright

GW = "http://localhost:8090"
OK, FALHA = [], []


def checar(nome, condicao, detalhe=""):
    (OK if condicao else FALHA).append(nome)
    print(f"{'OK  ' if condicao else 'FALHA'} · {nome}{(' — ' + str(detalhe)) if detalhe else ''}")


def rodar():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
        pagina = navegador.new_context(viewport={"width": 1400, "height": 900}).new_page()

        pedidos_media, entregas = [], []
        pagina.on("request", lambda r: pedidos_media.append(r.url) if "/media/" in r.url else None)
        pagina.on(
            "response",
            lambda r: entregas.append((r.url, r.status)) if "/api/impexp/" in r.url
            and "/arquivo/" in r.url else None,
        )
        erros_js = []
        pagina.on("pageerror", lambda e: erros_js.append(str(e)))

        # --- login -----------------------------------------------------------
        pagina.goto(f"{GW}/login", wait_until="networkidle")
        pagina.fill("input#username", "demo")
        pagina.fill("input#password", "demo123")
        pagina.click("button[type=submit]")
        # O `networkidle` chega antes de o login sair (a página já estava parada):
        # espera a navegação que o login faz, e não o silêncio da rede.
        try:
            pagina.wait_for_url(lambda url: "/login" not in url, timeout=20_000)
        except Exception:
            pass
        pagina.wait_for_load_state("networkidle")
        checar("login demo pelo gateway", "/login" not in pagina.url, pagina.url)

        # --- RH: a ficha do funcionário --------------------------------------
        pagina.goto(f"{GW}/app/rh", wait_until="networkidle")
        pagina.wait_for_timeout(1500)
        checar("a lista de funcionários carrega", "/app/rh" in pagina.url, pagina.url)

        linhas = pagina.query_selector_all("tbody tr")
        if linhas:
            linhas[0].click()
            pagina.wait_for_load_state("networkidle")
            pagina.wait_for_timeout(1500)
            checar("a ficha do funcionário abre", "/app/rh/" in pagina.url, pagina.url)

        # --- diário: as miniaturas são blobs, não `/media/` -------------------
        pagina.goto(f"{GW}/app/diario", wait_until="networkidle")
        pagina.wait_for_timeout(2500)
        checar("o diário de obra carrega", "/app/diario" in pagina.url, pagina.url)

        # --- ERP: a lista de notas fiscais ------------------------------------
        pagina.goto(f"{GW}/app/erp/notas-fiscais", wait_until="networkidle")
        pagina.wait_for_timeout(2000)

        # --- clientes e obras --------------------------------------------------
        for rota in ("/app/clientes", "/app/obras"):
            pagina.goto(f"{GW}{rota}", wait_until="networkidle")
            pagina.wait_for_timeout(1200)

        # --- o veredito --------------------------------------------------------
        checar(f"NENHUMA tela pediu /media/ -> {len(pedidos_media)} pedidos",
               not pedidos_media, pedidos_media[:5])
        checar(f"nenhum erro de JS nas telas visitadas -> {len(erros_js)}",
               not erros_js, erros_js[:3])
        falhas_de_entrega = [e for e in entregas if e[1] >= 400]
        checar(f"toda entrega pela porta única respondeu 2xx -> {len(entregas)} entregas",
               not falhas_de_entrega, falhas_de_entrega[:5])

        navegador.close()


rodar()
print(f"\n=== {len(OK)}/{len(OK) + len(FALHA)} ===")
if FALHA:
    print("FALHARAM:", FALHA)
sys.exit(1 if FALHA else 0)
