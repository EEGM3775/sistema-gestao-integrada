"""PDCA — a montagem do plano **dentro** do posto PLANO, pelo gateway (8090).

Reproduz, na ordem de um usuário real, exatamente as chamadas que a tela faz
(`frontend/src/modules/pdca/pages/PlanoPage.tsx`, `components/GradeEap.tsx`,
`components/Inspetor.tsx`, `api/montagemApi.ts`):

  1. Sessão         -> admin do demo (segundo fator), cookie + anti-CSRF; o
                       `/auth/me/` que a tela lê para `hasPermission`.
  2. A obra         -> obra própria do teste, sem plano (a tela mostra
                       "Criar o plano").
  3. Criar o plano  -> só "Início da obra": {obra, descricao, data_inicio}.
  4. "+ Etapa"      -> raiz "1" (Nova etapa, 1 dia); "+" na linha cria 1.1 e
                       1.2 dentro dela; "+ Marco" cria "2" sem duração. Os
                       códigos vêm do mesmo `proximoCodigo` da tela.
  5. A grade        -> duplo clique renomeia ({nome}) e muda a duração
                       ({duracao_dias}), um PATCH por célula.
  6. O inspetor     -> "+ Começa depois de…" (1.1 → 1.2, FS+0); seletor
                       "Etapa da obra" → "+ Nova etapa…" cria a EtapaObra e
                       grava {etapa} na atividade; nome repetido diz por quê.
  7. Calcular       -> o CPM roda sobre o plano montado na tela.
  8. Publicar       -> vira vigente e para de aceitar edição.
  9. Replanejar     -> pede motivo, abre a v2 — e a tela tem de abrir NELA.
 10. Na v2          -> mais uma atividade (raiz e dentro de uma folha com
                       seta), calcular, e excluir uma que tem filhas.
 11. Faxina         -> rascunhos saem, a obra vai para a lixeira.

Rodar (stack de pé):  python testes/e2e/pdca_plano_montagem_test.py
`SGI_VERBOSO=1` imprime status e corpo de cada chamada.
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date

from _segundo_fator import entrar
from _sessao import cabecalhos

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")
VERBOSO = os.environ.get("SGI_VERBOSO") == "1"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

MARCA = "E2E Montagem " + uuid.uuid4().hex[:8]

passed = []
log = []


def check(label, cond, detalhe=None):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")
    if not cond and detalhe is not None:
        print(f"        -> {json.dumps(detalhe, ensure_ascii=False)[:600]}")


def fatal(msg):
    print(f"\n  !! {msg}")
    print(f"     Parcial: {sum(1 for p in passed if p)}/{len(passed)}")
    faxina()
    sys.exit(2)


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", **cabecalhos(SESSAO)}
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=120, context=_CTX) as resp:
            corpo = resp.read().decode()
            status, saida = resp.status, (json.loads(corpo) if corpo else None)
    except urllib.error.HTTPError as e:
        bruto = e.read().decode()
        try:
            status, saida = e.code, json.loads(bruto or "null")
        except Exception:
            status, saida = e.code, bruto[:400]
    log.append((method, path, status, saida))
    if VERBOSO:
        print(f"     {method} {path} {json.dumps(body, ensure_ascii=False) if body else ''}"
              f"\n       -> {status} {json.dumps(saida, ensure_ascii=False)[:400]}")
    return status, saida


def texto(resposta) -> str:
    return json.dumps(resposta, ensure_ascii=False).lower() if resposta is not None else ""


def lista(corpo):
    if isinstance(corpo, list):
        return corpo
    return (corpo or {}).get("results", [])


def proximo_codigo(atividades, pai):
    """O mesmo `proximoCodigo` de `montagemApi.ts`."""
    pai_id = pai["atividade_id"] if pai else None
    irmas = [a for a in atividades if a.get("pai") == pai_id]
    maior = 0
    for a in irmas:
        try:
            maior = max(maior, int(a["codigo"].split(".")[-1]))
        except ValueError:
            pass
    n = max(maior, len(irmas)) + 1
    return f"{pai['codigo']}.{n}" if pai else str(n)


def plano_corrente(obra_id):
    """O mesmo `usePlanoCorrente` de `hooks.ts`: vigente ?? rascunho de maior versão."""
    _, corpo = req("GET", f"/api/pdca/cronogramas/?obra={obra_id}")
    planos = lista(corpo)
    vigente = next((c for c in planos if c["status"] == "vigente"), None)
    rascunhos = sorted((c for c in planos if c["status"] == "rascunho"),
                       key=lambda c: -c["versao"])
    return vigente or (rascunhos[0] if rascunhos else None), planos


def gantt(cronograma_id):
    status, corpo = req("GET", f"/api/pdca/cronogramas/{cronograma_id}/gantt/")
    return corpo if status == 200 else {"atividades": [], "precedencias": []}


def criar_atividade(cronograma_id, atividades, pai, marco=False):
    """O `criar(pai, marco)` da PlanoPage, campo a campo."""
    corpo = {
        "cronograma": cronograma_id,
        "pai": pai["atividade_id"] if pai else None,
        "codigo": proximo_codigo(atividades, pai),
        "nome": "Novo marco" if marco else ("Nova atividade" if pai else "Nova etapa"),
        "eh_marco": marco,
    }
    if not marco:
        corpo["duracao_dias"] = 1
    return req("POST", "/api/pdca/atividades/", corpo)


OBRA_ID = None
RASCUNHOS = []


def faxina():
    if SESSAO is None or OBRA_ID is None:
        return
    for cid in RASCUNHOS:
        req("DELETE", f"/api/pdca/cronogramas/{cid}/")
    req("DELETE", f"/api/obras/{OBRA_ID}/?motivo=Faxina+do+E2E+montagem+do+plano")


print(f"\n{'='*62}\nPDCA — montagem do plano no posto PLANO, pelo gateway\n{'='*62}")
print(f"Gateway: {GW}   Marca: {MARCA}")

# ------------------------------------------------------------------ 1. sessão
print("\n1. Sessão do admin e as permissões que a tela consulta")
SESSAO = None
try:
    SESSAO = entrar(GW, "admin", "admin123", _CTX)
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé?")
if not SESSAO:
    fatal("o admin não entrou (senha recusada ou segundo fator)")
check("admin do demo entra com cookie de sessão", True)

# Sobras de uma execução interrompida: SGI_LIMPAR_OBRAS=222,223
for _sobra in filter(None, os.environ.get("SGI_LIMPAR_OBRAS", "").split(",")):
    _, _cs = req("GET", f"/api/pdca/cronogramas/?obra={_sobra}")
    for _c in lista(_cs):
        if _c["status"] == "rascunho":
            req("DELETE", f"/api/pdca/cronogramas/{_c['cronograma_id']}/")
    _st, _ = req("DELETE", f"/api/obras/{_sobra}/?motivo=Sobra+do+E2E+montagem+do+plano")
    print(f"     sobra obra {_sobra}: DELETE {_st}")

status, me = req("GET", "/auth/me/")
check("`/auth/me/` responde", status == 200, me)
perms = set((me or {}).get("permissions") or [])
admin_tenant = bool(((me or {}).get("user") or me or {}).get("is_tenant_admin"))
for codigo in ("pdca.cronograma.edit", "pdca.cronograma.publicar", "pdca.cronograma.replanejar"):
    # A tela libera se a permissão está na lista OU se é admin do tenant
    # (`AuthContext.hasPermission`).
    print(f"     {codigo}: {'na lista' if codigo in perms else 'FORA da lista'}"
          f"{' (admin do tenant libera)' if admin_tenant else ''}")
    check(f"a tela libera `{codigo}` para o admin", codigo in perms or admin_tenant,
          {"permissions": sorted(p for p in perms if p.startswith("pdca."))})

# ------------------------------------------------------------------- 2. a obra
print("\n2. Uma obra sem plano")
status, obra = req("POST", "/api/obras/", {
    "nome_obra": MARCA, "endereco": "Rua de teste, s/n", "status_obra": "planejamento",
})
if status not in (200, 201) or not obra:
    fatal(f"não consegui criar a obra (HTTP {status}: {obra})")
OBRA_ID = obra["obra_id"]
plano, _ = plano_corrente(OBRA_ID)
check("a obra nasce sem plano — a tela oferece \"Criar o plano\"", plano is None)

# ---------------------------------------------------------- 3. criar o plano
print("\n3. \"Criar o plano\" — a única pergunta é o início")
hoje = date.today().isoformat()
status, criado = req("POST", "/api/pdca/cronogramas/", {
    "obra": OBRA_ID, "descricao": "Plano da obra", "data_inicio": hoje,
})
check("o plano nasce com só {obra, descricao, data_inicio}", status == 201, criado)
if status != 201:
    fatal("sem plano não há montagem")
v1 = criado["cronograma_id"]
RASCUNHOS.append(v1)
check("rascunho v1, editável", criado["status"] == "rascunho" and criado["versao"] == 1
      and criado["editavel"] is True, criado)
plano, _ = plano_corrente(OBRA_ID)
check("a tela passa a mostrar esse plano", plano and plano["cronograma_id"] == v1)

# ------------------------------------------------------------- 4. a estrutura
print("\n4. \"+ Etapa\", \"+\" na linha e \"+ Marco\"")
ativs = gantt(v1)["atividades"]
status, raiz = criar_atividade(v1, ativs, None)
check("\"+ Etapa\" cria a raiz 1", status == 201 and raiz["codigo"] == "1", raiz)
if status != 201:
    fatal("a raiz não nasceu")

ativs = gantt(v1)["atividades"]
status, f1 = criar_atividade(v1, ativs, raiz)
check("\"+\" na linha cria 1.1 dentro dela", status == 201 and f1["codigo"] == "1.1", f1)
ativs = gantt(v1)["atividades"]
status, f2 = criar_atividade(v1, ativs, raiz)
check("e de novo cria 1.2", status == 201 and f2["codigo"] == "1.2", f2)
if not (f1 and f2 and "atividade_id" in f1 and "atividade_id" in f2):
    fatal("as filhas não nasceram")

ativs = gantt(v1)["atividades"]
status, marco = criar_atividade(v1, ativs, None, marco=True)
check("\"+ Marco\" cria o 2 sem duração", status == 201 and marco["codigo"] == "2"
      and marco["eh_marco"] is True, marco)

g = gantt(v1)
por_id = {a["atividade_id"]: a for a in g["atividades"]}
check("o Gantt traz as quatro linhas", len(g["atividades"]) == 4, g["atividades"])
check("a raiz virou sintética", por_id.get(raiz["atividade_id"], {}).get("tem_filhos") is True)

# ---------------------------------------------------------------- 5. a grade
print("\n5. Duplo clique na grade: renomear e mudar a duração")
status, renomeada = req("PATCH", f"/api/pdca/atividades/{f1['atividade_id']}/",
                        {"nome": "Escavação"})
check("renomear 1.1", status == 200 and renomeada["nome"] == "Escavação", renomeada)
status, durada = req("PATCH", f"/api/pdca/atividades/{f1['atividade_id']}/",
                     {"duracao_dias": 3})
check("mudar a duração de 1.1 para 3", status == 200 and durada["duracao_dias"] == 3, durada)
status, raiz_renomeada = req("PATCH", f"/api/pdca/atividades/{raiz['atividade_id']}/",
                             {"nome": "Fundação"})
check("renomear a sintética também", status == 200, raiz_renomeada)
status, _ = req("PATCH", f"/api/pdca/atividades/{f2['atividade_id']}/", {"duracao_dias": 0})
check("duração 0 na grade é recusada (400)", status == 400)

# ------------------------------------------------------------- 6. o inspetor
print("\n6. Inspetor: \"+ Começa depois de…\" e \"Etapa da obra\"")
status, seta = req("POST", "/api/pdca/precedencias/", {
    "tipo": "FS", "atraso_dias": 0,
    "origem": f1["atividade_id"], "destino": f2["atividade_id"],
})
check("1.2 começa depois de 1.1 (FS+0)", status == 201, seta)
status, seta_dup = req("POST", "/api/pdca/precedencias/", {
    "tipo": "FS", "atraso_dias": 0,
    "origem": f1["atividade_id"], "destino": f2["atividade_id"],
})
check("a mesma seta de novo é recusada com 400 (não 500)", status == 400, seta_dup)
print(f"     mensagem: {texto(seta_dup)[:200]}")

status, etapas = req("GET", f"/api/etapas-obras/?obra={OBRA_ID}&page_size=200")
check("lista as etapas da obra (vazia)", status == 200 and lista(etapas) == [], etapas)
ordem = max((e["ordem"] for e in lista(etapas)), default=0) + 1
status, etapa = req("POST", "/api/etapas-obras/", {
    "obra": OBRA_ID, "nome_etapa": "Infraestrutura", "ordem": ordem,
})
check("\"+ Nova etapa…\" cria a etapa da obra", status == 201, etapa)
etapa_id = (etapa or {}).get("etapa_id")
status, com_etapa = req("PATCH", f"/api/pdca/atividades/{f1['atividade_id']}/",
                        {"etapa": etapa_id})
check("e a atividade passa a apontar para ela", status == 200
      and com_etapa.get("etapa") == etapa_id and com_etapa.get("etapa_nome") == "Infraestrutura",
      com_etapa)

status, repetida = req("POST", "/api/etapas-obras/", {
    "obra": OBRA_ID, "nome_etapa": "Infraestrutura", "ordem": ordem + 1,
})
check("nome de etapa repetido na mesma obra é recusado com 400", status == 400, repetida)
print(f"     mensagem: {texto(repetida)[:300]}")
msg = texto(repetida)
# A tela mostra este texto cru no inspetor (`parseApiErrors` → `_form`).
check("e a mensagem fala a língua do usuário (sem 'set único' nem nome de coluna)",
      status == 400 and "set único" not in msg and "nome_etapa" not in msg, repetida)

# ------------------------------------------------------------------ 7. calcular
print("\n7. Calcular")
status, cals = req("GET", f"/api/pdca/calendarios/?para_obra={OBRA_ID}")
calendarios = lista(cals)
print(f"     expedientes que servem à obra: "
      f"{[(c['calendario_id'], c['nome'], c.get('padrao'), c.get('obra')) for c in calendarios]}")
status, cpm = req("POST", f"/api/pdca/cronogramas/{v1}/calcular/")
# A tela não pergunta o expediente ao criar o plano, e não há onde escolhê-lo
# depois (o painel "Expediente" só lista). Se o servidor não herdar o da obra
# ou o padrão da empresa, o plano montado na tela nunca calcula nem publica.
check("o CPM roda sobre o plano montado na tela (sem calendário escolhido)",
      status == 200, cpm)
if status == 400 and "calend" in texto(cpm):
    # FORA DA TELA: o roteiro dá ao plano o expediente que a tela não dá, só
    # para seguir sondando publicar/replanejar.
    if calendarios:
        cal_id = calendarios[0]["calendario_id"]
    else:
        _, cal = req("POST", "/api/pdca/calendarios/", {
            "obra": OBRA_ID, "nome": "Expediente " + MARCA,
        })
        cal_id = (cal or {}).get("calendario_id")
    status, com_cal = req("PATCH", f"/api/pdca/cronogramas/{v1}/", {"calendario": cal_id})
    print(f"     (fora da tela) PATCH calendario={cal_id}: {status}")
    status, cpm = req("POST", f"/api/pdca/cronogramas/{v1}/calcular/")
    print(f"     (fora da tela) calcular de novo: {status}")
g = gantt(v1)
por_codigo = {a["codigo"]: a for a in g["atividades"]}
check("1.1 começa no início do plano",
      por_codigo.get("1.1", {}).get("inicio_cedo") is not None, por_codigo.get("1.1"))
check("1.2 começa depois de 1.1 terminar",
      (por_codigo.get("1.2", {}).get("inicio_cedo") or "")
      > (por_codigo.get("1.1", {}).get("termino_cedo") or "~"),
      {k: (v.get("inicio_cedo"), v.get("termino_cedo")) for k, v in por_codigo.items()})

# ------------------------------------------------------------------ 8. publicar
print("\n8. Publicar")
status, pub = req("POST", f"/api/pdca/cronogramas/{v1}/publicar/")
check("publica", status == 200, pub)
check("e vira vigente", isinstance(pub, dict)
      and (pub.get("cronograma") or {}).get("status") == "vigente", pub)
if status == 200:
    RASCUNHOS.remove(v1)
else:
    fatal("sem plano vigente não há replanejar")
plano, _ = plano_corrente(OBRA_ID)
check("a tela mostra o vigente, não editável",
      plano and plano["cronograma_id"] == v1 and plano["editavel"] is False, plano)
status, barrado = req("POST", "/api/pdca/atividades/", {
    "cronograma": v1, "pai": None, "codigo": "3", "nome": "Nova etapa",
    "eh_marco": False, "duracao_dias": 1,
})
check("\"+ Etapa\" no vigente é recusado (400)", status == 400, barrado)

# ---------------------------------------------------------------- 9. replanejar
print("\n9. Replanejar")
status, v2 = req("POST", f"/api/pdca/cronogramas/{v1}/replanejar/",
                 {"motivo": "Sondagem pediu estaca mais funda"})
check("replanejar com motivo abre a v2", status in (200, 201) and isinstance(v2, dict)
      and v2.get("versao") == 2, v2)
if status not in (200, 201):
    fatal("sem v2 não há o resto")
v2_id = v2["cronograma_id"]
RASCUNHOS.append(v2_id)

plano, planos = plano_corrente(OBRA_ID)
# É o que a PlanoPage faz depois do replanejar: invalida a lista e volta a
# escolher `vigente ?? rascunho`. Com a v1 ainda vigente (ela só é substituída
# quando a v2 for publicada), a escolha cai de novo na v1 — e a v2, que o
# usuário acabou de criar para editar, não aparece na tela.
check("depois do replanejar a tela abre a v2 editável (usePlanoCorrente)",
      plano and plano["cronograma_id"] == v2_id,
      {"escolhido": plano and (plano["versao"], plano["status"]),
       "planos": [(c["versao"], c["status"]) for c in planos]})

status, v3 = req("POST", f"/api/pdca/cronogramas/{v1}/replanejar/",
                 {"motivo": "Cliquei Replanejar de novo porque a v2 não apareceu"})
check("um segundo replanejar com a v2 ainda em rascunho é recusado",
      status == 400, {"status": status, "versao": (v3 or {}).get("versao")})
if status in (200, 201) and isinstance(v3, dict) and v3.get("cronograma_id"):
    RASCUNHOS.append(v3["cronograma_id"])

# ----------------------------------------------------------- 10. editar a v2
print("\n10. Na v2: criar, calcular e excluir")
ativs = gantt(v2_id)["atividades"]
check("a árvore veio inteira para a v2", len(ativs) == 4, [a["codigo"] for a in ativs])
status, nova_raiz = criar_atividade(v2_id, ativs, None)
check("\"+ Etapa\" na v2 cria a raiz 3", status == 201 and nova_raiz["codigo"] == "3", nova_raiz)

ativs = gantt(v2_id)["atividades"]
f1_v2 = next((a for a in ativs if a["codigo"] == "1.1"), None)
status, neta = criar_atividade(v2_id, ativs, f1_v2)
# 1.1 tem a seta 1.1 → 1.2. O "+" da linha continua oferecido (só o marco não
# tem "+"), e a seta passaria a sair de uma sintética — que o CPM não aceita.
print(f"     \"+\" em 1.1 (folha com seta): {status} {texto(neta)[:300]}")
status_calc, calc_v2 = req("POST", f"/api/pdca/cronogramas/{v2_id}/calcular/")
check("depois do \"+\" numa folha com seta o plano continua calculável "
      "(ou o \"+\" é recusado com motivo)",
      status_calc == 200 or status == 400,
      {"criar_filha": status, "calcular": status_calc, "corpo": calc_v2})

ativs = gantt(v2_id)["atividades"]
raiz_v2 = next((a for a in ativs if a["codigo"] == "1"), None)
dentro = [a for a in ativs if a["codigo"].startswith("1.")]
status, _ = req("DELETE", f"/api/pdca/atividades/{raiz_v2['atividade_id']}/")
check(f"excluir a etapa 1 com {len(dentro)} atividades dentro", status == 204)
restantes = sorted(a["codigo"] for a in gantt(v2_id)["atividades"])
check("as de dentro saem junto (e a seta com elas)",
      not any(c == "1" or c.startswith("1.") for c in restantes), restantes)
status, calc_final = req("POST", f"/api/pdca/cronogramas/{v2_id}/calcular/")
check("o que sobrou calcula", status == 200, calc_final)

ativs = gantt(v2_id)["atividades"]
status, depois_exclusao = criar_atividade(v2_id, ativs, None)
check("\"+ Etapa\" depois de excluir não colide com código existente",
      status == 201, depois_exclusao)
if status == 201:
    print(f"     código escolhido: {depois_exclusao['codigo']}")

# ------------------------------------------------------------------- 11. faxina
print("\n11. Faxina")
for cid in list(RASCUNHOS):
    status, _ = req("DELETE", f"/api/pdca/cronogramas/{cid}/")
    check(f"rascunho {cid} sai", status in (200, 204))
    RASCUNHOS.remove(cid)
if etapa_id:
    status, _ = req("DELETE", f"/api/etapas-obras/{etapa_id}/?motivo=Faxina+do+E2E")
    check("a etapa do teste sai", status in (200, 204))
status, _ = req("DELETE", f"/api/obras/{OBRA_ID}/?motivo=Faxina+do+E2E+montagem+do+plano")
check("a obra vai para a lixeira (o vigente fica com ela)", status in (200, 204))
OBRA_ID = None

erros = [(m, p, s, c) for (m, p, s, c) in log if s >= 500]
check("nenhuma chamada devolveu 5xx", not erros, erros[:3])

ok = sum(1 for p in passed if p)
print(f"\n{'='*62}\nPDCA montagem do plano: {ok}/{len(passed)} checks")
sys.exit(0 if ok == len(passed) else 1)
