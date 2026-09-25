"""PDCA.7 — a máquina de verificação: FVS, NC, 5W2H e eficácia, pelo gateway (8090).

Irmão do `pdca5_programacao_test.py`, e existe pelo mesmo motivo: a suíte
unitária chama o serviço direto e empurra o usuário com `force_authenticate`;
aqui cada gesto atravessa login, assinatura RS256, gateway, entitlement de
módulo, permissão de campo e RLS.

O que esta fatia tem de próprio é que ela **fecha um laço**, e um laço só vale se
não houver atalho. Metade das verificações abaixo existe para provar que os
atalhos estão fechados: a ficha não conclui com obrigatória em branco, o desvio
não passa sem explicação, a NC não encerra com o plano concluído mas sem
eficácia verificada, e quem trata não assina a própria eficácia.

Quatro tokens reais, e a divisão é o teste:

  demo     / demo123     -> `engenharia`: aplica a ficha, responde, abre a NC e
                            monta o 5W2H. **Não** verifica a própria eficácia —
                            quem consertou não assina que o conserto funcionou.
  campo    / campo123    -> `campo`: é a persona do 5º instrumento. Responde a
                            ficha e abre NC; não trata e não edita o modelo —
                            afrouxar o critério da FVS no momento em que ela
                            reprova é exatamente o que a separação impede.
  gerente  / gerente123  -> `diretoria`: **verifica a eficácia e encerra**. É o
                            segundo verbo de escrita dela em todo o catálogo, e
                            como o primeiro (atestar medição) é uma assinatura.
  acme     / acme123     -> outro tenant: é a fronteira.

Seed: testes/seeds/seed_demo.py + testes/seeds/seed_demo_data.py

  1. O que existe   -> `status/` declara a máquina, o laço e os tetos novos.
  2. Cenário        -> obra, calendário, plano vigente com uma folha.
  3. A biblioteca   -> nasce **vazia** de propósito; `demo` monta a ficha.
  4. Congelamento   -> apertar o critério do modelo NÃO reescreve a ficha aplicada.
  5. O campo        -> `campo` responde; desvio sem explicação é recusado.
  6. Conclusão      -> obrigatória em branco impede assinar a ficha.
  7. A NC nasce     -> do item reprovado, com endereço, e não duplica.
  8. Seam do LPS    -> NC vira restrição e a atividade SAI do quadro da semana.
  9. O 5W2H         -> plano de ação põe a NC em tratamento.
 10. O laço         -> "ação concluída" NÃO encerra; sem eficácia, encerrar é 400.
 11. Eficácia       -> o "não" devolve ao tratamento; o "sim" libera o encerramento.
 12. Segregação     -> quem trata não verifica; quem aplica não edita o método.
 13. O Act          -> conformidade por domínio e o item que mais reprova.
 14. A fronteira    -> outro tenant não enxerga nada disto.
 15. Faxina         -> o teste desfaz o que dá para desfazer, e declara o resto.

Rodar (stack de pé):  python testes/e2e/pdca7_verificacao_test.py
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

MARCA = "E2E PDCA.7 " + uuid.uuid4().hex[:8]

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


def lista_de(resposta):
    """A API pagina quase tudo; alguns endpoints devolvem lista crua."""
    if isinstance(resposta, list):
        return resposta
    return (resposta or {}).get("results") or []


print(f"\n{'='*62}\nPDCA.7 — a máquina de verificação pelo gateway\n{'='*62}")
print(f"Gateway: {GW}")

try:
    demo = login("demo", "demo123")
    campo = login("campo", "campo123")
    gerente = login("gerente", "gerente123")
    acme = login("acme", "acme123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé? Rodou os dois seeds?")

# --------------------------------------------------------- 1. o que existe
print("\n1. O módulo declara a máquina de verificação e o laço")
status, st = req("GET", "/api/pdca/status/", demo)
check("`demo` lê o status", status == 200)
# **A regra do `pdca5` era "a fatia corrente afirma o número", e ela tinha um
# defeito de fabricação: a fatia corrente deixa de ser corrente.** Este check
# prendia `"PDCA.7"` e passou a reprovar no dia em que a PDCA.8 entrou — no
# roteiro da qualidade, acusando falha no que era progresso da segurança. O que
# importa provar aqui é que o módulo continua declarando **as capacidades desta
# fatia**, e é o que as linhas seguintes fazem.
check("o módulo declara em que fatia está", bool((st or {}).get("fatia")))
recursos = (st or {}).get("recursos", {})
check("modelo, ficha, NC, 5W2H e eficácia estão de pé",
      recursos.get("modelo_verificacao") is True
      and recursos.get("verificacao") is True
      and recursos.get("nao_conformidade") is True
      and recursos.get("plano_acao_5w2h") is True
      and recursos.get("verificacao_eficacia") is True)
check("o seam do Last Planner é declarado VIVO, não prometido",
      recursos.get("nc_gera_restricao") is True)
check("e o que a fatia NÃO faz é declarado, para a tela não oferecer botão morto",
      recursos.get("nc_cria_marcacao_na_prancheta") is False
      and recursos.get("modelos_de_fabrica") is False)
tetos = (st or {}).get("tetos", {})
check("os quatro tetos novos vêm do servidor (o dono decide o número)",
      isinstance(tetos.get("itens_por_modelo_verificacao"), int)
      and isinstance(tetos.get("modelos_por_tenant"), int)
      and isinstance(tetos.get("ncs_abertas_por_obra"), int)
      and isinstance(tetos.get("acoes_por_nc"), int))
check("e NÃO existe meta de conformidade entre eles (§5.6: resultado não é teto)",
      not any("conformidade" in k or "meta" in k for k in tetos))

# ------------------------------------------------------------- 2. o cenário
print("\n2. Obra, calendário e plano vigente com uma folha")
status, obra = req("POST", "/api/obras/", demo, {
    "nome_obra": MARCA, "endereco": "Rua da Conformidade, s/n",
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

hoje = date.today()
segunda = hoje - timedelta(days=hoje.weekday())
status, crono = req("POST", "/api/pdca/cronogramas/", demo, {
    "obra": obra_id, "descricao": "Plano " + MARCA,
    "data_inicio": segunda.isoformat(),
    "calendario": calendario["calendario_id"],
})
if status not in (200, 201):
    fatal(f"cronograma falhou (HTTP {status}: {crono})")
crono_id = crono["cronograma_id"]

status, ativ = req("POST", "/api/pdca/atividades/", demo, {
    "cronograma": crono_id, "codigo": "1", "nome": "Alvenaria do 4º",
    "duracao_dias": 5, "profundidade": 1,
})
if status not in (200, 201):
    fatal(f"atividade falhou (HTTP {status}: {ativ})")
ativ_id = ativ["atividade_id"]

status, _ = req("POST", f"/api/pdca/cronogramas/{crono_id}/publicar/", demo)
check("o plano publica (o quadro da semana precisa dele vigente)",
      status in (200, 201))

# --------------------------------------------------------- 3. a biblioteca
print("\n3. A biblioteca de fichas — e ela nasce vazia de propósito")
status, modelo = req("POST", "/api/pdca/modelos-verificacao/", demo, {
    "codigo": "FVS-" + uuid.uuid4().hex[:6].upper(),
    "nome": "FVS — Alvenaria " + MARCA,
    "dominio": "qualidade",
    "descricao": "Após a cura, antes do revestimento",
})
if status not in (200, 201) or not modelo:
    fatal(f"modelo falhou (HTTP {status}: {modelo}) — a linha nasceu sem tenant?")
modelo_id = modelo["modelo_id"]
check("`demo` monta o modelo, e ele nasce com tenant (senão a RLS recusaria)",
      status == 201)
check("nasce ativo e nunca aplicado", modelo.get("ativo") is True
      and modelo.get("aplicacoes") == 0)

status, aplicar_vazio = req("POST", "/api/pdca/verificacoes/aplicar/", demo, {
    "modelo": modelo_id, "obra": obra_id, "data": hoje.isoformat(),
})
check("ficha sem pergunta NÃO se aplica (concluiria 100% sem ninguém olhar)",
      aplicar_vazio is not None and status == 400
      and "nenhuma pergunta" in texto(aplicar_vazio))

CRITERIO_ORIGINAL = "Desvio até 3 mm em 2 m, conferido com régua"

itens_modelo = []
for ordem, (t, c, obrig) in enumerate([
    ("Prumo da parede", CRITERIO_ORIGINAL, True),
    ("Espessura da junta", "10 mm ± 2 mm", True),
    ("Limpeza da frente", "", False),
    ("Amarração da alvenaria", "Uma barra a cada 2 fiadas", False),
    # O quinto existe para o §7 provar o que a correção de 16/09 fez: duas
    # reprovas da MESMA ficha com pesos diferentes.
    ("Encunhamento", "Após 7 dias do levante", False),
], start=1):
    status, item = req("POST", "/api/pdca/itens-modelo-verificacao/", demo, {
        "modelo": modelo_id, "ordem": ordem, "texto": t, "criterio": c,
        "obrigatorio": obrig,
    })
    if status not in (200, 201):
        fatal(f"item {ordem} do modelo falhou (HTTP {status}: {item})")
    itens_modelo.append(item["item_modelo_id"])
check("as cinco perguntas entram com critério objetivo", len(itens_modelo) == 5)

# ------------------------------------------------------- 4. o congelamento
print("\n4. A ficha guarda a pergunta que respondeu")
status, ficha = req("POST", "/api/pdca/verificacoes/aplicar/", demo, {
    "modelo": modelo_id, "obra": obra_id, "data": hoje.isoformat(),
    "atividade": ativ_id, "inspetor": "Téc. E2E",
})
if status not in (200, 201) or not ficha:
    fatal(f"aplicar falhou (HTTP {status}: {ficha})")
ficha_id = ficha["verificacao_id"]
check("a ficha nasce da aplicação do modelo", status == 201)
check("e nasce SEM apuração — nunca 0% (régua de dado honesto)",
      (ficha.get("resultado") or {}).get("conformidade") is None)

status, itens = req("GET", f"/api/pdca/itens-verificacao/?verificacao={ficha_id}"
                    "&page_size=100", demo)
linhas = sorted(lista_de(itens), key=lambda i: i["ordem"])
check("as cinco perguntas foram COPIADAS para dentro da ficha", len(linhas) == 5)
check("e todas nascem pendentes, nunca reprovadas",
      all(i["resultado"] == "pendente" for i in linhas))

# **O teste mais importante da fatia.** A empresa aperta o critério no ano
# seguinte, e faz bem; a inspeção de ontem não pode passar a afirmar que
# conferiu o número novo.
req("PATCH", f"/api/pdca/itens-modelo-verificacao/{itens_modelo[0]}/", demo, {
    "criterio": "Desvio até 2 mm em 2 m",
})
status, itens_depois = req(
    "GET", f"/api/pdca/itens-verificacao/?verificacao={ficha_id}&page_size=100", demo,
)
congelado = sorted(lista_de(itens_depois), key=lambda i: i["ordem"])[0]
check("apertar o critério do modelo NÃO reescreve a ficha já aplicada",
      congelado["criterio"] == CRITERIO_ORIGINAL)
check("e o vínculo com a pergunta de origem continua de pé",
      congelado["item_modelo"] == itens_modelo[0])
status, modelo_agora = req(
    "GET", f"/api/pdca/modelos-verificacao/{modelo_id}/", demo,
)
apertado = [i for i in (modelo_agora or {}).get("itens") or []
            if i["item_modelo_id"] == itens_modelo[0]]
check("— e o modelo, esse sim, passou a perguntar o critério novo "
      "(é a contraprova: o congelamento não é o modelo ter ficado imutável)",
      bool(apertado) and apertado[0]["criterio"] == "Desvio até 2 mm em 2 m")

# ------------------------------------------------------------- 5. o campo
print("\n5. O campo responde — e o desvio exige explicação")
# ordem 1 e 2 são **obrigatórias**; 3 e 4, opcionais. A 2 fica de propósito sem
# resposta até a §6: é ela que prova a recusa de concluir com o essencial em
# branco, e respondê-la aqui tornaria aquela checagem impossível de falhar.
id0, id1, id2, id3, id4 = (i["item_verificacao_id"] for i in linhas)

status, recusa = req("PATCH", f"/api/pdca/itens-verificacao/{id0}/", campo, {
    "resultado": "nao_conforme", "observacao": "",
})
check("`campo` responde a ficha (é a persona do 5º instrumento)",
      status in (200, 400))
check("não conforme SEM dizer o quê é recusado — 400, não 500",
      status == 400)

status, recusa_na = req("PATCH", f"/api/pdca/itens-verificacao/{id2}/", campo, {
    "resultado": "nao_aplicavel", "observacao": "",
})
check("e 'não aplicável' sem motivo também — é a porta pela qual a ficha "
      "inteira passa sem ninguém verificar nada",
      recusa_na is not None and status == 400)

status, sem_peso = req("PATCH", f"/api/pdca/itens-verificacao/{id0}/", campo, {
    "resultado": "nao_conforme", "observacao": "Desvio de 12 mm no eixo C",
})
check("e reprovar sem dizer **quanto pesa** também é recusado — a gravidade é "
      "do defeito, e perguntá-la uma vez no fim faria um desalinhamento de "
      "porta pesar igual à falta de uma maçaneta",
      status == 400 and "pesa" in texto(sem_peso))

status, respondido = req("PATCH", f"/api/pdca/itens-verificacao/{id0}/", campo, {
    "resultado": "nao_conforme", "observacao": "Desvio de 12 mm no eixo C",
    "gravidade": "maior",
})
check("com a explicação e o peso, a resposta grava", status == 200)
check("e o peso volta resolvido, com rótulo",
      (respondido or {}).get("gravidade") == "maior"
      and bool((respondido or {}).get("gravidade_rotulo")))
check("e o PATCH devolve o item JÁ respondido (a tela do campo não pode "
      "mostrar a pergunta pendente logo depois de respondê-la)",
      (respondido or {}).get("resultado") == "nao_conforme"
      and bool((respondido or {}).get("respondido_em")))

status, _ = req("PATCH", f"/api/pdca/itens-verificacao/{id3}/", campo, {
    "resultado": "conforme",
})
check("conforme sai num toque, sem observação", status == 200)

# --------------------------------------------------------- 6. a conclusão
print("\n6. Concluir é assinar — e não se assina com o essencial em branco")
status, negado = req("POST", f"/api/pdca/verificacoes/{ficha_id}/concluir/", campo)
check("ficha com obrigatória pendente NÃO conclui", status == 400)
check("e a recusa NOMEIA o item que falta, em vez de dizer 'erro de validação'",
      "obrigatórios 2" in texto(negado))

status, _ = req("PATCH", f"/api/pdca/itens-verificacao/{id1}/", campo, {
    "resultado": "conforme",
})
status, _ = req("PATCH", f"/api/pdca/itens-verificacao/{id2}/", campo, {
    "resultado": "nao_aplicavel", "observacao": "Frente ainda não liberada",
})
# **O segundo reprovado, e com peso diferente do primeiro.** É a prova de que a
# gravidade é do item: o desalinhamento que se corrige na frente e o defeito que
# impede aceitar o serviço saem da mesma ficha com rótulos diferentes.
status, _ = req("PATCH", f"/api/pdca/itens-verificacao/{id4}/", campo, {
    "resultado": "nao_conforme", "observacao": "Encunhamento faltando num pano",
    "gravidade": "menor",
})
status, conclusao = req("POST", f"/api/pdca/verificacoes/{ficha_id}/concluir/", campo)
check("com as obrigatórias respondidas, a ficha fecha", status == 200)
resultado = (conclusao or {}).get("resultado") or {}
# 2 conformes e 2 não conformes = 50% sobre **4 julgados**. Se o "não aplicável"
# entrasse contado como acerto seria 60%, e como erro, 40% — os dois errados, e
# os dois plausíveis. É por isso que este número vale a checagem.
check("2 conformes de 4 julgados = 50% — o 'não aplicável' fica FORA do "
      "denominador (não é acerto nem erro)",
      str(resultado.get("conformidade")) == "50.00")
check("e o N/A aparece contado à parte, em vez de sumir",
      resultado.get("nao_aplicaveis") == 1)
reprovados = (conclusao or {}).get("reprovados_sem_nc") or []
check("a conclusão devolve os dois reprovados que ainda não viraram NC",
      len(reprovados) == 2)
check("**e cada um com o SEU peso** — a conclusão mostra o que vai abrir, em "
      "vez de perguntar um peso só para todos",
      sorted(l.get("gravidade") for l in reprovados) == ["maior", "menor"])
check("com o rótulo resolvido, para a tela não traduzir código",
      all(l.get("gravidade_rotulo") for l in reprovados))

status, depois = req("PATCH", f"/api/pdca/itens-verificacao/{id1}/", campo, {
    "resultado": "nao_conforme", "observacao": "tentando reescrever",
})
check("ficha concluída NÃO recebe mais resposta (ela virou prova)",
      status == 400)

# --------------------------------------------------------------- 7. a NC
print("\n7. A não-conformidade nasce do item reprovado")
# **Sem corpo.** Cada NC nasce com a gravidade do seu item, respondida por quem
# o reprovou — e é por isso que este verbo não escolhe peso nenhum.
status, abertas = req("POST", f"/api/pdca/verificacoes/{ficha_id}/abrir-ncs/", demo)
check("`demo` abre as NCs dos reprovados", status == 201
      and (abertas or {}).get("abertas") == 2)
ids_ncs = (abertas or {}).get("ncs") or []
if len(ids_ncs) != 2:
    fatal("as NCs não foram criadas — sem elas o resto do laço não existe")

# **O coração da correção de 16/09/2026**, provado no stack vivo: duas NCs da
# mesma ficha, com pesos diferentes. Antes, um único seletor na conclusão
# carimbava o mesmo rótulo nas duas — e o painel dizia "2 maiores" sobre um
# desalinhamento e uma falta.
pesos = sorted(
    (req("GET", f"/api/pdca/ncs/{i}/", demo)[1] or {}).get("gravidade")
    for i in ids_ncs
)
check("**e cada uma nasceu com o peso do seu item**, não com um peso só para "
      "as duas", pesos == ["maior", "menor"])

nc_id = next(
    i for i in ids_ncs
    if (req("GET", f"/api/pdca/ncs/{i}/", demo)[1] or {}).get("gravidade") == "maior"
)

status, de_novo = req("POST", f"/api/pdca/verificacoes/{ficha_id}/abrir-ncs/", demo)
check("clicar duas vezes não duplica (o botão fica na tela)",
      (de_novo or {}).get("abertas") == 0)

status, nc = req("GET", f"/api/pdca/ncs/{nc_id}/", demo)
check("a NC leva o endereço da ficha junto", nc is not None
      and nc.get("atividade") == ativ_id)
check("**e o peso que o técnico deu àquele item**, não um escolhido para todos",
      (nc or {}).get("gravidade") == "maior")
check("e a descrição junta a pergunta congelada com a observação do técnico",
      "prumo da parede" in texto(nc) and "12 mm" in texto(nc))
check("o seam da ficha é visível na NC (de onde o defeito veio)",
      (nc or {}).get("verificacao") == ficha_id)
check("e o estado diz o que falta a seguir, resolvido pelo SERVIDOR",
      ((nc or {}).get("estado") or {}).get("falta") == "montar o plano de ação")

# ------------------------------------------------------- 8. o seam do LPS
print("\n8. A gravidade tem dente: a NC para o serviço no quadro da semana")
status, prog = req("POST", "/api/pdca/programacoes/abrir/", demo, {
    "obra": obra_id, "semana": segunda.isoformat(),
})
if status not in (200, 201):
    fatal(f"não consegui abrir a semana (HTTP {status}: {prog})")
prog_id = prog["programacao_id"]

status, cands = req("GET", f"/api/pdca/programacoes/{prog_id}/candidatos/", demo)
antes = [c for c in lista_de(cands) if c["atividade"] == ativ_id]
check("antes da trava, a atividade é candidata da semana", len(antes) == 1)
check("e o quadro JÁ mostra os defeitos abertos nela (integração visível)",
      bool(antes) and antes[0].get("ncs_abertas") == 2)

status, gerada = req("POST", f"/api/pdca/ncs/{nc_id}/gerar-restricao/", demo, {})
check("a NC vira restrição — 'não é aceito assim' deixa de ser adjetivo",
      status == 201 and bool((gerada or {}).get("restricao")))
restricao_id = (gerada or {}).get("restricao")

status, de_novo = req("POST", f"/api/pdca/ncs/{nc_id}/gerar-restricao/", demo, {})
check("e gerar duas vezes devolve a mesma (régua do gerar-demanda)",
      (de_novo or {}).get("restricao") == restricao_id)

status, puxar = req("POST", "/api/pdca/itens-programacao/", demo, {
    "programacao": prog_id, "atividade": ativ_id, "ordem": 1,
})
check("com a trava aberta, a atividade NÃO entra no quadro da semana",
      status == 400)

# --------------------------------------------------------------- 9. o 5W2H
print("\n9. O plano de ação põe a NC em tratamento")
status, plano = req("POST", "/api/pdca/planos-acao/", demo, {
    "nao_conformidade": nc_id, "tipo": "corretiva",
    "o_que": "Demolir e reexecutar o trecho fora de prumo",
    "por_que": "Gabarito conferido só no fim da fiada",
    "quem": "Empreiteira do E2E", "quando": (hoje + timedelta(days=7)).isoformat(),
    "como": "Gabarito a cada 3 fiadas", "quanto": "1500.00",
})
check("`demo` monta o 5W2H", status == 201)
plano_id = (plano or {}).get("plano_id")
status, nc = req("GET", f"/api/pdca/ncs/{nc_id}/", demo)
check("e a NC passa a 'em tratamento' — o degrau que separa 'ninguém pegou' "
      "de 'está sendo consertado' na fila de decisão",
      (nc or {}).get("status") == "em_tratamento")

# --------------------------------------------------------------- 10. o laço
print("\n10. 'Ação concluída' NÃO encerra a não-conformidade")
status, _ = req("POST", f"/api/pdca/planos-acao/{plano_id}/concluir/", demo)
check("a ação é marcada como executada", status == 200)
status, nc = req("GET", f"/api/pdca/ncs/{nc_id}/", demo)
check("a NC continua aberta — é quem consertou dizendo que consertou",
      (nc or {}).get("status") == "em_tratamento")
check("e o estado agora pede a eficácia",
      ((nc or {}).get("estado") or {}).get("falta") == "verificar a eficácia")

status, recusa = req("POST", f"/api/pdca/ncs/{nc_id}/encerrar/", gerente, {})
check("encerrar SEM eficácia verificada é recusado — 400, não 500", status == 400)
check("e a recusa diz o porquê, não 'erro de validação'",
      "eficácia" in texto(recusa))

# ----------------------------------------------------------- 11. a eficácia
print("\n11. O 'não' devolve ao tratamento; o 'sim' libera o encerramento")
status, nao_pegou = req("POST", f"/api/pdca/ncs/{nc_id}/eficacia/", gerente, {
    "data": hoje.isoformat(), "eficaz": False,
    "evidencia": "A parede continua fora de prumo no mesmo trecho.",
})
check("`gerente` registra que o conserto NÃO pegou", status == 201)
check("e isso não encerra nada",
      (nao_pegou or {}).get("pode_encerrar") is False)

status, recusa2 = req("POST", f"/api/pdca/ncs/{nc_id}/encerrar/", gerente, {})
check("encerrar depois de uma eficácia negativa continua recusado", status == 400)

status, sem_evidencia = req("POST", f"/api/pdca/ncs/{nc_id}/eficacia/", gerente, {
    "data": hoje.isoformat(), "eficaz": True, "evidencia": "   ",
})
check("um 'sim' sem história é recusado — isso seria um carimbo",
      status == 400)

status, pegou = req("POST", f"/api/pdca/ncs/{nc_id}/eficacia/", gerente, {
    "data": hoje.isoformat(), "eficaz": True,
    "evidencia": "Trecho refeito e conferido com régua: 2 mm.",
})
check("a segunda verificação diz que pegou", status == 201
      and (pegou or {}).get("pode_encerrar") is True)

status, fechada = req("POST", f"/api/pdca/ncs/{nc_id}/encerrar/", gerente,
                      {"nota": "Conferido em obra."})
check("e agora a NC encerra", status == 200
      and (fechada or {}).get("status") == "encerrada")
check("as DUAS verificações ficam no histórico — a sequência é a história "
      "honesta de quantas tentativas o conserto levou",
      len((fechada or {}).get("eficacias") or []) == 2)

# -------------------------------------------------------- 12. a segregação
print("\n12. Quem trata não verifica; quem aplica não edita o método")
status, nc2 = req("POST", "/api/pdca/ncs/", demo, {
    "obra": obra_id, "descricao": "Trinca na viga " + MARCA, "gravidade": "menor",
})
check("`demo` abre uma NC avulsa (o encarregado vê a trinca de passagem)",
      status == 201)
nc2_id = (nc2 or {}).get("nc_id")

status, negado = req("POST", f"/api/pdca/ncs/{nc2_id}/eficacia/", demo, {
    "data": hoje.isoformat(), "eficaz": True, "evidencia": "Eu mesmo conferi.",
})
check("`demo` (engenharia) NÃO verifica a própria eficácia — 403", status == 403)
status, negado = req("POST", f"/api/pdca/ncs/{nc2_id}/encerrar/", demo, {})
check("e não encerra — é a segregação inteira da fatia", status == 403)

status, negado = req("PATCH", f"/api/pdca/modelos-verificacao/{modelo_id}/",
                     campo, {"nome": "afrouxando o critério"})
check("`campo` NÃO edita o método da empresa — afrouxar a FVS no momento em "
      "que ela reprova é exatamente o que a separação impede",
      status == 403)

status, negado = req("POST", "/api/pdca/planos-acao/", campo, {
    "nao_conformidade": nc2_id, "o_que": "qualquer coisa",
})
check("e `campo` não monta plano de ação (decidir é de quem responde pela obra)",
      status == 403)

status, negado = req("DELETE", f"/api/pdca/modelos-verificacao/{modelo_id}/", demo)
check("modelo já aplicado NÃO se apaga — as fichas perderiam o nome do que "
      "responderam",
      status == 400)

# ------------------------------------------------------------- 13. o "Act"
print("\n13. O Act da qualidade — conformidade e o que mais reprova")
status, painel = req("GET", f"/api/pdca/ncs/painel/?obra={obra_id}", demo)
check("o painel responde pela obra", status == 200)
check("conta só ficha CONCLUÍDA (inspeção pela metade faria o índice oscilar "
      "ao sabor de quem está caminhando)",
      (painel or {}).get("fichas_concluidas") == 1)
ranking = (painel or {}).get("itens_que_mais_reprovam") or []
check("e ranqueia a pergunta que mais reprova — é ela que aponta o PROCESSO "
      "a corrigir, não o serviço a refazer",
      bool(ranking) and any(l["item_modelo"] == itens_modelo[0] for l in ranking))
# **A reprova tratada CONTINUA no ranking** — se sumisse, a pergunta que mais dá
# trabalho desapareceria justamente quando a equipe está funcionando.
por_modelo = {l["item_modelo"]: l for l in ranking}
tratada = por_modelo.get(itens_modelo[0]) or {}
check("a reprova já encerrada continua contada (o número é história do "
      "processo, não a fila de agora)", tratada.get("reprovas") == 1)
# **E cada linha diz a situação de HOJE.** Era o que faltava: "Prumo da parede
# — 1" se lia como problema em aberto mesmo já consertado.
check("**e a linha diz que ela JÁ foi resolvida**, em vez de parecer que "
      "continua em não conformidade",
      tratada.get("encerradas") == 1 and tratada.get("em_aberto") == 0)
check("as três situações somam o total — a barra da tela é a reprova inteira, "
      "partida; se não somassem, ela mentiria pela largura",
      all(l["em_aberto"] + l["encerradas"] + l["sem_nc"] == l["reprovas"]
          for l in ranking))
check("o laço fechado aparece em número", (painel or {}).get("ncs_encerradas") == 1)
# **E o painel por gravidade deixou de mentir.** Era esta tabela que o dono
# olhou: com o peso escolhido uma vez na conclusão, ela dizia "N maiores" sobre
# defeitos de tamanhos diferentes. Agora cada linha conta o que de fato tem
# aquele peso — aqui, uma `maior` encerrada e uma `menor` ainda aberta.
por_gravidade = {
    l["gravidade"]: l for l in (painel or {}).get("ncs_por_gravidade") or []
}
check("o painel por gravidade separa os degraus em vez de somar tudo num só",
      por_gravidade.get("maior", {}).get("encerradas") == 1
      and por_gravidade.get("menor", {}).get("abertas") >= 1)

status, fila = req("GET", f"/api/pdca/ncs/fila/?obra={obra_id}", demo)
check("a fila de decisão separa o que ninguém pegou", status == 200
      and any(l["nc"] == nc2_id for l in (fila or {}).get("ncs_sem_plano") or []))
check("e a NC encerrada saiu da fila",
      not any(l["nc"] == nc_id for l in (fila or {}).get("ncs_sem_plano") or []))

status, ppc_gerente = req("GET", f"/api/pdca/ncs/painel/?obra={obra_id}", gerente)
check("`gerente` lê o painel (o indicador é de direção)", ppc_gerente is not None
      and status == 200)

# --------------------------------------------------------- 14. a fronteira
print("\n14. O tenant vizinho não enxerga nada disto")
status, _ = req("GET", f"/api/pdca/verificacoes/{ficha_id}/", acme)
check("`acme` não abre a ficha desta obra", status in (403, 404))
status, _ = req("GET", f"/api/pdca/ncs/{nc_id}/", acme)
check("nem a não-conformidade", status in (403, 404))
status, corpo = req("GET", f"/api/pdca/ncs/fila/?obra={obra_id}", acme)
check("nem a fila de decisão dela", status in (400, 403, 404))
status, modelos_acme = req("GET", "/api/pdca/modelos-verificacao/", acme)
check("e a biblioteca dele não traz o modelo desta empresa",
      status in (403, 404)
      or not any(m["modelo_id"] == modelo_id for m in lista_de(modelos_acme)))

# ------------------------------------------------------------- 15. a faxina
print("\n15. O que este teste deixa no ambiente")
# A obra vai para a LIXEIRA, e com ela nada mais desce: contrato, medição, NC e
# ficha sobrevivem à lápide (é o que o D131 ensinou na PDCA.3). Por isso o teste
# **declara** o que deixa, em vez de marcar a faxina como feita.
status, _ = req("DELETE", f"/api/obras/{obra_id}/", demo)
check("a obra do teste vai para a lixeira", status in (200, 204))
print(f"     Deixa no tenant `demo`: 1 modelo de verificação, 1 ficha,")
print(f"     2 NCs, 1 plano de ação, 2 verificações de eficácia, 1 restrição")
print(f"     e 1 programação — todos marcados com '{MARCA}' na obra.")
print("     Limpeza: python manage.py limpar_residuo_e2e")

# ------------------------------------------------------------------ resumo
ok = sum(1 for p in passed if p)
print(f"\n{'='*62}")
print(f"PDCA.7: {ok}/{len(passed)} checagens")
print(f"{'='*62}\n")
sys.exit(0 if ok == len(passed) else 1)
