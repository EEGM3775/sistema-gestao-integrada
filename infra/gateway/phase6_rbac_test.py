"""Fase 6 — RBAC de plataforma (genérico por módulo), via gateway (8090).

demo     -> modulos: drone, erp_financeiro, crm, rh | papel: financeiro
semdrone -> modulos: erp_financeiro                 | papel: operacional

Prova: camada 1 (entitlement de módulo) e camada 2 (papel), com o MESMO
mecanismo do drone, agora nos módulos internos do ERP.
"""
import json, urllib.request, urllib.error

GW = "http://localhost:8090"

def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code

def login(u, p):
    data = json.dumps({"username": u, "password": p}).encode()
    r = urllib.request.Request(GW + "/auth/login/", data=data, method="POST",
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.load(resp)["access"]

demo = login("demo", "demo123")
sem = login("semdrone", "semdrone123")

def row(label, path, exp_demo, exp_sem):
    d = req("GET", path, demo)
    s = req("GET", path, sem)
    okd = "OK" if d == exp_demo else "XXX"
    oks = "OK" if s == exp_sem else "XXX"
    print(f"  {label:<34} demo={d}[{okd}]  semdrone={s}[{oks}]")

print("== Camada 1: ENTITLEMENT DE MÓDULO ==")
print("  (demo tem crm/rh/erp; semdrone só erp)")
row("base /api/clientes/ (sem módulo)", "/api/clientes/", 200, 200)
row("módulo rh  /api/funcionarios/",     "/api/funcionarios/", 200, 403)
row("módulo crm /api/crm/leads/",        "/api/crm/leads/", 200, 403)

print("== Camada 2: RBAC POR PAPEL (financeiro) ==")
print("  (ambos têm o módulo erp_financeiro; só demo tem o papel 'financeiro')")
row("financeiro /api/erp/faturas/",      "/api/erp/faturas/", 200, 403)

print("== 6.1: login local do ERP foi APOSENTADO (404) ==")
print("  POST /api/token/      ->", req("POST", "/api/token/", body={}), "(esperado 404)")
print("  POST /api/auth/login/ ->", req("POST", "/api/auth/login/", body={}), "(esperado 404)")
