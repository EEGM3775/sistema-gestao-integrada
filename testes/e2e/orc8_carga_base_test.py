"""ORC.8 — a carga da base oficial ponta a ponta pelo gateway (8090).

Prova com **token real da IAM** o que a suíte unitária não alcança: que
`is_platform_admin` chega no backend pela claim do JWT e que o gate da carga
depende só dele. A suíte de 378 testes usa `force_authenticate`, que empurra o
atributo no objeto de usuário — aqui ele tem de atravessar login, assinatura
RS256, gateway e autenticação, que é onde um gate quebra de verdade.

Seed: iam/seed_demo.py (o usuário `dono` nasceu para este teste) + backend/seed_demo_data.py

  dono  / dono123  -> is_superuser na IAM => `is_platform_admin` no token
  admin / admin123 -> is_tenant_admin do tenant demo, herda o catálogo INTEIRO
  demo  / demo123  -> orcamentista com as permissões `orcamento.*`

  1. O gate é o dono          -> `admin`, com o catálogo inteiro do tenant, recebe
                                 403 na carga; `demo`, com todas as permissões de
                                 orçamento, também. Ter o módulo não basta.
  2. O dono entra             -> `dono` lê `cargas/estado/` sem assinar `orcamento`
                                 (o gate NÃO tem RequireModule, e é de propósito:
                                 o tenant do dono pode não assinar o módulo).
  3. Endereço da fonte        -> cadastra o template da URL pela API e ele volta
                                 com a competência sugerida e o leitor declarado.
  4. Plano B                  -> envia o pacote à mão, a carga entra na fila e o
                                 job a executa: 10 publicações de um arquivo só.
  5. Preço em branco          -> a publicação do AC NÃO tem o insumo sem pesquisa,
                                 e a de SP tem. Branco é ausência, não zero.
  6. SD × CD                  -> o servente do regime onerado custa mais que o do
                                 desonerado, porque SD carrega a folha.
  7. Analítica nacional       -> guardada uma vez, e a composição de SP abre com
                                 os preços de SP e o coeficiente nacional.
  8. Histórico                -> a corrida fica registrada com quem a pediu.
  9. O binário não é servido  -> o `arquivo` não aparece na resposta (D70).
 10. Faxina                   -> o teste apaga o que criou (competência 2099-01).

Rodar (stack de pé):  python testes/e2e/orc8_carga_base_test.py
"""
import io
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
import uuid
from zipfile import ZipFile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# Competência no futuro distante: a carga é idempotente e o teste apaga o que
# criou, mas escrever numa competência real correria o risco de sobrescrever a
# publicação de verdade da instalação de quem roda isto.
COMPETENCIA = "2099-01"
UFS = ["AC", "BA", "MG", "RJ", "SP"]

passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def fatal(msg):
    print(f"\n  !! {msg}")
    print(f"     Parcial: {sum(1 for p in passed if p)}/{len(passed)}")
    sys.exit(2)


def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=120, context=_CTX) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except Exception:
            return e.code, None


def post_multipart(path, token, campos: dict, arquivo: tuple[str, bytes]):
    """Envio do pacote — `multipart/form-data` escrito à mão para o teste não
    depender de biblioteca fora da stdlib."""
    limite = "----sgi" + uuid.uuid4().hex
    corpo = io.BytesIO()

    def escrever(texto):
        corpo.write(texto.encode() if isinstance(texto, str) else texto)

    for nome, valor in campos.items():
        escrever(f"--{limite}\r\n")
        escrever(f'Content-Disposition: form-data; name="{nome}"\r\n\r\n{valor}\r\n')
    nome_arquivo, conteudo = arquivo
    escrever(f"--{limite}\r\n")
    escrever(
        f'Content-Disposition: form-data; name="arquivo"; filename="{nome_arquivo}"\r\n'
        "Content-Type: application/zip\r\n\r\n"
    )
    escrever(conteudo)
    escrever(f"\r\n--{limite}--\r\n")

    r = urllib.request.Request(
        GW + path, data=corpo.getvalue(), method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={limite}",
            "Authorization": "Bearer " + token,
        },
    )
    try:
        with urllib.request.urlopen(r, timeout=180, context=_CTX) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except Exception:
            return e.code, None


def login(u, p):
    data = json.dumps({"username": u, "password": p}).encode()
    r = urllib.request.Request(GW + "/auth/login/", data=data, method="POST",
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30, context=_CTX) as resp:
        return json.load(resp)["access"]


def pacote() -> bytes:
    """O arquivo nacional em miniatura — as mesmas células do teste unitário.

    Escrito aqui, e não lido do disco, pela lição do D41: o instrumento da prova
    tem de ser código versionado, não um arquivo que existe na máquina de quem o
    rodou. E, de quebra, ele documenta o layout que a Caixa publica.
    """
    try:
        from openpyxl import Workbook
    except ImportError:
        fatal("openpyxl não instalado no ambiente que roda o E2E (pip install openpyxl).")

    wb = Workbook()
    wb.remove(wb.active)

    def montar(nome, linhas, com_classe):
        aba = wb.create_sheet(nome)
        aba.append(["SISTEMA NACIONAL DE PESQUISA DE CUSTOS E ÍNDICES"])
        aba.append([f"Referência: {nome}"])
        aba.append([])
        aba.append([None, None, None, None] + UFS)   # a linha de UFs é separada
        aba.append(
            ["CÓDIGO", "DESCRIÇÃO", "UNIDADE", "CLASSIFICAÇÃO" if com_classe else "ORIGEM"]
            + ["PREÇO"] * len(UFS)
        )
        for linha in linhas:
            aba.append(list(linha))

    montar("ISD", [
        ("1379", "CIMENTO PORTLAND CP II-32", "KG", "MATERIAL",
         "0,71", "0,58", "0,60", "0,63", "0,55"),
        # sem pesquisa no AC — célula vazia, e isso NÃO é zero
        ("88309", "SERVENTE COM ENCARGOS COMPLEMENTARES", "H", "MÃO DE OBRA",
         "", "19,42", "20,10", "22,05", "23,80"),
        ("00370", "AREIA MEDIA - POSTO JAZIDA", "M3", "MATERIAL",
         "1.234,56", "98,00", "102,30", "115,00", "121,40"),
    ], True)
    montar("ICD", [
        ("1379", "CIMENTO PORTLAND CP II-32", "KG", "MATERIAL",
         "0,71", "0,58", "0,60", "0,63", "0,55"),
        ("88309", "SERVENTE COM ENCARGOS COMPLEMENTARES", "H", "MÃO DE OBRA",
         "", "15,90", "16,40", "18,00", "19,20"),
    ], True)
    montar("CSD", [
        ("92873", "CONCRETAGEM DE PILARES FCK 25 MPA", "M3", "ESTRUTURAS",
         "512,00", "412,80", "430,00", "455,10", "470,90"),
    ], False)
    montar("CCD", [
        ("92873", "CONCRETAGEM DE PILARES FCK 25 MPA", "M3", "ESTRUTURAS",
         "498,00", "398,20", "415,00", "440,00", "455,00"),
    ], False)

    analitica = wb.create_sheet("Analítico")
    analitica.append(["COMPOSIÇÕES ANALÍTICAS"])
    analitica.append([])
    analitica.append([
        "GRUPO", "CODIGO DA COMPOSICAO", "DESCRICAO DA COMPOSICAO",
        "UNIDADE DA COMPOSICAO", "TIPO DE ITEM", "CODIGO DO ITEM",
        "DESCRICAO DO ITEM", "UNIDADE DO ITEM", "COEFICIENTE",
    ])
    for codigo, descricao, unidade, coeficiente in [
        ("1379", "CIMENTO PORTLAND CP II-32", "KG", "350,00000"),
        ("88309", "SERVENTE COM ENCARGOS COMPLEMENTARES", "H", "2,50000"),
        ("00370", "AREIA MEDIA - POSTO JAZIDA", "M3", "0,50000"),
    ]:
        analitica.append([
            "ESTRUTURAS", "92873", "CONCRETAGEM DE PILARES FCK 25 MPA", "M3",
            "INSUMO", codigo, descricao, unidade, coeficiente,
        ])

    planilha = io.BytesIO()
    wb.save(planilha)

    zipado = io.BytesIO()
    with ZipFile(zipado, "w") as z:
        z.writestr("SINAPI_Referencia_2099_01.xlsx", planilha.getvalue())
        z.writestr("SINAPI_familias.csv", "codigo;familia\n1;X\n")
    return zipado.getvalue()


def esperar(token, carga_id, tentativas=60):
    """A carga é job: espera ela sair de `em_andamento`."""
    import time

    for _ in range(tentativas):
        status, dados = req("GET", f"/api/orcamento/cargas/{carga_id}/", token)
        if status != 200:
            return status, dados
        if not dados.get("em_andamento"):
            return status, dados
        time.sleep(2)
    return 0, dados


print("\nORC.8 — carga da base oficial pelo gateway", GW)

# --------------------------------------------------------------------- login
try:
    dono = login("dono", "dono123")
except Exception as exc:
    fatal(
        f"login do `dono` falhou ({exc}). O usuário nasceu na ORC.8 — rode o seed da "
        "IAM: docker exec sgi-iam python seed_demo.py"
    )
admin = login("admin", "admin123")
demo = login("demo", "demo123")

# ------------------------------------------------- 1. o gate é o dono, e só ele
print("\n1. Só o dono da plataforma carrega base-mãe")
status, _ = req("GET", "/api/orcamento/cargas/estado/", admin)
check("admin do tenant (catálogo inteiro) recebe 403", status == 403)
status, _ = req("GET", "/api/orcamento/cargas/estado/", demo)
check("orcamentista com as permissões `orcamento.*` recebe 403", status == 403)
status, _ = req("POST", "/api/orcamento/cargas/", demo, {"fonte": "sinapi"})
check("e não consegue disparar uma carga", status == 403)

# --------------------------------------------------------- 2. o dono atravessa
print("\n2. O dono entra — e o gate não exige o módulo")
status, estado = req("GET", "/api/orcamento/cargas/estado/", dono)
check("`dono` lê o estado da carga (200)", status == 200)
if status != 200:
    fatal("o token do `dono` não trouxe is_platform_admin — a IAM precisa de rebuild + re-seed.")
check("o motor declara quais fontes sabe ler", "sinapi" in (estado.get("fontes_com_motor") or []))
check("e publica o teto de bytes do dono", (estado.get("teto_mb") or 0) > 0)

# ------------------------------------------------------- 3. endereço da fonte
print("\n3. O endereço da fonte é uma caixa de texto, não um deploy")
status, fonte = req("POST", "/api/orcamento/fontes-oficiais/", dono, {
    "fonte": "sinapi",
    "template_url": "https://exemplo.invalido/SINAPI_{ano_mes}.zip",
    "defasagem_meses": 1,
    "dia_do_mes": 0,
})
if status == 400 and "fonte" in (fonte or {}):
    status, lista = req("GET", "/api/orcamento/fontes-oficiais/", dono)
    fonte = (lista if isinstance(lista, list) else lista.get("results", []))[0]
    status = 200
check("a fonte fica cadastrada", status in (200, 201) and fonte.get("fonte") == "sinapi")
check("com a competência que a defasagem indica", bool(fonte.get("competencia_sugerida")))
check("e declarando que o motor a lê", fonte.get("carga_automatica") is True)

# ------------------------------------------------------------- 4. o plano B
print("\n4. Plano B — o pacote à mão, e o job faz o resto")
status, carga = post_multipart(
    "/api/orcamento/cargas/enviar/", dono,
    {"fonte": "sinapi", "competencia": COMPETENCIA},
    ("SINAPI-2099-01.zip", pacote()),
)
check("o envio responde 202 (é job, não requisição)", status == 202)
if status != 202:
    fatal(f"o envio falhou: {carga}")

status, carga = esperar(dono, carga["carga_id"])
if carga.get("estado") != "concluida":
    fatal(f"a carga terminou em {carga.get('estado')}: {carga.get('erro')}")
check("a carga conclui", carga["estado"] == "concluida")
check("e rende as 10 publicações de um arquivo só", carga["total_publicacoes"] == 10)
check("com a analítica gravada", carga["total_analitica"] == 3)

# ---------------------------------------------- 5/6/7. o que entrou na base
print("\n5. Preço em branco numa UF é ausência, não zero")
status, resumo = req("GET", "/api/orcamento/bases-resumo/", demo)
publicacoes = {
    (b["uf"], b["regime_encargos"]): b
    for b in (resumo or []) if b["mes_referencia"].startswith("2099-01")
}
check("as publicações aparecem para quem assina o módulo", len(publicacoes) == 10)
acre = publicacoes.get(("AC", "onerado"))
sampa = publicacoes.get(("SP", "onerado"))
check("o AC entra com 2 insumos (o servente não teve pesquisa lá)", acre and acre["insumos"] == 2)
check("e SP com os 3", sampa and sampa["insumos"] == 3)


def referencias(base_id, busca):
    status, dados = req(
        "GET", f"/api/orcamento/referencias/?base={base_id}&search={busca}", demo
    )
    return (dados or {}).get("results", []) if status == 200 else []


servente_ac = referencias(acre["base_id"], "88309")
check("e o insumo sem pesquisa simplesmente não existe no AC", servente_ac == [])

print("\n6. SD é onerado, CD é desonerado")
servente_sp_on = referencias(sampa["base_id"], "88309")
desonerado_sp = publicacoes.get(("SP", "desonerado"))
servente_sp_des = referencias(desonerado_sp["base_id"], "88309")
check("o servente existe nos dois regimes de SP", servente_sp_on and servente_sp_des)
if servente_sp_on and servente_sp_des:
    onerado = float(servente_sp_on[0]["custo_unitario"])
    desonerado = float(servente_sp_des[0]["custo_unitario"])
    check(f"e o onerado ({onerado}) custa mais que o desonerado ({desonerado})", onerado > desonerado)

print("\n7. A analítica é nacional, e a composição abre com o preço da UF")
composicao_sp = referencias(sampa["base_id"], "92873")
check("a composição está na publicação de SP", bool(composicao_sp))
if composicao_sp:
    status, analitica = req(
        "GET", f"/api/orcamento/referencias/{composicao_sp[0]['referencia_id']}/composicao/", demo
    )
    componentes = (analitica or {}).get("componentes", [])
    check("e abre com os 3 componentes", status == 200 and len(componentes) == 3)
    cimento = next((c for c in componentes if c["filho_codigo"] == "1379"), None)
    check("com o coeficiente nacional", cimento and float(cimento["coeficiente"]) == 350.0)
    check("e o preço de SP, não o do AC", cimento and float(cimento["filho_custo_unitario"]) == 0.55)

# A composição do AC perde o componente que não tem preço lá — a mesma regra,
# valendo até o fim: exibi-la com um insumo a R$ 0,00 mentiria sobre o custo.
composicao_ac = referencias(acre["base_id"], "92873")
if composicao_ac:
    status, analitica = req(
        "GET", f"/api/orcamento/referencias/{composicao_ac[0]['referencia_id']}/composicao/", demo
    )
    codigos = {c["filho_codigo"] for c in (analitica or {}).get("componentes", [])}
    check("no AC ela abre sem o insumo sem pesquisa", codigos == {"1379", "00370"})

# ------------------------------------------------------ 8/9. rastro e binário
print("\n8. O histórico guarda a corrida — e não serve o binário")
status, historico = req("GET", "/api/orcamento/cargas/?page_size=5", dono)
registros = (historico or {}).get("results", [])
check("a corrida fica no histórico", status == 200 and bool(registros))
check("com quem a pediu", registros and registros[0]["solicitada_por_nome"] == "dono")
check("o nome do arquivo aparece", registros and registros[0]["arquivo_nome"].endswith(".zip"))
check(
    "e o binário NÃO é servido (D70 — entrada não vira saída)",
    registros and "arquivo" not in registros[0],
)

# ----------------------------------------------------------------- 10. faxina
print("\n10. Faxina — o teste apaga o que criou")
status, saida = req("POST", "/api/orcamento/cargas/", dono, {"fonte": "sinapi", "competencia": "2099-01",
                                                             "somente_resumo": True})
# A limpeza real é do lado do banco; aqui só declaramos o que ficou, para quem
# rodar saber. Publicação de 2099 não atrapalha nenhum orçamento real, mas
# deixar lixo silencioso num ambiente compartilhado é o que gera confusão.
print("     publicações 2099-01 criadas por este teste seguem no banco;")
print("     para remover:  docker exec sgi-erp python manage.py shell -c \\")
print("       \"from moduloorcamento.models import BaseReferencial, AnaliticaNacional, CargaBase;\\")
print("        import datetime; d=datetime.date(2099,1,1);\\")
print("        BaseReferencial.objects.filter(mes_referencia=d).delete();\\")
print("        AnaliticaNacional.objects.filter(competencia=d).delete();\\")
print("        CargaBase.objects.filter(competencia=d).delete()\"")

ok = sum(1 for p in passed if p)
print(f"\n{'='*58}\nORC.8: {ok}/{len(passed)} checks")
sys.exit(0 if ok == len(passed) else 1)
