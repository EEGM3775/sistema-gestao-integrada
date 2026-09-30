"""E2E da Fase 4 — valida a plataforma inteira pelo gateway unificado (8090).

Pré: `docker compose --profile full up -d` e o seed da IAM (demo/semdrone).
"""
import json, urllib.request, urllib.error
from _sessao import cabecalhos, da_resposta
from _segundo_fator import entrar

GW = __import__("os").environ.get("SGI_GW", "http://localhost:8090")  # SGI_GW aponta ao staging (10.7)

def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers.update(cabecalhos(token))
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            txt = resp.read().decode(errors="replace")
            try:
                return resp.status, (json.loads(txt) if txt.strip() else None)
            except json.JSONDecodeError:
                return resp.status, None  # resposta não-JSON (ex.: HTML do React)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:160]

def login(user, pwd):
    return entrar(GW, user, pwd)  # o cookie da sessão (BFF, fase 5)

print("== Login pela IAM (via gateway) ==")
tok_demo = login("demo", "demo123")
tok_sem = login("semdrone", "semdrone123")
print("  demo token:", "OK" if tok_demo else "FALHOU", "| semdrone token:", "OK" if tok_sem else "FALHOU")

print("== Front-end servido pelo gateway ==")
print("  GET /        (React) ->", req("GET", "/")[0], "(esperado 200)")
print("  GET /drone/  (Angular) ->", req("GET", "/drone/")[0], "(esperado 200)")

print("== DoD: entitlement do drone (/odm-api) ==")
print("  sem token        ->", req("GET", "/odm-api/projects")[0], "(401)")
print("  demo (tem drone) ->", req("GET", "/odm-api/projects", tok_demo)[0], "(200)")
print("  semdrone (sem)   ->", req("GET", "/odm-api/projects", tok_sem)[0], "(403)")

print("== backend como resource server da IAM (/api) ==")
print("  sem token        -> /api/clientes/ ->", req("GET", "/api/clientes/")[0], "(401)")
print("  demo (token IAM) -> /api/clientes/ ->", req("GET", "/api/clientes/", tok_demo)[0], "(200)")

print("== Fase 3: criar projeto de drone vinculado a uma obra + filtrar ==")
s, p = req("POST", "/odm-api/projects", tok_demo,
           {"name": "E2E obra 1234", "empreendimentoId": 1234, "obraId": 5678})
print("  cria (obraId=5678) ->", s, "obraId=", (p or {}).get("obraId") if isinstance(p, dict) else p)
s, lst = req("GET", "/odm-api/projects?obraId=5678", tok_demo)
print("  GET ?obraId=5678 ->", s, "qtd:", len(lst) if isinstance(lst, list) else lst)
