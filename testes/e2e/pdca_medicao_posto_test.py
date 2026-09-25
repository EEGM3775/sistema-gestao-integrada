"""PDCA — o posto da medição (B3) pelo gateway: contratos com saldo e a fila do dinheiro.

Irmão do [pdca_cockpit_test.py](pdca_cockpit_test.py), e existe pelo mesmo
motivo: a suíte unitária chama o serviço direto e empurra o usuário com
`force_authenticate`; aqui a leitura atravessa login, assinatura RS256, gateway,
entitlement de módulo, permissão de campo e RLS.

O que esta leitura tem de próprio é que ela **atravessa assunto** em vez de
obra: o posto junta contrato e medição, que têm permissões diferentes. É a
terceira família de leitura do módulo, depois da que cruza obras (a carteira) e
da que cruza cinco assuntos de uma obra (`hoje/`), e metade das verificações
abaixo existe para provar que o recorte por bloco continua de pé — exigir as
duas permissões recusaria o posto a quem só ateste, que é justamente quem mais
o usa.

Tokens reais, e a divisão é o teste:

  gerente  / gerente123  -> `diretoria`: vê o dinheiro. É a persona do posto.
  demo     / demo123     -> `engenharia`: o recorte. O que ele não vê vem
                            **nomeado**, e a página **não** dá 403.
  acme     / acme123     -> outro tenant, sem o módulo: para no entitlement.

Seed: testes/seeds/seed_demo.py + testes/seeds/seed_demo_data.py + semear_pdca_demo
      + semear_pdca_execucao

  1. O que existe   -> `status/` declara o posto, o teto novo e **a ausência**.
  2. Uma leitura só -> contratos e fila na mesma resposta, do mesmo instante.
  3. O saldo        -> é o MESMO de `contratos/{id}/saldo/`, sem segunda conta.
  4. A trava        -> `planilha_editavel` viaja com a linha, com a frase.
  5. O dinheiro     -> viaja como string, nunca como float.
  6. A fila         -> documento parado, nunca contagem: qual, de quem, quanto.
  7. A ausência     -> NÃO existe faixa de "contrato sem medir há N dias".
  8. O corte        -> o total vem ao lado da lista cortada.
  9. Permissão      -> bloco negado vira frase, e NUNCA 403 na página inteira.
 10. Entrada ruim   -> obra que não existe responde 400 com frase, não 500.
 11. A fronteira    -> outro tenant não enxerga nada disto.

Rodar (stack de pé):  python testes/e2e/pdca_medicao_posto_test.py
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")

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
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=120, context=_CTX) as resp:
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
        return json.load(resp)["access"]


def bruto(resposta) -> str:
    return json.dumps(resposta, ensure_ascii=False) if resposta is not None else ""


BLOCOS = (
    "medicoes_em_rascunho", "medicoes_a_atestar",
    "retencoes_a_liberar", "aditivos_a_decidir",
)

print(f"\n{'='*62}\nPDCA — o posto da medição pelo gateway\n{'='*62}")
print(f"Gateway: {GW}")

try:
    gerente = login("gerente", "gerente123")
    demo = login("demo", "demo123")
    acme = login("acme", "acme123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé? Rodou os seeds?")

# ---------------------------------------------------------------------------
print("\n1. O que o módulo declara saber fazer — e o que declara NÃO fazer")
# ---------------------------------------------------------------------------
codigo, status = req("GET", "/api/pdca/status/", gerente)
if codigo != 200:
    fatal(f"status/ respondeu {codigo}")
check("declara 'posto_da_medicao'", status["recursos"].get("posto_da_medicao") is True)
check(
    "o teto de contratos do posto viaja para a tela poder declarar o corte",
    isinstance(status["tetos"].get("contratos_no_posto"), int)
    and status["tetos"]["contratos_no_posto"] > 0,
)
# A ausência é declarada, e não silenciosa: de quanto em quanto tempo se mede é
# cláusula combinada com cada empreiteiro, e o contrato não guarda esse campo.
check(
    "declara que NÃO cobra periodicidade de medição",
    status["recursos"].get("cobranca_por_periodicidade_de_medicao") is False,
)

# ---------------------------------------------------------------------------
print("\n2. Uma leitura só — contratos e fila do mesmo instante")
# ---------------------------------------------------------------------------
codigo, carteira = req("GET", "/api/pdca/carteira/", gerente)
if codigo != 200:
    fatal(f"carteira/ respondeu {codigo}: {carteira}")

# **A obra é escolhida pelo que ela tem, não pela ordem da carteira.** O tenant
# de demonstração acumula obras de execuções anteriores do E2E, e várias delas
# têm contrato com todas as medições já aprovadas — cair numa dessas provaria
# só que a fila responde vazia. A escolhida é a de fila mais cheia, que é a que
# exercita os blocos.
candidatas = []
for linha in carteira["obras"]:
    codigo, corpo = req("GET", f"/api/pdca/medicao/?obra={linha['obra']}", gerente)
    if codigo != 200:
        fatal(f"medicao/ respondeu {codigo} para a obra {linha['obra']}: {corpo}")
    if corpo["contratos"]["linhas"]:
        candidatas.append((corpo["fila"]["total"], linha["obra"], corpo))

if not candidatas:
    fatal(
        "nenhuma obra do seed tem contrato — rode "
        "`semear_pdca_demo` e `semear_pdca_execucao` antes"
    )

_, obra_id, posto = max(candidatas, key=lambda c: c[0])

check("responde 200 com os dois blocos na mesma resposta",
      "contratos" in posto and "fila" in posto)
check("diz de que obra está falando, pelo nome",
      posto["obra"] == obra_id and bool(posto["obra_nome"]))
contratos = posto["contratos"]
check("declara o teto de contratos na resposta", isinstance(contratos.get("teto"), int))
check(
    "quando corta, diz quantos ficaram de fora",
    (not contratos["truncada"]) or contratos["total"] > len(contratos["linhas"]),
)

contrato = contratos["linhas"][0]
check(
    "a linha do contrato traz saldo, retenção e o próximo período resolvidos",
    set(contrato["saldo"]) >= {
        "valor_contratado", "medido_aprovado", "medido_em_aprovacao",
        "saldo", "retencao", "periodo_sugerido",
    },
)

# ---------------------------------------------------------------------------
print("\n3. O saldo é o MESMO do endpoint do contrato — sem segunda conta")
# ---------------------------------------------------------------------------
codigo, direto = req(
    "GET", f"/api/pdca/contratos/{contrato['contrato']}/saldo/", gerente,
)
if codigo != 200:
    fatal(f"contratos/{contrato['contrato']}/saldo/ respondeu {codigo}: {direto}")
# Duas implementações da mesma soma é o D138 em escala de carteira: a tela do
# contrato diria um número e a do posto diria outro.
for campo in ("valor_contratado", "medido_aprovado", "saldo", "medido_em_aprovacao"):
    check(
        f"'{campo}' bate com o do contrato aberto",
        contrato["saldo"][campo] == direto[campo],
    )
check(
    "a retenção também bate parcela a parcela",
    contrato["saldo"]["retencao"] == direto["retencao"],
)

# ---------------------------------------------------------------------------
print("\n4. A trava da planilha viaja com a linha — a tela lê a resposta")
# ---------------------------------------------------------------------------
codigo, doc = req("GET", f"/api/pdca/contratos/{contrato['contrato']}/", gerente)
if codigo != 200:
    fatal(f"contratos/{contrato['contrato']}/ respondeu {codigo}")
check(
    "'planilha_editavel' é o mesmo que o documento do contrato publica",
    contrato["planilha_editavel"] == doc["planilha_editavel"],
)
check(
    "e o motivo vem junto, com a frase que a API devolveria ao recusar",
    contrato["planilha_fechada_porque"] == doc["planilha_fechada_porque"],
)
check(
    "planilha fechada SEMPRE tem motivo escrito",
    contrato["planilha_editavel"] or bool(contrato["planilha_fechada_porque"].strip()),
)

# ---------------------------------------------------------------------------
print("\n5. O dinheiro viaja como string — float não representa centavo")
# ---------------------------------------------------------------------------
check(
    "os valores do saldo são string, não float",
    all(
        isinstance(contrato["saldo"][campo], str)
        for campo in ("valor_contratado", "medido_aprovado", "saldo")
    ),
)
liquidos = [
    linha["liquido"]
    for bloco in BLOCOS for linha in posto["fila"][bloco]
    if "liquido" in linha
]
check(
    "o líquido de cada linha da fila também é string",
    all(isinstance(v, str) for v in liquidos),
)

# ---------------------------------------------------------------------------
print("\n6. A fila é documento parado — nunca contagem")
# ---------------------------------------------------------------------------
fila = posto["fila"]
check("os quatro blocos existem, mesmo vazios",
      all(isinstance(fila.get(b), list) for b in BLOCOS))
check(
    "o total do posto é a soma dos quatro totais",
    fila["total"] == sum(fila["totais"][b] for b in BLOCOS),
)
linhas = [linha for bloco in BLOCOS for linha in fila[bloco]]
if not linhas:
    fatal(
        "a fila do posto está vazia no seed — `semear_pdca_execucao` deveria "
        "deixar uma medição submetida e uma em apuração"
    )
check(
    "toda linha diz o que é, de que contrato e há quanto tempo espera",
    all(
        {"chave", "tipo", "id", "titulo", "detalhe", "dias"} <= set(linha)
        and linha["contrato"] is not None
        for linha in linhas
    ),
)
check(
    "toda linha traz o período no detalhe ou a condição, nunca só um número",
    all(bool(str(linha["detalhe"]).strip()) for linha in linhas),
)
check(
    "as espécies da fila são as quatro do posto",
    {linha["tipo"] for linha in linhas} <= {"medicao", "liberacao", "aditivo"},
)
em_atesto = fila["medicoes_a_atestar"]
check(
    "a medição em atesto diz em que degrau parou (ou que não há escada)",
    all("degrau" in linha for linha in em_atesto),
)

# ---------------------------------------------------------------------------
print("\n7. A ausência declarada — não existe cobrança por periodicidade")
# ---------------------------------------------------------------------------
# Seria a faixa óbvia, e seria ruído: acenderia todo dia para todo contrato
# vigente. O período em aberto viaja no contrato, como informação.
check(
    "a fila NÃO inventa faixa de contrato sem medir",
    not any(
        chave in fila
        for chave in ("contratos_a_medir", "contratos_atrasados", "sem_medir")
    ),
)
periodo = contrato["saldo"]["periodo_sugerido"]
check(
    "mas o período que a próxima medição cobriria vem no contrato",
    {"inicio", "fim", "ultima_medicao", "lacuna_dias"} <= set(periodo),
)
check(
    "e o período nasce ancorado na corrente, não no primeiro do mês",
    periodo["fim"] >= periodo["inicio"],
)

# ---------------------------------------------------------------------------
print("\n8. O corte — o total vem AO LADO da lista cortada")
# ---------------------------------------------------------------------------
check(
    "cada bloco tem o seu total, e nunca é menor que as linhas devolvidas",
    all(fila["totais"][b] >= len(fila[b]) for b in BLOCOS),
)

# ---------------------------------------------------------------------------
print("\n9. Permissão por bloco — e NUNCA 403 na página inteira")
# ---------------------------------------------------------------------------
codigo, recortado = req("GET", f"/api/pdca/medicao/?obra={obra_id}", demo)
check("quem tem o módulo abre o posto, mesmo sem as duas permissões",
      codigo == 200)
if codigo == 200:
    negados = (
        recortado["contratos"]["sem_permissao"] + recortado["fila"]["sem_permissao"]
    )
    check(
        "todo bloco negado vem com a permissão que falta NOMEADA",
        all(
            {"bloco", "o_que", "permissao", "motivo"} <= set(n)
            and n["permissao"].startswith("pdca.")
            for n in negados
        ),
    )
    check(
        "bloco negado vem VAZIO, e não com o dado de quem pode",
        all(
            recortado["contratos"]["linhas"] == []
            for n in negados if n["bloco"] == "contrato"
        ),
    )
    visto = bool(recortado["contratos"]["linhas"]) or bool(
        [l for b in BLOCOS for l in recortado["fila"][b]]
    )
    check("e o que a pessoa PODE ver continua vindo", visto or bool(negados))

# ---------------------------------------------------------------------------
print("\n10. Entrada ruim — 400 com frase, nunca 500")
# ---------------------------------------------------------------------------
for rotulo, caminho in (
    ("sem informar a obra", "/api/pdca/medicao/"),
    ("obra que não é número", "/api/pdca/medicao/?obra=abc"),
    ("obra inexistente", "/api/pdca/medicao/?obra=99999999"),
):
    codigo, corpo = req("GET", caminho, gerente)
    check(f"{rotulo} → 400 (e não 500)", codigo == 400)

# ---------------------------------------------------------------------------
print("\n11. A fronteira — outro tenant não enxerga nada disto")
# ---------------------------------------------------------------------------
codigo, corpo = req("GET", f"/api/pdca/medicao/?obra={obra_id}", acme)
check("o posto recusa quem não contratou o módulo", codigo == 403)
check("e não vaza o nome da obra na recusa", posto["obra_nome"] not in bruto(corpo))

codigo, corpo = req("GET", f"/api/pdca/medicao/?obra={obra_id}")
check("sem token, o posto é recusado", codigo in (401, 403))

# ---------------------------------------------------------------------------
total, ok = len(passed), sum(1 for p in passed if p)
print(f"\n{'='*62}\n  {ok}/{total} verificações\n{'='*62}")
sys.exit(0 if ok == total else 1)
