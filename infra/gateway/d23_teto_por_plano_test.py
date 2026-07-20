#!/usr/bin/env python3
"""E2E do D23 — o teto de requisições vem do PLANO e chega ao backend.

Roda contra o stack vivo, pelo gateway. Prova a cadeia inteira, que os testes de
unidade não cobrem: IAM lê o plano do tenant -> calcula o teto -> assina no claim
`rate_hora` -> backend lê o claim -> usa como teto do eixo por tenant -> devolve
`X-RateLimit-*`.

Uso:  python3 d23_teto_por_plano_test.py
Env:  SGI_GW (default http://localhost:8090), SGI_IAM_CONTAINER (default sgi-iam)

Restaura o plano original do tenant no fim, inclusive se algo falhar.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

GW = os.getenv("SGI_GW", "http://localhost:8090").rstrip("/")
IAM_CONTAINER = os.getenv("SGI_IAM_CONTAINER", "sgi-iam")
USUARIO, SENHA = "demo", "demo123"

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
        f"{GW}{caminho}", headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req) as r:
            r.read()
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)


def claims(token: str) -> dict:
    """Decodifica o payload do JWT (sem validar — o backend é quem valida)."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def login() -> str:
    status, corpo, _ = _post("/auth/login/", {"username": USUARIO, "password": SENHA})
    if status != 200 or "access" not in corpo:
        print(f"login falhou ({status}) — a stack está no ar? {GW}")
        sys.exit(2)
    return corpo["access"]


def definir_plano(slug: str | None) -> None:
    """Muda o plano do tenant demo direto no shell da IAM (não há endpoint —
    o provisionamento por plano é o D24)."""
    codigo = (
        "from identity.models import Tenant; "
        f"Tenant.objects.filter(slug='demo').update(plano={slug!r})"
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
        checar("token carrega o teto (claim rate_hora)", isinstance(teto_free, int),
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
        status, headers = _get("/api/notificacoes/", token)
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
        checar("downgrade reduz o teto no token seguinte",
               isinstance(teto_ess, int) and teto_ess < teto_emp,
               f"essencial={teto_ess} < empresarial={teto_emp}")
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
