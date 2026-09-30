"""Remodelagem da segurança, fase 4 — o token prova quem é; o PDP decide (fecha o D194).

O stack inteiro, pelo gateway, com as contas da demo e todos os módulos virados
para o PDP (fase 3):

  1. O token enxuto   -> nenhuma lista, papel, plano ou e-mail no access; tamanho
                         constante abaixo de 1 KB para toda persona; `sid` presente.
  2. Tudo funciona    -> backend e drone respondem pelo PDP; o drone, que caía com
                         "Request header is too large" (o D194 no Tomcat), abre.
                         O `/auth/me/` segue dando a lista à tela; o plano chega
                         ao backend pela ficha da empresa.
  3. Revogação        -> tirar o papel: a MESMA sessão perde o acesso em segundos.
     em segundos         Logout: o MESMO access passa a 401 no backend e no drone,
                         chamados direto (sem o gateway, que desde a fase 5 nem
                         deixa o cliente mandar token).
  4. Auditoria        -> a negação fica registrada em `DecisaoAcesso`, com o `sid`.

Limpeza: o papel do campo volta ao que era, com ou sem falha.

Rodar (stack de pé, imagens `iam`, `erp`, `iam-pdp` e do drone reconstruídas,
todos os módulos no PDP):  python3 testes/e2e/seg4_token_enxuto_test.py
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

from _segundo_fator import completar_login
from _sessao import access_do_bff, cabecalhos, da_resposta, direto

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")
ERP = os.environ.get("SGI_ERP_CONTAINER", "sgi-erp")
ESPERA_MAXIMA_S = 20
TETO_DO_TOKEN = 1024
SAIRAM = {"permissions", "roles", "modules", "is_tenant_admin", "is_platform_admin",
          "email", "tenant_slug", "plano", "rate_hora", "quotas"}
passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def fatal(msg):
    print(f"\n  !! {msg}")
    print(f"     Parcial: {sum(1 for p in passed if p)}/{len(passed)}")
    sys.exit(2)


def req(method, path, body=None, token=None, cookie=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers.update(cabecalhos(token))
    if cookie:
        headers["Cookie"] = cookie
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            corpo = resp.read().decode()
            try:
                corpo = json.loads(corpo) if corpo else None
            except ValueError:
                pass
            return resp.status, corpo, resp.headers
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null"), e.headers
        except Exception:
            return e.code, None, e.headers


def entrar(usuario, senha):
    """Devolve (cookie da sessão, os cookies da resposta — sessão e refresh)."""
    st, corpo, cab = req("POST", "/auth/login/", {"username": usuario, "password": senha})
    if st == 429:
        time.sleep(60)
        st, corpo, cab = req("POST", "/auth/login/", {"username": usuario, "password": senha})
    if st != 200:
        fatal(f"login de {usuario} → {st}")
    if "segundo_fator" in (corpo or {}):
        # Quem tem segundo fator (o admin) só precisa da sessão aqui.
        return completar_login(GW, corpo)["sessao"], ""
    cookies = "; ".join(c.split(";", 1)[0] for c in cab.get_all("Set-Cookie") or [])
    return da_resposta(cab), cookies


def carga(token):
    parte = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4)))


def shell(codigo):
    r = subprocess.run(["docker", "exec", ERP, "python", "manage.py", "shell", "-c", codigo],
                       capture_output=True, text=True, timeout=120)
    return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]


def esperar(condicao, limite=ESPERA_MAXIMA_S):
    inicio = time.monotonic()
    while time.monotonic() - inicio < limite:
        if condicao():
            return round(time.monotonic() - inicio, 1)
        time.sleep(0.5)
    return None


print("\n1. O token enxuto")
pessoas = {}
for usuario, senha in (("demo", "demo123"), ("semdrone", "semdrone123"), ("acme", "acme123"),
                       ("campo", "campo123"), ("admin", "admin123")):
    sessao, cookie = entrar(usuario, senha)
    pessoas[usuario] = (sessao, cookie)
    access = access_do_bff(sessao) or ""  # o que o gateway injeta no backend
    c = carga(access) if access else {}
    linha = len("Authorization: Bearer ") + len(access)
    check(f"{usuario}: linha Authorization com {linha} B (< {TETO_DO_TOKEN}), sem lista nem plano,"
          f" com sid", access and linha < TETO_DO_TOKEN and not (SAIRAM & set(c)) and c.get("sid"))

print("\n2. Tudo funciona pelo PDP")
demo, sem = pessoas["demo"][0], pessoas["semdrone"][0]
check("demo lê /api/clientes/ (200)", req("GET", "/api/clientes/", token=demo)[0] == 200)
check("demo lê o RH (200); semdrone não (403)",
      (req("GET", "/api/funcionarios/", token=demo)[0], req("GET", "/api/funcionarios/", token=sem)[0]) == (200, 403))
st_drone = req("GET", "/odm-api/projects", token=demo)[0]
check(f"drone: demo abre os projetos ({st_drone}) — o D194 no Tomcat acabou", st_drone == 200)
check("drone: semdrone recebe 403", req("GET", "/odm-api/projects", token=sem)[0] == 403)
st, me, _ = req("GET", "/auth/me/", token=demo)
check("o /auth/me/ dá a lista à tela", st == 200 and "permissions" in me and "drone" in me.get("modules", []))
st, plano, _ = req("GET", "/api/plano/", token=demo)
check(f"o plano chega ao backend pela ficha ({st}, {(plano or {}).get('plano') or (plano or {}).get('slug')})",
      st == 200 and bool(plano))

admin, campo = pessoas["admin"][0], pessoas["campo"][0]
st, usuarios, _ = req("GET", "/iam/usuarios/", token=admin)
lista = usuarios.get("results", usuarios) if isinstance(usuarios, dict) else usuarios
alvo = next((u for u in lista or [] if u.get("username") == "campo"), None)
if st != 200 or not alvo:
    fatal(f"não achei o usuário campo pela IAM ({st})")
perfis_originais = list(alvo["perfis"])
st, perfis, _ = req("GET", "/iam/perfis/", token=admin)
perfis = perfis.get("results", perfis) if isinstance(perfis, dict) else perfis
papel_campo = next((p["id"] for p in perfis if p["nome"] == "campo"), None)


def trocar_papeis(ids):
    return req("PATCH", f"/iam/usuarios/{alvo['id']}/", {"perfis": ids}, token=admin)[0]


try:
    print("\n3. Revogação em segundos")
    check("com o papel, o campo lê o cronograma", req("GET", "/api/pdca/cronogramas/", token=campo)[0] == 200)
    check("admin tira o papel campo", trocar_papeis([p for p in perfis_originais if p != papel_campo]) == 200)
    t = esperar(lambda: req("GET", "/api/pdca/cronogramas/", token=campo)[0] == 403)
    check(f"o MESMO token perde o cronograma em {t} s", t is not None)
    trocar_papeis(perfis_originais)
    t = esperar(lambda: req("GET", "/api/pdca/cronogramas/", token=campo)[0] == 200)
    check(f"com o papel de volta, lê de novo em {t} s", t is not None)

    sessao, cookie = entrar("demo", "demo123")
    do_backend, do_drone = access_do_bff(sessao, "api"), access_do_bff(sessao, "drone")
    backend_direto = "http://localhost:8000/api/clientes/"
    drone_direto = "http://java-service:8080/api/v1/projects"
    check("com a sessão aberta, a sessão vale no backend e no drone",
          (req("GET", "/api/clientes/", token=sessao)[0], req("GET", "/odm-api/projects", token=sessao)[0]) == (200, 200))
    check("e o access de cada um vale direto no serviço",
          (direto(backend_direto, do_backend), direto(drone_direto, do_drone)) == (200, 200))
    check("logout (200)", req("POST", "/auth/logout/", cookie=cookie)[0] == 200)
    t = esperar(lambda: direto(backend_direto, do_backend) == 401)
    check(f"o MESMO access cai no backend em {t} s", t is not None)
    t = esperar(lambda: direto(drone_direto, do_drone) == 401)
    check(f"e no drone em {t} s", t is not None)
    check("pelo gateway, a sessão encerrada não vira token (401)", req("GET", "/api/clientes/", token=sessao)[0] == 401)
    check("o refresh da sessão encerrada é recusado", req("POST", "/auth/refresh/", cookie=cookie)[0] == 401)

    print("\n4. Auditoria de decisão")
    sid_sem = carga(access_do_bff(sem))["sid"]
    req("GET", "/api/funcionarios/", token=sem)
    n = shell("from nucleo.models import DecisaoAcesso as D; "
              f"print(D.objects.filter(sid='{sid_sem}', decisao=False, acao='m:rh').count())")
    check(f"a negação do semdrone no RH ficou registrada com o sid ({n} linha(s))", n.isdigit() and int(n) >= 1)
    n = shell("from nucleo.models import DecisaoAcesso as D; "
              "print(D.objects.filter(decisao=True, classe__in=['A', 'B']).count())")
    check(f"concessão comum não vai à tabela ({n})", n == "0")
finally:
    trocar_papeis(perfis_originais)

total = sum(1 for p in passed if p)
print(f"\n  Resultado: {total}/{len(passed)}")
sys.exit(0 if total == len(passed) else 1)
