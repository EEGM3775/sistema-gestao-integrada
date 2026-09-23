"""PDCA.5 — o quadro da semana no NAVEGADOR, pelo gateway (8090).

Existe pela régua escrita em 15/09/2026, depois de a PDCA.4 sair com a suíte
verde, dois E2E de API verdes e três defeitos que o dono achou clicando
([README](README.md) §"Teste de API não substitui teste de navegador"): **tela
nova entrega com teste de navegador junto**, e ele mede as três coisas que só
existem ali — *o conteúdo aparece*, *o que se faz sobrevive ao F5*, e *com a
tela parada não pode haver requisição*.

O [pdca5_programacao_test.py](pdca5_programacao_test.py) prova a API inteira
(82 verificações). Este prova que existe caminho de dedo até ela, e cobre o que
nenhuma chamada de API alcança:

  1. o caminho de dedo: Planejamento → cartão da obra → **Programação da semana**;
  2. a semana **não aberta** não desenha um quadro vazio — ela se oferece para
     ser aberta, e diz o que abrir significa;
  3. **o cartão travado não é clicável**, e diz por quê. É a frase que define o
     instrumento (atividade com restrição aberta não entra na programação) e a
     única parte dela que não dá para provar por API: recusar só no envio faria
     o time descobrir a trava depois de a reunião ter acabado;
  4. **a tela é outra em cada estado** — em rascunho há de onde puxar e há como
     devolver; assumida, as duas coisas somem. Um só layout com botões
     desabilitados faria a pessoa descobrir o estado tentando;
  5. **o select de causa só aparece quando ela é exigida** — marcar "Saiu" não
     abre campo de explicação;
  6. o PPC e o ranking **aparecem** depois do encerramento, e sobrevivem ao F5;
  6b. a semana **errada tem volta**: reabrir pede a razão por escrito, o selo
      de correção aparece e o PPC recalcula sozinho — ele nunca foi gravado;
  5b. o cartão mostra **quanto foi prometido e quanto o campo apontou** — o
      compromisso é binário, a execução não é, e o número fica ao lado do
      julgamento sem nunca entrar no PPC;
  6d. o gráfico do PPC mostra a semana **inteira** partida em saiu/não saiu,
      com eixo 0–100 legível, legenda das duas partes e a tabela-gêmea;
  6c. o PPC é apresentado **sem meta escondida** (a faixa de cor por desempenho
      era uma meta cravada em código) e **sem tendência de um ponto só**;
  7. e a tela fica **parada** — sem laço de renderização.

Rodar (stack de pé, imagem `react` rebuildada):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/pdca5_quadro_browser_test.py

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
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_pdca5")
MARCA = "E2E PDCA.5 tela " + uuid.uuid4().hex[:6]

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


print(f"\n{'='*62}\nPDCA.5 — o quadro da semana no navegador\n{'='*62}")
os.makedirs(SHOTS, exist_ok=True)

try:
    demo = login("demo", "demo123")
except Exception as e:
    fatal(f"login falhou ({e}). Stack de pé? Seeds rodados?")

# --- O cenário, montado por API (o que este teste prova é a TELA) -----------
print("\n0. Cenário montado por API")
status, obra = req("POST", "/api/obras/", demo, {
    "nome_obra": MARCA, "endereco": "Rua do Quadro, s/n", "status_obra": "planejamento",
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

for codigo, nome in (("1", "Alvenaria do 4º pavimento"),
                     ("2", "Contrapiso do 3º pavimento")):
    status, a = req("POST", "/api/pdca/atividades/", demo, {
        "cronograma": crono_id, "codigo": codigo, "nome": nome,
        "duracao_dias": 5, "peso_informado": "50",
    })
    if status not in (200, 201):
        fatal(f"atividade {codigo} falhou ({status}: {a})")

status, _ = req("POST", f"/api/pdca/cronogramas/{crono_id}/publicar/", demo)
if status != 200:
    fatal(f"publicar falhou ({status})")
check("obra, calendário e plano vigente com duas folhas nesta semana", True)

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

    print("\n2. O caminho de dedo até o quadro (a lição da PRA.5c)")
    # **O Last Planner mora DENTRO do PDCA**, como a medição: não há item próprio
    # na barra lateral, e o caminho é Planejamento → a obra → Programação.
    pagina.wait_for_load_state("networkidle")
    item_menu = pagina.locator("a[href='/app/pdca']")
    try:
        item_menu.first.wait_for(state="attached", timeout=10000)
    except Exception:
        pass
    check("o Planejamento está na barra lateral", item_menu.count() > 0)
    check("e NÃO há item separado de programação (o LPS não é um módulo à parte)",
          pagina.locator("a[href='/app/pdca/programacao']").count() == 0)
    if item_menu.count() > 0:
        item_menu.first.click()
        pagina.wait_for_url("**/app/pdca", timeout=15000)
    else:
        pagina.goto(f"{GW}/app/pdca")
    pagina.wait_for_load_state("networkidle")

    botao = pagina.get_by_role("button", name="Programação da semana")
    try:
        botao.first.wait_for(state="visible", timeout=10000)
    except Exception:
        pass
    # O botão existe em **todo** cartão de obra — é isso que se prova aqui.
    # Clicar no primeiro abriria o quadro de *outra* obra (o tenant de
    # demonstração tem várias), então a navegação segue para a obra deste teste.
    check("o cartão da obra oferece 'Programação da semana'", botao.count() > 0)
    pagina.goto(f"{GW}/app/pdca/obra/{obra_id}/programacao")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1200)
    check("o quadro da obra abre", f"/obra/{obra_id}/programacao" in pagina.url)

    print("\n3. A semana não aberta se OFERECE — não desenha um quadro vazio")
    corpo = pagina.inner_text("body").lower()
    check("a tela diz que a semana ainda não foi aberta",
          "ainda não foi aberta" in corpo)
    check("e explica o que abrir significa, antes de alguém clicar",
          "nada entra sozinho" in corpo)
    check("o nome da obra está na tela (não é 'Obra 123')", MARCA.lower() in corpo)
    pagina.screenshot(path=f"{SHOTS}/01_semana_fechada.png", full_page=True)

    abrir = pagina.get_by_role("button", name="Abrir a semana")
    check("e oferece 'Abrir a semana'", abrir.count() > 0)
    abrir.first.click()
    pagina.wait_for_timeout(2500)
    pagina.wait_for_load_state("networkidle")
    corpo = pagina.inner_text("body").lower()
    check("o quadro nasce em RASCUNHO", "rascunho" in corpo)
    #: O id da semana que a TELA abriu — o cenário do §5b precisa dele para pôr
    #: o prometido e o apontado por API.
    status, abertas = req(
        "GET", f"/api/pdca/programacoes/?obra={obra_id}&semana_inicio={segunda.isoformat()}",
        demo,
    )
    prog_id = ((abertas or {}).get("results") or [{}])[0].get("programacao_id")
    if prog_id is None:
        fatal("não achei a programação que a tela abriu")
    check("com a área de onde se puxa ao lado",
          "o plano diz que é desta semana" in corpo)
    check("e o quadro da semana, vazio, dizendo o que fazer",
          "quadro vazio" in corpo)

    print("\n4. O cartão travado NÃO é clicável — a regra que define o LPS")
    # É o que nenhuma chamada de API alcança: a API recusa no envio; a tela tem
    # de recusar **antes**, ou o time descobre a trava depois da reunião.
    painel = pagina.get_by_role("button", name="Restrição")
    check("o painel de restrições oferece registrar uma", painel.count() > 0)
    painel.first.click()
    pagina.wait_for_timeout(700)
    corpo = pagina.inner_text("body").lower()
    check("o formulário diz a consequência antes de gravar",
          "não pode ser puxada para o quadro" in corpo)

    selects = pagina.locator("select")
    selects.nth(0).select_option(index=2)          # a 2ª atividade do plano
    selects.nth(1).select_option("material")
    pagina.locator("textarea").first.fill(
        "Bloco cerâmico 14×19×39 não entregue — " + MARCA
    )
    pagina.get_by_role("button", name="Registrar").first.click()
    pagina.wait_for_timeout(2500)
    pagina.wait_for_load_state("networkidle")

    corpo = pagina.inner_text("body").lower()
    check("a restrição aparece no painel, com o tipo",
          "bloco cerâmico" in corpo and "material" in corpo)
    check("e o painel mostra o que ela trava",
          "contrapiso do 3º pavimento" in corpo)

    travado = pagina.locator("button", has_text="Contrapiso do 3º pavimento").first
    check("o cartão da atividade travada existe na área de rascunho",
          travado.count() > 0)
    check("e ele está DESABILITADO — não dá para puxá-lo", travado.is_disabled())
    check("dizendo quantas travas pesam sobre ele", "1 trava(s)" in pagina.inner_text("body"))
    check("com a explicação no title, para quem passar o mouse",
          "remova a trava" in (travado.get_attribute("title") or "").lower())
    pagina.screenshot(path=f"{SHOTS}/02_cartao_travado.png", full_page=True)

    print("\n4b. E a trava sobrevive ao F5 — ela é do servidor, não da tela")
    pagina.reload()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1800)
    travado = pagina.locator("button", has_text="Contrapiso do 3º pavimento").first
    check("depois do F5 o cartão continua travado", travado.is_disabled())

    print("\n5. Puxar o que está livre, e devolver")
    livre = pagina.locator("button", has_text="Alvenaria do 4º pavimento").first
    check("a atividade sem trava está clicável", not livre.is_disabled())
    livre.click()
    pagina.wait_for_timeout(2200)
    pagina.wait_for_load_state("networkidle")
    check("o cartão entrou no quadro (e o botão 'Devolver' apareceu)",
          pagina.get_by_role("button", name="Devolver").count() > 0)

    pagina.reload()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1800)
    check("e sobrevive ao F5 — o quadro é do servidor, não do navegador",
          pagina.get_by_role("button", name="Devolver").count() > 0)

    print("\n6. Destravar pela tela, e a atividade libera na hora")
    pagina.get_by_role("button", name="Remover").first.click()
    pagina.wait_for_timeout(700)
    corpo = pagina.inner_text("body").lower()
    check("o diálogo pergunta COMO ela foi removida",
          "como ela foi removida" in corpo)
    # O botão nasce desabilitado: remover sem explicação não é caminho oferecido.
    confirmar = pagina.get_by_role("button", name="Remover").last
    check("e o botão de confirmar nasce DESABILITADO, sem a nota",
          confirmar.is_disabled())
    pagina.locator("textarea").first.fill(
        "Entrega recebida na 3ª feira, nota 4412 — 4.000 blocos no canteiro."
    )
    pagina.wait_for_timeout(300)
    pagina.get_by_role("button", name="Remover").last.click()
    pagina.wait_for_timeout(2500)
    pagina.wait_for_load_state("networkidle")

    liberado = pagina.locator("button", has_text="Contrapiso do 3º pavimento").first
    check("a atividade LIBERA na hora, sem recarregar", not liberado.is_disabled())
    liberado.click()
    pagina.wait_for_timeout(2200)
    pagina.wait_for_load_state("networkidle")
    check("e entra no quadro — são dois compromissos agora",
          pagina.get_by_role("button", name="Devolver").count() == 2)
    pagina.screenshot(path=f"{SHOTS}/03_quadro_montado.png", full_page=True)

    print("\n5b. O compromisso é binário; a execução não é")
    # A obra que assumiu 20 pontos e entregou 12 **fez 12**, e um cartão que só
    # diz "não saiu" faz o sistema parecer dizer que ela não fez nada. O número
    # vem do apontamento da PDCA.2 — o campo já o lançou no dia —, e existe para
    # se julgar **com a prova na frente** em vez de julgar de memória.
    #
    # O quadro é montado por clique (sem percentual), então o cenário põe o
    # prometido e o apontado por API: o que se prova aqui é que a TELA os mostra.
    status, itens_api = req(
        "GET", f"/api/pdca/itens-programacao/?programacao={prog_id}", demo,
    )
    cartoes_api = (itens_api or {}).get("results") or []
    alvo = next(
        (c for c in cartoes_api if "Contrapiso" in (c.get("atividade_nome") or "")),
        None,
    )
    if alvo is None:
        fatal("não achei o cartão do contrapiso para exercitar o parcial")
    req("PATCH", f"/api/pdca/itens-programacao/{alvo['item_programacao_id']}/", demo,
        {"percentual_previsto": "20"})
    req("POST", "/api/pdca/apontamentos/", demo, {
        "atividade": alvo["atividade"],
        "data": (segunda + timedelta(days=2)).isoformat(),
        "percentual": "12",
    })
    #: E o **outro** cartão promete sem o campo apontar nada — é o caso em que a
    #: distinção entre "não apontou" e "apontou zero" decide se o sistema acusa
    #: a equipe de uma parada que talvez não tenha havido.
    outro = next(
        (c for c in cartoes_api
         if c["item_programacao_id"] != alvo["item_programacao_id"]), None,
    )
    if outro is not None:
        req("PATCH", f"/api/pdca/itens-programacao/{outro['item_programacao_id']}/",
            demo, {"percentual_previsto": "15"})
    pagina.reload()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1800)
    corpo = pagina.inner_text("body")
    check("o cartão mostra quanto a equipe PROMETEU avançar",
          "prometeu" in corpo.lower() and "20" in corpo)
    check("e quanto o campo APONTOU de verdade na semana",
          "campo apontou" in corpo.lower() and "12" in corpo)
    check("o cartão que prometeu e não teve apontamento DIZ isso, em vez de "
          "fabricar um zero que acusaria a equipe",
          "sem apontamento do campo" in corpo.lower())
    pagina.screenshot(path=f"{SHOTS}/03b_parcial.png", full_page=True)

    print("\n7. Assumir a semana — e a tela vira OUTRA")
    assumir = pagina.get_by_role("button", name="Assumir a semana")
    check("o rascunho oferece assumir", assumir.count() > 0)
    check("e avisa que depois disso a lista não recebe cartão novo",
          "não recebe cartão novo" in pagina.inner_text("body").lower())
    assumir.first.click()
    pagina.wait_for_timeout(2800)
    pagina.wait_for_load_state("networkidle")

    corpo = pagina.inner_text("body").lower()
    check("a semana passa a COMPROMETIDA", "comprometida" in corpo)
    check("a área de onde se puxava SOME — ela não teria mais função",
          "o plano diz que é desta semana" not in corpo)
    check("e o 'Devolver' some junto: compromisso assumido se julga, não se apaga",
          pagina.get_by_role("button", name="Devolver").count() == 0)
    check("o PPC aparece como 'sem apuração', nunca como 0%",
          "sem apuração" in corpo and "ppc 0" not in corpo)
    check("dizendo quantos faltam julgar", "2 por julgar" in corpo)
    pagina.screenshot(path=f"{SHOTS}/04_comprometida.png", full_page=True)

    print("\n8. Julgar — e a causa só aparece quando é exigida")
    pagina.get_by_role("button", name="Julgar a semana").first.click()
    pagina.wait_for_timeout(900)
    check("o quadro entra em modo julgamento",
          "julgando" in pagina.inner_text("body").lower())
    check("cada cartão recebe as duas respostas",
          pagina.get_by_role("button", name="Saiu", exact=True).count() == 2
          and pagina.get_by_role("button", name="Não saiu").count() == 2)
    check("e NENHUMA vem pré-selecionada — um padrão em 'saiu' faria o quadro "
          "inteiro passar por cumprido em quem só clicou em encerrar",
          pagina.locator("select").count() == 0)

    pagina.get_by_role("button", name="Saiu", exact=True).first.click()
    pagina.wait_for_timeout(400)
    check("marcar 'Saiu' NÃO abre campo de explicação",
          pagina.locator("select").count() == 0)

    pagina.get_by_role("button", name="Não saiu").last.click()
    pagina.wait_for_timeout(500)
    check("marcar 'Não saiu' abre o select de causa", pagina.locator("select").count() == 1)
    check("e o campo do detalhe, que é de onde sai a ação",
          pagina.locator("input[placeholder='Qual material? Que projeto?']").count() == 1)
    opcoes = pagina.locator("select option").all_inner_texts()
    check("o catálogo de fábrica está na lista, sem ninguém cadastrar nada",
          any("Material não chegou" in o for o in opcoes))

    pagina.locator("select").first.select_option(label="Material não chegou")
    pagina.locator("input[placeholder='Qual material? Que projeto?']").fill(
        "Faltou argamassa colante AC-III"
    )
    pagina.wait_for_timeout(400)
    pagina.screenshot(path=f"{SHOTS}/05_julgando.png", full_page=True)

    pagina.get_by_role("button", name="Encerrar a semana").first.click()
    pagina.wait_for_timeout(3500)
    pagina.wait_for_load_state("networkidle")

    print("\n9. O PPC e o ranking APARECEM — e não some nada")
    corpo = pagina.inner_text("body").lower()
    check("a semana encerra e a tela não some", "encerrada" in corpo)
    check("o PPC da semana aparece: 1 de 2 = 50%",
          "50.0%" in pagina.inner_text("body") or "50%" in pagina.inner_text("body"))
    check("com o denominador ao lado do índice, não o índice sozinho",
          "1 de 2 saíram" in corpo)
    #: "última semana" só existe a partir da **segunda** encerrada — com uma
    #: só, o painel chama o número do que ele é e diz quando a tendência começa
    #: (ver §10d). Afirmar o rótulo antigo aqui era exigir da tela o que ela
    #: deixou de fazer de propósito.
    check("o painel do PPC mostra o índice da semana apurada",
          "primeira semana apurada" in corpo)
    check("e o ranking de causas nomeia o que segurou a obra",
          "material não chegou" in corpo)
    check("com o corte por categoria, que decide com quem é a conversa",
          "de onde vem a falha" in corpo)
    pagina.screenshot(path=f"{SHOTS}/06_ppc.png", full_page=True)

    print("\n10. F5 — e o que se julgou continua lá")
    pagina.reload()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(2000)
    corpo = pagina.inner_text("body").lower()
    check("o PPC sobrevive ao F5", "1 de 2 saíram" in corpo)
    check("a causa do compromisso que não saiu continua no cartão",
          "não saiu — material não chegou" in corpo)
    check("com o detalhe que a reunião escreveu", "argamassa colante" in corpo)

    print("\n10b. A semana errada tem volta — pela tela")
    # A lição da PRA.5c: porta sem caminho de dedo é porta que não existe. O
    # `reabrir/` só serve se quem errou na reunião o alcançar sem chamar o
    # suporte.
    reabrir = pagina.get_by_role("button", name="Reabrir para rejulgar")
    check("a semana encerrada oferece reabrir", reabrir.count() > 0)
    reabrir.first.click()
    pagina.wait_for_timeout(800)
    corpo = pagina.inner_text("body").lower()
    check("o diálogo diz o que vai acontecer ANTES de confirmar",
          "o julgamento" in corpo and "fica" in corpo)
    check("e avisa que a semana sai da série enquanto estiver em revisão",
          "sai da série" in corpo or "sai da serie" in corpo)
    confirmar = pagina.get_by_role("button", name="Reabrir", exact=True).last
    check("o botão de confirmar nasce DESABILITADO, sem a razão escrita",
          confirmar.is_disabled())

    pagina.locator("textarea").last.fill(
        "A causa do contrapiso foi lançada errada na reunião."
    )
    pagina.wait_for_timeout(300)
    pagina.get_by_role("button", name="Reabrir", exact=True).last.click()
    pagina.wait_for_timeout(3200)
    pagina.wait_for_load_state("networkidle")

    corpo = pagina.inner_text("body").lower()
    check("a semana volta a COMPROMETIDA", "comprometida" in corpo)
    check("e o selo de correção aparece com a razão ao lado",
          "reaberta 1" in corpo and "contrapiso" in corpo)
    check("o PPC volta a 'sem apuração' — em revisão não é conclusão de nada",
          "sem apuração" in corpo)
    pagina.screenshot(path=f"{SHOTS}/07_reaberta.png", full_page=True)

    print("\n10c. Corrigir e encerrar de novo — o PPC recalcula sozinho")
    pagina.get_by_role("button", name="Julgar a semana").first.click()
    pagina.wait_for_timeout(900)
    #: O cartão que não saiu é o segundo; marcá-lo como "Saiu" muda o índice.
    pagina.get_by_role("button", name="Saiu", exact=True).last.click()
    pagina.wait_for_timeout(500)
    pagina.get_by_role("button", name="Encerrar a semana").first.click()
    pagina.wait_for_timeout(3500)
    pagina.wait_for_load_state("networkidle")
    corpo = pagina.inner_text("body")
    check("o PPC recalculou: 2 de 2 saíram", "2 de 2 saíram" in corpo)
    check("e a marca de que a semana foi corrigida CONTINUA lá",
          "reaberta 1" in corpo.lower())

    print("\n10d. O PPC apresentado — sem meta escondida, sem tendência de um ponto")
    corpo = pagina.inner_text("body").lower()
    check("com UMA semana encerrada a tela não desenha tendência",
          "tendência aparece na segunda semana" in corpo)
    check("e chama o número do que ele é — a primeira semana apurada",
          "primeira semana apurada" in corpo)
    check("a média de um ponto NÃO é exibida como segunda leitura",
          "média de 1 semana" not in corpo)
    # **A meta escondida saiu.** A primeira escrita pintava a barra por faixa
    # (verde ≥80, amarelo ≥60, vermelho abaixo) — uma meta cravada em código,
    # invisível e sem legenda, contra a decisão da §5.5j do `planos.py`.
    barras = pagina.locator("div[title*='%']")
    if barras.count() > 0:
        estilo = (barras.first.get_attribute("style") or "").lower()
        check("nenhuma barra é pintada de vermelho por faixa de desempenho",
              "--danger" not in estilo)

    print("\n10e. Com a segunda semana, o gráfico aparece — e mostra as duas partes")
    # A coluna é a semana **inteira** (o que a equipe assumiu), partida no que
    # saiu e no que não saiu. É isso que dá referência: uma barra que desenha só
    # a altura do índice não diz contra o quê, e 50% vira um bloco solto.
    semana2 = (segunda + timedelta(days=7)).isoformat()
    status, prog2 = req("POST", "/api/pdca/programacoes/abrir/", demo,
                        {"obra": obra_id, "semana": semana2})
    pid2 = (prog2 or {}).get("programacao_id")
    status, item_a = req("POST", "/api/pdca/itens-programacao/", demo,
                         {"programacao": pid2, "atividade": alvo["atividade"], "ordem": 0})
    req("POST", f"/api/pdca/programacoes/{pid2}/comprometer/", demo)
    req("POST", f"/api/pdca/programacoes/{pid2}/julgar/", demo, {
        "julgamentos": [
            {"item": item_a["item_programacao_id"], "cumprido": True},
        ],
    })
    status, _ = req("POST", f"/api/pdca/programacoes/{pid2}/encerrar/", demo)
    check("a segunda semana encerra", status == 200)

    pagina.goto(f"{GW}/app/pdca/obra/{obra_id}/programacao?semana={semana2}")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(2600)

    graficos = pagina.locator("svg[role='img']")
    check("agora o gráfico do PPC é desenhado", graficos.count() > 0)
    corpo = pagina.inner_text("body").lower()
    check("com a legenda das DUAS partes — identidade nunca depende só da cor",
          "saiu" in corpo and "não saiu" in corpo)
    check("e a marca da semana reaberta explicada na legenda",
          "semana reaberta" in corpo)
    check("o eixo traz a régua de 0 a 100, para o valor ser LIDO e não estimado",
          "100" in pagina.inner_text("body"))
    check("sem faixa de cor por desempenho — a meta é do dono, não do sistema",
          "não é régua do sistema" in corpo or "acordo entre" in corpo)
    pagina.screenshot(path=f"{SHOTS}/08_ppc_serie.png", full_page=True)

    print("\n10f. A tabela-gêmea — obrigatória, não enfeite")
    # O acento da Malha fica em 2,16:1 contra a superfície clara, abaixo de 3:1:
    # a régua de dataviz diz que esse aviso só se resolve com rótulo visível ou
    # tabela, e que ele **não é dispensável**.
    ver_tabela = pagina.get_by_role("button", name="Ver tabela")
    check("o painel oferece ver os mesmos números em tabela", ver_tabela.count() > 0)
    ver_tabela.first.click()
    pagina.wait_for_timeout(700)
    check("e a tabela traz semana, PPC, saiu e assumidos",
          pagina.locator("table").count() > 0)
    corpo = pagina.inner_text("body").lower()
    check("com o denominador em coluna própria — nenhum valor fica só no gráfico",
          "assumidos" in corpo)

    print("\n11. Com a tela parada não pode haver requisição")
    parado = len(requisicoes)
    pagina.wait_for_timeout(4000)
    check("nenhuma requisição com a tela em repouso (sem laço de renderização)",
          len(requisicoes) - parado == 0)

    check("nenhum erro de JavaScript na página", not erros_js)
    if erros_js:
        print("     erros:", erros_js[:3])

    navegador.close()

# --- Faxina -----------------------------------------------------------------
print("\n12. Faxina")
status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
check("a obra do teste sai (vai para a lixeira, que é o desenho)",
      status in (200, 204))
print(
    "\n     Como o irmão de API, este teste deixa a semana encerrada e os\n"
    "     compromissos julgados — documento com decisão registrada não se\n"
    "     apaga. Para devolver o ambiente ao estado anterior:\n"
    "       docker exec sgi-erp python manage.py limpar_residuo_e2e --confirmar"
)

ok = sum(1 for p in passed if p)
print(f"\n{'='*62}\nPDCA.5 (tela): {ok}/{len(passed)} verificações\n{'='*62}")
sys.exit(0 if ok == len(passed) else 1)
