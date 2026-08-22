#!/usr/bin/env python3
"""Carrega um acervo de DWGs reais na Prancheta, pela porta que o cliente usa.

**Existe para a tela ter acervo de verdade.** O corpus de 160 DWGs que mede a
cobertura do motor ([ferramentas/medicao/](../medicao/README.md)) prova números; o que
ele não faz é aparecer na Prancheta. Este script põe os mesmos arquivos no
sistema **pelo lote do acervo histórico** (PRA.5b / R18) — nada de `INSERT` no
banco: sobe multipart pelo gateway, passa pela conferência, aplica, e as
conversões saem pela fila `conversao` como sairiam para qualquer cliente.

Ir pela porta real é o ponto. Um seed que escrevesse direto no ORM produziria uma
tela bonita sobre um caminho que ninguém exercitou — e é exatamente esse caminho
(assinatura de bytes, taxonomia adivinhada da pasta, conferência, desfazer) que a
PRA.5a/5b construiu.

    python3 testes/e2e/carregar_acervo_dwg.py ~/medicao-dwg/corpus --obra 7

    --lote N        arquivos por requisição (padrão 10)
    --limite N      para depois de N arquivos — a versão pequena, para ver antes
    --lista ARQ     sobe exatamente estes caminhos relativos (um por linha)
    --publicar      publica cada revisão criada; sem isto elas ficam em rascunho
    --usuario/--senha, --gateway

**As revisões nascem `rascunho`, e publicar é opção separada aqui pelo mesmo
motivo que é verbo separado no backend** (a lição do D28): o lote pede
`documento.edit`, publicar muda o que o campo executa. Sem `--publicar` o acervo
aparece com a fila de decisão cheia — que é o cockpit funcionando, não uma
lacuna.
"""
import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
import uuid

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

#: O que o acervo aceita como desenho. Fora disso o registry recusa na porta, e
#: um lote inteiro pararia por causa de um `.bak` esquecido na pasta.
EXTENSOES = (".dwg", ".dxf", ".pdf", ".ifc")


def req(gw, metodo, caminho, token=None, corpo=None, timeout=300):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    cabecalhos = {"Content-Type": "application/json"}
    if token:
        cabecalhos["Authorization"] = "Bearer " + token
    pedido = urllib.request.Request(gw + caminho, data=dados, method=metodo,
                                    headers=cabecalhos)
    try:
        with urllib.request.urlopen(pedido, timeout=timeout, context=_CTX) as resposta:
            return resposta.status, json.loads(resposta.read().decode() or "null")
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read().decode() or "null")
        except Exception:
            return erro.code, None


def upload_lote(gw, caminho, token, campos, arquivos, timeout=900):
    """multipart com `arquivos[]` + `caminhos[]` paralelos — a porta da R18.

    É o **caminho** na pasta, não o nome, que carrega a taxonomia (disciplina,
    código, revisão). Mandar só o nome faria a plataforma adivinhar pior do que
    ela sabe.
    """
    limite = "----sgi" + uuid.uuid4().hex
    partes = []
    for chave, valor in (campos or {}).items():
        partes.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="{chave}"\r\n\r\n{valor}\r\n'.encode()
        )
    for nome, relativo, binario, tipo in arquivos:
        partes.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="arquivos"; '
            f'filename="{nome}"\r\nContent-Type: {tipo}\r\n\r\n'.encode() + binario + b"\r\n"
        )
        partes.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="caminhos"\r\n\r\n'
            f"{relativo}\r\n".encode()
        )
    partes.append(f"--{limite}--\r\n".encode())

    pedido = urllib.request.Request(
        gw + caminho, data=b"".join(partes), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={limite}",
                 "Authorization": "Bearer " + token},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=timeout, context=_CTX) as resposta:
            return resposta.status, json.loads(resposta.read().decode() or "null")
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read().decode() or "null")
        except Exception:
            return erro.code, None


def escolher(pasta, opcoes):
    if opcoes.lista:
        with open(opcoes.lista, encoding="utf-8") as arquivo:
            relativos = [l.strip() for l in arquivo if l.strip()]
    else:
        relativos = []
        for raiz, _dirs, nomes in os.walk(pasta):
            for nome in sorted(nomes):
                if nome.lower().endswith(EXTENSOES):
                    relativos.append(os.path.relpath(os.path.join(raiz, nome), pasta))
        relativos.sort()
    return relativos[:opcoes.limite] if opcoes.limite else relativos


def publicar_rascunhos(gw, token, obra, pagina=200):
    """Publica o que o lote deixou em rascunho — em ordem, e sem inventar id.

    Um documento só tem **uma** vigente, e publicar rebaixa a anterior; por isso
    a ordem importa e a página é percorrida do começo ao fim, deixando por último
    a revisão mais nova de cada documento. Idempotente: republicar responde 409 e
    a contagem separa isso de erro de verdade.
    """
    publicadas, ja_publicadas, falhas = 0, 0, 0
    travadas: set = set()
    while True:
        status, corpo = req(
            gw, "GET",
            f"/api/prancheta/revisoes/?documento__obra={obra}&situacao=rascunho"
            f"&page_size={pagina}", token,
        )
        if status != 200 or not corpo:
            break
        itens = corpo.get("results", corpo) if isinstance(corpo, dict) else corpo
        # **Só as que ainda não recusaram.** A lista encolhe a cada publicação
        # (o filtro é `situacao=rascunho`), então relê-se sempre a 1ª página em
        # vez de paginar; sem descontar as travadas isso seria laço infinito no
        # dia em que uma revisão se recusar a publicar.
        pendentes = [r for r in itens if r["id"] not in travadas]
        if not pendentes:
            break
        for revisao in pendentes:
            status, _ = req(gw, "POST",
                            f"/api/prancheta/revisoes/{revisao['id']}/publicar/", token)
            if status in (200, 202):
                publicadas += 1
            elif status == 409:
                ja_publicadas += 1
                travadas.add(revisao["id"])
            else:
                falhas += 1
                travadas.add(revisao["id"])
    print(f"publicadas {publicadas} · já estavam {ja_publicadas} · falharam {falhas}")


def principal():
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("pasta")
    analisador.add_argument("--obra", required=True)
    analisador.add_argument("--gateway", default="http://localhost:8090")
    analisador.add_argument("--usuario", default="demo")
    analisador.add_argument("--senha", default="demo123")
    analisador.add_argument("--lote", type=int, default=10)
    analisador.add_argument("--limite", type=int, default=0)
    analisador.add_argument("--lista", default="")
    analisador.add_argument("--publicar", action="store_true")
    opcoes = analisador.parse_args()

    gw = opcoes.gateway.rstrip("/")
    status, sessao = req(gw, "POST", "/auth/login/",
                         corpo={"username": opcoes.usuario, "password": opcoes.senha})
    if status != 200 or not (sessao or {}).get("access"):
        sys.exit(f"login falhou ({status}): {sessao}")
    token = sessao["access"]

    relativos = escolher(opcoes.pasta, opcoes)
    if not relativos:
        sys.exit("nenhum arquivo encontrado.")
    total_bytes = sum(os.path.getsize(os.path.join(opcoes.pasta, r)) for r in relativos)
    print(f"{len(relativos)} arquivos · {total_bytes / 1e6:.0f} MB · obra {opcoes.obra}")

    criadas, ja_existiam, recusados = [], 0, []
    for inicio in range(0, len(relativos), opcoes.lote):
        janela = relativos[inicio:inicio + opcoes.lote]
        arquivos = []
        for relativo in janela:
            with open(os.path.join(opcoes.pasta, relativo), "rb") as arquivo:
                arquivos.append((os.path.basename(relativo), relativo, arquivo.read(),
                                 "application/octet-stream"))

        status, lote = upload_lote(
            gw, "/api/impexp/prancheta.acervo/importar-arquivos/", token,
            {"contexto": json.dumps({"obra": opcoes.obra})}, arquivos,
        )
        rotulo = f"[{inicio + 1}-{inicio + len(janela)}/{len(relativos)}]"
        if status != 201 or not (lote or {}).get("importacao_id"):
            print(f"  {rotulo} RECUSADO ({status}): {lote}")
            recusados.extend(janela)
            continue

        identificador = lote["importacao_id"]
        status, aplicado = req(gw, "POST",
                               f"/api/impexp/importacoes/{identificador}/aplicar/", token)
        if status not in (200, 202):
            print(f"  {rotulo} aplicar falhou ({status}): {aplicado}")
            recusados.extend(janela)
            continue

        # O `aplicar` devolve **contagem**, não os ids do que criou — então quem
        # sabe o que existe é o acervo, consultado depois. Melhor assim: publicar
        # o que está em rascunho na obra é idempotente e sobrevive a um lote que
        # tenha falhado no meio.
        aplicadas = (aplicado or {}).get("aplicadas") or 0
        criadas.append(aplicadas)
        ja_existiam += len(janela) - aplicadas
        print(f"  {rotulo} aplicadas={aplicadas} · lote {identificador}")

    print(f"\naplicadas {sum(criadas)} · já existiam {ja_existiam} · recusadas {len(recusados)}")
    for relativo in recusados[:10]:
        print(f"  recusado: {relativo}")

    if opcoes.publicar:
        publicar_rascunhos(gw, token, opcoes.obra)

    print("\nA conversão roda na fila `conversao` (worker próprio, 1 por vez): "
          "acompanhe em /api/prancheta/status/ ou na aba Conversões da tela.")


if __name__ == "__main__":
    principal()
