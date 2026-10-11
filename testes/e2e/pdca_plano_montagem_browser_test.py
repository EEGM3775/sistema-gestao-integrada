"""A montagem do plano **pela tela** — o posto PLANO do PDCA, clicando como gente.

Decisão do dono, 09/10/2026: *"hoje só consigo criar tarefa e mais nada. Quero
fazer tudo."* Este roteiro prova o "tudo" no navegador, sem API por trás da tela
(a API só cria a obra do teste e confere o que a tela gravou):

  1. obra sem plano abre o **assistente**; expediente escolhido (ou cadastrado ali);
  2. etapas por sugestão, atividades com duração, sequência encadeada → "Criar o plano";
  3. a grade traz a árvore com datas calculadas, e a fase seguinte começa depois da anterior;
  4. **teclado de planilha**: Insert cria abaixo já em edição, Tab recua, Shift+Tab avança;
  5. coluna **Predecessoras** digitada (`1.1SS+2`) e **Ctrl+Z** desfaz;
  6. **colar do Excel** pelo diálogo: hierarquia e predecessora entram;
  7. **Gantt**: puxar o pino de uma barra até outra liga (FS); arrastar a barra fixa a data;
  8. **Inspetor**: restrição de material com prazo segura o começo da atividade;
  9. "Trazer do orçamento" numa obra sem orçamento diz isso; publicar deixa vigente.

A obra é criada aqui, com o prefixo `E2E Plano`, e vai para a lixeira no fim.
Cada verificação que falha deixa evidência: faixa de erro, rede >= 400 e
screenshot em `/tmp/e2e_plano_<passo>.png`.

Rodar (stack de dev de pé, bundle novo no `sgi-react`):

    ~/sgi_e2e_venv.sh pdca_plano_montagem_browser_test.py
"""
import os
import re
import sys
import time
from datetime import date, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright
from _segundo_fator import responder_no_navegador
from _sessao import ANTI_CSRF

GW = os.environ.get("SGI_GW", "http://localhost:8090")
SHOTS = os.environ.get("SGI_SHOTS", "/tmp")
MARCA = f"E2E Plano {time.strftime('%d%m %H%M%S')}"
DATA_BR = re.compile(r"\d{2}/\d{2}/\d{2,4}")
ESPERA = 12_000
USUARIO = os.environ.get("SGI_USUARIO", "admin")
SENHA = os.environ.get("SGI_SENHA", "admin123")

passed = []
falhas = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")
    return bool(cond)


def fatal(msg):
    print(f"\n  !! {msg}")
    print(f"     Parcial: {sum(1 for p in passed if p)}/{len(passed)}")
    sys.exit(2)


print(f"\n{'='*62}\nPDCA — a montagem do plano na tela (09/10/2026)\n{'='*62}")
print(f"Gateway: {GW} · obra do teste: {MARCA} · usuário: {USUARIO}")

with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = navegador.new_context(viewport={"width": 1700, "height": 980})
    pagina = ctx.new_page()

    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))
    rede_ruim = []
    pagina.on("response", lambda r: rede_ruim.append(r) if r.status >= 400 else None)
    marco_rede = [0]

    def api(metodo, caminho, corpo=None):
        r = ctx.request.fetch(
            GW + caminho, method=metodo,
            headers={**ANTI_CSRF, "Content-Type": "application/json"}, data=corpo,
        )
        try:
            return r.status, r.json()
        except Exception:
            return r.status, r.text()

    def evidencia(passo, label):
        partes = []
        try:
            faixas = [f.strip() for f in pagina.locator("[role=alert]").all_inner_texts() if f.strip()]
            if faixas:
                partes.append("faixa: " + " | ".join(faixas))
        except Exception:
            pass
        for r in rede_ruim[marco_rede[0]:]:
            try:
                corpo = r.text()[:300]
            except Exception:
                corpo = "(sem corpo)"
            partes.append(f"HTTP {r.status} {r.request.method} {r.url.replace(GW, '')} → {corpo}")
        nome = re.sub(r"[^a-z0-9]+", "_", passo.lower()).strip("_")
        caminho = f"{SHOTS}/e2e_plano_{nome}.png"
        try:
            pagina.screenshot(path=caminho, full_page=True)
            partes.append(f"screenshot: {caminho}")
        except Exception:
            pass
        falhas.append((passo, label, partes))
        for x in partes:
            print(f"       · {x}")

    def verifica(passo, label, cond):
        if not check(label, cond):
            evidencia(passo, label)
        return cond

    def novo_passo():
        marco_rede[0] = len(rede_ruim)

    def espera(locator, timeout=ESPERA):
        try:
            locator.first.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    def ate(cond, segundos=10):
        fim = time.time() + segundos
        while time.time() < fim:
            try:
                if cond():
                    return True
            except Exception:
                pass
            pagina.wait_for_timeout(300)
        return False

    grade = pagina.locator("[role=grid][aria-label='Estrutura do plano']")
    aside = pagina.locator("aside[aria-label='Detalhe do que está selecionado']")

    def linha(nome):
        return grade.locator(f"[role=row]:has(span[title='{nome}'])").first

    def codigo(nome):
        try:
            return linha(nome).locator("[role=gridcell]").nth(0).inner_text().strip()
        except Exception:
            return None

    def celula(nome, indice):
        return linha(nome).locator("[role=gridcell]").nth(indice)

    def plano_da_obra():
        _, planos = api("GET", f"/api/pdca/cronogramas/?obra={obra_id}")
        lista = planos.get("results", planos) if isinstance(planos, dict) else planos
        return sorted(lista or [], key=lambda c: -c["versao"])[0] if lista else None

    def rede():
        c = plano_da_obra()
        _, g = api("GET", f"/api/pdca/cronogramas/{c['cronograma_id']}/gantt/")
        por_nome = {a["nome"]: a for a in g["atividades"]}
        return por_nome, g["precedencias"]

    # ------------------------------------------------------------------ login
    print(f"\n0. Login de `{USUARIO}`")
    pagina.goto(f"{GW}/login", wait_until="networkidle")
    pagina.fill("input#username", USUARIO)
    pagina.fill("input#password", SENHA)
    pagina.click("button[type=submit]")
    try:
        responder_no_navegador(pagina)
        pagina.wait_for_url("**/app/**", timeout=25_000)
    except Exception as e:
        pagina.screenshot(path=f"{SHOTS}/e2e_plano_login.png")
        fatal(f"`{USUARIO}` não entrou ({str(e).splitlines()[0]})")
    check(f"`{USUARIO}` entrou", "/app" in pagina.url)

    status, obra = api("POST", "/api/obras/", {
        "nome_obra": MARCA, "endereco": "Rua de teste, s/n", "status_obra": "planejamento",
    })
    if status not in (200, 201):
        fatal(f"não consegui criar a obra do teste (HTTP {status}: {obra})")
    obra_id = obra["obra_id"]

    try:
        # ------------------------------------------------------------- 1
        P = "1 assistente"
        print("\n1. Obra sem plano abre o assistente")
        novo_passo()
        pagina.goto(f"{GW}/app/pdca/o/{obra_id}/plano", wait_until="networkidle")
        verifica(P, "o assistente 'Montar o plano da obra' aparece",
                 espera(pagina.get_by_text("Montar o plano da obra")))
        if pagina.get_by_role("button", name="Cadastrar expediente").count():
            pagina.get_by_role("button", name="Cadastrar expediente").click()
            verifica(P, "o expediente se cadastra ali mesmo",
                     ate(lambda: pagina.get_by_role("button", name="Próximo").is_enabled()))
        proximo = pagina.get_by_role("button", name="Próximo")
        verifica(P, "com início e expediente, dá para seguir", ate(lambda: proximo.is_enabled()))
        proximo.click()
        verifica(P, "os quatro pontos de partida aparecem",
                 espera(pagina.get_by_text("Do orçamento da obra")) and pagina.get_by_text("Colar do Excel ou MS Project").count() > 0)
        pagina.get_by_role("button", name=re.compile("Digitar etapas e atividades")).click()
        proximo.click()

        # ------------------------------------------------------------- 2
        P = "2 etapas e atividades"
        print("\n2. Etapas por sugestão, atividades com duração")
        novo_passo()
        pagina.get_by_role("button", name="+ Fundação").click()
        pagina.get_by_role("button", name="+ Estrutura").click()
        atividade_btn = pagina.get_by_role("button", name="Atividade", exact=True)
        nomes = pagina.get_by_placeholder("Atividade (Enter adiciona a próxima)")
        duracoes = pagina.get_by_label("Duração em dias úteis")
        atividade_btn.nth(0).click()
        nomes.nth(0).fill("Estacas")
        duracoes.nth(0).fill("10")
        nomes.nth(0).press("Enter")
        nomes.nth(1).fill("Blocos")
        duracoes.nth(1).fill("8")
        atividade_btn.nth(1).click()
        nomes.nth(2).fill("Pilares")
        duracoes.nth(2).fill("5")
        verifica(P, "três atividades digitadas", nomes.count() == 3)
        proximo.click()
        verifica(P, "o passo da sequência aparece", espera(pagina.get_by_text("Uma etapa começa quando a anterior termina")))
        proximo.click()
        pagina.get_by_role("button", name=re.compile("Criar o plano")).click()

        # ------------------------------------------------------------- 3
        P = "3 grade"
        print("\n3. A grade nasce com a árvore e as datas")
        novo_passo()
        verifica(P, "a grade aparece", espera(grade, 20_000))
        verifica(P, "as linhas e os códigos: 1 Fundação, 1.1 Estacas, 1.2 Blocos, 2 Estrutura, 2.1 Pilares",
                 ate(lambda: [codigo(n) for n in ("Fundação", "Estacas", "Blocos", "Estrutura", "Pilares")]
                     == ["1", "1.1", "1.2", "2", "2.1"]))
        verifica(P, "as datas estão calculadas (início de Pilares)",
                 ate(lambda: bool(DATA_BR.search(celula("Pilares", 4).inner_text()))))
        por_nome, prec = rede()
        blocos, pilares = por_nome["Blocos"], por_nome["Pilares"]
        verifica(P, f"Estrutura (fase) começa depois de Fundação: Pilares {pilares['inicio_cedo']} > Blocos {blocos['termino_cedo']}",
                 pilares["inicio_cedo"] and blocos["termino_cedo"] and pilares["inicio_cedo"] > blocos["termino_cedo"])
        verifica(P, "Blocos depende de Estacas (encadeado dentro da etapa)",
                 any(x["origem"] == por_nome["Estacas"]["atividade_id"] and x["destino"] == blocos["atividade_id"] for x in prec))
        pagina.screenshot(path=f"{SHOTS}/e2e_plano_ok_03_grade.png", full_page=True)

        # ------------------------------------------------------------- 4
        P = "4 teclado"
        print("\n4. Teclado de planilha: Insert, Tab, Shift+Tab")
        novo_passo()
        celula("Blocos", 1).click()
        pagina.keyboard.press("Insert")
        editor = grade.locator("input[type=text]")
        verifica(P, "Insert cria a linha abaixo já em edição", espera(editor))
        pagina.keyboard.press("Control+a")
        pagina.keyboard.type("Formas")
        pagina.keyboard.press("Enter")
        verifica(P, "a nova linha 'Formas' entra como 1.3", ate(lambda: codigo("Formas") == "1.3"))
        celula("Formas", 1).click()
        pagina.keyboard.press("Tab")
        verifica(P, "Tab recua: Formas vira 1.2.1 (dentro de Blocos)", ate(lambda: codigo("Formas") == "1.2.1"))
        celula("Formas", 1).click()
        pagina.keyboard.press("Shift+Tab")
        verifica(P, "Shift+Tab avança: Formas volta a 1.3", ate(lambda: codigo("Formas") == "1.3"))

        # ------------------------------------------------------------- 5
        P = "5 predecessoras"
        print("\n5. Predecessoras digitadas e Ctrl+Z")
        novo_passo()
        celula("Formas", 3).click()
        pagina.keyboard.type("1.1SS+2")
        pagina.keyboard.press("Enter")

        def ligacao_formas():
            por_nome, prec = rede()
            f = por_nome["Formas"]["atividade_id"]
            return [x for x in prec if x["destino"] == f]
        verifica(P, "Formas ← Estacas, SS +2",
                 ate(lambda: any(x["tipo"] == "SS" and x["atraso_dias"] == 2 for x in ligacao_formas())))
        verifica(P, "a coluna mostra 1.1SS+2", ate(lambda: "1.1SS+2" in celula("Formas", 3).inner_text()))
        celula("Formas", 1).click()
        pagina.keyboard.press("Control+z")
        verifica(P, "Ctrl+Z desfaz a ligação", ate(lambda: ligacao_formas() == []))

        # ------------------------------------------------------------- 6
        P = "6 colar"
        print("\n6. Colar do Excel pelo diálogo")
        novo_passo()
        pagina.get_by_role("button", name=re.compile("Montar")).click()
        pagina.get_by_role("menuitem", name=re.compile("Colar do Excel")).click()
        pagina.locator("[role=dialog] textarea").fill("3\tAcabamento\n3.1\tPintura\t4\t2.1")
        verifica(P, "a prévia mostra Pintura", espera(pagina.locator("td", has_text="Pintura")))
        pagina.get_by_role("button", name=re.compile(r"Trazer 2 linha")).click()
        verifica(P, "o resultado diz 2 linhas e 1 ligação",
                 espera(pagina.get_by_text(re.compile(r"2 linha\(s\) e 1 ligação"))))
        pagina.locator("[role=dialog]").get_by_role("button", name="Fechar", exact=True).last.click()
        verifica(P, "Pintura entra como 3.1", ate(lambda: codigo("Pintura") == "3.1"))

        # ------------------------------------------------------------- 7
        P = "7 gantt"
        print("\n7. Gantt: puxar o pino liga; arrastar a barra fixa a data")
        novo_passo()
        celula("Estacas", 1).click()
        pino = pagina.locator("circle", has=pagina.locator("title", has_text="o que vem depois"))
        tem_pino = espera(pino)
        verifica(P, "a barra selecionada mostra o pino de ligar", tem_pino)
        if tem_pino:
            a = pino.first.bounding_box()
            alvo = linha("Pintura").bounding_box()
            svg = pagina.locator("svg[style*='touch-action']").bounding_box()
            pagina.mouse.move(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2)
            pagina.mouse.down()
            pagina.mouse.move(svg["x"] + 40, alvo["y"] + alvo["height"] / 2, steps=12)
            pagina.mouse.move(svg["x"] + 4, alvo["y"] + alvo["height"] / 2, steps=4)
            pagina.mouse.up()

            def ligou():
                por_nome, prec = rede()
                return any(x["origem"] == por_nome["Estacas"]["atividade_id"]
                           and x["destino"] == por_nome["Pintura"]["atividade_id"]
                           and x["tipo"] == "FS" for x in prec)
            verifica(P, "Estacas → Pintura (FS) gravada", ate(ligou))

        # XPath não enxerga o espaço de nomes do SVG: acha-se o <title> e sobe ao <g>.
        barra = pagina.locator("svg title", has_text="2.1 · Pilares").locator("..")
        tem_barra = espera(barra)
        verifica(P, "a barra de Pilares está no Gantt", tem_barra)
        if tem_barra:
            b = barra.first.bounding_box()
            pagina.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
            pagina.mouse.down()
            pagina.mouse.move(b["x"] + b["width"] / 2 + 70, b["y"] + b["height"] / 2, steps=10)
            pagina.mouse.up()
            verifica(P, "arrastar fixou 'não começar antes de' em Pilares",
                     ate(lambda: rede()[0]["Pilares"]["nao_comecar_antes_de"] is not None))
        pagina.screenshot(path=f"{SHOTS}/e2e_plano_ok_07_gantt.png", full_page=True)

        # ------------------------------------------------------------- 8
        P = "8 restricao"
        print("\n8. Inspetor: restrição de material segura o começo")
        novo_passo()
        celula("Estacas", 1).click()
        verifica(P, "o Inspetor abre com a rede e as restrições",
                 espera(aside.get_by_text("Depende de")) and aside.get_by_text(re.compile("Restrições")).count() > 0)
        prazo = (date.today() + timedelta(days=40)).isoformat()
        aside.get_by_role("button", name=re.compile(r"\+ Restrição")).click()
        aside.get_by_placeholder("Ex.: aço CA-50 da 2ª laje").fill("Aço das estacas")
        aside.locator("input[title='Quando o material chega']").fill(prazo)
        aside.get_by_role("button", name="Registrar").click()
        verifica(P, "a restrição aparece no Inspetor", espera(aside.get_by_text("Aço das estacas")))
        verifica(P, f"Estacas não começa antes de {prazo}",
                 ate(lambda: rede()[0]["Estacas"]["nao_comecar_antes_de"] == prazo))

        # ------------------------------------------------------------- 8b
        P = "8b achados do dono"
        print("\n8b. Recolher, várias de vez, excluir no diálogo, Ctrl+Z (achados do dono, 09/10)")
        novo_passo()
        linha("Fundação").get_by_role("button", name="Recolher").click()
        verifica(P, "recolher esconde as filhas (e não as joga no fim do plano)",
                 ate(lambda: linha("Estacas").count() == 0 and linha("Blocos").count() == 0))
        pagina.reload(wait_until="networkidle")
        espera(grade)
        verifica(P, "recolhida continua recolhida depois de recarregar",
                 ate(lambda: linha("Fundação").count() == 1 and linha("Estacas").count() == 0))
        linha("Fundação").get_by_role("button", name="Expandir").click()
        verifica(P, "e volta ao expandir", ate(lambda: linha("Estacas").count() == 1))

        celula("Formas", 1).click()
        celula("Pintura", 1).click(modifiers=["Control"])
        verifica(P, "Ctrl+clique marca duas linhas (o Inspetor mostra o lote)",
                 espera(aside.get_by_text("2 linhas marcadas")))
        dialogos_nativos = []
        pagina.on("dialog", lambda d: (dialogos_nativos.append(d.message), d.dismiss()))
        pagina.keyboard.press("Delete")
        confirma = pagina.locator("[role=dialog]", has_text="Excluir 2 linhas?")
        verifica(P, "Delete abre o diálogo do sistema (não o popup do navegador)",
                 espera(confirma) and not dialogos_nativos)
        inicio_exclusao = time.time()
        confirma.get_by_role("button", name="Excluir", exact=True).click()
        sumiu_rapido = ate(lambda: linha("Formas").count() == 0 and linha("Pintura").count() == 0, 3)
        verifica(P, f"as duas somem da tela na hora ({time.time() - inicio_exclusao:.1f}s)", sumiu_rapido)
        verifica(P, "e saem do servidor", ate(lambda: "Formas" not in rede()[0] and "Pintura" not in rede()[0]))
        pagina.get_by_text("Plano", exact=True).first.click()
        pagina.keyboard.press("Control+z")
        verifica(P, "Ctrl+Z fora da grade traz as duas de volta, nos mesmos lugares",
                 ate(lambda: codigo("Formas") == "1.3" and codigo("Pintura") == "3.1", 15))
        verifica(P, "com a ligação de Pintura (2.1) restaurada",
                 ate(lambda: "2.1" in celula("Pintura", 3).inner_text()))

        celula("Pilares", 1).click()
        pagina.keyboard.press("F2")
        pagina.keyboard.press("Control+a")
        pagina.keyboard.type("Pilares do térreo")
        pagina.keyboard.press("Enter")
        verifica(P, "renomeia", ate(lambda: linha("Pilares do térreo").count() == 1))
        pagina.reload(wait_until="networkidle")
        espera(grade)
        pagina.get_by_text("Plano", exact=True).first.click()
        pagina.keyboard.press("Control+z")
        verifica(P, "Ctrl+Z vale depois de recarregar a página", ate(lambda: linha("Pilares").count() == 1, 15))

        # ------------------------------------------------------------- 9
        P = "9 orcamento e publicar"
        print("\n9. Orçamento ausente é dito; publicar")
        novo_passo()
        # Janela estreita: o botão quebra para a esquerda e o menu tem de abrir
        # por cima de tudo, dentro da tela (achado do dono, 09/10/2026).
        pagina.set_viewport_size({"width": 1000, "height": 900})
        pagina.wait_for_timeout(400)
        pagina.get_by_role("button", name=re.compile("Montar")).click()
        menu = pagina.locator("[role=menu]")
        espera(menu)
        caixa = menu.bounding_box()
        verifica(P, "com a janela estreita o menu cabe na tela",
                 caixa is not None and caixa["x"] >= 0 and caixa["x"] + caixa["width"] <= 1000)
        no_topo = caixa is not None and pagina.evaluate(
            "([x, y]) => !!document.elementFromPoint(x, y)?.closest('[role=menu]')",
            [caixa["x"] + caixa["width"] / 2, caixa["y"] + 20],
        )
        verifica(P, "e fica por cima das abas e do trilho", no_topo)
        pagina.get_by_role("menuitem", name=re.compile("Trazer do orçamento")).click()
        pagina.set_viewport_size({"width": 1700, "height": 980})
        verifica(P, "sem orçamento, o diálogo diz isso", espera(pagina.get_by_text("Esta obra ainda não tem orçamento")))
        pagina.get_by_role("button", name="Cancelar").click()
        pagina.get_by_role("button", name="Publicar").click()
        verifica(P, "o plano fica vigente", espera(pagina.get_by_text("Este plano está vigente")))

        print("\n10. A tela ficou limpa")
        verifica("10 tela limpa", f"nenhum erro de JavaScript ({len(erros_js)})", not erros_js)
        for e in erros_js[:4]:
            print(f"       · {e[:200]}")
    finally:
        print("\n11. Faxina")
        s, _ = api("DELETE", f"/api/obras/{obra_id}/?motivo=Faxina+do+E2E+montagem+do+plano")
        print(f"     obra {obra_id} → lixeira, HTTP {s}")
        navegador.close()

ok = sum(1 for p in passed if p)
if falhas:
    print(f"\n{'-'*62}\nFalhas, com evidência:")
    for passo, label, partes in falhas:
        print(f"  - [{passo}] {label}")
        for x in partes:
            print(f"      {x}")
print(f"\n{'='*62}\n  Montagem do plano na tela: {ok}/{len(passed)} verificações\n{'='*62}\n")
sys.exit(0 if ok == len(passed) else 1)
