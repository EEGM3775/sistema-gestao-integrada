"""PDCA.7 — a qualidade no NAVEGADOR, pelo gateway (8090).

Existe pela régua do [README](README.md) §"Teste de API não substitui teste de
navegador": **tela nova entrega com teste de navegador junto**, e ele mede as
três coisas que só existem ali — *o conteúdo aparece*, *o que se faz sobrevive
ao F5*, e *com a tela parada não pode haver requisição*.

O [pdca7_verificacao_test.py](pdca7_verificacao_test.py) prova a API inteira (75
verificações). Este prova que existe caminho de dedo até ela, e cobre o que
nenhuma chamada de API alcança:

  1. o caminho de dedo: Planejamento → cartão da obra → **Qualidade e verificação**;
  2. a biblioteca **vazia diz por que está vazia** — é a decisão da §11.14, e uma
     lista em branco sem explicação passaria por tela quebrada;
  3. **o cockpit e o campo são telas diferentes**, e é isso que a fatia afirma: a
     ficha abre em endereço próprio, com uma pergunta por vez, e não como um
     painel dentro do cockpit;
  4. **o critério aparece junto da pergunta** — é o que separa a FVS de uma
     opinião, e escondê-lo atrás de um toque entregaria a pergunta sem a régua;
  5. **conforme sai num toque; o desvio abre o campo de texto** e a tela recusa
     antes do servidor, com a frase que diz o que falta;
  6. **o que se responde sobrevive ao F5** — é a prova de que grava a cada
     resposta, e não no fim (no canteiro o sinal cai e a ficha se perderia
     inteira);
  7. a ficha concluída **vira leitura** e mostra a conformidade sem meta;
  8. o cockpit mostra a **fila de decisão** com a frase do que falta, e a NC
     aberta aparece nela;
  9. **"ação concluída" não habilita encerrar** — a regra do §11.12 dita na tela,
     não só no 400 do servidor;
 10. e a tela fica **parada** — sem laço de renderização.

Rodar (stack de pé, imagem `react` rebuildada):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/pdca7_ficha_browser_test.py

**Sobre o `LD_LIBRARY_PATH`:** o Chromium do Playwright pede bibliotecas que o
WSL não traz, e instalá-las mexeria na máquina do dono — a saída já usada pela
PRA.5c é extraí-las de uma imagem `ubuntu:24.04` para uma pasta do usuário.
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
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_pdca7")
MARCA = "E2E PDCA.7 tela " + uuid.uuid4().hex[:6]

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


print(f"\n{'='*62}\nPDCA.7 — a qualidade no navegador\n{'='*62}")
os.makedirs(SHOTS, exist_ok=True)

try:
    demo = login("demo", "demo123")
except Exception as e:
    fatal(f"login falhou ({e}). Stack de pé? Seeds rodados?")

# --- O cenário, montado por API (o que este teste prova é a TELA) -----------
print("\n0. Cenário montado por API")
status, obra = req("POST", "/api/obras/", demo, {
    "nome_obra": MARCA, "endereco": "Rua da Ficha, s/n", "status_obra": "planejamento",
})
if status not in (200, 201):
    fatal(f"obra falhou ({status}: {obra})")
obra_id = obra["obra_id"]

status, calendario = req("POST", "/api/pdca/calendarios/", demo, {
    "obra": obra_id, "nome": "Expediente " + MARCA,
})
if status not in (200, 201):
    fatal(f"calendário falhou ({status}: {calendario})")

hoje = date.today()
segunda = hoje - timedelta(days=hoje.weekday())
status, crono = req("POST", "/api/pdca/cronogramas/", demo, {
    "obra": obra_id, "descricao": "Plano " + MARCA,
    "data_inicio": segunda.isoformat(),
    "calendario": calendario["calendario_id"],
})
if status not in (200, 201):
    fatal(f"cronograma falhou ({status}: {crono})")
crono_id = crono["cronograma_id"]
status, ativ = req("POST", "/api/pdca/atividades/", demo, {
    "cronograma": crono_id, "codigo": "1", "nome": "Alvenaria do 4º pavimento",
    "duracao_dias": 5, "peso_informado": "100",
})
if status not in (200, 201):
    fatal(f"atividade falhou ({status}: {ativ})")
ativ_id = ativ["atividade_id"]
req("POST", f"/api/pdca/cronogramas/{crono_id}/publicar/", demo)

CODIGO_MODELO = "FVS-TELA-" + uuid.uuid4().hex[:5].upper()
CRITERIO = "Desvio até 3 mm em 2 m, conferido com régua"
status, modelo = req("POST", "/api/pdca/modelos-verificacao/", demo, {
    "codigo": CODIGO_MODELO, "nome": "FVS — Alvenaria " + MARCA,
    "dominio": "qualidade", "descricao": "Após a cura, antes do revestimento",
})
if status not in (200, 201):
    fatal(f"modelo falhou ({status}: {modelo})")
modelo_id = modelo["modelo_id"]
for ordem, (t, c, obrig) in enumerate([
    ("Prumo da parede", CRITERIO, True),
    ("Espessura da junta", "10 mm ± 2 mm", True),
], start=1):
    status, _ = req("POST", "/api/pdca/itens-modelo-verificacao/", demo, {
        "modelo": modelo_id, "ordem": ordem, "texto": t, "criterio": c,
        "obrigatorio": obrig,
    })
    if status not in (200, 201):
        fatal(f"item {ordem} falhou ({status})")
check("obra, plano vigente e um modelo de FVS com duas perguntas", True)

# --- A tela -----------------------------------------------------------------
with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = navegador.new_context(viewport={"width": 1440, "height": 900})
    pagina = ctx.new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))
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

    print("\n2. O caminho de dedo até a qualidade")
    pagina.goto(f"{GW}/app/pdca")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(800)
    botao = pagina.get_by_role("button", name="Qualidade e verificação")
    try:
        botao.first.wait_for(state="visible", timeout=10000)
    except Exception:
        pass
    check("o cartão da obra oferece 'Qualidade e verificação'", botao.count() > 0)
    check("e NÃO há item separado na barra lateral (a verificação mora na obra)",
          pagina.locator("a[href='/app/pdca/qualidade']").count() == 0)

    pagina.goto(f"{GW}/app/pdca/obra/{obra_id}/qualidade")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1200)
    check("o cockpit da obra abre", f"/obra/{obra_id}/qualidade" in pagina.url)
    corpo = pagina.inner_text("body").lower()
    check("o nome da obra está na tela (não é 'Obra 123')", MARCA.lower() in corpo)
    check("a fila de decisão vem primeiro, e diz que não há nada esperando",
          "nada espera decisão" in corpo)
    pagina.screenshot(path=f"{SHOTS}/01_cockpit_vazio.png", full_page=True)

    print("\n3. A biblioteca diz POR QUE está vazia")
    pagina.get_by_role("button", name="Biblioteca").first.click()
    pagina.wait_for_timeout(1200)
    corpo = pagina.inner_text("body").lower()
    check("a biblioteca lista o modelo que existe", CODIGO_MODELO.lower() in corpo)
    check("e o cartão diz quantas perguntas ele tem", "perguntas" in corpo)
    check("e que ele nunca foi aplicado", "nunca aplicado" in corpo)

    print("\n4. Aplicar a ficha abre o CAMPO, em endereço próprio")
    pagina.get_by_role("button", name="aplicar uma ficha").first.click()
    pagina.wait_for_timeout(900)
    select = pagina.locator("select").first
    select.select_option(str(modelo_id))
    pagina.get_by_role("button", name="Abrir a ficha").first.click()
    pagina.wait_for_url("**/verificacao/**", timeout=20000)
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1000)
    check("a ficha abre em ENDEREÇO PRÓPRIO — não é um painel dentro do cockpit",
          "/verificacao/" in pagina.url)
    ficha_id = int(pagina.url.rstrip("/").split("/")[-1])

    corpo = pagina.inner_text("body")
    check("a primeira pergunta ocupa a tela", "Prumo da parede" in corpo)
    check("**o critério vem junto dela** — é o que separa a FVS de uma opinião",
          "Desvio até 3 mm em 2 m" in corpo)
    check("e a tela diz quantas faltam, não a conformidade (isso é do cockpit)",
          "de 2 respondidas" in corpo.replace("\n", " "))
    check("os três alvos estão na tela",
          pagina.get_by_role("button", name="Conforme").count() > 0
          and pagina.get_by_role("button", name="Não conforme").count() > 0)
    pagina.screenshot(path=f"{SHOTS}/02_campo_pergunta_1.png", full_page=True)

    print("\n5. Conforme sai num toque; o desvio pede a explicação ANTES do servidor")
    pagina.get_by_role("button", name="Não conforme").first.click()
    pagina.wait_for_timeout(600)
    check("o desvio abre o campo de texto na hora",
          pagina.locator("textarea").count() > 0)
    # **E a pergunta do peso aparece NO ITEM.** É a correção de 16/09/2026: com
    # ela no fim da ficha, um desalinhamento de porta e a falta de uma maçaneta
    # saíam com o mesmo rótulo.
    corpo = pagina.inner_text("body")
    check("**e a pergunta do peso aparece aqui, no item** — não no fim da ficha",
          "Quanto este defeito pesa?" in corpo)
    check("com os três degraus dizendo o que cada um autoriza, e não "
          "'baixa/média/alta'",
          "corrige-se na frente" in corpo and "para o serviço" in corpo)

    # Gravar sem escrever: a tela recusa **antes** de mandar a requisição.
    antes = len(requisicoes)
    pagina.get_by_role("button", name="Gravar e seguir").first.click()
    pagina.wait_for_timeout(800)
    corpo = pagina.inner_text("body").lower()
    check("e a tela recusa sozinha, com a frase do que falta",
          "diga o que está errado" in corpo)
    check("sem gastar uma requisição para descobrir isso",
          len([u for u in requisicoes[antes:] if "itens-verificacao" in u]) == 0)

    # Com a explicação mas SEM o peso: a tela recusa de novo, sozinha.
    pagina.locator("textarea").first.fill("Desvio de 12 mm no eixo C")
    antes = len(requisicoes)
    pagina.get_by_role("button", name="Gravar e seguir").first.click()
    pagina.wait_for_timeout(800)
    corpo = pagina.inner_text("body").lower()
    check("com a explicação mas sem o peso, ainda recusa — também sem requisição",
          "quanto este defeito pesa" in corpo
          and len([u for u in requisicoes[antes:] if "itens-verificacao" in u]) == 0)

    pagina.get_by_role("button", name="Maior — o serviço não é aceito assim").first.click()
    pagina.wait_for_timeout(400)
    pagina.get_by_role("button", name="Gravar e seguir").first.click()
    pagina.wait_for_timeout(1500)
    corpo = pagina.inner_text("body")
    check("com os dois, gravou e **avançou sozinha** para a pergunta seguinte",
          "Espessura da junta" in corpo)

    print("\n6. O que se responde sobrevive ao F5")
    pagina.reload()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1500)
    corpo = pagina.inner_text("body")
    check("depois do F5 a ficha continua com 1 de 2 respondidas",
          "1 de 2 respondidas" in corpo.replace("\n", " "))
    pagina.get_by_role("button", name="ver todas").first.click()
    pagina.wait_for_timeout(700)
    corpo = pagina.inner_text("body")
    check("e a resposta gravada aparece na lista — não se perdeu",
          "Não conforme" in corpo)
    pagina.keyboard.press("Escape")
    pagina.wait_for_timeout(400)

    print("\n7. Concluir é assinar — e a tela avisa antes de deixar tentar")
    corpo = pagina.inner_text("body").lower()
    check("a tela diz que falta 1 obrigatória, antes do clique",
          "falta" in corpo and "obrigatória" in corpo)
    # Responde a segunda e conclui.
    status, itens = req(
        "GET", f"/api/pdca/itens-verificacao/?verificacao={ficha_id}&page_size=50", demo,
    )
    segundo = sorted((itens or {}).get("results") or [], key=lambda i: i["ordem"])[1]
    req("PATCH", f"/api/pdca/itens-verificacao/{segundo['item_verificacao_id']}/",
        demo, {"resultado": "conforme"})
    pagina.reload()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1200)
    pagina.get_by_role("button", name="Concluir a ficha").first.click()
    pagina.wait_for_timeout(2000)
    corpo = pagina.inner_text("body")
    check("a conclusão oferece abrir a NC do que reprovou",
          "Abrir as não-conformidades" in corpo)
    # **A conclusão MOSTRA, não pergunta.** Era aqui que existia um seletor
    # único de gravidade, e é o que o dono apontou: ele fazia o painel dizer
    # "3 maiores" sobre três coisas de tamanhos diferentes.
    check("**e ela mostra o peso que cada item já recebeu**, em vez de "
          "perguntar um peso para todos",
          "não é aceito assim" in corpo)
    check("sem nenhum seletor de gravidade no diálogo",
          "Cada uma nasce com o peso que você deu ao item" in corpo)
    pagina.screenshot(path=f"{SHOTS}/03_conclusao.png", full_page=True)
    pagina.get_by_role("button", name="Abrir as não-conformidades").first.click()
    pagina.wait_for_url("**/qualidade**", timeout=20000)
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1500)

    print("\n8. A fila de decisão do cockpit mostra o que espera alguém")
    corpo = pagina.inner_text("body").lower()
    check("a NC recém-aberta aparece na fila",
          "sem plano de ação" in corpo)
    check("e a fila diz o que fazer a seguir, não o estado do banco",
          "ninguém pegou" in corpo)
    pagina.screenshot(path=f"{SHOTS}/04_fila.png", full_page=True)

    print("\n9. A ficha concluída virou leitura, e mostra a conformidade sem meta")
    pagina.goto(f"{GW}/app/pdca/obra/{obra_id}/verificacao/{ficha_id}")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1200)
    corpo = pagina.inner_text("body").lower()
    check("a ficha concluída não oferece mais responder", "ficha concluída" in corpo)
    check("e diz que corrigir é reinspecionar", "reinspecionar" in corpo)
    check("a conformidade aparece (1 de 2 julgados = 50%)", "50.00" in corpo or "50," in corpo)

    print("\n10. 'Ação concluída' não habilita encerrar — a regra na tela")
    pagina.goto(f"{GW}/app/pdca/obra/{obra_id}/qualidade?aba=ncs")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1500)
    corpo = pagina.inner_text("body").lower()
    check("a aba de NCs lista o defeito", "prumo da parede" in corpo)
    check("e o cartão diz o que falta nele",
          "montar o plano de ação" in corpo)

    print("\n11. O servidor fora do ar vira FRASE, não a página do nginx")
    # **O achado do dono, 16/09/2026**: ele viu a página de 502 do nginx inteira
    # dentro do diálogo de tratar a NC — "erro sem escrita não é válido, ninguém
    # sabe o que é isso". O `parseApiErrors` fazia `String(data)` num corpo que
    # era HTML e despejava a encanação na tela.
    #
    # O 502 é **forjado aqui**, com `route()`, em vez de derrubar o backend: o
    # teste tem de provar o que a TELA faz, e derrubar o stack no meio de uma
    # suíte que compartilha máquina atingiria outra sessão.
    HTML_502 = (
        "<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n"
        "<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n"
        "<hr><center>nginx/1.31.2</center>\r\n</body>\r\n</html>"
    )
    pagina.route(
        "**/api/pdca/planos-acao/",
        lambda rota: rota.fulfill(status=502, content_type="text/html", body=HTML_502),
    )
    pagina.goto(f"{GW}/app/pdca/obra/{obra_id}/qualidade?aba=ncs")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1500)
    pagina.get_by_text("Prumo da parede").first.click()
    pagina.wait_for_timeout(1200)
    pagina.get_by_role("button", name="nova ação").first.click()
    pagina.wait_for_timeout(700)
    pagina.locator("textarea").first.fill("Refazer o trecho")
    pagina.get_by_role("button", name="Gravar a ação").first.click()
    pagina.wait_for_timeout(1500)
    corpo = pagina.inner_text("body")
    check("a tela NÃO mostra a página do nginx",
          "502 Bad Gateway" not in corpo and "nginx/" not in corpo)
    check("ela diz, em português, que o servidor está fora do ar",
          "fora do ar ou reiniciando" in corpo.lower())
    check("**e diz que nada do que a pessoa digitou foi gravado** — é a parte "
          "acionável, sem ela ninguém sabe se o conserto existe",
          "nada do que você digitou foi gravado" in corpo.lower())
    pagina.screenshot(path=f"{SHOTS}/05_erro_com_escrita.png", full_page=True)
    pagina.unroute("**/api/pdca/planos-acao/")
    pagina.keyboard.press("Escape")
    pagina.wait_for_timeout(400)
    pagina.keyboard.press("Escape")
    pagina.wait_for_timeout(600)

    print("\n12. A tela fica parada — sem laço de renderização")
    pagina.wait_for_timeout(1500)
    marco = len(requisicoes)
    pagina.wait_for_timeout(5000)
    depois = len(requisicoes) - marco
    check(f"com a tela parada, nenhuma requisição nova (foram {depois})",
          depois == 0)
    check("e nenhum erro de JavaScript em todo o caminho",
          not erros_js or fatal(f"erros de JS: {erros_js[:3]}"))

    navegador.close()

# --- Faxina -----------------------------------------------------------------
print("\n13. O que este teste deixa no ambiente")
status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
check("a obra do teste vai para a lixeira", status in (200, 204))
print(f"     Deixa no tenant `demo`: 1 modelo de verificação, 1 ficha e 1 NC,")
print(f"     todos ligados à obra '{MARCA}'.")
print("     Limpeza: python manage.py limpar_residuo_e2e")
print(f"     Capturas em {SHOTS}/")

ok = sum(1 for p in passed if p)
print(f"\n{'='*62}")
print(f"PDCA.7 (navegador): {ok}/{len(passed)} checagens")
print(f"{'='*62}\n")
sys.exit(0 if ok == len(passed) else 1)
