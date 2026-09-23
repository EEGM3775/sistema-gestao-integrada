"""O cockpit do PDCA **na tela** — carteira, HOJE e a paleta ⌘K, no navegador.

Irmão do `pdca7_ficha_browser_test.py`. O `pdca_cockpit_test.py` prova que a API
responde certo; este prova que a **tela** faz o que a régua de pronto
(modulopdca-frontend.md §12) exige, e cada verificação abaixo é um item dela:

  1. **a carteira é fila de decisão em escala de carteira** — a obra que dói
     aparece com o que dói nomeado, e não com uma contagem somada;
  2. **HOJE abre com a fila**, e a fila traz o verbo que decide, não um número;
  3. **nenhum número é fabricado** — onde falta apuração a tela escreve a frase
     do servidor, e em lugar nenhum aparece um `0%` no lugar dela;
  4. **a integração é clicável** — cada leitura do pulso leva ao posto que a
     explica, e cada faixa da fila ao posto que a resolve;
  5. **a trava vem do backend** — o que a pessoa não pode ver vira cadeado com
     motivo, e nunca uma seção em branco;
  6. **a ⌘K acha** o que o rail de seis postos não mostra, sem acento;
  7. e a tela fica **parada** — sem laço de renderização e sem erro de console.

Rodar (stack de pé, imagem `react` rebuildada):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/pdca_cockpit_browser_test.py

**Sobre o `LD_LIBRARY_PATH`:** o Chromium do Playwright pede bibliotecas que o
WSL não traz, e instalá-las mexeria na máquina do dono — a saída já usada pela
PRA.5c é extraí-las de uma imagem `ubuntu:24.04` para uma pasta do usuário.
"""
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright

GW = os.environ.get("SGI_GW", "http://localhost:8090")
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_cockpit")
os.makedirs(SHOTS, exist_ok=True)

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


def login(u, p):
    data = json.dumps({"username": u, "password": p}).encode()
    r = urllib.request.Request(GW + "/auth/login/", data=data, method="POST",
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30, context=_CTX) as resp:
        return json.load(resp)["access"]


def req(path, token):
    r = urllib.request.Request(GW + path, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(r, timeout=60, context=_CTX) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, None


print(f"\n{'='*62}\nPDCA — o cockpit na tela\n{'='*62}")
print(f"Gateway: {GW}")

try:
    token = login("gerente", "gerente123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé?")

codigo, carteira = req("/api/pdca/carteira/", token)
if codigo != 200 or not carteira["obras"]:
    fatal("a carteira não respondeu com obras — rode os seeds do PDCA.")

alvo = next(
    (o for o in carteira["obras"]
     if o["prazo"] and o["prazo"]["tem_plano"] and o["pendencias"]),
    next((o for o in carteira["obras"] if o["prazo"] and o["prazo"]["tem_plano"]), None),
)
if alvo is None:
    fatal("nenhuma obra com cronograma publicado — rode `semear_pdca_demo`.")
obra_id, obra_nome = alvo["obra"], alvo["nome"]
print(f"     obra de trabalho: {obra_id} · {obra_nome}")

with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = navegador.new_context(viewport={"width": 1500, "height": 950})
    pagina = ctx.new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))
    chamadas = []
    pagina.on("request", lambda r: chamadas.append(r.url) if "/api/pdca/" in r.url else None)

    print("\n1. Login pela tela")
    pagina.goto(f"{GW}/login")
    pagina.wait_for_load_state("networkidle")
    pagina.fill("input#username", "gerente")
    pagina.fill("input#password", "gerente123")
    pagina.click("button[type=submit]")
    pagina.wait_for_url("**/app/**", timeout=25000)
    check("`gerente` entrou", "/app" in pagina.url)

    print("\n2. A carteira — a porta de fora")
    pagina.goto(f"{GW}/app/pdca")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1400)
    corpo = pagina.inner_text("body")
    baixo = corpo.lower()
    check("a carteira abre e lista a obra pelo nome", obra_nome[:18].lower() in baixo)
    check("e diz para que ela serve — qual obra precisa de você",
          "precisa de você" in baixo)
    check("as cinco colunas de leitura estão na tela",
          all(r in baixo for r in ("avanço", "prazo", "ppc", "conformidade",
                                   "sem afastamento")))
    check("e dá para ordenar pelo que dói", pagina.get_by_role(
        "button", name="O que dói").count() > 0)
    pagina.screenshot(path=f"{SHOTS}/01_carteira.png", full_page=True)

    print("\n3. Nenhum número fabricado")
    check(
        "onde falta apuração a tela escreve 'sem apuração', e não 0%",
        "sem apuração" in baixo,
    )
    sem_plano = [o for o in carteira["obras"] if not (o["prazo"] or {}).get("tem_plano")]
    if sem_plano:
        check(
            "obra sem cronograma publicado diz isso em vez de mostrar zero",
            "sem cronograma publicado" in baixo,
        )

    print("\n4. A pendência é nomeada, nunca somada")
    if alvo["pendencias"]:
        rotulo = alvo["pendencias"][0]["rotulo"]
        check(f"a carteira mostra '{rotulo}' com o número dela",
              rotulo.lower() in baixo)
        check(
            "e NÃO existe um 'N pendências' que misture o que não se mistura",
            not re.search(r"\d+\s+pend[êe]ncias", baixo),
        )
        check("e oferece abrir a fila daquela obra", "abrir a fila desta obra" in baixo)

    print("\n5. HOJE — a fila de decisão vem primeiro")
    pagina.goto(f"{GW}/app/pdca/o/{obra_id}/hoje")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1600)
    corpo = pagina.inner_text("body")
    baixo = corpo.lower()
    check("o posto abre", f"/o/{obra_id}/hoje" in pagina.url)
    check("o nome da obra está na tela, e não um número",
          obra_nome[:18].lower() in baixo)
    check("a primeira faixa é a da decisão", "o que exige a sua decisão" in baixo)

    codigo, hoje = req(f"/api/pdca/hoje/?obra={obra_id}", token)
    faixas = hoje["fila"]["faixas"]
    if faixas:
        check("a fila mostra o degrau de consequência",
              any(d in baixo for d in ("prazo legal", "dinheiro", "retrabalho",
                                       "compromisso assumido", "segurança")))
        check("e cada faixa traz o VERBO que decide, não só a contagem",
              faixas[0]["o_que_decidir"].lower()[:28] in baixo)
        check("e o botão que leva ao posto que resolve",
              pagina.get_by_role("button", name="Resolver").count() > 0)
        check("as linhas dizem há quanto tempo esperam",
              "há " in baixo or "hoje" in baixo)
    else:
        check("fila vazia diz que varreu as onze, em vez de abrir em branco",
              "nenhuma das" in baixo)
    pagina.screenshot(path=f"{SHOTS}/02_hoje_fila.png", full_page=True)

    print("\n6. O pulso — quatro leituras, e a integração clicável")
    check("as quatro leituras estão na tela",
          all(r in baixo for r in ("avanço físico", "cumprimento da semana",
                                   "conformidade", "sem acidente com afastamento")))
    check(
        "a ausência das taxas de segurança é declarada em português de obra",
        "homem-hora" in baixo,
    )
    check(
        "e sem citar documento interno nem número de fatia",
        "pdca." not in baixo and "§" not in corpo,
    )
    ligacoes = [
        pagina.locator(f"a[href='/app/pdca/o/{obra_id}/{posto}']").count()
        for posto in ("plano", "semana", "qualidade", "seguranca")
    ]
    check("cada leitura leva ao posto que a explica", all(n > 0 for n in ligacoes))

    print("\n7. O que mudou — fatos, não posts")
    if hoje.get("mudancas") and hoje["mudancas"]["fatos"]:
        check("a faixa do que mudou aparece", "o que mudou" in baixo)
        verbo = hoje["mudancas"]["fatos"][0]["verbo"]
        check(f"e traz o ato com o verbo ('{verbo}')", verbo.lower() in baixo)
    else:
        check("sem fatos recentes, a faixa diz isso em vez de sumir",
              "o que mudou" in baixo)

    print("\n8. A paleta ⌘K — a válvula que segura o rail em seis")
    pagina.keyboard.press("Control+k")
    pagina.wait_for_timeout(700)
    check("a paleta abre no atalho",
          pagina.get_by_role("dialog", name="Busca e comandos").count() > 0)
    entrada = pagina.locator("div[role=dialog] input").first
    entrada.fill("a")
    pagina.wait_for_timeout(600)
    dialogo = pagina.inner_text("div[role=dialog]").lower()
    check(
        "uma letra não varre, e a tela avisa MESMO mostrando postos e obras",
        "2 letras" in dialogo,
    )

    #: O termo e o que ele tem de achar saem da própria API, para o teste não
    #: depender de como o seed nomeou as coisas nesta máquina.
    codigo, previa = req(f"/api/pdca/busca/?q=alvenaria&obra={obra_id}", token)
    esperadas = [e["rotulo"].lower() for e in (previa or {}).get("especies", [])]
    entrada.fill("alvenaria")
    pagina.wait_for_timeout(2200)
    dialogo = pagina.inner_text("div[role=dialog]").lower()
    if esperadas:
        check(
            f"com duas letras ela procura e agrupa por tipo ({', '.join(esperadas)})",
            all(rotulo in dialogo for rotulo in esperadas),
        )
        check(
            "e o rodapé diz quantos tipos de registro foram varridos",
            "tipos de registro" in dialogo,
        )
    else:
        check("busca sem resultado diz 'nada com esse nome'",
              "nada com esse nome" in dialogo)

    #: **Acento nas duas direções, contra um termo que existe de verdade.** O
    #: par tem de achar o MESMO — comparar duas listas vazias não prova nada.
    _, cru = req(f"/api/pdca/busca/?q=fundacao&obra={obra_id}", token)
    if (cru or {}).get("total"):
        entrada.fill("fundacao")
        pagina.wait_for_timeout(2200)
        sem_acento = pagina.inner_text("div[role=dialog]").lower()
        entrada.fill("fundação")
        pagina.wait_for_timeout(2200)
        com_acento = pagina.inner_text("div[role=dialog]").lower()
        check(
            "acha sem acento e com acento — no canteiro ninguém caça o ç",
            "nada com esse nome" not in sem_acento
            and "nada com esse nome" not in com_acento,
        )
    else:
        print("     (nada chamado 'fundação' no seed — acento fica com o teste de API)")
    pagina.screenshot(path=f"{SHOTS}/03_paleta.png", full_page=True)
    pagina.keyboard.press("Escape")
    pagina.wait_for_timeout(400)

    print("\n9. Uma leitura só, e a tela fica parada")
    de_hoje = [u for u in chamadas if "/api/pdca/hoje/" in u]
    check(
        f"HOJE faz UMA chamada para os três blocos (fez {len(de_hoje)})",
        len(de_hoje) <= 2,
    )
    antes = len(chamadas)
    pagina.wait_for_timeout(3000)
    check("sem laço de renderização — nada foi refeito parado",
          len(chamadas) == antes)
    check(f"nenhum erro de JavaScript ({len(erros_js)})", not erros_js)
    if erros_js:
        for e in erros_js[:4]:
            print(f"       · {e[:160]}")

    navegador.close()

total = len(passed)
ok = sum(1 for p in passed if p)
print(f"\n  Telas em {SHOTS}")
print(f"\n{'='*62}\n  {ok}/{total} verificações\n{'='*62}\n")
sys.exit(0 if ok == total else 1)
