"""PDCA.6 — linha de balanço: ritmo, gargalo e choque de equipe, pelo gateway (8090).

Irmão do `pdca5_programacao_test.py`. A fatia não move dinheiro nem alçada — ela
move **como o planejador pensa**: no Gantt se arrasta uma barra pronta e se
pensa em duração; aqui se desenha a reta e se pensa em **ritmo**. O que este
teste prova é que a conta que sai disso está certa do outro lado do gateway.

A LOB **não tem tabela** (planta §4.9): é derivada de `Atividade` × `LocalObra`.
Por isso metade das verificações é sobre a derivação continuar honesta — o eixo
na ordem em que a obra sobe, o ritmo que é o pedido, o gargalo que é o mais
lento, o conflito que é fato e não geometria, e o **que ficou de fora** dito em
voz alta.

Seed: testes/seeds/seed_demo.py + testes/seeds/seed_demo_data.py

  demo     / demo123     -> `engenharia` + `planejador`: desenha e lê.
  campo    / campo123    -> `campo`: lê o plano e **não** o desenha — traçar a
                            linha cria atividades, e isso é ato de quem assume
                            o prazo.
  acme     / acme123     -> outro tenant: é a fronteira.

  1. O que existe   -> `status/` declara a LOB, o ritmo e o choque de equipe.
  2. Cenário        -> obra, calendário, torre com quatro pavimentos, plano.
  3. Simular        -> a mesma conta, **sem gravar** (a régua da PDCA.0).
  4. O traço        -> desenha a alvenaria, e a precedência é **SS com atraso**.
  5. A leitura      -> eixo na ordem da obra, uma reta, ritmo em número.
  6. O gargalo      -> um segundo serviço mais lento passa a ditar o ritmo.
  7. O choque       -> duas equipes no mesmo pavimento, com os dias contados.
  8. Honestidade    -> atividade sem local fica fora, e o número vem no corpo.
  9. As travas      -> plano vigente não recebe traço; local de outra obra, não.
 10. Segregação     -> quem só lê o plano não desenha a linha.
 11. A fronteira    -> outro tenant não enxerga nada disto.
 12. Faxina.

Rodar (stack de pé):  python testes/e2e/pdca6_linha_de_balanco_test.py
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

GW = os.environ.get("SGI_GW", "http://localhost:8090")

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

MARCA = "E2E PDCA.6 " + uuid.uuid4().hex[:8]

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


def texto(resposta) -> str:
    return json.dumps(resposta, ensure_ascii=False).lower() if resposta is not None else ""


print(f"\n{'='*62}\nPDCA.6 — linha de balanço pelo gateway\n{'='*62}")
print(f"Gateway: {GW}")

try:
    demo = login("demo", "demo123")
    campo = login("campo", "campo123")
    acme = login("acme", "acme123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé? Rodou os dois seeds?")

# --------------------------------------------------------- 1. o que existe
print("\n1. O módulo declara o que a fatia entregou")
status, st = req("GET", "/api/pdca/status/", demo)
check("`demo` lê o status", status == 200)
# **O número da fatia NÃO se prende.** Este check dizia `fatia == "PDCA.6"` e
# passou a reprovar no dia em que a PDCA.7 entrou — acusando falha no que era
# progresso, e num roteiro que nada tem a ver com verificação. O que este teste
# tem de provar é que o módulo **continua declarando o que esta fatia entregou**,
# e é o que a linha seguinte faz; a fatia corrente é sempre a mais nova, e
# fixá-la aqui é pendurar um alarme no relógio.
check("o módulo declara em que fatia está", bool((st or {}).get("fatia")))
recursos = (st or {}).get("recursos", {})
check("linha de balanço, ritmo e choque de equipe estão de pé",
      recursos.get("linha_de_balanco") is True
      and recursos.get("ritmo") is True
      and recursos.get("conflito_de_equipe") is True)
tetos = (st or {}).get("tetos", {})
check("os tetos novos vêm do servidor (o dono decide o número)",
      isinstance(tetos.get("locais_na_linha_de_balanco"), int)
      and isinstance(tetos.get("linhas_de_balanco"), int)
      and isinstance(tetos.get("locais_por_ritmo"), int))

# ------------------------------------------------------------- 2. o cenário
print("\n2. Obra, torre de quatro pavimentos e um plano em rascunho")
status, obra = req("POST", "/api/obras/", demo, {
    "nome_obra": MARCA, "endereco": "Rua do Ritmo, s/n",
    "status_obra": "planejamento",
})
if status not in (200, 201) or not obra:
    fatal(f"não consegui criar a obra do teste (HTTP {status}: {obra})")
obra_id = obra["obra_id"]

status, torre = req("POST", "/api/pdca/locais/", demo, {
    "obra": obra_id, "nivel": "bloco", "codigo": "T1", "nome": "Torre 1",
    "ordem": 1,
})
if status not in (200, 201) or not torre:
    fatal(f"local raiz falhou (HTTP {status}: {torre})")
torre_id = torre["local_id"]

# **Os códigos vão a P10 de propósito.** Ordenados por texto, "P10" viria antes
# de "P9" e a reta do serviço desceria no meio do gráfico — o eixo tem de seguir
# a árvore, não o alfabeto.
pavimentos = []
for n in (1, 2, 9, 10):
    status, pav = req("POST", "/api/pdca/locais/", demo, {
        "obra": obra_id, "pai": torre_id, "nivel": "pavimento",
        "codigo": f"P{n}", "nome": f"{n}º pavimento", "ordem": n,
    })
    if status not in (200, 201) or not pav:
        fatal(f"pavimento {n} falhou (HTTP {status}: {pav})")
    pavimentos.append(pav["local_id"])
check("a torre e os quatro pavimentos entraram", len(pavimentos) == 4)

status, calendario = req("POST", "/api/pdca/calendarios/", demo, {
    "obra": obra_id, "nome": "Expediente " + MARCA,
})
if status not in (200, 201):
    fatal(f"calendário falhou (HTTP {status}: {calendario})")

hoje = date.today()
segunda = hoje - timedelta(days=hoje.weekday())
status, crono = req("POST", "/api/pdca/cronogramas/", demo, {
    "obra": obra_id, "descricao": "Plano " + MARCA,
    "data_inicio": segunda.isoformat(),
    "calendario": calendario["calendario_id"],
})
if status not in (200, 201) or not crono:
    fatal(f"cronograma falhou (HTTP {status}: {crono})")
crono_id = crono["cronograma_id"]
check("o plano nasce em rascunho — só ele recebe traço novo",
      crono.get("status") == "rascunho")

# ------------------------------------------------------------- 3. simular
print("\n3. Simular — a mesma conta, sem gravar (a régua da PDCA.0)")
traco = {
    "nome": "Alvenaria", "codigo": "1", "locais": pavimentos,
    "inicio": segunda.isoformat(), "duracao_por_local": 4, "ritmo_dias": 2,
}
status, previa = req("POST", f"/api/pdca/cronogramas/{crono_id}/ritmo/", demo,
                     {**traco, "simular": True})
check("a simulação responde 200 (não 201 — nada nasceu)", status == 200)
check("e se declara simulada", (previa or {}).get("simulado") is True)
check("dizendo quantas atividades o traço criaria", (previa or {}).get("criar") == 4)
check("e o prazo dele ANTES de gravar: 2×3 + 4 = 10 dias úteis",
      (previa or {}).get("dias_uteis_total") == 10)
check("a prévia mostra código e local de cada folha",
      len((previa or {}).get("previa") or []) == 4
      and "1º pavimento" in texto(previa))

status, lista = req("GET", f"/api/pdca/atividades/?cronograma={crono_id}", demo)
quantas = len((lista or {}).get("results") or [])
check("e o plano continua VAZIO — simular não escreve", quantas == 0)

# --------------------------------------------------------------- 4. o traço
print("\n4. Desenhar a linha — e a precedência é SS com atraso")
status, feito = req("POST", f"/api/pdca/cronogramas/{crono_id}/ritmo/", demo,
                    {**traco, "simular": False})
if status not in (200, 201) or not feito:
    fatal(f"o traço falhou (HTTP {status}: {feito})")
check("o traço responde 201 — as atividades nasceram", status == 201)
check("quatro folhas, uma por pavimento", len(feito.get("atividades") or []) == 4)
servico_alvenaria = feito["pai"]

status, precedencias = req(
    "GET", f"/api/pdca/precedencias/?cronograma={crono_id}&page_size=200", demo,
)
ligacoes = (precedencias or {}).get("results") or []
check("três ligações para quatro locais", len(ligacoes) == 3)
check("e elas são **SS**, não FS — é o que faz a inclinação ser o RITMO e não "
      "a duração", all(p.get("tipo") == "SS" for p in ligacoes))
check("com o atraso igual ao ritmo pedido (2 dias)",
      all(p.get("atraso_dias") == 2 for p in ligacoes))

# ------------------------------------------------------------- 5. a leitura
print("\n5. A leitura derivada — eixo, reta e ritmo em número")
status, lob = req("GET", f"/api/pdca/cronogramas/{crono_id}/linha-de-balanco/", demo)
check("a LOB responde", status == 200)
eixo = [e["codigo"] for e in (lob or {}).get("eixo") or []]
check("o eixo segue a ÁRVORE e não o alfabeto: P1, P2, P9, P10",
      eixo == ["P1", "P2", "P9", "P10"])
linhas = (lob or {}).get("linhas") or []
check("uma reta, a da alvenaria", len(linhas) == 1)
alvenaria = linhas[0] if linhas else {}
check("com um ponto por local, já ordenados pelo eixo",
      [p["y"] for p in alvenaria.get("pontos", [])] == [0, 1, 2, 3])
check("e o ritmo vem em NÚMERO — 'mais inclinado' não é uma medida",
      alvenaria.get("dias_por_local") is not None
      and alvenaria.get("locais_por_semana") is not None)
check("o ritmo atravessa como string (a régua do D151)",
      isinstance(alvenaria.get("dias_por_local"), str))
check("cada ponto carrega a janela do plano naquele local",
      all(p.get("inicio") and p.get("fim") for p in alvenaria.get("pontos", [])))
check("um serviço só: ainda não há gargalo a apontar",
      (lob or {}).get("gargalo") == servico_alvenaria)
check("e nenhum choque — uma equipe sozinha não colide com ninguém",
      (lob or {}).get("conflitos") == [])

# -------------------------------------------------------------- 6. gargalo
print("\n6. O gargalo — o mais lento dita o ritmo de todos")
status, lento = req("POST", f"/api/pdca/cronogramas/{crono_id}/ritmo/", demo, {
    "nome": "Elétrica", "codigo": "2", "locais": pavimentos,
    "inicio": segunda.isoformat(), "duracao_por_local": 6, "ritmo_dias": 6,
    "simular": False,
})
if status not in (200, 201) or not lento:
    fatal(f"o segundo traço falhou (HTTP {status}: {lento})")
servico_eletrica = lento["pai"]

status, lob = req("GET", f"/api/pdca/cronogramas/{crono_id}/linha-de-balanco/", demo)
linhas = (lob or {}).get("linhas") or []
check("duas retas agora", len(linhas) == 2)
check("e o GARGALO é a elétrica, que sobe a cada 6 dias e não a cada 2",
      (lob or {}).get("gargalo") == servico_eletrica)
por_servico = {l["servico"]: l for l in linhas}
check("o ritmo da alvenaria é maior que o da elétrica (mais locais por semana)",
      float(por_servico[servico_alvenaria]["locais_por_semana"])
      > float(por_servico[servico_eletrica]["locais_por_semana"]))

# --------------------------------------------------------------- 7. choque
print("\n7. O choque de equipe — o que a LOB existe para achar")
conflitos = (lob or {}).get("conflitos") or []
check("dois serviços começando juntos no mesmo pavimento é CHOQUE",
      len(conflitos) >= 1)
if conflitos:
    choque = conflitos[0]
    check("e ele é FATO, não geometria: local, os dois serviços e a janela",
          choque.get("local_rotulo") and choque.get("servico_a")
          and choque.get("servico_b") and choque.get("inicio"))
    check("com os dias contados, para não medir a tela com o dedo",
          isinstance(choque.get("dias"), int) and choque["dias"] >= 1)
    check("os serviços do choque são DIFERENTES — o conflito é entre ofícios",
          choque["servico_a"] != choque["servico_b"])
    check("e o maior choque vem primeiro",
          all(choque["dias"] >= c["dias"] for c in conflitos))

# ---------------------------------------------------------- 8. honestidade
print("\n8. O gráfico diz o que NÃO está mostrando")
status, sem_endereco = req("POST", "/api/pdca/atividades/", demo, {
    "cronograma": crono_id, "codigo": "9", "nome": "Canteiro (sem endereço)",
    "duracao_dias": 5,
})
check("uma atividade sem local entra no plano", status in (200, 201))
req("POST", f"/api/pdca/cronogramas/{crono_id}/calcular/", demo)
status, lob = req("GET", f"/api/pdca/cronogramas/{crono_id}/linha-de-balanco/", demo)
check("e ela NÃO aparece na LOB — sem endereço não há eixo onde pô-la",
      len((lob or {}).get("linhas") or []) == 2)
check("mas o corpo diz que ela existe: um gráfico que mostra 2 de 3 frentes "
      "sem avisar faz quem olha concluir que a obra tem duas",
      (lob or {}).get("atividades_sem_local") == 1)

# ---------------------------------------------------------------- 9. travas
print("\n9. As travas do desenho")
status, alheio = req("POST", f"/api/pdca/cronogramas/{crono_id}/ritmo/", demo, {
    "nome": "Fantasma", "codigo": "8", "locais": [999999999],
    "inicio": segunda.isoformat(), "duracao_por_local": 3,
})
check("local que não é desta obra é recusado", status == 400)

status, marco = req("POST", f"/api/pdca/cronogramas/{crono_id}/ritmo/", demo, {
    "nome": "Zero", "codigo": "7", "locais": [pavimentos[0]],
    "inicio": segunda.isoformat(), "duracao_por_local": 0,
})
check("duração zero é recusada", status == 400)
check("e a recusa diz por quê (marco não tem ritmo)", "marco" in texto(marco))

status, sem_nome = req("POST", f"/api/pdca/cronogramas/{crono_id}/ritmo/", demo, {
    "codigo": "6", "locais": [pavimentos[0]],
    "inicio": segunda.isoformat(), "duracao_por_local": 3,
})
check("traço sem serviço e sem pai é recusado", status == 400)

req("POST", f"/api/pdca/cronogramas/{crono_id}/publicar/", demo)
status, vigente = req("POST", f"/api/pdca/cronogramas/{crono_id}/ritmo/", demo, {
    "nome": "Tarde demais", "codigo": "5", "locais": [pavimentos[0]],
    "inicio": segunda.isoformat(), "duracao_por_local": 3,
})
check("o plano VIGENTE não recebe traço novo", status == 400)
check("e a recusa manda replanejar — o vigente é a régua do atraso",
      "replaneje" in texto(vigente) or "rascunho" in texto(vigente))

status, lob = req("GET", f"/api/pdca/cronogramas/{crono_id}/linha-de-balanco/", demo)
check("mas o plano publicado continua LEGÍVEL na LOB",
      status == 200 and len((lob or {}).get("linhas") or []) == 2)

# ------------------------------------------------------------ 10. segregação
print("\n10. Quem só lê o plano não desenha a linha")
status, _ = req("GET", f"/api/pdca/cronogramas/{crono_id}/linha-de-balanco/", campo)
check("`campo` (mestre de obra) LÊ a linha de balanço — é o plano dele", status == 200)
status, negado = req("POST", f"/api/pdca/cronogramas/{crono_id}/ritmo/", campo, {
    "nome": "Do campo", "codigo": "4", "locais": [pavimentos[0]],
    "inicio": segunda.isoformat(), "duracao_por_local": 3,
})
check("e NÃO a desenha — traçar cria atividades, e isso é ato de quem assume "
      "o prazo", status == 403)

# ---------------------------------------------------------- 11. a fronteira
print("\n11. A fronteira de tenant")
status, _ = req("GET", f"/api/pdca/cronogramas/{crono_id}/linha-de-balanco/", acme)
check("outro tenant não lê esta linha de balanço", status in (403, 404))
status, _ = req("POST", f"/api/pdca/cronogramas/{crono_id}/ritmo/", acme, {
    "nome": "Invasor", "codigo": "3", "locais": [pavimentos[0]],
    "inicio": segunda.isoformat(), "duracao_por_local": 3,
})
check("nem desenha nela", status in (403, 404))

# --------------------------------------------------------------- 12. faxina
print("\n12. Faxina — o teste desfaz o que dá para desfazer")
status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
check("a obra do teste sai (vai para a lixeira, que é o desenho)",
      status in (200, 204))
print(
    "\n     Como os irmãos, este teste deixa o cronograma publicado — plano\n"
    "     vigente não se apaga, e é isso que a PDCA.1 garante. Para devolver\n"
    "     o ambiente ao estado anterior:\n"
    "       docker exec sgi-erp python manage.py limpar_residuo_e2e --confirmar"
)

# ------------------------------------------------------------------ resumo
ok = sum(1 for p in passed if p)
print(f"\n{'='*62}\nPDCA.6: {ok}/{len(passed)} verificações\n{'='*62}")
sys.exit(0 if ok == len(passed) else 1)
