"""PRA.1d pelo gateway — o teto age, a escada entrega, e a folha diz o que e.

    python3 testes/e2e/pra1d_hachura_test.py

Prova no stack vivo o que a su�te prova em unidade: que a conversao passou a ter
**orcamento** (D57) e que estourar o orcamento nao e mais um worker morto, e sim
uma prancha pior que se declara.

Sobe DUAS pranchas pelo gateway, e o par e o teste:

- **normal** — hachura comum. Converte como sempre e declara `hachura:
  "completa"`. E a garantia de que nada regrediu: a folha que hoje abre bem nao
  muda de aparencia por causa desta fatia;
- **pesada** — varias hachuras de padrao fino sobre area grande, que e a forma
  exata do arquivo do acervo que expandiu ate 62 GB. Ela **nao pode** derrubar
  nada: ou cabe no orcamento, ou desce um degrau e volta em `contorno`.

**O que este teste NAO aceita como sucesso:** derivada presa em `convertendo`
(worker morto sem rastro, o cenario que o D57 descreve), `motor_insuficiente` na
prancha pesada (seria cobrar do cliente por um limite nosso) e folha degradada
que nao se declara na tela.

**Carga declarada:** a prancha pesada pode alocar ate o teto de
`PRANCHETA_CONVERSAO_MEMORIA_MB` (1536 MB de fabrica) dentro do
`worker-conversao`, que o compose limita a 3 GB e 2 CPUs. O consumo e limitado
por construcao — e provar isso e justamente o objetivo.

**Por que a amostra usa `ezdxf`**, contra a convencao do `amostras_pra8.py` (que
escreve DXF a mao para rodar em clone limpo): um `HATCH` de padrao tem definicao
de padrao, caminho de contorno e ponto-semente, e um group code errado faz o
`ezdxf` **ignorar a entidade em silencio** — o teste passaria sem ter desenhado
hachura nenhuma, que e o unico jeito de este teste especifico mentir. O `ezdxf` e
dependencia declarada do backend (`requirements.txt`), entao qualquer ambiente de
desenvolvimento o tem.

Pre-requisito: stack `--profile full` de pe (incluindo o **worker-conversao**) e
os seeds rodados (demo/demo123).
"""
import json, ssl, sys, time, urllib.error, urllib.request, uuid
from _sessao import cabecalhos, da_resposta
from _segundo_fator import entrar

BASE = "http://localhost:8090"
#: Quanto esperar a conversao. Generoso de proposito: a prancha pesada tem de
#: percorrer o orcamento inteiro (300 s de fabrica) ANTES de descer o degrau, e
#: um timeout curto aqui leria "ainda convertendo" como falha.
ESPERA_MAXIMA_S = 420

try:
    import ezdxf
except ImportError:
    print("ezdxf nao instalado — ele gera as amostras deste teste "
          "(veja o cabecalho). `pip install ezdxf`")
    sys.exit(1)

ssl._create_default_https_context = ssl._create_unverified_context


def req(metodo, caminho, token=None, corpo=None, arquivo=None):
    url = BASE + caminho
    dados, headers = None, {}
    if token:
        headers.update(cabecalhos(token))
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
        with urllib.request.urlopen(pedido, timeout=180) as r:
            texto = r.read().decode("utf-8", "ignore")
            return r.status, (json.loads(texto) if texto.strip().startswith(("{", "[")) else texto)
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "ignore")
        return e.code, (json.loads(texto) if texto.strip().startswith(("{", "[")) else texto)


falhas = []


def checar(nome, condicao, extra=""):
    print(("  ok    " if condicao else "  FALHA ") + nome + ("" if condicao else f"  <- {extra}"))
    if not condicao:
        falhas.append(nome)


# ---------------------------------------------------------------------------
# As amostras
# ---------------------------------------------------------------------------
def dxf(hachuras: int, lado: float, escala: float) -> bytes:
    """Uma planta com `hachuras` areas hachuradas de `lado` unidades.

    `escala` e o que decide o custo: e a distancia entre as linhas do padrao, e o
    numero de segmentos cresce com (lado / escala)^2. E o mesmo mecanismo do
    arquivo do acervo — padrao fino sobre area grande —, com o botao a mostra.
    """
    import io

    modelo = ezdxf.new("R2010", setup=True)
    espaco = modelo.modelspace()
    for i in range(hachuras):
        x = i * lado * 1.2
        hachura = espaco.add_hatch(color=7)
        hachura.set_pattern_fill("ANSI31", scale=escala)
        hachura.paths.add_polyline_path(
            [(x, 0), (x + lado, 0), (x + lado, lado), (x, lado)], is_closed=True,
        )
        # Traco que NAO e hachura: e ele que tem de sobreviver ao degrau. Uma
        # folha degradada que perdesse o desenho junto seria pior que a falha.
        espaco.add_line((x, 0), (x + lado, lado))

    fluxo = io.StringIO()
    modelo.write(fluxo)
    return fluxo.getvalue().encode("utf-8")


def subir(token, obra, nome, conteudo, titulo):
    codigo = f"PRA1D-{uuid.uuid4().hex[:6].upper()}"
    status, doc = req("POST", "/api/prancheta/documentos/", token, {
        "obra": obra, "codigo": codigo, "titulo": titulo,
        "disciplina": "arquitetura", "projetista": "PRA.1d"})
    if status != 201:
        print(f"documento falhou: {status} {doc}")
        sys.exit(1)
    status, rev = req("POST", "/api/prancheta/revisoes/", token,
                      {"documento": doc["documento_id"], "revisao": "R01"},
                      arquivo=(nome, conteudo))
    if status != 201:
        print(f"upload falhou: {status} {rev}")
        sys.exit(1)
    return rev["revisao_id"]


def esperar(token, rid):
    """Espera a conversao sair dos estados de transito. Devolve (revisao, segundos)."""
    inicio = time.time()
    while time.time() - inicio < ESPERA_MAXIMA_S:
        time.sleep(4)
        status, atual = req("GET", f"/api/prancheta/revisoes/{rid}/", token)
        derivadas = atual.get("derivadas") or []
        estados = {d["estado"] for d in derivadas}
        if derivadas and not (estados & {"pendente", "lendo", "convertendo"}):
            return atual, time.time() - inicio
    return None, time.time() - inicio


def memoria_de(revisao):
    memoria = {}
    for d in revisao.get("derivadas") or []:
        memoria.update(d.get("memoria") or {})
    return memoria


# ---------------------------------------------------------------------------
token = entrar(BASE, "demo", "demo123")  # o cookie da sessão (BFF, fase 5)
if not token:
    print("login falhou")
    sys.exit(1)

status, obras = req("GET", "/api/obras/?page_size=1", token)
lista = obras["results"] if isinstance(obras, dict) else obras
obra = lista[0]["obra_id"]

print("\n1) A prancha normal — a garantia de que NADA regrediu")
leve = dxf(hachuras=2, lado=200.0, escala=1.0)
print(f"       amostra: 2 hachuras, padrao normal ({len(leve)/1024:.0f} KB)")
rid = subir(token, obra, "planta-hachura-normal.dxf", leve, "Hachura normal (PRA.1d)")
revisao, segundos = esperar(token, rid)
checar("a conversao terminou", revisao is not None, f"{segundos:.0f}s")
if revisao:
    derivadas = revisao.get("derivadas") or []
    memoria = memoria_de(revisao)
    print(f"       convergiu em {segundos:.0f}s · hachura={memoria.get('hachura')} "
          f"· hachuras={memoria.get('hachuras')}")
    checar("a folha ficou pronta", any(d["estado"] == "pronto" for d in derivadas),
           str({d["estado"] for d in derivadas}))
    checar("declarou hachura COMPLETA", memoria.get("hachura") == "completa",
           memoria.get("hachura"))
    checar("o censo contou as duas hachuras", memoria.get("hachuras") == 2,
           memoria.get("hachuras"))
    aviso = None
    for d in derivadas:
        aviso = aviso or d.get("aviso")
    checar("prancha normal NAO gera aviso de hachura",
           not (aviso or {}).get("codigo") == "hachura_simplificada", aviso)

print("\n2) A prancha pesada — o teto age, e o degrau entrega")
print("       (pode alocar ate 1536 MB dentro do worker-conversao, que o compose")
print("        limita a 3 GB e 2 CPUs — o consumo e limitado por construcao)")
pesada = dxf(hachuras=8, lado=4000.0, escala=0.004)
print(f"       amostra: 8 hachuras de padrao fino sobre area grande ({len(pesada)/1024:.0f} KB)")
rid = subir(token, obra, "planta-hachura-pesada.dxf", pesada, "Hachura pesada (PRA.1d)")
revisao, segundos = esperar(token, rid)

checar("a conversao terminou (nao ficou presa em 'convertendo')",
       revisao is not None, f"passou de {ESPERA_MAXIMA_S}s — worker morto sem rastro e o D57")
if revisao:
    derivadas = revisao.get("derivadas") or []
    memoria = memoria_de(revisao)
    estados = {d["estado"] for d in derivadas}
    motivos = {d.get("erro_motivo") for d in derivadas if d.get("erro_motivo")}
    print(f"       convergiu em {segundos:.0f}s · estados={estados} "
          f"· hachura={memoria.get('hachura')} · motivos={motivos or '{}'}")

    # O desfecho aceitavel e um dos dois: coube (e a folha e fiel), ou nao coube
    # e desceu o degrau. O que NAO pode e a linha ficar sem desfecho.
    checar("nenhuma derivada ficou em transito",
           not (estados & {"pendente", "lendo", "convertendo"}), str(estados))

    if memoria.get("hachura") == "contorno":
        print("       -> ESTOUROU o orcamento e desceu o degrau (o caminho da fatia)")
        checar("a folha ficou pronta mesmo tendo estourado",
               any(d["estado"] == "pronto" for d in derivadas), str(estados))

        # A folha degradada tem de ser uma folha DE VERDADE: baixa-se pela porta
        # gateada (a mesma da PRA.2) e o desenho que nao e hachura tem de estar
        # la. Um degrau que devolvesse folha vazia seria pior que a falha
        # honesta, porque ninguem desconfia de uma folha que abriu.
        url = next((d.get("arquivo_url") for d in derivadas if d.get("arquivo_url")), None)
        checar("a folha degradada tem arquivo para abrir", bool(url), str(derivadas[:1]))
        if url:
            caminho = url.split(BASE, 1)[-1] if url.startswith("http") else url
            status_svg, svg = req("GET", caminho, token)
            texto = svg if isinstance(svg, str) else str(svg)
            checar("a porta gateada serve a folha", status_svg == 200, status_svg)
            checar("o traco que nao e hachura sobreviveu", "<path" in texto,
                   f"{len(texto)} bytes")
        aviso = None
        for d in derivadas:
            aviso = aviso or d.get("aviso")
        checar("a tela declara a hachura simplificada",
               (aviso or {}).get("codigo") == "hachura_simplificada", aviso)
        checar("o aviso afirma que nada foi omitido",
               "omitido" in ((aviso or {}).get("mensagem") or ""), aviso)
    elif "recurso_excedido" in motivos:
        print("       -> estourou nos DOIS degraus (aceitavel: o erro e legivel)")
        checar("recurso_excedido NAO virou upsell",
               "motor_insuficiente" not in motivos, str(motivos))
        for d in derivadas:
            if d.get("erro_motivo") == "recurso_excedido":
                checar("a frase explica o limite, sem culpar o arquivo",
                       "limite" in (d.get("erro_detalhe") or "").lower()
                       or "processamento" in (d.get("erro_detalhe") or "").lower(),
                       d.get("erro_detalhe"))
                break
    else:
        print(f"       -> coube no orcamento sem degradar (hachura={memoria.get('hachura')})")
        checar("coube, e a folha esta fiel",
               memoria.get("hachura") in {"completa", "parcial"}, memoria.get("hachura"))

    # Vale nos tres desfechos: o limite e NOSSO, e nunca pode virar venda.
    checar("nenhum desfecho virou 'motor_insuficiente'",
           "motor_insuficiente" not in motivos, str(motivos))

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "tudo verde"))
sys.exit(1 if falhas else 0)
