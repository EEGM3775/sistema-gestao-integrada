"""PRA.8 — módulo Prancheta ponta a ponta pelo gateway (8090).

Prova com token real da IAM o que a suíte unitária (133 testes) concede à mão e
por isso nunca esbarra: o entitlement `prancheta`, as 7 permissões `prancheta.*`
e as personas `projetista`/`campo` só existem depois do rebuild da imagem da IAM
+ re-seed — a lição do **D31**, que se repetiu duas vezes neste módulo.

E prova, sobretudo, três coisas que só existem no stack vivo:

- **o gate é UM só** (planta §2). Ao contrário do Maps, a Prancheta não tem
  metade de fundação: georreferenciar a obra é cadastro que outros módulos
  consomem, abrir o projeto dela não é. Quem não assina não lê nem o acervo;
- **os quatro motores livres convertem arquivo de verdade** — foi assim que o
  **D34** apareceu (DWG e IFC falhavam 100% e nenhum unitário via, porque o
  unitário não roda `dwg2dxf` nem espera o destrutor do serializador do glTF), e
  é o único teste que pega o **D33** voltando se o build stage do LibreDWG
  quebrar num GCC futuro;
- **a porta de leitura do acervo é da API**, não de `/media/` — o **S10** que o
  MAP.3 recusou repetir e que a PRA.2 fechou aqui.

Seed: testes/seeds/seed_demo.py (demo + acme + campo) · testes/seeds/seed_demo_data.py

  demo     / demo123     -> assina `prancheta`, persona `projetista`: governa o
                            acervo, publica revisão, calibra, resolve marcação
  campo    / campo123     -> MESMO tenant, persona `campo`: lê a prancha, marca e
                            mede — e **não** resolve nem calibra. É o único ator
                            capaz de separar `marcacao.edit` de `.resolver`; sem
                            ele a segregação da PRA.3 fica no papel
  acme     / acme123      -> tenant que NÃO assina `prancheta` (só `drone`)

   1. Módulo vivo         -> /status/ declara motor em 3 colunas (plano × código ×
                             imagem) e o catálogo inteiro de formatos, travados
                             com o motivo — nunca escondidos.
   2. **Gate único**      -> sem o módulo, 403 em TUDO, inclusive no acervo. É o
                             contraste com o Maps, onde `Local` abria sem ele.
   3. Parede comercial    -> RVT que o plano não abre é **402** (com o CTA dentro),
                             extensão desconhecida é **400** (nenhum plano a abre)
                             e `.bcfzip` é 400 apontando a porta certa.
   4. **Os 4 motores**    -> PDF→miniatura · DXF→SVG · DWG→SVG (LibreDWG) ·
                             IFC→glTF, cada um carimbando o motor que o gerou.
   5. **Leitura gateada** -> 401 sem token, 403 sem entitlement, e com token vem
                             `nosniff` + `attachment` + `private, immutable`.
                             Nenhuma resposta publica caminho de `/media/`.
   6. Publicar é alçada   -> PATCH não move `situacao`; publicar rebaixa a
                             anterior; republicar 409; superada 409.
   7. **Quem aponta não fecha** -> o `campo` marca, comenta e mede; leva 403 no
                             verbo de situação. O `projetista` resolve.
   8. Régua declarada     -> sem calibração a medida sai em fração da largura (sem
                             unidade); calibrada, sai em metro — e o valor é do
                             SERVIDOR. Área escala com o quadrado.
   9. Recalibrar não reescreve -> a medida antiga carimbou a escala e se declara
                             desatualizada, em vez de mudar de valor sozinha.
  10. **BCF ida e volta** -> o GUID reencontra a MESMA linha: 0 duplicadas, e o
                             comentário não se multiplica a cada viagem.
  11. Fila de decisão     -> as 7 contagens do cockpit, incluindo a marcação viva
                             sobre desenho já superado.
  12. D38                 -> a resposta do verbo de situação já traz o comentário
                             que o próprio ato acabou de escrever.

Rodar (stack de pé):  python testes/e2e/pra8_prancheta_test.py
                      SGI_GW=https://localhost:8443 python testes/e2e/pra8_prancheta_test.py
"""
import json, os, ssl, sys, time, urllib.error, urllib.request, uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from amostras_pra8 import AMOSTRAS, DWG, DXF, PDF, RVT_RECONHECIVEL  # noqa: E402
from _sessao import cabecalhos, da_resposta

# Console do Windows costuma ser cp1252 e quebra em acento ao redirecionar.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")  # SGI_GW aponta ao staging (10.7)

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# Tudo que o teste cria carrega este prefixo no `codigo` do documento, que é
# unique por (tenant, obra, codigo) — sem faxina, a 2ª execução morreria em 400 e
# pareceria defeito do módulo.
TAG = "E2E-PRA8"

# Teto de espera da conversão. Generoso de propósito: o `dwg2dxf` é subprocesso e
# o IfcOpenShell tessela geometria — num runner frio os dois passam de 10 s, e um
# timeout curto transformaria lentidão em "o motor não converte".
ESPERA_CONVERSAO = 90


def req(method, path, token=None, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers.update(cabecalhos(token))
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=timeout, context=_CTX) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except Exception:
            return e.code, None


def bruto(path, token=None, timeout=120):
    """GET que devolve `(status, headers, bytes)` — para o arquivo do acervo.

    Os headers SÃO o teste aqui: `nosniff`, `attachment` e `immutable` são as
    três decisões de entrega da planta §7.1, e nenhuma delas aparece no corpo.
    """
    headers = cabecalhos(token) if token else {}
    r = urllib.request.Request(GW + path, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=timeout, context=_CTX) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


def upload(path, token, campos, arquivo=None, metodo="POST"):
    """multipart/form-data — revisão e BCF entram por arquivo, não por JSON."""
    limite = "----sgi" + uuid.uuid4().hex
    partes = []
    for chave, valor in (campos or {}).items():
        partes.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="{chave}"\r\n\r\n{valor}\r\n'.encode()
        )
    if arquivo is not None:
        campo, nome, dados, tipo = arquivo
        partes.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="{campo}"; '
            f'filename="{nome}"\r\nContent-Type: {tipo}\r\n\r\n'.encode()
            + dados + b"\r\n"
        )
    partes.append(f"--{limite}--\r\n".encode())

    r = urllib.request.Request(
        GW + path, data=b"".join(partes), method=metodo,
        headers={
            "Content-Type": f"multipart/form-data; boundary={limite}",
            **cabecalhos(token),
        },
    )
    try:
        with urllib.request.urlopen(r, timeout=180, context=_CTX) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except Exception:
            return e.code, None


def upload_lote(path, token, campos, arquivos):
    """multipart com N arquivos — a porta de lote do motor (`arquivos[]`).

    Irmão do `upload` e não um parâmetro dele: o lote manda `arquivos[]` **e**
    `caminhos[]` como listas paralelas, e é o caminho (não o nome) que carrega a
    taxonomia da pasta do projetista. Cada item de `arquivos` é
    `(nome, caminho, bytes, tipo)`.
    """
    limite = "----sgi" + uuid.uuid4().hex
    partes = []
    for chave, valor in (campos or {}).items():
        partes.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="{chave}"\r\n\r\n{valor}\r\n'.encode()
        )
    for nome, caminho, dados, tipo in arquivos:
        partes.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="arquivos"; '
            f'filename="{nome}"\r\nContent-Type: {tipo}\r\n\r\n'.encode() + dados + b"\r\n"
        )
        partes.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="caminhos"\r\n\r\n'
            f"{caminho}\r\n".encode()
        )
    partes.append(f"--{limite}--\r\n".encode())

    r = urllib.request.Request(
        GW + path, data=b"".join(partes), method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={limite}",
            **cabecalhos(token),
        },
    )
    try:
        with urllib.request.urlopen(r, timeout=180, context=_CTX) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
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


def linhas(payload):
    if isinstance(payload, dict):
        return payload.get("results", [])
    return payload or []


passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def fatal(msg):
    print(f"\n  !! {msg}")
    print("     O seed da IAM (testes/seeds/seed_demo.py) e o do backend precisam ter rodado.")
    print("     Entitlement/persona novos exigem rebuild da imagem `sgi-iam` + re-seed (D31).")
    print(f"     Parcial: {sum(1 for p in passed if p)}/{len(passed)}")
    sys.exit(2)


def esperar_conversao(revisao_id, token, *, segundos=ESPERA_CONVERSAO):
    """Espera a derivada sair de pendente/lendo/convertendo.

    A conversão é assíncrona por natureza (planta §5) — um RVT de 300 MB não
    converte no request —, então o teste espera como a tela espera. Devolve a
    revisão no último estado visto, mesmo se estourar: um teste que só dissesse
    "timeout" esconderia a informação que interessa, que é em QUE estado travou.
    """
    limite = time.time() + segundos
    revisao = None
    while time.time() < limite:
        _status, revisao = req("GET", f"/api/prancheta/revisoes/{revisao_id}/", token)
        derivadas = (revisao or {}).get("derivadas") or []
        if derivadas and all(d["estado"] in ("pronto", "erro") for d in derivadas):
            return revisao
        time.sleep(2)
    return revisao


demo = login("demo", "demo123")
acme = login("acme", "acme123")
try:
    campo = login("campo", "campo123")
except urllib.error.HTTPError:
    print("  !! O usuário `campo` não existe na IAM deste stack.")
    print("     Ele é o único ator capaz de provar a segregação `edit` × `resolver`")
    print("     da PRA.3. Rebuilde a imagem `sgi-iam` e rode o seed de novo:")
    print("       docker compose build iam && docker compose up -d iam")
    print("       docker exec -i sgi-iam python manage.py shell < testes/seeds/seed_demo.py")
    sys.exit(2)

# ---------------------------------------------------------------------------
# Faxina — a rerodada tem de encontrar o terreno como o encontrou da 1ª vez.
# Apagar o documento leva junto revisões, derivadas, marcações e medições
# (CASCADE), então uma passada só basta.
# ---------------------------------------------------------------------------
def faxina():
    apagados = 0
    status, dados = req("GET", "/api/prancheta/documentos/?page_size=200", demo)
    if status == 200:
        for doc in linhas(dados):
            if str(doc.get("codigo", "")).startswith(TAG):
                req("DELETE", f"/api/prancheta/documentos/{doc['documento_id']}/", demo)
                apagados += 1
    return apagados


print(f"== 0. Faxina de execução anterior ==\n  {faxina()} documentos do E2E removidos")

# ---------------------------------------------------------------------------
print("== 1. Módulo vivo, e o que ESTE plano abre ==")
status, st = req("GET", "/api/prancheta/status/", demo)
check(f"GET /api/prancheta/status/ (200) -> {status}", status == 200)
if status != 200:
    fatal(f"o módulo não respondeu: {st}")

motores = {m["codigo"]: m for m in (st or {}).get("motores") or []}
check(f"declara os 7 motores do registry -> {len(motores)}", len(motores) == 7)
livres = ("pdf_nativo", "ezdxf", "libredwg", "ifcopenshell")
for codigo in livres:
    motor = motores.get(codigo, {})
    check(f"motor `{codigo}` habilitado+implementado+disponível -> "
          f"{motor.get('habilitado')}/{motor.get('implementado')}/{motor.get('disponivel')} "
          f"({motor.get('versao') or '—'})",
          motor.get("habilitado") and motor.get("implementado") and motor.get("disponivel"))

# As 3 colunas respondem perguntas diferentes, e o valor do endpoint é não
# confundi-las. A APS é o caso em que plano e código dizem "não" pelo mesmo
# motivo (PRA.4 não existe); o `gdal` é o caso em que o PLANO diz sim e o
# CÓDIGO diz não — que é uma lacuna nossa, não um upsell.
check(f"APS declarada e não habilitada neste plano -> {motores['aps'].get('habilitado')}",
      motores["aps"].get("habilitado") is False)
check(f"`gdal` habilitado pelo plano mas SEM adaptador (lacuna declarada) -> "
      f"habilitado={motores['gdal'].get('habilitado')} implementado={motores['gdal'].get('implementado')}",
      motores["gdal"].get("implementado") is False)
check(f"conversao_disponivel é medida, não fixa -> {st.get('conversao_disponivel')}",
      st.get("conversao_disponivel") is True)

formatos = {f["codigo"]: f for f in (st or {}).get("formatos") or []}
check(f"o catálogo INTEIRO viaja, não só o contratado -> {len(formatos)} formatos",
      len(formatos) >= 18)
check(f"RVT aparece travado com o motivo (não escondido) -> contratado="
      f"{formatos['rvt']['contratado']} exige_premium={formatos['rvt']['exige_motor_premium']}",
      formatos["rvt"]["contratado"] is False and formatos["rvt"]["exige_motor_premium"] is True)
check("BCF não é vendido como upsell de motor (interop, sem motor) -> "
      f"interop={formatos['bcf']['interop']} exige_premium={formatos['bcf']['exige_motor_premium']}",
      formatos["bcf"]["interop"] is True and formatos["bcf"]["exige_motor_premium"] is False)

# ---------------------------------------------------------------------------
print("== 2. O gate é UM só — a Prancheta não tem metade de fundação ==")
# É o contraste deliberado com o MAP.6: lá o `acme` LIA `/api/maps/locais/` sem
# assinar `maps`, porque `Local` é cadastro que o SIL e o SCM consomem. Aqui o
# acervo é o produto, e o custo (storage de CAD/BIM, motor de conversão) é todo
# do módulo — então não há o que abrir de graça.
for rota in ("documentos/", "revisoes/", "derivadas/", "marcacoes/", "medicoes/",
             "status/", "acervo/?obra=1"):
    status, _ = req("GET", f"/api/prancheta/{rota}", acme)
    check(f"tenant SEM o módulo leva 403 em /{rota} -> {status}", status == 403)

status, _ = req("GET", "/api/prancheta/documentos/", demo)
check(f"e quem assina entra -> {status}", status == 200)
status, _ = req("GET", "/api/prancheta/documentos/", campo)
check(f"o `campo` também lê o acervo (é o caso de uso central) -> {status}", status == 200)

# ---------------------------------------------------------------------------
print("== 3. Onde nasce o acervo: obra, documento e as quatro entradas ==")
status, obras = req("GET", "/api/obras/?page_size=1", demo)
lista_obras = linhas(obras)
if status != 200 or not lista_obras:
    fatal("nenhuma obra no tenant demo — rode o seed do backend")
obra_id = lista_obras[0]["obra_id"]
print(f"  obra de trabalho: {obra_id} — {lista_obras[0].get('nome_obra')}")

documentos = {}
for codigo_formato, nome, _dados, _tipo in AMOSTRAS:
    status, doc = req("POST", "/api/prancheta/documentos/", demo, {
        "obra": obra_id,
        "codigo": f"{TAG}-{codigo_formato.upper()}",
        "titulo": f"Amostra {codigo_formato.upper()} — E2E PRA.8",
        "disciplina": "arquitetura",
        "projetista": "Escritório de teste",
    })
    check(f"documento {codigo_formato.upper()} criado (201) -> {status}", status == 201)
    if status != 201:
        fatal(f"não consegui criar o documento: {doc}")
    documentos[codigo_formato] = doc["documento_id"]

check(f"documento nasce SEM revisão vigente (é fila, não erro) -> {doc.get('vigente')}",
      doc.get("vigente") is None)

# ---------------------------------------------------------------------------
print("== 4. Parede comercial: 402 é 'compre', 400 é 'isso não existe aqui' ==")
alvo = documentos["pdf"]
status, erro = upload(
    "/api/prancheta/revisoes/", demo, {"documento": alvo, "revisao": "R99"},
    arquivo=("arquivo", "modelo.rvt", RVT_RECONHECIVEL, "application/octet-stream"),
)
check(f"RVT (formato existente, plano não inclui) -> 402, não 403 -> {status}", status == 402)
check(f"e o corpo traz o CTA pronto -> code={(erro or {}).get('code')} "
      f"formato={(erro or {}).get('formato')}",
      (erro or {}).get("code") == "formato_nao_contratado" and (erro or {}).get("formato") == "rvt")
check(f"com a lista do que passa hoje -> {len((erro or {}).get('formatos_aceitos') or [])} formatos",
      "pdf" in ((erro or {}).get("formatos_aceitos") or []))

# PRA.5a / D75 — o par que separa "não vendemos isto" de "isto não é isto".
# As duas requisições trazem o MESMO nome de arquivo; só os bytes diferem, e é
# a única coisa que a porta olha. Enquanto o sufixo decidia, as duas davam 402:
# `payload.exe` renomeado para `.rvt` ganhava uma tela de upsell em vez de uma
# recusa, e um renomeado para `.dwg` seguia adiante para o LibreDWG, que é
# parser em C rodando no worker. É esta linha que impede aquilo de voltar.
status, erro = upload(
    "/api/prancheta/revisoes/", demo, {"documento": alvo, "revisao": "R99"},
    arquivo=("arquivo", "modelo.rvt", b"MZ\x90\x00 nao sou um Revit", "application/octet-stream"),
)
check(f"RVT no NOME mas não nos BYTES -> 400 (recusa), não 402 (upsell) -> {status}",
      status == 400)

status, erro = upload(
    "/api/prancheta/revisoes/", demo, {"documento": alvo, "revisao": "R99"},
    arquivo=("arquivo", "planta.dwg", b"MZ\x90\x00 executavel renomeado", "application/octet-stream"),
)
check(f"e o executável com sufixo .dwg não chega ao LibreDWG -> 400 -> {status}",
      status == 400)

status, erro = upload(
    "/api/prancheta/revisoes/", demo, {"documento": alvo, "revisao": "R99"},
    arquivo=("arquivo", "planilha.xyz", b"conteudo", "application/octet-stream"),
)
check(f"extensão que NENHUM plano abre -> 400, não 402 -> {status}", status == 400)
check("e a mensagem lista as extensões aceitas (não manda comprar) -> "
      f"{str((erro or {}).get('arquivo'))[:52]}…",
      "Aceitos" in json.dumps(erro or {}, ensure_ascii=False))

status, erro = upload(
    "/api/prancheta/revisoes/", demo, {"documento": alvo, "revisao": "R99"},
    arquivo=("arquivo", "marcacoes.bcfzip", b"PK\x03\x04", "application/octet-stream"),
)
check(f"BCF como revisão -> 400 apontando a porta certa -> {status}", status == 400)
check("e o texto diz que ele não é desenho -> "
      f"{str((erro or {}).get('arquivo'))[:56]}…",
      "marcações" in json.dumps(erro or {}, ensure_ascii=False))

# ---------------------------------------------------------------------------
print("== 5. Os quatro motores livres, sobre arquivo de verdade (o D34) ==")
revisoes = {}
for codigo_formato, nome, dados, tipo_esperado in AMOSTRAS:
    status, rev = upload(
        "/api/prancheta/revisoes/", demo,
        {"documento": documentos[codigo_formato], "revisao": "R00",
         "observacao": f"{TAG} — amostra de {codigo_formato}"},
        arquivo=("arquivo", nome, dados, "application/octet-stream"),
    )
    check(f"{codigo_formato.upper()}: revisão criada (201) -> {status}", status == 201)
    if status != 201:
        fatal(f"upload de {codigo_formato} recusado: {rev}")
    revisoes[codigo_formato] = rev["revisao_id"]
    check(f"{codigo_formato.upper()}: formato/hash/tamanho saem do ARQUIVO, não do payload -> "
          f"{rev['formato']} {rev['tamanho_bytes']}B {rev['hash_sha256'][:8]}…",
          rev["formato"] == codigo_formato and rev["tamanho_bytes"] == len(dados)
          and len(rev["hash_sha256"]) == 64)
    check(f"{codigo_formato.upper()}: nasce RASCUNHO (publicar é outro ato) -> {rev['situacao']}",
          rev["situacao"] == "rascunho")

for codigo_formato, nome, dados, tipo_esperado in AMOSTRAS:
    rev = esperar_conversao(revisoes[codigo_formato], demo)
    derivadas = (rev or {}).get("derivadas") or []
    pronta = next((d for d in derivadas if d["estado"] == "pronto"), None)
    check(f"{codigo_formato.upper()}: converteu -> "
          f"{[(d['tipo'], d['motor'], d['estado']) for d in derivadas] or 'NENHUMA'}",
          pronta is not None)
    if pronta is None:
        continue
    check(f"{codigo_formato.upper()}: derivada é `{tipo_esperado}` -> {pronta['tipo']}",
          pronta["tipo"] == tipo_esperado)
    check(f"{codigo_formato.upper()}: carimba o motor e a versão -> "
          f"{pronta['motor']} / {pronta['motor_versao']}",
          bool(pronta["motor"]) and bool(pronta["motor_versao"]))
    check(f"{codigo_formato.upper()}: guarda o hash da origem (idempotência) -> "
          f"{(pronta.get('hash_origem') or '')[:8]}…",
          len(pronta.get("hash_origem") or "") == 64)

# O DWG é o único cujo motor exigiu compilar código de terceiro na imagem (D33):
# se o build stage do LibreDWG quebrar num GCC futuro, é aqui que aparece.
dwg_pronta = next(
    (d for d in (esperar_conversao(revisoes["dwg"], demo) or {}).get("derivadas") or []
     if d["estado"] == "pronto"), None)
check(f"DWG passou pelo LibreDWG compilado na imagem (D33) -> "
      f"{(dwg_pronta or {}).get('motor')}",
      (dwg_pronta or {}).get("motor") == "libredwg")

# ---------------------------------------------------------------------------
print("== 6. A porta de leitura é da API — o S10 recusado outra vez ==")
status, rev_pdf = req("GET", f"/api/prancheta/revisoes/{revisoes['pdf']}/", demo)
url_arquivo = rev_pdf.get("arquivo_url")
# A rota mudou na PRA.5a e o que ela protege não: era `/api/prancheta/…`, virou
# `/api/impexp/…` quando as três saídas do módulo passaram por `entrega.servir`.
# O S10 nunca foi sobre o prefixo — é sobre o arquivo sair **pela API, com gate**,
# e não por `/media/`. Fixar o prefixo antigo faria a consolidação das portas
# parecer regressão; o que segue abaixo (401/403/200, nosniff, attachment) é a
# prova de verdade, e vale igual do outro lado da mudança.
check(f"a resposta traz `arquivo_url` apontando para a API -> {url_arquivo}",
      isinstance(url_arquivo, str) and url_arquivo.startswith("/api/impexp/"))
check("e NENHUMA resposta do módulo publica caminho de /media/ -> "
      f"{'limpo' if '/media/' not in json.dumps(rev_pdf) else 'VAZOU'}",
      "/media/" not in json.dumps(rev_pdf))

status, headers, corpo = bruto(url_arquivo)
check(f"sem token -> 401 (não é arquivo público por id) -> {status}", status == 401)
status, headers, corpo = bruto(url_arquivo, acme)
check(f"com token de quem não assina -> 403 -> {status}", status == 403)

status, headers, corpo = bruto(url_arquivo, demo)
check(f"com o token certo -> 200 e os bytes do arquivo -> {status} ({len(corpo)}B)",
      status == 200 and corpo == PDF)
check(f"tipo vem do REGISTRY, não do nome que o cliente mandou -> "
      f"{headers.get('Content-Type')}",
      (headers.get("Content-Type") or "").startswith("application/pdf"))
check(f"nada é servido como página -> nosniff={headers.get('X-Content-Type-Options')} "
      f"disposition={(headers.get('Content-Disposition') or '')[:10]}",
      headers.get("X-Content-Type-Options") == "nosniff"
      and (headers.get("Content-Disposition") or "").startswith("attachment"))
check(f"cache imutável (o gancho do offline da §8) -> {headers.get('Cache-Control')}",
      "immutable" in (headers.get("Cache-Control") or "")
      and "private" in (headers.get("Cache-Control") or ""))

# A derivada tem o MESMO gate — foi por aqui que a PRA.2 tirou o SVG de /media/,
# e o SVG é o caso que mais importa: é documento executável.
status, derivadas = req("GET", f"/api/prancheta/derivadas/?revisao={revisoes['dxf']}", demo)
derivada = linhas(derivadas)[0]
status, headers, corpo = bruto(derivada["arquivo_url"], demo)
check(f"o SVG do DXF sai gateado e como anexo -> {status} "
      f"{headers.get('Content-Type')} / {(headers.get('Content-Disposition') or '')[:10]}",
      status == 200 and headers.get("Content-Type") == "image/svg+xml"
      and (headers.get("Content-Disposition") or "").startswith("attachment"))
check(f"e é SVG de verdade, com traço dentro -> {len(corpo)}B",
      b"<svg" in corpo[:2000] and len(corpo) > 500)
status, _headers, _corpo = bruto(derivada["arquivo_url"])
check(f"a derivada sem token também é 401 -> {status}", status == 401)

# ---------------------------------------------------------------------------
print("== 7. Publicar é alçada — e PATCH não é atalho para ela ==")
status, patch = req("PATCH", f"/api/prancheta/revisoes/{revisoes['pdf']}/", demo,
                    {"situacao": "vigente"})
check(f"PATCH situacao=vigente responde 200 mas NÃO move -> {patch.get('situacao')}",
      status == 200 and patch.get("situacao") == "rascunho")

status, publicada = req("POST", f"/api/prancheta/revisoes/{revisoes['pdf']}/publicar/", demo, {})
check(f"publicar (persona projetista) -> 200 e vigente -> {publicada.get('situacao')}",
      status == 200 and publicada.get("situacao") == "vigente")
check(f"e carimba quem publicou -> {publicada.get('publicado_por_nome')}",
      publicada.get("publicado_por_nome") == "demo")

status, erro = req("POST", f"/api/prancheta/revisoes/{revisoes['pdf']}/publicar/", demo, {})
check(f"republicar a vigente -> 409, não 200 mudo -> {status}", status == 409)

status, r01 = upload(
    "/api/prancheta/revisoes/", demo,
    {"documento": documentos["pdf"], "revisao": "R01", "observacao": f"{TAG} — segunda entrega"},
    arquivo=("arquivo", "prancha-amostra.pdf", PDF, "application/octet-stream"),
)
check(f"R01 entra como revisão nova (não UPDATE) -> {status}", status == 201)
status, _ = req("POST", f"/api/prancheta/revisoes/{r01['revisao_id']}/publicar/", demo, {})
check(f"publicar a R01 -> {status}", status == 200)
status, r00 = req("GET", f"/api/prancheta/revisoes/{revisoes['pdf']}/", demo)
check(f"a R00 foi rebaixada a superada -> {r00.get('situacao')}", r00.get("situacao") == "superada")
status, erro = req("POST", f"/api/prancheta/revisoes/{revisoes['pdf']}/publicar/", demo, {})
check(f"republicar uma SUPERADA -> 409 com o caminho certo na mensagem -> {status}", status == 409)
check(f"e a mensagem manda registrar revisão nova -> {str((erro or {}).get('detail'))[:48]}…",
      "revisão nova" in str((erro or {}).get("detail")))

status, erro = upload(
    f"/api/prancheta/revisoes/{r01['revisao_id']}/", demo, {},
    arquivo=("arquivo", "outra.pdf", PDF, "application/octet-stream"), metodo="PATCH",
)
check(f"trocar o arquivo de uma revisão existente -> 400 (write-once) -> {status}", status == 400)

# O `campo` não publica: é literalmente a linha que separa as duas personas.
status, _ = req("POST", f"/api/prancheta/revisoes/{revisoes['dxf']}/publicar/", campo, {})
check(f"o `campo` NÃO publica -> 403 -> {status}", status == 403)
status, _ = req("POST", f"/api/prancheta/revisoes/{revisoes['dxf']}/publicar/", demo, {})
status, _ = req("POST", f"/api/prancheta/revisoes/{revisoes['ifc']}/publicar/", demo, {})
status, _ = req("POST", f"/api/prancheta/revisoes/{revisoes['dwg']}/publicar/", demo, {})
check(f"e as demais pranchas ficam vigentes -> {status}", status == 200)

# ---------------------------------------------------------------------------
print("== 8. Quem aponta não fecha (a segregação da PRA.3) ==")
status, marcacao = req("POST", "/api/prancheta/marcacoes/", campo, {
    "revisao": revisoes["dxf"],
    "titulo": f"{TAG} — pilar fora de prumo",
    "descricao": "A face do P3 está 12 cm fora do alinhamento da fôrma.",
    "tipo": "Issue",
    "prioridade": "High",
    "ancora": {"x": 0.42, "y": 0.31},
})
check(f"o `campo` MARCA (é o trabalho dele) -> {status}", status == 201)
if status != 201:
    fatal(f"o campo não conseguiu marcar: {marcacao}")
marcacao_id = marcacao["marcacao_id"]
check(f"a marcação nasce aberta -> {marcacao.get('situacao')}/{marcacao.get('aberta')}",
      marcacao.get("situacao") == "Open" and marcacao.get("aberta") is True)
check(f"com GUID próprio (a identidade fora daqui) -> {marcacao.get('guid')}",
      len(str(marcacao.get("guid") or "")) == 36)
check(f"e a âncora guardada normalizada -> {marcacao.get('ancora')}",
      (marcacao.get("ancora") or {}).get("x") == 0.42)

status, comentario = req("POST", f"/api/prancheta/marcacoes/{marcacao_id}/comentar/", campo,
                         {"texto": "Conferido com a trena, duas vezes."})
check(f"o `campo` comenta (a conversa é de todo mundo) -> {status}", status == 201)

status, negado = req("POST", f"/api/prancheta/marcacoes/{marcacao_id}/situacao/", campo,
                     {"situacao": "Closed"})
check(f"mas NÃO fecha o próprio apontamento -> 403 -> {status}", status == 403)

status, fechada = req("POST", f"/api/prancheta/marcacoes/{marcacao_id}/situacao/", demo,
                      {"situacao": "Resolved"})
check(f"o `projetista` resolve -> 200 -> {status}", status == 200)
check(f"e o carimbo de quem resolveu fica -> {fechada.get('resolvido_por_nome')}",
      fechada.get("resolvido_por_nome") == "demo")

# D38 — o defeito que só o teste que olha a RESPOSTA pega: o comentário
# automático do próprio ato tem de vir na conversa que a ação devolve, e não só
# no próximo refetch.
textos = [c["texto"] for c in fechada.get("comentarios") or []]
check(f"a RESPOSTA já traz o comentário do próprio ato (D38) -> {len(textos)} comentários",
      any("Situação alterada" in t for t in textos))

status, reaberta = req("POST", f"/api/prancheta/marcacoes/{marcacao_id}/situacao/", demo,
                       {"situacao": "Open"})
check(f"reabrir limpa o carimbo (ninguém fica acusado de encerrar) -> "
      f"resolvido_por={reaberta.get('resolvido_por')}",
      status == 200 and reaberta.get("resolvido_por") is None)

status, erro = req("POST", f"/api/prancheta/marcacoes/{marcacao_id}/situacao/", demo,
                   {"situacao": "Encerrado"})
check(f"situação fora do vocabulário BCF -> 400 com a lista -> {status}", status == 400)

# ---------------------------------------------------------------------------
print("== 9. Medir exige régua declarada — e o valor é do SERVIDOR ==")
# A prancha do DXF ainda não foi calibrada: a medida existe, o metro não.
status, sem_regua = req("POST", "/api/prancheta/medicoes/", campo, {
    "revisao": revisoes["dxf"], "tipo": "distancia",
    "pontos": [{"x": 0.10, "y": 0.10}, {"x": 0.60, "y": 0.10}],
    "rotulo": f"{TAG} sem escala",
})
check(f"sem calibração a medida é aceita -> {status}", status == 201)
check(f"e sai em fração da largura, com a unidade VAZIA (declarada) -> "
      f"{sem_regua.get('valor')} '{sem_regua.get('unidade')}'",
      sem_regua.get("unidade") == "" and abs(float(sem_regua["valor"]) - 0.5) < 1e-6)
check(f"sem escala aplicada carimbada -> {sem_regua.get('escala_aplicada')}",
      sem_regua.get("escala_aplicada") is None)

# **A régua é da FOLHA, não da revisão** (PRA.1c): quando uma revisão passou a
# poder trazer vários desenhos, uma escala por revisão descreveria no máximo um
# deles — e em silêncio para os outros. O verbo mudou de `revisoes/{id}/calibrar`
# para `desenhos/{id}/calibrar`, e este teste ficou para trás porque não voltou a
# rodar desde então: batia em 404 e o 404 se parecia com o 403 que ele esperava.
status, folhas = req("GET", f"/api/prancheta/desenhos/?revisao={revisoes['dxf']}", demo)
desenho_dxf = linhas(folhas)[0]["desenho_id"]
check(f"a revisão do DXF tem folha para calibrar -> desenho {desenho_dxf}",
      status == 200 and bool(desenho_dxf))

status, negado = req("POST", f"/api/prancheta/desenhos/{desenho_dxf}/calibrar/", campo, {
    "a": {"x": 0.0, "y": 0.0}, "b": {"x": 0.5, "y": 0.0}, "distancia_real": 10, "unidade": "m",
})
check(f"o `campo` NÃO calibra (quem mede não define a régua) -> 403 -> {status}", status == 403)

status, calibrada = req("POST", f"/api/prancheta/desenhos/{desenho_dxf}/calibrar/", demo, {
    "a": {"x": 0.0, "y": 0.0}, "b": {"x": 0.5, "y": 0.0}, "distancia_real": 10, "unidade": "m",
})
check(f"o responsável calibra -> 200 -> {status}", status == 200)
check(f"e a escala é CALCULADA (10 m / 0,5 da largura = 20) -> {calibrada.get('escala_valor')}",
      abs(float(calibrada["escala_valor"]) - 20.0) < 1e-6)
check(f"com a referência gravada (dois pontos + a cota digitada) -> "
      f"{(calibrada.get('escala_referencia') or {}).get('distancia_real')}",
      (calibrada.get("escala_referencia") or {}).get("distancia_real") == 10)
check(f"e quem calibrou fica -> {calibrada.get('escala_calibrada_em') is not None}",
      calibrada.get("escala_calibrada_em") is not None)

status, com_regua = req("POST", "/api/prancheta/medicoes/", campo, {
    "revisao": revisoes["dxf"], "tipo": "distancia",
    "pontos": [{"x": 0.10, "y": 0.10}, {"x": 0.60, "y": 0.10}],
    "rotulo": f"{TAG} com escala",
    # O cliente MANDA um valor absurdo de propósito: quem calcula é o servidor.
    "valor": 999, "unidade": "km",
})
check(f"a mesma medida, agora calibrada -> {com_regua.get('valor')} {com_regua.get('unidade')}",
      status == 201 and abs(float(com_regua["valor"]) - 10.0) < 1e-6
      and com_regua.get("unidade") == "m")
check("o 999 que o cliente mandou foi ignorado — o valor é do servidor",
      abs(float(com_regua["valor"]) - 999) > 1)
check(f"e a escala com que foi tirada fica carimbada -> {com_regua.get('escala_aplicada')}",
      abs(float(com_regua["escala_aplicada"]) - 20.0) < 1e-6)

status, area = req("POST", "/api/prancheta/medicoes/", campo, {
    "revisao": revisoes["dxf"], "tipo": "area",
    "pontos": [{"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0},
               {"x": 0.5, "y": 0.5}, {"x": 0.0, "y": 0.5}],
    "rotulo": f"{TAG} área",
})
# 0,25 da largura² × 20² = 100 m². Área escala com o QUADRADO do fator linear —
# o erro clássico aqui é multiplicar por 20 e entregar 5 m².
check(f"área escala com o QUADRADO do fator -> {area.get('valor')} {area.get('unidade')}",
      status == 201 and abs(float(area["valor"]) - 100.0) < 1e-6 and area.get("unidade") == "m²")

status, erro = req("POST", f"/api/prancheta/desenhos/{desenho_dxf}/calibrar/", demo, {
    "a": {"x": 0.2, "y": 0.2}, "b": {"x": 0.2005, "y": 0.2}, "distancia_real": 5, "unidade": "m",
})
check(f"dois pontos quase juntos não viram régua -> 400 -> {status}", status == 400)

# ---------------------------------------------------------------------------
print("== 10. Recalibrar não reescreve o que alguém já anotou ==")
status, recalibrada = req("POST", f"/api/prancheta/desenhos/{desenho_dxf}/calibrar/", demo, {
    "a": {"x": 0.0, "y": 0.0}, "b": {"x": 0.5, "y": 0.0}, "distancia_real": 20, "unidade": "m",
})
check(f"a régua muda (agora 40) -> {recalibrada.get('escala_valor')}",
      abs(float(recalibrada["escala_valor"]) - 40.0) < 1e-6)
status, antiga = req("GET", f"/api/prancheta/medicoes/{com_regua['medicao_id']}/", demo)
check(f"a medida antiga NÃO mudou de valor -> {antiga.get('valor')} {antiga.get('unidade')}",
      abs(float(antiga["valor"]) - 10.0) < 1e-6)
check(f"e passa a se declarar desatualizada -> {antiga.get('desatualizada')}",
      antiga.get("desatualizada") is True)

# ---------------------------------------------------------------------------
print("== 11. BCF: sai, volta e reencontra a MESMA linha ==")
status, headers, bcfzip = bruto(
    f"/api/prancheta/marcacoes/bcf/?revisao__documento__obra={obra_id}", demo)
check(f"exportar o BCF da obra -> 200 ({len(bcfzip)}B) -> {status}", status == 200)
check(f"é um zip de verdade -> {bcfzip[:2]}", bcfzip[:2] == b"PK")
check(f"e NÃO é cacheável (o filtro de amanhã dá outro arquivo) -> "
      f"{headers.get('Cache-Control')}",
      "no-store" in (headers.get("Cache-Control") or ""))

status, antes = req("GET", f"/api/prancheta/marcacoes/?revisao={revisoes['dxf']}", demo)
total_antes = antes.get("count")

status, resumo = upload(
    "/api/prancheta/marcacoes/importar-bcf/", demo, {"revisao": revisoes["dxf"]},
    arquivo=("arquivo", "marcacoes.bcfzip", bcfzip, "application/octet-stream"),
)
check(f"reimportar o mesmo arquivo -> 200 -> {status}", status == 200)
check(f"e ele RECONHECE as linhas pelo GUID: 0 criadas -> "
      f"criadas={(resumo or {}).get('criadas')} atualizadas={(resumo or {}).get('atualizadas')}",
      (resumo or {}).get("criadas") == 0 and (resumo or {}).get("atualizadas", 0) > 0)

status, depois = req("GET", f"/api/prancheta/marcacoes/?revisao={revisoes['dxf']}", demo)
check(f"nenhuma marcação duplicada -> {total_antes} -> {depois.get('count')}",
      depois.get("count") == total_antes)

status, topico = req("GET", f"/api/prancheta/marcacoes/{marcacao_id}/", demo)
comentarios_depois = len(topico.get("comentarios") or [])
status, resumo2 = upload(
    "/api/prancheta/marcacoes/importar-bcf/", demo, {"revisao": revisoes["dxf"]},
    arquivo=("arquivo", "marcacoes.bcfzip", bcfzip, "application/octet-stream"),
)
status, topico2 = req("GET", f"/api/prancheta/marcacoes/{marcacao_id}/", demo)
check(f"segunda viagem: o comentário também dedupla por GUID -> "
      f"{comentarios_depois} -> {len(topico2.get('comentarios') or [])}",
      len(topico2.get("comentarios") or []) == comentarios_depois)
check(f"e a âncora (que é NOSSA, o BCF não a carrega) sobrevive -> {topico2.get('ancora')}",
      (topico2.get("ancora") or {}).get("x") == 0.42)

status, erro = upload(
    "/api/prancheta/marcacoes/importar-bcf/", demo, {},
    arquivo=("arquivo", "marcacoes.bcfzip", bcfzip, "application/octet-stream"),
)
check(f"importar sem dizer a prancha de destino -> 400 (não adivinha) -> {status}", status == 400)

status, erro = upload(
    "/api/prancheta/marcacoes/importar-bcf/", demo, {"revisao": revisoes["dxf"]},
    arquivo=("arquivo", "quebrado.bcfzip", b"nao sou um zip", "application/octet-stream"),
)
check(f"BCF corrompido -> 400 com mensagem de usuário, não 500 -> {status}", status == 400)

# ---------------------------------------------------------------------------
print("== 12. A fila de decisão do cockpit ==")
status, acervo = req("GET", f"/api/prancheta/acervo/?obra={obra_id}", campo)
check(f"o acervo da obra numa chamada só -> {status} "
      f"({acervo.get('total_documentos')} documentos)", status == 200)
check(f"agrupado por disciplina (o eixo do carimbo) -> "
      f"{[d['disciplina'] for d in acervo.get('disciplinas') or []]}",
      len(acervo.get("disciplinas") or []) >= 1)

fila = acervo.get("requer_decisao") or {}
# **A divisão entre elas é o desenho, e por isso o teste é o CONJUNTO e não a
# contagem.** As quatro de conversão são separadas de propósito, uma por quem
# age (planta §11): `que_exigem_upgrade` o cliente resolve comprando,
# `aguardando_anexo` quem enviou resolve reenviando com os XREF, `sem_desenho`
# ninguém resolve (existe para ser subtraída, senão o badge vira ruído
# permanente) e o resto é nosso. Eram 7 até a PRA.1b partir a conversão que
# falhou nessas quatro; um `len(fila) == 7` transforma essa distinção — que é o
# produto — num número que quebra sem dizer o que mudou.
ESPERADAS = {
    "conversoes_aguardando_anexo", "conversoes_com_erro",
    "conversoes_que_exigem_upgrade", "conversoes_sem_desenho",
    "documentos_sem_revisao_vigente", "marcacoes_abertas",
    "marcacoes_atribuidas_a_mim", "marcacoes_em_revisao_superada",
    "revisoes_em_rascunho",
}
check(f"a fila declara as 9 perguntas do cockpit -> "
      f"faltando={sorted(ESPERADAS - set(fila))} a_mais={sorted(set(fila) - ESPERADAS)}",
      set(fila) == ESPERADAS)
check("e separa o que o cliente resolve comprando do que nós consertamos -> "
      f"erro={fila.get('conversoes_com_erro')} "
      f"upgrade={fila.get('conversoes_que_exigem_upgrade')}",
      "conversoes_com_erro" in fila and "conversoes_que_exigem_upgrade" in fila)
check(f"marcações abertas atribuídas a mim aparecem -> "
      f"abertas={fila.get('marcacoes_abertas')} minhas={fila.get('marcacoes_atribuidas_a_mim')}",
      fila.get("marcacoes_abertas", 0) >= 1)

# A pergunta que só existe quando acervo e marcação convivem: marcação viva sobre
# um desenho que já não vale. Publicar a R01 do DXF é o que a produz.
status, r01_dxf = upload(
    "/api/prancheta/revisoes/", demo,
    {"documento": documentos["dxf"], "revisao": "R01"},
    arquivo=("arquivo", "planta-amostra.dxf", AMOSTRAS[1][2], "application/octet-stream"),
)
req("POST", f"/api/prancheta/revisoes/{r01_dxf['revisao_id']}/publicar/", demo, {})
status, acervo2 = req("GET", f"/api/prancheta/acervo/?obra={obra_id}", demo)
fila2 = acervo2.get("requer_decisao") or {}
check(f"revisão nova sobre marcação aberta entra na fila -> "
      f"{fila2.get('marcacoes_em_revisao_superada')}",
      fila2.get("marcacoes_em_revisao_superada", 0) >= 1)

status, marcacao_superada = req("GET", f"/api/prancheta/marcacoes/{marcacao_id}/", demo)
check(f"e a própria marcação já diz que o desenho dela foi superado -> "
      f"{marcacao_superada.get('revisao_superada')}",
      marcacao_superada.get("revisao_superada") is True)

status, sem_obra = req("GET", "/api/prancheta/acervo/", demo)
check(f"acervo sem ?obra= -> 400 dizendo o que falta -> {status}", status == 400)

# ---------------------------------------------------------------------------
print("== 13. Reprocessar: CPU (e, na PRA.4, dinheiro) tem permissão própria ==")
status, negado = req("POST", f"/api/prancheta/revisoes/{revisoes['dxf']}/reprocessar/", campo, {})
check(f"o `campo` não dispara reconversão -> 403 -> {status}", status == 403)
status, aceito = req("POST", f"/api/prancheta/revisoes/{revisoes['dxf']}/reprocessar/", demo, {})
check(f"quem tem `conversao.reprocessar` -> 202 (é assíncrono, não 200) -> {status}",
      status == 202)
check(f"e diz o que enfileirou -> {(aceito or {}).get('agendadas')}",
      len((aceito or {}).get("agendadas") or []) >= 1)

# ---------------------------------------------------------------------------
print("== 14. Isolamento: o acervo de uma empresa não existe para a outra ==")
status, _ = req("GET", f"/api/prancheta/revisoes/{revisoes['pdf']}/", acme)
check(f"id de revisão do demo, token do acme -> 403 (nem chega ao objeto) -> {status}",
      status == 403)
status, headers, _corpo = bruto(url_arquivo, acme)
check(f"e o arquivo dela também -> {status}", status == 403)

# ---------------------------------------------------------------------------
print("== 15. PRA.5b: as duas portas que restavam, e o lote do acervo ==")
# Fecha o D75. O que se prova aqui não é "o upload funciona" — o `tests.py` já o
# prova — e sim que a porta única está no caminho REAL, atrás do gateway, com
# token de verdade: é ali que a PRA.5a descobriu que as recusas saíam como 500.

EXECUTAVEL = b"MZ\x90\x00" + b"\x00" * 2048
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 2048

status, ponto_mau = upload(
    f"/api/prancheta/marcacoes/{marcacao_id}/ponto-de-vista/", demo, {},
    arquivo=("snapshot", "recorte.png", EXECUTAVEL, "image/png"),
)
check(f"executável com nome de imagem NÃO vira snapshot -> 400 -> {status}", status == 400)

status, antes_pv = req("GET", f"/api/prancheta/marcacoes/{marcacao_id}/", demo)
status, ponto_bom = upload(
    f"/api/prancheta/marcacoes/{marcacao_id}/ponto-de-vista/", demo, {},
    arquivo=("snapshot", "recorte.png", PNG, "image/png"),
)
check(f"e o PNG de verdade continua entrando -> 201 -> {status}", status == 201)
check(f"com a URL do snapshot pela porta do motor -> {(ponto_bom or {}).get('snapshot_url')}",
      "/api/impexp/prancheta.marcacao/" in ((ponto_bom or {}).get("snapshot_url") or ""))

status, desenho_na_porta_errada = upload(
    "/api/prancheta/marcacoes/importar-bcf/", demo, {"revisao": revisoes["dxf"]},
    arquivo=("arquivo", "planta.dwg", DWG, "application/octet-stream"),
)
check(f"desenho na porta da marcação -> 400 com o ENDEREÇO certo, não a lista "
      f"de formatos -> {status}",
      status == 400 and "acervo" in str((desenho_na_porta_errada or {}).get("arquivo") or "").lower())

# --- o lote do acervo histórico (R18) --------------------------------------
LOTE = "/api/impexp/prancheta.acervo/importar-arquivos/"
# **As duas entregas precisam ser bytes DIFERENTES entre si e do que já está no
# acervo**, e descobrir isso foi útil: a primeira versão deste teste mandou o
# `DXF` puro, que a seção 4 já subiu nesta mesma obra, e o lote o classificou
# como `duplicada` — a idempotência por `hash` fazendo exatamente o que deve. O
# `999` é o grupo de comentário do DXF, então o arquivo continua válido.
def _entrega(marca):
    return b"999\n" + marca + b"\n" + DXF


status, lote = upload_lote(LOTE, demo, {"contexto": json.dumps({"obra": obra_id})}, [
    (f"{TAG}-LOTE_R00.dxf", f"TorreA/ARQ/{TAG}-LOTE_R00.dxf",
     _entrega(b"primeira entrega"), "image/vnd.dxf"),
    (f"{TAG}-LOTE_R01.dxf", f"TorreA/ARQ/{TAG}-LOTE_R01.dxf",
     _entrega(b"segunda entrega"), "image/vnd.dxf"),
])
check(f"a pasta do projetista entra em lote -> 201 -> {status}", status == 201)
check(f"e para na conferência, não no acervo -> {(lote or {}).get('status')}",
      (lote or {}).get("status") == "conferindo")
check(f"duas unidades de decisão, ambas novas -> novas={(lote or {}).get('novas')}",
      (lote or {}).get("novas") == 2)
if not (lote or {}).get("importacao_id"):
    fatal(f"o lote não chegou a existir: {lote}")

status, conferencia = req("GET", f"/api/impexp/importacoes/{lote['importacao_id']}/", demo)
palpites = [linha.get("valores") or {} for linha in (conferencia or {}).get("linhas") or []]
check(f"a conferência mostra o que a PLATAFORMA adivinhou (R18) -> "
      f"{[(p.get('codigo'), p.get('revisao'), p.get('disciplina')) for p in palpites]}",
      all(p.get("disciplina") == "arquitetura" for p in palpites)
      and sorted(p.get("revisao") for p in palpites) == ["R00", "R01"]
      and len({p.get("codigo") for p in palpites}) == 1)

status, aplicado = req("POST", f"/api/impexp/importacoes/{lote['importacao_id']}/aplicar/", demo)
check(f"confirmar aplica as duas -> {(aplicado or {}).get('aplicadas')} -> {status}",
      status == 200 and (aplicado or {}).get("aplicadas") == 2)

status, acervo_lote = req("GET", f"/api/prancheta/acervo/?obra={obra_id}", demo)
documento_lote = next(
    (d for disciplina in (acervo_lote.get("disciplinas") or [])
     for d in (disciplina.get("documentos") or [])
     if str(d.get("codigo", "")).startswith(f"{TAG}-LOTE")),
    None,
)
check("as duas entregas colapsam num documento só (é o que faz acervo virar "
      f"acervo) -> {(documento_lote or {}).get('codigo')} com "
      f"{(documento_lote or {}).get('total_revisoes')} revisões",
      documento_lote is not None and documento_lote.get("total_revisoes") == 2)
check(f"na disciplina que a PASTA declarou -> {(documento_lote or {}).get('disciplina')}",
      (documento_lote or {}).get("disciplina") == "arquitetura")
check(f"e ele nasce SEM vigente — publicar é outro verbo -> "
      f"{(documento_lote or {}).get('vigente')}",
      (documento_lote or {}).get("vigente") is None)

status, ja_no_acervo = upload_lote(
    LOTE, demo, {"contexto": json.dumps({"obra": obra_id})},
    [(f"{TAG}-REPETIDO.dxf", f"TorreA/ARQ/{TAG}-REPETIDO.dxf", DXF, "image/vnd.dxf")],
)
check(f"o desenho que JÁ está no acervo desta obra volta como duplicada, mesmo "
      f"com outro nome -> duplicadas={(ja_no_acervo or {}).get('duplicadas')}",
      (ja_no_acervo or {}).get("duplicadas") == 1)
req("POST", f"/api/impexp/importacoes/{(ja_no_acervo or {}).get('importacao_id')}/descartar/", demo)

status, executavel_no_lote = upload_lote(
    LOTE, demo, {"contexto": json.dumps({"obra": obra_id})},
    [(f"{TAG}-X.dwg", f"TorreA/ARQ/{TAG}-X.dwg", EXECUTAVEL, "application/octet-stream")],
)
check(f"executável renomeado NÃO entra pelo lote (o pior caminho do D75: "
      f"centenas de arquivos de uma vez) -> 400 -> {status}", status == 400)

status, sem_obra_lote = upload_lote(
    LOTE, demo, {"contexto": json.dumps({})},
    [(f"{TAG}-Y.dxf", f"TorreA/ARQ/{TAG}-Y.dxf", DXF, "image/vnd.dxf")],
)
check(f"lote sem obra de destino -> 400 antes de ler um byte -> {status}", status == 400)

status, desfeito = req("POST", f"/api/impexp/importacoes/{lote['importacao_id']}/desfazer/", demo)
check(f"desfazer devolve o acervo ao estado anterior -> "
      f"{(desfeito or {}).get('desfeitas')} -> {status}",
      status == 200 and (desfeito or {}).get("desfeitas") == 2)
status, acervo_depois = req("GET", f"/api/prancheta/acervo/?obra={obra_id}", demo)
check("e o documento do lote sai junto (foi ele que o criou)", not any(
    str(d.get("codigo", "")).startswith(f"{TAG}-LOTE")
    for disciplina in (acervo_depois.get("disciplinas") or [])
    for d in (disciplina.get("documentos") or [])
))

# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
verdes = sum(1 for p in passed if p)
print(f"PRA.8 — {verdes}/{len(passed)} verificações no stack vivo pelo gateway")
print("=" * 70)
if verdes != len(passed):
    print("\nFalhas:")
    sys.exit(1)
print("\nFaxina final…")
print(f"  {faxina()} documentos do E2E removidos")
sys.exit(0)
