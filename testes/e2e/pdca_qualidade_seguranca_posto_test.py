"""PDCA — os postos da qualidade e da segurança (B8, B9) pelo gateway, e o D194.

Irmão do [pdca_medicao_posto_test.py](pdca_medicao_posto_test.py). A suíte do
Django chama o serviço e empurra o usuário com `force_authenticate`; aqui cada
leitura atravessa login, assinatura RS256, gateway, entitlement, permissão e
RLS — e o D194, fechado pela fase 4: o token do admin não leva lista nenhuma,
cabe folgado em qualquer borda, e a tela recebe a lista exata pelo `/auth/me/`.

Tokens reais, e a divisão é o teste:

  admin    / admin123    -> admin do tenant: o token que estourava os 8 KB.
  demo     / demo123     -> abre o defeito e monta o plano — e NÃO assina a
                            eficácia. Tem `engenharia`, que classifica ocorrência.
  campo    / campo123    -> o canteiro: registra a ocorrência e NÃO a classifica
                            (quem é medido não classifica a própria medida).
  gerente  / gerente123  -> `diretoria`: assina a eficácia e encerra.
  acme     / acme123     -> outro tenant, sem o módulo: para no entitlement.

  1. O D194         -> token sem lista e pequeno; a lista exata vem do `/auth/me/`.
  2. O que existe   -> `status/` declara os dois postos.
  3. A qualidade    -> a fila do posto é a do dia recortada; o laço inteiro
                       (sem plano -> executado -> eficácia -> encerrada) anda
                       pela fila, e a eficácia é de outra pessoa.
  4. A segurança    -> a data no futuro é recusada PELA PORTA (D203); quem
                       registra não classifica; as taxas voltam nulas com frase.
  5. O diálogo      -> abre, colhe a lista, encerra.
  6. As frases      -> nenhuma cita número de fatia.
  7. A fronteira    -> outro tenant não enxerga nada disto.

Tudo que o roteiro cria vai para a lixeira no fim: exercitar o posto não pode
deixar rastro no tenant de demonstração.

Rodar (stack de pé):  python testes/e2e/pdca_qualidade_seguranca_posto_test.py
"""
import base64
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

from _segundo_fator import completar_login
from datetime import datetime, timedelta
from _sessao import access_do_bff, cabecalhos, da_resposta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")
#: Janela de uma linha de cabeçalho que a borda tem hoje — o contorno do D194
#: (`large_client_header_buffers 8 32k` no gateway, `--limit-request-field_size
#: 32768` no gunicorn). Janela de protocolo de terceiro, não teto do produto.
JANELA_DA_BORDA = 32768

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

passed = []
lixo: list[tuple[str, str]] = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def fatal(msg):
    print(f"\n  !! {msg}")
    limpar()
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


def claims(token):
    carga = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))


def limpar():
    for caminho, token in reversed(lixo):
        req("DELETE", caminho, token)
    lixo.clear()


def faixa(fila, codigo):
    return next((f for f in fila["faixas"] if f["codigo"] == codigo), None)


def ids_da_faixa(fila, codigo):
    f = faixa(fila, codigo)
    return {linha["id"] for linha in f["linhas"]} if f else set()


print(f"\n{'='*62}\nPDCA — qualidade e segurança pelo gateway\n{'='*62}")
print(f"Gateway: {GW}")

try:
    admin = login("admin", "admin123")
    demo = login("demo", "demo123")
    gerente = login("gerente", "gerente123")
    campo = login("campo", "campo123")
    acme = login("acme", "acme123")
except Exception as e:
    fatal(f"login falhou ({e}). O stack está de pé? Rodou os seeds?")

codigo, obras = req("GET", "/api/obras/", demo)
lista_obras = obras if isinstance(obras, list) else (obras or {}).get("results", [])
if codigo != 200 or not lista_obras:
    fatal(f"sem obra no tenant demo ({codigo})")
OBRA = lista_obras[0]["obra_id"]
print(f"Obra: {OBRA} — {lista_obras[0].get('nome_obra')}")

# ---------------------------------------------------------------------------
print("\n1. D194 — token sem lista; a lista exata vem do /auth/me/")
# ---------------------------------------------------------------------------
# BFF (fase 5): o roteiro tem o cookie da sessão; o token é o que o gateway injeta.
token_admin = access_do_bff(admin) or ""
linha_admin = len("Authorization: Bearer ") + len(token_admin)
check(f"a linha Authorization do admin tem {linha_admin} B, abaixo de {JANELA_DA_BORDA}",
      token_admin and linha_admin < JANELA_DA_BORDA)
check("o token do admin não leva lista de permissões (fase 4)",
      token_admin and "permissions" not in claims(token_admin))
codigo, corpo = req("GET", f"/api/pdca/qualidade/?obra={OBRA}", admin)
check("o admin abre o posto da qualidade (200)", codigo == 200)
check("e nenhum bloco vem negado", corpo is not None and corpo.get("sem_permissao") == [])
codigo, _ = req("GET", f"/api/pdca/ncs/?obra={OBRA}", admin)
check("e passa no portão por permissão (ncs/ → 200)", codigo == 200)
codigo, me = req("GET", "/auth/me/", admin)
perms_admin = (me or {}).get("permissions", [])
check(f"`/auth/me/` dá à tela a lista exata ({len(perms_admin)} códigos), sem curinga",
      codigo == 200 and "pdca.nc.view" in perms_admin and not any("*" in p for p in perms_admin))

# ---------------------------------------------------------------------------
print("\n2. O que o módulo declara")
# ---------------------------------------------------------------------------
codigo, status = req("GET", "/api/pdca/status/", demo)
check("declara 'posto_da_qualidade'", status["recursos"].get("posto_da_qualidade") is True)
check("declara 'posto_da_seguranca'", status["recursos"].get("posto_da_seguranca") is True)

# ---------------------------------------------------------------------------
print("\n3. A qualidade — o laço inteiro, andando pela fila")
# ---------------------------------------------------------------------------
codigo, nc = req("POST", "/api/pdca/ncs/", demo, {
    "obra": OBRA, "gravidade": "maior",
    "descricao": "E2E F.5 — parede do banheiro fora de prumo",
})
if codigo != 201:
    fatal(f"abrir NC respondeu {codigo}: {nc}")
NC = nc["nc_id"]
lixo.append((f"/api/pdca/ncs/{NC}/", admin))
check("o defeito nasce aberto, dizendo o que falta",
      nc["status"] == "aberta" and nc["estado"]["falta"] == "montar o plano de ação")

codigo, posto = req("GET", f"/api/pdca/qualidade/?obra={OBRA}", demo)
check("a fila do posto põe o defeito em 'sem plano'", NC in ids_da_faixa(posto["fila"], "ncs_sem_plano"))
codigo, hoje = req("GET", f"/api/pdca/hoje/?obra={OBRA}&mudancas=0", demo)
do_dia = [f["codigo"] for f in hoje["fila"]["faixas"] if f["origem"] == "qualidade"]
check("e é a fila do dia recortada — as mesmas faixas, na mesma ordem",
      [f["codigo"] for f in posto["fila"]["faixas"]] == do_dia)
check("o painel vem ao lado, contando o defeito aberto",
      posto["painel"] is not None and posto["painel"]["ncs_abertas"] >= 1)

codigo, plano = req("POST", "/api/pdca/planos-acao/", demo, {
    "nao_conformidade": NC, "tipo": "corretiva",
    "o_que": "Demolir e refazer a fiada", "quem": "Equipe da alvenaria",
    "quando": (datetime.now() + timedelta(days=3)).date().isoformat(),
})
check("o plano de ação nasce (201)", codigo == 201)
codigo, posto = req("GET", f"/api/pdca/qualidade/?obra={OBRA}", demo)
check("com plano, o defeito sai de 'sem plano'", NC not in ids_da_faixa(posto["fila"], "ncs_sem_plano"))

codigo, _ = req("POST", f"/api/pdca/planos-acao/{plano['plano_id']}/concluir/", demo, {})
check("executar a ação (200)", codigo == 200)
codigo, posto = req("GET", f"/api/pdca/qualidade/?obra={OBRA}", demo)
check("executado, ele entra em 'conserto por conferir'",
      NC in ids_da_faixa(posto["fila"], "ncs_esperando_eficacia"))
codigo, nc = req("GET", f"/api/pdca/ncs/{NC}/", demo)
check("e executar NÃO encerra — o servidor diz que falta a eficácia",
      nc["status"] != "encerrada" and nc["estado"]["falta"] == "verificar a eficácia"
      and nc["estado"]["pode_encerrar"] is False)

eficacia = {"data": datetime.now().date().isoformat(), "eficaz": True,
            "evidencia": "Prumo conferido com nível laser nos quatro cantos"}
codigo, _ = req("POST", f"/api/pdca/ncs/{NC}/eficacia/", demo, eficacia)
check("quem montou o plano NÃO assina a eficácia (403)", codigo == 403)
codigo, _ = req("POST", f"/api/pdca/ncs/{NC}/eficacia/", gerente, eficacia)
check("a diretoria assina a eficácia (201)", codigo == 201)
codigo, nc = req("POST", f"/api/pdca/ncs/{NC}/encerrar/", gerente, {"nota": "E2E"})
check("e encerra (200, encerrada)", codigo == 200 and nc["status"] == "encerrada")
codigo, posto = req("GET", f"/api/pdca/qualidade/?obra={OBRA}", demo)
check("encerrado, some de todas as faixas do laço", all(
    NC not in ids_da_faixa(posto["fila"], c)
    for c in ("ncs_sem_plano", "ncs_esperando_eficacia")
))

# ---------------------------------------------------------------------------
print("\n4. A segurança — a porta, a segregação e o número que não se inventa")
# ---------------------------------------------------------------------------
amanha = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
codigo, corpo = req("POST", "/api/pdca/ocorrencias/", demo, {
    "obra": OBRA, "tipo": "quase_acidente", "ocorrido_em": amanha,
    "descricao": "E2E F.5 — datado de amanhã por engano",
})
check("D203: ocorrência no futuro é recusada PELA PORTA (400)", codigo == 400)
check("e a recusa tem frase", "futuro" in json.dumps(corpo, ensure_ascii=False))

agora = (datetime.now() - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M")
codigo, oc = req("POST", "/api/pdca/ocorrencias/", campo, {
    "obra": OBRA, "tipo": "quase_acidente", "ocorrido_em": agora,
    "descricao": "E2E F.5 — martelo caiu do andaime sem atingir ninguém",
})
if codigo != 201:
    fatal(f"registrar ocorrência respondeu {codigo}: {oc}")
OC = oc["ocorrencia_id"]
lixo.append((f"/api/pdca/ocorrencias/{OC}/", admin))
check("a ocorrência nasce sem classificação", oc["classificacao"] == "pendente")
check("quase-acidente não exige CAT, e o servidor diz", oc["prazo_cat"]["exige"] is False)

codigo, posto = req("GET", f"/api/pdca/seguranca/?obra={OBRA}", demo)
check("registrada pelo canteiro, ela aparece no posto do escritório 'por classificar'",
      OC in ids_da_faixa(posto["fila"], "ocorrencias_sem_classificacao"))
ind = posto["indicadores"]
check("taxa de frequência e de gravidade voltam NULAS",
      ind["taxa_frequencia"] is None and ind["taxa_gravidade"] is None)
check("com a frase no lugar do número", bool(ind["taxas_indisponiveis_porque"]))

codigo, _ = req("POST", f"/api/pdca/ocorrencias/{OC}/classificar/", campo,
                {"classificacao": "sem_afastamento"})
check("o canteiro, que registrou, NÃO classifica (403)", codigo == 403)
codigo, oc = req("POST", f"/api/pdca/ocorrencias/{OC}/classificar/", demo,
                 {"classificacao": "sem_afastamento"})
check("quem classifica, classifica (200)", codigo == 200 and oc["classificacao"] == "sem_afastamento")

codigo, inv = req("POST", f"/api/pdca/ocorrencias/{OC}/investigar/", admin, {})
check("investigar abre um defeito no laço da qualidade (201)", codigo == 201 and inv.get("nc"))
if inv and inv.get("nc"):
    lixo.append((f"/api/pdca/ncs/{inv['nc']}/", admin))
codigo, oc = req("POST", f"/api/pdca/ocorrencias/{OC}/encerrar/", admin, {"nota": "E2E"})
check("classificada e sem frente interditada, encerra (200)", codigo == 200 and oc["status"] == "encerrada")

# ---------------------------------------------------------------------------
print("\n5. O diálogo de segurança")
# ---------------------------------------------------------------------------
codigo, dds = req("POST", "/api/pdca/dds/", demo, {
    "obra": OBRA, "data": datetime.now().date().isoformat(),
    "tema": "E2E F.5 — cinto na periferia da laje",
})
if codigo != 201:
    fatal(f"abrir DDS respondeu {codigo}: {dds}")
DDS = dds["dds_id"]
lixo.append((f"/api/pdca/dds/{DDS}/", admin))
codigo, _ = req("POST", f"/api/pdca/dds/{DDS}/encerrar/", demo, {"publicar_no_diario": False})
check("encerrar sem ninguém na roda é recusado (400)", codigo == 400)
codigo, corpo = req("POST", f"/api/pdca/dds/{DDS}/presenca/", demo, {
    "participantes": [{"nome": "João Pereira"}, {"nome": "Maria Souza"}],
})
check("a lista chega em lote (201, 2 nomes)", codigo == 201 and corpo["registrados"] == 2)
codigo, corpo = req("POST", f"/api/pdca/dds/{DDS}/encerrar/", demo, {"publicar_no_diario": False})
check("com gente na roda, encerra (200)", codigo == 200 and corpo["dds"]["status"] == "encerrado")
codigo, _ = req("POST", f"/api/pdca/dds/{DDS}/presenca/", demo, {"participantes": [{"nome": "Atrasado"}]})
check("encerrado, a lista não recebe nome novo (400)", codigo == 400)

# ---------------------------------------------------------------------------
print("\n6. As frases que chegam à tela")
# ---------------------------------------------------------------------------
for rota in ("qualidade", "seguranca"):
    codigo, corpo = req("GET", f"/api/pdca/{rota}/?obra={OBRA}", demo)
    check(f"nenhuma frase de `{rota}/` cita número de fatia",
          codigo == 200 and not re.search(r"PDCA\.\d", json.dumps(corpo, ensure_ascii=False)))

# ---------------------------------------------------------------------------
print("\n7. A fronteira")
# ---------------------------------------------------------------------------
codigo, _ = req("GET", f"/api/pdca/qualidade/?obra={OBRA}", acme)
check("outro tenant, sem o módulo, para no entitlement (403)", codigo == 403)
codigo, _ = req("GET", "/api/pdca/seguranca/?obra=abc", demo)
check("obra que não é número responde 400, não 500", codigo == 400)

limpar()
total = len(passed)
ok = sum(1 for p in passed if p)
print(f"\n{'='*62}\nResultado: {ok}/{total}\n{'='*62}")
sys.exit(0 if ok == total else 1)
