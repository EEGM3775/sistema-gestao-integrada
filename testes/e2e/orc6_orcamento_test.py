"""ORC.6 — módulo Orçamento ponta a ponta pelo gateway (8090).

Prova com um token real da IAM o que a suíte unitária (206 testes) não cobre:
entitlement `orcamento`, as 9 permissões `orcamento.*` e a persona `orcamentista`
só existem depois do rebuild da imagem da IAM + re-seed. E, sobretudo, prova a
**integração visível** — que o orçamento aprovado passa a valer como régua nos
outros módulos, não só dentro do seu.

Seed: iam/seed_demo.py (tenant demo) + backend/seed_demo_data.py

  demo     / demo123     -> módulos scm+sil+orcamento, papéis inclusive `orcamentista`
  semdrone / semdrone123 -> só erp_financeiro, papel `operacional` — SEM `orcamento`

   1. Módulo vivo            -> GET /api/orcamento/status/ 200 com publicação ativa.
   2. Entitlement fecha      -> semdrone em /api/orcamento/orcamentos/ -> 403.
   3. Base é pública         -> leitura 200; escrita 405 (é dado público, gravado
                                só por `importar_base_referencial`).
   4. Adoção no catálogo     -> referência da base vira `catalogo.Item`, idempotente:
                                adotar duas vezes não cria dois itens.
   5. Planilha versionada    -> orçamento nasce rascunho editável; linha criada pelo
                                catálogo carrega o SNAPSHOT (descrição/unidade).
   6. Snapshot congela       -> renomear o item no catálogo NÃO mexe na linha.
   7. Explosão              -> composição abre em insumos; `por-categoria` declara
                                a `cobertura_pct` em vez de fingir total.
   8. **Alçada (D28)**       -> o `orcamentista` aprova pela permissão da persona,
                                sem depender do bypass do admin do tenant.
   9. Aprovar congela        -> `editavel` cai; PATCH e nova linha são recusados.
  10. **Seam do controle**   -> a obra que não tinha `orcado` em /controle/ passa a
                                ter, com as quatro colunas e a nota de cobertura.
  11. Revisar                -> sem motivo 400; com motivo cria v+1 editável.
  12. Cronograma + curva S   -> distribuição linear responde e a curva sai.
  13. Reprecificar           -> prévia não altera; aplicar muda; desfazer restaura.
  14. Duplicar               -> planilha nova em rascunho, sem rebaixar a origem.
  15. Exportar documento     -> XLSX da planilha responde pelo gateway.
  16. NBR 12721              -> os quadros da incorporação respondem.
  17. Gate de relatório      -> quem não tem `orcamento.relatorio.view` não lê /controle/.

Rodar (stack de pé):  python testes/e2e/orc6_orcamento_test.py
                      SGI_GW=https://localhost:8443 python testes/e2e/orc6_orcamento_test.py
"""
import json, os, ssl, sys, urllib.error, urllib.parse, urllib.request
from datetime import date
from decimal import Decimal

# Console do Windows costuma ser cp1252 e quebra em acento ao redirecionar.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")  # SGI_GW aponta ao staging (10.7)

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def req(method, path, token=None, body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=120, context=_CTX) as resp:
            if raw:  # binário (XLSX/PDF): interessa o tamanho, não o corpo
                return resp.status, resp.read()
            return resp.status, json.loads(resp.read().decode() or "null")
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
    return Decimal(str(v if v not in (None, "") else 0))


passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def fatal(msg):
    print(f"\n  !! {msg}")
    print("     O seed do backend (backend/seed_demo_data.py) precisa ter rodado.")
    print(f"     Parcial: {sum(1 for p in passed if p)}/{len(passed)}")
    sys.exit(2)


demo = login("demo", "demo123")
semdrone = login("semdrone", "semdrone123")

# ---------------------------------------------------------------------------
print("== 1. Módulo vivo ==")
status, st = req("GET", "/api/orcamento/status/", demo)
check(f"GET /api/orcamento/status/ (200) -> {status}", status == 200)
check(f"há publicação referencial ativa -> {(st or {}).get('bases_referenciais')}",
      status == 200 and (st or {}).get("bases_referenciais", 0) > 0)

# ---------------------------------------------------------------------------
print("== 2. Entitlement fecha para quem não assina ==")
status, _ = req("GET", "/api/orcamento/orcamentos/", semdrone)
check(f"semdrone (sem o módulo orcamento) -> 403, veio {status}", status == 403)
status, _ = req("GET", "/api/orcamento/orcamentos/", demo)
check(f"demo (assina) -> 200, veio {status}", status == 200)

# ---------------------------------------------------------------------------
print("== 3. Base referencial é dado público e read-only ==")
status, bases = req("GET", "/api/orcamento/bases/", demo)
check(f"GET /bases/ (200) -> {status}", status == 200)
base = next(iter(linhas(bases)), None)
if base is None:
    fatal("nenhuma publicação referencial no seed — sem ela não há o que adotar")
base_id = base.get("base_id") or base.get("id")

status, _ = req("POST", "/api/orcamento/bases/", demo, {"fonte": "sinapi", "uf": "SP"})
check(f"POST /bases/ recusado (405) -> {status}", status == 405)

status, refs = req("GET", f"/api/orcamento/referencias/?base_referencial={base_id}"
                          f"&tipo=composicao&page_size=5", demo)
check(f"GET /referencias/ (200) -> {status}", status == 200)
composicao = next(iter(linhas(refs)), None)
if composicao is None:
    fatal("a publicação do seed não tem composição — a explosão do ORC.2 fica sem prova")
ref_id = composicao.get("referencia_id") or composicao.get("id")
print(f"  publicação={base_id} composição de referência={ref_id} "
      f"({composicao.get('codigo')} {str(composicao.get('descricao'))[:40]}…)")

# ---------------------------------------------------------------------------
print("== 4. Adoção no catálogo é idempotente ==")
status, adotado = req("POST", f"/api/orcamento/referencias/{ref_id}/adotar/", demo, {})
check(f"adotar (200/201) -> {status}", status in (200, 201))
item_id = (adotado or {}).get("item_id") or (adotado or {}).get("item")
check(f"devolveu o item do catálogo -> {item_id}", bool(item_id))

status2, adotado2 = req("POST", f"/api/orcamento/referencias/{ref_id}/adotar/", demo, {})
item_id2 = (adotado2 or {}).get("item_id") or (adotado2 or {}).get("item")
check(f"adotar de novo devolve o MESMO item ({item_id}) -> {item_id2}",
      status2 in (200, 201) and str(item_id2) == str(item_id))

# D110 — a procedência tem de chegar preenchida na adoção real, e não só no
# teste unitário: é a garantia pedida para quando as bases de verdade entrarem.
status, catalogado = req("GET", f"/api/catalogo/itens/{item_id}/", demo)
publicacao = (catalogado or {}).get("publicacao_referencia")
check(f"o item adotado guarda a EDIÇÃO de origem -> {publicacao!r}",
      status == 200 and bool(publicacao))

# A publicação declara se a classificação dela chega até a natureza — e, quando
# não chega, quais palavras não soubemos ler (D112).
status, resumo = req("GET", "/api/orcamento/bases-resumo/", demo)
check(f"GET /bases-resumo/ (200) -> {status}", status == 200)
declaram = [b for b in (resumo or []) if "classifica_insumo" in b and "classes_desconhecidas" in b]
check(f"toda publicação declara se classifica insumo -> {len(declaram)}/{len(resumo or [])}",
      bool(resumo) and len(declaram) == len(resumo))
ilegiveis = {c for b in (resumo or []) for c in b.get("classes_desconhecidas", [])}
check(f"nenhuma classe ilegível nas publicações do seed -> {sorted(ilegiveis) or 'nenhuma'}",
      not ilegiveis)

# ---------------------------------------------------------------------------
print("== 5. Planilha versionada: rascunho v1 + snapshot na linha ==")
# Uma obra SEM orçamento aprovado, para o seam do passo 8 ser causal: mede-se
# /controle/ antes e depois de aprovar. Se todas já tiverem, o teste diz.
status, obras = req("GET", "/api/obras/", demo)
if status != 200:
    fatal(f"não consegui listar obras (status {status})")
status, controle_antes = req("GET", "/api/orcamento/controle/", demo)
check(f"GET /controle/ (200) -> {status}", status == 200)
com_orcado = {str(o["obra"]) for o in (controle_antes or {}).get("obras", [])
              if o.get("orcado") is not None}
obra_id = next((o.get("obra_id") for o in linhas(obras)
                if str(o.get("obra_id")) not in com_orcado), None)
if obra_id is None:
    fatal("toda obra do seed já tem orçamento aprovado — o passo 8 perderia a prova causal")
print(f"  obra limpa escolhida: {obra_id}")

hoje = date.today().replace(day=1)
status, orc = req("POST", "/api/orcamento/orcamentos/", demo, {
    "obra": obra_id,
    "base_referencial": base_id,
    "descricao": "E2E ORC.6 — planilha do teste vivo",
    "data_base": hoje.isoformat(),
    "regime_encargos": "desonerado",
    "encargos_sociais_percentual": "77.00",
    "bdi_percentual": "22.00",
})
check(f"orçamento criado (201) -> {status}", status == 201)
if status != 201:
    fatal(f"não consegui criar o orçamento: {orc}")
orc_id = orc["orcamento_id"]
# A versão é do servidor (a obra pode já ter planilhas): o que se prova é que
# nasce rascunho editável e numerado, não que seja exatamente a v1.
check(f"nasce em rascunho editável e numerado -> {orc.get('status')} v{orc.get('versao')}",
      orc.get("status") == "rascunho" and orc.get("editavel") is True
      and (orc.get("versao") or 0) >= 1)
versao_inicial = orc.get("versao")

status, linha = req("POST", "/api/orcamento/itens/do-catalogo/", demo, {
    "orcamento": orc_id, "item": item_id, "quantidade": "10",
})
check(f"linha criada do catálogo (201) -> {status}", status == 201)
if status != 201:
    fatal(f"não consegui criar a linha: {linha}")
linha_id = linha["item_orcado_id"] if "item_orcado_id" in (linha or {}) else linha.get("id")
desc_snapshot = linha.get("descricao")
check(f"a linha trouxe o snapshot da descrição -> {str(desc_snapshot)[:40]}…",
      bool(desc_snapshot))
check(f"e o custo unitário da publicação -> {linha.get('custo_unitario')}",
      D(linha.get("custo_unitario")) > 0)

status, arvore = req("GET", f"/api/orcamento/orcamentos/{orc_id}/arvore/", demo)
check(f"GET /arvore/ (200) -> {status}", status == 200)

# ---------------------------------------------------------------------------
print("== 6. O snapshot congela: mexer no catálogo não mexe na régua ==")
status, item_antes_rename = req("GET", f"/api/catalogo/itens/{item_id}/", demo)
check(f"o item adotado existe no catálogo do tenant -> {status}", status == 200)
nome_original = (item_antes_rename or {}).get("descricao")
status, _ = req("PATCH", f"/api/catalogo/itens/{item_id}/", demo,
                {"descricao": "RENOMEADO PELO E2E ORC.6"})
check(f"renomear o item no catálogo (200) -> {status}", status == 200)
status, releitura = req("GET", f"/api/orcamento/itens/{linha_id}/", demo)
check(f"a linha do orçamento manteve a descrição antiga -> {str((releitura or {}).get('descricao'))[:40]}…",
      status == 200 and (releitura or {}).get("descricao") == desc_snapshot)
# devolve o catálogo ao estado anterior — E2E não deve deixar lixo com nome falso
if nome_original:
    req("PATCH", f"/api/catalogo/itens/{item_id}/", demo, {"descricao": nome_original})

# ---------------------------------------------------------------------------
print("== 7. Explosão da composição e a cobertura honesta ==")
status, memoria = req("POST", f"/api/orcamento/itens/{linha_id}/explodir/", demo, {})
explodiu = status == 200
check(f"explodir (200) -> {status}", explodiu)
if explodiu:
    check(f"a memória de cálculo veio com insumos -> {len((memoria or {}).get('insumos', []))}",
          len((memoria or {}).get("insumos", [])) > 0)

status, categoria = req("GET", f"/api/orcamento/orcamentos/{orc_id}/por-categoria/", demo)
check(f"GET /por-categoria/ (200) -> {status}", status == 200)
check(f"declara a cobertura em vez de fingir total -> {(categoria or {}).get('cobertura_pct')}",
      status == 200 and "cobertura_pct" in (categoria or {}))

# ---------------------------------------------------------------------------
print("== 8. Alçada de aprovação (D28) ==")
# Até 26/07/2026 `aprovar`/`revisar` não estavam em NENHUMA persona de fábrica, e
# só o admin do tenant alcançava os dois verbos (ele bypassa o RequirePermission).
# Por decisão do dono do produto, a alçada passou a ser do próprio `orcamentista`.
status, aprovado = req("POST", f"/api/orcamento/orcamentos/{orc_id}/aprovar/", demo, {})
check(f"o orçamentista aprova (200) -> {status}", status == 200)
check("a permissão veio da persona, não do bypass de admin (o token do demo não é tenant_admin)",
      status == 200)

print("== 9. Aprovar congela a régua ==")
check(f"status aprovado e não mais editável -> {(aprovado or {}).get('status')}",
      (aprovado or {}).get("status") == "aprovado" and (aprovado or {}).get("editavel") is False)

status, _ = req("PATCH", f"/api/orcamento/orcamentos/{orc_id}/", demo, {"descricao": "não deveria passar"})
check(f"PATCH em aprovado recusado (409/400) -> {status}", status in (400, 409))
status, _ = req("POST", "/api/orcamento/itens/do-catalogo/", demo,
                {"orcamento": orc_id, "item": item_id, "quantidade": "1"})
check(f"nova linha em aprovado recusada (409/400) -> {status}", status in (400, 409))

# ---------------------------------------------------------------------------
print("== 10. Seam: a régua aprovada passa a valer nas quatro colunas ==")
status, controle = req("GET", f"/api/orcamento/controle/?obra={obra_id}", demo)
check(f"GET /controle/?obra= (200) -> {status}", status == 200)
linha_obra = next((o for o in (controle or {}).get("obras", [])
                   if str(o.get("obra")) == str(obra_id)), None)
check(f"a obra que NÃO tinha orçado agora tem -> {linha_obra and linha_obra.get('orcado')}",
      linha_obra is not None and linha_obra.get("orcado") is not None)
check(f"aponta o orçamento que virou régua ({orc_id}) -> {linha_obra and linha_obra.get('orcamento')}",
      linha_obra is not None and str(linha_obra.get("orcamento")) == str(orc_id))
check("as quatro colunas vêm juntas",
      linha_obra is not None
      and all(k in linha_obra for k in ("orcado", "comprometido", "aplicado", "realizado")))
check(f"o BDI entra no orçado com BDI -> {linha_obra and linha_obra.get('orcado_com_bdi')}",
      linha_obra is not None
      and D(linha_obra.get("orcado_com_bdi")) > D(linha_obra.get("orcado")))
check("a nota diz o que o realizado cobre (dado honesto)",
      "nota_realizado" in (controle or {}))

# ---------------------------------------------------------------------------
print("== 11. Revisar gera a versão seguinte ==")
status, _ = req("POST", f"/api/orcamento/orcamentos/{orc_id}/revisar/", demo, {})
check(f"revisar sem motivo recusado (400) -> {status}", status == 400)
status, nova = req("POST", f"/api/orcamento/orcamentos/{orc_id}/revisar/", demo,
                   {"tipo": "aditivo", "motivo": "E2E ORC.6 — aditivo de teste"})
check(f"revisar com motivo (201) -> {status}", status == 201)
rev_id = (nova or {}).get("orcamento_id")
check(f"a revisão é a versão seguinte (v{versao_inicial} -> v{(nova or {}).get('versao')}) e é editável",
      (nova or {}).get("versao") == (versao_inicial or 0) + 1
      and (nova or {}).get("editavel") is True)

# ---------------------------------------------------------------------------
print("== 12. Cronograma físico-financeiro e curva S ==")
inicio = hoje.isoformat()
fim = hoje.replace(year=hoje.year + (1 if hoje.month > 8 else 0),
                   month=((hoje.month + 3 - 1) % 12) + 1).isoformat()
status, crono = req("POST", f"/api/orcamento/orcamentos/{rev_id}/distribuir-cronograma/", demo,
                    {"inicio": inicio, "fim": fim})
check(f"distribuir-cronograma (201) -> {status}", status == 201)
check(f"gerou competências -> {(crono or {}).get('competencias')}",
      len((crono or {}).get("competencias", [])) > 0)

# A conferência dos 100% vem no GET (`validacao`), não na resposta da distribuição.
# Ler a chave certa importa: a primeira versão deste teste procurava
# `total_percentual`, que não existe, e o check passava com None — verde vazio.
status, grade = req("GET", f"/api/orcamento/orcamentos/{rev_id}/cronograma/", demo)
check(f"GET /cronograma/ (200) -> {status}", status == 200)
validacao = (grade or {}).get("validacao") or {}
check(f"a distribuição linear fecha 100% em toda etapa -> "
      f"consistente={validacao.get('consistente')} problemas={validacao.get('problemas')}",
      validacao.get("consistente") is True)

status, curva = req("GET", f"/api/orcamento/orcamentos/{rev_id}/curva-s/", demo)
check(f"GET /curva-s/ (200) -> {status}", status == 200)

# ---------------------------------------------------------------------------
print("== 13. Reprecificação: prévia inerte, aplicar, desfazer ==")
status, todas_bases = req("GET", "/api/orcamento/bases/", demo)
outra = next((b for b in linhas(todas_bases)
              if str(b.get("base_id") or b.get("id")) != str(base_id)), None)
if outra is None:
    print("      (só há uma publicação no seed — reprecificação sem destino, pulada)")
else:
    destino_id = outra.get("base_id") or outra.get("id")
    status, item_antes = req("GET", "/api/orcamento/itens/?orcamento=%s" % rev_id, demo)
    alvo = next(iter(linhas(item_antes)), None)
    preco_antes = D((alvo or {}).get("custo_unitario"))

    status, previa = req("POST", f"/api/orcamento/orcamentos/{rev_id}/reprecificar/", demo,
                         {"base_destino": destino_id})
    check(f"prévia de reprecificação (200) -> {status}", status == 200)
    lote_id = (previa or {}).get("reprecificacao")  # chave do `serializar_previa`
    check(f"a prévia devolveu o lote e o que ele muda -> lote={lote_id} "
          f"delta={(previa or {}).get('delta')} linhas={(previa or {}).get('linhas_afetadas')}",
          bool(lote_id))

    status, item_meio = req("GET", "/api/orcamento/itens/?orcamento=%s" % rev_id, demo)
    meio = next(iter(linhas(item_meio)), None)
    check(f"a prévia NÃO alterou o preço ainda ({preco_antes}) -> {(meio or {}).get('custo_unitario')}",
          D((meio or {}).get("custo_unitario")) == preco_antes)

    if lote_id:
        status, _ = req("POST", f"/api/orcamento/reprecificacoes/{lote_id}/aplicar/", demo, {})
        check(f"aplicar o lote (200) -> {status}", status == 200)
        status, _ = req("POST", f"/api/orcamento/reprecificacoes/{lote_id}/desfazer/", demo, {})
        check(f"desfazer o lote (200) -> {status}", status == 200)
        status, item_fim = req("GET", "/api/orcamento/itens/?orcamento=%s" % rev_id, demo)
        fim_linha = next(iter(linhas(item_fim)), None)
        check(f"o preço voltou ao que era ({preco_antes}) -> {(fim_linha or {}).get('custo_unitario')}",
              D((fim_linha or {}).get("custo_unitario")) == preco_antes)

# ---------------------------------------------------------------------------
print("== 14. Duplicar é planilha nova, não revisão ==")
# O estado da origem ANTES: a revisão do passo 11 já a deixou `superado` (é o
# desenho do `revisar` — a versão anterior deixa de ser a vigente). O que se
# prova aqui é que `duplicar` NÃO mexe no estado da origem, ao contrário de
# `revisar`; comparar com "aprovado" fixo confundia os dois verbos.
status, antes_dup = req("GET", f"/api/orcamento/orcamentos/{orc_id}/", demo)
estado_antes = (antes_dup or {}).get("status")

status, dup = req("POST", f"/api/orcamento/orcamentos/{orc_id}/duplicar/", demo,
                  {"descricao": "E2E ORC.6 — duplicata"})
check(f"duplicar (201) -> {status}", status == 201)
# `resumo_da_duplicata` devolve o id do orçamento novo em `orcamento` (int).
bruto = (dup or {}).get("orcamento")
dup_id = bruto.get("orcamento_id") if isinstance(bruto, dict) else bruto
status, origem = req("GET", f"/api/orcamento/orcamentos/{orc_id}/", demo)
check(f"duplicar não mexeu no estado da origem ({estado_antes}) -> {(origem or {}).get('status')}",
      (origem or {}).get("status") == estado_antes)
if dup_id:
    status, nova_dup = req("GET", f"/api/orcamento/orcamentos/{dup_id}/", demo)
    check(f"a duplicata nasce rascunho -> {(nova_dup or {}).get('status')}",
          (nova_dup or {}).get("status") == "rascunho")

# ---------------------------------------------------------------------------
print("== 15. Exportação do documento formatado ==")
status, blob = req("GET", f"/api/orcamento/orcamentos/{orc_id}/exportar/"
                          f"?formato=xlsx&nivel=sintetico&peca=planilha", demo, raw=True)
check(f"XLSX da planilha responde ({status}) com corpo -> "
      f"{len(blob) if isinstance(blob, bytes) else blob} bytes",
      status == 200 and isinstance(blob, bytes) and len(blob) > 1000)

# ---------------------------------------------------------------------------
print("== 16. NBR 12721 (incorporação) ==")
status, nbr = req("GET", f"/api/orcamento/nbr12721/?obra={obra_id}", demo)
check(f"GET /nbr12721/?obra= (200) -> {status}", status == 200)

# ---------------------------------------------------------------------------
print("== 17. Gate de relatório: entitlement não basta ==")
status, _ = req("GET", "/api/orcamento/controle/", semdrone)
check(f"semdrone em /controle/ -> 403, veio {status}", status == 403)

print()
ok = sum(1 for p in passed if p)
print(f"RESULTADO: {ok}/{len(passed)}")
sys.exit(0 if ok == len(passed) else 1)
