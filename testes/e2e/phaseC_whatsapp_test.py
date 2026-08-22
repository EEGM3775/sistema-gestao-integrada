"""Fase 11.3 / Fase C — canal WhatsApp em Python (absorção do microsserviço Node).

Prova, no stack vivo e **pelo gateway** (:8090), que o webhook do WhatsApp foi
reabsorvido como app Django (`funcoeswhatsapp`) e roda ponta a ponta:

  borda (nginx /webhooks/ → backend) → view (HMAC da Meta, resolução de tenant por
  phone_number_id, idempotência) → fila (Celery/Redis) → worker (máquina de
  estados) → escrita in-process no ORM (Lead do modulocrm).

Fecha as pendências A2 (WhatsApp) e D1 (WhatsApp): sem `Token` legado, sem
callback Node→backend — o processamento é in-process sob `tenant_context`.

Checagens (todas via gateway, exceto setup/verificação de efeito colateral):
  1. GET handshake da Meta: verify_token certo → 200 + ecoa o challenge.
  2. GET handshake com verify_token errado → 403.
  3. POST de número (phone_number_id) desconhecido → 200 e descartado (sem vazar).
  4. POST com assinatura HMAC inválida → 403.
  5. POST válido sem mensagem (status de entrega) → 200 (nada a processar).
  6. Conversa de lead (3 POSTs assinados, telefone/ids únicos) → cada um 200 e, ao
     final, um Lead criado no tenant demo com nome e origem "WhatsApp".

O canal demo usa `access_token=''` → o cliente de saída ignora o envio (sem HTTP
à Meta), então o fluxo roda sem credencial real. O efeito colateral (Lead) é
verificado no banco via `docker exec sgi-erp` sob `rls_bypass` — o Lead nasce sem
`assigned_to` e o `BaseCrmViewSet` filtra a API por dono, logo não apareceria pela
API de um usuário comum; a checagem direta no ORM é a prova fiel e tenant-safe.

Rodar (stack de pé, imagem do backend com o app funcoeswhatsapp):
    python testes/e2e/phaseC_whatsapp_test.py
"""
import hashlib
import hmac
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = __import__("os").environ.get("SGI_GW", "http://localhost:8090")  # SGI_GW aponta ao staging (10.7)
WEBHOOK = "/webhooks/whatsapp"
# Container do backend para as checagens de efeito colateral no ORM (docker exec).
# Default = dev (sgi-erp); no staging o validate.sh exporta SGI_ERP_CONTAINER=sgi-stg-erp
# (senão o teste escreveria via gateway no banco de staging e checaria o lead no de dev).
ERP_CONTAINER = __import__("os").environ.get("SGI_ERP_CONTAINER", "sgi-erp")

# Credenciais do canal demo (mesmas do seed_demo_data.py).
PNID = "DEMO-WA-PNID"
APP_SECRET = "demo-wa-app-secret"
VERIFY_TOKEN = "demo-wa-verify-token"

# Identificadores únicos por execução (idempotência por message.id; telefone novo
# a cada corrida evita colidir com um lead de execução anterior).
RUN = str(int(time.time()))
PHONE = "5599" + RUN[-9:]
NAME = "TesteC Whatsapp"   # first_name="TesteC", last_name="Whatsapp"

passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


# ── HTTP pelo gateway ────────────────────────────────────────────────────────
def _do(req):
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def get(path):
    return _do(urllib.request.Request(GW + path, method="GET"))


def post(body_bytes, signature):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return _do(urllib.request.Request(GW + WEBHOOK, data=body_bytes, method="POST", headers=headers))


def sign(body_bytes, secret=APP_SECRET):
    return "sha256=" + hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()


# ── Payloads da Meta ─────────────────────────────────────────────────────────
def envelope(pnid, value_extra):
    value = {"metadata": {"phone_number_id": pnid}}
    value.update(value_extra)
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": value}]}]}


def text_message(pnid, from_num, texto, mid):
    msg = {"id": mid, "from": from_num, "type": "text", "text": {"body": texto}}
    return json.dumps(envelope(pnid, {"messages": [msg]})).encode()


def status_only(pnid):
    return json.dumps(envelope(pnid, {"statuses": [{"id": "st-1", "status": "delivered"}]})).encode()


# ── Verificação do efeito colateral no ORM (via container) ───────────────────
def erp_shell(code):
    """Roda `code` no shell Django do backend e devolve o stdout."""
    out = subprocess.run(
        ["docker", "exec", "-i", ERP_CONTAINER, "python", "manage.py", "shell", "-c", code],
        capture_output=True, text=True, timeout=120,
    )
    return out.stdout + out.stderr


def ensure_canal():
    """Garante o CanalWhatsApp demo (idempotente) e devolve o tenant_id."""
    code = (
        "from nucleo.tenancy import rls_bypass\n"
        "from nucleo.models import Tenant\n"
        "from funcoeswhatsapp.models import CanalWhatsApp\n"
        "with rls_bypass():\n"
        "    t,_=Tenant.objects.get_or_create(slug='demo', defaults={'nome':'Empresa Demo'})\n"
        "    CanalWhatsApp.objects.get_or_create(phone_number_id='%s', defaults=dict("
        "tenant=t, nome_exibicao='Demo WhatsApp', app_secret='%s', verify_token='%s', "
        "access_token='', ativo=True))\n"
        "    print('TENANT|%%s' %% t.id)\n" % (PNID, APP_SECRET, VERIFY_TOKEN)
    )
    for line in erp_shell(code).splitlines():
        if line.startswith("TENANT|"):
            return line.split("|", 1)[1].strip()
    return None


def find_lead():
    """Devolve (count, first_name, source) do lead do telefone desta corrida."""
    code = (
        "from nucleo.tenancy import rls_bypass\n"
        "from nucleo.models import Tenant\n"
        "from modulocrm.models import Lead\n"
        "with rls_bypass():\n"
        "    t=Tenant.objects.get(slug='demo')\n"
        "    q=Lead.objects.filter(tenant=t, phone='+%s')\n"
        "    if q.exists():\n"
        "        l=q.order_by('-id').first()\n"
        "        print('RESULT|%%d|%%s|%%s' %% (q.count(), l.first_name, l.source))\n"
        "    else:\n"
        "        print('RESULT|0||')\n" % PHONE
    )
    for line in erp_shell(code).splitlines():
        if line.startswith("RESULT|"):
            _, cnt, fn, src = line.split("|", 3)
            return int(cnt), fn.strip(), src.strip()
    return 0, "", ""


def cleanup(tenant_id):
    """Remove o lead desta corrida e a chave de estado no Redis (mantém o demo limpo)."""
    code = (
        "from nucleo.tenancy import rls_bypass\n"
        "from nucleo.models import Tenant\n"
        "from modulocrm.models import Lead\n"
        "from django.core.cache import cache\n"
        "with rls_bypass():\n"
        "    t=Tenant.objects.get(slug='demo')\n"
        "    Lead.objects.filter(tenant=t, phone='+%s').delete()\n"
        "cache.delete('wa:state:%s:%s')\n"
        "print('CLEAN OK')\n" % (PHONE, tenant_id, PHONE)
    )
    erp_shell(code)


# ── Execução ─────────────────────────────────────────────────────────────────
print("== Setup: garantir o canal WhatsApp do tenant demo ==")
tenant_id = ensure_canal()
check(f"CanalWhatsApp demo pronto (tenant {tenant_id})", bool(tenant_id))

print("== 1) Handshake GET da Meta ==")
st, body = get(f"{WEBHOOK}?hub.mode=subscribe&hub.verify_token={VERIFY_TOKEN}"
               f"&hub.challenge=DESAFIO-{RUN}&phone_number_id={PNID}")
check(f"verify_token correto -> {st} (esperado 200)", st == 200)
check("ecoa o hub.challenge", body.decode(errors="replace") == f"DESAFIO-{RUN}")

st, _ = get(f"{WEBHOOK}?hub.mode=subscribe&hub.verify_token=ERRADO"
            f"&hub.challenge=X&phone_number_id={PNID}")
check(f"verify_token errado -> {st} (esperado 403)", st == 403)

print("== 2) POST de número desconhecido é descartado ==")
corpo = text_message("PNID-INEXISTENTE", PHONE, "oi", f"wamid.C.{RUN}.x")
st, _ = post(corpo, sign(corpo))
check(f"phone_number_id desconhecido -> {st} (esperado 200, descartado)", st == 200)

print("== 3) POST com assinatura HMAC inválida ==")
corpo = text_message(PNID, PHONE, "oi", f"wamid.C.{RUN}.bad")
st, _ = post(corpo, sign(corpo, secret="segredo-errado"))
check(f"assinatura inválida -> {st} (esperado 403)", st == 403)

print("== 4) POST válido sem mensagem (status de entrega) ==")
corpo = status_only(PNID)
st, _ = post(corpo, sign(corpo))
check(f"payload de status -> {st} (esperado 200, nada a processar)", st == 200)

print("== 5) Conversa de lead (número desconhecido → Lead no CRM) ==")
# 3 mensagens: gatilho → nome → interesse. Espera o worker avançar o estado entre elas.
for idx, texto in enumerate(["quero informações", NAME, "cliente"], start=1):
    corpo = text_message(PNID, PHONE, texto, f"wamid.C.{RUN}.{idx}")
    st, _ = post(corpo, sign(corpo))
    check(f"mensagem {idx} ({texto!r}) -> {st} (esperado 200)", st == 200)
    time.sleep(1.5)

# Aguarda o worker criar o Lead (processamento assíncrono via Celery).
count, first_name, source = 0, "", ""
for _ in range(15):
    count, first_name, source = find_lead()
    if count:
        break
    time.sleep(1)

check(f"Lead criado no tenant demo (count={count})", count == 1)
check(f"first_name = {first_name!r} (esperado 'TesteC')", first_name == "TesteC")
check(f"source = {source!r} contém 'WhatsApp'", "WhatsApp" in source)

if tenant_id:
    cleanup(tenant_id)

print()
if all(passed):
    print(f"RESULTADO: TODOS OS {len(passed)} CHECKS PASSARAM ✅ (canal WhatsApp em Python, Fase C)")
else:
    print(f"RESULTADO: {passed.count(False)}/{len(passed)} FALHARAM ❌")
    raise SystemExit(1)
