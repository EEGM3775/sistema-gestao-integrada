"""E2E ao vivo do D70 — `/media/` fechado e o arquivo saindo pela porta única.

**Por que este só existe no stack vivo.** Os unitários provam o gate, o tenant e a
trilha; o que eles **não** podem provar é o nginx. O D70 tinha duas metades — o
serializer publicando `/media/` e o gateway servindo `/media/` — e um teste de
Django não vê a segunda: ele fala com o Django direto, onde `DEBUG=True` e a
`static()` do `config/urls.py` continuam de pé. É pelo gateway, e só por ele, que
a frase "`/media/` é 404 para tudo" pode ser verificada.

Atores do seed (testes/seeds/seed_demo.py):

  demo     / demo123     -> assina `rh`; personas rh_gestor + rh_medico + rh_financeiro
  semdrone / semdrone123 -> MESMO tenant, só `erp_financeiro`: prova o gate sem o módulo
  acme     / acme123     -> outro tenant, sem `rh`

  1. `/media/` é 404      -> os 9 prefixos da allowlist morta, com e sem token
  2. JSON limpo           -> nenhuma resposta do RH publica caminho de `/media/`
  3. Porta única          -> a URL é `/api/impexp/rh.documentos/...` e entrega os bytes
  4. Guarda-corpos        -> attachment + nosniff + `no-store` (não `immutable`)
  5. Gate                 -> sem token 401; sem o módulo `rh` 403
"""
import io
import sys
import time

import requests
from _sessao import ANTI_CSRF

GW = "http://localhost:8090"
OK, FALHA = [], []

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"

#: Os nove prefixos que a allowlist nomeava até 09/08/2026. Um `200` em qualquer
#: um deles é o D70 reaberto.
PREFIXOS_DA_ALLOWLIST_MORTA = [
    "asos_funcionarios", "holerites", "carteiras_trabalho", "documentos_funcionarios",
    "documentos_clientes", "nfe_xmls", "notas_fiscais", "documentos_obras",
    "diario_obra_media",
]


def checar(nome, condicao, detalhe=""):
    (OK if condicao else FALHA).append(nome)
    print(f"{'OK  ' if condicao else 'FALHA'} · {nome}{(' — ' + str(detalhe)) if detalhe else ''}")


def entrar(usuario, senha):
    s = requests.Session()
    r = s.post(f"{GW}/auth/login/", json={"username": usuario, "password": senha}, timeout=30)
    if r.status_code != 200:
        return s, None
    # BFF (fase 5): a Session guarda o cookie da sessão; falta só o anti-CSRF.
    return s, dict(ANTI_CSRF)


s, H = entrar("demo", "demo123")
checar("login demo", H is not None)
if H is None:
    print("sem token, nada a testar")
    sys.exit(1)

# ---------------------------------------------------------------------------
print("\n== 1. `/media/` é 404 — a allowlist morreu ==")
# ---------------------------------------------------------------------------
for prefixo in PREFIXOS_DA_ALLOWLIST_MORTA:
    r = s.get(f"{GW}/media/{prefixo}/qualquer-arquivo.pdf", timeout=30)
    checar(f"/media/{prefixo}/ -> 404", r.status_code == 404, r.status_code)

# Com token também: o gateway corta antes do Django, então autenticar não muda
# nada — e é essa a diferença entre "fechado" e "protegido por sorte".
r = s.get(f"{GW}/media/asos_funcionarios/x.pdf", headers=H, timeout=30)
checar("com token continua 404 (o corte é no gateway)", r.status_code == 404, r.status_code)

r = s.get(f"{GW}/media/impexp/entrada/2026/08/x.xlsx", timeout=30)
checar("prefixo que já tinha porta -> 404", r.status_code == 404, r.status_code)
r = s.get(f"{GW}/media/prefixo-que-nao-existe/x.bin", timeout=30)
checar("prefixo desconhecido -> 404", r.status_code == 404, r.status_code)

# ---------------------------------------------------------------------------
print("\n== 2. Um documento de funcionário, ponta a ponta ==")
# ---------------------------------------------------------------------------
marca = str(int(time.time()))[-6:]
novo = s.post(f"{GW}/api/funcionarios/", headers=H, timeout=30, json={
    "nome_completo": f"E2E D70 {marca}",
    "cpf": f"999.{marca[:3]}.{marca[3:]}-00",
    "data_nascimento": "1990-05-01",
    "genero": "masculino",
    "endereco_completo": "Rua do Teste, 100",
    "data_admissao": "2024-01-10",
    "salario_base": "3200.00",
})
checar("funcionário criado", novo.status_code == 201, novo.status_code)
if novo.status_code != 201:
    print(novo.text[:500])
    sys.exit(1)
funcionario_id = novo.json()["funcionario_id"]

envio = s.post(
    f"{GW}/api/documentos-funcionarios/", headers=H, timeout=60,
    files={"arquivo": ("rg-do-jose.pdf", io.BytesIO(PDF), "application/pdf")},
    data={"funcionario": funcionario_id, "tipo_documento": "rg",
          "nome_documento": "RG frente e verso"},
)
checar("documento enviado (a ENTRADA não mudou no D70)", envio.status_code == 201, envio.status_code)
if envio.status_code != 201:
    print(envio.text[:500])
    sys.exit(1)
documento = envio.json()
url_arquivo = documento.get("arquivo") or ""

checar("a resposta NÃO publica caminho de /media/",
       "/media/" not in str(documento), documento)
checar(f"o arquivo aponta para a porta única -> {url_arquivo}",
       url_arquivo.startswith("/api/impexp/rh.documentos/arquivo/documento/"))

ficha = s.get(f"{GW}/api/funcionarios/{funcionario_id}/", headers=H, timeout=30).json()
checar("nem a ficha do funcionário publica /media/", "/media/" not in str(ficha))

# ---------------------------------------------------------------------------
print("\n== 3. A porta entrega, com os guarda-corpos ==")
# ---------------------------------------------------------------------------
r = s.get(f"{GW}{url_arquivo}", headers=H, timeout=30)
checar("com o token certo -> 200 e os bytes", r.status_code == 200 and r.content == PDF,
       f"{r.status_code} ({len(r.content)}B)")
checar(f"tipo declarado por nós -> {r.headers.get('Content-Type')}",
       (r.headers.get("Content-Type") or "").startswith("application/pdf"))
# **`in` e não `==`, e a diferença tem história.** O header chega DUAS vezes:
# o gateway o adiciona a toda resposta (`add_header ... always`, Fase 5) e o
# `entrega.servir` o põe de novo no arquivo. As duas fontes são deliberadas e o
# valor é o mesmo, então o `requests` junta em `"nosniff, nosniff"`. Exigir
# igualdade aqui reprovaria uma resposta correta — e é o que este teste viu antes
# de a asserção ser corrigida. (O `pra8` não enxerga isso porque lê os headers com
# `dict(resp.headers)`, que descarta a duplicata em silêncio.)
nosniff = r.headers.get("X-Content-Type-Options") or ""
checar("nada é servido como página (nosniff + attachment)",
       "nosniff" in nosniff
       and (r.headers.get("Content-Disposition") or "").startswith("attachment"),
       f"{nosniff} · {r.headers.get('Content-Disposition')}")
# `no-store` e NÃO `immutable`: substituir o PDF reescreve o mesmo campo sob o
# mesmo id, então a URL não identifica o conteúdo (D51 com agravante de LGPD).
checar(f"cache não promete o que a URL não sustenta -> {r.headers.get('Cache-Control')}",
       "no-store" in (r.headers.get("Cache-Control") or "")
       and "immutable" not in (r.headers.get("Cache-Control") or ""))

# ---------------------------------------------------------------------------
print("\n== 4. O gate — o que `/media/` não tinha ==")
# ---------------------------------------------------------------------------
r = requests.get(f"{GW}{url_arquivo}", timeout=30)
checar("sem token -> 401 (não é arquivo público por id)", r.status_code == 401, r.status_code)

s2, H2 = entrar("semdrone", "semdrone123")
if H2:
    r = s2.get(f"{GW}{url_arquivo}", headers=H2, timeout=30)
    checar("mesmo tenant, sem o módulo rh -> 403", r.status_code == 403, r.status_code)

s3, H3 = entrar("acme", "acme123")
if H3:
    r = s3.get(f"{GW}{url_arquivo}", headers=H3, timeout=30)
    checar("outro tenant -> não entrega", r.status_code in (403, 404), r.status_code)

# ---------------------------------------------------------------------------
print("\n== 5. Faxina ==")
# ---------------------------------------------------------------------------
apagou = s.delete(f"{GW}/api/documentos-funcionarios/{documento['documento_id']}/",
                  headers=H, timeout=30)
s.delete(f"{GW}/api/funcionarios/{funcionario_id}/", headers=H, timeout=30)
checar("documento de teste removido", apagou.status_code in (204, 200), apagou.status_code)

print(f"\n=== {len(OK)}/{len(OK) + len(FALHA)} ===")
if FALHA:
    print("FALHARAM:", FALHA)
sys.exit(1 if FALHA else 0)
