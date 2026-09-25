"""O segundo fator nos roteiros (remodelagem da segurança, fase 1).

`admin` e `dono` são obrigados a ter segundo fator, e na demo nascem com um
segredo TOTP conhecido (`testes/seeds/seed_demo.py`, o mesmo valor daqui). Os roteiros
não sabem nada disso: trocam o `json.load(resp)["access"]` do login por
`completar_login(GW, json.load(resp))`, e este módulo responde a segunda etapa
quando ela vem.

O código é calculado aqui, só com a biblioteca padrão (RFC 6238), para o roteiro
rodar no Python do sistema sem instalar nada.
"""
import base64
import hashlib
import hmac
import json
import struct
import time
import urllib.error
import urllib.request

#: O mesmo de `testes/seeds/seed_demo.py`. Só vale para a demo.
SEGREDO_TOTP_DEMO = "GXW6RXK3CRP7C6FM3L25R55B6YAE72T5"
PASSO_S = 30


def codigo(deslocamento: int = 0, segredo: str = SEGREDO_TOTP_DEMO) -> str:
    """O código que o app mostraria agora (ou no passo vizinho)."""
    chave = base64.b32decode(segredo + "=" * (-len(segredo) % 8))
    passo = int(time.time() // PASSO_S) + deslocamento
    mac = hmac.new(chave, struct.pack(">Q", passo), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    return f"{(struct.unpack('>I', mac[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def _post(gw, caminho, corpo, contexto):
    r = urllib.request.Request(
        gw + caminho, data=json.dumps(corpo).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=30, context=contexto) as resp:
        return json.load(resp)


def completar_login(gw: str, corpo: dict, contexto=None) -> dict:
    """Recebe o JSON de `/auth/login/` e devolve o de uma sessão.

    O código de um passo só vale uma vez por conta (anti-reuso). Se outro
    roteiro acabou de entrar com a mesma conta, o do passo atual já foi gasto —
    e o do passo seguinte também é aceito agora, pela tolerância de um passo.
    Se os dois foram gastos, espera o passo virar."""
    if corpo.get("segundo_fator") != "codigo":
        return corpo
    tentativas = [0, 1, "esperar"]
    erro = None
    for t in tentativas:
        if t == "esperar":
            time.sleep(PASSO_S - time.time() % PASSO_S + 1)
            t = 1
        try:
            return _post(gw, "/auth/login/segundo-fator/", {"desafio": corpo["desafio"], "codigo": codigo(t)}, contexto)
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            erro = e
    raise erro


def responder_no_navegador(pagina) -> None:
    """Depois de clicar em Entrar: se a tela pediu o código (conta com segundo
    fator), digita; se já entrou, não faz nada."""
    fim = time.time() + 20
    while time.time() < fim:
        if "/login" not in pagina.url:
            return
        if pagina.locator("input#codigo-segundo-fator").count():
            break
        pagina.wait_for_timeout(200)
    else:
        return
    for tentativa in range(2):
        pagina.fill("input#codigo-segundo-fator", codigo(1))
        pagina.click("button[type=submit]")
        try:
            pagina.wait_for_url(lambda url: "/login" not in url, timeout=6_000)
            return
        except Exception:
            if tentativa:
                raise
            # O código deste passo já foi gasto pela mesma conta: espera virar.
            time.sleep(PASSO_S - time.time() % PASSO_S + 1)
