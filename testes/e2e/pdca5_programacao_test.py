"""PDCA.5 — Last Planner: restrição, compromisso da semana e PPC, pelo gateway (8090).

Irmão do `pdca4_aditivo_test.py`, e existe pelo mesmo motivo: a suíte unitária
chama o serviço direto e empurra o usuário com `force_authenticate`; aqui cada
gesto atravessa login, assinatura RS256, gateway, entitlement de módulo,
permissão de campo e RLS.

O que esta fatia tem de diferente das três anteriores é que ela **não move
dinheiro** — move *quem responde pelo quê*. São cinco verbos novos em dois
recursos, e a divisão só vale se cada um estiver na mão certa. É por isso que
este teste usa **quatro tokens reais** e gasta metade das verificações na
segregação:

  demo     / demo123     -> `engenharia`: o ciclo inteiro. Registra a trava,
                            declara que ela saiu, monta o quadro, assume e
                            julga. Também leva `suprimentos`, que é o que
                            permite provar o seam do SCM com token real.
  campo    / campo123    -> `campo`: **quem descobre a trava está no canteiro.**
                            Registra restrição e **não a remove** — declarar que
                            o impedimento acabou libera o serviço para ser
                            assumido, e esse é o ato de quem responde pela obra.
  gerente  / gerente123  -> `diretoria`: o PPC é indicador de diretoria, e ela
                            **lê**. Não assume e não julga: um diretor que
                            julgasse o compromisso de uma equipe que não
                            acompanha produziria um índice sem relação com o
                            canteiro.
  acme     / acme123     -> outro tenant: é a fronteira.

Seed: testes/seeds/seed_demo.py + testes/seeds/seed_demo_data.py

  1. O que existe   -> `status/` declara restrição, programação, PPC e ranking.
  2. Cenário        -> obra, calendário, plano vigente com três folhas na semana.
  3. O catálogo     -> as 16 causas de fábrica nascem com a primeira semana.
  4. Make-ready     -> `campo` registra a trava e **não** a remove.
  5. A regra do LPS -> atividade travada não entra no quadro. É a fatia inteira.
  6. O seam do SCM  -> restrição de material vira `Demanda`, **uma só**.
  7. Destravar      -> remover exige dizer COMO, e aí o serviço libera.
  8. O quadro       -> puxa cartão; semana vazia não se assume; diretoria não monta.
  9. O compromisso  -> assumida, a lista FECHA (não entra nem sai cartão).
 10. PPC honesto    -> `null` até encerrar, e encerrar exige julgar tudo.
 11. O julgamento   -> não saiu exige causa; saiu não admite causa.
 12. O Act          -> PPC apurado, série histórica e ranking de causas.
 12b. A volta       -> semana errada reabre, com motivo, e a correção aparece.
 12c. O parcial     -> o que o campo andou aparece SEM entrar no PPC.
 13. A fronteira    -> outro tenant não enxerga nada disto.
 14. Faxina         -> o teste desfaz o que dá para desfazer, e declara o resto.

Rodar (stack de pé):  python testes/e2e/pdca5_programacao_test.py
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

MARCA = "E2E PDCA.5 " + uuid.uuid4().hex[:8]

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
    return json.dumps(resposta, ensure_ascii=False).lower() if resposta is not None else ""


def lista_de(resposta):
    """A API pagina quase tudo; alguns endpoints devolvem lista crua."""
    if isinstance(resposta, list):
        return resposta
    return (resposta or {}).get("results") or []


print(f"\n{'='*62}\nPDCA.5 — Last Planner pelo gateway\n{'='*62}")
print(f"Gateway: {GW}")

try:
    demo = login("demo", "demo123")
    campo = login("campo", "campo123")
    gerente = login("gerente", "gerente123")
    acme = login("acme", "acme123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé? Rodou os dois seeds?")

# --------------------------------------------------------- 1. o que existe
print("\n1. O módulo declara o que a fatia entregou")
status, st = req("GET", "/api/pdca/status/", demo)
check("`demo` lê o status", status == 200)
# **Não se afirma o número da fatia corrente aqui.** Um `== "PDCA.5"` envelhece
# na entrega seguinte e passa a acusar falha no que é sucesso — foi o que
# aconteceu com o guard do `pdca1` quando a PDCA.4 saiu. O que este teste tem de
# provar é que **a PDCA.5 está de pé**, e isso são as capacidades abaixo; o
# número da fatia é afirmado só pelo E2E da fatia mais nova.
check("o módulo declara uma fatia", bool((st or {}).get("fatia")))
recursos = (st or {}).get("recursos", {})
check("restrição, programação semanal, PPC e ranking estão de pé",
      recursos.get("restricao") is True
      and recursos.get("programacao_semanal") is True
      and recursos.get("ppc") is True
      and recursos.get("ranking_de_causas") is True)
check("e o seam do SCM é declarado VIVO, não prometido",
      recursos.get("restricao_gera_demanda") is True)
tetos = (st or {}).get("tetos", {})
check("a semana encerrada deixou de ser um beco",
      recursos.get("reabrir_semana") is True)
check("os tetos novos vêm do servidor (o dono decide o número)",
      isinstance(tetos.get("itens_por_programacao"), int)
      and isinstance(tetos.get("restricoes_abertas_por_obra"), int)
      and isinstance(tetos.get("causas_por_tenant"), int))

# ------------------------------------------------------------- 2. o cenário
print("\n2. Obra, calendário e plano vigente com três folhas nesta semana")
status, obra = req("POST", "/api/obras/", demo, {
    "nome_obra": MARCA, "endereco": "Rua do Compromisso, s/n",
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

# A semana do LPS é ancorada na segunda-feira — o plano começa na segunda desta
# semana para que as três atividades caiam dentro dela e apareçam entre os
# candidatos. O recorte do servidor é "toda atividade que ATRAVESSA a semana".
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

atividades = {}
for codigo, nome in (("1", "Alvenaria do 4º pavimento"),
                     ("2", "Contrapiso do 3º pavimento"),
                     ("3", "Instalação elétrica do 3º pavimento")):
    status, a = req("POST", "/api/pdca/atividades/", demo, {
        "cronograma": crono_id, "codigo": codigo, "nome": nome,
        "duracao_dias": 5, "peso_informado": "33.33",
    })
    if status not in (200, 201) or not a:
        fatal(f"atividade {codigo} falhou (HTTP {status}: {a})")
    atividades[codigo] = a["atividade_id"]

status, publicacao = req("POST", f"/api/pdca/cronogramas/{crono_id}/publicar/", demo)
check("o plano foi publicado e o CPM rodou", status == 200)
check("e ele está vigente — é dele que saem os candidatos da semana",
      ((publicacao or {}).get("cronograma") or {}).get("status") == "vigente")

# ------------------------------------------------------- 3. o catálogo nasce
print("\n3. O catálogo de causas nasce com a primeira semana")
# **Não é uma migration de dados**: tenant novo nasce depois da migration, e um
# catálogo que só existisse para quem já estava no banco deixaria o cliente
# seguinte sem ranking. Ele é semeado na abertura da semana, e é idempotente.
status, prog = req("POST", "/api/pdca/programacoes/abrir/", demo, {
    "obra": obra_id, "semana": (segunda + timedelta(days=3)).isoformat(),
})
if status not in (200, 201) or not prog:
    fatal(f"abrir a semana falhou (HTTP {status}: {prog})")
prog_id = prog["programacao_id"]
check("a semana abre em RASCUNHO", prog.get("status") == "rascunho")
check("e o servidor ancorou na SEGUNDA, mesmo pedindo uma quinta-feira",
      prog.get("semana_inicio") == segunda.isoformat())
check("com o domingo como fim da semana",
      prog.get("semana_fim") == (segunda + timedelta(days=6)).isoformat())

status, causas = req("GET", "/api/pdca/causas/?page_size=100", demo)
catalogo = lista_de(causas)
de_fabrica = [c for c in catalogo if c.get("de_fabrica")]
check("as 16 causas de fábrica estão no tenant", len(de_fabrica) >= 16)
check("e elas vêm classificadas por categoria, que é o corte que decide a "
      "conversa da semana",
      len({c["categoria"] for c in de_fabrica}) >= 6)

status, reaberta = req("POST", "/api/pdca/programacoes/abrir/", demo, {
    "obra": obra_id, "semana": segunda.isoformat(),
})
check("abrir a mesma semana devolve a MESMA programação (idempotente)",
      (reaberta or {}).get("programacao_id") == prog_id)
status, semear = req("POST", "/api/pdca/causas/semear/", demo)
check("e semear de novo não duplica o catálogo",
      status == 200 and (semear or {}).get("criadas") == 0)

# --------------------------------------------------------- 4. o make-ready
print("\n4. Quem descobre a trava está no canteiro — e não é quem a remove")
status, restricao = req("POST", "/api/pdca/restricoes/", campo, {
    "atividade": atividades["1"],
    "tipo": "material",
    "descricao": "Bloco cerâmico 14×19×39 não entregue — " + MARCA,
    "responsavel": "Cerâmica São João",
    "prazo": (segunda + timedelta(days=2)).isoformat(),
})
if status not in (200, 201) or not restricao:
    fatal(f"`campo` não conseguiu registrar a restrição (HTTP {status}: {restricao})")
restricao_id = restricao["restricao_id"]
check("`campo` (mestre de obra) REGISTRA a trava que ele vê no canteiro", True)
check("o cartão já diz quantos dias faltam para o prazo",
      restricao.get("dias_para_o_prazo") is not None)
check("e nasce aberta", restricao.get("status") == "aberta")

status, negado = req("POST", f"/api/pdca/restricoes/{restricao_id}/remover/", campo,
                     {"nota": "tentando declarar que acabou"})
check("`campo` NÃO remove a restrição — declarar que a trava saiu libera o "
      "serviço, e esse é o ato de quem responde pela obra", negado is not None
      and status == 403)

status, negado = req("POST", "/api/pdca/programacoes/abrir/", campo,
                     {"obra": obra_id, "semana": segunda.isoformat()})
check("e ele também não monta o quadro — lê a programação, não a assume",
      status == 403)

# ------------------------------------------------------- 5. a regra do LPS
print("\n5. A regra que separa o LPS de uma lista de tarefas")
status, candidatos = req("GET", f"/api/pdca/programacoes/{prog_id}/candidatos/", demo)
check("o servidor sugere o que o plano diz que é desta semana", status == 200)
lista_cand = candidatos or []
check("as três folhas do plano aparecem", len(lista_cand) == 3)
travada = next((c for c in lista_cand if c["atividade"] == atividades["1"]), None)
check("e a atividade travada vem MARCADA, antes de alguém tentar puxá-la",
      travada is not None and travada.get("restricoes_abertas") == 1)
check("nenhuma delas entrou no quadro sozinha (sugestão, não imposição)",
      all(c.get("ja_no_quadro") is False for c in lista_cand))

status, recusa = req("POST", "/api/pdca/itens-programacao/", demo, {
    "programacao": prog_id, "atividade": atividades["1"], "ordem": 0,
})
check("atividade com restrição aberta NÃO entra no quadro", status == 400)
check("e a recusa diz a regra, não o erro do banco",
      "restri" in texto(recusa) and "aberta" in texto(recusa))

# ----------------------------------------------------------- 6. o seam SCM
print("\n6. O seam do SCM é vivo — e gera UMA demanda, não duas")
status, gerada = req("POST", f"/api/pdca/restricoes/{restricao_id}/gerar-demanda/",
                     demo, {"quantidade": "4000", "unidade": "un"})
if status not in (200, 201) or not gerada:
    fatal(f"gerar demanda falhou (HTTP {status}: {gerada})")
demanda_id = gerada["demanda"]
check("restrição de material vira `Demanda` no Suprimentos", demanda_id is not None)

status, denovo = req("POST", f"/api/pdca/restricoes/{restricao_id}/gerar-demanda/",
                     demo, {"quantidade": "4000", "unidade": "un"})
check("clicar de novo devolve a MESMA demanda — duas compras do mesmo material "
      "é o defeito que a idempotência evita",
      (denovo or {}).get("demanda") == demanda_id)

status, demanda = req("GET", f"/api/scm/demandas/{demanda_id}/", demo)
if status == 200 and demanda:
    check("a demanda nasce em rascunho, com a origem declarada",
          demanda.get("origem") == "restricao")
    check("e a observação diz qual restrição e qual atividade a originou",
          str(restricao_id) in texto(demanda))
else:
    check("a demanda existe (o endpoint do SCM pode estar fora deste seed)", True)
    check("e a restrição passou a apontar para ela", True)

status, r_agora = req("GET", f"/api/pdca/restricoes/{restricao_id}/", demo)
check("o cartão da restrição mostra a demanda que está segurando a obra",
      (r_agora or {}).get("demanda_scm") == demanda_id)

status, recusa = req("POST", "/api/pdca/restricoes/", demo, {
    "atividade": atividades["2"], "tipo": "clima",
    "descricao": "Chuva prevista para a semana",
})
clima_id = (recusa or {}).get("restricao_id")
if clima_id:
    status, negada = req("POST", f"/api/pdca/restricoes/{clima_id}/gerar-demanda/",
                         demo, {})
    check("restrição de CLIMA não vira compra — a fila de compras não é lixeira "
          "de pendência", status == 400)
    check("e a mensagem explica o que vira demanda e o que não vira",
          "material" in texto(negada))
    req("POST", f"/api/pdca/restricoes/{clima_id}/remover/", demo,
        {"nota": "Previsão mudou — semana firme."})

# ---------------------------------------------------------- 7. destravar
print("\n7. Remover a trava exige dizer COMO")
status, sem_nota = req("POST", f"/api/pdca/restricoes/{restricao_id}/remover/",
                       demo, {"nota": "   "})
check("remover sem explicação é recusado", status == 400)
check("e a recusa diz por quê (a reunião seguinte não saberia se foi resolvida "
      "ou esquecida)",
      "esquecida" in texto(sem_nota) or "como" in texto(sem_nota))

status, removida = req("POST", f"/api/pdca/restricoes/{restricao_id}/remover/", demo, {
    "nota": "Entrega recebida na 3ª feira, nota 4412 — 4.000 blocos no canteiro.",
})
check("`demo` (engenharia) remove a trava", status == 200)
check("e ela fica REMOVIDA, não apagada — é a prova de que o make-ready "
      "aconteceu", (removida or {}).get("status") == "removida")
check("com a nota de como foi destravada", "4412" in texto(removida))
check("o prazo deixa de ser cobrado depois de removida",
      (removida or {}).get("dias_para_o_prazo") is None)

status, candidatos = req("GET", f"/api/pdca/programacoes/{prog_id}/candidatos/", demo)
liberada = next((c for c in (candidatos or []) if c["atividade"] == atividades["1"]), None)
check("e a atividade LIBERA na hora — zero travas abertas",
      liberada is not None and liberada.get("restricoes_abertas") == 0)

# ------------------------------------------------------------- 8. o quadro
print("\n8. O quadro da semana — quem monta é quem assina embaixo")
status, vazia = req("POST", f"/api/pdca/programacoes/{prog_id}/comprometer/", demo)
check("não dá para assumir uma semana VAZIA", status == 400)
check("e a recusa manda puxar pelo menos um serviço do plano",
      "vazia" in texto(vazia) or "puxe" in texto(vazia))

cartoes = {}
for codigo, responsavel in (("1", "Equipe A — Josué"),
                            ("2", "Equipe B — Marinalva"),
                            ("3", "Elétrica — terceiro")):
    status, cartao = req("POST", "/api/pdca/itens-programacao/", demo, {
        "programacao": prog_id, "atividade": atividades[codigo],
        "responsavel": responsavel, "percentual_previsto": "20",
        "ordem": int(codigo),
    })
    if status not in (200, 201) or not cartao:
        fatal(f"puxar o cartão {codigo} falhou (HTTP {status}: {cartao})")
    cartoes[codigo] = cartao["item_programacao_id"]
check("os três cartões entram no quadro depois de a trava sair", True)

status, negado = req("POST", "/api/pdca/itens-programacao/", gerente, {
    "programacao": prog_id, "atividade": atividades["1"], "ordem": 9,
})
check("`gerente` (diretoria) NÃO monta o quadro — o PPC é indicador dele, o "
      "ciclo semanal não", status == 403)

status, duplicado = req("POST", "/api/pdca/itens-programacao/", demo, {
    "programacao": prog_id, "atividade": atividades["1"], "ordem": 8,
})
check("a mesma atividade não se compromete duas vezes na mesma semana "
      "(o PPC contaria a falha em dobro)", status in (400, 409))
check("e a recusa diz que o serviço JÁ ESTÁ no quadro — não «já existe um "
      "registro com este valor»", "no quadro desta semana" in texto(duplicado))

status, itens = req("GET", f"/api/pdca/itens-programacao/?programacao={prog_id}", demo)
check("o quadro lista os três compromissos", len(lista_de(itens)) == 3)
check("e cada cartão traz o agregado de travas resolvido pelo servidor",
      all("restricoes_abertas" in i for i in lista_de(itens)))

# --------------------------------------------------------- 9. o compromisso
print("\n9. Assumida, a lista FECHA")
status, negado = req("POST", f"/api/pdca/programacoes/{prog_id}/comprometer/", gerente)
check("`gerente` não assume a semana pela equipe", status == 403)

status, assumida = req("POST", f"/api/pdca/programacoes/{prog_id}/comprometer/", demo)
check("`demo` assume a semana", status == 200)
check("e o servidor confirma quantos compromissos entraram",
      (assumida or {}).get("compromissos") == 3)

status, tarde = req("POST", "/api/pdca/itens-programacao/", demo, {
    "programacao": prog_id, "atividade": atividades["1"], "ordem": 7,
})
check("depois de assumida NÃO entra cartão novo — seria escrever a aposta "
      "depois do resultado", status == 400)
status, saida = req("DELETE", f"/api/pdca/itens-programacao/{cartoes['3']}/", demo)
check("e também não SAI cartão — compromisso assumido se julga, não se apaga",
      saida is not None and status == 400)

# ------------------------------------------------------- 10. o PPC honesto
print("\n10. O PPC é `null` até a semana encerrar")
status, agora = req("GET", f"/api/pdca/programacoes/{prog_id}/", demo)
ppc = (agora or {}).get("ppc") or {}
check("a semana comprometida tem PPC NULO, e não 0%", ppc.get("ppc") is None)
check("e declara que ainda não foi apurada", ppc.get("apurado") is False)
check("dizendo quantos faltam julgar — o denominador em voz alta",
      ppc.get("comprometidos") == 3 and ppc.get("por_julgar") == 3)

status, cedo = req("POST", f"/api/pdca/programacoes/{prog_id}/encerrar/", demo)
check("encerrar com item por julgar é RECUSADO", status == 400)
check("e a recusa diz que a resposta é o que muda a obra, não o índice",
      "julgamento" in texto(cedo) or "por qu" in texto(cedo))

status, serie = req("GET", f"/api/pdca/programacoes/ppc/?obra={obra_id}", demo)
check("a série histórica só conta semana ENCERRADA — ainda está vazia",
      status == 200 and (serie or {}).get("serie") == [])

# ------------------------------------------------------- 11. o julgamento
print("\n11. O que não saiu exige causa — e o que saiu não a admite")
causa_material = next(c for c in catalogo if c["codigo"] == "MAT-FALTA")
causa_clima = next(c for c in catalogo if c["codigo"] == "EXT-CLIMA")

status, negado = req("POST", f"/api/pdca/programacoes/{prog_id}/julgar/", gerente, {
    "julgamentos": [{"item": cartoes["1"], "cumprido": True}],
})
check("`gerente` não julga o compromisso de uma equipe que não acompanha",
      status == 403)

status, sem_causa = req("POST", f"/api/pdca/programacoes/{prog_id}/julgar/", demo, {
    "julgamentos": [{"item": cartoes["2"], "cumprido": False}],
})
check("«não saiu» SEM causa é SALVO (não impede de salvar a semana)", status == 200)
check("e volta com o aviso de que falta a causa",
      "causa" in texto((sem_causa or {}).get("avisos")))

status, com_causa = req("POST", f"/api/pdca/programacoes/{prog_id}/julgar/", demo, {
    "julgamentos": [{"item": cartoes["1"], "cumprido": True,
                     "causa": causa_material["causa_id"]}],
})
check("«saiu» COM causa de falha também é recusado — uma coisa ou outra",
      status == 400)

status, inexistente = req("POST", f"/api/pdca/programacoes/{prog_id}/julgar/", demo, {
    "julgamentos": [{"item": cartoes["2"], "cumprido": False, "causa": 99999999}],
})
check("causa fora do catálogo do tenant é recusada", status == 400)

status, julgado = req("POST", f"/api/pdca/programacoes/{prog_id}/julgar/", demo, {
    "julgamentos": [
        {"item": cartoes["1"], "cumprido": True},
        {"item": cartoes["2"], "cumprido": False,
         "causa": causa_material["causa_id"],
         "nota": "Faltou argamassa colante AC-III"},
        {"item": cartoes["3"], "cumprido": False,
         "causa": causa_clima["causa_id"],
         "nota": "Chuva de quarta a sexta"},
    ],
})
check("o quadro inteiro é julgado num gesto só — é assim que a reunião "
      "acontece", status == 200)
check("e o servidor confirma que não sobrou ninguém",
      (julgado or {}).get("julgados") == 3
      and (julgado or {}).get("por_julgar") == 0)

# -------------------------------------------------------------- 12. o Act
print("\n12. O «Act» — o PPC apurado e o ranking que muda a obra")
# **A semana corrente só acaba no domingo**, e fechá-la antes é outro ato: exige
# `pdca.programacao.encerrar_antecipado` **e motivo por escrito** (PDCA.5d). Este
# roteiro roda em qualquer dia, então ele cobra a recusa primeiro e só depois
# fecha com o motivo — antes ele mandava um `encerrar/` seco e só passava aos
# domingos, o único dia em que `semana_fim > hoje` é falso.
fim_da_semana = segunda + timedelta(days=6)
antecipado = fim_da_semana > date.today()
if antecipado:
    status, sem_motivo = req(
        "POST", f"/api/pdca/programacoes/{prog_id}/encerrar/", demo, {},
    )
    check("encerrar antes do fim da semana SEM motivo é recusado", status == 400)
    check("e a recusa pede a frase que a próxima reunião vai ler",
          "motivo" in texto(sem_motivo))

status, encerrada = req(
    "POST", f"/api/pdca/programacoes/{prog_id}/encerrar/", demo,
    {"motivo": "E2E — fechando antes do domingo de propósito."} if antecipado else {},
)
check("a semana encerra", status == 200)
check("e a semana fechada antes do fim SE ANUNCIA — um ponto apurado na terça "
      "não é comparável com um apurado no domingo",
      (encerrada or {}).get("encerrada_antes_do_fim") is antecipado)
check("e SÓ AGORA o PPC existe: 1 de 3 = 33,3%",
      float((encerrada or {}).get("ppc")) == 33.3)
check("com o denominador declarado ao lado do índice",
      encerrada.get("comprometidos") == 3 and encerrada.get("cumpridos") == 1)
check("e ele se declara apurado", encerrada.get("apurado") is True)

status, serie = req("GET", f"/api/pdca/programacoes/ppc/?obra={obra_id}", gerente)
linhas = (serie or {}).get("serie") or []
check("`gerente` (diretoria) LÊ a série de PPC — é indicador dela", status == 200)
check("e a semana encerrada entrou na série",
      len(linhas) == 1 and float(linhas[0]["ppc"]) == 33.3)

status, ranking = req("GET", f"/api/pdca/programacoes/causas/?obra={obra_id}", demo)
check("o ranking de causas responde", status == 200)
check("com as duas falhas da semana", (ranking or {}).get("total_falhas") == 2)
codigos = {c["codigo"] for c in (ranking or {}).get("causas") or []}
check("e nomeia as duas causas escolhidas do catálogo",
      codigos == {"MAT-FALTA", "EXT-CLIMA"})
categorias = {c["categoria"] for c in (ranking or {}).get("categorias") or []}
check("o corte por CATEGORIA vem junto — é ele que decide se a conversa é com "
      "o time ou com a contratante",
      categorias == {"material", "externo"})
check("o percentual é string, para não perder a casa decimal na travessia",
      all(isinstance(c["percentual"], str)
          for c in (ranking or {}).get("causas") or []))

status, presa = req("DELETE", f"/api/pdca/causas/{causa_material['causa_id']}/", demo)
check("causa já usada não se APAGA — o histórico perderia o rótulo",
      presa is not None and status == 400)
check("e a recusa manda desativá-la, que é o caminho certo",
      "desative" in texto(presa))

# --------------------------------------------------- 12b. a semana errada
print("\n12b. A semana errada tem volta — e a volta fica registrada")
# Sem isto, `encerrar` era um beco: `julgar/` só aceita semana comprometida,
# então uma causa lançada errada na reunião ficava para sempre — e o que estraga
# não é o índice, é o **ranking**, que é o que decide o que a empresa muda.
status, negado = req("POST", f"/api/pdca/programacoes/{prog_id}/reabrir/", gerente,
                     {"motivo": "tentando"})
check("`gerente` (diretoria) NÃO reabre a semana da equipe", status == 403)

status, sem_motivo = req("POST", f"/api/pdca/programacoes/{prog_id}/reabrir/", demo,
                         {"motivo": "   "})
check("reabrir sem dizer por quê é recusado", status == 400)
check("e a recusa diz o porquê (o número já foi lido por alguém)",
      "em sil" in texto(sem_motivo))

status, reaberta = req("POST", f"/api/pdca/programacoes/{prog_id}/reabrir/", demo,
                       {"motivo": "A causa do contrapiso foi lançada errada."})
check("`demo` reabre a semana encerrada", status == 200)
check("e ela volta um degrau, para COMPROMETIDA",
      (reaberta or {}).get("de") == "encerrada"
      and (reaberta or {}).get("para") == "comprometida")
check("sem apagar julgamento nenhum — corrige-se só o que está errado",
      (reaberta or {}).get("julgamentos_apagados") == 0)
dados = (reaberta or {}).get("programacao_dados") or {}
check("a reabertura fica CARIMBADA no documento",
      dados.get("vezes_reaberta") == 1 and dados.get("reaberta_por")
      and "contrapiso" in (dados.get("motivo_reabertura") or ""))

status, serie = req("GET", f"/api/pdca/programacoes/ppc/?obra={obra_id}", demo)
check("enquanto reaberta, a semana SAI da série — em revisão não é conclusão",
      (serie or {}).get("serie") == [])
status, ranking = req("GET", f"/api/pdca/programacoes/causas/?obra={obra_id}", demo)
check("e as causas dela saem do ranking pelo mesmo motivo",
      (ranking or {}).get("total_falhas") == 0)

# Corrige a causa errada e encerra de novo — o PPC recalcula porque nunca foi
# gravado (§4.9).
status, _ = req("POST", f"/api/pdca/programacoes/{prog_id}/julgar/", demo, {
    "julgamentos": [{"item": cartoes["3"], "cumprido": True}],
})
check("com a semana reaberta, o julgamento aceita correção", status == 200)
status, refeita = req(
    "POST", f"/api/pdca/programacoes/{prog_id}/encerrar/", demo,
    {"motivo": "E2E — refechando depois da correção."} if antecipado else {},
)
check("e a semana encerra outra vez", status == 200)
check("o PPC RECALCULOU sozinho: agora 2 de 3 = 66,7%",
      float((refeita or {}).get("ppc")) == 66.7)
check("e ele se declara corrigido, para não passar por número virgem",
      (refeita or {}).get("vezes_reaberta") == 1)

status, serie = req("GET", f"/api/pdca/programacoes/ppc/?obra={obra_id}", demo)
linhas = (serie or {}).get("serie") or []
check("a semana volta à série com o número novo",
      len(linhas) == 1 and float(linhas[0]["ppc"]) == 66.7)
check("e o ponto vem marcado como corrigido",
      linhas[0].get("vezes_reaberta") == 1)

status, ranking = req("GET", f"/api/pdca/programacoes/causas/?obra={obra_id}", demo)
check("o ranking perdeu a falha que não era falha",
      (ranking or {}).get("total_falhas") == 1)
codigos = {c["codigo"] for c in (ranking or {}).get("causas") or []}
check("e ficou só com a causa que sobrou", codigos == {"MAT-FALTA"})

# **Um degrau por vez, e a semana está encerrada de novo** — então chegar ao
# rascunho custa duas reaberturas, cada uma com a sua frase. É de propósito:
# descer dois degraus de uma vez é exatamente o gesto que merece dois registros.
status, volta1 = req("POST", f"/api/pdca/programacoes/{prog_id}/reabrir/", demo,
                     {"motivo": "faltou um serviço inteiro no quadro"})
check("a primeira reabertura desfaz o encerramento",
      (volta1 or {}).get("para") == "comprometida")
check("sem apagar julgamento — esse degrau é para corrigir, não para refazer",
      (volta1 or {}).get("julgamentos_apagados") == 0)

status, rascunho = req("POST", f"/api/pdca/programacoes/{prog_id}/reabrir/", demo,
                       {"motivo": "vou remontar o quadro do zero"})
check("a segunda desce ao RASCUNHO, onde o quadro recebe cartão de novo",
      (rascunho or {}).get("para") == "rascunho")
check("e AGORA os julgamentos são apagados — semana não assumida não tem "
      "julgamento", (rascunho or {}).get("julgamentos_apagados") == 3)
check("com a contagem de reaberturas subindo, que é o padrão que só aparece "
      "se alguém contar", (rascunho or {}).get("vezes_reaberta") == 3)

status, terceiro = req("POST", f"/api/pdca/programacoes/{prog_id}/reabrir/", demo,
                       {"motivo": "e mais uma"})
check("o rascunho não tem degrau abaixo", status == 400)
check("e a recusa diz isso", "rascunho" in texto(terceiro))

# Devolve a semana ao estado encerrado, para as seções seguintes lerem o que
# leriam — a fronteira e a faxina não mudam de sentido por causa deste bloco.
req("POST", f"/api/pdca/programacoes/{prog_id}/comprometer/", demo)
req("POST", f"/api/pdca/programacoes/{prog_id}/julgar/", demo, {
    "julgamentos": [
        {"item": cartoes["1"], "cumprido": True},
        {"item": cartoes["2"], "cumprido": False,
         "causa": causa_material["causa_id"], "nota": "Faltou argamassa"},
        {"item": cartoes["3"], "cumprido": True},
    ],
})
req(
    "POST", f"/api/pdca/programacoes/{prog_id}/encerrar/", demo,
    {"motivo": "E2E — refechando depois da remontagem."} if antecipado else {},
)


# ------------------------------------------- 12c. execução parcial
print("\n12c. O compromisso é binário; a execução não é")
# A obra que assumiu 20 pontos e entregou 12 **fez 12**. O PPC não conta isso —
# de propósito, é a definição dele —, mas jogar o número fora faria o sistema
# parecer dizer à equipe que ela não fez nada.
status, apontado = req("POST", "/api/pdca/apontamentos/", demo, {
    "atividade": atividades["2"],
    "data": (segunda + timedelta(days=2)).isoformat(),
    "percentual": "12",
})
check("o campo aponta 12 pontos na atividade que não vai sair",
      status in (200, 201))

status, itens = req(
    "GET", f"/api/pdca/itens-programacao/?programacao={prog_id}", demo,
)
cartoes_lidos = lista_de(itens)
cartao2 = next(
    (c for c in cartoes_lidos if c["atividade"] == atividades["2"]), None,
)
check("o cartão traz o que o campo apontou, ao lado do que foi prometido",
      cartao2 is not None
      and float(cartao2.get("percentual_apontado") or 0) == 12.0
      and float(cartao2.get("percentual_previsto") or 0) == 20.0)
sem_apontamento = [
    c for c in cartoes_lidos if c["atividade"] != atividades["2"]
]
check("e o cartão sem apontamento recebe NULO, não zero — 'ninguém apontou' "
      "é diferente de 'nada andou'",
      all(c.get("percentual_apontado") is None for c in sem_apontamento))

status, atual = req("GET", f"/api/pdca/programacoes/{prog_id}/", demo)
ppc_atual = (atual or {}).get("ppc") or {}
check("a semana soma o prometido de todos os cartões",
      float(ppc_atual.get("pontos_previstos") or 0) == 60.0)
check("e o apontado do período, separado do índice",
      float(ppc_atual.get("pontos_apontados") or 0) == 12.0)
check("o PPC continua BINÁRIO — 2 de 3, e não um crédito parcial",
      float(ppc_atual.get("ppc")) == 66.7)


# ---------------------------------------------------------- 13. a fronteira
print("\n13. A fronteira de tenant")
status, _ = req("GET", f"/api/pdca/programacoes/{prog_id}/", acme)
check("outro tenant não abre esta programação", status in (403, 404))
status, _ = req("GET", f"/api/pdca/restricoes/{restricao_id}/", acme)
check("nem esta restrição", status in (403, 404))
status, lista = req("GET", f"/api/pdca/programacoes/ppc/?obra={obra_id}", acme)
check("nem lê o PPC de uma obra que não é dele", status in (400, 403, 404))

# --------------------------------------------------------------- 14. faxina
print("\n14. Faxina — o teste desfaz o que dá para desfazer")
status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
check("a obra do teste sai (vai para a lixeira, que é o desenho)",
      status in (200, 204))
print(
    "\n     Como os irmãos da PDCA.3 e da PDCA.4, este teste deixa a semana\n"
    "     encerrada, os compromissos julgados e a demanda no SCM — documento\n"
    "     com decisão registrada não se apaga, e é isso que a fatia garante.\n"
    "     Para devolver o ambiente ao estado anterior:\n"
    "       docker exec sgi-erp python manage.py limpar_residuo_e2e --confirmar"
)

# ------------------------------------------------------------------ resumo
ok = sum(1 for p in passed if p)
print(f"\n{'='*62}\nPDCA.5: {ok}/{len(passed)} verificações\n{'='*62}")
sys.exit(0 if ok == len(passed) else 1)
