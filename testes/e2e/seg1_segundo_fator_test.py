"""Remodelagem da segurança, fase 1 — o segundo fator pelo gateway.

A suíte da IAM prova as regras chamando a view; aqui cada passo atravessa o
nginx (com a zona de limite própria da segunda etapa), o cookie HttpOnly do
refresh e a IAM de verdade, com os usuários da demo:

  admin / admin123 -> obrigado a ter segundo fator; nasce com o segredo da demo.
  demo  / demo123  -> não é obrigado. Liga o fator pela tela de perfil (API),
                      e no fim o admin o redefine — que é a limpeza do roteiro.

  1. O admin      -> a senha só devolve o desafio; código errado, código certo,
                     `amr` no token, refresh pelo cookie, desafio que não reabre.
  2. O comum      -> entra só com senha; liga o fator; passa a ser pedido.
  3. A redefinição -> o admin apaga o fator do demo, e o demo volta a entrar só
                     com a senha.

Rodar (stack de pé):  python3 testes/e2e/seg1_segundo_fator_test.py
"""
import base64
import hashlib
import hmac
import http.cookiejar
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request

from _segundo_fator import codigo as codigo_demo, completar_login
from _sessao import ANTI_CSRF, NOME, access_do_bff

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")
passed = []
limpar_demo = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def fatal(msg):
    print(f"\n  !! {msg}")
    print(f"     Parcial: {sum(1 for p in passed if p)}/{len(passed)}")
    sys.exit(2)


def navegador():
    """Um "navegador" com pote de cookies: o refresh e a sessão (BFF, fase 5)
    vivem em cookies HttpOnly, e é o pote que os manda de volta."""
    pote = http.cookiejar.CookieJar()
    abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(pote))
    abridor.pote = pote
    return abridor


def sessao_de(abridor):
    """O cookie da sessão que o "navegador" guardou, ou None."""
    return next((c.value for c in abridor.pote if c.name == NOME and c.value), None)


def amr_de(abridor):
    """O `amr` do access que o gateway injetaria para esta sessão."""
    sessao = sessao_de(abridor)
    token = access_do_bff(sessao) if sessao else None
    return carga(token).get("amr") if token else None


def req(abridor, method, path, body=None):
    headers = {"Content-Type": "application/json", **ANTI_CSRF}
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with abridor.open(r, timeout=30) as resp:
            corpo = resp.read().decode()
            return resp.status, (json.loads(corpo) if corpo else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except Exception:
            return e.code, None


def carga(token):
    parte = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4)))


def totp(segredo, deslocamento=0):
    chave = base64.b32decode(segredo + "=" * (-len(segredo) % 8))
    passo = int(time.time() // 30) + deslocamento
    mac = hmac.new(chave, struct.pack(">Q", passo), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    return f"{(struct.unpack('>I', mac[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def errado(certo):
    return "000000" if certo != "000000" else "111111"


print(f"\n{'='*62}\nSegundo fator pelo gateway (remodelagem, fase 1)\n{'='*62}")
print(f"Gateway: {GW}")

try:
    # ------------------------------------------------------------------
    print("\n1. O admin — obrigado a ter")
    # ------------------------------------------------------------------
    nav = navegador()
    st, corpo = req(nav, "POST", "/auth/login/", {"username": "admin", "password": "admin123"})
    if st != 200:
        fatal(f"login do admin respondeu {st}. Stack de pé? Seeds rodados?")
    check("a senha certa do admin NÃO abre sessão", sessao_de(nav) is None)
    check("devolve o desafio da etapa do código", corpo.get("segundo_fator") == "codigo" and corpo.get("desafio"))
    desafio = corpo["desafio"]

    st, r = req(nav, "POST", "/auth/login/segundo-fator/", {"desafio": desafio, "codigo": errado(codigo_demo())})
    check(f"código errado → 400 com frase ({st})", st == 400 and "incorreto" in (r or {}).get("detail", ""))

    sessao = None
    for d in (0, 1):
        st, r = req(nav, "POST", "/auth/login/segundo-fator/", {"desafio": desafio, "codigo": codigo_demo(d)})
        if st == 200:
            sessao = r
            break
    check("código certo → sessão (o cookie, sem token no corpo)",
          sessao is not None and sessao_de(nav) and "access" not in sessao)
    if sessao is None:
        fatal("sem sessão do admin, o resto não anda")
    check("o token diz como a sessão provou quem é: amr = senha + código", amr_de(nav) == ["pwd", "otp"])

    st, r = req(nav, "POST", "/auth/login/segundo-fator/", {"desafio": desafio, "codigo": codigo_demo(1)})
    check(f"o mesmo desafio não abre outra sessão ({st})", st == 401)

    st, r = req(nav, "POST", "/auth/refresh/")
    check(f"o refresh pelo cookie renova ({st})", st == 200)
    check("e preserva o amr", st == 200 and amr_de(nav) == ["pwd", "otp"])

    st, seg = req(nav, "GET", "/auth/conta/seguranca/")
    check("Minha conta: obrigatório e ativo", st == 200 and seg["segundo_fator"]["obrigatorio"] and seg["segundo_fator"]["ativo"])
    check("e a janela de confirmação começa no padrão do dono", st == 200 and seg["janela_confirmacao"]["minutos"] == seg["janela_confirmacao"]["padrao"])

    # ------------------------------------------------------------------
    print("\n2. O comum — opcional, pela tela de perfil")
    # ------------------------------------------------------------------
    nav_demo = navegador()
    st, corpo = req(nav_demo, "POST", "/auth/login/", {"username": "demo", "password": "demo123"})
    check(f"demo entra só com a senha ({st})", st == 200 and sessao_de(nav_demo))
    check("amr = só senha", amr_de(nav_demo) == ["pwd"])

    st, inicio = req(nav_demo, "POST", "/auth/segundo-fator/cadastro/", {})
    check(f"começar o cadastro devolve QR e chave ({st})", st == 200 and inicio["qr"].startswith("data:image/svg+xml") and inicio["segredo"])
    segredo = inicio["segredo"]
    st, fim = req(nav_demo, "POST", "/auth/segundo-fator/cadastro/confirmar/", {"codigo": totp(segredo)})
    check(f"o primeiro código certo liga o fator ({st})", st == 200)
    if st == 200:
        limpar_demo.append(True)
        check("devolve os 10 códigos de recuperação", len(fim.get("codigos", [])) == 10)
        check("e uma sessão nova com código", amr_de(nav_demo) == ["pwd", "otp"])

    st, corpo = req(navegador(), "POST", "/auth/login/", {"username": "demo", "password": "demo123"})
    check("agora a senha do demo também só devolve o desafio", st == 200 and corpo.get("segundo_fator") == "codigo")
    recuperado = navegador()
    st, r = req(recuperado, "POST", "/auth/login/segundo-fator/", {"desafio": corpo["desafio"], "codigo": fim["codigos"][0]})
    check(f"um código de recuperação entra ({st})", st == 200 and sessao_de(recuperado))
    check("e diz quantos restam", (r or {}).get("codigos_restantes") == 9)

    # ------------------------------------------------------------------
    print("\n2b. Trocar de celular — nunca sem fator (D241)")
    # ------------------------------------------------------------------
    st, r = req(nav, "POST", "/auth/segundo-fator/desativar/", {"senha": "admin123", "codigo": codigo_demo(1)})
    check(f"o admin, obrigado, não desativa ({st})", st == 409)
    st, troca = req(nav_demo, "POST", "/auth/segundo-fator/troca/", {"senha": "demo123", "codigo": totp(segredo, 1)})
    check(f"a troca começa com senha + código e devolve o QR novo ({st})",
          st == 200 and troca["qr"].startswith("data:image/svg+xml") and troca["segredo"] != segredo)
    st, seg = req(nav_demo, "GET", "/auth/conta/seguranca/")
    check("entre as duas etapas, o celular antigo continua sendo o fator", st == 200 and seg["segundo_fator"]["ativo"])
    novo = troca["segredo"] if st == 200 else segredo
    st, fim_troca = req(nav_demo, "POST", "/auth/segundo-fator/troca/confirmar/", {"codigo": totp(novo)})
    check(f"o código do celular novo troca o aparelho ({st})", st == 200 and len((fim_troca or {}).get("codigos", [])) == 10)
    check("e a sessão segue, com código", amr_de(nav_demo) == ["pwd", "otp"])
    st, corpo = req(navegador(), "POST", "/auth/login/", {"username": "demo", "password": "demo123"})
    antigo = totp(segredo, 1)
    if antigo != totp(novo, 1):
        st, r = req(navegador(), "POST", "/auth/login/segundo-fator/", {"desafio": corpo["desafio"], "codigo": antigo})
        check(f"o código do celular antigo não entra mais ({st})", st == 400)

    # ------------------------------------------------------------------
    print("\n3. A redefinição pelo admin — e a limpeza")
    # ------------------------------------------------------------------
    st, usuarios = req(nav, "GET", "/iam/usuarios/")
    alvo = next((u for u in (usuarios or []) if u["username"] == "demo"), None)
    check("a lista do admin mostra que o demo tem segundo fator", alvo is not None and alvo["segundo_fator_ativo"])
    st, r = req(nav, "POST", f"/iam/usuarios/{alvo['id']}/redefinir-segundo-fator/", {})
    check(f"o admin redefine ({st})", st == 200)
    if st == 200:
        limpar_demo.clear()
    de_novo = navegador()
    st, corpo = req(de_novo, "POST", "/auth/login/", {"username": "demo", "password": "demo123"})
    check("e o demo volta a entrar só com a senha", st == 200 and sessao_de(de_novo))
    eu = next((u for u in (usuarios or []) if u["username"] == "admin"), None)
    st, r = req(nav, "POST", f"/iam/usuarios/{eu['id']}/redefinir-segundo-fator/", {})
    check(f"ninguém redefine a própria conta por aqui ({st})", st == 400)
finally:
    if limpar_demo:
        # Última rede: o roteiro não pode deixar o demo com segundo fator — os
        # outros roteiros entram com ele só pela senha.
        print("\n  !! limpeza: o demo ficou com segundo fator; redefina pela tela de usuários.")

print(f"\n{'='*62}\nResultado: {sum(passed)}/{len(passed)}\n{'='*62}")
sys.exit(0 if all(passed) else 1)
