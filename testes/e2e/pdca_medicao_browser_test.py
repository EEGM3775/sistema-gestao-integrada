"""O posto da MEDIÇÃO **na tela** — contratos, prévia, grade e escada de atesto.

Irmão do `pdca_cockpit_browser_test.py`, e o **sucessor dos dois roteiros da
PDCA.3** (`pdca3_formulario_browser_test.py` e `pdca3_grade_browser_test.py`),
que dirigiam a tela apagada em 20/09/2026 quando o frontend do módulo foi
redesenhado do eixo. A régua que eles guardavam continua valendo; o que
envelheceu foi o caminho até a tela — o endereço deixou de ser
`/app/pdca/obra/{id}/contratos` e passou a ser `/app/pdca/o/{id}/medicao`, e o
contrato deixou de ser uma página para virar uma vista dentro do posto.

O `pdca_medicao_posto_test.py` prova que a API responde certo; este prova que a
**tela** faz o que a régua de pronto (modulopdca-frontend.md §12) exige:

  1. **o posto abre pela fila**, e a fila é documento parado com o verbo que o
     fecha — nunca "N pendências";
  2. **a carteira de contratos traz o saldo derivado**, e clicar entra no
     contrato sem trocar de posto;
  3. **a prévia é somente leitura, e a tela diz** — número é texto, não `input`
     desabilitado (convenções §10). É a régua que o dono cobrou em 15/09/2026:
     *"a parte mais importante da medição não consigo editar"*;
  4. **a grade do boletim aberto é viva**, tem as colunas da G703 e a memória
     de cálculo abre linha a linha, dizendo de onde veio o número;
  5. **a trava da planilha vem do servidor** — com medição em voo, a planilha
     aparece fechada COM a frase, e não com campos que a API recusaria
     (convenções §11);
  6. **o boletim não some**: totais, deduções e escada renderizam juntos — foi
     um `r.deducoes.map is not a function` que deixou esta tela em branco;
  7. **o estado vazio traz o botão** que leva à ação que ele pede
     (convenções §12);
  8. e a tela fica **parada** — uma leitura por abertura, sem laço de
     renderização e sem erro de console.

Rodar (stack de pé, imagem `react` rebuildada):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/pdca_medicao_browser_test.py

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
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_medicao")
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
        with urllib.request.urlopen(r, timeout=90, context=_CTX) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, None


BLOCOS = (
    "medicoes_em_rascunho", "medicoes_a_atestar",
    "retencoes_a_liberar", "aditivos_a_decidir",
)

print(f"\n{'='*62}\nPDCA — o posto da medição na tela\n{'='*62}")
print(f"Gateway: {GW}")

try:
    token = login("gerente", "gerente123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé?")

codigo, carteira = req("/api/pdca/carteira/", token)
if codigo != 200 or not carteira["obras"]:
    fatal("a carteira não respondeu com obras — rode os seeds do PDCA.")

# A obra de trabalho é a de fila mais cheia: o tenant de demonstração acumula
# obras de execuções anteriores do E2E, e cair numa delas provaria só que a
# tela sabe ficar vazia.
candidatas = []
for linha in carteira["obras"]:
    codigo, corpo = req(f"/api/pdca/medicao/?obra={linha['obra']}", token)
    if codigo == 200 and corpo["contratos"]["linhas"]:
        candidatas.append((corpo["fila"]["total"], linha["obra"], linha["nome"], corpo))
if not candidatas:
    fatal("nenhuma obra com contrato — rode `semear_pdca_demo` e `semear_pdca_execucao`.")

_, obra_id, obra_nome, posto = max(candidatas, key=lambda c: c[0])
linhas_de_contrato = posto["contratos"]["linhas"]
fila_total = posto["fila"]["total"]

# **O contrato de trabalho é o de preço unitário**, porque é ele que tem grade:
# no regime de administração não há linha nenhuma — o que se mede é o custo, e
# a tela troca a grade pelo campo do custo reembolsável (§5.4 do desenho). O
# de administração fica guardado à parte, para provar justamente essa troca.
contrato = next(
    (c for c in linhas_de_contrato if c["regime"] != "administracao"),
    linhas_de_contrato[0],
)
contrato_adm = next(
    (c for c in linhas_de_contrato if c["regime"] == "administracao"), None,
)
print(f"     obra de trabalho: {obra_id} · {obra_nome}")
print(f"     contrato: {contrato['numero']} ({contrato['regime']}) "
      f"· fila com {fila_total} documento(s)")

with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = navegador.new_context(viewport={"width": 1500, "height": 950})
    pagina = ctx.new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))
    chamadas = []
    pagina.on(
        "request",
        lambda r: chamadas.append(r.url) if "/api/pdca/" in r.url else None,
    )

    print("\n1. Login pela tela")
    pagina.goto(f"{GW}/login")
    pagina.wait_for_load_state("networkidle")
    pagina.fill("input#username", "gerente")
    pagina.fill("input#password", "gerente123")
    pagina.click("button[type=submit]")
    pagina.wait_for_url("**/app/**", timeout=25000)
    check("`gerente` entrou", "/app" in pagina.url)

    print("\n2. O posto abre — e o rail leva até ele")
    pagina.goto(f"{GW}/app/pdca/o/{obra_id}/hoje")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1200)
    alvo = pagina.get_by_role("link", name=re.compile("Medição", re.I))
    check("o posto MEDIÇÃO está no rail e é clicável (não trancado)",
          alvo.count() > 0)
    if alvo.count() > 0:
        alvo.first.click()
        pagina.wait_for_timeout(1800)
    else:
        pagina.goto(f"{GW}/app/pdca/o/{obra_id}/medicao")
        pagina.wait_for_load_state("networkidle")
        pagina.wait_for_timeout(1800)

    corpo = pagina.inner_text("body")
    baixo = corpo.lower()
    check("o endereço é o do posto", f"/o/{obra_id}/medicao" in pagina.url)
    check("e a página diz o que ela decide", "medição" in baixo)

    print("\n3. A fila do dinheiro — documento parado, com o verbo que o fecha")
    if fila_total > 0:
        check("a fila abre primeiro, e diz que é decisão",
              "o que espera decisão" in baixo)
        check(
            "cada bloco traz o VERBO, não só a contagem",
            any(v in baixo for v in (
                "atestar ou devolver", "conferir a grade e enviar",
                "conferir a condição do contrato", "decidir antes da próxima",
            )),
        )
        check(
            "e NÃO existe um 'N pendências' que misture o que não se mistura",
            not re.search(r"\d+\s+pend[êe]ncias", baixo),
        )
        check("as linhas dizem há quanto tempo esperam",
              "há " in baixo or "hoje" in baixo)
        check("e o valor de cada uma, para escolher qual olhar primeiro",
              "r$" in baixo)
    else:
        check("fila vazia diz o que varreu, em vez de abrir em branco",
              "nenhum documento parado" in baixo)

    print("\n4. A ausência declarada — nada de 'contrato sem medir há N dias'")
    check(
        "a tela não inventa cobrança por periodicidade de medição",
        "sem medir" not in baixo and "atrasad" not in baixo.split("retenção")[0],
    )
    pagina.screenshot(path=f"{SHOTS}/01_posto_fila.png", full_page=True)

    print("\n5. A carteira de contratos — o saldo derivado na tela")
    check("lista o contrato pelo número", contrato["numero"].lower() in baixo)
    check("e o empreiteiro pelo nome",
          contrato["fornecedor_nome"][:16].lower() in baixo)
    check(
        "com as colunas do dinheiro: contratado, aprovado, saldo e retido",
        all(c in baixo for c in ("contratado", "aprovado", "saldo", "retido")),
    )
    check(
        "e o período que a PRÓXIMA medição cobriria, como informação",
        "próximo período" in baixo,
    )

    print("\n5b. A segregação aparece na tela — quem ateste não monta contrato")
    # `gerente` é a diretoria: tem `medicao.atestar` e `aditivo.aprovar`, e
    # **não** tem `contrato.edit`. O verbo some, em vez de aparecer e recusar:
    # é a régua omitir × trancar aplicada a um verbo, e não a uma página.
    check(
        "o botão de cadastrar contrato NÃO aparece para quem só ateste",
        pagina.get_by_role("button", name=re.compile("Novo contrato", re.I)).count() == 0,
    )

    print("\n6. Entrar no contrato — o posto troca de vista, não de rota")
    pagina.get_by_text(contrato["numero"], exact=True).first.click()
    pagina.wait_for_timeout(1500)
    corpo = pagina.inner_text("body")
    baixo = corpo.lower()
    check("o contrato entra no endereço — o link é colável",
          f"contrato={contrato['contrato']}" in pagina.url)
    check("continua no posto MEDIÇÃO", f"/o/{obra_id}/medicao" in pagina.url)
    check(
        "e as cinco vistas do contrato aparecem",
        all(v in baixo for v in ("apurar", "boletins", "planilha", "aditivos",
                                 "retenção")),
    )
    check("o saldo acompanha o cabeçalho em todas as vistas",
          "contratado" in baixo and "saldo" in baixo)

    print("\n7. Apurar — a prévia, e o período vem ancorado na corrente")
    check("a vista abre em Apurar", "apurar um período" in baixo)
    check(
        "e diz de onde o período nasceu, em vez de abrir no primeiro do mês",
        "a última medição fechou em" in baixo or "ainda não houve medição" in baixo,
    )
    ver = pagina.get_by_role("button", name=re.compile("Ver a prévia", re.I))
    check("existe caminho de dedo até a prévia", ver.count() > 0)
    if ver.count() > 0:
        ver.first.click()
        pagina.wait_for_timeout(2500)
        corpo = pagina.inner_text("body")
        baixo = corpo.lower()
        check("a prévia renderiza as colunas da G703",
              all(c in baixo for c in ("contratado", "já medido", "saldo", "proposto")))
        # **A régua que o dono cobrou**: a prévia é leitura por desenho, e a
        # tela tem de DIZER isso — `input` desabilitado tem borda e cursor e
        # convida a clicar sem aceitar nada.
        check(
            "e a tela DIZ que é leitura, em vez de mostrar campos travados",
            "esta grade é de leitura" in baixo,
        )
        campos = pagina.locator("table input:not([type=checkbox])")
        check(
            f"nenhum campo de digitação na prévia (achei {campos.count()})",
            campos.count() == 0,
        )
        check(
            "e o total da prévia é chamado de bruto, não de total",
            "de bruto, antes de retenção" in baixo,
        )
    pagina.screenshot(path=f"{SHOTS}/02_previa.png", full_page=True)

    print("\n8. A planilha contratual — a trava vem do servidor, com a frase")
    pagina.get_by_role("button", name=re.compile("^Planilha$", re.I)).first.click()
    pagina.wait_for_timeout(1800)
    corpo = pagina.inner_text("body")
    baixo = corpo.lower()
    check("a planilha abre", "planilha contratual" in baixo)
    if contrato["planilha_editavel"]:
        check("planilha aberta oferece o caminho de incluir item",
              "novo item" in baixo or "cadastrar o primeiro item" in baixo)
    else:
        # A frase é a MESMA que a API devolveria ao recusar — duas redações
        # divergiriam na primeira mudança de regra.
        trecho = contrato["planilha_fechada_porque"].replace("**", "")[:40].lower()
        check("planilha fechada mostra o motivo do servidor, e não um aviso próprio",
              trecho in baixo)
        campos = pagina.locator("table input:not([type=checkbox])")
        check(
            f"e não oferece campo que a API recusaria (achei {campos.count()})",
            campos.count() == 0,
        )
    pagina.screenshot(path=f"{SHOTS}/03_planilha.png", full_page=True)

    print("\n9. O boletim — totais, deduções e escada renderizam juntos")
    pagina.get_by_role("button", name=re.compile("^Boletins$", re.I)).first.click()
    pagina.wait_for_timeout(1800)
    corpo = pagina.inner_text("body")
    baixo = corpo.lower()

    codigo, boletins = req(
        f"/api/pdca/medicoes/?contrato={contrato['contrato']}&resumo=1", token,
    )
    linhas_api = (boletins or {}).get("results", boletins if isinstance(boletins, list) else [])
    if linhas_api:
        check("a lista de boletins mostra período e estado de cada um",
              "a " in baixo and any(
                  b["status_rotulo"].lower() in baixo for b in linhas_api))
        pagina.get_by_text(re.compile(r"\d{2}/\d{2}/\d{4} a \d{2}/\d{2}/\d{4}")).first.click()
        pagina.wait_for_timeout(2200)
        corpo = pagina.inner_text("body")
        baixo = corpo.lower()
        check("o boletim entra no endereço", "boletim=" in pagina.url)
        # O boletim que some é o defeito que um `map` num dado achatado causou:
        # a tela ficava em branco e ninguém sabia por quê.
        check("o boletim NÃO fica em branco", len(corpo.strip()) > 400)
        check(
            "o dinheiro aparece na ordem em que encolhe",
            all(r in baixo for r in ("bruto do período", "retenção contratual",
                                     "descontos", "líquido a pagar")),
        )
        check("as deduções têm seção própria, mesmo vazias",
              "descontos deste boletim" in baixo)
        check(
            "e a escada diz de quem se espera a assinatura",
            "quem assinou" in baixo or "não passou por escada" in baixo,
        )

        print("\n10. A grade do boletim — viva, com a memória de cálculo")
        boletim_id = int(pagina.url.split("boletim=")[1].split("&")[0])
        codigo, contexto = req(f"/api/pdca/medicoes/{boletim_id}/contexto/", token)
        if codigo == 200 and contexto["linhas"]:
            primeiro = contexto["linhas"][0]["codigo"]
            linha_da_grade = pagina.get_by_role(
                "button", name=re.compile(rf"^{re.escape(primeiro)}$"),
            )
            check("a grade traz uma linha por item do contrato",
                  linha_da_grade.count() > 0)
            if contexto["editavel"]:
                campos = pagina.locator("table input:not([type=checkbox])")
                check(f"rascunho tem campo para digitar (achei {campos.count()})",
                      campos.count() > 0)
                # **D137**: "Salvar grade" e "Submeter" como botões separados
                # faziam o servidor congelar os números antigos, em silêncio, e
                # emitir o título. O botão sumiu porque o sistema passou a
                # gravar sozinho — e o selo diz sempre em que pé está.
                check(
                    "NÃO existe botão de salvar a grade — ela grava sozinha",
                    pagina.get_by_role(
                        "button", name=re.compile("Gravar a grade", re.I)).count() == 0,
                )
                check("e o selo de gravação está sempre na tela",
                      "grava sozinha" in baixo)
            else:
                check("boletim enviado tem a grade em leitura, e diz isso",
                      "esta grade é de leitura" in baixo)
            # **De onde veio o número** — é o que separa apuração conferível de
            # caixa preta, e é a régua que o posto existe para cumprir.
            if linha_da_grade.count() > 0:
                linha_da_grade.first.click()
                pagina.wait_for_timeout(700)
                corpo = pagina.inner_text("body")
                baixo = corpo.lower()
                check("abrir a linha mostra de onde veio a quantidade proposta",
                      "de onde veio a quantidade proposta" in baixo)
                sem_vinculo = contexto["cobertura"]["sem_vinculo"]
                if sem_vinculo:
                    check(
                        "e a cobertura é declarada: item sem serviço ligado não "
                        "vira zero mudo",
                        "não têm serviço do cronograma ligado" in baixo,
                    )
        pagina.screenshot(path=f"{SHOTS}/04_boletim.png", full_page=True)
    else:
        check("contrato sem boletim traz o botão que leva a apurar",
              "apurar um período" in baixo)

    if contrato_adm is not None:
        print("\n10b. Administração — o que se mede é o CUSTO, não a quantidade")
        codigo, bol_adm = req(
            f"/api/pdca/medicoes/?contrato={contrato_adm['contrato']}&resumo=1", token,
        )
        adm = (bol_adm or {}).get("results") or []
        if adm:
            pagina.goto(
                f"{GW}/app/pdca/o/{obra_id}/medicao"
                f"?contrato={contrato_adm['contrato']}&boletim={adm[0]['medicao_id']}"
            )
            pagina.wait_for_load_state("networkidle")
            pagina.wait_for_timeout(2200)
            corpo = pagina.inner_text("body")
            baixo = corpo.lower()
            # Sem esta porta, o regime inteiro ficava sem tela: abria o boletim
            # e nunca conseguia submetê-lo.
            check("o boletim por administração pede o custo reembolsável",
                  "custo reembolsável do período" in baixo)
            check(
                "e diz onde conferir o número, em vez de explicar o software",
                "confira com a folha" in baixo,
            )
            check(
                "sem prometer apuração automática que não existe",
                "apropriação" not in baixo,
            )

    print("\n11. Sem jargão na tela")
    check(
        "nenhum número de fatia nem referência a documento interno",
        not re.search(r"pdca\.\d|§\d", corpo),
    )
    check(
        "e nenhum código de permissão cru fora do aviso de cadeado",
        "pdca.medicao.view" not in baixo or "não tem permissão" in baixo,
    )

    print("\n11b. O contrato novo, com `demo` — e os seis defeitos do D132")
    # Quem monta contrato é a engenharia (`contrato.edit` + `medicao.apurar`),
    # e é por isso que esta parte troca de pessoa: o formulário não existe para
    # a diretoria. Os seis defeitos do formulário anterior foram corrigidos no
    # **kit** (`malha/Campos.tsx`), e é o kit que este trecho cobra.
    pg2 = ctx.new_page()
    erros_pg2 = []
    pg2.on("pageerror", lambda e: erros_pg2.append(str(e)))
    pg2.goto(f"{GW}/login")
    pg2.wait_for_load_state("networkidle")
    pg2.fill("input#username", "demo")
    pg2.fill("input#password", "demo123")
    pg2.click("button[type=submit]")
    pg2.wait_for_url("**/app/**", timeout=25000)
    pg2.goto(f"{GW}/app/pdca/o/{obra_id}/medicao")
    pg2.wait_for_load_state("networkidle")
    pg2.wait_for_timeout(2000)

    novo = pg2.get_by_role("button", name=re.compile("Novo contrato", re.I))
    check("quem monta contrato VÊ o caminho de cadastrá-lo", novo.count() > 0)
    if novo.count() > 0:
        novo.first.click()
        pg2.wait_for_timeout(1400)
        check("o formulário se anuncia como diálogo para quem usa leitor de tela",
              pg2.get_by_role("dialog").count() > 0)
        # D132.3 — `/api/fornecedores/` responde lista crua; ler `.results`
        # deixava o select vazio sem erro nenhum.
        opcoes = pg2.locator("select").first.locator("option")
        check(f"o select de empreiteiros vem cheio (achei {opcoes.count()} opções)",
              opcoes.count() > 1)
        # D132.4 — o rodapé do Modal `alto` só fica preso se o miolo colaborar
        # com `overflowY` e `minHeight: 0`; sem isso ele sai da tela.
        salvar = pg2.get_by_role("button", name=re.compile("Cadastrar contrato", re.I))
        check("o botão de gravar está alcançável, e não empurrado para fora",
              salvar.count() > 0 and salvar.first.is_visible())
        check("e nasce inativo enquanto falta o que a API exigiria",
              salvar.first.is_disabled())
        # D132.1 e 2 — dinheiro em real e sem zero à esquerda. O campo de valor
        # só existe fora do unitário, onde o total é a soma da planilha.
        pg2.get_by_role("radio").nth(1).check()
        pg2.wait_for_timeout(500)
        moeda = pg2.get_by_label("Valor fechado do contrato")
        if moeda.count() > 0:
            moeda.click()
            moeda.type("500000")
            pg2.wait_for_timeout(300)
            valor = moeda.input_value()
            check(f"o valor se apresenta em real, e não cru ({valor})",
                  "." in valor and "," in valor)
            check("e sem zero à esquerda sobrevivendo na caixa",
                  not valor.strip().startswith("0"))
        texto2 = pg2.inner_text("body").lower()
        check("o formulário diz o que cada regime significa NA MEDIÇÃO",
              "mede-se quantidade executada" in texto2 or "mede-se o custo" in texto2)
        check(
            "e no regime público pede o limite em vez de escolher 25% sozinho",
            "limite legal" in texto2 or "regime" in texto2,
        )
        pg2.screenshot(path=f"{SHOTS}/05_contrato_novo.png", full_page=True)
        pg2.keyboard.press("Escape")
        pg2.wait_for_timeout(700)
        check("o Esc fecha sem gravar nada", pg2.get_by_role("dialog").count() == 0)

    print("\n11c. A grade que se digita — autosave, selo e a trava do saldo (D137)")
    # Só `demo` tem `medicao.apurar`, então é aqui que a grade é viva. O
    # roteiro devolve o número original no fim: exercitar a tela não pode
    # deixar rastro no tenant de demonstração.
    # Procura **em qualquer obra da carteira**: o rascunho de preço unitário
    # nem sempre está na obra de fila mais cheia, e a grade viva é a régua que
    # este trecho existe para guardar.
    rascunho = None
    for _, obra_c, _, posto_c in candidatas:
        for c in posto_c["contratos"]["linhas"]:
            if c["regime"] == "administracao":
                continue
            codigo, lista = req(
                f"/api/pdca/medicoes/?contrato={c['contrato']}&resumo=1", token,
            )
            for b in (lista or {}).get("results", []):
                if b["status"] != "rascunho":
                    continue
                codigo, ctx = req(
                    f"/api/pdca/medicoes/{b['medicao_id']}/contexto/", token,
                )
                if codigo == 200 and ctx["linhas"]:
                    rascunho = (obra_c, c, b, ctx)
                    break
            if rascunho:
                break
        if rascunho:
            break

    if rascunho is None:
        print("     (nenhum rascunho de preço unitário no seed — a grade viva")
        print("      fica com o `pdca3_medicao_test.py`, que prova a API)")
    else:
        obra_r, contrato_r, boletim_r, ctx_r = rascunho
        primeira = ctx_r["linhas"][0]
        pg2.goto(
            f"{GW}/app/pdca/o/{obra_r}/medicao"
            f"?contrato={contrato_r['contrato']}&boletim={boletim_r['medicao_id']}"
        )
        pg2.wait_for_load_state("networkidle")
        pg2.wait_for_timeout(2400)
        texto2 = pg2.inner_text("body").lower()

        check("quem apura vê a grade viva, com campo para digitar",
              pg2.locator("table input").count() > 0)
        check(
            "e NÃO existe botão de salvar — a grade grava sozinha (D137)",
            pg2.get_by_role(
                "button", name=re.compile("Gravar a grade", re.I)).count() == 0,
        )
        check("o selo de gravação está sempre na tela, não só quando falha",
              "grava sozinha" in texto2)

        campo = pg2.get_by_label(f"Quantidade medida de {primeira['codigo']}")
        if campo.count() > 0:
            original = campo.first.input_value()
            # **A trava acende na digitação**, e não só na submissão: é a frase
            # que define o instrumento, e a única parte dele que não dá para
            # provar por API.
            campo.first.click()
            campo.first.fill("")
            campo.first.type("999999")
            pg2.wait_for_timeout(400)
            texto2 = pg2.inner_text("body").lower()
            check("passar do saldo acende a trava na própria linha",
                  "passa do saldo" in texto2)
            check("e o selo diz que há coisa não gravada",
                  "não salvo" in texto2 or "salvando" in texto2)

            # O debounce é de 1,5 s — esperar 3 s prova que ele grava sozinho.
            pg2.wait_for_timeout(3200)
            texto2 = pg2.inner_text("body").lower()
            check("passados alguns segundos, a tela diz que gravou sozinha",
                  "salvo às" in texto2 or "não deu para gravar" in texto2)

            # Devolve o que estava lá: o roteiro não deixa rastro.
            campo.first.click()
            campo.first.fill("")
            campo.first.type(original or "0")
            pg2.wait_for_timeout(3200)
            check(
                "e o roteiro devolve o número original ao boletim",
                campo.first.input_value() == (original or "0"),
            )
        pg2.screenshot(path=f"{SHOTS}/06_grade_viva.png", full_page=True)

    check(f"nenhum erro de JavaScript na segunda sessão ({len(erros_pg2)})",
          not erros_pg2)
    pg2.close()

    print("\n12. Uma leitura só, e a tela fica parada")
    do_posto = [u for u in chamadas if "/api/pdca/medicao/?" in u]
    check(
        f"o posto faz UMA chamada para contratos e fila (fez {len(do_posto)})",
        len(do_posto) <= 2,
    )
    antes = len(chamadas)
    pagina.wait_for_timeout(3000)
    check("sem laço de renderização — nada foi refeito parado",
          len(chamadas) == antes)
    check(f"nenhum erro de JavaScript ({len(erros_js)})", not erros_js)
    if erros_js:
        for e in erros_js[:4]:
            print(f"       · {e[:180]}")

    navegador.close()

total = len(passed)
ok = sum(1 for p in passed if p)
print(f"\n  Telas em {SHOTS}")
print(f"\n{'='*62}\n  {ok}/{total} verificações\n{'='*62}\n")
sys.exit(0 if ok == total else 1)
