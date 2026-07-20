"""Fase 5 — valida RS256/JWKS pelo gateway (8090).

Prova: (a) a IAM assina RS256, (b) backend e drone validam com a chave pública,
(c) um token forjado com o ANTIGO segredo HS256 é REJEITADO — o buraco do
segredo compartilhado (bug da Fase 2) está fechado.
"""
import json, base64, urllib.request, urllib.error, hmac, hashlib, time, uuid

GW = __import__("os").environ.get("SGI_GW", "http://localhost:8090")  # SGI_GW aponta ao staging (10.7)

def b64u_decode(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            txt = resp.read().decode(errors="replace")
            try:
                return resp.status, (json.loads(txt) if txt.strip() else None)
            except json.JSONDecodeError:
                return resp.status, None
    except urllib.error.HTTPError as e:
        return e.code, None

s, d = req("POST", "/auth/login/", body={"username": "demo", "password": "demo123"})
tok = d["access"]
hdr = json.loads(b64u_decode(tok.split(".")[0]))
print("1) IAM assina com alg =", hdr.get("alg"), "(esperado RS256)")

s, jwks = req("GET", "/.well-known/jwks.json")
kty = jwks["keys"][0]["kty"] if jwks and jwks.get("keys") else None
print("2) JWKS ->", s, "| kty =", kty, "(esperado RSA)")

print("3) Token RS256 REAL da IAM:")
print("   drone /odm-api/projects ->", req("GET", "/odm-api/projects", tok)[0], "(esperado 200)")
print("   backend   /api/clientes/    ->", req("GET", "/api/clientes/", tok)[0], "(esperado 200)")

# 4) Ataque: forja um token HS256 com o antigo segredo compartilhado
secret = None
for line in open("/home/eegm/projetos/02sistema_gestao_integrada/.env", encoding="utf-8", errors="replace"):
    if line.strip().startswith("JWT_SECRET="):
        secret = line.strip().split("=", 1)[1].strip().strip('"').strip("'"); break
def b64u(x): return base64.urlsafe_b64encode(x).rstrip(b"=").decode()
now = int(time.time())
h = {"alg": "HS256", "typ": "JWT"}
p = {"sub": "attacker", "tenant_id": str(uuid.uuid4()), "tenant_slug": "x",
     "modules": ["drone"], "iat": now, "exp": now + 3600}
si = b64u(json.dumps(h).encode()) + "." + b64u(json.dumps(p).encode())
forged = si + "." + b64u(hmac.new(secret.encode(), si.encode(), hashlib.sha256).digest())
print("4) Token FORJADO (HS256 com o segredo antigo) — deve ser REJEITADO:")
print("   drone /odm-api/projects ->", req("GET", "/odm-api/projects", forged)[0], "(esperado 401)")
print("   backend   /api/clientes/    ->", req("GET", "/api/clientes/", forged)[0], "(esperado 401)")
