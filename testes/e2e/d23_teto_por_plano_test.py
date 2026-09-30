#!/usr/bin/env python3
"""E2E do D23 — o teto de requisições vem do PLANO e chega ao backend.

Roda contra o stack vivo, pelo gateway. Prova a cadeia inteira, que os testes de
unidade não cobrem: IAM lê o plano do tenant -> calcula o teto -> publica na ficha
da empresa (desde a fase 4 da remodelagem o teto não viaja mais no token) ->
backend lê a ficha -> usa como teto do eixo por tenant -> devolve
`X-RateLimit-*`. O teto esperado vem do `/auth/me/`, que a tela também lê; a
ficha chega ao backend em até `ESPERA_S` (o cache dela é de 30 s por processo).

Uso:  python3 d23_teto_por_plano_test.py
Env:  SGI_GW (default http://localhost:8090), SGI_IAM_CONTAINER (default sgi-iam)

Restaura o plano original do tenant no fim, inclusive se algo falhar.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from _sessao import cabecalhos, da_resposta
from _segundo_fator import entrar

GW = os.getenv("SGI_GW", "http://localhost:8090").rstrip("/")
IAM_CONTAINER = os.getenv("SGI_IAM_CONTAINER", "sgi-iam")
USUARIO, SENHA = "demo", "demo123"
ESPERA_S = 40

falhas: list[str] = []


def checar(nome: str, condicao: bool, detalhe: str = "") -> None:
    print(f"  {'OK  ' if condicao else 'FALHA'}  {nome}{(' — ' + detalhe) if detalhe else ''}")
    if not condicao:
        falhas.append(nome)


def _post(caminho: str, corpo: dict) -> tuple[int, dict, dict]:
    req = urllib.request.Request(
        f"{GW}{caminho}",
        data=json.dumps(corpo).encode(),
        headers={"Content-Type": "application/json", "Origin": GW},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, {}, dict(e.headers)


def _get(caminho: str, token: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{GW}{caminho}", headers=cabecalhos(token)
    )
    try:
        with urllib.request.urlopen(req) as r:
            r.read()
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)


def claims(token: str) -> dict:
    """O plano e o teto como a IAM os calcula — o corpo do `/auth/me/`."""
    req = urllib.request.Request(f"{GW}/auth/me/", headers=cabecalhos(token))
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def teto_no_backend(token: str, esperado: int) -> tuple[int, dict]:
    """Espera a ficha nova chegar ao backend; devolve a última resposta."""
    fim = time.monotonic() + ESPERA_S
    while True:
        status, headers = _get("/api/notificacoes/", token)
        if headers.get("X-RateLimit-Limit") == str(esperado) or time.monotonic() > fim:
            return status, headers
        time.sleep(2)


def login() -> str:
    sessao = entrar(GW, USUARIO, SENHA)  # o cookie da sessão (BFF, fase 5)
    if not sessao:
        print(f"login falhou — a stack está no ar? {GW}")
        sys.exit(2)
    return sessao


def definir_plano(slug: str | None) -> None:
    """Muda o plano do tenant demo direto no shell da IAM (não há endpoint —
    o provisionamento por plano é o D24). Por `save()`, como a tela e o admin:
    é o sinal que publica a ficha na hora; um `update()` só chegaria ao backend
    na volta periódica do `iam-pdp`."""
    codigo = (
        "from identity.models import Tenant; "
        "t = Tenant.objects.get(slug='demo'); "
        f"t.plano = {slug!r}; t.save()"
    )
    subprocess.run(
        ["docker", "exec", IAM_CONTAINER, "python", "manage.py", "shell", "-c", codigo],
        check=True, capture_output=True,
    )


def main() -> int:
    print(f"D23 — teto por plano, E2E pelo gateway ({GW})\n")

    # O `shell -c` imprime um banner ("N objects imported automatically...") ANTES
    # da saída do código. Ler o stdout cru faria o restore gravar o banner como
    # nome do plano — foi o que aconteceu na 1ª execução. Daí o marcador.
    saida = subprocess.run(
        ["docker", "exec", IAM_CONTAINER, "python", "manage.py", "shell", "-c",
         "from identity.models import Tenant; "
         "print('PLANO=' + (Tenant.objects.get(slug='demo').plano or ''))"],
        check=True, capture_output=True, text=True,
    ).stdout
    original = next(
        (l[len("PLANO="):].strip() for l in saida.splitlines() if l.startswith("PLANO=")),
        "",
    )

    try:
        # 1. Sem plano definido -> free (o default seguro).
        definir_plano(None)
        c = claims(login())
        checar("tenant sem assinatura cai no plano free", c.get("plano") == "free",
               f"plano={c.get('plano')}")
        teto_free = c.get("rate_hora")
        checar("a IAM calcula o teto do plano (rate_hora)", isinstance(teto_free, int),
               f"rate_hora={teto_free}")

        # 2. Upgrade de plano -> teto maior no MESMO tenant.
        definir_plano("empresarial")
        c = claims(login())
        teto_emp = c.get("rate_hora")
        checar("plano empresarial recebe teto maior que o free",
               isinstance(teto_emp, int) and teto_emp > teto_free,
               f"free={teto_free} < empresarial={teto_emp}")

        # 3. O backend USA o teto: os headers refletem o do plano vigente.
        token = login()
        status, headers = teto_no_backend(token, teto_emp)
        checar("backend responde 200 com o token do plano", status == 200, f"status={status}")
        checar("X-RateLimit-Limit reflete o teto do plano",
               headers.get("X-RateLimit-Limit") == str(teto_emp),
               f"header={headers.get('X-RateLimit-Limit')} teto={teto_emp}")
        checar("X-RateLimit-Remaining presente e coerente",
               headers.get("X-RateLimit-Remaining", "").isdigit()
               and int(headers["X-RateLimit-Remaining"]) < teto_emp,
               f"restante={headers.get('X-RateLimit-Remaining')}")
        checar("X-RateLimit-Reset presente",
               headers.get("X-RateLimit-Reset", "").isdigit(),
               f"reset={headers.get('X-RateLimit-Reset')}")

        # 4. Downgrade volta a valer no token seguinte (propagação por refresh).
        definir_plano("essencial")
        teto_ess = claims(login()).get("rate_hora")
        checar("downgrade reduz o teto calculado",
               isinstance(teto_ess, int) and teto_ess < teto_emp,
               f"essencial={teto_ess} < empresarial={teto_emp}")
        _, headers = teto_no_backend(token, teto_ess)
        checar("o MESMO token passa a ter o teto menor no backend (a ficha, não o token)",
               headers.get("X-RateLimit-Limit") == str(teto_ess),
               f"header={headers.get('X-RateLimit-Limit')} teto={teto_ess}")
    finally:
        definir_plano(original or None)
        print(f"\n  (plano do tenant demo restaurado para {original or 'None'})")

    print()
    if falhas:
        print(f"FALHOU — {len(falhas)} checagem(ns): {', '.join(falhas)}")
        return 1
    print("TUDO VERDE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
