"""Remodelagem da segurança, fases 2 e 3 — o PDP de pé, a sombra e a virada.

As suítes provam cada peça isolada (a IAM contra um SpiceDB de teste, o backend
com PDP e Redis de mentira e contra o SpiceDB de teste). Aqui é o stack inteiro,
pelo gateway e com as contas da demo:

  1. O PDP de pé     -> SpiceDB saudável, `iam-pdp` e `pdp-invalidador` rodando.
  2. A equivalência  -> para cada pessoa da demo, as 241 perguntas (todo código do
                        catálogo, todo módulo, admin e supervisor): o PDP responde
                        o que o token dela responde. Zero divergência.
  3. A sombra        -> o admin tira o papel `campo` do usuário campo: o PDP sabe
                        em segundos; o token velho ainda não — e a divergência é
                        classificada `token_defasado`, não `real`.
  4. A virada (fase 3) -> o PDCA passa a ser decidido pelo PDP: o campo, com o
                        MESMO token, perde o cronograma em segundos quando perde o
                        papel, e o recupera quando o papel volta. A volta ao
                        token vale na hora.

Limpeza: o papel do campo e o modo do PDCA voltam ao que eram, com ou sem falha.

Rodar (stack de pé, imagens `iam` e `erp` reconstruídas, `iam-pdp` e
`pdp-invalidador` no ar):  python3 testes/e2e/seg2_pdp_sombra_test.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

from _segundo_fator import completar_login

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")
ERP = os.environ.get("SGI_ERP_CONTAINER", "sgi-erp")
PREFIXO = os.environ.get("SGI_PREFIX", "sgi")
#: "Revogação em segundos" (§10.3): quanto se espera antes de reprovar.
ESPERA_MAXIMA_S = 20
passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def fatal(msg):
    print(f"\n  !! {msg}")
    print(f"     Parcial: {sum(1 for p in passed if p)}/{len(passed)}")
    sys.exit(2)


def req(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            corpo = resp.read().decode()
            return resp.status, (json.loads(corpo) if corpo else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except Exception:
            return e.code, None


def entrar(usuario, senha):
    st, corpo = req("POST", "/auth/login/", {"username": usuario, "password": senha})
    if st == 429:
        time.sleep(60)
        st, corpo = req("POST", "/auth/login/", {"username": usuario, "password": senha})
    if st != 200:
        fatal(f"login de {usuario} → {st}")
    return completar_login(GW, corpo)["access"]


def manage(*args):
    r = subprocess.run(["docker", "exec", ERP, "python", "manage.py", *args],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"manage.py {' '.join(args)}: {r.stderr.strip()[-400:]}")
    return r.stdout


def conferir(token, pergunta=None):
    args = ["conferir_pdp", "--token", token]
    if pergunta:
        args += ["--pergunta", pergunta]
    return json.loads(manage(*args).strip().splitlines()[-1])


def rodando(nome):
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}",
                        f"{PREFIXO}-{nome}"], capture_output=True, text=True)
    return r.stdout.strip()


def esperar(condicao, limite=ESPERA_MAXIMA_S):
    """Segundos até a condição valer, ou None se não valeu dentro do limite."""
    inicio = time.monotonic()
    while time.monotonic() - inicio < limite:
        if condicao():
            return round(time.monotonic() - inicio, 1)
        time.sleep(0.5)
    return None


print("\n1. O PDP de pé")
check("SpiceDB saudável", rodando("spicedb").endswith("healthy"))
check("iam-pdp rodando (reconciliação contínua)", rodando("iam-pdp").startswith("running"))
check("pdp-invalidador rodando (Watch)", rodando("pdp-invalidador").startswith("running"))

print("\n2. A equivalência — cada pessoa da demo, todas as perguntas")
pessoas = {}
for usuario, senha in (("demo", "demo123"), ("semdrone", "semdrone123"), ("acme", "acme123"),
                       ("campo", "campo123"), ("admin", "admin123")):
    pessoas[usuario] = entrar(usuario, senha)
    r = conferir(pessoas[usuario])
    check(f"{usuario}: {r['perguntas']} perguntas, {len(r['divergencias'])} divergência(s)"
          f", PDP indisponível em {r['pdp_indisponivel']}",
          r["perguntas"] >= 241 and not r["divergencias"] and not r["pdp_indisponivel"])
    if r["divergencias"]:
        print("       ", r["divergencias"][:5])

admin, campo = pessoas["admin"], pessoas["campo"]
st, usuarios = req("GET", "/iam/usuarios/", token=admin)
lista = usuarios.get("results", usuarios) if isinstance(usuarios, dict) else usuarios
alvo = next((u for u in lista or [] if u.get("username") == "campo"), None)
if st != 200 or not alvo:
    fatal(f"não achei o usuário campo pela IAM ({st})")
perfis_originais = list(alvo["perfis"])
st, perfis = req("GET", "/iam/perfis/", token=admin)
perfis = perfis.get("results", perfis) if isinstance(perfis, dict) else perfis
papel_campo = next((p["id"] for p in perfis if p["nome"] == "campo"), None)
if papel_campo not in perfis_originais:
    fatal("o usuário campo não tem o papel campo — a demo mudou?")


def trocar_papeis(ids):
    st, _ = req("PATCH", f"/iam/usuarios/{alvo['id']}/", {"perfis": ids}, token=admin)
    return st


try:
    print("\n3. A sombra — o PDP sabe em segundos; o token velho ainda não")
    check("admin tira o papel campo do usuário campo", trocar_papeis(
        [p for p in perfis_originais if p != papel_campo]) == 200)
    t = esperar(lambda: conferir(campo, "c:pdca.avanco.apontar")["respostas"]["c:pdca.avanco.apontar"]["pdp"] is False)
    check(f"o PDP negou `pdca.avanco.apontar` em {t} s (limite {ESPERA_MAXIMA_S} s)", t is not None)
    r = conferir(campo, "c:pdca.avanco.apontar")
    check("o token velho ainda concede — é a janela que a fase 4 fecha",
          r["respostas"]["c:pdca.avanco.apontar"]["token"] is True)
    check("a divergência é classificada `token_defasado`, não `real`",
          [d["tipo"] for d in r["divergencias"]] == ["token_defasado"])
    check("o papel volta", trocar_papeis(perfis_originais) == 200)
    t = esperar(lambda: not conferir(campo)["divergencias"])
    check(f"com o papel de volta, zero divergência de novo em {t} s", t is not None)

    print("\n4. A virada — o PDP decide o PDCA")
    manage("modo_autorizacao", "pdca", "pdp", "--forcar")
    st, _ = req("GET", "/api/pdca/cronogramas/", token=campo)
    check(f"com o papel, o campo lê o cronograma pelo PDP ({st})", st == 200)
    trocar_papeis([p for p in perfis_originais if p != papel_campo])
    t = esperar(lambda: req("GET", "/api/pdca/cronogramas/", token=campo)[0] == 403)
    check(f"sem o papel, o MESMO token perde o cronograma em {t} s", t is not None)
    trocar_papeis(perfis_originais)
    t = esperar(lambda: req("GET", "/api/pdca/cronogramas/", token=campo)[0] == 200)
    check(f"com o papel de volta, lê de novo em {t} s", t is not None)
    trocar_papeis([p for p in perfis_originais if p != papel_campo])
    esperar(lambda: req("GET", "/api/pdca/cronogramas/", token=campo)[0] == 403)
    manage("modo_autorizacao", "pdca", "token")
    t = esperar(lambda: req("GET", "/api/pdca/cronogramas/", token=campo)[0] == 200, limite=10)
    check(f"a volta ao token vale em {t} s: o token velho ainda concede, como antes da virada",
          t is not None)
    st, _ = req("GET", "/api/pdca/cronogramas/", token=pessoas["semdrone"])
    check(f"quem nunca teve o PDCA continua sem ({st})", st == 403)
finally:
    trocar_papeis(perfis_originais)
    try:
        manage("modo_autorizacao", "pdca", "token")
    except Exception as exc:  # noqa: BLE001
        print(f"  !! não consegui devolver o PDCA ao token: {exc}")

total = sum(1 for p in passed if p)
print(f"\n  Resultado: {total}/{len(passed)}")
sys.exit(0 if total == len(passed) else 1)
