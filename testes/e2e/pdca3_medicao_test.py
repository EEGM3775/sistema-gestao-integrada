"""PDCA.3 — do avanço apontado ao título no ERP, pelo gateway (8090).

Prova com **token real da IAM** o que a suíte unitária do `modulopdca` não
alcança. Lá o serviço é chamado direto e o usuário é empurrado com
`force_authenticate`; aqui cada gesto atravessa login, assinatura RS256,
gateway, entitlement de módulo, permissão de campo e RLS — que é onde dinheiro
saindo quebra de verdade.

**Por que esta fatia ganhou E2E próprio** (as demais esperam a PDCA.13): é a
primeira em que o módulo **escreve no ERP**. O `conta_pagar_ref` existia como
seam inerte desde 07/2026 e nunca foi preenchido por ninguém; um teste de
unidade prova que a função cria o título, não que ele atravessa a fronteira de
tenant, o entitlement do ERP e a RLS com o token de quem apertou o botão.

Seed: testes/seeds/seed_demo.py + testes/seeds/seed_demo_data.py

  demo     / demo123     -> `gestor_contratos`: monta contrato e APURA medição.
                            **Não ateste** — é o lado de cá da segregação §8.
  gerente  / gerente123  -> `diretoria`: ATESTE e não apura. O lado de lá.
  semdrone / semdrone123 -> NÃO tem o módulo: é a camada 1.
  acme     / acme123     -> outro tenant: é a fronteira.

  1. Camada 1      -> quem não assina `pdca` não passa em contrato nem medição.
  2. O módulo declara-> `status/` diz o que existe e o que ainda não existe.
  3. Cenário        -> obra, plano vigente, duas frentes e avanço apontado.
  4. O contrato     -> planilha contratual com 5% de retenção e condição escrita.
  5. A prévia       -> a proposta NASCE DO AVANÇO e não grava nada.
  6. A grade        -> abrir a medição com o ajuste do gestor, que fica visível.
  7. A trava        -> acumulado acima do contratado é recusado com o excesso.
  8. Segregação     -> `demo` submete e NÃO aprova; `gerente` ateste.
  9. O título       -> o líquido vira `ContaPagar` de verdade, legível pelo ERP.
 10. Retenção       -> retido some no líquido, e a liberação vira título próprio.
 11. Retificação    -> aprovada não se edita; a retificadora nasce vazia.
 12. A fronteira    -> outro tenant não enxerga nada disto.
 13. Faxina         -> o teste desfaz o que criou.

Rodar (stack de pé):  python testes/e2e/pdca3_medicao_test.py
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

from _segundo_fator import completar_login
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

MARCA = "E2E PDCA.3 " + uuid.uuid4().hex[:8]

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
        return completar_login(GW, resp, _CTX)["sessao"]


def texto(resposta) -> str:
    return json.dumps(resposta, ensure_ascii=False).lower() if resposta is not None else ""


def dec(v) -> float:
    """O dinheiro chega como **string** de propósito (o float do JSON não
    representa centavo). Converter só aqui, para comparar, é o que mantém a
    asserção honesta sem reintroduzir o erro na travessia."""
    return float(v)


print(f"\n{'='*62}\nPDCA.3 — contrato, medição e título no ERP pelo gateway\n{'='*62}")
print(f"Gateway: {GW}")

try:
    demo = login("demo", "demo123")
    gerente = login("gerente", "gerente123")
    admin = login("admin", "admin123")
    semdrone = login("semdrone", "semdrone123")
    acme = login("acme", "acme123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé? Rodou os dois seeds?")

# --------------------------------------------------------------- 1. camada 1
print("\n1. Quem não assina o módulo não passa")
status, _ = req("GET", "/api/pdca/contratos/", semdrone)
check("`semdrone` (sem `pdca`) leva 403 em contratos", status == 403)
status, _ = req("GET", "/api/pdca/medicoes/", semdrone)
check("e 403 em medições", status == 403)

# ------------------------------------------------------- 2. o módulo declara
print("\n2. O módulo declara o que existe")
status, st = req("GET", "/api/pdca/status/", demo)
check("`demo` lê o status", status == 200)
recursos = (st or {}).get("recursos", {})
check("`contrato` e `medicao` estão de pé", recursos.get("contrato") is True
      and recursos.get("medicao") is True)
check("`retencao` também", recursos.get("retencao") is True)
check("e `aditivo` passou a existir (PDCA.4)", recursos.get("aditivo") is True)
check("o que a fatia NÃO fecha continua declarado como ausente",
      recursos.get("importar_planilha_do_empreiteiro") is False
      and recursos.get("anexo_por_linha") is False)
tetos = (st or {}).get("tetos", {})
check("os tetos da fatia vêm do servidor (o dono decide o número)",
      isinstance(tetos.get("itens_por_contrato"), int)
      and isinstance(tetos.get("linhas_por_medicao"), int))

# ------------------------------------------------------- 3. o cenário do teste
print("\n3. Obra, plano vigente e avanço apontado")
status, obra = req("POST", "/api/obras/", demo, {
    "nome_obra": MARCA, "endereco": "Rua da Medição, s/n",
    "status_obra": "planejamento",
})
if status not in (200, 201) or not obra:
    fatal(f"não consegui criar a obra do teste (HTTP {status}: {obra})")
obra_id = obra["obra_id"]
check("obra criada só para este teste", True)

status, calendario = req("POST", "/api/pdca/calendarios/", demo, {
    "obra": obra_id, "nome": "Expediente " + MARCA,
    "trabalha_sabado": False, "trabalha_domingo": False,
})
if status not in (200, 201):
    fatal(f"calendário falhou (HTTP {status}: {calendario})")

# Uma segunda-feira no passado: sem passado não há avanço para medir.
inicio_plano = date.today() - timedelta(days=60)
inicio_plano -= timedelta(days=inicio_plano.weekday())

status, crono = req("POST", "/api/pdca/cronogramas/", demo, {
    "obra": obra_id, "descricao": "Plano " + MARCA,
    "data_inicio": inicio_plano.isoformat(), "calendario": calendario["calendario_id"],
})
if status not in (200, 201) or not crono:
    fatal(f"cronograma falhou (HTTP {status}: {crono})")
crono_id = crono["cronograma_id"]

atividades = {}
for codigo, nome, dias in (("1", "Alvenaria", 30), ("2", "Reboco", 25)):
    status, a = req("POST", "/api/pdca/atividades/", demo, {
        "cronograma": crono_id, "codigo": codigo, "nome": nome,
        "duracao_dias": dias, "peso_informado": "100",
    })
    if status not in (200, 201) or not a:
        fatal(f"atividade {codigo} falhou (HTTP {status}: {a})")
    atividades[codigo] = a["atividade_id"]
check("WBS com duas frentes", len(atividades) == 2)

status, _ = req("POST", f"/api/pdca/cronogramas/{crono_id}/publicar/", demo)
check("plano publicado (vigente) — é sobre ele que a medição é calculada",
      status in (200, 201))

dia_avanco = (inicio_plano + timedelta(days=7)).isoformat()
status, ap = req("POST", "/api/pdca/apontamentos/", demo, {
    "atividade": atividades["1"], "data": dia_avanco, "percentual": "30",
})
check("30% apontados na alvenaria", status in (200, 201))
status, _ = req("POST", "/api/pdca/apontamentos/", demo, {
    "atividade": atividades["2"], "data": dia_avanco, "percentual": "20",
})
check("20% apontados no reboco", status in (200, 201))

# ------------------------------------------------- 3b. a escada do tenant
# Montar a escada é ato de **administração** (`plataforma.fluxo_aprovacao.edit`),
# e é o que um tenant real faz antes da primeira medição. O teste passa por esse
# caminho em vez de contorná-lo: sem escada, submeter aprovaria em um passo e
# exigiria `atestar` de quem apura — que é justamente a segregação em jogo.
print("\n3b. A escada de atesto da empresa (ato do admin do tenant)")
status, alvos = req("GET", "/api/aprovacao/fluxos/alvos/", admin)
check("o admin descobre quais documentos aceitam escada", status == 200)
alvo_medicao = next(
    (a for a in (alvos or []) if a["codigo"] == "modulopdca.medicao"), None,
)
check("a medição aparece entre eles (declarou a GenericRelation)",
      alvo_medicao is not None)
if alvo_medicao is None:
    fatal("sem o ContentType da medição não dá para montar a escada")

status, fluxos = req(
    "GET", f"/api/aprovacao/fluxos/?alvo={alvo_medicao['id']}&padrao=true", admin,
)
existente = (
    fluxos if isinstance(fluxos, list) else (fluxos or {}).get("results") or []
)
fluxo_id = existente[0]["fluxo_id"] if existente else None
if fluxo_id is None:
    status, fluxo = req("POST", "/api/aprovacao/fluxos/", admin, {
        "codigo": "medicao-obra", "nome": "Aprovação de medição",
        "alvo": alvo_medicao["id"], "padrao": True, "ativo": True,
    })
    if status not in (200, 201) or not fluxo:
        fatal(f"criar o fluxo falhou (HTTP {status}: {fluxo})")
    fluxo_id = fluxo["fluxo_id"]
    status, nivel = req("POST", "/api/aprovacao/niveis/", admin, {
        "fluxo": fluxo_id, "ordem": 1, "nome": "Gerente de contrato",
        "permissao_exigida": "pdca.medicao.atestar",
    })
    if status not in (200, 201):
        fatal(f"criar o degrau falhou (HTTP {status}: {nivel})")
check("escada de um degrau exigindo `pdca.medicao.atestar`", fluxo_id is not None)

status, valida = req("GET", f"/api/aprovacao/fluxos/{fluxo_id}/validar/", admin)
check("e ela se declara utilizável ANTES de alguém depender dela",
      status == 200 and (valida or {}).get("valido") is True)

status, negado = req("POST", "/api/aprovacao/fluxos/", demo, {
    "codigo": "pirata", "nome": "Escada do operador",
    "alvo": alvo_medicao["id"], "padrao": False,
})
check("quem opera o documento NÃO monta a própria escada", status == 403)

# ----------------------------------------------------------- 4. o contrato
print("\n4. O contrato — planilha, retenção e a condição que a libera")
status, fornecedores = req("GET", "/api/fornecedores/?page_size=1", demo)
# `/api/fornecedores/` responde **lista crua** quando não paginada, e página
# quando paginada — o teste aceita as duas em vez de fixar a que vale hoje.
lista_forn = (
    fornecedores if isinstance(fornecedores, list)
    else (fornecedores or {}).get("results") or []
)
if not lista_forn:
    fatal("o seed não tem fornecedor — o contrato usa o cadastro que já existe (§7)")
fornecedor_id = lista_forn[0]["fornecedor_id"]

status, contrato = req("POST", "/api/pdca/contratos/", demo, {
    "obra": obra_id, "fornecedor": fornecedor_id,
    "numero": "E2E-" + uuid.uuid4().hex[:6], "objeto": "Alvenaria e revestimento",
    "regime": "unitario", "data_inicio": inicio_plano.isoformat(),
    "retencao_percentual": "5", "retencao_natureza": "tecnica",
    "retencao_condicao_liberacao": "Aceitação definitiva dos serviços pela fiscalização.",
    "prazo_pagamento_dias": 30, "status": "vigente",
})
if status not in (200, 201) or not contrato:
    fatal(f"contrato falhou (HTTP {status}: {contrato})")
contrato_id = contrato["contrato_id"]
check("contrato vigente criado pelo `gestor_contratos`", True)

status, recusado = req("POST", "/api/pdca/contratos/", demo, {
    "obra": obra_id, "fornecedor": fornecedor_id, "numero": "E2E-GLOBAL",
    "objeto": "Sem valor", "regime": "global",
    "data_inicio": inicio_plano.isoformat(),
})
check("regime global sem valor fechado é recusado com o motivo",
      status == 400 and "valor" in texto(recusado))

itens = {}
for codigo, desc, atividade, qtd, preco in (
    ("1.1", "Alvenaria de blocos", "1", "1000", "80"),
    ("1.2", "Reboco interno", "2", "500", "40"),
):
    status, item = req("POST", "/api/pdca/itens-contrato/", demo, {
        "contrato": contrato_id, "codigo": codigo, "descricao": desc,
        "unidade": "m2", "atividade": atividades[atividade],
        "quantidade_contratada": qtd, "preco_unitario": preco,
    })
    if status not in (200, 201) or not item:
        fatal(f"item {codigo} falhou (HTTP {status}: {item})")
    itens[codigo] = item["item_contrato_id"]
check("planilha contratual com 2 itens (R$ 100.000)", len(itens) == 2)

status, saldo = req("GET", f"/api/pdca/contratos/{contrato_id}/saldo/", demo)
check("o saldo é derivado e vem do servidor",
      status == 200 and dec(saldo["valor_contratado"]) == 100000.0)
check("e o dinheiro viaja como string, não como float",
      isinstance(saldo["valor_contratado"], str))

# --------------------------------------------------------------- 5. a prévia
print("\n5. A prévia — a medição NASCE do avanço, e não grava nada")
p_ini = inicio_plano.isoformat()
p_fim = (inicio_plano + timedelta(days=30)).isoformat()
status, proposta = req(
    "GET",
    f"/api/pdca/contratos/{contrato_id}/proposta-de-medicao/?inicio={p_ini}&fim={p_fim}",
    demo,
)
check("a prévia responde", status == 200)
linhas = {l["codigo"]: l for l in (proposta or {}).get("linhas", [])}
check("30% de 1.000 m² viram 300 m² propostos — ninguém digitou este número",
      dec(linhas["1.1"]["quantidade_proposta"]) == 300.0)
check("20% de 500 m² viram 100 m²",
      dec(linhas["1.2"]["quantidade_proposta"]) == 100.0)
check("a proposta declara o critério de cada linha",
      linhas["1.1"]["criterio"] == "direto")
status, medicoes = req("GET", f"/api/pdca/medicoes/?contrato={contrato_id}", demo)
check("e a prévia NÃO gravou medição nenhuma", (medicoes or {}).get("count") == 0)

# ---------------------------------------------------------------- 6. a grade
print("\n6. A grade — o gestor confere e ajusta, e o ajuste fica visível")
status, medicao = req("POST", "/api/pdca/medicoes/abrir/", demo, {
    "contrato": contrato_id, "inicio": p_ini, "fim": p_fim,
    "linhas": [
        {"item_contrato_id": itens["1.1"], "quantidade": "250"},
        {"item_contrato_id": itens["1.2"], "quantidade": "100"},
    ],
})
if status not in (200, 201) or not medicao:
    fatal(f"abrir medição falhou (HTTP {status}: {medicao})")
medicao_id = medicao["medicao_id"]
check("medição 1 aberta em rascunho", medicao["status"] == "rascunho"
      and medicao["numero"] == 1)

linha_alv = next(i for i in medicao["itens"] if i["codigo"] == "1.1")
check("o gestor mediu 250 onde o sistema propôs 300",
      dec(linha_alv["quantidade"]) == 250.0
      and dec(linha_alv["quantidade_proposta"]) == 300.0)
check("e o ajuste é declarado na própria linha", linha_alv["origem"] == "manual")
check("bruto = 250×80 + 100×40 = R$ 24.000",
      dec(medicao["totais"]["bruto"]) == 24000.0)
check("retenção de 5% = R$ 1.200", dec(medicao["totais"]["retencao"]) == 1200.0)
check("líquido = R$ 22.800", dec(medicao["totais"]["liquido"]) == 22800.0)

# ----------------------------------------------------------------- 7. a trava
print("\n7. A trava do mercado — acumulado não excede o contratado")
status, recusa = req("POST", f"/api/pdca/medicoes/{medicao_id}/linhas/", demo, {
    "linhas": [{"item_contrato_id": itens["1.1"], "quantidade": "1200"}],
})
check("a grade aceita a digitação (a recusa é do documento, não da célula)",
      status in (200, 201))
status, recusa = req("POST", f"/api/pdca/medicoes/{medicao_id}/submeter/", demo)
check("submeter 1.200 de um contratado de 1.000 é recusado",
      status == 400 and "excede o contratado" in texto(recusa))
check("e a mensagem aponta o caminho certo (aditivo, não medição)",
      "aditivo" in texto(recusa))

# devolve a grade ao estado conferido
status, _ = req("POST", f"/api/pdca/medicoes/{medicao_id}/linhas/", demo, {
    "linhas": [
        {"item_contrato_id": itens["1.1"], "quantidade": "250"},
        {"item_contrato_id": itens["1.2"], "quantidade": "100"},
    ],
})
check("a grade é reescrita (substitui, não soma)", status in (200, 201))
status, conferida = req("GET", f"/api/pdca/medicoes/{medicao_id}/", demo)
check("e continua com 2 linhas depois de duas reescritas",
      len(conferida["itens"]) == 2)

# ------------------------------------------------------------ 8. segregação
print("\n8. Quem apura não ateste (§8) — com token real dos dois lados")
status, _ = req("GET", f"/api/pdca/medicoes/{medicao_id}/", gerente)
check("`gerente` lê a medição", status == 200)
status, negado = req("POST", "/api/pdca/medicoes/abrir/", gerente, {
    "contrato": contrato_id, "inicio": p_ini, "fim": p_fim,
})
check("`gerente` NÃO apura (sem `pdca.medicao.apurar`)", status == 403)

status, submetida = req("POST", f"/api/pdca/medicoes/{medicao_id}/submeter/", demo)
if status != 200:
    fatal(f"submeter falhou (HTTP {status}: {submetida})")
estado = (submetida or {}).get("estado")
check("`demo` submete — e com escada montada isso NÃO aprova nada",
      estado == "em_aprovacao")
status, parada = req("GET", f"/api/pdca/medicoes/{medicao_id}/", demo)
check("a medição diz em que degrau está parada, e o que ele exige",
      (parada.get("escada") or {}).get("permissao_exigida") == "pdca.medicao.atestar")
check("e ainda não gerou título nenhum", parada.get("conta_pagar_ref") is None)

status, negado = req("POST", f"/api/pdca/medicoes/{medicao_id}/atestar/", demo,
                     {"aprovar": True})
check("`demo` não ateste (nem o degrau o aceita, nem ele tem o verbo)",
      status in (400, 403))
status, atestada = req("POST", f"/api/pdca/medicoes/{medicao_id}/atestar/",
                       gerente, {"aprovar": True})
check("`gerente` ateste e a escada termina", status == 200)

# ------------------------------------------------------------- 9. o título
print("\n9. O título no ERP — a primeira escrita real nesta fronteira")
status, aprovada = req("GET", f"/api/pdca/medicoes/{medicao_id}/", demo)
check("a medição está aprovada e congelada",
      aprovada["status"] == "aprovada" and aprovada["congelada_em"])
conta_ref = aprovada.get("conta_pagar_ref")
check("e gerou a referência do título", isinstance(conta_ref, int))

if conta_ref:
    # A leitura é pelo ERP, com o token de quem apurou — é o que prova que o
    # título atravessou a fronteira inteira (tenant, entitlement, RLS) e não só
    # que uma linha foi gravada no banco.
    status, conta = req("GET", f"/api/erp/contas-a-pagar/{conta_ref}/", demo)
    if status == 200 and conta:
        check("o título existe no ERP, legível pelo módulo financeiro", True)
        check("e vale o LÍQUIDO, não o bruto (a retenção fica com a construtora)",
              dec(conta["valor"]) == 22800.0)
        check("a descrição diz de onde ele veio",
              "medição" in (conta.get("descricao") or "").lower())
    else:
        check(f"o título é legível pelo ERP (HTTP {status})", False)

status, rejeitada = req("POST", f"/api/pdca/medicoes/{medicao_id}/linhas/", demo, {
    "linhas": [{"item_contrato_id": itens["1.1"], "quantidade": "10"}],
})
check("medição aprovada não aceita mais reescrita", status == 400)

# ------------------------------------------------------------- 10. retenção
print("\n10. A retenção — retida na medição, devolvida em título próprio")
status, ret = req("GET", f"/api/pdca/contratos/{contrato_id}/retencao/", demo)
check("o retido é somado na leitura (não há coluna de saldo)",
      status == 200 and dec(ret["retido"]) == 1200.0)
check("e o disponível desconta o que já foi liberado",
      dec(ret["disponivel"]) == 1200.0)

status, negado = req("POST", f"/api/pdca/contratos/{contrato_id}/liberar-retencao/",
                     demo, {"valor": "500", "data": date.today().isoformat(),
                            "condicao_atendida": "Aceito."})
check("`demo` não libera retenção (é ato de quem ateste)", status == 403)

status, excesso = req("POST", f"/api/pdca/contratos/{contrato_id}/liberar-retencao/",
                      gerente, {"valor": "5000", "data": date.today().isoformat(),
                                "condicao_atendida": "Aceito."})
check("liberar acima do retido é recusado, dizendo as parcelas",
      status == 400 and "1200" in texto(excesso))

status, sem_condicao = req("POST", f"/api/pdca/contratos/{contrato_id}/liberar-retencao/",
                           gerente, {"valor": "1200", "data": date.today().isoformat(),
                                     "condicao_atendida": "   "})
check("liberar sem declarar a condição é recusado",
      status == 400 and "condi" in texto(sem_condicao))
check("e a recusa mostra a cláusula do próprio contrato",
      "aceitação definitiva" in texto(sem_condicao))

status, liberada = req("POST", f"/api/pdca/contratos/{contrato_id}/liberar-retencao/",
                       gerente, {"valor": "1200", "data": date.today().isoformat(),
                                 "condicao_atendida": "Serviços aceitos em vistoria."})
check("`gerente` libera a retenção", status in (200, 201))
lib = (liberada or {}).get("liberacao") or {}
status, ret2 = req("GET", f"/api/pdca/contratos/{contrato_id}/retencao/", demo)
check("o disponível zera depois da liberação", dec(ret2["disponivel"]) == 0.0)

status, todas = req("GET", f"/api/pdca/liberacoes/?contrato={contrato_id}", demo)
registrada = ((todas or {}).get("results") or [{}])[0]
check("a liberação gerou título PRÓPRIO, e não uma baixa na conta da medição",
      registrada.get("conta_pagar_ref") not in (None, conta_ref))

# ---------------------------------------------------------- 11. retificação
print("\n11. Aprovada congela — a correção é documento novo (§11.5)")
status, retificadora = req("POST", f"/api/pdca/medicoes/{medicao_id}/retificar/",
                           demo, {"motivo": "O item 1.1 mediu 250 e apurou-se 240."})
check("a retificadora é aberta com motivo", status in (200, 201))
if retificadora:
    check("ela aponta para a medição corrigida",
          retificadora.get("retifica") == medicao_id)
    check("e nasce VAZIA — o estorno completo não vem pré-marcado",
          len(retificadora.get("itens") or []) == 0)
    check("herdando o período da original",
          retificadora.get("periodo_inicio") == p_ini)

status, duplicada = req("POST", f"/api/pdca/medicoes/{medicao_id}/retificar/",
                        demo, {"motivo": "de novo"})
check("e não se retifica a mesma medição duas vezes",
      duplicada is not None and status == 400)

# ------------------------------------------------------------ 12. fronteira
print("\n12. A fronteira de tenant")
status, vizinho = req("GET", f"/api/pdca/contratos/{contrato_id}/", acme)
check("outro tenant não abre este contrato", status in (403, 404))
status, listado = req("GET", "/api/pdca/contratos/", acme)
check("nem o vê na listagem", status in (403, 404)
      or (listado or {}).get("count") == 0)

# --------------------------------------------------------------- 13. faxina
print("\n13. Faxina — o teste desfaz o que criou")
#
# **A primeira escrita desta faxina apagava só a obra, e era um defeito.** A
# exclusão da obra é a **lixeira** (lápide, não `DELETE`), então contrato,
# medição e o `ContaPagar` gerado sobreviviam — em 15/09/2026 o ambiente de
# demonstração tinha 14 obras, 12 contratos e 4 títulos de teste, e o dono
# esbarrou num deles achando que era dado seu.
#
# O que a API permite apagar daqui, apaga-se; o resto (medição aprovada, que
# **não** se exclui por desenho, e o título que ela gerou no ERP) exige o
# `manage.py limpar_residuo_e2e`, que existe por causa disto e sabe a ordem dos
# `PROTECT`. O teste diz isso em voz alta em vez de fingir que limpou.
if retificadora:
    req("DELETE", f"/api/pdca/medicoes/{retificadora['medicao_id']}/", demo)
status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
check("a obra do teste sai (vai para a lixeira, que é o desenho)",
      status in (200, 204))
print(
    "\n     Este teste deixa contrato, medição aprovada e título no ERP — a\n"
    "     medição aprovada não se apaga, e é isso que a fatia garante. Para\n"
    "     devolver o ambiente ao estado anterior:\n"
    "       docker exec sgi-erp python manage.py limpar_residuo_e2e --confirmar"
)

# ------------------------------------------------------------------ resumo
ok = sum(1 for p in passed if p)
print(f"\n{'='*62}")
print(f"PDCA.3: {ok}/{len(passed)} verificações")
print(f"{'='*62}\n")
sys.exit(0 if ok == len(passed) else 1)
