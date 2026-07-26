"""E2E ao vivo do IE.0b/IE.1 pelo gateway — o caminho que travou em produção de dev.

Exercita justamente o que o bug do worker escondeu: arquivo grande → job → cabeçalho
irreconhecível → de-para manual → conferência → aplicar → desfazer.
"""
import io
import json
import sys
import time

import requests

GW = "http://localhost:8090"
OK, FALHA = [], []


def checar(nome, condicao, detalhe=""):
    (OK if condicao else FALHA).append(nome)
    print(f"{'OK  ' if condicao else 'FALHA'} · {nome}{(' — ' + str(detalhe)) if detalhe else ''}")


s = requests.Session()
login = s.post(f"{GW}/auth/login/", json={"username": "demo", "password": "demo123"}, timeout=30)
checar("login demo", login.status_code == 200, login.status_code)
token = login.json().get("access")
H = {"Authorization": f"Bearer {token}"}

# --- 1. o recurso aparece para quem tem acesso total -------------------------
r = s.get(f"{GW}/api/impexp/recursos/", headers=H, timeout=30)
ids = [x["id"] for x in r.json().get("recursos", [])]
checar("recursos publica orcamento.banco_preco", "orcamento.banco_preco" in ids, ids)

# --- 2. um banco destravado de destino ---------------------------------------
bancos = s.get(f"{GW}/api/orcamento/bancos/", headers=H, timeout=30).json()
lista = bancos.get("results", bancos) if isinstance(bancos, dict) else bancos
destino = next((b for b in lista if not b.get("travado")), None)
if destino is None:
    criado = s.post(f"{GW}/api/orcamento/bancos/", headers=H, timeout=30,
                    json={"nome": "E2E IE.1"})
    destino = criado.json()
checar("banco de destino", bool(destino.get("banco_id")), destino.get("nome"))
banco_id = destino["banco_id"]

# --- 3. arquivo GRANDE com cabeçalho irreconhecível → job + pedido de de-para --
linhas = ["Xis;Ipsilon;Ze;Www;Kkk"] + [
    f"E2E-{i};ITEM DE TESTE {i};UN;{10 + i},50;GRUPO" for i in range(4000)
]
conteudo = "\n".join(linhas).encode("utf-8")

envio = s.post(
    f"{GW}/api/impexp/orcamento.banco_preco/importar/", headers=H, timeout=120,
    files={"arquivo": ("grande.csv", io.BytesIO(conteudo), "text/csv")},
    data={"contexto": json.dumps({"banco": banco_id})},
)
checar("arquivo grande vira job (202)", envio.status_code == 202, envio.status_code)
lote = envio.json()["importacao_id"]

# --- 4. o job para pedindo o de-para, sem beco sem saída ----------------------
resumo = {}
for _ in range(40):
    resumo = s.get(f"{GW}/api/impexp/importacoes/{lote}/", headers=H, timeout=30).json()
    if resumo["status"] != "lendo":
        break
    time.sleep(1)
checar("job pediu o de-para (R4)", resumo.get("aguarda_de_para") is True, resumo.get("status"))
checar("devolveu os cabeçalhos vistos", bool(resumo.get("cabecalhos_vistos")))

# --- 5. remapear relê o MESMO arquivo, sem novo upload ------------------------
remap = s.post(
    f"{GW}/api/impexp/importacoes/{lote}/remapear/", headers=H, timeout=60,
    json={"de_para": {"codigo": 0, "descricao": 1, "unidade": 2, "custo_unitario": 3, "grupo": 4}},
)
checar("remapear aceito", remap.status_code == 200, remap.status_code)

for _ in range(60):
    resumo = s.get(f"{GW}/api/impexp/importacoes/{lote}/", headers=H, timeout=30).json()
    if resumo["status"] != "lendo":
        break
    time.sleep(1)
checar("conferência pronta", resumo.get("status") == "conferindo", resumo.get("status"))
checar("4000 linhas classificadas", resumo.get("total") == 4000, resumo.get("total"))
checar("nada gravado antes da decisão (R1)",
       s.get(f"{GW}/api/orcamento/itens-banco/?banco={banco_id}&page_size=1",
             headers=H, timeout=30).json().get("count", 0) == 0)

# --- 6. aplicar e desfazer ----------------------------------------------------
aplicado = s.post(f"{GW}/api/impexp/importacoes/{lote}/aplicar/", headers=H, timeout=180).json()
checar("aplicou as 4000", aplicado.get("aplicadas") == 4000, aplicado.get("aplicadas"))

conta = s.get(f"{GW}/api/orcamento/itens-banco/?banco={banco_id}&page_size=1",
              headers=H, timeout=30).json().get("count", 0)
checar("itens no banco", conta == 4000, conta)

historico = s.get(f"{GW}/api/impexp/orcamento.banco_preco/importacoes/",
                  headers=H, timeout=30).json()["importacoes"]
atual = next(h for h in historico if h["importacao_id"] == lote)
checar("histórico marca desfazível (R6)", atual["pode_desfazer"] is True)

desfeito = s.post(f"{GW}/api/impexp/importacoes/{lote}/desfazer/", headers=H, timeout=180)
checar("desfazer aceito", desfeito.status_code == 200, desfeito.status_code)
conta = s.get(f"{GW}/api/orcamento/itens-banco/?banco={banco_id}&page_size=1",
              headers=H, timeout=30).json().get("count", 0)
checar("banco voltou ao que era", conta == 0, conta)

# --- 7. exportação: o recorte da tela -----------------------------------------
exp = s.get(f"{GW}/api/impexp/orcamento.banco_preco/exportar/",
            headers=H, timeout=120, params={"formato": "csv", "banco": banco_id})
checar("exportar responde", exp.status_code in (200, 202), exp.status_code)

# --- 8. o gate do §3: meia permissão não vê o recurso -------------------------
sem = requests.Session()
login2 = sem.post(f"{GW}/auth/login/", json={"username": "semdrone", "password": "demo123"}, timeout=30)
if login2.status_code == 200:
    H2 = {"Authorization": f"Bearer {login2.json()['access']}"}
    ids2 = [x["id"] for x in sem.get(f"{GW}/api/impexp/recursos/", headers=H2,
                                     timeout=30).json().get("recursos", [])]
    checar("operacional não vê o recurso (R11)", "orcamento.banco_preco" not in ids2, ids2)

print(f"\n=== {len(OK)}/{len(OK) + len(FALHA)} ===")
if FALHA:
    print("FALHARAM:", FALHA)
sys.exit(1 if FALHA else 0)
