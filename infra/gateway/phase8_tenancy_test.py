"""Fase 8.5 — isolamento de tenant nas entidades-filhas do drone, via gateway (8090).

Contexto: as filhas do drone (chunks, tasks, measurements, annotations, images)
vivem sob /odm-api/projects/{projectId}/... e eram escopadas SÓ por projectId.
Um usuário de outra empresa que passasse o projectId alheio lia/gravava as filhas
daquele projeto. A Fase 8.5 fecha isso na borda (ProjectTenantInterceptor): o
projeto da URL precisa pertencer ao tenant do token, senão 404.

Prova (precisa do seed com DOIS tenants drone — iam/seed_demo.py):
  demo / demo123  -> tenant demo | módulo drone
  acme / acme123  -> tenant acme | módulo drone

  1. demo cria um projeto.
  2. acme (outro tenant, MESMO módulo) recebe 404 em toda rota-filha daquele
     projeto e não o vê na própria listagem.
  3. demo continua acessando o próprio projeto normalmente (200).

Rodar (stack de pé):  python infra/gateway/phase8_tenancy_test.py
"""
import json, sys, urllib.request, urllib.error

# Console do Windows costuma ser cp1252 e quebra em emoji/acentos ao redirecionar.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = __import__("os").environ.get("SGI_GW", "http://localhost:8090")  # SGI_GW aponta ao staging (10.7)

def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            payload = resp.read().decode() or "null"
            return resp.status, json.loads(payload)
    except urllib.error.HTTPError as e:
        return e.code, None

def login(u, p):
    data = json.dumps({"username": u, "password": p}).encode()
    r = urllib.request.Request(GW + "/auth/login/", data=data, method="POST",
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.load(resp)["access"]

passed = []
def check(label, cond):
    passed.append(cond)
    print(f"  [{'OK' if cond else 'XXX'}] {label}")

demo = login("demo", "demo123")
acme = login("acme", "acme123")

print("== Setup: demo cria um projeto de drone ==")
status, proj = req("POST", "/odm-api/projects", demo, {"name": "Obra Isolamento 8.5"})
check(f"demo cria projeto (201/200) -> {status}", status in (200, 201) and proj and proj.get("id"))
pid = proj["id"] if proj else None
print(f"  projeto do tenant demo: id={pid}")

print("== Cross-tenant: acme NÃO acessa filhas do projeto de demo (404) ==")
child_paths = [
    ("GET  chunks",       "GET",  f"/odm-api/projects/{pid}/chunks"),
    ("GET  measurements", "GET",  f"/odm-api/projects/{pid}/measurements"),
    ("GET  annotations",  "GET",  f"/odm-api/projects/{pid}/annotations"),
    ("GET  tasks",        "GET",  f"/odm-api/projects/{pid}/tasks"),
    ("GET  projeto",      "GET",  f"/odm-api/projects/{pid}"),
]
for label, method, path in child_paths:
    status, _ = req(method, path, acme)
    check(f"acme {label} -> {status} (esperado 404)", status == 404)

# Escrita também barrada (criar anotação no projeto alheio)
status, _ = req("POST", f"/odm-api/projects/{pid}/annotations", acme,
                {"type": "MARKER", "coordinatesJson": "[0,0]", "text": "invasor"})
check(f"acme POST annotation -> {status} (esperado 404)", status == 404)

print("== Listagem escopada: acme não vê o projeto de demo ==")
status, lista = req("GET", "/odm-api/projects", acme)
ids_acme = [p.get("id") for p in (lista or [])]
check(f"acme lista projetos ({status}) sem o id {pid}", status == 200 and pid not in ids_acme)

print("== Sanidade: demo acessa o PRÓPRIO projeto (200) ==")
status, _ = req("GET", f"/odm-api/projects/{pid}/chunks", demo)
check(f"demo GET chunks -> {status} (esperado 200)", status == 200)
status, _ = req("GET", f"/odm-api/projects/{pid}", demo)
check(f"demo GET projeto -> {status} (esperado 200)", status == 200)

print()
if all(passed):
    print(f"RESULTADO: TODOS OS {len(passed)} CHECKS PASSARAM ✅  (isolamento do drone provado)")
else:
    print(f"RESULTADO: {passed.count(False)}/{len(passed)} FALHARAM ❌")
    raise SystemExit(1)
