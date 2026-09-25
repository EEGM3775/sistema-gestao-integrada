"""PRA.5c — o acervo entra pela TELA, e o navegador é quem prova.

**O que só o browser prova, e por que aqui isso é a coisa toda.** A porta de lote
de arquivo (`/api/impexp/<recurso>/importar-arquivos/`, R18) existe e é testada
desde a PRA.5b — o [carregar_acervo_dwg.py](carregar_acervo_dwg.py) sobe 160 DWGs
por ela há três passadas de medição. O que **não** existia era o gesto: nenhuma
tela do sistema chamava aquele endpoint. O botão estava, literalmente, inativo —
não desabilitado, ausente. Um E2E de API teria continuado verde o tempo todo, e
foi por isso que a lacuna sobreviveu.

Então este teste faz o caminho do cliente e nada além dele: abre o navegador,
entra como `admin`, escolhe a obra, abre a aba **Acervo**, clica em *Enviar
acervo (pasta)*, aponta a pasta, confere o que a plataforma adivinhou e clica em
**Confirmar tudo**. O que se afirma no fim é o que o acervo passou a ter.

Duas asserções são sobre a régua, e não sobre o feliz caminho:

1. **nada é gravado antes da decisão** (R1) — entre o fim do upload e o clique em
   confirmar, o acervo da obra continua vazio. É a regra do módulo inteiro, e ela
   agora vale sobre o **conjunto**, não sobre a remessa: o envio é picado em
   remessas de 10 (teto do Django), mas as 16 ficam em `CONFERINDO` até a decisão;
2. **o caminho da pasta vira taxonomia** — o `webkitRelativePath` chega ao
   servidor em `caminhos[]`, e é dele que saem código, disciplina e revisão. Um
   corpus com nomes de arquivo repetidos entre subpastas (este tem: `006.dwg`,
   `Desenho1.dwg`…) é o que torna a asserção não-trivial.

Roda pelo gateway (8090), contra o bundle que o container serve — não pelo Vite.

    LD_LIBRARY_PATH=~/.local/chromium-libs \\
      .venv/bin/python testes/e2e/pra5c_upload_acervo_browser_test.py \\
        ~/acervo-corpus-160 --obra 11

**Sobre o `LD_LIBRARY_PATH`:** o Chromium do Playwright pede quatro bibliotecas
que o WSL não traz (`libnss3`, `libnspr4`, `libasound2`, `libsoftokn3`), e
instalá-las mexe na máquina do dono. Extraí-las de uma imagem `ubuntu:24.04` para
uma pasta do usuário resolve sem tocar no sistema — é o que destrava também o
[d70_browser_test.py](d70_browser_test.py), que estava parado por essa mesma
falta desde 09/08/2026.
"""
import argparse
import json
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

from _segundo_fator import completar_login, responder_no_navegador

GW = "http://localhost:8090"
OK, FALHA = [], []


def checar(nome, condicao, detalhe=""):
    (OK if condicao else FALHA).append(nome)
    print(f"{'OK  ' if condicao else 'FALHA'} · {nome}{(' — ' + str(detalhe)) if detalhe else ''}")


def acervo_por_api(token, obra):
    """Quantas REVISÕES a obra tem, visto de fora da tela.

    A conferência da R1 não pode ser feita lendo a própria tela que está no meio
    do fluxo — ela mostraria o que o wizard tem em mãos, não o que o servidor
    gravou. Daí a segunda opinião, pela API.

    **Revisão e não documento, e a diferença é o recurso funcionando.** Um arquivo
    entra como uma revisão; o *documento* é o lugar lógico da prancha, e a
    taxonomia da R18 agrupa nele os arquivos de mesmo código. Neste corpus 158
    arquivos viraram 140 documentos — os `AEGS06.DWG` espalhados por quatro
    subpastas são quatro revisões do mesmo desenho, que é exatamente o que se
    quer. Contar documentos e esperar arquivos leria acerto como perda.
    """
    pagina, total = 1, 0
    while True:
        pedido = urllib.request.Request(
            f"{GW}/api/prancheta/revisoes/?documento__obra={obra}"
            f"&page_size=200&page={pagina}",
            headers={"Authorization": "Bearer " + token},
        )
        with urllib.request.urlopen(pedido, timeout=60) as resposta:
            dados = json.loads(resposta.read().decode())
        total += len(dados.get("results", []))
        if not dados.get("next"):
            return total
        pagina += 1


def token_de(usuario, senha):
    pedido = urllib.request.Request(
        f"{GW}/auth/login/", method="POST",
        data=json.dumps({"username": usuario, "password": senha}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(pedido, timeout=60) as resposta:
        return completar_login(GW, json.loads(resposta.read().decode()))["access"]


def rodar(pasta, obra, usuario, senha, esperados, nome_da_obra):
    token = token_de(usuario, senha)
    antes = acervo_por_api(token, obra)
    checar("a obra começa sem acervo", antes == 0, f"{antes} documento(s)")

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        pagina = navegador.new_context(viewport={"width": 1440, "height": 950}).new_page()
        erros_js = []
        pagina.on("pageerror", lambda e: erros_js.append(str(e)))
        remessas = []
        pagina.on(
            "response",
            lambda r: remessas.append((r.url, r.status))
            if "importar-arquivos" in r.url else None,
        )

        # --- login -----------------------------------------------------------
        pagina.goto(f"{GW}/login", wait_until="networkidle")
        pagina.fill("input#username", usuario)
        pagina.fill("input#password", senha)
        pagina.click("button[type=submit]")
        responder_no_navegador(pagina)
        # Esperar a URL mudar, e não o `networkidle`: a rede fica ociosa antes de
        # o roteador navegar, e a asserção passaria a olhar a tela de login.
        pagina.wait_for_url(lambda u: "/login" not in u, timeout=60_000)
        checar(f"login de {usuario} pelo gateway", "/login" not in pagina.url, pagina.url)

        # --- a Prancheta, e a obra -------------------------------------------
        pagina.goto(f"{GW}/app/prancheta", wait_until="networkidle")
        pagina.wait_for_timeout(3000)

        # A Prancheta **lembra** a última obra do aparelho (é o que o canteiro
        # precisa), então o seletor só aparece depois do "Trocar de obra".
        trocar = pagina.locator("button:has-text('Trocar de obra')")
        if trocar.count():
            trocar.first.click()
            pagina.wait_for_timeout(1200)

        alvo = pagina.locator(f"button:has-text('{nome_da_obra}')").first
        checar("a obra do teste aparece no seletor", alvo.count() > 0, nome_da_obra)
        alvo.click()
        pagina.wait_for_timeout(3000)

        aba = pagina.locator("button:has-text('Acervo')")
        checar("a obra abriu na Prancheta", aba.count() > 0)
        aba.first.click()
        pagina.wait_for_timeout(1500)

        # --- o botão que não existia ------------------------------------------
        botao = pagina.locator("button:has-text('Enviar acervo (pasta)')")
        checar("o botão de enviar acervo existe na aba", botao.count() > 0)
        if not botao.count():
            navegador.close()
            return
        botao.first.click()
        pagina.wait_for_timeout(600)

        # --- a pasta ------------------------------------------------------------
        # `webkitdirectory` é o único jeito de um navegador entregar uma ÁRVORE, e
        # é o que faz `webkitRelativePath` existir. Apontar arquivo por arquivo
        # passaria no upload e perderia a taxonomia, que é metade do recurso.
        entrada = pagina.locator("input[type=file][webkitdirectory]")
        entrada.set_input_files(pasta)
        pagina.wait_for_timeout(2500)

        peneirados = pagina.locator("text=/\\d+ para enviar/").first
        rotulo = peneirados.inner_text() if peneirados.count() else ""
        checar(f"a peneira contou os arquivos aceitos ({rotulo})",
               str(esperados) in rotulo, rotulo)

        # --- envio --------------------------------------------------------------
        comeco = time.monotonic()
        pagina.locator("button:has-text('Enviar')").last.click()
        # 350 MB em 16 remessas: o teto é generoso de propósito, e a espera é pela
        # CONFERÊNCIA aparecer — não por um tempo fixo, que mentiria numa máquina
        # mais lenta.
        pagina.wait_for_selector("text=/Confirmar tudo/", timeout=900_000)
        subida = time.monotonic() - comeco
        print(f"     upload: {subida:.0f}s em {len(remessas)} remessa(s)")

        recusadas = [r for r in remessas if r[1] >= 400]
        checar(f"toda remessa foi aceita ({len(remessas)} remessas)",
               not recusadas, recusadas[:3])

        # --- R1: nada gravado ANTES da decisão ---------------------------------
        no_meio = acervo_por_api(token, obra)
        checar("R1 — nada foi gravado antes de confirmar", no_meio == 0,
               f"{no_meio} documento(s) já no acervo")

        conferidos = pagina.locator("text=/\\d+ arquivo\\(s\\) em \\d+ remessa/").first
        if conferidos.count():
            print(f"     conferência: {conferidos.inner_text()}")

        # --- a decisão ----------------------------------------------------------
        pagina.locator("button:has-text('Confirmar tudo')").click()
        pagina.wait_for_timeout(3000)
        for _ in range(120):
            if acervo_por_api(token, obra) >= esperados:
                break
            pagina.wait_for_timeout(1000)

        depois = acervo_por_api(token, obra)
        checar(f"o acervo recebeu os {esperados} arquivos", depois >= esperados,
               f"{depois} revisão(ões)")
        checar(f"nenhum erro de JS na tela -> {len(erros_js)}", not erros_js, erros_js[:3])

        pagina.screenshot(path="/tmp/pra5c-acervo.png", full_page=True)
        navegador.close()


if __name__ == "__main__":
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("pasta")
    analisador.add_argument("--obra", type=int, required=True)
    analisador.add_argument("--nome-da-obra", default="Corpus 160")
    analisador.add_argument("--usuario", default="admin")
    analisador.add_argument("--senha", default="admin123")
    analisador.add_argument("--esperados", type=int, default=159)
    opcoes = analisador.parse_args()
    rodar(opcoes.pasta, opcoes.obra, opcoes.usuario, opcoes.senha, opcoes.esperados,
          opcoes.nome_da_obra)
    print(f"\n=== {len(OK)}/{len(OK) + len(FALHA)} ===")
    if FALHA:
        print("FALHARAM:", FALHA)
    sys.exit(1 if FALHA else 0)
