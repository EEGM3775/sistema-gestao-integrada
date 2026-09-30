"""Remodelagem da segurança, fase 6 — testes de caos: o modo de falha é o declarado (§10.8).

Derruba de propósito o PDP (SpiceDB), o Redis e a IAM do stack de dev, um de
cada vez e juntos, e confere que cada classe de ação falha como a planta diz:

| Fora             | Leitura comum (A)                | Sensível (B)           | Ato grave (C) |
|------------------|----------------------------------|------------------------|---------------|
| PDP              | serve o cache até 60 s; depois nega | até 5 s; depois nega | nega na hora  |
| Redis            | pergunta direto ao PDP (passa)   | idem                   | idem          |
| PDP e Redis      | nega                             | nega                   | nega          |
| IAM (o BFF)      | o gateway não injeta token: nada passa (5xx), nada vaza (nunca 200) |

E a sessão com o Redis fora: o logout ainda derruba o access em segundos — o
PEP pergunta à IAM (classe B do `sid`).

**Derruba contêineres compartilhados do dev** (sgi-spicedb, sgi-redis, sgi-iam):
não rode junto de outro roteiro. Tudo volta no `finally`, e o roteiro espera
cada um ficar saudável antes de terminar.

Rodar: python3 testes/e2e/seg6_caos_test.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

from _segundo_fator import entrar
from _sessao import access_do_bff, cabecalhos, direto

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")
PREFIXO = os.environ.get("SGI_PREFIX", "sgi")
PDP, REDIS, IAM = f"{PREFIXO}-spicedb", f"{PREFIXO}-redis", f"{PREFIXO}-iam"
TTL_A, TTL_B = 60, 5  # funcoesautorizacao/classes.py — o pior caso com o invalidador fora
passed = []
parados = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def status(method, path, sessao=None):
    r = urllib.request.Request(GW + path, method=method, headers=cabecalhos(sessao) if sessao else {})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return -1


def docker(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=180)


def saudavel(nome):
    r = docker("inspect", "-f", "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}", nome)
    return r.stdout.strip() in ("healthy", "running")


def parar(nome):
    docker("stop", "-t", "5", nome)
    parados.append(nome)


def subir(nome, limite=180):
    docker("start", nome)
    if nome in parados:
        parados.remove(nome)
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if saudavel(nome):
            return True
        time.sleep(2)
    return False


def esperar(condicao, limite):
    inicio = time.monotonic()
    while time.monotonic() - inicio < limite:
        if condicao():
            return round(time.monotonic() - inicio, 1)
        time.sleep(1)
    return None


LEITURA_A = "/api/clientes/"          # cadastro.cliente.view — classe A
LEITURA_B = "/api/erp/transacoes/"     # erp.transacao.view — classe B (o RH só confere o módulo, A)

print(f"\n{'='*62}\nFase 6 — caos: PDP, Redis e IAM fora\n{'='*62}\nGateway: {GW}")
demo = entrar(GW, "demo", "demo123")
admin = entrar(GW, "admin", "admin123")
if not (demo and admin):
    print("  !! sem as sessões da demo")
    sys.exit(2)
st, corpo = 0, None
r = urllib.request.Request(GW + "/api/clientes/?page_size=1", headers=cabecalhos(admin))
with urllib.request.urlopen(r, timeout=30) as resp:
    corpo = json.loads(resp.read().decode())
cliente = (corpo.get("results", corpo) if isinstance(corpo, dict) else corpo)[0]["cliente_id"]
ATO_C = f"/api/lgpd/cliente/{cliente}/exportar/"  # plataforma.lgpd.exportar — classe C

try:
    # ------------------------------------------------------------ 0. de pé
    print("\n0. Tudo de pé")
    check("A: demo lê clientes (200)", status("GET", LEITURA_A, demo) == 200)
    check("B: demo lê o razão financeiro (200)", status("GET", LEITURA_B, demo) == 200)
    check("C: admin exporta dado pessoal (200)", status("GET", ATO_C, admin) == 200)

    # --------------------------------------------------------- 1. PDP fora
    print("\n1. PDP fora")
    status("GET", LEITURA_A, demo)  # aquece o cache da classe A
    parar(PDP)
    inicio = time.monotonic()
    check(f"C nega na hora ({status('GET', ATO_C, admin)})", status("GET", ATO_C, admin) == 403)
    check("A serve do cache enquanto ele vale (200)", status("GET", LEITURA_A, demo) == 200)
    time.sleep(TTL_B + 1)
    check(f"B nega depois de {TTL_B} s", status("GET", LEITURA_B, demo) == 403)
    time.sleep(max(0, TTL_A + 2 - (time.monotonic() - inicio)))
    check(f"A nega depois de {TTL_A} s", status("GET", LEITURA_A, demo) == 403)
    check("PDP de volta", subir(PDP))
    t = esperar(lambda: status("GET", LEITURA_A, demo) == 200, 90)
    check(f"e a leitura volta a passar em {t} s", t is not None)

    # ------------------------------------------------------- 2. Redis fora
    print("\n2. Redis fora")
    outra = entrar(GW, "demo", "demo123")
    token_outra = access_do_bff(outra, "api")
    parar(REDIS)
    t = esperar(lambda: status("GET", LEITURA_A, demo) == 200, 30)
    check(f"A pergunta direto ao PDP e passa ({t} s)", t is not None)
    check("B também (200)", status("GET", LEITURA_B, demo) == 200)
    check("C também — PDP de pé, consistência total (200)", status("GET", ATO_C, admin) == 200)
    check("logout com o Redis fora (200)", status("POST", "/auth/logout/", outra) == 200)
    t = esperar(lambda: direto("http://localhost:8000/api/clientes/", token_outra) == 401, 30)
    check(f"o access daquela sessão cai no backend em {t} s (o PEP pergunta à IAM)", t is not None)

    # ------------------------------------------------- 3. PDP e Redis fora
    print("\n3. PDP e Redis fora")
    parar(PDP)
    t = esperar(lambda: status("GET", LEITURA_A, demo) == 403, TTL_A + 10)
    check(f"A nega ({t} s)", t is not None)
    check("B nega", status("GET", LEITURA_B, demo) == 403)
    check("C nega", status("GET", ATO_C, admin) == 403)
    check("Redis de volta", subir(REDIS))
    check("PDP de volta", subir(PDP))
    t = esperar(lambda: status("GET", LEITURA_A, demo) == 200, 120)
    check(f"e tudo volta em {t} s", t is not None)

    # -------------------------------------------------- 4. IAM (o BFF) fora
    print("\n4. IAM fora — o gateway não tem como trocar o cookie")
    parar(IAM)
    time.sleep(2)
    st_a = status("GET", LEITURA_A, demo)
    check(f"a API não passa sem a IAM ({st_a}) — e nunca 200", st_a >= 500)
    st_l = status("POST", "/auth/login/")
    check(f"o login também não ({st_l})", st_l >= 500)
    check("IAM de volta", subir(IAM))
    t = esperar(lambda: status("GET", LEITURA_A, demo) == 200, 120)
    check(f"e a mesma sessão volta a passar em {t} s", t is not None)
finally:
    for nome in list(parados):
        print(f"  (restaurando {nome})")
        subir(nome)

total = sum(1 for x in passed if x)
print(f"\n  Resultado: {total}/{len(passed)}")
sys.exit(0 if total == len(passed) else 1)
