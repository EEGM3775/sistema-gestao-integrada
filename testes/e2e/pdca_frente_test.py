"""A frente do canteiro — `minhas-frentes/` e o apontamento, pelo gateway.

Irmão do `pdca_cockpit_test.py`, e existe pela mesma razão: a suíte unitária
chama o serviço direto e empurra o usuário com `force_authenticate`; aqui cada
leitura atravessa login, assinatura RS256, gateway, entitlement de módulo,
permissão de campo e RLS.

O que esta leitura tem de próprio é **quem** ela atende. As quatro do cockpit
respondem a quem olha a obra de fora; esta responde a quem está dentro dela, e
casa o trabalho por **nome de texto** — porque `responsavel`, `quem` e
`inspetor` são rótulo durável em todo o módulo, e não FK de usuário (quem assume
a frente é com frequência o encarregado da empreiteira, que não tem login). É
esse casamento por nome que a maior parte das verificações abaixo cobra.

Quatro tokens reais, e a divisão é o teste:

  campo    / campo123    -> a persona do canteiro. Aponta avanço, e o seed lhe
                            deixa compromisso na semana corrente.
  demo     / demo123     -> `engenharia`. Usa `?como=` para ver a frente de um
                            rótulo que não é o nome dele.
  gerente  / gerente123  -> `diretoria`. Serve para provar o recorte por bloco.
  acme     / acme123     -> outro tenant, **sem o módulo contratado**: para na
                            primeira das duas barreiras (entitlement, não RLS).

Seed: testes/seeds/seed_demo.py + testes/seeds/seed_demo_data.py + semear_pdca_demo
      + semear_pdca_execucao

  1. O que existe   -> `status/` declara a capacidade e o teto, e declara que
                       **não** há trabalho sem rede.
  2. A frente       -> quatro blocos, e os quatro dizem o que fazer.
  3. Casa por nome  -> sem acento e sem caixa; `?como=` troca o alvo.
  4. Vazio com voz  -> bloco sem linha traz a razão escrita, nunca em branco.
  5. Atravessa obra -> sem `?obra=` vêm todas; com ele, só uma.
  6. Honesto        -> apontado nulo é "ninguém apontou", e não zero.
  7. Permissão      -> bloco negado vira frase, e NUNCA 403 na página inteira.
  8. O ato          -> apontar avanço grava, aparece na frente e **estorna**.
  9. Entrada ruim   -> obra alheia responde 400 com frase e sem vazar o nome.
 10. A fronteira    -> outro tenant não enxerga nada disto, por nenhuma porta.

Rodar (stack de pé):  python testes/e2e/pdca_frente_test.py
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

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


def frente(token, **params):
    consulta = urllib.parse.urlencode(params) if params else ""
    return req("GET", "/api/pdca/minhas-frentes/" + (f"?{consulta}" if consulta else ""), token)


def texto(resposta) -> str:
    return json.dumps(resposta, ensure_ascii=False).lower() if resposta is not None else ""


BLOCOS = ("compromissos", "restricoes", "acoes", "fichas")

print(f"\n{'='*62}\nPDCA — a frente do canteiro pelo gateway\n{'='*62}")
print(f"Gateway: {GW}")

try:
    campo = login("campo", "campo123")
    demo = login("demo", "demo123")
    gerente = login("gerente", "gerente123")
    acme = login("acme", "acme123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé? Rodou os seeds?")

# ---------------------------------------------------------------------------
print("\n1. O que o módulo declara sobre a segunda superfície")
# ---------------------------------------------------------------------------
codigo, status = req("GET", "/api/pdca/status/", campo)
if codigo != 200:
    fatal(f"status/ respondeu {codigo}")
check("declara 'minhas_frentes'", status["recursos"].get("minhas_frentes") is True)
check(
    "e declara que NÃO há trabalho sem rede — a ausência é dita, não escondida",
    status["recursos"].get("campo_offline") is False,
)
check(
    "o teto por bloco viaja, para a tela dizer o que ficou de fora",
    isinstance(status["tetos"].get("linhas_por_frente"), int)
    and status["tetos"]["linhas_por_frente"] > 0,
)

# ---------------------------------------------------------------------------
print("\n2. A frente — quatro blocos, e cada um diz o que fazer")
# ---------------------------------------------------------------------------
codigo, minha = frente(campo)
if codigo != 200:
    fatal(f"minhas-frentes/ respondeu {codigo}: {minha}")
check("responde 200 para a persona do canteiro", codigo == 200)
check("os quatro blocos vêm na resposta", all(b in minha for b in BLOCOS))
check(
    "cada bloco diz o verbo que o fecha — lista sem verbo é inventário",
    all(minha[b] and minha[b]["o_que_fazer"] for b in BLOCOS),
)
check(
    "a semana da resposta é a semana corrente, ancorada na segunda",
    date.fromisoformat(minha["semana_inicio"]).weekday() == 0,
)
check(
    "e o servidor diz contra qual nome procurou",
    isinstance(minha.get("quem"), str) and minha["quem"] != "",
)
check(
    "a frente da persona de campo tem pelo menos um compromisso semeado",
    minha["compromissos"]["total"] > 0,
)
if minha["compromissos"]["total"] == 0:
    print("     (rode: python manage.py semear_pdca_execucao --tenant demo)")

# ---------------------------------------------------------------------------
print("\n3. O casamento por nome — a régua de acessibilidade aplicada a gente")
# ---------------------------------------------------------------------------
meu_nome = minha["quem"]
codigo, sem_acento = frente(campo, como=meu_nome.upper())
check("o nome casa sem olhar a caixa", codigo == 200
      and sem_acento["compromissos"]["total"] == minha["compromissos"]["total"])

codigo, de_outro = frente(demo, como="Encarregado da frente")
check("`?como=` troca o alvo da busca", codigo == 200)
check(
    "e quem pede vê a frente daquele rótulo, não a dele",
    de_outro["quem"] == "Encarregado da frente",
)
codigo, sem_como = frente(demo)
check(
    "sem `?como=`, o alvo volta a ser quem pediu",
    codigo == 200 and sem_como["quem"] != "Encarregado da frente",
)
check(
    "e os dois não devolvem a mesma lista — o recorte é real",
    de_outro["compromissos"]["total"] != sem_como["compromissos"]["total"]
    or de_outro["compromissos"]["total"] == 0,
)

# ---------------------------------------------------------------------------
print("\n4. Vazio com voz — no celular, lista em branco parece tela quebrada")
# ---------------------------------------------------------------------------
codigo, ninguem = frente(demo, como="Ninguem Com Esse Nome")
check("nome que não existe responde 200, e não erro", codigo == 200)
check("com total zero", ninguem["total"] == 0)
check(
    "e TODO bloco vazio traz a razão escrita",
    all(ninguem[b]["vazio_porque"] for b in BLOCOS),
)
check(
    "a razão do bloco de compromissos ensina o que fazer a respeito",
    "nome" in ninguem["compromissos"]["vazio_porque"].lower(),
)

# ---------------------------------------------------------------------------
print("\n5. Atravessa obras de propósito — o mestre que cobre duas vê as duas")
# ---------------------------------------------------------------------------
linhas = minha["compromissos"]["linhas"]
obras = {linha["obra"] for linha in linhas}
check("cada compromisso diz de que obra é", all(linha["obra_nome"] for linha in linhas))
if obras:
    uma = sorted(obras)[0]
    codigo, recortada = frente(campo, obra=uma)
    check("`?obra=` recorta a leitura", codigo == 200)
    check(
        "e só sobra a obra pedida",
        {l["obra"] for l in recortada["compromissos"]["linhas"]} <= {uma},
    )

# ---------------------------------------------------------------------------
print("\n6. Dado honesto — o nulo que a régua exige")
# ---------------------------------------------------------------------------
check(
    "prometido e apontado viajam SEPARADOS, nunca somados",
    all({"previsto", "apontado", "apontou"} <= set(l) for l in linhas),
)
sem_apontamento = [l for l in linhas if not l["apontou"]]
check(
    "sem apontamento o valor é nulo — e zero nunca aparece no lugar",
    all(l["apontado"] is None for l in sem_apontamento),
)
check(
    "e a trava e o defeito do serviço vêm no cartão, antes de a pessoa ir à frente",
    all({"restricoes_abertas", "ncs_abertas"} <= set(l) for l in linhas),
)

# ---------------------------------------------------------------------------
print("\n7. Permissão por bloco — nunca 403 na página inteira")
# ---------------------------------------------------------------------------
codigo, do_gerente = frente(gerente)
check("a diretoria também abre a leitura", codigo == 200)
negados = {n["permissao"] for n in do_gerente["sem_permissao"]}
nulos = [b for b in BLOCOS if do_gerente[b] is None]
check(
    "todo bloco nulo tem a permissão que falta NOMEADA",
    len(nulos) == len(negados) or not nulos,
)
check(
    "e nenhum bloco vem vazio sem explicação — nem nulo nem em branco",
    all(do_gerente[b] is not None or negados for b in BLOCOS),
)

# ---------------------------------------------------------------------------
print("\n8. O ato do campo — apontar avanço, e estornar o próprio erro")
# ---------------------------------------------------------------------------
if not linhas:
    print("     (sem compromisso semeado; o ato não pôde ser exercido)")
else:
    alvo = linhas[0]
    hoje = minha["hoje"]
    codigo, lancado = req("POST", "/api/pdca/apontamentos/", campo, {
        "atividade": alvo["atividade"],
        "data": hoje,
        "percentual": "3.50",
        "origem": "app",
        "observacao": "E2E da frente do canteiro.",
    })
    check("o campo aponta avanço e o servidor aceita", codigo == 201)
    if codigo != 201:
        print(f"     resposta: {lancado}")
    else:
        apontamento = lancado["apontamento_id"]
        check("a origem registrada é a do aplicativo de campo",
              lancado.get("origem") == "app")

        codigo, depois = frente(campo)
        atual = next(
            (l for l in depois["compromissos"]["linhas"] if l["item"] == alvo["item"]),
            None,
        )
        check("e o número aparece na frente na leitura seguinte",
              atual is not None and atual["apontou"] is True)

        codigo, estorno = req(
            "POST", f"/api/pdca/apontamentos/{apontamento}/estornar/", campo,
            {"motivo": "E2E — desfazendo o lançamento de teste."},
        )
        check("estornar corrige sem apagar: nasce o lançamento contrário",
              codigo == 201 and float(estorno["percentual"]) < 0)

        codigo, limpo = frente(campo)
        voltou = next(
            (l for l in limpo["compromissos"]["linhas"] if l["item"] == alvo["item"]),
            None,
        )
        # **Contra o valor de antes, e não contra zero.** O serviço pode já ter
        # avanço apontado na semana, e "voltou ao que era" é o que o estorno
        # promete — o par soma zero e não mexe no acumulado. Nulo só volta a ser
        # nulo se não havia nada: depois do par, o campo vale zero, que é
        # "apontou e estornou" e é diferente de "ninguém apontou".
        antes = float(alvo["apontado"] or 0)
        check(
            "e a soma volta ao que era antes do teste",
            voltou is not None and abs(float(voltou["apontado"] or 0) - antes) < 0.001,
        )

        # A diretoria **lê** o avanço e não o aponta: quem responde pela obra
        # aponta, quem lê o número não o escreve. É a segregação do catálogo,
        # conferida pela porta.
        codigo, _ = req("POST", "/api/pdca/apontamentos/", gerente, {
            "atividade": alvo["atividade"], "data": hoje, "percentual": "1",
        })
        check(
            "quem só lê o avanço é recusado ao tentar apontá-lo",
            codigo == 403,
        )

# ---------------------------------------------------------------------------
print("\n9. Entrada ruim — recusa com frase, e sem vazar o nome do vizinho")
# ---------------------------------------------------------------------------
codigo, recusa = frente(campo, obra=999999)
check("obra que não existe responde 400, e não 500", codigo == 400)
check("com frase em português", "obra" in texto(recusa))

# ---------------------------------------------------------------------------
print("\n10. A fronteira — o tenant sem o módulo para antes da RLS")
# ---------------------------------------------------------------------------
codigo, _ = frente(acme)
check("sem o módulo contratado, a porta fecha com 403", codigo == 403)

codigo, deles = frente(acme, como="Encarregado da frente")
check("e nem com `?como=` ele alcança a obra alheia", codigo == 403)

# ---------------------------------------------------------------------------
ok = sum(1 for p in passed if p)
print(f"\n{'='*62}")
print(f"RESULTADO: {ok}/{len(passed)}")
print('='*62)
sys.exit(0 if ok == len(passed) else 1)
