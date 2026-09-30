"""ORC.10 — a planilha editável no NAVEGADOR, pelo gateway (8090).

Existe pela régua do [README](README.md) §"Teste de API não substitui teste de
navegador": **tela reescrita entrega com teste de navegador junto**. A ORC.10
reescreveu a grade do Orçar — seleção múltipla, arrastar, barra de lote,
desfazer, composição editável e o banco acoplado —, e a suíte do Django
(`test_edicao.py`, 68 testes) prova os verbos, não o caminho de dedo até eles.

O que só existe aqui:

  1. o caminho: Orçamento → Orçar → obra → planilha, e a grade desenhando;
  2. **a barra de lote não existe sem seleção** — ela aparece com o primeiro
     clique e some quando a seleção é limpa. Uma barra permanente de botões
     cinzas ocuparia altura da grade o tempo todo para dizer "não dá", e é a
     grade que é o módulo;
  3. **desfazer nasce desabilitado** e acende depois da primeira edição — o
     botão que promete o que não pode cumprir é pior que a ausência dele;
  4. **Ctrl+Z devolve o valor à célula**, na tela, sem F5. É a prova de que a
     pilha de `historico.ts` está ligada no caminho real e não só nos testes;
  4b. **o escopo da seleção é honesto**: marcar a etapa acende as filhas como
      "vão junto", a barra conta as duas coisas separadamente, e o diálogo de
      excluir nomeia o que sai e quanto dinheiro vai com ele — antes, marcar
      uma etapa dizia "1 linha" e sumiam três, sem perguntar nada;
  4c. **marcar tudo respeita o filtro** — com "placa" digitado, o cabeçalho
      marca a linha do filtro, não a planilha inteira. O caminho contrário é o
      que faz alguém apagar quatrocentas linhas achando que apagava três;
  5. o **banco acoplado** abre ao lado da grade e lista a publicação;
  6. em analítico a composição abre e tem **por onde somar insumo** — o gesto
     que a ORC.10c existe para permitir;
  7. e a tela fica **parada**: sem laço de renderização e sem erro de JS, que
     foram os dois defeitos que nenhum teste de API pegou em 15/09/2026;
  7b. **as ações da linha são ícones, não três pontos**, e cada uma é um clique
      só — memória de cálculo, memória do quantitativo, duplicar e excluir
      aparecem ao passar o mouse; a chave inglesa guarda o resto;
  8. o **assistente** que o dono pediu: ligado, o cartão diz o que fazer e
     explica o botão de três pontos; a tecla `?` abre a lista inteira de gestos;
     e a chave na barra de cima desliga tudo — a régua é a do velho assistente
     do Office, aparece quando se quer e some quando não se quer.

Rodar (stack de pé, imagem `react` rebuildada):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/orc10_planilha_browser_test.py

**Sobre o `LD_LIBRARY_PATH`:** o Chromium do Playwright pede bibliotecas que o
WSL não traz, e instalá-las mexeria na máquina do dono — a saída já usada pelos
roteiros do PDCA é extraí-las de uma imagem `ubuntu:24.04` para uma pasta do
usuário.
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
import uuid

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright
from _sessao import cabecalhos, da_resposta

GW = os.environ.get("SGI_GW", "http://localhost:8090")
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_orc10")
MARCA = "E2E ORC.10 " + uuid.uuid4().hex[:6]

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def texto_da(pagina):
    """O texto da tela em caixa baixa.

    `inner_text` devolve o texto **renderizado**, e o kit do módulo marca rótulo
    de seção com `textTransform: uppercase` (o `CAPS` de `ui.tsx`). Comparar
    contra a string do código-fonte falha por caixa, não por defeito — e um
    roteiro que grita errado é desligado na terceira vez.
    """
    return pagina.inner_text("body").lower()


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


print(f"\n{'='*62}\nORC.10 — a planilha editável no navegador\n{'='*62}")
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

status, orc = req("POST", "/api/orcamento/orcamentos/", demo, {
    "obra": obra_id, "descricao": "Planilha " + MARCA,
    "bdi_percentual": "20.00", "encargos_sociais_percentual": "80.00",
})
if status not in (200, 201):
    fatal(f"orçamento falhou ({status}: {orc})")
orc_id = orc["orcamento_id"]

status, etapa = req("POST", "/api/orcamento/itens/", demo, {
    "orcamento": orc_id, "tipo_linha": "sintetico", "descricao": "Serviços preliminares",
    "ordem": 0,
})
if status not in (200, 201):
    fatal(f"etapa falhou ({status}: {etapa})")

linhas = []
for n, (desc, qtd, custo) in enumerate([
    ("Tapume de chapa compensada", "10", "50.00"),
    ("Placa de obra", "1", "800.00"),
]):
    status, linha = req("POST", "/api/orcamento/itens/", demo, {
        "orcamento": orc_id, "pai": etapa["item_orcado_id"], "tipo_linha": "analitico",
        "descricao": desc, "unidade": "M2", "quantidade": qtd, "custo_unitario": custo,
        "ordem": n,
    })
    if status not in (200, 201):
        fatal(f"linha {desc} falhou ({status}: {linha})")
    linhas.append(linha)

# Uma composição para o analítico ter o que abrir (ORC.10c).
status, insumo = req("POST", "/api/orcamento/insumos/", demo, {
    "item_orcado": linhas[0]["item_orcado_id"], "descricao": "Chapa compensada 12mm",
    "unidade": "M2", "categoria": "material", "coeficiente": "1.05", "custo_unitario": "40.00",
})
if status not in (200, 201):
    fatal(f"insumo falhou ({status}: {insumo}) — a rota da ORC.10c está no ar?")
check("obra, planilha com uma etapa, dois serviços e uma composição", True)

# --- A tela -----------------------------------------------------------------
with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = navegador.new_context(viewport={"width": 1600, "height": 900})
    pagina = ctx.new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))
    requisicoes = []
    pagina.on("request", lambda r: requisicoes.append(r.url) if "/api/" in r.url else None)

    print("\n1. Login e caminho até a planilha")
    pagina.goto(f"{GW}/login")
    pagina.wait_for_load_state("networkidle")
    pagina.fill("input#username", "demo")
    pagina.fill("input#password", "demo123")
    pagina.click("button[type=submit]")
    pagina.wait_for_url("**/app/**", timeout=30_000)
    check("login pela tela", "/app" in pagina.url)

    pagina.goto(f"{GW}/app/orcamento/orcar/orcamento/{orc_id}")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1200)
    pagina.screenshot(path=f"{SHOTS}/01_planilha.png")

    corpo = texto_da(pagina)
    check("a planilha abre com as linhas criadas", "tapume de chapa compensada" in corpo)
    check("o rodapé fecha o total", "total do orçamento" in corpo)

    print("\n2. A barra de lote não existe sem seleção")
    check("sem seleção, a barra de lote não está na tela",
          "linha(s) selecionada(s)" not in texto_da(pagina))

    print("\n3. Selecionar faz a barra aparecer, com os verbos de estrutura")
    caixa = pagina.locator("input[aria-label='Selecionar Tapume de chapa compensada']")
    check("a linha tem caixa de seleção", caixa.count() == 1)
    caixa.first.click()
    pagina.wait_for_timeout(400)

    corpo = texto_da(pagina)
    check("a barra aparece e conta a seleção", "1 linha(s) selecionada(s)" in corpo)
    check("indentar está ao alcance", pagina.locator("[title*='Indentar']").count() >= 1)
    check("desindentar está ao alcance", pagina.locator("[title*='Desindentar']").count() >= 1)
    check("duplicar está ao alcance", "duplicar" in corpo)
    check("o percentual de lote está ao alcance", pagina.locator("input[title*='Percentual']").count() >= 1)
    pagina.screenshot(path=f"{SHOTS}/02_barra_de_lote.png")

    print("\n4. Limpar a seleção some com a barra")
    pagina.locator("[title='Limpar seleção']").first.click()
    pagina.wait_for_timeout(400)
    check("sem seleção de novo, a barra sai da tela",
          "linha(s) selecionada(s)" not in texto_da(pagina))


    print("\n4b. O escopo da seleção é honesto")
    caixa_etapa = pagina.locator("input[aria-label='Selecionar Serviços preliminares']")
    caixa_etapa.first.click()
    pagina.wait_for_timeout(500)
    corpo = texto_da(pagina)
    check("marcar a etapa conta as filhas que vão junto", "2 vão junto" in corpo)
    check("a linha filha se anuncia como já incluída",
          pagina.locator("input[title*='já vai junto']").count() >= 1)
    pagina.screenshot(path=f"{SHOTS}/07_escopo.png")

    print("\n4c. Excluir pergunta, e diz o que sai")
    pagina.get_by_role("button", name="Excluir").first.click()
    pagina.wait_for_timeout(700)
    corpo = texto_da(pagina)
    check("o diálogo aparece antes de apagar", "excluir 3 linhas?" in corpo)
    check("ele avisa que as filhas vão junto", "2 linha(s) vão junto" in corpo)
    check("ele nomeia o que foi marcado", "serviços preliminares" in corpo)
    check("e diz quanto sai do total", "sai do total" in corpo)
    pagina.screenshot(path=f"{SHOTS}/08_confirmar_exclusao.png")

    pagina.get_by_role("button", name="Cancelar").first.click()
    pagina.wait_for_timeout(600)
    corpo = texto_da(pagina)
    check("cancelar não apagou nada", "tapume de chapa compensada" in corpo)

    print("\n4d. Marcar tudo respeita o filtro")
    pagina.fill("input[placeholder='Filtrar linhas']", "placa")
    pagina.wait_for_timeout(700)
    pagina.locator("input[aria-label='Marcar tudo o que está à vista']").first.click()
    pagina.wait_for_timeout(500)
    corpo = texto_da(pagina)
    check("marca só a linha do filtro, não a planilha inteira",
          "1 linha(s) selecionada(s)" in corpo)
    pagina.fill("input[placeholder='Filtrar linhas']", "")
    pagina.wait_for_timeout(600)
    pagina.locator("[title='Limpar seleção']").first.click()
    pagina.wait_for_timeout(400)

    print("\n5. Desfazer nasce desabilitado e acende com a primeira edição")
    botao_desfazer = pagina.locator("[title*='Nada a desfazer']")
    check("desfazer começa desabilitado e diz por quê", botao_desfazer.count() >= 1)

    # Edita a quantidade do tapume: 10 -> 25. Duplo clique abre a célula.
    celula = pagina.locator("div.orc-cel", has_text="10,00").first
    celula.dblclick()
    pagina.wait_for_timeout(300)
    pagina.keyboard.press("Control+a")
    pagina.keyboard.type("25")
    pagina.keyboard.press("Enter")
    pagina.wait_for_timeout(1200)

    corpo = texto_da(pagina)
    check("a quantidade digitada aparece na grade", "25,00" in corpo)
    check("desfazer acendeu depois da edição",
          pagina.locator("[title*='Desfazer: editar']").count() >= 1)
    pagina.screenshot(path=f"{SHOTS}/03_editado.png")

    print("\n6. Ctrl+Z devolve o valor — na tela, sem F5")
    pagina.keyboard.press("Control+z")
    pagina.wait_for_timeout(1500)
    corpo = texto_da(pagina)
    check("o valor anterior voltou à célula", "10,00" in corpo)
    check("o aviso diz o que foi desfeito", "desfeito" in corpo)
    pagina.screenshot(path=f"{SHOTS}/04_desfeito.png")

    print("\n7. O banco de preço abre ao lado da grade")
    pagina.locator("[title*='Banco de preço ao lado']").first.click()
    pagina.wait_for_timeout(1500)
    corpo = texto_da(pagina)
    check("o painel abre com o próprio título", "banco de preço" in corpo)
    check("e explica o gesto de arrastar", "arraste um item para a planilha" in corpo)
    pagina.screenshot(path=f"{SHOTS}/05_banco_acoplado.png")
    pagina.locator("[title='Fechar o painel']").first.click()
    pagina.wait_for_timeout(500)

    print("\n8. Analítico abre a composição, e ela tem por onde crescer")
    pagina.get_by_text("Analítico", exact=True).first.click()
    pagina.wait_for_timeout(1800)
    corpo = texto_da(pagina)
    check("a composição da linha aparece", "chapa compensada 12mm" in corpo)
    check("há por onde somar insumo (ORC.10c)", "somar insumo" in corpo)
    check("e por onde tirar o que está lá",
          pagina.locator("[aria-label*='Tirar Chapa compensada']").count() >= 1)
    pagina.screenshot(path=f"{SHOTS}/06_composicao.png")


    print("\n8a. As ações da linha são ícones de um clique, não três pontos")
    linha = pagina.locator("div.orc-linha").filter(has_text="Placa de obra").first

    def passar_o_mouse():
        """Move o ponteiro para o meio da linha, por coordenada.

        O `.hover()` do Playwright exige que o **elemento alvo** receba o
        ponteiro e desiste quando um filho está por cima — e numa célula de
        grade sempre está. Mover o mouse para o ponto é o que a pessoa faz de
        verdade, e o `:hover` da linha acende do mesmo jeito; de quebra, o
        roteiro passa a provar o gesto real em vez da abstração da ferramenta.
        """
        caixa = linha.bounding_box()
        assert caixa, "a linha da Placa de obra não está na tela"
        pagina.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)
        pagina.wait_for_timeout(400)

    passar_o_mouse()

    memoria = pagina.locator("[aria-label='Memória de cálculo de Placa de obra']")
    regua = pagina.locator("[aria-label='Memória do quantitativo de Placa de obra']")
    copia = pagina.locator("[aria-label='Duplicar Placa de obra']")
    lixo = pagina.locator("[aria-label='Excluir Placa de obra']")
    chave = pagina.locator("[aria-label*='Mais ações da linha']")
    check("a linha tem o ícone da memória de cálculo", memoria.count() == 1)
    check("e o da memória do quantitativo", regua.count() == 1)
    check("e o de duplicar", copia.count() == 1)
    check("e o de excluir", lixo.count() == 1)
    check("e a chave inglesa para o resto (nenhum ⋮)", chave.count() >= 1)
    pagina.screenshot(path=f"{SHOTS}/11_acoes_da_linha.png")

    # **Um clique**, e não dois: o drawer da memória abre direto, sem menu no
    # meio. Era esta a reclamação — o ⋮ cobrava um clique só para revelar.
    memoria.first.click()
    pagina.wait_for_timeout(1200)
    corpo = texto_da(pagina)
    check("um clique no ícone abre a memória de cálculo, sem menu no meio",
          "memória de cálculo" in corpo)
    pagina.keyboard.press("Escape")
    pagina.wait_for_timeout(600)

    # A lixeira da linha também pergunta antes — o mesmo caminho do lote.
    passar_o_mouse()
    lixo.first.click()
    pagina.wait_for_timeout(700)
    check("a lixeira da linha pergunta antes de apagar",
          "excluir esta linha?" in texto_da(pagina))
    pagina.get_by_role("button", name="Cancelar").first.click()
    pagina.wait_for_timeout(500)

    print("\n8b. O assistente ensina, e a tecla ? abre a lista inteira")
    corpo = texto_da(pagina)
    check("o cartão do assistente aparece ligado por padrão", "planilha orçamentária" in corpo)
    # A primeira dica mudou de assunto junto com a tela: antes explicava o que
    # havia atrás do `⋮`, agora conta que os verbos estão na própria linha —
    # porque a pergunta deixou de ser "o que é isso" e virou "onde ficam".
    check("e a primeira dica diz onde estão as ações da linha",
          "os ícones das ações aparecem" in corpo)
    pagina.screenshot(path=f"{SHOTS}/09_assistente.png")

    # A tecla `?` não pode disparar de dentro de um campo de texto — lá ela é só
    # um caractere. O roteiro tira o foco antes de apertar.
    pagina.keyboard.press("Escape")
    pagina.mouse.click(900, 500)
    pagina.keyboard.press("?")
    pagina.wait_for_timeout(700)
    corpo = texto_da(pagina)
    check("a tecla ? abre a referência da tela", "o que dá para fazer" in corpo)
    check("ela tem a seção de escolher linhas", "escolher linhas" in corpo)
    check("ela tem a seção de organizar a eap", "organizar a eap" in corpo)
    check("e explica o menu da linha", "salvar composição no banco" in corpo)
    pagina.screenshot(path=f"{SHOTS}/10_painel_ajuda.png")

    pagina.keyboard.press("Escape")
    pagina.wait_for_timeout(500)
    check("Esc fecha o painel", "o que dá para fazer" not in texto_da(pagina))

    print("\n8c. A chave da barra de cima desliga o assistente")
    pagina.locator("[aria-label='Desligar o assistente']").first.click()
    pagina.wait_for_timeout(600)
    check("desligado, o cartão some",
          "planilha orçamentária" not in texto_da(pagina))
    pagina.locator("[aria-label='Ligar o assistente']").first.click()
    pagina.wait_for_timeout(600)
    check("e volta quando se liga de novo", "planilha orçamentária" in texto_da(pagina))

    print("\n9. A tela fica parada")
    requisicoes.clear()
    pagina.wait_for_timeout(4000)
    check(f"nenhuma requisição com a tela parada (foram {len(requisicoes)})",
          len(requisicoes) == 0)
    check(f"nenhum erro de JS (foram {len(erros_js)}): {erros_js[:2]}", not erros_js)

    navegador.close()

# --- Faxina -----------------------------------------------------------------
#
# **A obra também sai.** Apagar só a planilha deixava uma obra por corrida no
# tenant, e o plano `profissional` vende 40: na nona execução o roteiro morria
# em 402 (cota estourada) — falha que parece do produto e é do próprio teste,
# o pior tipo. A ordem importa: a FK da obra é `PROTECT`, então a planilha sai
# primeiro.
print("\n10. Faxina — o roteiro apaga o que criou")
status, _ = req("DELETE", f"/api/orcamento/orcamentos/{orc_id}/", demo)
check(f"planilha removida ({status})", status in (204, 200, 404, 409))
status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
check(f"obra removida ({status})", status in (204, 200, 404))

total = len(passed)
ok = sum(1 for x in passed if x)
print(f"\n{'='*62}\nORC.10 navegador: {ok}/{total} checks")
print(f"Telas em {SHOTS}")
sys.exit(0 if ok == total else 1)
