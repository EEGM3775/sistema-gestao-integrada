"""Fase 7 / E.3 — módulo SIL (estoque & logística interna) e o laço vivo com o SCM,
via gateway (8090).

Prova ponta a ponta que os dois sentidos da integração funcionam com um token real
da IAM — o que a suíte unitária não cobre (entitlement `sil`, permissões `sil.*` e a
persona `almoxarife` só existem depois do rebuild da imagem da IAM + re-seed).

Seed: iam/seed_demo.py (tenant demo) + backend/seed_demo_data.py

  demo     / demo123     -> módulos scm+sil, papéis `suprimentos` + `almoxarife`
  semdrone / semdrone123 -> só erp_financeiro, papel `operacional` — SEM o módulo `sil`

  1. Módulo vivo               -> GET /api/sil/status/ 200.
  2. Entitlement fecha         -> semdrone em /api/sil/saldos/ -> 403.
  3. SCM -> SIL (ida)          -> compra direta + recebimento gera ENTRADA no estoque,
                                  no local do seam `local_entrega`, ao preço do pedido.
  4. Custo médio ponderado     -> a entrada recalcula o custo médio do saldo.
  5. Idempotência do signal    -> re-salvar a linha do recebimento NÃO duplica a entrada.
  6. SIL -> SCM (volta)        -> saldo abaixo do mínimo -> `gerar_demanda` cria Demanda
                                  (origem=estoque) no SCM, com o item certo.
  7. Requisição ponta a ponta  -> criar -> aprovar (reserva) -> atender (baixa o saldo),
                                  apropriando obra + etapa na movimentação.
  8. Físico-financeiro         -> o consumo aparece em /api/sil/aplicado/ na obra/etapa,
                                  com `orcado` nulo (módulo Orçamento ainda não existe).

Rodar (stack de pé):  python infra/gateway/phase7_sil_test.py
                      SGI_GW=https://localhost:8443 python infra/gateway/phase7_sil_test.py
"""
import json, os, ssl, sys, urllib.error, urllib.request
from decimal import Decimal

# Console do Windows costuma ser cp1252 e quebra em emoji/acentos ao redirecionar.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")  # SGI_GW aponta ao staging (10.7)

# O staging usa certificado autoassinado (nginx.staging.conf); o dev é http.
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=30, context=_CTX) as resp:
            payload = resp.read().decode() or "null"
            return resp.status, json.loads(payload)
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


def linhas(payload):
    """Normaliza a resposta: paginada (dict com 'results') ou lista pura."""
    if isinstance(payload, dict):
        return payload.get("results", [])
    return payload or []


def D(v):
    return Decimal(str(v or 0))


passed = []
def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def fatal(msg):
    print(f"\n  !! {msg}")
    print("     O seed do backend (backend/seed_demo_data.py) precisa ter rodado.")
    sys.exit(2)


demo = login("demo", "demo123")
semdrone = login("semdrone", "semdrone123")

print("== 1. Módulo SIL vivo pelo gateway ==")
status, st = req("GET", "/api/sil/status/", demo)
check(f"GET /api/sil/status/ (200) -> {status}", status == 200)

print("== 2. Entitlement do módulo fecha para quem não assina ==")
status, _ = req("GET", "/api/sil/saldos/", semdrone)
check(f"semdrone (sem o módulo sil) -> 403, veio {status}", status == 403)
status, _ = req("GET", "/api/sil/saldos/", demo)
check(f"demo (almoxarife) -> 200, veio {status}", status == 200)

# --- Setup: uma oferta de compra direta cujo produto seja estocável -----------
print("== Setup: oferta de compra direta com item estocável ==")
status, ofertas = req("GET", "/api/scm/ofertas/?compra_direta=true&page_size=50", demo)
if status != 200:
    fatal(f"não consegui listar ofertas do SCM (status {status})")
oferta = None
for o in linhas(ofertas):
    if not o.get("compra_direta"):
        continue
    s, item = req("GET", f"/api/catalogo/itens/{o['produto']}/", demo)
    if s == 200 and item.get("estocavel"):
        oferta, item_cat = o, item
        break
if oferta is None:
    fatal("nenhuma oferta com compra_direta e item estocável no seed")
print(f"  oferta={oferta['oferta_id']} item={item_cat['item_id']} ({item_cat['descricao']})"
      f" preco_direto={oferta.get('preco_direto')}")

# Local de destino: o seam `local_entrega` do recebimento resolve por nome.
status, locais = req("GET", "/api/sil/locais/?tipo=central", demo)
central = next((l for l in linhas(locais) if l.get("ativo")), None)
if central is None:
    fatal("nenhum local de estoque central ativo no seed")
print(f"  local de entrega: {central['local_id']} ({central['nome']})")

ITEM, LOCAL = item_cat["item_id"], central["local_id"]
QTD = Decimal("40")


def saldo_de(item_id, local_id):
    s, payload = req("GET", f"/api/sil/saldos/?item={item_id}&local={local_id}", demo)
    linha = next(iter(linhas(payload)), None)
    return linha or {}


antes = saldo_de(ITEM, LOCAL)
q_antes, c_antes = D(antes.get("quantidade")), D(antes.get("custo_medio"))
print(f"  saldo antes: quantidade={q_antes} custo_medio={c_antes}")

print("== 3. SCM -> SIL: recebimento de compra direta vira ENTRADA no estoque ==")
status, pedido = req("POST", "/api/scm/pedidos/comprar_direto/", demo, {
    "oferta": oferta["oferta_id"], "quantidade": str(QTD),
})
check(f"compra direta gera pedido (201) -> {status}", status == 201)
if status != 201:
    fatal("a compra direta falhou; sem pedido não há recebimento")
pedido_id = pedido["pedido_id"]

status, itens_pedido = req("GET", f"/api/scm/itens-pedido/?pedido={pedido_id}", demo)
ip = next(iter(linhas(itens_pedido)), None)
check("pedido tem a linha do item", ip is not None and str(ip["produto"]) == str(ITEM))
preco = D(ip["preco_unitario"]) if ip else D(0)

status, receb = req("POST", "/api/scm/recebimentos/", demo, {
    "pedido": pedido_id, "tipo": "total", "local_entrega": central["nome"],
    "observacao": "E2E Fase 7 — laço SCM->SIL",
})
check(f"recebimento criado (201) -> {status}", status == 201)
if status != 201:
    fatal("sem recebimento não há entrada de estoque")
receb_id = receb["recebimento_id"]

status, ir = req("POST", "/api/scm/itens-recebimento/", demo, {
    "recebimento": receb_id, "item_pedido": ip["item_pedido_id"], "quantidade_recebida": str(QTD),
})
check(f"linha de recebimento criada (201) -> {status}", status == 201)
ir_id = ir.get("item_recebimento_id") if isinstance(ir, dict) else None

status, movs = req("GET", f"/api/sil/movimentacoes/?recebimento_scm_ref={receb_id}", demo)
entradas = linhas(movs)
check(f"o signal gerou 1 movimentação de entrada -> {len(entradas)}", len(entradas) == 1)
if entradas:
    m = entradas[0]
    check(f"tipo=entrada -> {m['tipo']}", m["tipo"] == "entrada")
    check(f"quantidade={QTD} -> {m['quantidade']}", D(m["quantidade"]) == QTD)
    check(f"local do seam local_entrega={LOCAL} -> {m['local']}", str(m["local"]) == str(LOCAL))
    check(f"custo veio do preço do pedido ({preco}) -> {m['custo_unitario']}",
          D(m["custo_unitario"]) == preco)

print("== 4. Custo médio ponderado móvel ==")
depois = saldo_de(ITEM, LOCAL)
q_depois, c_depois = D(depois.get("quantidade")), D(depois.get("custo_medio"))
check(f"saldo subiu {QTD}: {q_antes} -> {q_depois}", q_depois == q_antes + QTD)
esperado = ((q_antes * c_antes + QTD * preco) / (q_antes + QTD)) if (q_antes + QTD) > 0 else D(0)
# Compara com a precisão persistida (4 casas), não com o racional exato.
check(f"custo médio ponderado ~= {esperado:.4f} -> {c_depois}",
      abs(c_depois - esperado) <= Decimal("0.0001"))

print("== 5. Idempotência: re-salvar a linha do recebimento não duplica a entrada ==")
status, _ = req("PATCH", f"/api/scm/itens-recebimento/{ir_id}/", demo,
                {"quantidade_recebida": str(QTD)})
status2, movs2 = req("GET", f"/api/sil/movimentacoes/?recebimento_scm_ref={receb_id}", demo)
check(f"segue com 1 movimentação depois do re-save -> {len(linhas(movs2))}",
      len(linhas(movs2)) == 1)
depois2 = saldo_de(ITEM, LOCAL)
check(f"saldo inalterado pelo re-save -> {D(depois2.get('quantidade'))}",
      D(depois2.get("quantidade")) == q_depois)

print("== 6. SIL -> SCM: abaixo do mínimo gera Demanda de reposição ==")
alvo = q_depois + Decimal("100")  # ponto de reposição acima do saldo => abaixo do mínimo
saldo_id = depois.get("saldo_id") or depois.get("id")
status, s_min = req("POST", f"/api/sil/saldos/{saldo_id}/definir_minimo/", demo,
                    {"ponto_reposicao": str(alvo)})
check(f"definir_minimo (200) -> {status}", status == 200)
check(f"saldo marcado abaixo_minimo -> {s_min.get('abaixo_minimo') if s_min else None}",
      bool(s_min and s_min.get("abaixo_minimo")))

status, fila = req("GET", "/api/sil/saldos/?abaixo_minimo=1", demo)
check("item entra na fila de reposição do cockpit",
      any(str(l.get("saldo_id") or l.get("id")) == str(saldo_id) for l in linhas(fila)))

status, dem = req("POST", f"/api/sil/saldos/{saldo_id}/gerar_demanda/", demo, {"quantidade": "60"})
check(f"gerar_demanda (201) -> {status}", status == 201)
demanda_id = dem.get("demanda_id") if isinstance(dem, dict) else None

status, demanda = req("GET", f"/api/scm/demandas/{demanda_id}/", demo)
check(f"a Demanda existe no SCM (200) -> {status}", status == 200)
if status == 200:
    check(f"origem=estoque -> {demanda.get('origem')}", demanda.get("origem") == "estoque")
    check(f"status=aberta -> {demanda.get('status')}", demanda.get("status") == "aberta")
status, itens_dem = req("GET", f"/api/scm/itens-demanda/?demanda={demanda_id}", demo)
idem = next(iter(linhas(itens_dem)), None)
check(f"a linha da demanda aponta o item do estoque ({ITEM}) -> {idem and idem.get('produto')}",
      idem is not None and str(idem["produto"]) == str(ITEM) and D(idem["quantidade"]) == D(60))

print("== 7. Requisição: criar -> aprovar (reserva) -> atender (baixa) ==")
status, obras = req("GET", "/api/obras/?page_size=50", demo)
if status != 200:
    fatal(f"não consegui listar obras (status {status})")
# A apropriação por etapa é feature-título do SIL v2: procura uma obra que TENHA
# etapa em vez de seguir sem ela (um check pulado em silêncio não prova nada).
obra_id = etapa_id = None
for o in linhas(obras):
    oid = o.get("obra_id") or o.get("id")
    s, etapas = req("GET", f"/api/etapas-obras/?obra={oid}&page_size=1", demo)
    if s != 200:
        fatal(f"rota de etapas respondeu {s} — o E2E não consegue provar a apropriação")
    et = next(iter(linhas(etapas)), None)
    if et:
        obra_id, etapa_id = oid, et.get("etapa_id") or et.get("id")
        break
if etapa_id is None:
    fatal("nenhuma obra com etapa no seed — sem isso a apropriação por etapa fica sem prova")
print(f"  apropriação: obra={obra_id} etapa={etapa_id}")

status, requisicao = req("POST", "/api/sil/requisicoes/", demo, {
    "local": LOCAL, "obra": obra_id, "etapa": etapa_id,
    "observacao": "E2E Fase 7 — consumo na etapa",
})
check(f"requisição criada (201) -> {status}", status == 201)
req_id = requisicao.get("requisicao_id") if isinstance(requisicao, dict) else None

CONSUMO = Decimal("10")
status, _ = req("POST", "/api/sil/itens-requisicao/", demo, {
    "requisicao": req_id, "item": ITEM, "quantidade": str(CONSUMO),
})
check(f"linha da requisição criada (201) -> {status}", status == 201)

status, aprovada = req("POST", f"/api/sil/requisicoes/{req_id}/aprovar/", demo, {})
check(f"aprovar (200) -> {status}", status == 200)
check(f"status=aprovada -> {aprovada.get('status') if aprovada else None}",
      bool(aprovada) and aprovada.get("status") == "aprovada")
reservado = D(saldo_de(ITEM, LOCAL).get("reservado"))
check(f"aprovação reservou {CONSUMO} -> reservado={reservado}", reservado >= CONSUMO)

status, atendida = req("POST", f"/api/sil/requisicoes/{req_id}/atender/", demo, {})
check(f"atender (200) -> {status}", status == 200)
check(f"status=atendida -> {atendida.get('status') if atendida else None}",
      bool(atendida) and atendida.get("status") == "atendida")

final = saldo_de(ITEM, LOCAL)
check(f"saldo baixou {CONSUMO}: {q_depois} -> {D(final.get('quantidade'))}",
      D(final.get("quantidade")) == q_depois - CONSUMO)
check(f"reserva liberada na baixa -> reservado={D(final.get('reservado'))}",
      D(final.get("reservado")) == reservado - CONSUMO)

status, saidas = req("GET", f"/api/sil/movimentacoes/?requisicao={req_id}", demo)
saida = next(iter(linhas(saidas)), None)
check("a saída ficou no ledger", saida is not None and saida["tipo"] == "saida")
if saida:
    check(f"apropriada na obra {obra_id} -> {saida.get('obra')}",
          str(saida.get("obra")) == str(obra_id))
    check(f"apropriada na etapa {etapa_id} -> {saida.get('etapa')}",
          str(saida.get("etapa")) == str(etapa_id))
    check(f"saída valorizada pelo custo médio ({c_depois:.4f}) -> {saida.get('custo_unitario')}",
          abs(D(saida.get("custo_unitario")) - c_depois) <= Decimal("0.0001"))

print("== 8. Físico-financeiro: o consumo aparece em aplicado/ ==")
status, aplicado = req("GET", f"/api/sil/aplicado/?obra={obra_id}", demo)
check(f"GET /api/sil/aplicado/ (200) -> {status}", status == 200)
linha_obra = next((l for l in (aplicado or [])
                   if str(l.get("obra")) == str(obra_id) and str(l.get("etapa")) == str(etapa_id)), None)
check(f"a obra/etapa aparece com valor aplicado > 0 -> {linha_obra and linha_obra['aplicado']}",
      linha_obra is not None and D(linha_obra["aplicado"]) > 0)
# O seam do orçado: até 25/07 este check exigia `orcado is None` "porque o módulo
# Orçamento não existe". O módulo existe desde a ORC.1 e preenche a coluna quando
# a obra/etapa tem régua aprovada — a asserção antiga passava por sorte (depende de
# qual obra o loop acima escolhe) e viraria vermelha na primeira obra com orçamento.
# O contrato que vale nos dois mundos: a chave existe; o valor é o orçado ou nulo.
# Quem prova o lado cheio é o orc6_orcamento_test.py (passo 10).
check("a linha declara a coluna `orcado` (nula sem régua aprovada, preenchida com ela) -> "
      f"{linha_obra and linha_obra.get('orcado')}",
      linha_obra is not None and "orcado" in linha_obra)

print()
ok = sum(1 for p in passed if p)
print(f"RESULTADO: {ok}/{len(passed)}")
sys.exit(0 if ok == len(passed) else 1)
