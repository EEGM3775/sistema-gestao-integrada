"""Os postos QUALIDADE e SEGURANÇA **na tela**, e os três atos de campo.

Sucessor do `pdca7_ficha_browser_test.py`, que dirigia a tela apagada em
20/09/2026 (D195). A régua dele continua valendo — critério junto da pergunta,
desvio que abre o texto e recusa **sem gastar requisição**, o peso perguntado
no item, F5 que não perde resposta, ficha concluída que vira leitura, "ação
executada" que não habilita encerrar, o 502 que não mostra a página do nginx —
e agora o caminho até a tela é o rail do posto e a fila dele.

O `pdca_qualidade_seguranca_posto_test.py` prova a API; este prova a tela:

  1. o rail leva aos dois postos, **destrancados**;
  2. a qualidade abre pelo **laço aberto** ao lado do que mais reprova, e a
     linha da fila **abre o documento** (a ficha), não só o posto;
  3. a ficha no escritório: conforme num toque, desvio com peso e texto, F5
     que não perde nada, conclusão que mostra o peso de cada reprovado;
  4. o defeito: plano de ação, "executada" que **não** habilita encerrar, e a
     eficácia que é de outra pessoa — dito na tela;
  5. a segurança: as duas taxas **sem apuração**, com a frase; registrar e
     classificar a ocorrência; o diálogo com a lista e o encerramento;
  6. o campo, em tela de celular: responder a ficha **uma pergunta por tela**,
     abrir o defeito do que reprovou, registrar ocorrência — sem rolagem
     lateral;
  7. o 502 forjado não mostra a página do nginx, e diz que nada foi gravado;
  8. e a tela fica **parada** — nenhuma requisição com a tela quieta, nenhum
     erro de JavaScript.

Tudo o que o roteiro cria vai para a lixeira no fim.

Rodar (stack de pé, imagem `react` rebuildada):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/pdca_qualidade_seguranca_browser_test.py
"""
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

from _segundo_fator import completar_login
import uuid
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright
from _sessao import cabecalhos, da_resposta

GW = os.environ.get("SGI_GW", "http://localhost:8090")
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_f5")
os.makedirs(SHOTS, exist_ok=True)
MARCA = "E2E F.5 tela " + uuid.uuid4().hex[:6]

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

passed = []
lixo: list[str] = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def login(u, p):
    data = json.dumps({"username": u, "password": p}).encode()
    r = urllib.request.Request(GW + "/auth/login/", data=data, method="POST",
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30, context=_CTX) as resp:
        return completar_login(GW, resp, _CTX)["sessao"]


def api(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(GW + path, data=data, method=method, headers={
        **cabecalhos(token), "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(r, timeout=90, context=_CTX) as resp:
            corpo = resp.read().decode()
            return resp.status, (json.loads(corpo) if corpo else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except Exception:
            return e.code, None


def lista(corpo):
    return corpo if isinstance(corpo, list) else (corpo or {}).get("results", [])


def limpar(admin):
    for caminho in reversed(lixo):
        api("DELETE", caminho, admin)


def fatal(msg, admin=None):
    print(f"\n  !! {msg}")
    if admin:
        limpar(admin)
    print(f"     Parcial: {sum(1 for p in passed if p)}/{len(passed)}")
    sys.exit(2)


def entrar(pagina, usuario, senha):
    pagina.goto(f"{GW}/login")
    pagina.wait_for_load_state("networkidle")
    pagina.fill("input#username", usuario)
    pagina.fill("input#password", senha)
    pagina.click("button[type=submit]")
    pagina.wait_for_url("**/app/**", timeout=25000)


def quieta(pagina, chamadas, ms=3000):
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(600)
    antes = len(chamadas)
    pagina.wait_for_timeout(ms)
    return len(chamadas) - antes


print(f"\n{'='*62}\nPDCA — qualidade e segurança na tela\n{'='*62}")
print(f"Gateway: {GW} · marca: {MARCA}")

try:
    admin = login("admin", "admin123")
    demo = login("demo", "demo123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé?")

codigo, obras = api("GET", "/api/obras/", demo)
if codigo != 200 or not lista(obras):
    fatal("sem obra no tenant demo", admin)
OBRA = lista(obras)[0]["obra_id"]

codigo, modelos = api("GET", "/api/pdca/modelos-verificacao/?ativo=true&page_size=100", demo)
candidatos = sorted(
    (m for m in lista(modelos) if m["itens_count"] >= 2),
    key=lambda m: m["itens_count"],
)
if not candidatos:
    fatal("nenhum modelo de ficha com duas perguntas — rode `semear_pdca_execucao`.", admin)
MODELO = candidatos[0]


def aplicar(inspetor):
    codigo, ficha = api("POST", "/api/pdca/verificacoes/aplicar/", demo, {
        "modelo": MODELO["modelo_id"], "obra": OBRA,
        "data": date.today().isoformat(), "inspetor": inspetor,
    })
    if codigo != 201:
        fatal(f"aplicar ficha respondeu {codigo}: {ficha}", admin)
    lixo.append(f"/api/pdca/verificacoes/{ficha['verificacao_id']}/")
    _, itens = api("GET", f"/api/pdca/itens-verificacao/?verificacao={ficha['verificacao_id']}&ordering=ordem&page_size=200", demo)
    return ficha["verificacao_id"], lista(itens)


FICHA_ESC, ITENS_ESC = aplicar(f"{MARCA} escritório")
FICHA_CAMPO, ITENS_CAMPO = aplicar(f"{MARCA} campo")
print(f"     obra {OBRA} · modelo {MODELO['codigo']} ({MODELO['itens_count']} perguntas)")

with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])

    # =====================================================================
    # O escritório
    # =====================================================================
    ctx = navegador.new_context(viewport={"width": 1500, "height": 950})
    pagina = ctx.new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))
    chamadas = []
    pagina.on("request", lambda r: chamadas.append(r.url) if "/api/pdca/" in r.url else None)

    print("\n1. O rail leva aos dois postos, destrancados")
    entrar(pagina, "demo", "demo123")
    pagina.goto(f"{GW}/app/pdca/o/{OBRA}/hoje")
    pagina.wait_for_load_state("networkidle")
    for nome in ("Qualidade", "Segurança"):
        check(f"o posto {nome.upper()} está no rail como link",
              pagina.get_by_role("link", name=re.compile(nome, re.I)).count() > 0)
    pagina.get_by_role("link", name=re.compile("Qualidade", re.I)).first.click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(800)
    check("o endereço é o do posto", f"/o/{OBRA}/qualidade" in pagina.url)

    print("\n2. A qualidade abre pelo laço aberto")
    corpo = pagina.inner_text("body")
    baixo = corpo.lower()
    check("a página abre pela fila do laço", "o laço aberto" in baixo)
    check("com o que mais reprova ao lado", "o que mais reprova" in baixo)
    check("a ficha parada aparece na fila, com o verbo que a fecha",
          "Ficha parada no meio" in corpo and "Terminar de responder" in corpo)
    # A faixa mostra as mais antigas primeiro e corta pelo teto; o tenant de
    # demonstração guarda fichas de execuções anteriores, então a nova pode
    # estar além do corte. O que se prova aqui é a forma da linha.
    check("a linha da fila é um link para o DOCUMENTO",
          pagina.locator("a[href*='qualidade?ficha=']").count() > 0)
    link_da_ficha = pagina.locator(f"a[href*='ficha={FICHA_ESC}']")
    if link_da_ficha.count():
        link_da_ficha.first.click()
    else:
        pagina.goto(f"{GW}/app/pdca/o/{OBRA}/qualidade?ficha={FICHA_ESC}")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(800)
    check("a ficha abre no endereço dela", f"ficha={FICHA_ESC}" in pagina.url)

    print("\n3. A ficha no escritório")
    corpo = pagina.inner_text("body")
    check("o nome do modelo está na tela", MODELO["nome"] in corpo)
    com_criterio = next((i for i in ITENS_ESC if i["criterio"]), None)
    if com_criterio:
        check("o critério vem junto da pergunta", com_criterio["criterio"] in corpo)
    reprovado = ITENS_ESC[0]
    k = reprovado["ordem"]
    grupo = pagina.get_by_role("group", name=f"Resposta da pergunta {k}")
    grupo.get_by_role("button", name="Não conforme", exact=True).click()
    pagina.wait_for_timeout(300)
    check("o desvio abre o texto e o peso na hora",
          pagina.get_by_role("group", name=f"Gravidade da pergunta {k}").count() == 1
          and pagina.get_by_label(f"Observação da pergunta {k}").count() == 1)
    antes = len(chamadas)
    gravar = pagina.get_by_role("button", name="Gravar resposta")
    check("sem texto e sem peso, o botão recusa — sem gastar requisição",
          gravar.is_disabled() and len(chamadas) == antes)
    pagina.get_by_role("group", name=f"Gravidade da pergunta {k}").get_by_role(
        "button", name=re.compile("^Maior")).click()
    pagina.get_by_label(f"Observação da pergunta {k}").fill(f"{MARCA} — fora de prumo")
    gravar.click()
    pagina.wait_for_load_state("networkidle")
    for item in ITENS_ESC[1:]:
        pagina.get_by_role("group", name=f"Resposta da pergunta {item['ordem']}").get_by_role(
            "button", name="Conforme", exact=True).click()
        pagina.wait_for_load_state("networkidle")
        pagina.wait_for_timeout(250)
    pagina.reload()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(800)
    _, itens = api("GET", f"/api/pdca/itens-verificacao/?verificacao={FICHA_ESC}&page_size=200", demo)
    check("depois do F5, nenhuma resposta se perdeu",
          all(i["resultado"] != "pendente" for i in lista(itens)))
    check("e a reprovada guardou peso e texto",
          any(i["resultado"] == "nao_conforme" and i["gravidade"] == "maior"
              and MARCA in i["observacao"] for i in lista(itens)))

    pagina.get_by_role("button", name="Concluir a ficha").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(800)
    corpo = pagina.inner_text("body")
    check("concluída, ela vira leitura e diz que corrigir é reinspecionar",
          "reinspecionar" in corpo and pagina.get_by_role("button", name="Concluir a ficha").count() == 0)
    check("a conclusão mostra o peso que cada reprovado recebeu", "— Maior" in corpo)
    pagina.get_by_role("button", name="Abrir o defeito").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(900)
    m = re.search(r"nc=(\d+)", pagina.url)
    check("abrir o defeito leva ao documento dele", m is not None)
    if m:
        lixo.append(f"/api/pdca/ncs/{m.group(1)}/")

    print("\n4. O defeito e o laço")
    corpo = pagina.inner_text("body")
    check("o defeito diz o próximo passo", "Próximo passo: montar o plano de ação" in corpo)
    check("e mostra de que ficha veio", "Veio de uma ficha de verificação" in corpo)
    pagina.get_by_role("button", name="Montar o plano de ação").click()
    pagina.get_by_label("O que será feito").fill(f"{MARCA} — refazer a fiada")
    pagina.get_by_label("Quem").fill("Equipe da alvenaria")
    pagina.get_by_role("button", name="Gravar ação").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(700)
    pagina.get_by_role("button", name="Executada").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(700)
    corpo = pagina.inner_text("body")
    check("executada, o próximo passo é a eficácia", "Próximo passo: verificar a eficácia" in corpo)
    check("e NÃO aparece botão de encerrar",
          pagina.get_by_role("button", name="Encerrar o defeito").count() == 0)
    check("a tela diz que a eficácia é de outra pessoa",
          "quem montou o plano não assina que ele funcionou" in corpo)
    novas = quieta(pagina, chamadas)
    check(f"com a tela parada, nenhuma requisição nova (foram {novas})", novas == 0)

    print("\n5. A segurança")
    pagina.get_by_role("link", name=re.compile("Segurança", re.I)).first.click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(900)
    corpo = pagina.inner_text("body")
    check("o posto abre pelo que pede ação", "o que pede ação" in corpo.lower())
    check("as duas taxas aparecem SEM APURAÇÃO, nunca zero",
          corpo.count("sem apuração") >= 2 and "homem-hora" in corpo)
    pagina.get_by_role("button", name="Registrar ocorrência").first.click()
    pagina.get_by_role("button", name="Quase-acidente", exact=True).click()
    pagina.get_by_label("O que aconteceu").fill(f"{MARCA} — martelo caiu do andaime")
    pagina.get_by_role("button", name="Registrar", exact=True).click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(900)
    m = re.search(r"ocorrencia=(\d+)", pagina.url)
    check("registrada, a ocorrência abre no documento dela", m is not None)
    if m:
        lixo.append(f"/api/pdca/ocorrencias/{m.group(1)}/")
    check("e nasce sem classificação", "Ainda não classificada" in pagina.inner_text("body"))
    pagina.get_by_role("button", name="Sem afastamento", exact=True).click()
    pagina.get_by_role("button", name="Classificar", exact=True).click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(700)
    check("classificada, a tela oferece reclassificar",
          pagina.get_by_role("button", name="Reclassificar").count() == 1)

    pagina.get_by_role("tab", name=re.compile("Diálogos de segurança")).click()
    pagina.wait_for_timeout(600)
    pagina.get_by_role("button", name=re.compile("Novo diálogo|Registrar o primeiro")).first.click()
    pagina.get_by_label("Tema", exact=True).fill(f"{MARCA} — cinto na periferia")
    pagina.get_by_role("button", name="Abrir e colher a lista").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(700)
    m = re.search(r"dds=(\d+)", pagina.url)
    check("o diálogo abre no endereço dele", m is not None)
    if m:
        lixo.append(f"/api/pdca/dds/{m.group(1)}/")
    pagina.get_by_label("Acrescentar nomes").fill("Fulano da Silva\nBeltrana Souza")
    pagina.get_by_role("button", name="Acrescentar 2 nomes").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(600)
    check("a lista mostra os dois presentes", "2 presentes" in pagina.inner_text("body"))
    pagina.get_by_label("Escrever este diálogo no diário da obra").uncheck()
    pagina.get_by_role("button", name="Encerrar o diálogo").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(700)
    check("encerrado, a lista fecha", "Acrescentar nomes" not in pagina.inner_text("body"))

    print("\n7. O 502 forjado")
    pagina.goto(f"{GW}/app/pdca/o/{OBRA}/qualidade?v=defeitos")
    pagina.wait_for_load_state("networkidle")
    pagina.route("**/api/pdca/ncs/", lambda r: r.fulfill(
        status=502, content_type="text/html",
        body="<html><head><title>502 Bad Gateway</title></head><body><center>nginx</center></body></html>",
    ) if r.request.method == "POST" else r.continue_())
    pagina.get_by_role("button", name="Registrar defeito").click()
    pagina.get_by_label("O que está errado").fill(f"{MARCA} — nunca chega")
    pagina.get_by_role("button", name=re.compile("^Menor")).click()
    pagina.get_by_role("dialog").get_by_role("button", name="Registrar defeito").click()
    pagina.wait_for_timeout(900)
    corpo = pagina.inner_text("body")
    check("a tela NÃO mostra a página do nginx", "Bad Gateway" not in corpo and "nginx" not in corpo)
    check("e diz que nada do que foi digitado foi gravado", "nada do que você digitou foi gravado" in corpo)
    pagina.unroute("**/api/pdca/ncs/")
    check(f"nenhum erro de JavaScript no escritório ({len(erros_js)})", not erros_js)
    for erro in erros_js[:3]:
        print("       ", erro[:160])
    pagina.screenshot(path=f"{SHOTS}/escritorio.png")
    ctx.close()

    # =====================================================================
    # O campo, em tela de celular
    # =====================================================================
    print("\n6. O campo, em tela de celular")
    ctx = navegador.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pagina = ctx.new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))
    entrar(pagina, "campo", "campo123")
    pagina.goto(f"{GW}/campo")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(800)
    corpo = pagina.inner_text("body")
    check("a frente oferece os três atos de registro",
          all(t in corpo for t in ("Defeito com foto", "Ocorrência de segurança", "Diálogo de segurança")))

    pagina.goto(f"{GW}/campo/ficha/{FICHA_CAMPO}")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(800)
    check("a ficha abre uma pergunta por tela",
          f"Pergunta 1 de {len(ITENS_CAMPO)}" in pagina.inner_text("body"))
    for n, item in enumerate(ITENS_CAMPO):
        ultima = n == len(ITENS_CAMPO) - 1
        resposta = pagina.get_by_role("group", name="Resposta")
        if ultima:
            resposta.get_by_role("button", name="Não conforme", exact=True).click()
            pagina.get_by_role("group", name="Gravidade").get_by_role(
                "button", name=re.compile("^Crítica")).click()
            pagina.get_by_label("O que está errado").fill(f"{MARCA} — falta a maçaneta")
            pagina.get_by_role("button", name="Gravar e seguir").click()
        else:
            resposta.get_by_role("button", name="Conforme", exact=True).click()
            pagina.wait_for_timeout(250)
            if pagina.get_by_role("button", name="Gravar e seguir").count():
                pagina.get_by_role("button", name="Gravar e seguir").click()
        pagina.wait_for_load_state("networkidle")
        pagina.wait_for_timeout(350)
    corpo = pagina.inner_text("body")
    check("respondidas todas, a tela vai para a revisão", "Revisão" in corpo)
    largura = pagina.evaluate("document.scrollingElement.scrollWidth - window.innerWidth")
    check(f"sem rolagem lateral no celular ({largura}px a mais)", largura <= 1)
    pagina.get_by_role("button", name="Concluir a ficha").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(700)
    check("concluída pelo campo", "Ficha concluída" in pagina.inner_text("body"))
    pagina.get_by_role("button", name=re.compile("Abrir o defeito")).click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(700)
    check("e o defeito do que reprovou se abre dali", "Defeito aberto" in pagina.inner_text("body"))
    _, itens = api("GET", f"/api/pdca/itens-verificacao/?verificacao={FICHA_CAMPO}&page_size=200", demo)
    for i in lista(itens):
        if i.get("nc"):
            lixo.append(f"/api/pdca/ncs/{i['nc']}/")
    check("com o peso que o campo deu — crítica",
          any(i.get("gravidade") == "critica" and i.get("nc") for i in lista(itens)))

    pagina.goto(f"{GW}/campo/ocorrencia?obra={OBRA}")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(600)
    pagina.get_by_role("button", name="Quase-acidente", exact=True).click()
    pagina.get_by_label("O que aconteceu").fill(f"{MARCA} — tábua solta no 3º")
    pagina.get_by_role("button", name="Registrar", exact=True).click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(700)
    check("a ocorrência do campo é registrada", "Registrada" in pagina.inner_text("body"))
    _, ocorrencias = api("GET", f"/api/pdca/ocorrencias/?obra={OBRA}&search={MARCA.split()[-1]}", demo)
    for o in lista(ocorrencias):
        lixo.append(f"/api/pdca/ocorrencias/{o['ocorrencia_id']}/")
    check(f"nenhum erro de JavaScript no campo ({len(erros_js)})", not erros_js)
    pagina.screenshot(path=f"{SHOTS}/campo.png")
    ctx.close()
    navegador.close()

limpar(admin)
total = len(passed)
ok = sum(1 for p in passed if p)
print(f"\n{'='*62}\nResultado: {ok}/{total}\n{'='*62}")
sys.exit(0 if ok == total else 1)
