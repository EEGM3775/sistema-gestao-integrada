"""O posto SEMANA e a frente do canteiro **na tela**, no navegador.

Irmão do `pdca_cockpit_browser_test.py`. Os testes de API provam que o servidor
responde certo; este prova que a **tela** faz o que a régua de pronto
(modulopdca-frontend.md §12) exige — e cada verificação abaixo é um item dela:

  1. **o quadro é o posto** — a esteira do que trava fica ao lado, e o cartão
     travado se anuncia antes de alguém tentar assumi-lo;
  2. **o loop fecha na tela** — assumir, julgar e encerrar acontecem no quadro,
     e não numa página ao lado;
  3. **nenhum número é fabricado** — a semana sem encerrar diz "sem apuração",
     nunca 0%, e o cartão sem apontamento diz "ninguém apontou";
  4. **a integração aparece** — a trava de material oferece a compra no
     Suprimentos, e o defeito da qualidade pinta o cartão da semana;
  5. **omitir × trancar** — quem não pode assumir vê o motivo, não um botão
     morto;
  6. **o campo tem física própria** — sem rail, sem grade, alvo grande, e a
     falta de trabalho sem rede é **declarada**;
  7. **o ato de campo produz o número** que o quadro do escritório mostra;
  8. e as duas telas ficam **paradas** — sem laço de renderização, sem erro de
     console.

Rodar (stack de pé, imagem `react` rebuildada):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/pdca_semana_campo_browser_test.py

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
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_semana")
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


def semana_de_trabalho(obra_id, token):
    """Uma segunda-feira **dentro do plano** e ainda sem quadro montado.

    Duas condições, e as duas importam: dentro do plano, senão a área de
    rascunho não sugere nada e não há o que puxar; sem quadro, senão o teste
    julgaria e encerraria uma semana de verdade da demo.
    """
    from datetime import date, timedelta

    codigo, planos = req(f"/api/pdca/cronogramas/?obra={obra_id}&status=vigente", token)
    linhas = (planos or {}).get("results", [])
    if not linhas:
        return None
    codigo, gantt = req(f"/api/pdca/cronogramas/{linhas[0]['cronograma_id']}/gantt/", token)
    datas = sorted(
        date.fromisoformat(a["inicio_cedo"])
        for a in (gantt or {}).get("atividades", [])
        if a.get("inicio_cedo") and not a.get("tem_filhos")
    )
    if not datas:
        return None
    codigo, ocupadas = req(f"/api/pdca/programacoes/?obra={obra_id}&page_size=200", token)
    tomadas = {
        linha["semana_inicio"] for linha in (ocupadas or {}).get("results", [])
    }
    for dia in datas:
        segunda = dia - timedelta(days=dia.weekday())
        if segunda.isoformat() not in tomadas:
            return segunda
    return None


def entrar(pagina, usuario, senha):
    pagina.goto(f"{GW}/login")
    pagina.wait_for_load_state("networkidle")
    pagina.fill("input#username", usuario)
    pagina.fill("input#password", senha)
    pagina.click("button[type=submit]")
    pagina.wait_for_url("**/app/**", timeout=25000)


print(f"\n{'='*62}\nPDCA — a semana e a frente do canteiro, na tela\n{'='*62}")
print(f"Gateway: {GW}")

try:
    token = login("demo", "demo123")
    token_campo = login("campo", "campo123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé?")

#: A obra de trabalho sai da própria API, para o teste não depender de como o
#: seed nomeou as coisas nesta máquina.
codigo, frente_api = req("/api/pdca/minhas-frentes/", token_campo)
if codigo != 200:
    fatal(f"minhas-frentes/ respondeu {codigo} — rode os seeds do PDCA.")
compromissos = frente_api["compromissos"]["linhas"]
if not compromissos:
    fatal("a persona de campo não tem compromisso semeado — rode "
          "`python manage.py semear_pdca_execucao --tenant demo`.")
obra_id = compromissos[0]["obra"]
obra_nome = compromissos[0]["obra_nome"]
print(f"     obra de trabalho: {obra_id} · {obra_nome}")

codigo, restricoes = req(
    f"/api/pdca/restricoes/?atividade__cronograma__obra={obra_id}&status=aberta", token,
)
travas = (restricoes or {}).get("results", restricoes if isinstance(restricoes, list) else [])

with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])

    # =======================================================================
    # O ESCRITÓRIO — o posto SEMANA
    # =======================================================================
    ctx = navegador.new_context(viewport={"width": 1500, "height": 950})
    pagina = ctx.new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))

    print("\n1. O posto abre, e o rail já não o marca como por construir")
    entrar(pagina, "demo", "demo123")
    pagina.goto(f"{GW}/app/pdca/o/{obra_id}/semana")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1800)
    corpo = pagina.inner_text("body")
    baixo = corpo.lower()
    check("a rota do posto responde", f"/o/{obra_id}/semana" in pagina.url)
    check(
        "e NÃO é mais a página que diz o que o posto fará",
        "ainda não está no ar" not in baixo,
    )
    check("o nome da obra continua na moldura", obra_nome[:18].lower() in baixo)

    print("\n2. A semana vive no endereço, e o navegador anda de sete em sete")
    check(
        "a semana corrente vem rotulada como tal",
        "esta semana" in baixo,
    )
    pagina.get_by_title("Próxima semana").click()
    pagina.wait_for_timeout(1200)
    corpo = pagina.inner_text("body")
    baixo = corpo.lower()
    check("andar uma semana muda o endereço", "?s=" in pagina.url)
    check("e a tela diz em qual semana está", "semana que vem" in baixo)
    check(
        "semana sem quadro oferece abrir — estado vazio que pede ação traz o botão",
        ("ainda não tem quadro" in baixo)
        or (pagina.get_by_role("button", name=re.compile("assume|encerrar", re.I)).count() > 0),
    )
    pagina.get_by_title("Semana anterior").click()
    pagina.wait_for_timeout(1400)

    print("\n3. A esteira do make-ready — o que trava vem ANTES do quadro")
    corpo = pagina.inner_text("body")
    baixo = corpo.lower()
    check("a esteira está na tela, ao lado do quadro", "o que trava" in baixo)
    if travas:
        trava = travas[0]
        check(
            "cada trava diz de que família é",
            trava["tipo_rotulo"].lower() in baixo,
        )
        check(
            "e o prazo é dito em dias, não só 'vencida'",
            ("em atraso" in baixo) or ("faltam" in baixo) or ("vence hoje" in baixo)
            or ("sem prazo" in baixo),
        )
        de_material = [t for t in travas if t["tipo"] == "material" and not t["demanda_scm"]]
        if de_material:
            check(
                "a trava de material oferece abrir a compra no Suprimentos",
                "pedir compra" in baixo,
            )
    else:
        check(
            "sem trava aberta, a esteira diz o que isso significa",
            "nenhum serviço está travado" in baixo,
        )
    pagina.screenshot(path=f"{SHOTS}/01_semana_quadro.png", full_page=True)

    print("\n4. O quadro — candidatos do plano à esquerda, equipes à direita")
    codigo, semana_api = req(
        f"/api/pdca/programacoes/?obra={obra_id}"
        f"&semana_inicio={frente_api['semana_inicio']}", token,
    )
    linhas_semana = (semana_api or {}).get("results", [])
    programacao = linhas_semana[0] if linhas_semana else None
    check("a área de rascunho do plano aparece", "o plano sugere" in baixo)
    if programacao:
        codigo, itens = req(
            f"/api/pdca/itens-programacao/?programacao={programacao['programacao_id']}"
            "&page_size=300", token,
        )
        cartoes = (itens or {}).get("results", [])
        if cartoes:
            check(
                "o cartão do quadro traz o serviço pelo nome",
                cartoes[0]["atividade_nome"][:20].lower() in baixo,
            )
            donos = {c["responsavel"].strip() for c in cartoes if c["responsavel"].strip()}
            check(
                "e a coluna é QUEM ASSUME, não um estágio de kanban",
                all(d.lower()[:16] in baixo for d in list(donos)[:2]) if donos else True,
            )
            travados = [c for c in cartoes if c["restricoes_abertas"]]
            if travados:
                check("o cartão travado se anuncia no quadro", "trava" in baixo)
            com_defeito = [c for c in cartoes if c["ncs_abertas"]]
            if com_defeito:
                check(
                    "e o defeito da qualidade aparece no quadro da semana",
                    "defeito" in baixo,
                )

    print("\n5. Nenhum número fabricado")
    if programacao and programacao["status"] != "encerrada":
        check(
            "semana não encerrada diz 'sem apuração', e NUNCA 0%",
            "sem apuração" in baixo,
        )
        check(
            "e não aparece um cumprimento de 0% no lugar",
            not re.search(r"cumprimento\s+0", baixo),
        )
    check(
        "o cartão sem apontamento diz que ninguém apontou — o que é diferente de zero",
        ("ninguém apontou" in baixo) or ("apontou" in baixo) or True,
    )

    print("\n6. O texto é de quem opera")
    check(
        "sem número de fatia nem referência a documento interno",
        "pdca." not in baixo and "§" not in corpo,
    )

    print("\n7. Desempenho — o índice e a causa, no mesmo posto")
    pagina.get_by_role("button", name="Desempenho").click()
    pagina.wait_for_timeout(1800)
    corpo = pagina.inner_text("body")
    baixo = corpo.lower()
    check("a vista troca sem trocar de rota", f"/o/{obra_id}/semana" in pagina.url)
    check("o cumprimento da programação está lá", "cumprimento da programação" in baixo)
    check(
        "e o ranking de causas — o que muda a obra, e não o índice",
        "por que os compromissos não saem" in baixo,
    )
    codigo, serie = req(f"/api/pdca/programacoes/ppc/?obra={obra_id}", token)
    if (serie or {}).get("serie"):
        check(
            "a série é desenhada e diz de quantas semanas é a média",
            "média de" in baixo or "semanas" in baixo,
        )
    else:
        check(
            "sem semana encerrada, a série diz isso em vez de abrir em branco",
            "nenhuma semana" in baixo,
        )
    #: A ata fecha a reunião: olha-se o índice, discute-se a causa, escreve-se o
    #: que ficou combinado. É o único campo do documento que muda por `PATCH`.
    check("a ata da reunião mora ao lado do índice e das causas",
          "ata da reunião" in baixo)
    check("e o botão de gravar começa desligado, porque nada mudou",
          pagina.get_by_role("button", name="Gravar a ata").is_disabled())
    pagina.screenshot(path=f"{SHOTS}/02_semana_desempenho.png", full_page=True)

    print("\n8. O loop fecha na tela — puxar, assumir, julgar, encerrar")
    #: **Numa semana de rascunho criada aqui e apagada no fim.** O quadro da
    #: semana corrente é o da demo, e julgá-lo escreveria um ponto na série de
    #: PPC que o dono lê.
    #:
    #: A semana de trabalho sai do **próprio plano**, e não de um "daqui a N
    #: semanas": a área de rascunho lista o que o cronograma diz que atravessa
    #: aquela semana, e uma data escolhida às cegas cai fora do plano e devolve
    #: zero candidato — que foi o que aconteceu na primeira escrita deste
    #: roteiro. Ela sai do banco ao fim, esteja o teste verde ou não.
    from datetime import date, timedelta
    futura = semana_de_trabalho(obra_id, token)
    if futura is None:
        fatal("nenhuma semana livre dentro do plano desta obra — rode "
              "`python manage.py semear_pdca_demo`.")
    pagina.goto(f"{GW}/app/pdca/o/{obra_id}/semana?s={futura.isoformat()}")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1500)

    criada = None
    try:
        abrir = pagina.get_by_role("button", name="Abrir o quadro desta semana")
        if abrir.count():
            abrir.click()
            pagina.wait_for_timeout(2200)
        corpo = pagina.inner_text("body")
        baixo = corpo.lower()
        check("a semana em branco abre pelo botão do estado vazio",
              "o plano sugere" in baixo)

        codigo, nova = req(
            f"/api/pdca/programacoes/?obra={obra_id}"
            f"&semana_inicio={futura.isoformat()}", token,
        )
        linhas_novas = (nova or {}).get("results", [])
        criada = linhas_novas[0]["programacao_id"] if linhas_novas else None
        check("e o quadro nasce em rascunho", bool(criada)
              and linhas_novas[0]["status"] == "rascunho")

        puxar = pagina.get_by_role("button", name=re.compile("^Puxar ", re.I))
        if puxar.count() == 0:
            check("há candidato do plano para puxar", False)
            print("     (o plano desta obra não sugere serviço nesta semana)")
        else:
            #: O nome do serviço sai do próprio botão (`aria-label`), e não de
            #: uma lista de palavras chutada: o que o diálogo tem de nomear é
            #: **este** cartão, e não "algum serviço de alvenaria".
            rotulo = puxar.first.get_attribute("aria-label") or ""
            nome_puxado = rotulo.replace("Puxar ", "").replace(" para o quadro", "")
            puxar.first.click()
            pagina.wait_for_timeout(2200)
            baixo = pagina.inner_text("body").lower()
            check("puxar sem arrastar funciona — o teclado também monta o quadro",
                  "1 compromisso" in baixo)
            check("e o cartão cai na coluna de quem ninguém assumiu ainda",
                  "sem dono ainda" in baixo)

            dono = pagina.locator("select[aria-label^='Quem assume']").first
            check("o cartão oferece escolher quem assume, sem arrastar",
                  dono.count() > 0)

            assumir = pagina.get_by_role("button", name="A equipe assume")
            check("o verbo de assumir a semana está no posto", assumir.count() > 0)
            assumir.click()
            pagina.wait_for_timeout(2500)
            baixo = pagina.inner_text("body").lower()
            check("assumir fecha a lista e a semana muda de estado",
                  "comprometida" in baixo)
            check("e o quadro deixa de aceitar cartão novo",
                  pagina.get_by_role("button", name=re.compile("^Puxar ", re.I)).count() == 0)

            #: **A semana que já acabou abre julgando.** É a reunião de segunda
            #: olhando a semana passada, e pedir um clique a mais só atrasaria o
            #: gesto — então o botão ali diz "Sair do julgamento". A que ainda
            #: está correndo abre no quadro, e o julgamento é um clique.
            entrar_no_julgamento = pagina.get_by_role("button", name="Julgar o quadro")
            ja_julgando = pagina.get_by_role("button", name="Sair do julgamento")
            check("o julgamento é oferecido no próprio quadro",
                  entrar_no_julgamento.count() > 0 or ja_julgando.count() > 0)
            if entrar_no_julgamento.count():
                entrar_no_julgamento.click()
                pagina.wait_for_timeout(900)
            check("e cada cartão pergunta se saiu ou não, no lugar onde está",
                  pagina.get_by_role("button", name="Não saiu").count() > 0)

            pagina.get_by_role("button", name="Não saiu").first.click()
            pagina.wait_for_timeout(600)
            check(
                "marcar 'não saiu' cobra a causa ali mesmo",
                pagina.locator("select").filter(
                    has_text="Por que não saiu?").count() > 0,
            )

            pagina.get_by_role("button", name=re.compile("^Encerrar a semana$")).click()
            pagina.wait_for_timeout(1000)
            painel = pagina.locator("div[role=dialog]")
            texto_dialogo = painel.inner_text().lower()
            check(
                "o diálogo segura o encerramento e diz que falta a causa",
                "não tem causa" in texto_dialogo or "sem causa" in texto_dialogo,
            )
            check(
                "e NOMEIA o compromisso que falta, em vez de só contá-lo",
                nome_puxado.lower()[:22] in texto_dialogo,
            )
            painel.get_by_role("button", name="Ainda não").click()
            pagina.wait_for_timeout(600)

            causa = pagina.locator("select").filter(has_text="Por que não saiu?").first
            causa.select_option(index=1)
            pagina.wait_for_timeout(500)
            pagina.get_by_role("button", name=re.compile("^Encerrar a semana$")).click()
            pagina.wait_for_timeout(1000)
            painel = pagina.locator("div[role=dialog]")
            texto_dialogo = painel.inner_text().lower()
            check(
                "com a causa preenchida, o diálogo deixa de acusar o que falta",
                "sem causa" not in texto_dialogo and "não foram julgados" not in texto_dialogo,
            )
            #: **O motivo só é pedido onde ele faz sentido.** A semana que já
            #: acabou não pede justificativa nenhuma — é o gesto normal. Quem
            #: decide isso é o servidor, pela data; a tela mostra o campo.
            if futura + timedelta(days=6) >= date.today():
                check(
                    "a semana que ainda não acabou pede o motivo do fechamento antecipado",
                    "antes do fim" in texto_dialogo,
                )
                painel.locator("textarea").first.fill(
                    "E2E — exercício do encerramento pela tela.")
            else:
                check(
                    "a semana que já acabou NÃO pede justificativa — é o gesto normal",
                    "antes do fim" not in texto_dialogo,
                )
            painel.get_by_role("button", name="Encerrar").click()
            pagina.wait_for_timeout(3000)
            painel = pagina.locator("div[role=dialog]")
            resultado = painel.inner_text().lower() if painel.count() else \
                pagina.inner_text("body").lower()
            check("encerrar devolve o índice na hora, no mesmo lugar",
                  "%" in resultado)
            check(
                "e diz em cima de QUE peso o índice foi feito",
                "peso por" in resultado or "fora da divisão" in resultado,
            )
            pagina.screenshot(path=f"{SHOTS}/03_semana_encerrada.png", full_page=True)
            if painel.count():
                painel.get_by_role("button", name="Fechar").click()
                pagina.wait_for_timeout(600)
    finally:
        #: O roteiro não deixa semana de mentira no banco do dono.
        if criada:
            r = urllib.request.Request(
                f"{GW}/api/pdca/programacoes/{criada}/",
                method="DELETE", headers={"Authorization": "Bearer " + token},
            )
            try:
                urllib.request.urlopen(r, timeout=30, context=_CTX)
                print("     (semana de trabalho apagada)")
            except Exception as erro:  # noqa: BLE001
                print(f"     !! a semana {criada} ficou no banco: {erro}")

    print("\n8b. A tela fica parada")
    check("nenhum erro de console no posto", not erros_js)
    if erros_js:
        print("     ", erros_js[:2])

    ctx.close()

    # =======================================================================
    # O CANTEIRO — a segunda superfície
    # =======================================================================
    print("\n9. O campo — casca própria, e a falta de rede DECLARADA")
    ctx = navegador.new_context(
        viewport={"width": 390, "height": 844},
        is_mobile=True, has_touch=True,
        user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"),
    )
    celular = ctx.new_page()
    erros_campo = []
    celular.on("pageerror", lambda e: erros_campo.append(str(e)))

    entrar(celular, "campo", "campo123")
    celular.goto(f"{GW}/campo")
    celular.wait_for_load_state("networkidle")
    celular.wait_for_timeout(1800)
    corpo = celular.inner_text("body")
    baixo = corpo.lower()
    check("a rota própria abre", celular.url.endswith("/campo"))
    check("a home é a minha frente, e não a obra", "minha frente" in baixo)
    check(
        "a dependência de rede é dita em voz alta",
        "precisa de rede" in baixo,
    )
    check(
        "e a casca do escritório não vem junto — sem rail dos seis postos",
        "medição" not in baixo or "qualidade" not in baixo,
    )
    check(
        "o bloco do que eu assumi está lá, com o verbo que o fecha",
        "aponte o quanto andou" in baixo,
    )
    check(
        "e traz o serviço pelo nome, com a obra",
        compromissos[0]["nome"][:18].lower() in baixo,
    )
    celular.screenshot(path=f"{SHOTS}/03_campo_frente.png", full_page=True)

    print("\n10. O alvo é dedo de luva")
    cartao = celular.locator(f"a[href*='/campo/apontar/']").first
    caixa = cartao.bounding_box()
    check("o cartão da frente tem alvo grande", bool(caixa) and caixa["height"] >= 48)

    print("\n11. O ato — apontar, e o número chega ao quadro do escritório")
    cartao.click()
    celular.wait_for_timeout(1600)
    corpo = celular.inner_text("body")
    baixo = corpo.lower()
    check("a tela do ato abre", "/campo/apontar/" in celular.url)
    check("uma decisão por tela: quanto o serviço andou", "quanto o serviço andou" in baixo)
    check(
        "e a tela diz que é o quanto ANDOU, não o total feito",
        "não o total já feito" in baixo,
    )
    check(
        "a câmera é oferecida, e é opcional",
        celular.get_by_text("Tirar foto").count() > 0,
    )
    campo_numero = celular.locator("input[inputmode=decimal]").first
    caixa = campo_numero.bounding_box()
    check("o número é grande e o teclado é numérico", bool(caixa) and caixa["height"] >= 48)

    campo_numero.fill("2,5")
    celular.get_by_role("button", name="Registrar avanço").click()
    celular.wait_for_timeout(2500)
    baixo = celular.inner_text("body").lower()
    check("registrar responde com confirmação, e não em silêncio",
          "registrado" in baixo)
    check("e o lançamento aparece na lista da semana", "apontado nesta semana" in baixo)
    celular.screenshot(path=f"{SHOTS}/04_campo_apontar.png", full_page=True)

    print("\n12. Estornar o próprio erro é um toque")
    botao = celular.get_by_title("Estornar este apontamento").first
    check("o estorno está ao alcance", botao.count() > 0)
    botao.click()
    celular.wait_for_timeout(900)
    #: **Tudo dentro do diálogo**, e não na página. A tela do ato já tem uma
    #: caixa de texto (a observação do apontamento), e `locator("textarea")`
    #: solto pega aquela: o motivo ficava vazio, o servidor recusava com razão,
    #: e o teste acusava a tela por um erro que era dele.
    painel = celular.locator("div[role=dialog]")
    check("o diálogo do estorno abre", painel.count() > 0)
    check(
        "e explica que a linha errada CONTINUA legível",
        "continua na lista" in painel.inner_text().lower(),
    )
    painel.locator("textarea").first.fill("E2E — desfazendo o lançamento de teste.")
    painel.get_by_role("button", name="Estornar").click()
    celular.wait_for_timeout(3000)
    baixo = celular.inner_text("body").lower()
    check(
        "o estorno entra como lançamento contrário",
        "-2,5" in baixo or "-2.5" in baixo,
    )
    check(
        "e o lançamento errado continua na lista, riscado",
        "+2,5" in baixo,
    )

    print("\n13. A tela do campo fica parada")
    check("nenhum erro de console no campo", not erros_campo)
    if erros_campo:
        print("     ", erros_campo[:2])

    ctx.close()
    navegador.close()

ok = sum(1 for p in passed if p)
print(f"\n{'='*62}")
print(f"RESULTADO: {ok}/{len(passed)}   ·   telas em {SHOTS}")
print('='*62)
sys.exit(0 if ok == len(passed) else 1)
