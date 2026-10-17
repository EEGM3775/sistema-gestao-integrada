"""PDCA › CONTROLE, aba Semana — o quadro da semana no NAVEGADOR, pelo gateway (8090).

**Substitui o `pdca5_quadro_browser_test.py`** (D195): aquele dirigia
`/app/pdca/obra/{id}/programacao`, a tela apagada no redesenho de 20/09/2026. O
quadro mora hoje na aba *Semana* do Controle (`/app/pdca/o/{id}/controle?aba=semana`;
o endereço `/o/{id}/semana` ainda redireciona para lá), e este roteiro carrega a
régua do antigo — a parte que o `pdca_semana_campo_browser_test.py` não cobre,
porque aquele roda sobre a obra semeada da demo e não pode registrar trava,
encerrar nem reabrir a semana de verdade do dono. Aqui a obra é do teste.

O [pdca5_programacao_test.py](pdca5_programacao_test.py) prova a API. Este prova:

  1. o link antigo **ainda chega** ao quadro, e a semana não aberta se oferece
     para ser aberta, dizendo o que abrir significa;
  2. **a trava se registra na tela** e diz a consequência antes de gravar; o
     cartão travado **não se puxa** (sem botão), diz quantas travas pesam sobre
     ele e por quê — e continua assim depois do F5;
  3. **destravar pede como foi resolvida** (sem a nota, nada muda) e o cartão
     libera na hora, sem recarregar; a trava fica na esteira, riscada;
  4. o quadro montado **sobrevive ao F5**;
  5. o cartão mostra **quanto foi prometido e quanto o campo apontou** — e o que
     ninguém apontou é dito, nunca vira zero;
  6. **a tela é outra em cada estado**: assumida, some de onde puxar e some o
     devolver; o índice é "sem apuração", nunca 0%;
  7. o julgamento é pelo **% concluído** (decisão do dono, 09/10/2026): nenhum
     cartão nasce julgado, bater a meta não pede causa, ficar abaixo pede — do
     catálogo de fábrica — e o detalhe;
  8. encerrar devolve **1 de 2** com o peso dito, o ranking nomeia a causa, e
     tudo sobrevive ao F5;
  9. a semana **errada tem volta**: reabrir sem a razão não reabre; com ela, o
     selo de reaberta aparece, o índice volta a "sem apuração" e recalcula;
 10. a série do PPC **não fabrica tendência** com um ponto e marca a semana
     reaberta na legenda;
 11. e a tela fica **parada** — sem laço de renderização, sem erro de JS.

**O que o antigo cobrava e não veio, e por quê:**

- *o caminho Planejamento → cartão → "Programação da semana"* — a obra abre no
  posto do papel (`pdca_porta_por_papel_browser_test.py` cobre a porta);
- *botões "Saiu"/"Não saiu" sem pré-seleção* — o julgamento virou o % concluído;
  a régua (nenhum cartão nasce julgado) vem para o campo numérico, §7;
- *o botão de confirmar desligado sem a nota/razão* — a tela nova deixa clicar e
  o servidor recusa; a régua (nada muda sem a razão escrita) vem como recusa, §3 e §9;
- *tabela-gêmea da série, eixo 0–100 rotulado e legenda saiu/não saiu* — a série
  nova não tem nenhum dos três. Não é desenho declarado: é o **D295**
  ([pendencias.md](../../docs/pendencias.md)).

Rodar (stack de pé, imagens `erp` e `react` rebuildadas):

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/pdca_semana_quadro_browser_test.py
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
SHOTS = os.environ.get("SGI_SHOTS", "/tmp/sgi_semana_quadro")
MARCA = "E2E Quadro " + uuid.uuid4().hex[:6]
ALVENARIA = "Alvenaria do 4º pavimento"
CONTRAPISO = "Contrapiso do 3º pavimento"

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


def texto(pagina):
    return pagina.inner_text("body").lower()


def recarregar(pagina, espera=2200):
    pagina.reload()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(espera)


def puxar(pagina, nome):
    return pagina.get_by_role("button", name=f"Puxar {nome} para o quadro")


def concluido(pagina, nome):
    return pagina.get_by_label(f"Quanto de {nome} está concluído")


def encerrar_pela_tela(pagina, motivo):
    """Encerra pelo diálogo; devolve o texto do resultado (ou da página)."""
    pagina.get_by_role("button", name="Encerrar a semana", exact=True).click()
    pagina.wait_for_timeout(1000)
    dialogo = pagina.locator("div[role=dialog]")
    #: A semana corrente ainda não acabou: o servidor pede o motivo do
    #: fechamento antecipado, e a tela mostra o campo.
    if dialogo.locator("textarea").count():
        dialogo.locator("textarea").first.fill(motivo)
    dialogo.get_by_role("button", name="Encerrar", exact=True).click()
    pagina.wait_for_timeout(3000)
    dialogo = pagina.locator("div[role=dialog]")
    resultado = dialogo.inner_text().lower() if dialogo.count() else texto(pagina)
    if dialogo.count():
        dialogo.get_by_role("button", name="Fechar").last.click()
        pagina.wait_for_timeout(800)
    return resultado


print(f"\n{'='*62}\nPDCA › CONTROLE, Semana — o quadro no navegador\n{'='*62}")
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
    "data_inicio": segunda.isoformat(), "calendario": calendario["calendario_id"],
})
if status not in (200, 201):
    fatal(f"cronograma falhou ({status}: {crono})")
crono_id = crono["cronograma_id"]

atividade_id = {}
for codigo, nome in (("1", ALVENARIA), ("2", CONTRAPISO)):
    status, a = req("POST", "/api/pdca/atividades/", demo, {
        "cronograma": crono_id, "codigo": codigo, "nome": nome,
        "duracao_dias": 5, "peso_informado": "50",
    })
    if status not in (200, 201):
        fatal(f"atividade {codigo} falhou ({status}: {a})")
    atividade_id[nome] = a["atividade_id"]

status, _ = req("POST", f"/api/pdca/cronogramas/{crono_id}/publicar/", demo)
if status != 200:
    fatal(f"publicar falhou ({status})")
check("obra, calendário e plano vigente com duas folhas nesta semana", True)

# --- A tela -----------------------------------------------------------------
with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = navegador.new_context(viewport={"width": 1500, "height": 950})
    pagina = ctx.new_page()
    erros_js = []
    pagina.on("pageerror", lambda e: erros_js.append(str(e)))
    #: Tela parada não faz requisição — a prova de que não há laço de
    #: renderização, o defeito que travou a aba do dono em 15/09/2026.
    requisicoes = []
    pagina.on("request", lambda r: requisicoes.append(r.url) if "/api/" in r.url else None)

    print("\n1. Login, e o link antigo ainda chega ao quadro")
    pagina.goto(f"{GW}/login")
    pagina.wait_for_load_state("networkidle")
    pagina.fill("input#username", "demo")
    pagina.fill("input#password", "demo123")
    pagina.click("button[type=submit]")
    pagina.wait_for_url("**/app/**", timeout=20000)
    check("`demo` entrou", "/app" in pagina.url)

    pagina.goto(f"{GW}/app/pdca/o/{obra_id}/semana")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(2000)
    check("`/o/{id}/semana` leva à aba Semana do Controle",
          f"/o/{obra_id}/controle" in pagina.url and "aba=semana" in pagina.url)
    corpo = texto(pagina)
    check("o nome da obra está na moldura (não é 'Obra 123')", MARCA.lower() in corpo)

    print("\n2. A semana não aberta se OFERECE — não desenha um quadro vazio")
    check("a tela diz que a semana ainda não tem quadro", "ainda não tem quadro" in corpo)
    check("e explica o que abrir significa, antes de alguém clicar",
          "folha em branco" in corpo)
    abrir = pagina.get_by_role("button", name="Abrir o quadro desta semana")
    check("e oferece abrir o quadro", abrir.count() > 0)
    abrir.first.click()
    pagina.wait_for_timeout(2500)
    pagina.wait_for_load_state("networkidle")
    corpo = texto(pagina)
    check("o quadro nasce em RASCUNHO", "rascunho" in corpo)
    check("com o plano sugerindo de onde puxar", "o plano sugere" in corpo)
    check("e a esteira do que trava ao lado, dizendo que nada trava",
          "nenhum serviço está travado" in corpo)
    status, abertas = req(
        "GET", f"/api/pdca/programacoes/?obra={obra_id}&semana_inicio={segunda.isoformat()}",
        demo,
    )
    prog_id = ((abertas or {}).get("results") or [{}])[0].get("programacao_id")
    if prog_id is None:
        fatal("não achei a programação que a tela abriu")
    pagina.screenshot(path=f"{SHOTS}/01_rascunho.png", full_page=True)

    print("\n3. A trava se registra NA TELA, e trava o cartão")
    pagina.get_by_role("button", name="Registrar", exact=True).first.click()
    pagina.wait_for_timeout(900)
    dialogo = pagina.locator("div[role=dialog]")
    check("o diálogo de trava abre", dialogo.count() > 0)
    check("e diz a consequência antes de gravar",
          "não entra no quadro" in dialogo.inner_text().lower())
    dialogo.locator("select[size='6']").select_option(str(atividade_id[CONTRAPISO]))
    dialogo.locator("textarea").first.fill("Argamassa do contrapiso não entregue")
    dialogo.get_by_role("button", name="Registrar", exact=True).click()
    pagina.wait_for_timeout(2500)
    corpo = texto(pagina)
    check("a trava aparece na esteira, com o que ela trava",
          "argamassa do contrapiso não entregue" in corpo and CONTRAPISO.lower() in corpo)
    check("o cartão travado NÃO se puxa — não há botão para isso",
          puxar(pagina, CONTRAPISO).count() == 0)
    check("e diz quantas travas pesam sobre ele", "1 trava" in corpo)
    cartao_travado = pagina.locator("div[title*='não entra no quadro']")
    check("com a explicação no title, para quem passar o mouse",
          cartao_travado.count() > 0)
    check("o cartão sem trava, esse sim, se puxa", puxar(pagina, ALVENARIA).count() > 0)

    recarregar(pagina)
    check("depois do F5 o cartão continua travado",
          puxar(pagina, CONTRAPISO).count() == 0 and "1 trava" in texto(pagina))

    print("\n4. Puxar monta o quadro, e o quadro é do servidor")
    puxar(pagina, ALVENARIA).first.click()
    pagina.wait_for_timeout(2200)
    corpo = texto(pagina)
    check("o cartão entrou no quadro", "1 compromisso" in corpo)
    check("e o cartão do quadro pode ser devolvido ao plano",
          pagina.locator("button[title='Devolver ao plano']").count() > 0)
    recarregar(pagina)
    check("e sobrevive ao F5", "1 compromisso" in texto(pagina))

    print("\n5. Destravar pede COMO — e o cartão libera na hora")
    pagina.get_by_role("button", name="Destravar", exact=True).first.click()
    pagina.wait_for_timeout(900)
    dialogo = pagina.locator("div[role=dialog]")
    check("o diálogo pergunta como a trava foi resolvida",
          "como foi resolvida" in dialogo.inner_text().lower())
    dialogo.get_by_role("button", name="Destravar", exact=True).click()
    pagina.wait_for_timeout(1800)
    check("sem a nota, nada destrava: o diálogo segue aberto e o cartão segue travado",
          pagina.locator("div[role=dialog]").count() > 0
          and puxar(pagina, CONTRAPISO).count() == 0)
    dialogo.locator("textarea").first.fill("Argamassa entregue hoje, conferida pelo almoxarife")
    antes = len(requisicoes)
    dialogo.get_by_role("button", name="Destravar", exact=True).click()
    pagina.wait_for_timeout(2500)
    check("com a nota, o cartão libera NA HORA, sem recarregar",
          puxar(pagina, CONTRAPISO).count() > 0 and len(requisicoes) > antes)
    check("e a trava fica na esteira, riscada, com o caminho de volta",
          "destravadas (1)" in texto(pagina))
    puxar(pagina, CONTRAPISO).first.click()
    pagina.wait_for_timeout(2200)
    check("e entra no quadro — são dois compromissos agora",
          "2 compromissos" in texto(pagina))

    print("\n6. Prometido × apontado — o compromisso é binário; a execução não é")
    #: O quadro é montado por clique (sem percentual): o cenário põe o prometido
    #: e o apontado por API, e o que se prova é que a TELA os mostra.
    status, itens_api = req("GET", f"/api/pdca/itens-programacao/?programacao={prog_id}", demo)
    cartoes = {c["atividade_nome"]: c for c in (itens_api or {}).get("results", [])}
    if set(cartoes) != {ALVENARIA, CONTRAPISO}:
        fatal(f"o quadro tem {sorted(cartoes)}, e não os dois cartões")
    req("PATCH", f"/api/pdca/itens-programacao/{cartoes[CONTRAPISO]['item_programacao_id']}/",
        demo, {"percentual_previsto": "20"})
    req("PATCH", f"/api/pdca/itens-programacao/{cartoes[ALVENARIA]['item_programacao_id']}/",
        demo, {"percentual_previsto": "15"})
    status, _ = req("POST", "/api/pdca/apontamentos/", demo, {
        "atividade": atividade_id[CONTRAPISO], "data": segunda.isoformat(), "percentual": "12",
    })
    recarregar(pagina)
    corpo = texto(pagina)
    check("o cartão mostra quanto a equipe PROMETEU", "prometeu 20" in corpo)
    check("e quanto o campo APONTOU", "apontou 12" in corpo)
    check("o que prometeu e ninguém apontou DIZ isso, em vez de fabricar um zero",
          "ninguém apontou" in corpo)
    pagina.screenshot(path=f"{SHOTS}/02_quadro_montado.png", full_page=True)

    print("\n7. Assumir muda a tela — não é o mesmo layout com botão desligado")
    assumir = pagina.get_by_role("button", name="A equipe assume")
    check("o rascunho oferece assumir", assumir.count() > 0)
    check("e avisa que depois disso o quadro não recebe cartão novo",
          "não recebe cartão novo" in (assumir.first.get_attribute("title") or ""))
    assumir.first.click()
    pagina.wait_for_timeout(2500)
    corpo = texto(pagina)
    check("a semana passa a COMPROMETIDA", "comprometida" in corpo)
    check("de onde se puxava SOME — não teria mais função",
          puxar(pagina, ALVENARIA).count() == 0 and "o plano sugere" not in corpo)
    check("e o devolver some junto: compromisso assumido se julga, não se apaga",
          pagina.locator("button[title='Devolver ao plano']").count() == 0)
    check("o índice é 'sem apuração', nunca 0%", "sem apuração" in corpo)

    print("\n8. Julgar pelo % concluído")
    pagina.get_by_role("button", name="Julgar o quadro").click()
    pagina.wait_for_timeout(1000)
    campos = [concluido(pagina, ALVENARIA), concluido(pagina, CONTRAPISO)]
    check("cada cartão pergunta quanto está concluído, no lugar onde está",
          all(c.count() == 1 for c in campos))
    check("e NENHUM nasce julgado — um padrão faria o quadro inteiro 'sair' sem ninguém olhar",
          all(c.input_value() == "" for c in campos)
          and "bateu a meta" not in texto(pagina) and "abaixo da meta" not in texto(pagina))

    status, itens_api = req("GET", f"/api/pdca/itens-programacao/?programacao={prog_id}", demo)
    cartoes = {c["atividade_nome"]: c for c in (itens_api or {}).get("results", [])}
    meta = float(cartoes[CONTRAPISO]["meta_da_semana"] or 100)
    atual = float(cartoes[CONTRAPISO]["avanco_atual"] or 0)
    if atual >= meta:
        fatal(f"o contrapiso já bateu a meta ({atual} ≥ {meta}) — o cenário não serve")

    campos[0].fill("100")
    pagina.wait_for_timeout(500)
    causa = pagina.locator("select").filter(has_text="Por que não saiu?")
    check("bater a meta diz 'saiu' e NÃO pede causa",
          "bateu a meta · saiu" in texto(pagina) and causa.count() == 0)
    campos[1].fill(f"{atual:g}".replace(".", ","))
    pagina.wait_for_timeout(500)
    check("ficar abaixo da meta diz 'não saiu' e pede a causa ali mesmo",
          "abaixo da meta · não saiu" in texto(pagina) and causa.count() == 1)
    opcoes = causa.first.locator("option").all_text_contents()
    check("com o catálogo de fábrica na lista, sem ninguém cadastrar nada",
          len(opcoes) > 5)
    check("e o campo do detalhe, de onde sai a ação",
          pagina.get_by_placeholder("Qual material? Que projeto?").count() == 1)
    causa.first.select_option(index=1)
    causa_escolhida = opcoes[1].split("·", 1)[-1].strip()
    pagina.get_by_placeholder("Qual material? Que projeto?").fill("argamassa colante")
    pagina.wait_for_timeout(400)

    print("\n9. Encerrar — o índice aparece, com o denominador e o peso")
    resultado = encerrar_pela_tela(pagina, "E2E — exercício do encerramento pela tela.")
    check("encerrar devolve o índice na hora", "%" in resultado)
    check("e diz em cima de que peso o índice foi feito",
          "peso por" in resultado or "fora da divisão" in resultado)
    corpo = texto(pagina)
    check("a semana fica ENCERRADA, e a tela não some", "encerrada" in corpo)
    check("o cumprimento é 50% — um de dois, de pesos iguais", "cumprimento 50" in corpo)
    check("o cartão que não saiu mostra a causa", causa_escolhida.lower() in corpo)
    status, itens_api = req("GET", f"/api/pdca/itens-programacao/?programacao={prog_id}", demo)
    gravado = next(c for c in itens_api["results"] if c["atividade_nome"] == CONTRAPISO)
    check("e o detalhe que a reunião escreveu foi gravado", gravado["nota"] == "argamassa colante")
    recarregar(pagina)
    corpo = texto(pagina)
    check("o índice e a causa sobrevivem ao F5",
          "cumprimento 50" in corpo and causa_escolhida.lower() in corpo)
    pagina.screenshot(path=f"{SHOTS}/03_encerrada.png", full_page=True)

    print("\n10. Desempenho — o índice com o denominador, e a causa no ranking")
    pagina.get_by_role("button", name="Desempenho").click()
    pagina.wait_for_timeout(2000)
    corpo = texto(pagina)
    check("o índice vem com o denominador ao lado, não sozinho", "1 de 2 compromissos" in corpo)
    check("o ranking nomeia o que segurou a obra",
          "por que os compromissos não saem" in corpo and causa_escolhida.lower() in corpo)
    check("com UMA semana encerrada, a tela não desenha média — um ponto não é tendência",
          "média de" not in corpo)
    barras = pagina.locator("svg[role='img'] rect[fill='var(--danger)']")
    check("nenhuma barra é pintada de vermelho por faixa de desempenho — a meta é do dono",
          barras.count() == 0)

    print("\n11. A semana errada tem volta — com a razão escrita")
    pagina.get_by_role("button", name="Quadro", exact=True).click()
    pagina.wait_for_timeout(1200)
    pagina.get_by_role("button", name="Reabrir", exact=True).first.click()
    pagina.wait_for_timeout(900)
    dialogo = pagina.locator("div[role=dialog]")
    aviso = dialogo.inner_text().lower()
    check("o diálogo diz o que vai acontecer ANTES de confirmar",
          "deixa de valer" in aviso)
    check("e que a reabertura fica marcada na série", "marcada na série" in aviso)
    dialogo.get_by_role("button", name="Reabrir", exact=True).click()
    pagina.wait_for_timeout(1800)
    check("sem a razão, nada reabre: o servidor recusa e a semana segue encerrada",
          pagina.locator("div[role=dialog] [role=alert]").count() > 0
          and req("GET", f"/api/pdca/programacoes/{prog_id}/", demo)[1]["status"] == "encerrada")
    dialogo.locator("textarea").first.fill("O contrapiso foi concluído na sexta e ninguém avisou")
    dialogo.get_by_role("button", name="Reabrir", exact=True).click()
    pagina.wait_for_timeout(2500)
    corpo = texto(pagina)
    check("com a razão, a semana volta a COMPROMETIDA", "comprometida" in corpo)
    selo = pagina.locator("[title='O contrapiso foi concluído na sexta e ninguém avisou']")
    check("e o selo de reaberta aparece, com a razão ao lado",
          "reaberta 1×" in corpo and selo.count() > 0)
    check("o índice volta a 'sem apuração' — em revisão não é conclusão de nada",
          "sem apuração" in corpo)

    pagina.get_by_role("button", name="Julgar o quadro").click()
    pagina.wait_for_timeout(1000)
    concluido(pagina, CONTRAPISO).fill("100")
    pagina.wait_for_timeout(500)
    encerrar_pela_tela(pagina, "E2E — reencerrada depois da correção.")
    corpo = texto(pagina)
    check("o índice RECALCULA: 100%, os dois saíram", "cumprimento 100" in corpo)
    check("e a marca de que a semana foi corrigida CONTINUA lá", "reaberta 1×" in corpo)

    print("\n12. A série marca a semana reaberta")
    pagina.get_by_role("button", name="Desempenho").click()
    pagina.wait_for_timeout(2000)
    corpo = texto(pagina)
    check("o índice da série é o recalculado", "2 de 2 compromissos" in corpo)
    check("e a legenda explica a marca da semana reaberta",
          "semana reaberta" in corpo)
    #: D295 — o que o redesenho tinha perdido e voltou.
    check("a legenda nomeia as DUAS partes da coluna — identidade não depende só da cor",
          "saiu" in corpo and "não saiu" in corpo)
    check("o eixo traz a régua escrita, de 0 a 100, para o valor ser LIDO",
          "100%" in corpo and "50%" in corpo and "0%" in corpo)
    pagina.screenshot(path=f"{SHOTS}/04_serie.png", full_page=True)
    ver_tabela = pagina.get_by_role("button", name="Ver tabela")
    check("o painel oferece ver os mesmos números em tabela", ver_tabela.count() == 1)
    ver_tabela.click()
    pagina.wait_for_timeout(600)
    tabela = pagina.locator("table")
    cabecalho = tabela.locator("thead").inner_text().lower() if tabela.count() else ""
    check("a tabela traz semana, cumprimento, saíram e assumidos",
          all(c in cabecalho for c in ("semana", "cumprimento", "saíram", "assumidos")))
    linha = tabela.locator("tbody tr").first.inner_text().lower() if tabela.count() else ""
    check("com o denominador em coluna própria e a reabertura dita por escrito",
          "100%" in linha and "2" in linha and "reaberta 1×" in linha)
    pagina.get_by_role("button", name="Ver gráfico").click()
    pagina.wait_for_timeout(400)

    print("\n13. Com a tela parada não pode haver requisição")
    pagina.wait_for_load_state("networkidle")
    parado = len(requisicoes)
    pagina.wait_for_timeout(4000)
    check("nenhuma requisição com a tela em repouso (sem laço de renderização)",
          len(requisicoes) - parado == 0)
    check("nenhum erro de JavaScript na página", not erros_js)
    if erros_js:
        print("     erros:", erros_js[:3])

    navegador.close()

# --- Faxina -----------------------------------------------------------------
print("\n14. Faxina")
status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
check("a obra do teste sai (vai para a lixeira, que é o desenho)",
      status in (200, 204))
print(
    "\n     A semana encerrada e os compromissos julgados ficam — documento com\n"
    "     decisão registrada não se apaga. Para devolver o ambiente ao estado\n"
    "     anterior:\n"
    "       docker exec sgi-erp python manage.py limpar_residuo_e2e --confirmar"
)

ok = sum(1 for p in passed if p)
print(f"\n{'='*62}\nPDCA › Semana, o quadro (tela): {ok}/{len(passed)} verificações\n{'='*62}")
sys.exit(0 if ok == len(passed) else 1)
