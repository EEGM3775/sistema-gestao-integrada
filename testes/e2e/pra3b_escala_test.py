"""PRA.3b pelo gateway — a prancha nasce medindo em metro, e o metro tem dono.

    python3 testes/e2e/pra3b_escala_test.py            # DXF gerado, deterministico
    python3 testes/e2e/pra3b_escala_test.py /caminho/planta.dwg   # arquivo real

Sem argumento, sobe um DXF que **declara milimetros** com um retangulo de
1000 x 500: a folha renderizada tem de medir 1,02 m de largura (1000 + 2 x 10 mm
de margem), numero conferivel a mao. Com um arquivo real, observa o que o acervo
do cliente traz de fato — e os dois caminhos sao cobrados, porque os dois sao
comportamento:

- **declarou unidade plausivel** -> `escala_origem = desenho`, medida em metro
  calculada pelo servidor;
- **nao declarou, ou declarou algo que daria uma prancha de 143 km** -> fica
  **sem escala**, a medida sai em fracao da largura e a tela diz isso. Adivinhar
  metro aqui seria a unica falha deste modulo que vira parede no lugar errado.

Depois calibra a mao e reprocessa: a calibracao humana e **soberana**, e nenhuma
reconversao a sobrescreve (a regra do pin `exata` do MAP.6).

Pre-requisito: stack `--profile full` de pe e os seeds rodados (demo/demo123).
"""
import json, os, ssl, sys, time, urllib.request, urllib.error, uuid

BASE = "http://localhost:8090"


def dxf_em_milimetros(largura=1000.0, altura=500.0) -> bytes:
    """DXF R12 que DECLARA milimetros — o caso deterministico da fatia.

    Com `$INSUNITS = 4` e um retangulo de 1000 x 500 unidades, a folha
    renderizada mede 1000 + 2x10 mm de margem = 1,02 m de largura real. Esse
    numero e verificavel a mao, e e o que o teste cobra do servidor.
    """
    cantos = [(0.0, 0.0), (largura, 0.0), (largura, altura), (0.0, altura)]
    linhas = [
        "0", "SECTION", "2", "HEADER",
        "9", "$ACADVER", "1", "AC1009",
        "9", "$INSUNITS", "70", "4",
        "9", "$EXTMIN", "10", "0.0", "20", "0.0", "30", "0.0",
        "9", "$EXTMAX", "10", f"{largura}", "20", f"{altura}", "30", "0.0",
        "0", "ENDSEC",
        "0", "SECTION", "2", "ENTITIES",
    ]
    for i, (x1, y1) in enumerate(cantos):
        x2, y2 = cantos[(i + 1) % len(cantos)]
        linhas += ["0", "LINE", "8", "PAREDE",
                   "10", f"{x1}", "20", f"{y1}", "30", "0.0",
                   "11", f"{x2}", "21", f"{y2}", "31", "0.0"]
    linhas += ["0", "ENDSEC", "0", "EOF"]
    return ("\r\n".join(linhas) + "\r\n").encode("ascii")


ARQUIVO = sys.argv[1] if len(sys.argv) > 1 else None
ssl._create_default_https_context = ssl._create_unverified_context

def req(metodo, caminho, token=None, corpo=None, arquivo=None):
    url = BASE + caminho
    dados, headers = None, {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if arquivo:
        limite = uuid.uuid4().hex
        nome, conteudo = arquivo
        partes = []
        for chave, valor in (corpo or {}).items():
            partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{chave}\"\r\n\r\n{valor}\r\n".encode())
        partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"arquivo\"; filename=\"{nome}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode())
        partes.append(conteudo)
        partes.append(f"\r\n--{limite}--\r\n".encode())
        dados = b"".join(partes)
        headers["Content-Type"] = f"multipart/form-data; boundary={limite}"
    elif corpo is not None:
        dados = json.dumps(corpo).encode()
        headers["Content-Type"] = "application/json"
    pedido = urllib.request.Request(url, data=dados, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(pedido, timeout=120) as r:
            texto = r.read().decode("utf-8", "ignore")
            return r.status, (json.loads(texto) if texto.strip().startswith(("{", "[")) else texto)
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "ignore")
        return e.code, (json.loads(texto) if texto.strip().startswith(("{", "[")) else texto)

falhas = []
def checar(nome, condicao, extra=""):
    print(("  ok   " if condicao else "  FALHA ") + nome + ("" if condicao else f"  <- {extra}"))
    if not condicao:
        falhas.append(nome)

status, corpo = req("POST", "/auth/login/", corpo={"username": "demo", "password": "demo123"})
token = (corpo or {}).get("access") if status == 200 else None
if not token:
    print(f"login falhou: {status} {corpo}"); sys.exit(1)

status, obras = req("GET", "/api/obras/?page_size=1", token)
lista = obras["results"] if isinstance(obras, dict) else obras
obra = lista[0]["obra_id"]

codigo = f"PRA3B-{uuid.uuid4().hex[:6].upper()}"
status, doc = req("POST", "/api/prancheta/documentos/", token, {
    "obra": obra, "codigo": codigo, "titulo": "Escala do desenho (PRA.3b)",
    "disciplina": "arquitetura", "projetista": "acervo real"})
if status != 201:
    print(f"documento falhou: {status} {doc}"); sys.exit(1)

if ARQUIVO:
    with open(ARQUIVO, "rb") as f:
        conteudo = f.read()
    nome_arquivo = os.path.basename(ARQUIVO)
    print(f"\nArquivo real do acervo: {nome_arquivo} ({len(conteudo)/1e6:.1f} MB)")
    esperado_m = None
else:
    conteudo = dxf_em_milimetros()
    nome_arquivo = "planta-em-milimetros.dxf"
    esperado_m = 1.02  # 1000 mm de desenho + 2 x 10 mm de margem
    print(f"\nDXF gerado que declara milimetros — esperado: {esperado_m} m de largura")

status, rev = req("POST", "/api/prancheta/revisoes/", token,
                  {"documento": doc["documento_id"], "revisao": "R01"},
                  arquivo=(nome_arquivo, conteudo))
if status != 201:
    print(f"upload falhou: {status} {rev}"); sys.exit(1)
rid = rev["revisao_id"]

print("\n1) O que o desenho declarou, e o que o servidor fez com isso")
# A REGUA E DA FOLHA, nao da revisao (PRA.1c): quando uma revisao passou a poder
# trazer varios desenhos, uma escala por revisao descreveria no maximo um deles —
# e em silencio para os outros. Este teste lia a escala da revisao e calibrava em
# `revisoes/{id}/calibrar`, de antes da mudanca; batia em 404 e em campo vazio.
escala = None
for _ in range(90):
    time.sleep(4)
    status, atual = req("GET", f"/api/prancheta/revisoes/{rid}/", token)
    derivadas = atual.get("derivadas") or []
    estados = {d["estado"] for d in derivadas}
    if derivadas and not (estados & {"pendente", "lendo", "convertendo"}):
        escala = atual
        break
checar("a conversao terminou", escala is not None)

did = None
if escala:
    status, folhas = req("GET", f"/api/prancheta/desenhos/?revisao={rid}", token)
    linhas = folhas.get("results") if isinstance(folhas, dict) else folhas
    checar("a revisao rendeu ao menos uma folha", bool(linhas), folhas)
    if linhas:
        did = linhas[0]["desenho_id"]
        # Daqui em diante a escala lida e a DA FOLHA — a revisao nao a carrega mais.
        escala = {**escala, **{k: v for k, v in linhas[0].items() if k.startswith("escala_")}}
if escala:
    memoria = {}
    for d in escala.get("derivadas") or []:
        memoria.update(d.get("memoria") or {})
    print(f"       $INSUNITS={memoria.get('unidades_desenho')} "
          f"({memoria.get('unidades_rotulo') or 'nao declarada'})")

    if escala.get("escala_valor"):
        # Caminho A: o desenho declarou unidade plausivel.
        checar("escala_origem = desenho", escala.get("escala_origem") == "desenho",
               escala.get("escala_origem"))
        checar("a unidade lida ficou registrada",
               bool((escala.get("escala_referencia") or {}).get("unidades_rotulo")))
        print(f"       largura real da folha: {escala['escala_valor']} m")
        if esperado_m is not None:
            checar(f"a conta bate com o desenho ({esperado_m} m)",
                   abs(escala["escala_valor"] - esperado_m) < 0.001, escala["escala_valor"])
    else:
        # Caminho B: sem unidade, ou unidade que daria tamanho absurdo. A regra e
        # nao ter regua — e DIZER isso, em vez de escrever metro adivinhado.
        checar("sem unidade utilizavel, a prancha fica SEM escala",
               escala.get("escala_origem") == "", escala.get("escala_origem"))
        if memoria.get("escala_recusada"):
            print(f"       recusada: daria {memoria['escala_recusada']:.0f} m de largura")

    print("\n2) A medida sai calculada pelo servidor, na unidade que ele pode provar")
    status, medicao = req("POST", "/api/prancheta/medicoes/", token, {
        "revisao": rid, "tipo": "distancia",
        "pontos": [{"x": 0.2, "y": 0.5}, {"x": 0.7, "y": 0.5}],
        "valor": 999, "unidade": "km"})
    checar("medicao aceita", status == 201, medicao)
    if status == 201:
        if escala.get("escala_valor"):
            esperado = 0.5 * escala["escala_valor"]
            checar("valor calculado pelo servidor (999 ignorado)",
                   abs(medicao["valor"] - esperado) < 0.01, f"{medicao['valor']} != {esperado}")
            checar("unidade e metro", medicao["unidade"] == "m", medicao["unidade"])
            checar("carimbou a escala usada",
                   abs((medicao.get("escala_aplicada") or 0) - escala["escala_valor"]) < 1e-6)
        else:
            checar("sem escala, o valor sai em fracao da largura",
                   abs(medicao["valor"] - 0.5) < 0.01, medicao["valor"])
            checar("e a unidade sai vazia, declarando que nao ha metro",
                   medicao["unidade"] == "", repr(medicao["unidade"]))

    print("\n3) A calibracao humana e soberana")
    status, calibrada = req("POST", f"/api/prancheta/desenhos/{did}/calibrar/", token, {
        "a": {"x": 0.25, "y": 0.5}, "b": {"x": 0.75, "y": 0.5},
        "distancia_real": 3.5, "unidade": "m"})
    checar("calibrar respondeu 200", status == 200, calibrada)
    if status == 200:
        checar("escala_origem virou calibrada", calibrada.get("escala_origem") == "calibrada")
        checar("valor passou a ser o humano (7,00 m na largura)",
               abs(calibrada["escala_valor"] - 7.0) < 1e-6, calibrada.get("escala_valor"))
    status, _ = req("POST", f"/api/prancheta/revisoes/{rid}/reprocessar/", token, {})
    checar("reprocessar aceito", status in (202, 200), status)
    for _ in range(60):
        time.sleep(4)
        status, depois = req("GET", f"/api/prancheta/revisoes/{rid}/", token)
        estados = {d["estado"] for d in (depois.get("derivadas") or [])}
        if not (estados & {"pendente", "lendo", "convertendo"}):
            break
    # Reler a FOLHA, e relendo a lista em vez de reusar o id: quem cria e apaga
    # desenho e o motor, e e exatamente por a reconversao poder refazer a folha
    # que este teste existe — a regua humana tem de sobreviver a isso.
    status, folhas = req("GET", f"/api/prancheta/desenhos/?revisao={rid}", token)
    linhas = folhas.get("results") if isinstance(folhas, dict) else folhas
    depois = (linhas or [{}])[0]
    checar("reconversao NAO sobrescreveu a calibracao",
           abs((depois.get("escala_valor") or 0) - 7.0) < 1e-6, depois.get("escala_valor"))
    checar("procedencia continua calibrada", depois.get("escala_origem") == "calibrada")

req("DELETE", f"/api/prancheta/documentos/{doc['documento_id']}/", token)
print("\n" + ("TODAS OK" if not falhas else f"FALHAS: {falhas}"))
sys.exit(1 if falhas else 0)
