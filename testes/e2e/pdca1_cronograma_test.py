"""PDCA.1 — o plano de tempo da obra ponta a ponta pelo gateway (8090).

Prova com **token real da IAM** o que a suíte unitária do `modulopdca` não
alcança. Lá o CPM é chamado direto e o usuário é empurrado com
`force_authenticate`; aqui cada gesto atravessa login, assinatura RS256, gateway,
entitlement de módulo, permissão de campo e RLS — que é onde um plano de obra
quebra de verdade.

Seed: testes/seeds/seed_demo.py + testes/seeds/seed_demo_data.py

  demo     / demo123     -> tem o módulo `pdca` e o papel `planejador`
                            (`pdca.cronograma.*`, os quatro verbos)
  semdrone / semdrone123 -> NÃO tem o módulo: é a camada 1
  acme     / acme123     -> outro tenant: é a fronteira

  1. Camada 1          -> quem não assina `pdca` não passa, mesmo autenticado.
  2. O módulo se declara-> `status/` diz que `cronograma` existe (e que medição
                           ainda não) — a tela lê isto para não prometer aba que
                           não há.
  3. A obra do teste   -> obra própria + calendário de segunda a sexta. O teste
                           não encosta em obra de verdade de quem roda isto.
  4. Um plano por obra -> nasce em rascunho v1; o segundo cronograma da mesma
                           obra é recusado com o motivo (replanejar, não criar).
  5. A WBS             -> sintética com três folhas; código repetido é barrado
                           pelo banco, não pela tela.
  6. A rede            -> FS entre as folhas; o ciclo é recusado **nomeando** as
                           atividades, e a seta para a sintética também.
  7. O CPM             -> datas reais sobre o calendário: o fim de semana é
                           pulado, o caminho crítico aparece e a folga da corrente
                           curta é positiva.
  8. Uma chamada só    -> `gantt/` traz árvore, setas, linha de base e cobertura.
  9. Arrastar a barra  -> `reprogramar/` fixa a restrição e o CPM decide — a
                           sucessora anda junto.
 10. Publicar congela  -> vigente não aceita edição de atividade.
 11. Replanejar        -> exige motivo, abre a v2 e a v1 vira a régua: a linha de
                           base mostra o desvio atividade a atividade.
 12. Cobertura         -> o denominador aparece: quantas folhas ficaram sem peso.
 13. A fronteira       -> outro tenant não enxerga nada disto.
 14. Faxina            -> o teste apaga a obra que criou, e a cascata leva o resto.

Rodar (stack de pé):  python testes/e2e/pdca1_cronograma_test.py
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta
from _sessao import cabecalhos, da_resposta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

MARCA = "E2E PDCA.1 " + uuid.uuid4().hex[:8]

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
        return da_resposta(resp)


def texto(resposta) -> str:
    """A mensagem de erro do DRF, venha ela como lista, dicionário ou string."""
    return json.dumps(resposta, ensure_ascii=False).lower() if resposta is not None else ""


print(f"\n{'='*58}\nPDCA.1 — cronograma, CPM e linha de base pelo gateway\n{'='*58}")
print(f"Gateway: {GW}")

try:
    demo = login("demo", "demo123")
    semdrone = login("semdrone", "semdrone123")
    acme = login("acme", "acme123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé? Rodou os dois seeds?")

# --------------------------------------------------------------- 1. camada 1
print("\n1. Quem não assina o módulo não passa")
status, _ = req("GET", "/api/pdca/cronogramas/", semdrone)
check("`semdrone` (sem `pdca`) leva 403 na listagem", status == 403)
status, _ = req("GET", "/api/pdca/status/", semdrone)
check("e também no status do módulo", status == 403)

# ------------------------------------------------------- 2. o módulo se declara
print("\n2. O módulo declara o que existe")
status, st = req("GET", "/api/pdca/status/", demo)
check("`demo` lê o status", status == 200)
recursos = (st or {}).get("recursos", {})
check("`cronograma` está de pé", recursos.get("cronograma") is True)
check("`locais` e `calendario` também (PDCA.0)",
      recursos.get("locais") is True and recursos.get("calendario") is True)
# **Este check é um guard móvel, e ele precisa ser movido a cada fatia.** Ele
# impede o `status/` de voltar a prometer o que não há, apontando sempre para a
# PRÓXIMA capacidade ainda não construída — e por isso envelhece sozinho: ficou
# apontando para `aditivo` depois de a PDCA.4 o ter ligado, depois para
# `verificacao` depois de a PDCA.7 o ter ligado, e nas duas vezes passou a
# acusar falha no que era sucesso. Hoje a fronteira é a **apropriação de
# homem-hora**: sem ela as taxas de frequência e gravidade não existem, e é
# justamente a ausência que o módulo declara em voz alta em vez de mostrar zero.
check("`medicao` está de pé (PDCA.3)", recursos.get("medicao") is True)
check("`aditivo` está de pé (PDCA.4)", recursos.get("aditivo") is True)
check("`programacao_semanal` está de pé (PDCA.5)",
      recursos.get("programacao_semanal") is True)
check("`linha_de_balanco` está de pé (PDCA.6)",
      recursos.get("linha_de_balanco") is True)
check("`verificacao` está de pé (PDCA.7)", recursos.get("verificacao") is True)
check("`ocorrencia` está de pé (PDCA.8)", recursos.get("ocorrencia") is True)
check("e a taxa de frequência continua declarada como AUSENTE — ela divide por "
      "homem-hora, que o sistema ainda não apropria",
      recursos.get("taxa_frequencia") is not True)

# ------------------------------------------------------------ 3. a obra do teste
print("\n3. A obra do teste — e o expediente dela")
status, obra = req("POST", "/api/obras/", demo, {
    "nome_obra": MARCA,
    "endereco": "Rua de teste, s/n",
    "status_obra": "planejamento",
})
if status not in (200, 201) or not obra:
    fatal(f"não consegui criar a obra do teste (HTTP {status}: {obra})")
obra_id = obra["obra_id"]
check("obra criada só para este teste", True)

status, calendario = req("POST", "/api/pdca/calendarios/", demo, {
    "obra": obra_id,
    "nome": "Expediente " + MARCA,
    "trabalha_sabado": False,
    "trabalha_domingo": False,
})
if status not in (200, 201) or not calendario:
    fatal(f"não consegui criar o calendário (HTTP {status}: {calendario})")
calendario_id = calendario["calendario_id"]
check("calendário de segunda a sexta criado para a obra", True)

status, recusado = req("POST", "/api/pdca/calendarios/", demo, {
    "obra": obra_id, "nome": "Nunca",
    "trabalha_segunda": False, "trabalha_terca": False, "trabalha_quarta": False,
    "trabalha_quinta": False, "trabalha_sexta": False,
    "trabalha_sabado": False, "trabalha_domingo": False,
})
check("calendário sem nenhum dia útil é recusado", status == 400)

# ------------------------------------------------------- 4. um plano por obra
print("\n4. Um plano por obra, e ele nasce rascunho")
# Segunda-feira, para a conta de dias úteis do teste não depender do dia em que
# alguém resolveu rodá-lo.
inicio = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)
status, plano = req("POST", "/api/pdca/cronogramas/", demo, {
    "obra": obra_id,
    "descricao": "Plano " + MARCA,
    "data_inicio": inicio.isoformat(),
    "calendario": calendario_id,
})
if status not in (200, 201) or not plano:
    fatal(f"não consegui criar o cronograma (HTTP {status}: {plano})")
plano_id = plano["cronograma_id"]
check("cronograma criado", True)
check("nasce em rascunho, versão 1", plano["status"] == "rascunho" and plano["versao"] == 1)
check("e editável", plano["editavel"] is True)

status, segundo = req("POST", "/api/pdca/cronogramas/", demo, {
    "obra": obra_id, "descricao": "Segundo plano", "data_inicio": inicio.isoformat(),
})
check("o segundo cronograma da mesma obra é recusado", status == 400)
check("e a recusa manda replanejar, em vez de só dizer não",
      "replaneje" in texto(segundo))


# ------------------------------------------------------------------ 5. a WBS
print("\n5. A WBS — sintética e folhas")


def atividade(payload):
    status, corpo = req("POST", "/api/pdca/atividades/", demo, {"cronograma": plano_id, **payload})
    if status not in (200, 201):
        fatal(f"não consegui criar a atividade {payload.get('codigo')} (HTTP {status}: {corpo})")
    return corpo


fundacao = atividade({"codigo": "1", "nome": "Fundação", "ordem": 1, "duracao_dias": 1})
estaca = atividade({"codigo": "1.1", "nome": "Estaca hélice", "pai": fundacao["atividade_id"],
                    "ordem": 1, "duracao_dias": 5})
bloco = atividade({"codigo": "1.2", "nome": "Blocos e baldrames", "pai": fundacao["atividade_id"],
                   "ordem": 2, "duracao_dias": 3})
paralela = atividade({"codigo": "2", "nome": "Canteiro", "ordem": 2, "duracao_dias": 2})
marco = atividade({"codigo": "M1", "nome": "Fundação concluída", "ordem": 3, "eh_marco": True})

check("três folhas e um marco criados", True)
status, corpo = req("GET", f"/api/pdca/atividades/{fundacao['atividade_id']}/", demo)
check("a pai virou sintética (tem filhas)", status == 200 and corpo["tem_filhos"] is True)

status, repetido = req("POST", "/api/pdca/atividades/", demo, {
    "cronograma": plano_id, "codigo": "1.1", "nome": "Outra", "duracao_dias": 1,
})
check("código repetido no mesmo cronograma é barrado", status == 400)

status, sem_duracao = req("POST", "/api/pdca/atividades/", demo, {
    "cronograma": plano_id, "codigo": "9", "nome": "Sem duração",
})
check("folha sem duração é recusada", status == 400)
check("e o marco não aceita duração",
      req("POST", "/api/pdca/atividades/", demo, {
          "cronograma": plano_id, "codigo": "M9", "nome": "Marco torto",
          "eh_marco": True, "duracao_dias": 3})[0] == 400)

# ------------------------------------------------------------------ 6. a rede
print("\n6. A rede — e as quatro recusas que dão endereço ao erro")


def ligar(origem, destino, tipo="FS", atraso=0, esperado=(200, 201)):
    status, corpo = req("POST", "/api/pdca/precedencias/", demo, {
        "origem": origem, "destino": destino, "tipo": tipo, "atraso_dias": atraso,
    })
    if esperado and status not in esperado:
        fatal(f"ligação {origem}->{destino} devolveu {status}: {corpo}")
    return status, corpo


ligar(estaca["atividade_id"], bloco["atividade_id"])
ligar(bloco["atividade_id"], marco["atividade_id"])
check("estaca → blocos → marco ligados", True)

status, ciclo = ligar(bloco["atividade_id"], estaca["atividade_id"], esperado=None)
check("a seta que fecharia ciclo é recusada", status == 400)
check("e a recusa nomeia as atividades envolvidas",
      "1.1" in texto(ciclo) and "1.2" in texto(ciclo))

status, sintetica = ligar(paralela["atividade_id"], fundacao["atividade_id"], esperado=None)
check("a seta para uma sintética é recusada", status == 400)
check("e explica que a precedência liga as folhas", "folha" in texto(sintetica))

# ------------------------------------------------------------------- 7. o CPM
print("\n7. O CPM sobre o calendário da obra")
status, cpm = req("POST", f"/api/pdca/cronogramas/{plano_id}/calcular/", demo)
if status != 200 or not cpm:
    fatal(f"o CPM não rodou (HTTP {status}: {cpm})")
check("calcula e devolve o resultado", True)
check("conta as folhas do grafo (3 folhas + 1 marco)", cpm["folhas"] == 4)
check("o plano começa na âncora", cpm["inicio"] == inicio.isoformat())

status, arvore = req("GET", f"/api/pdca/atividades/?cronograma={plano_id}&page_size=50", demo)
por_codigo = {a["codigo"]: a for a in (arvore or {}).get("results", [])}
estaca_calc = por_codigo["1.1"]
bloco_calc = por_codigo["1.2"]
canteiro_calc = por_codigo["2"]

check("a estaca começa na segunda-feira do plano", estaca_calc["inicio_cedo"] == inicio.isoformat())
# 5 dias úteis a partir de segunda terminam na sexta; os blocos só começam na
# segunda seguinte — é o fim de semana saindo da conta, que é a razão de o
# calendário existir.
check("5 dias úteis terminam na sexta",
      estaca_calc["termino_cedo"] == (inicio + timedelta(days=4)).isoformat())
check("o sucessor pula o fim de semana",
      bloco_calc["inicio_cedo"] == (inicio + timedelta(days=7)).isoformat())
check("a corrente longa é a crítica",
      estaca_calc["critica"] is True and bloco_calc["critica"] is True)
check("e a atividade solta tem folga",
      canteiro_calc["critica"] is False and (canteiro_calc["folga_total"] or 0) > 0)
check("a sintética é o intervalo das filhas",
      por_codigo["1"]["inicio_cedo"] == estaca_calc["inicio_cedo"]
      and por_codigo["1"]["termino_cedo"] == bloco_calc["termino_cedo"])
check("o marco é um instante", por_codigo["M1"]["inicio_cedo"] == por_codigo["M1"]["termino_cedo"])


# ------------------------------------------------------- 8. o Gantt numa chamada
print("\n8. O Gantt vem inteiro numa chamada")
status, gantt = req("GET", f"/api/pdca/cronogramas/{plano_id}/gantt/", demo)
check("`gantt/` responde", status == 200 and gantt is not None)
check("com o cronograma, a árvore e as setas",
      gantt and len(gantt["atividades"]) == 5 and len(gantt["precedencias"]) == 2)
check("com a linha de base declarada (ainda não há)", gantt and gantt["base"]["tem_base"] is False)
check("e com a cobertura do orçamento junto", gantt and "cobertura_orcamento" in gantt)
check("o peso viaja com a origem",
      all("peso" in a and "peso_origem" in a for a in (gantt or {}).get("atividades", [])))

# ---------------------------------------------------------- 9. arrastar a barra
print("\n9. Arrastar a barra é fixar restrição e deixar o CPM decidir")
nova_data = (inicio + timedelta(days=2)).isoformat()
status, arrasto = req("POST", f"/api/pdca/atividades/{estaca['atividade_id']}/reprogramar/", demo,
                      {"nao_comecar_antes_de": nova_data})
check("`reprogramar/` aceita a restrição", status == 200)
check("a atividade anda para a data pedida",
      arrasto and arrasto["atividade"]["inicio_cedo"] == nova_data)
check("e o CPM roda junto, na mesma resposta", arrasto and "cpm" in arrasto)

status, depois = req("GET", f"/api/pdca/atividades/{bloco['atividade_id']}/", demo)
check("a sucessora foi empurrada junto",
      status == 200 and depois["inicio_cedo"] > bloco_calc["inicio_cedo"])

status, esticado = req("POST", f"/api/pdca/atividades/{bloco['atividade_id']}/reprogramar/", demo,
                       {"duracao_dias": 8})
check("esticar a ponta muda a duração", status == 200 and esticado["atividade"]["duracao_dias"] == 8)
status, invalida = req("POST", f"/api/pdca/atividades/{bloco['atividade_id']}/reprogramar/", demo,
                       {"duracao_dias": 0})
check("duração zero é recusada", status == 400)

# ------------------------------------------------------------ 10. publicar congela
print("\n10. Publicar congela o plano")
status, publicado = req("POST", f"/api/pdca/cronogramas/{plano_id}/publicar/", demo)
check("publica", status == 200)
check("e vira vigente", publicado and publicado["cronograma"]["status"] == "vigente")
check("com o CPM rodado antes de virar a chave", publicado and "cpm" in publicado)
check("carimbando quem publicou", publicado and publicado["cronograma"]["publicado_por"] == "demo")

status, barrado = req("PATCH", f"/api/pdca/atividades/{estaca['atividade_id']}/", demo,
                      {"duracao_dias": 99})
check("editar atividade de plano vigente é recusado", status == 400)
check("e a recusa manda replanejar", "replane" in texto(barrado))

status, seta_barrada = ligar(paralela["atividade_id"], marco["atividade_id"], esperado=None)
check("criar precedência no vigente também é recusado", status == 400)

# ------------------------------------------------------------- 11. replanejar
print("\n11. Replanejar — a versão anterior vira a régua")
status, sem_motivo = req("POST", f"/api/pdca/cronogramas/{plano_id}/replanejar/", demo, {})
check("replanejar sem motivo é recusado", status == 400)

status, v2 = req("POST", f"/api/pdca/cronogramas/{plano_id}/replanejar/", demo,
                 {"motivo": "Chuva acima da média e atraso das esquadrias"})
if status not in (200, 201) or not v2:
    fatal(f"replanejar falhou (HTTP {status}: {v2})")
v2_id = v2["cronograma_id"]
check("a v2 nasce", v2["versao"] == 2 and v2["status"] == "rascunho")
check("apontando para a v1 como origem", v2["origem"] == plano_id)
check("com o motivo gravado", "chuva" in v2["motivo_replanejamento"].lower())

status, copia = req("GET", f"/api/pdca/atividades/?cronograma={v2_id}&page_size=50", demo)
copia_por_codigo = {a["codigo"]: a for a in (copia or {}).get("results", [])}
check("a árvore inteira foi copiada", len(copia_por_codigo) == 5)
check("e a hierarquia veio junto",
      copia_por_codigo["1.1"]["pai"] == copia_por_codigo["1"]["atividade_id"])
status, setas_v2 = req("GET", f"/api/pdca/precedencias/?cronograma={v2_id}", demo)
check("as setas também", (setas_v2 or {}).get("count") == 2)

# O desvio: encurtar a estaca na v2 e conferir contra a base.
estaca_v2 = copia_por_codigo["1.1"]
req("POST", f"/api/pdca/atividades/{estaca_v2['atividade_id']}/reprogramar/", demo,
    {"nao_comecar_antes_de": None, "duracao_dias": 3})
status, base = req("GET", f"/api/pdca/cronogramas/{v2_id}/linha-de-base/", demo)
check("a linha de base existe agora", status == 200 and base["tem_base"] is True)
check("e aponta para a v1", base["base"]["versao"] == 1)
linhas = {l["codigo"]: l for l in base["linhas"]}
check("a estaca aparece adiantada contra o combinado",
      linhas.get("1.1", {}).get("situacao") == "adiantada")
check("com o desvio em dias", isinstance(linhas.get("1.1", {}).get("desvio_dias"), int))


# --------------------------------------------------------------- 12. cobertura
print("\n12. A cobertura do orçamento traz o denominador")
status, cobertura = req("GET", f"/api/pdca/cronogramas/{v2_id}/cobertura/", demo)
check("`cobertura/` responde", status == 200 and cobertura is not None)
check("contando as folhas", cobertura and cobertura["folhas"] == 4)
check("e dizendo quantas ficaram sem peso — não escondendo",
      cobertura and cobertura["sem_peso"] == 4 and cobertura["cobertura"] == 0.0)

# Peso informado numa folha: a cobertura de **orçamento** não muda (ela mede
# vínculo, não peso), mas a contagem de peso informado sim. É a diferença entre
# "tem régua de custo" e "tem um número digitado".
req("PATCH", f"/api/pdca/atividades/{estaca_v2['atividade_id']}/", demo, {"peso_informado": "100.00"})
status, cobertura2 = req("GET", f"/api/pdca/cronogramas/{v2_id}/cobertura/", demo)
check("peso informado entra na conta certa",
      cobertura2 and cobertura2["com_peso_informado"] == 1 and cobertura2["sem_peso"] == 3)
check("e não é confundido com vínculo de orçamento", cobertura2 and cobertura2["com_item_orcado"] == 0)

status, atividade_peso = req("GET", f"/api/pdca/atividades/{estaca_v2['atividade_id']}/", demo)
check("a origem do peso viaja com ele", atividade_peso["peso_origem"] == "informado")

# ------------------------------------------------- 12b. escrita em lote e EAP
print("\n12b. Colar planilha e renumerar a EAP — numa requisição")
status, st = req("GET", "/api/pdca/status/", demo)
teto = ((st or {}).get("tetos") or {}).get("linhas_por_lote")
check("o módulo declara o teto por chamada, para a tela fatiar", isinstance(teto, int) and teto > 0)

status, resultado = req("POST", f"/api/pdca/cronogramas/{v2_id}/lote/", demo, {"edicoes": [
    {"atividade": copia_por_codigo["1.1"]["atividade_id"], "campos": {"nome": "Estaca hélice contínua"}},
    {"atividade": copia_por_codigo["1.2"]["atividade_id"], "campos": {"nome": "Blocos, baldrames e vigas"}},
]})
check("duas células numa chamada", status == 200 and (resultado or {}).get("atividades") == 2)

# A troca cruzada: o código novo de uma é o código atual da outra. Numa passada
# só isso bate na trava de unicidade — é o caso que obriga as duas passadas.
status, cruzado = req("POST", f"/api/pdca/cronogramas/{v2_id}/lote/", demo, {"edicoes": [
    {"atividade": copia_por_codigo["1.1"]["atividade_id"], "campos": {"codigo": "1.2"}},
    {"atividade": copia_por_codigo["1.2"]["atividade_id"], "campos": {"codigo": "1.1"}},
]})
check("a troca cruzada de códigos passa", status == 200)
check("e o servidor declara quantas renomeou", (cruzado or {}).get("renomeadas") == 2)

status, estouro = req("POST", f"/api/pdca/cronogramas/{v2_id}/lote/", demo, {"edicoes": [
    {"atividade": copia_por_codigo["2"]["atividade_id"], "campos": {"nome": f"n{i}"}}
    for i in range(teto + 1)
]})
check("acima do teto por chamada é recusado", status == 400)
check("e a recusa cita o número do dono", str(teto) in texto(estouro))

status, previa = req("POST", f"/api/pdca/cronogramas/{v2_id}/renumerar-eap/", demo, {"simular": True})
check("simular a renumeração conta sem escrever", status == 200 and previa["aplicadas"] == 0)
status, feito = req("POST", f"/api/pdca/cronogramas/{v2_id}/renumerar-eap/", demo, {"simular": False})
check("renumerar aplica de uma vez", status == 200 and feito["aplicadas"] == previa["mudancas"])

status, arvore2 = req("GET", f"/api/pdca/atividades/?cronograma={v2_id}&page_size=50", demo)
codigos = sorted(a["codigo"] for a in (arvore2 or {}).get("results", []))
check("a EAP saiu numerada na ordem da árvore", codigos == ["1", "1.1", "1.2", "2", "3"])

# ------------------------------------------------------------ 12c. plano modelo
print("\n12c. O plano modelo — não se planeja 300 unidades 300 vezes")
status, modelo = req("POST", f"/api/pdca/cronogramas/{v2_id}/marcar-modelo/", demo,
                     {"nome": "Padrão " + MARCA})
check("o plano entra na biblioteca", status == 200 and modelo["eh_modelo"] is True)

status, sem_nome = req("POST", f"/api/pdca/cronogramas/{v2_id}/marcar-modelo/", demo, {"nome": ""})
check("modelo sem nome é recusado", status == 400)

status, biblioteca = req("GET", "/api/pdca/cronogramas/modelos/", demo)
nomes = [c["nome_modelo"] for c in (biblioteca or {}).get("results", biblioteca or [])]
check("a biblioteca lista o modelo", status == 200 and ("Padrão " + MARCA) in nomes)

status, obra2 = req("POST", "/api/obras/", demo, {
    "nome_obra": MARCA + " — unidade 2", "endereco": "Rua de teste, 2",
})
obra2_id = obra2["obra_id"]
status, aplicado = req("POST", f"/api/pdca/cronogramas/{v2_id}/aplicar-modelo/", demo, {
    "obra": obra2_id, "data_inicio": inicio.isoformat(), "descricao": "Plano da unidade 2",
})
check("o modelo se aplica à obra nova", status == 201)
check("e o que nasce é rascunho v1, não modelo",
      aplicado and aplicado["versao"] == 1 and aplicado["status"] == "rascunho"
      and aplicado["eh_modelo"] is False)

status, copiadas = req("GET", f"/api/pdca/atividades/?cronograma={aplicado['cronograma_id']}&page_size=50", demo)
check("a estrutura inteira veio junto", (copiadas or {}).get("count") == 5)
status, setas_novas = req("GET", f"/api/pdca/precedencias/?cronograma={aplicado['cronograma_id']}", demo)
check("e a rede também", (setas_novas or {}).get("count") == 2)

status, repetido = req("POST", f"/api/pdca/cronogramas/{v2_id}/aplicar-modelo/", demo, {
    "obra": obra2_id, "data_inicio": inicio.isoformat(),
})
check("aplicar de novo na mesma obra é recusado", status == 400)
check("e manda replanejar, que é o caminho certo", "replaneje" in texto(repetido))

# -------------------------------------------------------------- 13. a fronteira
print("\n13. A fronteira do tenant")
status, _ = req("GET", f"/api/pdca/cronogramas/{plano_id}/", acme)
check("outro tenant não alcança o cronograma (403 ou 404, nunca 200)", status in (403, 404))
status, lista = req("GET", "/api/pdca/cronogramas/", demo)
ids = [c["cronograma_id"] for c in (lista or {}).get("results", [])]
check("e a listagem do dono traz os dois planos dele", plano_id in ids and v2_id in ids)

# ------------------------------------------------------------------ 14. faxina
print("\n14. Faxina — e as três recusas que ela encontra pelo caminho")
status, _ = req("DELETE", f"/api/pdca/cronogramas/{v2_id}/", demo)
check("o rascunho sai", status in (200, 204))

status, vigente = req("DELETE", f"/api/pdca/cronogramas/{plano_id}/", demo)
check("o vigente NÃO sai — ele é substituído, não apagado", status == 400)
check("e a recusa diz isso", "substitu" in texto(vigente))

# A obra fica: o calendário dela é `PROTECT` do cronograma vigente. A recusa
# **com motivo** é o que este teste cobra — até 23/08/2026 ela era um 500, com a
# página de erro do Django quebrando por cima (ver nucleo/excecoes.py).
status, protegido = req("DELETE", f"/api/obras/{obra_id}/", demo)
check("a obra com plano vigente é recusada com 409, e não com 500", status == 409)
check("nomeando quantos dependem", protegido and protegido.get("total_dependentes", 0) >= 1)
check("e sem imprimir o objeto protegido",
      protegido and "cronograma" in texto(protegido.get("dependentes", [])))

print(f"     a obra '{MARCA}' (id {obra_id}) fica no banco com o plano vigente;")
print("     para remover:  docker exec sgi-erp python manage.py shell -c \\")
print(f"       \"from obras.models import Obra; Obra.objects.filter(pk={obra_id}).delete()\"")
print("     (excluir obra com plano publicado é decisão de produto — D116 em pendencias.md)")


ok = sum(1 for p in passed if p)
print(f"\n{'='*58}\nPDCA.1: {ok}/{len(passed)} checks")
sys.exit(0 if ok == len(passed) else 1)
