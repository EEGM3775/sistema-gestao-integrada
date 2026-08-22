"""MAP.6 — módulo Maps ponta a ponta pelo gateway (8090).

Prova com um token real da IAM o que a suíte unitária (44 testes) não cobre: o
entitlement `maps`, as 10 permissões `mapa.*` e a persona `topografo` só existem
depois do rebuild da imagem da IAM + re-seed. E, sobretudo, prova as **duas
metades** do módulo (planta §2) — a tese que a suíte concede permissão à mão e
por isso nunca esbarra: `Local` é fundação **sem** entitlement; camada, acervo,
voo e rota ficam atrás dele.

O ator que fecha essa prova é o `acme`: tenant que assina **só `drone`** e cujo
papel `engenharia` foi composto pelo `sync_authz` **sem nenhuma permissão de
`maps`** (a trava anti-escalada corta o que o tenant não assina), sobrando
exatamente `mapa.local.*` — que vive no módulo `base`. Ele é o único ator do seed
capaz de separar os dois eixos do gate: o `admin` **não serve**, porque
`is_tenant_admin` herda todos os módulos do tenant.

Seed: iam/seed_demo.py (tenants demo + acme) + backend/seed_demo_data.py

  demo     / demo123     -> assina `maps`, papéis inclusive `topografo`
  acme     / acme123     -> tenant SEM `maps`, mas com `mapa.local.*` (fundação)
  semdrone / semdrone123 -> tenant COM `maps`, mas sem nenhuma `mapa.*`

   1. Módulo vivo            -> /status/ declara os provedores que a instalação TEM.
   2. **As duas metades**    -> admin sem `maps` LÊ /locais/ (fundação) e leva 403
                                em /camadas/ e /planos-voo/; sem permissão nem a
                                fundação abre (semdrone).
   3. Cascata real           -> Local nasce do CEP e se localiza sozinho (rede de
                                verdade: BrasilAPI/IBGE), com precisão declarada.
   4. Pin exata é soberano   -> nem `?forcar=1` rebaixa coordenada de campo.
   5. Vínculo coerente       -> tipo sem a FK vira 400 limpo, não 500 do driver.
   6. Fila de decisão        -> obra sem coordenada e pin de município entram na
                                fila; sem `maps` a fila não inventa item de camada.
   7. Vizinhança             -> "fornecedores num raio de X km desta obra", que
                                era impossível quando endereço era texto livre.
   8. **Seam do SCM**        -> a proposta que não tinha distância passa a ter,
                                pela cadeia cotação→demanda→centro de custo→obra;
                                fornecedor sem local segue `null`, nunca zero.
   9. Antes/depois           -> `?ate=` devolve o acervo na data, não o de hoje.
  10. Tile com gate          -> o raster do acervo NÃO é público por UUID (S10):
                                sem token 401, sem entitlement 403.
  11. Altura sai do GSD      -> a memória de cálculo bate com a fórmula da câmera,
                                e o plano exporta nos 4 formatos de campo.
  12. Estimativa se declara  -> sem OSRM a rota é reta carimbada `estimada`, e o
                                otimizador devolve as violações de janela.
  13. Cerca + conter         -> raio vira polígono e responde "este ponto está
                                dentro?" — o gancho de RH/diário.
  14. **R1 do impexp**       -> detecção não grava nada; a conferência é que grava,
                                a linha fora do Brasil é recusada, e o lote desfaz.

Rodar (stack de pé):  python testes/e2e/map6_maps_test.py
                      SGI_GW=https://localhost:8443 python testes/e2e/map6_maps_test.py
"""
import json, os, ssl, sys, urllib.error, urllib.parse, urllib.request, uuid
from datetime import date, timedelta

# Console do Windows costuma ser cp1252 e quebra em acento ao redirecionar.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GW = os.environ.get("SGI_GW", "http://localhost:8090")  # SGI_GW aponta ao staging (10.7)

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# Tudo que o teste cria carrega este prefixo — é o que torna a rerodada limpa
# (Camada/PlanoVoo/Geofence têm unique por tenant+nome; sem faxina, a 2ª execução
# morreria em 400 e pareceria defeito do módulo).
TAG = "E2E MAP.6"


def req(method, path, token=None, body=None, raw=False, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(GW + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=timeout, context=_CTX) as resp:
            if raw:  # binário (KML/KMZ/tile): interessa o tamanho, não o corpo
                return resp.status, resp.read()
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except Exception:
            return e.code, None


def upload(path, token, nome_arquivo, conteudo: bytes, campos=None):
    """POST multipart — o `funcoesimpexp` recebe arquivo, não JSON."""
    limite = "----sgi" + uuid.uuid4().hex
    partes = []
    for chave, valor in (campos or {}).items():
        partes.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="{chave}"\r\n\r\n{valor}\r\n'.encode()
        )
    partes.append(
        f'--{limite}\r\nContent-Disposition: form-data; name="arquivo"; '
        f'filename="{nome_arquivo}"\r\nContent-Type: text/csv\r\n\r\n'.encode()
        + conteudo + b"\r\n"
    )
    partes.append(f"--{limite}--\r\n".encode())
    corpo = b"".join(partes)

    r = urllib.request.Request(
        GW + path, data=corpo, method="POST",
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


def linhas(payload):
    """Normaliza a resposta: paginada (dict com 'results') ou lista pura."""
    if isinstance(payload, dict):
        return payload.get("results", [])
    return payload or []


passed = []


def check(label, cond):
    passed.append(bool(cond))
    print(f"  [{'OK' if cond else 'XXX'}] {label}")


def fatal(msg):
    print(f"\n  !! {msg}")
    print("     O seed do backend (backend/seed_demo_data.py) precisa ter rodado.")
    print(f"     Parcial: {sum(1 for p in passed if p)}/{len(passed)}")
    sys.exit(2)


demo = login("demo", "demo123")
acme = login("acme", "acme123")
semdrone = login("semdrone", "semdrone123")

# ---------------------------------------------------------------------------
# Faxina — a rerodada tem de encontrar o terreno como o encontrou da 1ª vez.
# A ordem importa: `Rota.origem` e `ParadaRota.local` são PROTECT, então rota
# sai antes do local, senão a faxina falha em 409 e o teste "não é idempotente"
# vira ruído em cima de um módulo que está certo.
# ---------------------------------------------------------------------------
def faxina():
    apagados = 0
    for rota, chave in (("rotas", "rota_id"), ("geofences", "geofence_id"),
                        ("planos-voo", "plano_id"), ("feicoes", "feicao_id"),
                        ("camadas", "camada_id"), ("ortofotos", "ortofoto_id"),
                        ("locais", "local_id")):
        status, dados = req("GET", f"/api/maps/{rota}/?page_size=500", demo)
        if status != 200:
            continue
        for obj in linhas(dados):
            rotulo = obj.get("nome") or obj.get("titulo") or ""
            if str(rotulo).startswith(TAG):
                req("DELETE", f"/api/maps/{rota}/{obj[chave]}/", demo)
                apagados += 1
    return apagados


print(f"== 0. Faxina de execução anterior ==\n  {faxina()} objetos do E2E removidos")

# ---------------------------------------------------------------------------
print("== 1. Módulo vivo e provedores declarados ==")
status, st = req("GET", "/api/maps/status/", demo)
check(f"GET /api/maps/status/ (200) -> {status}", status == 200)
provedores = (st or {}).get("provedores") or {}
check(f"declara o que a instalação consegue fazer -> {provedores}",
      set(provedores) >= {"geocodificacao_endereco", "motor_rota", "tiles_raster"})

# ---------------------------------------------------------------------------
print("== 2. As duas metades do gate (a tese do módulo) ==")
# O `acme` tem a permissão da fundação (`mapa.local.*`, módulo `base`) e NÃO
# assina `maps`. Sobra um eixo só — o entitlement —, que é o que se quer medir.
status, _ = req("GET", "/api/maps/locais/", acme)
check(f"tenant SEM o módulo lê a FUNDAÇÃO (/locais/ 200) -> {status}", status == 200)
status, _ = req("GET", "/api/maps/camadas/", acme)
check(f"e leva 403 na CAMADA (/camadas/) -> {status}", status == 403)
status, _ = req("GET", "/api/maps/planos-voo/", acme)
check(f"e 403 em /planos-voo/ -> {status}", status == 403)
status, _ = req("GET", "/api/maps/rotas/", acme)
check(f"e 403 em /rotas/ -> {status}", status == 403)

# Fundação sem entitlement não é fundação sem permissão: o `operacional` não tem
# `mapa.local.view` e por isso nem os pins alcança.
status, _ = req("GET", "/api/maps/locais/", semdrone)
check(f"sem a permissão `mapa.local.view` nem a fundação abre -> {status}", status == 403)

status, _ = req("GET", "/api/maps/camadas/", demo)
check(f"demo (assina maps + topografo) entra na camada -> {status}", status == 200)

# ---------------------------------------------------------------------------
print("== 3. O Local nasce e se localiza sozinho (cascata com rede real) ==")
status, doCep = req("POST", "/api/maps/locais/", demo, {
    "nome": f"{TAG} — nascido do CEP",
    "tipo": "avulso",
    "cep": "41820-021",
})
check(f"criado (201) -> {status}", status == 201)
if status != 201:
    fatal(f"não consegui criar o local: {doCep}")
check(f"a cascata resolveu a coordenada -> {doCep.get('ponto')}", doCep.get("ponto") is not None)
check(f"e declara a precisão (nunca coordenada crua) -> "
      f"{doCep.get('precisao')} / {doCep.get('precisao_rotulo')}",
      doCep.get("precisao") in ("endereco", "cep", "municipio"))
check(f"com a procedência junto -> {doCep.get('fonte')}", bool(doCep.get("fonte")))
check(f"completou cidade/UF a partir do CEP -> {doCep.get('cidade')}/{doCep.get('uf')}",
      (doCep.get("cidade") or "").lower().startswith("salvador") and doCep.get("uf") == "BA")

# ---------------------------------------------------------------------------
print("== 4. Pin de campo é soberano: nem forçar o rebaixa ==")
status, exato = req("POST", "/api/maps/locais/", demo, {
    "nome": f"{TAG} — pin à mão",
    "tipo": "avulso",
    "ponto": {"lon": -38.4573, "lat": -12.9822},
    "cidade": "Salvador", "uf": "BA",
})
check(f"local com pin criado (201) -> {status}", status == 201)
check(f"pin enviado à mão nasce `exata` -> {exato.get('precisao')}/{exato.get('fonte')}",
      exato.get("precisao") == "exata")
exato_id = exato.get("local_id")

status, tentativa = req("POST", f"/api/maps/locais/{exato_id}/geocodificar/?forcar=1", demo, {})
check(f"geocodificar --forcar num `exata` não muda nada -> "
      f"{(tentativa or {}).get('geocodificado')}",
      status == 200 and (tentativa or {}).get("geocodificado") is False)
check(f"e diz por quê -> {str((tentativa or {}).get('motivo'))[:60]}…",
      "exata" in str((tentativa or {}).get("motivo")).lower())
ponto_exato = ((tentativa or {}).get("local") or {}).get("ponto") or {}
check(f"a coordenada de campo continua de pé -> {ponto_exato}",
      round(float(ponto_exato.get("lat", 0)), 4) == -12.9822)

# ---------------------------------------------------------------------------
print("== 5. Discriminador e FK têm de bater (CheckConstraint vira 400) ==")
status, erro = req("POST", "/api/maps/locais/", demo, {"nome": f"{TAG} — incoerente", "tipo": "obra"})
check(f"tipo=obra sem obra recusado com 400 (não 500) -> {status}", status == 400)
check(f"e a mensagem nomeia o campo que falta -> {erro}", "obra" in json.dumps(erro or {}))

# ---------------------------------------------------------------------------
print("== 6. Fila de decisão: o que o mapa exige que alguém resolva ==")
status, obras = req("GET", "/api/obras/", demo)
if status != 200:
    fatal(f"não consegui listar obras (status {status})")
todas_obras = linhas(obras)
if len(todas_obras) < 2:
    fatal("o seed precisa de ao menos duas obras")


def obra_pk(o):
    return o.get("obra_id") or o.get("id")


# Uma obra vira o canteiro georreferenciado do seam do SCM; outra fica de
# propósito sem endereço, para provar que "sem coordenada" é estado legítimo e
# vira fila — não pin inventado em 0,0.
status, propostas_antes = req("GET", "/api/scm/propostas/?page_size=100", demo)
if status != 200:
    fatal(f"não consegui listar propostas do SCM (status {status})")
propostas = linhas(propostas_antes)
alvo = next((p for p in propostas if p.get("cotacao") and p.get("fornecedor")), None)
if alvo is None:
    fatal("o seed do SCM não tem proposta com fornecedor — o seam do passo 8 fica sem prova")
cotacao_alvo = alvo["cotacao"]
irmas = [p for p in propostas if p.get("cotacao") == cotacao_alvo]
check(f"cotação {cotacao_alvo} tem {len(irmas)} propostas para comparar", len(irmas) >= 2)
check("NENHUMA proposta tem distância antes de existir Local (dado honesto)",
      all(p.get("distancia_km") is None for p in irmas))

# A obra da cotação sai da cadeia que o próprio seam percorre; aqui basta pegar
# a primeira obra do tenant e amarrar tudo nela seria errado — o vínculo real é
# cotação→demanda→centro de custo→obra, então perguntamos ao SCM.
status, cotacao = req("GET", f"/api/scm/cotacoes/{cotacao_alvo}/", demo)
demanda_id = (cotacao or {}).get("demanda")
status, demanda = req("GET", f"/api/scm/demandas/{demanda_id}/", demo)
centro_id = (demanda or {}).get("centro_custo")
status, centro = req("GET", f"/api/scm/centros-custo/{centro_id}/", demo)
obra_da_cotacao = (centro or {}).get("obra")
if not obra_da_cotacao:
    fatal("o centro de custo da cotação não aponta obra — sem isso não há distância a medir")
print(f"  cadeia do seam: cotação {cotacao_alvo} → demanda {demanda_id} → "
      f"centro {centro_id} → obra {obra_da_cotacao}")

obra_sem_endereco = next((obra_pk(o) for o in todas_obras
                          if str(obra_pk(o)) != str(obra_da_cotacao)), None)

status, canteiro = req("POST", "/api/maps/locais/", demo, {
    "nome": f"{TAG} — canteiro da cotação",
    "tipo": "obra", "obra": obra_da_cotacao,
    "ponto": {"lon": -38.4573, "lat": -12.9822},
    "cidade": "Salvador", "uf": "BA",
})
check(f"canteiro georreferenciado (201) -> {status}", status == 201)
canteiro_id = (canteiro or {}).get("local_id")

status, orfa = req("POST", "/api/maps/locais/", demo, {
    "nome": f"{TAG} — obra sem endereço", "tipo": "obra", "obra": obra_sem_endereco,
})
check(f"obra sem nenhum endereço criada (201) -> {status}", status == 201)
check(f"fica `desconhecida` em vez de ganhar pin inventado -> {(orfa or {}).get('precisao')}",
      (orfa or {}).get("precisao") == "desconhecida" and (orfa or {}).get("ponto") is None)

# Pin de município: o caso que MAIS engana, porque no mapa parece resolvido.
status, grosseiro = req("POST", "/api/maps/locais/", demo, {
    "nome": f"{TAG} — só cidade", "tipo": "avulso",
    "cidade": "Feira de Santana", "uf": "BA",
})
check(f"local só com cidade cai no centroide do município -> {(grosseiro or {}).get('precisao')}",
      status == 201 and (grosseiro or {}).get("precisao") == "municipio")

status, mapa = req("GET", "/api/maps/mapa/", demo)
check(f"GET /api/maps/mapa/ (200) -> {status}", status == 200)
fila = {item["tipo"] for item in (mapa or {}).get("requer_decisao", [])}
check(f"a obra sem coordenada entrou na fila -> {sorted(fila)}", "sem_coordenada" in fila)
check("o pin de município entrou como pendência própria", "precisao_grosseira" in fila)
check(f"o resumo abre a carteira por precisão -> {(mapa or {}).get('resumo', {}).get('por_precisao')}",
      bool((mapa or {}).get("resumo", {}).get("por_precisao")))
check(f"e declara que o tenant assina as camadas -> {(mapa or {}).get('camadas_contratadas')}",
      (mapa or {}).get("camadas_contratadas") is True)

status, mapa_acme = req("GET", "/api/maps/mapa/", acme)
check(f"o mesmo mapa abre para quem NÃO assina (é fundação) -> {status}", status == 200)
check(f"mas declarando que não há camadas contratadas -> "
      f"{(mapa_acme or {}).get('camadas_contratadas')}",
      (mapa_acme or {}).get("camadas_contratadas") is False)
fila_acme = {i["tipo"] for i in (mapa_acme or {}).get("requer_decisao", [])}
check(f"e sem inventar pendência de camada que ele não tem -> {sorted(fila_acme)}",
      not (fila_acme & {"ortofoto_vencida", "voo_sem_autorizacao"}))
check(f"e sem enxergar um pin sequer do outro tenant -> "
      f"{(mapa_acme or {}).get('resumo', {}).get('total')}",
      (mapa_acme or {}).get("resumo", {}).get("total") == 0)

# ---------------------------------------------------------------------------
print("== 7. Vizinhança: o que era impossível com endereço em texto livre ==")
status, fornecedores = req("GET", "/api/fornecedores/?page_size=10", demo)
lista_forn = linhas(fornecedores)
if len(lista_forn) < 2:
    fatal("o seed precisa de ao menos dois fornecedores")


def forn_pk(f):
    return f.get("fornecedor_id") or f.get("id")


# O fornecedor de cada proposta da cotação — para o seam medir o que interessa.
forn_das_propostas = [p["fornecedor"] for p in irmas]
perto_id, longe_id = forn_das_propostas[0], forn_das_propostas[1]
# O terceiro (quando existe) fica DE PROPÓSITO sem local: é ele que prova que
# distância ausente vira `null`, e não zero.
sem_local_id = forn_das_propostas[2] if len(forn_das_propostas) > 2 else None

status, perto = req("POST", "/api/maps/locais/", demo, {
    "nome": f"{TAG} — fornecedor perto", "tipo": "fornecedor", "fornecedor": perto_id,
    "ponto": {"lon": -38.5100, "lat": -12.9750}, "cidade": "Salvador", "uf": "BA",
})
check(f"fornecedor próximo georreferenciado -> {status}", status == 201)
status, longe = req("POST", "/api/maps/locais/", demo, {
    "nome": f"{TAG} — fornecedor longe", "tipo": "fornecedor", "fornecedor": longe_id,
    "ponto": {"lon": -38.9663, "lat": -12.2664}, "cidade": "Feira de Santana", "uf": "BA",
})
check(f"fornecedor distante georreferenciado -> {status}", status == 201)

status, vizinhos = req("GET",
                       f"/api/maps/locais/proximos/?de={canteiro_id}&raio_km=150&tipo=fornecedor",
                       demo)
achados = (vizinhos or {}).get("resultados", [])
check(f"raio de 150 km alcança os dois -> {len(achados)}", status == 200 and len(achados) == 2)
check(f"cada um com a distância calculada -> "
      f"{[(a['nome'][-8:], a['distancia_km']) for a in achados]}",
      all(a.get("distancia_km") for a in achados))
check("e do mais perto para o mais longe (é fila de decisão, não lista)",
      len(achados) == 2 and achados[0]["distancia_km"] < achados[1]["distancia_km"])

status, curto = req("GET",
                    f"/api/maps/locais/proximos/?de={canteiro_id}&raio_km=20&tipo=fornecedor",
                    demo)
check(f"raio de 20 km exclui o distante (o filtro é espacial de verdade) -> "
      f"{len((curto or {}).get('resultados', []))}",
      len((curto or {}).get("resultados", [])) == 1)

status, _ = req("GET", "/api/maps/locais/proximos/", demo)
check(f"`proximos` sem origem recusado (400) -> {status}", status == 400)

# ---------------------------------------------------------------------------
print("== 8. Seam do SCM: a distância entra no mapa comparativo ==")
status, depois = req("GET", f"/api/scm/propostas/?cotacao={cotacao_alvo}", demo)
agora = linhas(depois)
check(f"GET /api/scm/propostas/?cotacao= (200) -> {status}", status == 200)
com_distancia = {p["fornecedor"]: p.get("distancia_km") for p in agora}
check(f"a proposta do fornecedor perto GANHOU distância -> {com_distancia.get(perto_id)} km",
      com_distancia.get(perto_id) is not None)
check(f"a do distante também, e é maior -> {com_distancia.get(longe_id)} km",
      (com_distancia.get(longe_id) or 0) > (com_distancia.get(perto_id) or 0))
if sem_local_id:
    check(f"o fornecedor SEM local segue `null` (nunca um zero) -> "
          f"{com_distancia.get(sem_local_id)}",
          com_distancia.get(sem_local_id) is None)

# ---------------------------------------------------------------------------
print("== 9. Camadas e o antes/depois do acervo ==")
status, camada = req("POST", "/api/maps/camadas/", demo,
                     {"nome": f"{TAG} — progresso", "cor": "#E79A22"})
check(f"camada criada (201) -> {status}", status == 201)
camada_id = (camada or {}).get("camada_id")

antiga, recente = date(2026, 1, 15), date(2026, 7, 15)
for nome, quando, lon in ((f"{TAG} — laje jan", antiga, -38.4575),
                          (f"{TAG} — laje jul", recente, -38.4571)):
    status, _ = req("POST", "/api/maps/feicoes/", demo, {
        "camada": camada_id, "nome": nome, "tipo": "progresso",
        "grupo": "e2e-laje", "data_referencia": quando.isoformat(),
        "geom": {"type": "Point", "coordinates": [lon, -12.9822]},
    })
    check(f"feição {quando:%m/%Y} criada (201) -> {status}", status == 201)

status, ate = req("GET", f"/api/maps/feicoes/?grupo=e2e-laje&ate={antiga.isoformat()}", demo)
check(f"`?ate=` mostra o acervo NAQUELA data, não o de hoje -> "
      f"{len(linhas(ate))} de 2", status == 200 and len(linhas(ate)) == 1)
status, tudo = req("GET", "/api/maps/feicoes/?grupo=e2e-laje", demo)
check(f"sem recorte, as duas versões da mesma feição -> {len(linhas(tudo))}",
      len(linhas(tudo)) == 2)

status, caixa = req("GET", "/api/maps/feicoes/?bbox=-38.4573,-12.9830,-38.4560,-12.9810", demo)
check(f"`?bbox=` recorta no espaço (só a de julho cai na caixa) -> {len(linhas(caixa))}",
      status == 200 and len(linhas(caixa)) == 1)

# ---------------------------------------------------------------------------
print("== 10. Ortofoto indexada e o tile que NÃO é público (contraste com o S10) ==")
voo_antigo = date.today() - timedelta(days=200)
status, orto = req("POST", "/api/maps/ortofotos/", demo, {
    "titulo": f"{TAG} — voo antigo",
    "data_voo": voo_antigo.isoformat(),
    "bbox": {"type": "Polygon", "coordinates": [[
        [-38.4600, -12.9850], [-38.4540, -12.9850],
        [-38.4540, -12.9800], [-38.4600, -12.9800], [-38.4600, -12.9850]]]},
    "url_cog": "https://exemplo.invalido/e2e.tif",
})
check(f"ortofoto indexada (201) -> {status}", status == 201)
orto_id = (orto or {}).get("ortofoto_id")
check(f"a idade do voo vem calculada (é o que gera a fila) -> "
      f"{(orto or {}).get('dias_desde_voo')} dias",
      (orto or {}).get("dias_desde_voo", 0) >= 90)

status, mapa2 = req("GET", "/api/maps/mapa/", demo)
fila2 = {i["tipo"] for i in (mapa2 or {}).get("requer_decisao", [])}
check(f"e o voo vencido entra na fila de decisão -> {sorted(fila2)}", "ortofoto_vencida" in fila2)

tile = f"/api/maps/ortofotos/{orto_id}/tiles/12/1500/2200/"
status, corpo = req("GET", tile, demo, raw=True)
check(f"o tile responde ao dono do acervo — 503 declarando que falta o TiTiler "
      f"nesta instalação -> {status}", status == 503)
status, _ = req("GET", tile, acme, raw=True)
check(f"quem NÃO assina maps não alcança o raster -> {status}", status == 403)
status, _ = req("GET", tile, None, raw=True)
check(f"e sem token o acervo não abre (não é `permitAll` por UUID) -> {status}", status == 401)

# ---------------------------------------------------------------------------
print("== 11. Plano de voo: a altura sai do GSD, não do dedo ==")
status, plano = req("POST", "/api/maps/planos-voo/", demo, {
    "nome": f"{TAG} — grid do canteiro", "tipo": "grid",
    "obra": obra_da_cotacao, "gsd_alvo_cm": "2.00",
    "area": {"type": "Polygon", "coordinates": [[
        [-38.4590, -12.9840], [-38.4560, -12.9840],
        [-38.4560, -12.9810], [-38.4590, -12.9810], [-38.4590, -12.9840]]]},
})
check(f"plano criado (201) -> {status}", status == 201)
plano_id = (plano or {}).get("plano_id")

status, _ = req("GET", f"/api/maps/planos-voo/{plano_id}/exportar/?formato=kml", demo, raw=True)
check(f"exportar antes de calcular é recusado (409) -> {status}", status == 409)

status, calculo = req("POST", f"/api/maps/planos-voo/{plano_id}/calcular/", demo, {})
check(f"calcular (200) -> {status}", status == 200)
memoria = (calculo or {}).get("memoria") or {}
check(f"devolve a MEMÓRIA de cálculo, não só o número -> {sorted(memoria)}",
      {"altura_m", "espacamento_m", "intervalo_foto_m", "waypoints"} <= set(memoria))
# altura = GSD(m/px) × focal(mm) × largura(px) / sensor(mm)
#        = 0,02 × 8,8 × 5472 / 13,2 ≈ 72,96 m  (câmera 1" padrão do modelo)
esperada = 0.02 * 8.8 * 5472 / 13.2
altura = float(memoria.get("altura_m") or 0)
check(f"e a altura BATE com a geometria da câmera ({esperada:.1f} m) -> {altura} m",
      abs(altura - esperada) <= 1.0)
check(f"o grid gerou waypoints -> {memoria.get('waypoints')}", (memoria.get("waypoints") or 0) > 1)

for formato, minimo in (("kml", 200), ("plan", 200), ("litchi", 60), ("wpml", 200)):
    status, blob = req("GET", f"/api/maps/planos-voo/{plano_id}/exportar/?formato={formato}",
                       demo, raw=True)
    check(f"exporta {formato} ({status}) -> {len(blob) if isinstance(blob, bytes) else blob} bytes",
          status == 200 and isinstance(blob, bytes) and len(blob) > minimo)

status, _ = req("GET", f"/api/maps/planos-voo/{plano_id}/exportar/?formato=inventado", demo)
check(f"formato desconhecido recusado (400) -> {status}", status == 400)

# ---------------------------------------------------------------------------
print("== 12. Rota: sem motor, a estimativa se declara estimativa ==")
status, rota = req("POST", "/api/maps/rotas/", demo, {
    "nome": f"{TAG} — entrega ao canteiro", "origem": canteiro_id,
    "data_planejada": date.today().isoformat(),
})
check(f"rota criada (201) -> {status}", status == 201)
rota_id = (rota or {}).get("rota_id")

# A parada distante ganha uma janela impossível para a ordem "mais curta" — é o
# que faz a violação aparecer em vez de ser engolida.
for local_id, janela in ((longe.get("local_id"), ("06:00", "06:30")),
                         (perto.get("local_id"), (None, None))):
    corpo = {"rota": rota_id, "local": local_id, "ordem": 1 if janela[0] else 2}
    if janela[0]:
        corpo.update({"janela_inicio": janela[0], "janela_fim": janela[1]})
    status, _ = req("POST", "/api/maps/paradas/", demo, corpo)
    check(f"parada adicionada (201) -> {status}", status == 201)

status, tracada = req("POST", f"/api/maps/rotas/{rota_id}/tracar/", demo, {})
check(f"traçar (200) -> {status}", status == 200)
check(f"sem OSRM o traçado se declara ESTIMADO -> "
      f"{(tracada or {}).get('procedencia')} / {(tracada or {}).get('procedencia_rotulo')}",
      (tracada or {}).get("procedencia") == "estimada")
check(f"com distância utilizável mesmo assim -> {(tracada or {}).get('distancia_km')} km",
      ((tracada or {}).get("distancia_km") or 0) > 0)

status, otimizada = req("POST", f"/api/maps/rotas/{rota_id}/otimizar/", demo, {})
check(f"otimizar (200) -> {status}", status == 200)
violacoes = (otimizada or {}).get("violacoes_de_janela")
check(f"a ordem mais curta NÃO esconde a janela furada -> {violacoes}",
      isinstance(violacoes, list) and len(violacoes) >= 1)
check(f"e a violação diz o motivo, não só que houve -> "
      f"{(violacoes or [{}])[0].get('motivo')}",
      bool((violacoes or [{}])[0].get("motivo")))
ordenadas = ((otimizada or {}).get("rota") or {}).get("paradas") or []
check(f"as paradas voltaram numeradas em sequência -> "
      f"{[p.get('ordem') for p in ordenadas]}",
      [p.get("ordem") for p in ordenadas] == list(range(1, len(ordenadas) + 1)))

# Parada sem coordenada é erro de dado, e o módulo diz QUAL parada.
status, _ = req("POST", "/api/maps/paradas/", demo,
                {"rota": rota_id, "local": (orfa or {}).get("local_id"), "ordem": 3})
status, recusa = req("POST", f"/api/maps/rotas/{rota_id}/tracar/", demo, {})
check(f"traçar com parada sem coordenada recusado (400) -> {status}", status == 400)
check(f"e a mensagem NOMEIA a parada culpada -> {str((recusa or {}).get('detail'))[:70]}…",
      "sem endereço" in str((recusa or {}).get("detail")))

# ---------------------------------------------------------------------------
print("== 13. Cerca de canteiro: raio vira polígono e responde 'está dentro?' ==")
status, cerca = req("POST", "/api/maps/geofences/gerar/", demo, {
    "local": canteiro_id, "nome": f"{TAG} — cerca do canteiro",
    "tipo": "canteiro", "raio_m": 150,
})
check(f"cerca gerada do raio (201) -> {status}", status == 201)
check(f"guardando o raio de origem (a explicação do desenho) -> {(cerca or {}).get('raio_m')}",
      (cerca or {}).get("raio_m") == 150)

status, dentro = req("GET", "/api/maps/geofences/conter/?lon=-38.4573&lat=-12.9822", demo)
check(f"o ponto do canteiro está dentro -> {(dentro or {}).get('dentro')}",
      status == 200 and (dentro or {}).get("dentro") is True)
status, fora = req("GET", "/api/maps/geofences/conter/?lon=-38.5100&lat=-12.9750", demo)
check(f"o do fornecedor a 6 km, fora -> {(fora or {}).get('dentro')}",
      (fora or {}).get("dentro") is False)
status, _ = req("POST", "/api/maps/geofences/gerar/", demo,
                {"local": (orfa or {}).get("local_id"), "nome": f"{TAG} — impossível"})
check(f"cerca de local sem coordenada recusada (400) -> {status}", status == 400)

# ---------------------------------------------------------------------------
print("== 14. MAP.5 — a detecção não grava; quem grava é a conferência (R1) ==")
texto = ("Prezados, a entrega deve ser feita na Av. Tancredo Neves, 1632, "
         "Caminho das Árvores, CEP 41820-021, aos cuidados do almoxarifado.")
status, deteccao = req("POST", "/api/maps/detectar-endereco/", demo, {"texto": texto})
candidatos = (deteccao or {}).get("candidatos") or []
check(f"detecta o endereço no texto livre (200) -> {status} / {len(candidatos)} candidato(s)",
      status == 200 and len(candidatos) >= 1)
primeiro = candidatos[0] if candidatos else {}
check(f"ancorado no CEP e validado -> {primeiro.get('metodo')} / {primeiro.get('confianca')}",
      primeiro.get("metodo") == "cep_validado" and primeiro.get("confianca") == "alta")
check(f"trazendo cidade/UF oficiais -> {primeiro.get('cidade')}/{primeiro.get('uf')}",
      primeiro.get("uf") == "BA")

nfe = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe><emit>
<CNPJ>12345678000199</CNPJ><xNome>Fornecedor E2E</xNome>
<enderEmit><xLgr>Rua da Grécia</xLgr><nro>10</nro><xBairro>Comércio</xBairro>
<cMun>2927408</cMun><xMun>Salvador</xMun><UF>BA</UF><CEP>40010010</CEP>
</enderEmit></emit></infNFe></NFe></nfeProc>"""
status, doXml = req("POST", "/api/maps/detectar-endereco/", demo, {"xml": nfe, "papel": "emit"})
doc = ((doXml or {}).get("candidatos") or [{}])[0]
check(f"o XML da NF-e entrega endereço conferido pela SEFAZ -> "
      f"{doc.get('logradouro')}, {doc.get('cidade')}/{doc.get('uf')}",
      status == 200 and doc.get("uf") == "BA")
status, _ = req("POST", "/api/maps/detectar-endereco/", demo, {})
check(f"sem texto nem xml, 400 -> {status}", status == 400)

status, recursos = req("GET", "/api/impexp/recursos/", demo)
ids = [r["id"] for r in (recursos or {}).get("recursos", [])]
check(f"o Maps declarou seu recurso no motor -> {'maps.local' in ids}", "maps.local" in ids)
status, recursos_sem = req("GET", "/api/impexp/recursos/", semdrone)
ids_sem = [r["id"] for r in (recursos_sem or {}).get("recursos", [])]
check("quem não tem acesso total nem vê o recurso (R11)", "maps.local" not in ids_sem)

status, antes_conta = req("GET", "/api/maps/locais/?page_size=1", demo)
locais_antes = (antes_conta or {}).get("count", 0)

csv = "\n".join([
    "Nome;CEP;Logradouro;Número;Bairro;Cidade;UF;Longitude;Latitude;Precisão",
    f"{TAG} — importado bom;40010-010;Rua da Grécia;10;Comércio;Salvador;BA;-38.5108;-12.9718;exata",
    f"{TAG} — coordenada trocada;;;;;Salvador;BA;-12.9718;-38.5108;exata",
    f"{TAG} — sem nada;;;;;;;;;",
]).encode("utf-8")

status, lote = upload("/api/impexp/maps.local/importar/", demo, "locais.csv", csv)
check(f"arquivo aceito para conferência ({status}) -> {(lote or {}).get('status')}",
      status in (201, 202))
lote_id = (lote or {}).get("importacao_id")
check(f"as 3 linhas foram classificadas -> {(lote or {}).get('total')}",
      (lote or {}).get("total") == 3)
check(f"a linha com lon/lat trocados foi barrada -> "
      f"{(lote or {}).get('invalidas')} inválida(s)",
      (lote or {}).get("invalidas", 0) >= 2)

status, meio = req("GET", "/api/maps/locais/?page_size=1", demo)
check(f"**R1**: nada gravado antes da decisão ({locais_antes} locais) -> "
      f"{(meio or {}).get('count')}",
      (meio or {}).get("count") == locais_antes)

status, aplicado = req("POST", f"/api/impexp/importacoes/{lote_id}/aplicar/", demo, {})
check(f"aplicar (200) -> {status}", status == 200)
check(f"só a linha boa entrou -> {(aplicado or {}).get('aplicadas')}",
      (aplicado or {}).get("aplicadas") == 1)
status, depois_conta = req("GET", "/api/maps/locais/?page_size=1", demo)
check(f"o acervo cresceu exatamente 1 -> {(depois_conta or {}).get('count')}",
      (depois_conta or {}).get("count") == locais_antes + 1)

status, desfeito = req("POST", f"/api/impexp/importacoes/{lote_id}/desfazer/", demo, {})
check(f"desfazer (200) -> {status}", status == 200)
status, final = req("GET", "/api/maps/locais/?page_size=1", demo)
check(f"e o acervo voltou ao que era ({locais_antes}) -> {(final or {}).get('count')}",
      (final or {}).get("count") == locais_antes)

status, blob = req("GET", "/api/impexp/maps.local/exportar/?formato=csv", demo, raw=True)
check(f"a carteira georreferenciada sai da empresa ({status})", status in (200, 202))

print()
ok = sum(1 for p in passed if p)
print(f"RESULTADO: {ok}/{len(passed)}")
sys.exit(0 if ok == len(passed) else 1)
