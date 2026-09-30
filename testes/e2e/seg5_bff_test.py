"""Remodelagem da segurança, fase 5 — BFF e audiência por serviço (acesso-e-permissoes.md §10.5–§10.6).

Critério de saída (§10.12): **nenhum token acessível ao JavaScript**. Pelo gateway,
com as contas da demo:

  1. A borda       -> o login devolve cookies HttpOnly/SameSite=Strict e nenhum
                      token; `/auth/interno/` é 404; o `Authorization` que o cliente
                      manda não chega aos serviços (nem o token verdadeiro).
  2. A audiência   -> o access que o gateway injeta no backend é `sgi-api`, o do
                      drone é `sgi-drone`, `typ: at+jwt`; um não entra no outro
                      (chamando o serviço direto, sem o gateway).
  3. A escrita     -> com o cookie e sem o cabeçalho anti-CSRF, 403; de outro site, 403.
  4. O navegador   -> login pela tela; nenhuma resposta que a página recebe traz
                      um JWT; nada no localStorage/sessionStorage; o cookie da
                      sessão é invisível ao JavaScript; o app do drone (/drone/)
                      abre com a mesma sessão, sem login próprio.

Rodar (stack de pé, imagens reconstruídas):
    LD_LIBRARY_PATH=~/.local/chromium-libs .venv/bin/python testes/e2e/seg5_bff_test.py
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

from _sessao import ANTI_CSRF, NOME, access_do_bff, cabecalhos, carga, direto
from _segundo_fator import entrar

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")
JWT = re.compile(r"eyJ[\w-]{8,}\.eyJ[\w-]{8,}\.[\w-]+")
passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def req(method, path, headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", **(headers or {})}
    r = urllib.request.Request(GW + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read().decode(errors="replace"), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace"), e.headers


print(f"\n{'='*62}\nFase 5 — BFF e audiência por serviço\n{'='*62}\nGateway: {GW}")

# ---------------------------------------------------------------- 1. a borda
print("\n1. A borda")
st, corpo, cab = req("POST", "/auth/login/", body={"username": "demo", "password": "demo123"})
check(f"login ({st}) sem token nenhum no corpo", st == 200 and not JWT.search(corpo))
cookies = cab.get_all("Set-Cookie") or []
sessao_linha = next((c for c in cookies if c.startswith(f"{NOME}=")), "")
check("o cookie da sessão é HttpOnly e SameSite=Strict, no caminho /",
      "HttpOnly" in sessao_linha and "SameSite=Strict" in sessao_linha and "Path=/" in sessao_linha)
check("o do refresh também é HttpOnly", any(c.startswith("sgi_refresh=") and "HttpOnly" in c for c in cookies))
sessao = entrar(GW, "demo", "demo123")
if not sessao:
    print("  !! sem sessão do demo — o resto não anda")
    sys.exit(2)
check("/auth/interno/bff/api/ não existe na borda (404)", req("GET", "/auth/interno/bff/api/")[0] == 404)
token_api = access_do_bff(sessao, "api")
check("com o cookie, o backend responde (200)", req("GET", "/api/clientes/", cabecalhos(sessao))[0] == 200)
check("o token VERDADEIRO mandado pelo cliente não chega ao backend (401)",
      req("GET", "/api/clientes/", {"Authorization": f"Bearer {token_api}"})[0] == 401)

# ------------------------------------------------------------ 2. a audiência
print("\n2. A audiência por serviço")
token_drone = access_do_bff(sessao, "drone")
c_api, c_drone = carga(token_api), carga(token_drone)
check(f"o access do backend é `sgi-api` ({c_api.get('aud')})", c_api.get("aud") == "sgi-api")
check(f"o do drone é `sgi-drone` ({c_drone.get('aud')})", c_drone.get("aud") == "sgi-drone")
tipo = json.loads(base64.urlsafe_b64decode(token_api.split(".")[0] + "==")).get("typ")
check(f"typ = at+jwt ({tipo})", tipo == "at+jwt")
backend, drone = "http://localhost:8000/api/clientes/", "http://java-service:8080/api/v1/projects"
check("direto no backend: o access dele entra (200)", direto(backend, token_api) == 200)
check("direto no backend: o do drone não entra (401)", direto(backend, token_drone) == 401)
check("direto no drone: o dele entra (200)", direto(drone, token_drone) == 200)
st = direto(drone, token_api)
check(f"direto no drone: o do backend não entra ({st})", st in (401, 403))

# --------------------------------------------------------------- 3. a escrita
print("\n3. A escrita pelo cookie")
so_cookie = {"Cookie": f"{NOME}={sessao}"}
check("POST sem o anti-CSRF → 403", req("POST", "/api/clientes/", so_cookie, {})[0] == 403)
st = req("POST", "/api/clientes/", {**so_cookie, **ANTI_CSRF}, {})[0]
check(f"com o anti-CSRF chega ao backend ({st}, validação)", st == 400)
st = req("POST", "/api/clientes/", {**so_cookie, **ANTI_CSRF, "Origin": "https://evil.example"}, {})[0]
check(f"de outro site, mesmo com o cabeçalho → 403 ({st})", st == 403)

# -------------------------------------------------------------- 4. navegador
print("\n4. No navegador")
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("  !! sem Playwright neste Python — rode com o .venv")
    sys.exit(2)

vistos, com_jwt = [], []
with sync_playwright() as p:
    nav = p.chromium.launch()
    # O certificado do staging é autoassinado (o README manda aceitar o aviso); o
    # Chromium não lê o SSL_CERT_FILE. Só o validate.sh liga isto.
    pagina = nav.new_page(ignore_https_errors=os.getenv("SGI_ACEITAR_CERT_LOCAL") == "1")

    def olhar(resposta):
        if not resposta.url.startswith(GW):
            return
        tipo_ = resposta.headers.get("content-type", "")
        if "json" not in tipo_ and "text" not in tipo_:
            return
        try:
            texto = resposta.text()
        except Exception:
            return
        vistos.append(resposta.url)
        if JWT.search(texto):
            com_jwt.append(resposta.url)

    pagina.on("response", olhar)
    pagina.goto(f"{GW}/login")
    pagina.fill("input#username", "demo")
    pagina.fill("input#password", "demo123")
    pagina.click("button[type=submit]")
    pagina.wait_for_url(lambda url: "/login" not in url, timeout=20_000)
    pagina.wait_for_load_state("networkidle")
    pagina.goto(f"{GW}/app/clientes")
    pagina.wait_for_load_state("networkidle")
    check(f"nenhuma resposta das {len(vistos)} que a página leu traz um JWT", vistos and not com_jwt)
    armazenado = pagina.evaluate(
        "() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)])"
    )
    check("nada de token no localStorage nem no sessionStorage", not JWT.search(armazenado))
    check("o cookie da sessão é invisível ao JavaScript (HttpOnly)",
          NOME not in pagina.evaluate("() => document.cookie"))
    pagina.goto(f"{GW}/drone/")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1500)
    check(f"o app do drone abre com a mesma sessão, sem login próprio ({pagina.url})",
          "/drone/" in pagina.url and "/login" not in pagina.url)
    armazenado = pagina.evaluate(
        "() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)])"
    )
    check("e o drone também não guarda token", not JWT.search(armazenado))
    nav.close()

total = sum(1 for x in passed if x)
print(f"\n  Resultado: {total}/{len(passed)}")
sys.exit(0 if total == len(passed) else 1)
