#!/usr/bin/env python3
"""
Proxy mínimo dedicado ao webhook do Asaas — usado para reduzir a superfície
exposta pelo túnel ngrok persistente a um único endpoint (ver
docs/modulos/funcoescobrancas.md, seção "Túnel ngrok persistente"):

- Só repassa `POST /api/erp/cobrancas/webhook/asaas/`; qualquer outro
  caminho/método recebe 404 — nada mais do gateway fica alcançável por aqui,
  mesmo que a URL do túnel vaze.
- Chamadas com o `asaas-access-token` correto (o mesmo que a view Django já
  valida) passam direto — é o tráfego real do Asaas.
- Chamadas SEM o token correto caem num desafio HTTP Basic Auth genérico:
  quem não tiver as credenciais recebe um 401 "Basic" anônimo, sem nenhuma
  pista de que há um Django/DRF/backend por trás (muro de obscuridade — reduz
  fingerprinting por scanners de internet).

Aponte o ngrok para cá em vez do gateway inteiro:
    ngrok http 8091   (em vez de `ngrok http 8090`)

Variáveis de ambiente (lidas do `.env` da raiz — exporte antes de rodar):
    WEBHOOK_PROXY_PORT        porta local do proxy (padrão 8091)
    WEBHOOK_UPSTREAM_URL      URL real do endpoint (padrão: gateway em :8090)
    ASAAS_WEBHOOK_TOKEN       mesmo token da view (.../cobrancas/webhook/asaas/)
    WEBHOOK_PROXY_BASIC_USER  usuário do muro de Basic Auth
    WEBHOOK_PROXY_BASIC_PASS  senha do muro de Basic Auth
"""
import base64
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("WEBHOOK_PROXY_PORT", "8091"))
UPSTREAM = os.environ.get(
    "WEBHOOK_UPSTREAM_URL",
    "http://localhost:8090/api/erp/cobrancas/webhook/asaas/",
)
WEBHOOK_TOKEN = os.environ.get("ASAAS_WEBHOOK_TOKEN", "")
BASIC_USER = os.environ.get("WEBHOOK_PROXY_BASIC_USER", "")
BASIC_PASS = os.environ.get("WEBHOOK_PROXY_BASIC_PASS", "")
ALLOWED_PATH = "/api/erp/cobrancas/webhook/asaas/"


def _basic_auth_ok(header_value):
    if not header_value or not header_value.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header_value[6:]).decode("utf-8")
        user, _, password = decoded.partition(":")
    except Exception:
        return False
    return user == BASIC_USER and password == BASIC_PASS


class Handler(BaseHTTPRequestHandler):
    server_version = "WebhookProxy/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[webhook-proxy] " + (fmt % args) + "\n")

    def do_POST(self):
        if self.path != ALLOWED_PATH:
            return self._not_found()

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        token = self.headers.get("asaas-access-token", "")

        if token != WEBHOOK_TOKEN and not _basic_auth_ok(self.headers.get("Authorization")):
            return self._require_basic_auth()

        self._forward(body, token)

    def do_GET(self):
        self._not_found()

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_GET

    def _forward(self, body, token):
        req = urllib.request.Request(
            UPSTREAM,
            data=body,
            method="POST",
            headers={
                "Content-Type": self.headers.get("Content-Type", "application/json"),
                "asaas-access-token": token,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self._respond(resp.status, resp.read(), resp.getheader("Content-Type"))
        except urllib.error.HTTPError as exc:
            self._respond(exc.code, exc.read(), exc.headers.get("Content-Type"))
        except urllib.error.URLError as exc:
            self.log_message("upstream indisponível: %s", exc)
            self._respond(502, b'{"detail": "upstream indisponivel"}', "application/json")

    def _respond(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type or "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self):
        self._respond(404, b"", "text/plain")

    def _require_basic_auth(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="restricted"')
        self.send_header("Content-Length", "0")
        self.end_headers()


def main():
    if not WEBHOOK_TOKEN:
        sys.exit("ASAAS_WEBHOOK_TOKEN não definido — abortando (o atalho do token real não funcionaria).")
    if not (BASIC_USER and BASIC_PASS):
        sys.exit("WEBHOOK_PROXY_BASIC_USER/WEBHOOK_PROXY_BASIC_PASS não definidos — abortando (sem o muro de Basic Auth).")

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[webhook-proxy] ouvindo em http://127.0.0.1:{PORT}{ALLOWED_PATH} -> {UPSTREAM}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
