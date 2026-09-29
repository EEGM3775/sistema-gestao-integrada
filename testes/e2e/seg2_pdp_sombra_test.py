"""Remodelagem da segurança, fases 2 e 3 — o PDP de pé, a equivalência e a virada.

Até 25/09/2026 este roteiro comparava o token de cada pessoa com o PDP e virava o
PDCA para ver o mesmo token perder o acesso. Com a fase 4 o token deixou de
carregar lista — não há "token velho" a comparar —, e o que ele provava ficou
dividido assim:

  1. O PDP de pé     -> SpiceDB saudável, `iam-pdp` e `pdp-invalidador` rodando.
  2. A equivalência  -> a saída da fase 2, exaustiva: toda pessoa ativa, mais uma
                        empresa descartável com uma pessoa por papel de fábrica
                        (com e sem liberação de módulo), cada uma com todas as
                        perguntas — o PDP responde o que as tabelas da IAM dizem
                        (`manage.py conferir_equivalencia --papeis-de-fabrica`).
  3. A virada        -> todo módulo decidido pelo PDP (fase 3), espelhado no
                        Redis para o drone.

A revogação em segundos com o mesmo token (papel e logout, backend e drone) está
no `seg4_token_enxuto_test.py`.

Rodar (stack de pé):  python3 testes/e2e/seg2_pdp_sombra_test.py
"""
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PREFIXO = os.environ.get("SGI_PREFIX", "sgi")
passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def docker(*args, timeout=600):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def rodando(nome):
    r = docker("inspect", "-f", "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}",
               f"{PREFIXO}-{nome}")
    return r.stdout.strip()


print("\n1. O PDP de pé")
check("SpiceDB saudável", rodando("spicedb").endswith("healthy"))
check("iam-pdp rodando (reconciliação contínua)", rodando("iam-pdp").startswith("running"))
check("pdp-invalidador rodando (Watch)", rodando("pdp-invalidador").startswith("running"))

print("\n2. A equivalência — toda pessoa, todo papel de fábrica, toda pergunta")
r = docker("exec", f"{PREFIXO}-iam", "python", "manage.py", "conferir_equivalencia", "--papeis-de-fabrica")
resumo = next((json.loads(linha) for linha in r.stdout.splitlines() if linha.startswith("{")), None)
if resumo is None:
    print("       ", (r.stderr or r.stdout)[-400:])
check(
    f"zero divergência: {resumo and resumo['pessoas']} pessoa(s), {resumo and resumo['empresas']} empresa(s),"
    f" {resumo and resumo['perguntas']} pergunta(s)",
    r.returncode == 0 and resumo is not None and not resumo["divergentes"] and resumo["perguntas"] > 10_000,
)

print("\n3. A virada — todo módulo no PDP")
r = docker("exec", f"{PREFIXO}-erp", "python", "manage.py", "modo_autorizacao", timeout=120)
modos = dict(linha.split() for linha in r.stdout.splitlines() if len(linha.split()) == 2)
check(f"{len(modos)} módulo(s), todos decididos pelo PDP", modos and set(modos.values()) == {"pdp"})
r = docker("exec", f"{PREFIXO}-redis", "redis-cli", "-n", "5", "get", "authz:modo:drone")
check("o drone lê a virada no Redis", r.stdout.strip() == "pdp")

total = sum(1 for p in passed if p)
print(f"\n  Resultado: {total}/{len(passed)}")
sys.exit(0 if total == len(passed) else 1)
