"""Helper do E2E do D11: lê a caixa do Mailpit.

Uso:
  python3 d11_mailpit_helper.py resumo  -> "destino|tem_link" por mensagem
  python3 d11_mailpit_helper.py token   -> token da mensagem que contém o link

A base vem de MAILPIT_BASE para o roteiro servir aos dois ambientes (dev :8025,
staging :8026) — o mesmo motivo que tornou o gateway parametrizável no .sh.
"""
import json
import os
import sys
import urllib.request

BASE = os.getenv("MAILPIT_BASE", "http://localhost:8025")


def _mensagens():
    d = json.load(urllib.request.urlopen(BASE + "/api/v1/messages?limit=30"))
    for m in d.get("messages", []):
        yield json.load(urllib.request.urlopen(BASE + "/api/v1/message/" + m["ID"]))


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "resumo"
    for full in _mensagens():
        texto = full["Text"]
        if modo == "resumo":
            tem = "sim" if "token=" in texto else "nao"
            print(full["To"][0]["Address"] + "|" + tem)
        elif modo == "token" and "token=" in texto:
            print(texto.split("token=")[1].split()[0])
            break
