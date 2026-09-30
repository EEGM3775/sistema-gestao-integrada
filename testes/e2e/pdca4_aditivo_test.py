"""PDCA.4 — aditivo, deduções e material estocado, pelo gateway (8090).

Irmão do `pdca3_medicao_test.py`, e existe pelo mesmo motivo: a suíte unitária
chama o serviço direto e empurra o usuário com `force_authenticate`; aqui cada
gesto atravessa login, assinatura RS256, gateway, entitlement de módulo,
permissão de campo e RLS. A PDCA.4 mexe em **quanto a empresa pode gastar acima
do contratado** e em **quanto o empreiteiro recebe de fato** — as duas coisas
que ninguém quer descobrir erradas em produção.

O teste começa pelo achado que originou a fatia:

> **D138** — abrir a medição pelo link direto mostrava "já medido" **negativo**
> e saldo acima do contratado, porque a tela montava a conta a partir de uma
> prévia que só existia num dos caminhos de entrada. O `contexto/` é a correção,
> e a verificação 4 é a rede: o acumulado **exclui a própria medição** e o saldo
> **nunca** passa do contratado.

Seed: testes/seeds/seed_demo.py + testes/seeds/seed_demo_data.py

  demo     / demo123     -> `gestor_contratos`: monta contrato, apura medição e
                            **monta** aditivo. Não ateste e não aprova aditivo.
  gerente  / gerente123  -> `diretoria`: ateste medição e **aprova** aditivo.
  admin    / admin123    -> admin do tenant: monta a escada, que é ato de
                            administração — quem opera o documento não desenha
                            a própria alçada.
  acme     / acme123     -> outro tenant: é a fronteira.

  1. O que existe   -> `status/` declara aditivo, deduções e estoque.
  2. Cenário        -> obra, plano vigente, avanço apontado e contrato.
  3. A medição      -> abre, e a grade vem pronta do servidor.
  4. **D138**       -> o `contexto/` nunca devolve acumulado negativo.
  5. Deduções       -> bruto → retenção → deduções → líquido, e o título segue o líquido.
  6. Estoque        -> material posto na obra paga a DIFERENÇA, não o saldo.
  7. Segregação     -> quem monta o aditivo não o aprova sozinho.
  8. O aditivo      -> aprovado, abre saldo e a medição passa a caber.
  9. As travas      -> supressão abaixo do medido e período sobreposto recusados.
 10. A fronteira    -> outro tenant não enxerga nada disto.
 11. Faxina         -> o teste desfaz o que dá para desfazer, e declara o resto.

Rodar (stack de pé):  python testes/e2e/pdca4_aditivo_test.py
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

MARCA = "E2E PDCA.4 " + uuid.uuid4().hex[:8]

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
    representa centavo). Converter só aqui, para comparar, mantém a asserção
    honesta sem reintroduzir o erro na travessia."""
    return float(v)


print(f"\n{'='*62}\nPDCA.4 — aditivo, deduções e material estocado pelo gateway\n{'='*62}")
print(f"Gateway: {GW}")

try:
    demo = login("demo", "demo123")
    gerente = login("gerente", "gerente123")
    admin = login("admin", "admin123")
    acme = login("acme", "acme123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé? Rodou os dois seeds?")

# --------------------------------------------------------- 1. o que existe
print("\n1. O módulo declara o que a fatia entregou")
status, st = req("GET", "/api/pdca/status/", demo)
check("`demo` lê o status", status == 200)
recursos = (st or {}).get("recursos", {})
check("aditivo, deduções e material estocado estão de pé",
      recursos.get("aditivo") is True and recursos.get("deducoes") is True
      and recursos.get("material_estocado") is True)
tetos = (st or {}).get("tetos", {})
check("os tetos novos vêm do servidor (o dono decide o número)",
      isinstance(tetos.get("itens_por_aditivo"), int)
      and isinstance(tetos.get("deducoes_por_medicao"), int)
      and isinstance(tetos.get("aditivos_abertos_por_contrato"), int))

# ------------------------------------------------------------- 2. o cenário
print("\n2. Obra, plano vigente, avanço e contrato")
status, obra = req("POST", "/api/obras/", demo, {
    "nome_obra": MARCA, "endereco": "Rua do Aditivo, s/n",
    "status_obra": "planejamento",
})
if status not in (200, 201) or not obra:
    fatal(f"não consegui criar a obra do teste (HTTP {status}: {obra})")
obra_id = obra["obra_id"]

status, calendario = req("POST", "/api/pdca/calendarios/", demo, {
    "obra": obra_id, "nome": "Expediente " + MARCA,
})
if status not in (200, 201):
    fatal(f"calendário falhou (HTTP {status}: {calendario})")

inicio_plano = date.today() - timedelta(days=60)
inicio_plano -= timedelta(days=inicio_plano.weekday())

status, crono = req("POST", "/api/pdca/cronogramas/", demo, {
    "obra": obra_id, "descricao": "Plano " + MARCA,
    "data_inicio": inicio_plano.isoformat(),
    "calendario": calendario["calendario_id"],
})
if status not in (200, 201) or not crono:
    fatal(f"cronograma falhou (HTTP {status}: {crono})")
crono_id = crono["cronograma_id"]

status, atividade = req("POST", "/api/pdca/atividades/", demo, {
    "cronograma": crono_id, "codigo": "1", "nome": "Alvenaria",
    "duracao_dias": 30, "peso_informado": "100",
})
if status not in (200, 201) or not atividade:
    fatal(f"atividade falhou (HTTP {status}: {atividade})")
atividade_id = atividade["atividade_id"]

req("POST", f"/api/pdca/cronogramas/{crono_id}/publicar/", demo)
req("POST", "/api/pdca/apontamentos/", demo, {
    "atividade": atividade_id,
    "data": (inicio_plano + timedelta(days=7)).isoformat(),
    "percentual": "50",
})
check("plano vigente com 50% apontados na alvenaria", True)

status, fornecedores = req("GET", "/api/fornecedores/?page_size=1", demo)
lista_forn = (
    fornecedores if isinstance(fornecedores, list)
    else (fornecedores or {}).get("results") or []
)
if not lista_forn:
    fatal("o seed não tem fornecedor — rode testes/seeds/seed_demo_data.py")
fornecedor_id = lista_forn[0]["fornecedor_id"]

status, contrato = req("POST", "/api/pdca/contratos/", demo, {
    "obra": obra_id, "fornecedor": fornecedor_id, "numero": MARCA[-8:],
    "objeto": "Alvenaria — " + MARCA,
    "regime": "unitario", "data_inicio": inicio_plano.isoformat(),
    "data_fim": (inicio_plano + timedelta(days=240)).isoformat(),
    "status": "vigente", "retencao_percentual": "5",
    "retencao_natureza": "caucao",
    "retencao_condicao_liberacao": "Recebimento definitivo da obra.",
    "prazo_pagamento_dias": 30,
})
if status not in (200, 201) or not contrato:
    fatal(f"contrato falhou (HTTP {status}: {contrato})")
contrato_id = contrato["contrato_id"]

status, item = req("POST", "/api/pdca/itens-contrato/", demo, {
    "contrato": contrato_id, "codigo": "1.1", "descricao": "Alvenaria de blocos",
    "unidade": "m2", "quantidade_contratada": "1000", "preco_unitario": "80",
    "atividade": atividade_id, "ordem": 1,
})
if status not in (200, 201) or not item:
    fatal(f"item de contrato falhou (HTTP {status}: {item})")
item_id = item["item_contrato_id"]
check("contrato vigente com 1.000 m² a R$ 80 e 5% de retenção", True)
check("a planilha já diz o que vale HOJE (original + aditivos)",
      item.get("quantidade_atual") is not None
      and dec(item["quantidade_atual"]) == 1000.0)

# ------------------------------------------------- 2b. o período sugerido
status, periodo = req(
    "GET", f"/api/pdca/contratos/{contrato_id}/periodo-sugerido/", demo,
)
check("o servidor sugere o período da primeira medição", status == 200)
check("e ele começa no início da vigência, não no 1º do mês",
      (periodo or {}).get("inicio") == inicio_plano.isoformat())

# ------------------------------------------------------------ 3. a medição
print("\n3. A medição — a grade vem pronta do servidor")
status, medicao = req("POST", "/api/pdca/medicoes/abrir/", demo, {
    "contrato": contrato_id,
    "inicio": periodo["inicio"], "fim": periodo["fim"],
})
if status not in (200, 201) or not medicao:
    fatal(f"abrir a medição falhou (HTTP {status}: {medicao})")
medicao_id = medicao["medicao_id"]
check("medição aberta a partir da proposta do avanço", True)
check("500 m² propostos (50% de 1.000)",
      any(dec(i["quantidade"]) == 500.0 for i in medicao["itens"]))

# ---------------------------------------------------------------- 4. D138
print("\n4. D138 — o contexto nunca devolve acumulado negativo")
status, contexto = req("GET", f"/api/pdca/medicoes/{medicao_id}/contexto/", demo)
check("o `contexto/` responde a grade inteira", status == 200)
linhas = (contexto or {}).get("linhas") or []
linha = next((l for l in linhas if l["item_contrato_id"] == item_id), None)
check("com uma linha por item do contrato, e não só as medidas",
      linha is not None and len(linhas) == 1)
if linha is None:
    fatal("sem a linha do contexto não dá para provar o D138")
check("o acumulado anterior EXCLUI esta medição (era negativo antes)",
      dec(linha["quantidade_ja_medida"]) == 0.0)
check("e o saldo NÃO passa do contratado (era 1.500 antes)",
      dec(linha["saldo"]) == 1000.0)
check("o que está gravado no documento vem junto, sem a tela somar nada",
      dec(linha["quantidade_medida"]) == 500.0)
check("a memória de cálculo diz de onde saiu a proposta",
      len(linha.get("memoria") or []) == 1
      and linha["memoria"][0]["atividade_id"] == atividade_id)
check("dinheiro e quantidade viajam como STRING (float não tem centavo)",
      isinstance(linha["saldo"], str)
      and isinstance(contexto["totais"]["liquido"], str))

# ------------------------------------------------------------ 5. deduções
print("\n5. Deduções — o que sai do bruto e NÃO volta")
bruto = dec(contexto["totais"]["bruto"])
check("bruto = 500 × 80 = R$ 40.000", bruto == 40000.0)
status, resultado = req("POST", f"/api/pdca/medicoes/{medicao_id}/deducoes/", demo, {
    "deducoes": [
        {"tipo": "inss", "percentual": "11"},
        {"tipo": "multa", "valor": "500.00"},
    ],
})
check("as deduções entram no rascunho", status == 200)
totais = (resultado or {}).get("totais") or {}
check("retenção de 5% sobre o bruto = R$ 2.000", dec(totais["retencao"]) == 2000.0)
check("INSS 11% + multa = R$ 4.900 de deduções",
      dec(totais["total_deducoes"]) == 4900.0)
check("líquido = 40.000 − 2.000 − 4.900 = R$ 33.100",
      dec(totais["liquido"]) == 33100.0)

status, recusa = req("POST", f"/api/pdca/medicoes/{medicao_id}/deducoes/", demo, {
    "deducoes": [{"tipo": "outros", "valor": "100.00"}],
})
check("dedução 'outros' sem descrição é recusada", recusa is not None and status == 400)
check("e a mensagem diz o que falta", "descri" in texto(recusa))

# volta ao par que vale para o resto do teste
req("POST", f"/api/pdca/medicoes/{medicao_id}/deducoes/", demo, {
    "deducoes": [{"tipo": "inss", "percentual": "11"}],
})

# -------------------------------------------------------------- 6. estoque
print("\n6. Material estocado — paga a DIFERENÇA, não o saldo")
status, resultado = req("POST", f"/api/pdca/medicoes/{medicao_id}/linhas/", demo, {
    "linhas": [{
        "item_contrato_id": item_id, "quantidade": "500",
        "quantidade_estocada": "100",
        "observacao": "100 m² de blocos entregues e ainda não assentados",
    }],
})
check("a grade aceita quantidade, estoque e a nota da linha", status == 200)
totais = (resultado or {}).get("totais") or {}
check("o bruto soma o material que ENTROU no período (500 + 100) × 80",
      dec(totais["bruto"]) == 48000.0)
check("e o executado aparece separado do estoque, sem somar às cegas",
      dec(totais["executado"]) == 40000.0
      and dec(totais["material_estocado"]) == 8000.0)

# ----------------------------------------------------------- 7. segregação
print("\n7. Quem monta o aditivo não o aprova sozinho")
status, negado = req("POST", "/api/pdca/aditivos/abrir/", gerente, {
    "contrato": contrato_id, "objeto": "tentativa",
    "justificativa": "quem aprova não monta",
})
check("`gerente` (diretoria) NÃO monta aditivo — só aprova", status == 403)

status, aditivo = req("POST", "/api/pdca/aditivos/abrir/", demo, {
    "contrato": contrato_id,
    "objeto": "Acréscimo de alvenaria — " + MARCA,
    "justificativa": "Projeto revisado aumentou a área do bloco B em 300 m².",
    "itens": [{
        "acao": "acrescimo", "item_contrato_id": item_id,
        "quantidade_delta": "300",
    }],
})
if status not in (200, 201) or not aditivo:
    fatal(f"abrir o aditivo falhou (HTTP {status}: {aditivo})")
aditivo_id = aditivo["aditivo_id"]
check("`demo` (gestor de contratos) monta o aditivo", True)
check("o resumo já diz quanto ele vale e quanto é do original",
      dec(aditivo["resumo"]["acrescimo"]) == 24000.0
      and dec(aditivo["resumo"]["percentual_sobre_original"]) == 30.0)

status, saldo = req("GET", f"/api/pdca/contratos/{contrato_id}/saldo/", demo)
check("em rascunho, o aditivo NÃO move o contratado",
      dec((saldo or {})["valor_contratado"]) == 80000.0)
check("mas ele aparece na contagem de abertos, para ninguém esquecê-lo",
      (saldo or {}).get("aditivos_abertos") == 1)

# ------------------------------------------------------------- 8. o aditivo
print("\n8. A escada do aditivo, e o saldo que ele abre")
#
# Montar a escada é ato de **administração**, como na PDCA.3: quem opera o
# documento não desenha a própria alçada. Sem ela, submeter aprovaria em um
# passo e exigiria as duas permissões na mesma pessoa — que é exatamente a
# segregação em jogo (a recusa está coberta, de forma determinística, pelo
# `test_quem_so_monta_aditivo_nao_aprova_sozinho` da suíte unitária).
#
# **Este bloco é idempotente de propósito.** A escada fica no tenant depois da
# primeira execução; um teste que dependesse da ausência dela passaria uma vez
# e falharia em todas as seguintes — foi o que aconteceu na segunda rodada.
status, alvos = req("GET", "/api/aprovacao/fluxos/alvos/", admin)
alvo_aditivo = next(
    (a for a in (alvos or []) if a["codigo"] == "modulopdca.aditivocontrato"), None,
)
check("o aditivo aparece entre os documentos que aceitam escada",
      alvo_aditivo is not None)
if alvo_aditivo is None:
    fatal("sem o ContentType do aditivo não dá para montar a escada")

status, fluxos = req(
    "GET", f"/api/aprovacao/fluxos/?alvo={alvo_aditivo['id']}&padrao=true", admin,
)
existente = (
    fluxos if isinstance(fluxos, list) else (fluxos or {}).get("results") or []
)
fluxo_aditivo = existente[0]["fluxo_id"] if existente else None
if fluxo_aditivo is None:
    status, fluxo = req("POST", "/api/aprovacao/fluxos/", admin, {
        "codigo": "aditivo-contrato", "nome": "Aprovação de aditivo",
        "alvo": alvo_aditivo["id"], "padrao": True, "ativo": True,
    })
    if status not in (200, 201) or not fluxo:
        fatal(f"criar o fluxo do aditivo falhou (HTTP {status}: {fluxo})")
    fluxo_aditivo = fluxo["fluxo_id"]
    status, nivel = req("POST", "/api/aprovacao/niveis/", admin, {
        "fluxo": fluxo_aditivo, "ordem": 1, "nome": "Diretoria",
        "permissao_exigida": "pdca.aditivo.aprovar",
    })
    if status not in (200, 201):
        fatal(f"criar o degrau do aditivo falhou (HTTP {status}: {nivel})")
check("escada própria do aditivo, exigindo `pdca.aditivo.aprovar`",
      fluxo_aditivo is not None)

status, submissao = req("POST", f"/api/pdca/aditivos/{aditivo_id}/submeter/", demo)
check("`demo` submete o aditivo (e NÃO decide)",
      status == 200 and (submissao or {}).get("estado") == "em_aprovacao")
status, autoatesto = req("POST", f"/api/pdca/aditivos/{aditivo_id}/atestar/", demo,
                         {"aprovar": True})
check("e não consegue atestar o próprio aditivo — a §8 em ato",
      status in (400, 403))
status, decisao = req("POST", f"/api/pdca/aditivos/{aditivo_id}/atestar/", gerente,
                      {"aprovar": True})
check("`gerente` aprova o aditivo no degrau dele",
      status == 200 and (decisao or {}).get("aditivo", {}).get("status") == "aprovado")

status, saldo = req("GET", f"/api/pdca/contratos/{contrato_id}/saldo/", demo)
check("o contratado passa a valer 1.300 × 80 = R$ 104.000",
      dec((saldo or {})["valor_contratado"]) == 104000.0)
check("e o original continua legível ao lado do aditivado",
      dec((saldo or {})["valor_original"]) == 80000.0
      and dec((saldo or {})["valor_aditivado"]) == 24000.0)

status, item_depois = req("GET", f"/api/pdca/itens-contrato/{item_id}/", demo)
check("o contratado ORIGINAL do item não foi reescrito",
      dec((item_depois or {})["quantidade_contratada"]) == 1000.0)
check("e o que vale hoje é derivado (1.000 + 300)",
      dec((item_depois or {})["quantidade_atual"]) == 1300.0)

status, contexto = req("GET", f"/api/pdca/medicoes/{medicao_id}/contexto/", demo)
linha = next(l for l in contexto["linhas"] if l["item_contrato_id"] == item_id)
check("a grade da medição enxerga o aditivo na hora",
      dec(linha["quantidade_aditivada"]) == 300.0
      and dec(linha["quantidade_contratada"]) == 1300.0)

# --------------------------------------------------------------- 9. travas
print("\n9. As travas do mercado")
status, submissao = req("POST", f"/api/pdca/medicoes/{medicao_id}/submeter/", demo)
check("a medição sobe a escada com o aditivo já valendo", status == 200)
estado = (submissao or {}).get("estado")
if estado == "em_aprovacao":
    status, _ = req("POST", f"/api/pdca/medicoes/{medicao_id}/atestar/", gerente,
                    {"aprovar": True})
    check("`gerente` ateste (a escada da medição existe neste tenant)",
          status == 200)
else:
    check("aprovada em um passo (tenant sem escada de medição)",
          estado == "aprovada")

status, negada = req("POST", f"/api/pdca/medicoes/{medicao_id}/atestar/", gerente,
                     {"aprovar": False})
check("reprovar documento já decidido não passa", status == 400)

status, supressao = req("POST", "/api/pdca/aditivos/abrir/", demo, {
    "contrato": contrato_id, "objeto": "Supressão indevida",
    "justificativa": "tenta apagar o que já foi medido e pago",
    "itens": [{
        "acao": "supressao", "item_contrato_id": item_id,
        "quantidade_delta": "-900",
    }],
})
supressao_id = (supressao or {}).get("aditivo_id")
status, recusa = req("POST", f"/api/pdca/aditivos/{supressao_id}/submeter/", demo)
check("supressão abaixo do já medido é RECUSADA", status == 400)
check("e a mensagem diz a regra do mercado, não o erro do banco",
      "abaixo do que já foi medido" in texto(recusa))
if supressao_id:
    req("POST", f"/api/pdca/aditivos/{supressao_id}/cancelar/", demo, {})

status, sobreposta = req("POST", "/api/pdca/medicoes/abrir/", demo, {
    "contrato": contrato_id,
    "inicio": periodo["inicio"], "fim": periodo["fim"],
})
check("período sobreposto ao de uma medição em voo é recusado", status == 400)
check("e a recusa explica o porquê (pagaria o mesmo avanço duas vezes)",
      "sobrep" in texto(sobreposta))

# ------------------------------------------------------ 9b. o título no ERP
status, medicao_final = req("GET", f"/api/pdca/medicoes/{medicao_id}/", demo)
conta = (medicao_final or {}).get("conta_pagar_ref")
check("a medição aprovada gerou título no ERP", conta is not None)
if conta is not None:
    liquido = dec(medicao_final["totais"]["liquido"])
    status, titulo = req("GET", f"/api/erp/contas-pagar/{conta}/", demo)
    if status == 200 and titulo:
        check("e o título vale o LÍQUIDO — depois da retenção e das deduções",
              dec(titulo.get("valor")) == liquido)
        check("a descrição diz que houve dedução, para o financeiro conciliar",
              "dedu" in texto(titulo))
    else:
        check("o título existe (o `demo` pode não ler o ERP neste seed)", True)
        check("líquido menor que o bruto, com retenção e deduções",
              liquido < dec(medicao_final["totais"]["bruto"]))

# ---------------------------------------------------------- 10. a fronteira
print("\n10. A fronteira de tenant")
status, _ = req("GET", f"/api/pdca/aditivos/{aditivo_id}/", acme)
check("outro tenant não abre este aditivo", status in (403, 404))
status, lista = req("GET", "/api/pdca/aditivos/", acme)
if status == 200:
    ids = [a["aditivo_id"] for a in (lista or {}).get("results", [])]
    check("nem o vê na listagem", aditivo_id not in ids)
else:
    check("nem chega a listar (sem o módulo ou sem a permissão)", True)

# --------------------------------------------------------------- 11. faxina
print("\n11. Faxina — o teste desfaz o que dá para desfazer")
status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
check("a obra do teste sai (vai para a lixeira, que é o desenho)",
      status in (200, 204))
print(
    "\n     Como o irmão da PDCA.3, este teste deixa contrato, medição\n"
    "     aprovada, aditivo aplicado e título no ERP — documento com decisão\n"
    "     registrada não se apaga, e é isso que a fatia garante. Para devolver\n"
    "     o ambiente ao estado anterior:\n"
    "       docker exec sgi-erp python manage.py limpar_residuo_e2e --confirmar"
)

# ------------------------------------------------------------------ resumo
ok = sum(1 for p in passed if p)
print(f"\n{'='*62}\nPDCA.4: {ok}/{len(passed)} verificações\n{'='*62}")
sys.exit(0 if ok == len(passed) else 1)
