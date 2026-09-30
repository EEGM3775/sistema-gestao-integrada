"""A sessão nos roteiros — o BFF da fase 5 (docs/acesso-e-permissoes.md §10.5).

Desde a fase 5 o login não devolve token: devolve os cookies HttpOnly da sessão,
e é o gateway que troca o cookie pelo access de cada serviço. Os roteiros fazem o
que o navegador faz — guardam o cookie da sessão e o mandam de volta, com o
cabeçalho anti-CSRF que o gateway exige na escrita:

    sessao = da_resposta(resp)                 # depois do POST /auth/login/
    urllib.request.Request(url, headers=cabecalhos(sessao))

Quem precisa **ver** o token (o que o gateway injetaria no serviço) usa
`access_do_bff`, que pergunta à IAM por dentro da rede dos contêineres — a porta
que a borda não expõe.

No staging (HTTPS) o cookie se chama `__Host-sgi_sessao`: `SGI_SESSAO_COOKIE`.
"""
import json
import os
import subprocess
from http.cookies import SimpleCookie

NOME = os.getenv("SGI_SESSAO_COOKIE", "sgi_sessao")
ANTI_CSRF = {"X-SGI-CSRF": "1"}


def _set_cookies(resp) -> list[str]:
    cabecalhos_ = resp if hasattr(resp, "get_all") else getattr(resp, "headers", None)
    if cabecalhos_ is None:
        return []
    if hasattr(cabecalhos_, "get_all"):  # urllib
        return cabecalhos_.get_all("Set-Cookie") or []
    bruto = getattr(getattr(resp, "raw", None), "headers", None)  # requests
    if bruto is not None and hasattr(bruto, "getlist"):
        return bruto.getlist("Set-Cookie")
    valor = cabecalhos_.get("Set-Cookie")
    return [valor] if valor else []


def da_resposta(resp) -> str | None:
    """A credencial do cookie da sessão numa resposta de login (urllib ou requests)
    ou nos cabeçalhos dela."""
    for linha in _set_cookies(resp):
        biscoito = SimpleCookie()
        biscoito.load(linha)
        if NOME in biscoito and biscoito[NOME].value:
            return biscoito[NOME].value
    return None


def cabecalhos(sessao: str | None, **extra) -> dict:
    """O que o navegador mandaria: o cookie da sessão e o anti-CSRF."""
    h = dict(ANTI_CSRF)
    if sessao:
        h["Cookie"] = f"{NOME}={sessao}"
    h.update(extra)
    return h


def access_do_bff(sessao: str, servico: str = "api", conteiner: str = "sgi-iam") -> str | None:
    """O access que o gateway injetaria em `/api/` (`api`) ou `/odm-api/` (`drone`).

    Pergunta à IAM por dentro do contêiner, como o `auth_request` do gateway.
    Só para os roteiros que conferem o conteúdo do token."""
    script = (
        "import urllib.request,sys;"
        f"r=urllib.request.Request('http://localhost:8001/auth/interno/bff/{servico}/',"
        f"headers={{'Cookie':'{NOME}='+sys.argv[1],'Host':'localhost'}});"
        "print(urllib.request.urlopen(r,timeout=10).headers.get('X-BFF-Authorization',''))"
    )
    saida = subprocess.run(
        ["docker", "exec", conteiner, "python", "-c", script, sessao],
        capture_output=True, text=True, timeout=30,
    )
    valor = (saida.stdout or "").strip()
    return valor.removeprefix("Bearer ") or None


def direto(url: str, token: str, conteiner: str = "sgi-erp") -> int:
    """Chama um serviço **sem passar pelo gateway**, com o token na mão — o
    status HTTP. É o jeito de provar que o serviço (e não só a borda) recusa um
    access revogado: pelo gateway, o cliente nem consegue mandar token.
    `http://localhost:8000/api/...` é o backend; `http://java-service:8080/api/v1/...`, o drone."""
    script = (
        "import urllib.request,urllib.error,sys\n"
        "r=urllib.request.Request(sys.argv[1],headers={'Authorization':'Bearer '+sys.argv[2],'Host':'localhost'})\n"
        "try:\n  print(urllib.request.urlopen(r,timeout=15).status)\n"
        "except urllib.error.HTTPError as e:\n  print(e.code)\n"
    )
    saida = subprocess.run(
        ["docker", "exec", conteiner, "python", "-c", script, url, token],
        capture_output=True, text=True, timeout=60,
    )
    valor = (saida.stdout or "").strip().splitlines()
    return int(valor[-1]) if valor and valor[-1].isdigit() else -1


def carga(token: str) -> dict:
    import base64

    parte = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4)))
