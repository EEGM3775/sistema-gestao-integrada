"""Fase 9.E — trilha de auditoria imutável (`AuditLog`), via gateway (8090).

Prova ponta a ponta que operações sensíveis alimentam a trilha, que a leitura é
restrita e que a trilha é imutável na API. Seed: iam/seed_demo.py (tenant demo).

  demo     / demo123     -> power-user RH (rh_gestor/rh_medico/rh_financeiro) — GERA eventos
  admin    / admin123    -> admin do tenant (usuário principal) — LÊ a trilha
  semdrone / semdrone123 -> operacional, sem `plataforma.auditoria.view` — NEGADO na leitura

  1. demo cria funcionário            -> AuditLog 'criar' (rh.Funcionario), com o autor.
  2. demo edita o funcionário         -> AuditLog 'atualizar' com detalhes.campos_alterados.
  3. demo cria dado médico e o LÊ     -> AuditLog 'visualizar_pii' (auditoria de leitura de PII).
  4. admin exporta o titular (LGPD)   -> AuditLog 'exportar_lgpd'.
  5. Leitura restrita: demo/semdrone 403; admin 200 (só as linhas do próprio tenant).
  6. Imutável na API: POST/DELETE em /api/auditoria/ -> 405 (read-only).

Rodar (stack de pé):  python infra/gateway/phase9_auditoria_test.py
"""
import json, random, sys, urllib.request, urllib.error

# Console do Windows costuma ser cp1252 e quebra em emoji/acentos ao redirecionar.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = "http://localhost:8090"


def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
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


def linhas(payload):
    """Normaliza a resposta: paginada (dict com 'results') ou lista pura."""
    if isinstance(payload, dict):
        return payload.get("results", [])
    return payload or []


passed = []
def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


demo = login("demo", "demo123")
admin = login("admin", "admin123")
sem = login("semdrone", "semdrone123")

cpf = "".join(random.choices("0123456789", k=11))  # único por-tenant; aleatório evita colisão em re-run

print("== Setup: demo cria um funcionário (evento sensível de RH) ==")
status, func = req("POST", "/api/funcionarios/", demo, {
    "nome_completo": "E2E Auditoria 9E",
    "cpf": cpf,
    "data_nascimento": "1990-01-01",
    "genero": "outro",
    "endereco_completo": "Rua E2E, 9",
    "data_admissao": "2026-01-10",
    "salario_base": "1000.00",
})
check(f"demo cria funcionário (201) -> {status}", status == 201 and func and func.get("funcionario_id"))
fid = func.get("funcionario_id") if isinstance(func, dict) else None
print(f"  funcionario_id={fid}")

print("== 1. Escrita de RH grava 'criar' na trilha (com o autor) ==")
status, aud = req("GET", f"/api/auditoria/?modelo=rh.Funcionario&objeto_id={fid}&acao=criar", admin)
criar = linhas(aud)
check(f"admin lê a trilha (200) -> {status}", status == 200)
check("existe AuditLog 'criar' rh.Funcionario", len(criar) >= 1)
check("registra o autor (usuario_nome=demo)", any(l.get("usuario_nome") == "demo" for l in criar))

print("== 2. Update grava os NOMES dos campos alterados (sem valores) ==")
status, _ = req("PATCH", f"/api/funcionarios/{fid}/", demo, {"nome_completo": "E2E Auditoria 9E (editado)"})
check(f"demo edita funcionário (200) -> {status}", status == 200)
status, aud = req("GET", f"/api/auditoria/?modelo=rh.Funcionario&objeto_id={fid}&acao=atualizar", admin)
upd = linhas(aud)
tem_campo = any("nome_completo" in ((l.get("detalhes") or {}).get("campos_alterados") or []) for l in upd)
check("AuditLog 'atualizar' com detalhes.campos_alterados contendo 'nome_completo'", tem_campo)

print("== 3. Leitura de PII (retrieve de dado médico) grava 'visualizar_pii' ==")
status, med = req("POST", "/api/dados-medicos-funcionarios/", demo, {"funcionario": fid, "tipo_sanguineo": "O+"})
check(f"demo cria dado médico (201) -> {status}", status == 201 and med and med.get("id"))
mid = med.get("id") if isinstance(med, dict) else None
if mid:
    req("GET", f"/api/dados-medicos-funcionarios/{mid}/", demo)  # dispara a auditoria de leitura
status, aud = req("GET", f"/api/auditoria/?modelo=rh.DadoMedicoFuncionario&objeto_id={mid}&acao=visualizar_pii", admin)
check("AuditLog 'visualizar_pii' após o retrieve do dado médico", len(linhas(aud)) >= 1)

print("== 4. Exportação LGPD grava 'exportar_lgpd' ==")
status, _ = req("GET", f"/api/lgpd/funcionario/{fid}/exportar/", admin)
check(f"admin exporta titular (200) -> {status}", status == 200)
status, aud = req("GET", f"/api/auditoria/?objeto_id={fid}&acao=exportar_lgpd", admin)
check("AuditLog 'exportar_lgpd' do titular", len(linhas(aud)) >= 1)

print("== 5. Leitura da trilha é RESTRITA (usuário específico/principal/superuser) ==")
s_sem, _ = req("GET", "/api/auditoria/", sem)
check(f"semdrone (operacional) -> {s_sem} (esperado 403)", s_sem == 403)
s_demo, _ = req("GET", "/api/auditoria/", demo)
check(f"demo (power-user sem 'auditor') -> {s_demo} (esperado 403)", s_demo == 403)
s_admin, _ = req("GET", "/api/auditoria/", admin)
check(f"admin (principal do tenant) -> {s_admin} (esperado 200)", s_admin == 200)

print("== 6. Trilha IMUTÁVEL na API (sem verbo de escrita) ==")
s_post, _ = req("POST", "/api/auditoria/", admin, {"acao": "criar", "modelo": "x", "objeto_id": "1"})
check(f"admin POST /api/auditoria/ -> {s_post} (esperado 405)", s_post == 405)
algum = linhas(aud) or linhas(req("GET", "/api/auditoria/", admin)[1])
some_id = algum[0].get("id") if algum else 1
s_del, _ = req("DELETE", f"/api/auditoria/{some_id}/", admin)
check(f"admin DELETE /api/auditoria/{some_id}/ -> {s_del} (esperado 405)", s_del == 405)

print()
if all(passed):
    print(f"RESULTADO: TODOS OS {len(passed)} CHECKS PASSARAM ✅  (trilha de auditoria 9.E provada)")
else:
    print(f"RESULTADO: {passed.count(False)}/{len(passed)} FALHARAM ❌")
    raise SystemExit(1)
