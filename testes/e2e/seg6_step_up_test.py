"""Remodelagem da segurança, fase 6 — o step-up do ato grave (acesso-e-permissoes.md §10.5, §10.8).

Uma sessão sequestrada navega, mas não paga. Pelo gateway, com o admin da demo
(que tem segundo fator):

  1. Na API         -> com a última prova de identidade velha (a sessão é
                       "envelhecida" no banco da IAM), mudar papel (IAM) e
                       exportar dado pessoal (backend) respondem 401 com o
                       desafio da RFC 9470; a senha não serve a quem tem segundo
                       fator; o código do app confirma, e o mesmo pedido passa.
  2. No navegador   -> criar um papel com a sessão velha abre "Confirme que é
                       você"; o código digitado conclui o que a pessoa pediu.

Limpeza: os papéis criados aqui são apagados, com ou sem falha.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

from _segundo_fator import PASSO_S, codigo, entrar, responder_no_navegador
from _sessao import NOME, cabecalhos

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")
IAM = os.environ.get("SGI_IAM_CONTAINER", "sgi-iam")
MARCA = "E2E step-up " + uuid.uuid4().hex[:6]
passed = []
criados = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def req(method, path, sessao, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(GW + path, data=data, method=method,
                               headers=cabecalhos(sessao, **{"Content-Type": "application/json"}))
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            texto = resp.read().decode() or "null"
            return resp.status, json.loads(texto), resp.headers
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null"), e.headers
        except Exception:
            return e.code, None, e.headers


def envelhecer(sessao, minutos=90):
    """A última prova de identidade desta sessão vira de `minutos` atrás (e o
    access guardado pelo BFF sai, para o próximo nascer com a hora velha)."""
    h = hashlib.sha256(sessao.encode()).hexdigest()
    codigo_py = (
        "from datetime import timedelta; from django.utils import timezone; "
        "from identity.models import Sessao; from identity import sessoes; "
        f"n = Sessao.objects.filter(credencial_hash='{h}').update(auth_time=timezone.now() - timedelta(minutes={minutos})); "
        f"sessoes.esquecer_tokens('{h}'); print(n)"
    )
    r = subprocess.run(["docker", "exec", IAM, "python", "manage.py", "shell", "-c", codigo_py],
                       capture_output=True, text=True, timeout=120)
    return r.stdout.strip().endswith("1")


def confirmar_com_codigo(sessao):
    """O código do app. O anti-reuso não aceita um passo igual ou anterior ao
    último usado pela conta (o login acabou de gastar um): tenta o do passo e o
    seguinte; se os dois já foram, espera o passo virar e usa o seguinte a ele."""
    for tentativa in (0, 1, "esperar"):
        if tentativa == "esperar":
            time.sleep(PASSO_S - time.time() % PASSO_S + 1)
            tentativa = 1
        st, corpo, _ = req("POST", "/auth/confirmar/", sessao, {"codigo": codigo(tentativa)})
        if st == 200:
            return st, corpo
    return st, corpo


def lista(corpo):
    return corpo.get("results", corpo) if isinstance(corpo, dict) else (corpo or [])


print(f"\n{'='*62}\nFase 6 — step-up do ato grave\n{'='*62}\nGateway: {GW}")
admin = entrar(GW, "admin", "admin123")
if not admin:
    print("  !! sem sessão do admin")
    sys.exit(2)

try:
    # ------------------------------------------------------------ 1. na API
    print("\n1. Na API")
    st, clientes, _ = req("GET", "/api/clientes/?page_size=1", admin)
    cliente_id = (lista(clientes) or [{}])[0].get("cliente_id")
    check(f"logo depois do login, criar papel passa ({MARCA} 1)",
          req("POST", "/iam/perfis/", admin, {"nome": MARCA + " 1", "permissoes": []})[0] == 201)
    check("envelhecer a sessão no banco da IAM", envelhecer(admin))

    st, corpo, cab = req("POST", "/iam/perfis/", admin, {"nome": MARCA + " 2", "permissoes": []})
    check(f"mudar papel com a prova velha → 401 ({st})",
          st == 401 and (corpo or {}).get("codigo") == "confirmacao_necessaria")
    check("com o desafio da RFC 9470 no WWW-Authenticate",
          'error="insufficient_user_authentication"' in (cab.get("WWW-Authenticate") or ""))
    if cliente_id:
        st, corpo, _ = req("GET", f"/api/lgpd/cliente/{cliente_id}/exportar/", admin)
        check(f"exportar dado pessoal (backend) com a prova velha → 401 ({st})",
              st == 401 and (corpo or {}).get("codigo") == "confirmacao_necessaria")
    st, clientes2, _ = req("GET", "/api/clientes/?page_size=1", admin)
    check("ler continua livre (200)", st == 200)

    st, estado, _ = req("GET", "/auth/confirmar/", admin)
    check(f"a tela sabe o que pedir: o código ({(estado or {}).get('metodo')})",
          st == 200 and estado.get("metodo") == "codigo")
    st, _, _ = req("POST", "/auth/confirmar/", admin, {"senha": "admin123"})
    check(f"a senha não basta a quem tem segundo fator ({st})", st == 400)
    st, _ = confirmar_com_codigo(admin)
    check(f"o código do app confirma ({st})", st == 200)

    st, corpo, _ = req("POST", "/iam/perfis/", admin, {"nome": MARCA + " 2", "permissoes": []})
    check(f"o mesmo pedido agora passa ({st})", st == 201)
    if cliente_id:
        st, _, _ = req("GET", f"/api/lgpd/cliente/{cliente_id}/exportar/", admin)
        check(f"e o backend também aceita ({st})", st == 200)

    # ------------------------------------------------------ 2. no navegador
    print("\n2. No navegador")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        nav = p.chromium.launch()
        # Certificado autoassinado do staging — ver o seg5_bff_test.py.
        contexto = nav.new_context(ignore_https_errors=os.getenv("SGI_ACEITAR_CERT_LOCAL") == "1")
        pagina = contexto.new_page()
        pagina.goto(f"{GW}/login")
        pagina.fill("input#username", "admin")
        pagina.fill("input#password", "admin123")
        pagina.click("button[type=submit]")
        responder_no_navegador(pagina)
        pagina.wait_for_url(lambda url: "/login" not in url, timeout=30_000)
        sessao_nav = next(c["value"] for c in contexto.cookies() if c["name"] == NOME)
        check("envelhecer a sessão do navegador", envelhecer(sessao_nav))

        pagina.goto(f"{GW}/app/admin/papeis")
        pagina.get_by_role("button", name="Novo papel").click()
        pagina.fill("input[placeholder='Ex: Analista Financeiro']", MARCA + " 3")
        pagina.click("button:has-text('Salvar papel')")
        dialogo = pagina.get_by_role("dialog", name="Confirme que é você")
        dialogo.wait_for(timeout=15_000)
        check("o ato grave abre 'Confirme que é você'", dialogo.is_visible())
        for tentativa in (0, 1, "esperar"):
            if tentativa == "esperar":  # ver confirmar_com_codigo
                time.sleep(PASSO_S - time.time() % PASSO_S + 1)
                tentativa = 1
            pagina.fill("#prova-confirmacao", codigo(tentativa))
            pagina.click("button:has-text('Confirmar e continuar')")
            try:
                dialogo.wait_for(state="hidden", timeout=6_000)
                break
            except Exception:
                continue
        pagina.get_by_text(MARCA + " 3").first.wait_for(timeout=15_000)
        check("e o papel pedido foi criado sem refazer nada", pagina.get_by_text(MARCA + " 3").count() > 0)
        nav.close()
finally:
    st, perfis, _ = req("GET", "/iam/perfis/", admin)
    for perfil in lista(perfis):
        if str(perfil.get("nome", "")).startswith(MARCA):
            req("DELETE", f"/iam/perfis/{perfil['id']}/", admin)

total = sum(1 for x in passed if x)
print(f"\n  Resultado: {total}/{len(passed)}")
sys.exit(0 if total == len(passed) else 1)
