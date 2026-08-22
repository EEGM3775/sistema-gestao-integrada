"""Fase 10.8 — auth serviço→serviço (JWT de serviço da IAM) + auth do WebSocket.

Fecha duas pendências antigas:
  • Fase 3 — ao excluir obra/empreendimento, o backend desvincula (soft) no drone
    os projetos órfãos. Não pode forjar token (só a IAM assina): pede um JWT de
    SERVIÇO à IAM (/auth/service-token/, segredo compartilhado) e chama o drone.
  • Fase 1 — o handshake STOMP do /ws era permitAll. Agora o frame CONNECT exige
    o access token da IAM (header STOMP Authorization); sem token / sem o módulo
    drone → CONNECT recusado (frame ERROR).

Prova (stack de pé, imagens IAM e java-service REBUILDADAS):
  1. /auth/service-token/ NÃO é público (bloqueado na borda → 404): é endpoint
     interno (backend→IAM na rede do compose). A emissão em si é coberta pelo
     teste de unidade da IAM (identity.tests.ServiceTokenTests).
  2. O endpoint de desvínculo do drone (/odm-api/projects/links/obra/{id}) é
     gateado pelo módulo drone: sem token → 401; com um token da IAM com o módulo
     drone → 200 (o token de serviço é exatamente isso — um JWT da IAM com drone).
  3. WS: CONNECT sem Authorization → ERROR; CONNECT com o access do demo → CONNECTED.

Rodar (stack de pé):  python testes/e2e/phase10_8_service_ws_test.py
"""
import json, os, socket, sys, base64, struct, urllib.request, urllib.error

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")  # SGI_GW aponta ao staging (10.7)
# O frame WebSocket usa socket cru (sem TLS): sob o gateway HTTPS de staging aponte
# para um listener em claro, ou valide o /ws separadamente (ver infra/staging/README.md).
WS_HOST = os.environ.get("SGI_WS_HOST", "localhost")
WS_PORT = int(os.environ.get("SGI_WS_PORT", "8090"))
# O handshake só passa se o Origin constar em `app.cors.allowed-origins` do drone
# (APP_CORS_ALLOWED_ORIGINS) — senão o java-service devolve 403 ANTES do upgrade.
# Default = origem do gateway de dev; no staging aponte à origem do gateway HTTPS.
WS_ORIGIN = os.environ.get("SGI_WS_ORIGIN", "http://localhost:8090")

passed = []
def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")

def req(method, path, token=None, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    if headers:
        h.update(headers)
    r = urllib.request.Request(GW + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            payload = resp.read().decode() or "null"
            return resp.status, json.loads(payload)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except Exception:
            return e.code, None

def login(u, p):
    data = json.dumps({"username": u, "password": p}).encode()
    r = urllib.request.Request(GW + "/auth/login/", data=data, method="POST",
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.load(resp)["access"]

# --- Cliente WebSocket + STOMP mínimo (stdlib) --------------------------------
def stomp_connect(auth_token):
    """Abre o WS nativo em /ws/websocket e envia um frame STOMP CONNECT.
    Devolve o comando do frame de resposta: 'CONNECTED' (aceito) ou 'ERROR'."""
    key = base64.b64encode(os.urandom(16)).decode()
    handshake = (
        f"GET /ws/websocket HTTP/1.1\r\nHost: {WS_HOST}:{WS_PORT}\r\n"
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
        f"Origin: {WS_ORIGIN}\r\n\r\n"
    )
    s = socket.create_connection((WS_HOST, WS_PORT), timeout=15)
    try:
        s.sendall(handshake.encode())
        resp = s.recv(4096).decode(errors="replace")
        if "101" not in resp.split("\r\n", 1)[0]:
            return f"NO_UPGRADE({resp.splitlines()[0] if resp else 'vazio'})"
        hdrs = "\naccept-version:1.2\nhost:localhost\n"
        if auth_token:
            hdrs = f"\naccept-version:1.2\nhost:localhost\nAuthorization:Bearer {auth_token}\n"
        _ws_send_text(s, f"CONNECT{hdrs}\n\x00")
        return _stomp_command(_ws_recv_text(s))
    finally:
        s.close()

def _ws_send_text(s, text):
    payload = text.encode()
    header = bytearray([0x81])  # FIN + text frame
    mask = os.urandom(4)
    n = len(payload)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126); header += struct.pack(">H", n)
    else:
        header.append(0x80 | 127); header += struct.pack(">Q", n)
    header += mask
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    s.sendall(bytes(header) + masked)

def _ws_recv_text(s):
    b0 = s.recv(1)
    if not b0:
        return ""
    b1 = s.recv(1)[0]
    length = b1 & 0x7F
    if length == 126:
        length = struct.unpack(">H", s.recv(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", s.recv(8))[0]
    data = b""
    while len(data) < length:
        chunk = s.recv(length - len(data))
        if not chunk:
            break
        data += chunk
    return data.decode(errors="replace")

def _stomp_command(frame):
    return (frame or "").lstrip().split("\n", 1)[0].strip() or "VAZIO"

demo = login("demo", "demo123")

# --- 1) /auth/service-token/ é interno: não vaza pela borda -------------------
print("== 1) /auth/service-token/ não é público (bloqueado na borda) ==")
status, _ = req("POST", "/auth/service-token/", body={"tenant_id": "x"},
                headers={"X-Service-Secret": "irrelevante"})
check(f"/auth/service-token/ -> {status} (esperado 404 na borda)", status == 404)
status, _ = req("POST", "/iam/auth/service-token/", body={"tenant_id": "x"},
                headers={"X-Service-Secret": "irrelevante"})
check(f"/iam/auth/service-token/ -> {status} (esperado 404 na borda)", status == 404)

# --- 2) Desvínculo no drone é gateado pelo módulo drone -----------------------
# O token de serviço é um JWT da IAM com o módulo drone; o access do demo (que
# tem o módulo drone) exerce o mesmo caminho de aceitação no drone.
print("== 2) Drone: endpoint de desvínculo gateado pelo módulo drone ==")
status, _ = req("DELETE", "/odm-api/projects/links/obra/999999")
check(f"desvínculo SEM token -> {status} (esperado 401)", status == 401)
status, body = req("DELETE", "/odm-api/projects/links/obra/999999", token=demo)
check(f"desvínculo com token (módulo drone) -> {status} (esperado 200)", status == 200)
check("resposta traz 'unlinked'", isinstance(body, dict) and "unlinked" in body)

# --- 3) WebSocket CONNECT exige o token ---------------------------------------
print("== 3) WebSocket /ws — CONNECT exige token da IAM ==")
sem = stomp_connect(None)
check(f"CONNECT sem token -> {sem} (esperado ERROR)", sem == "ERROR")
com = stomp_connect(demo)
check(f"CONNECT com token do demo -> {com} (esperado CONNECTED)", com == "CONNECTED")

print()
if all(passed):
    print(f"RESULTADO: TODOS OS {len(passed)} CHECKS PASSARAM ✅ (serviço→serviço + WS auth)")
else:
    print(f"RESULTADO: {passed.count(False)}/{len(passed)} FALHARAM ❌")
    raise SystemExit(1)
