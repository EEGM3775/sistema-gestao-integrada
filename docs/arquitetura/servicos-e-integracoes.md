# Prancha — Serviços & integrações

> Os componentes do sistema e como conversam entre si (gateway, APIs, eventos) + os fluxos de
> sequência dos casos-chave. Visão macro em [../arquitetura.md](../arquitetura.md) §3. Detalhe por
> módulo em [../modulos/README.md](../modulos/README.md).

## 1. Inventário de serviços

| Serviço | Stack | Porta interna | Responsabilidade |
|---|---|---|---|
| gateway | Nginx | 80 (→ 8090) | borda, domínio único, roteamento |
| iam | Django/DRF | 8001 | identidade/SSO, entitlements |
| erp | Django/DRF | 8000 | domínio de negócio (resource server) |
| react | Vite→nginx | 80 | shell/UI do app |
| java-service | Spring Boot | 8080 | API do drone (`funcoesODM`) |
| drone-nginx | Nginx | 80 | SPA Angular do drone (sob `/drone/`) |
| nodeodm | NodeODM | — | processamento fotogramétrico |
| potree-converter | serviço | 5001 | gera nuvens de pontos/ortofotos |
| funcoesodm-db | PostgreSQL | 5432 | banco do drone |
| postgres | PostgreSQL | 5432 | `iam_db` + `erp_db` |
| redis | Redis | 6379 | cache Django + broker/result Celery |
| funcoesnf / funcoeswhatsapp | Node.js | (acionados pelo backend) | NF, bot |

## 2. Contrato de borda (gateway)

[infra/gateway/nginx.unified.conf](../../infra/gateway/nginx.unified.conf):

| Rota | Upstream | Observação |
|---|---|---|
| `/` | react | shell |
| `/api` | erp | API DRF do backend |
| `/auth` | iam | login/refresh/logout/me + JWKS |
| `/drone` | drone-nginx | SPA Angular (base href `/drone/`) |
| `/odm-api` | java-service | reescrito para `/api/v1` |
| `/ws` | java-service | WebSocket (upgrade) — anotações em tempo real |

## 3. APIs por serviço (alto nível)

- **IAM** (`/auth/*`, `/.well-known/jwks.json`, admin de tenants/módulos/assinaturas/usuários/perfis).
  Contrato em [auth-sso.md](auth-sso.md).
- **backend** (`/api/...`): apps base (`clientes`, `empreendimentos`, `obras`, `fornecedores`) +
  `/api/erp` (financeiro), `/api/crm`, `/api/diario`, `/api/ia`, `/api/calendar`. Cada um em
  [../modulos/README.md](../modulos/README.md).
- **Drone** (`/odm-api` → `/api/v1`): projetos (com `obraId`/`empreendimentoId`), tasks, imagens,
  ortofotos; `/ws` para anotações.

## 4. Integrações entre serviços

### 4.1 backend ↔ funcoesnf (emissão de NF) — Node em `localhost:3003`
- backend → Node: `POST /api/emitir-nfse` e `/api/emitir-nfe` (`{fatura_id, nf_id, city_service_code?}`);
  `POST /api/consultar-nf` (`{nf_id, invoice_id}`).
- Node → backend (callbacks): `POST /api/erp/atualizar-status-nf/` (`{nf_id, nf_tipo, status,
  dados_retorno}`) e `POST .../registrar-arquivos` (URLs de PDF/XML que o backend baixa e anexa).
- Em dev, se o Node não responde, o backend cria a NF em modo simulação (status `AGUARDANDO`) sem falhar.
  Ver [../modulos/funcoesnf.md](../modulos/funcoesnf.md).

### 4.2 CRM in-process (ex-funcoeslead)
Conversão/scoring de lead (`modulocrm/services.py` + actions do `LeadViewSet`), agenda do
calendário (consulta direta às `Interaction`) e lembrete de tarefas (Celery task) rodam **dentro
do backend** desde a Fase 11.2 — o microsserviço Node foi descomissionado. Ver
[../modulos/funcoeslead.md](../modulos/funcoeslead.md) e [../modulos/modulocrm.md](../modulos/modulocrm.md).

### 4.3 backend ↔ funcoeswhatsapp (bot) — Node
Bot de WhatsApp para registrar diário de obra por chat; contatos desconhecidos viram `nucleo.PreCadastro`.
Ver [../modulos/funcoeswhatsapp.md](../modulos/funcoeswhatsapp.md).

### 4.4 backend ↔ funcoesia (análise de imagem) — Celery + worker Node embutido
Ao salvar um `DocumentoDiario`, o backend enfileira `disparar_analise_ia.delay(...)` (Redis/Celery). A
task **não** processa a imagem: faz `POST /api/analise` no worker **Node** embutido em
`backend/funcoesia/` (`:3002`, header `X-Internal-Service-Token`), que chama o **Google Gemini** e
grava o resultado de volta via API do Django. Ver [../modulos/funcoesia.md](../modulos/funcoesia.md)
e [../modulos/funcoesia-analise-ia.md](../modulos/funcoesia-analise-ia.md).
> ⚠️ O callback Node→Django usa `Authorization: Token` (legado pré-Fase 6) — mesmo problema do
> achado L4; ver [pendencias.md](../pendencias.md).

### 4.5 backend ↔ Asaas (cobrança) — app `funcoescobrancas`
Django app Python (não é microsserviço): action `gerar-cobranca` em `ContaReceber` enfileira Celery
task que espelha o `Cliente` como `customer` no Asaas e cria o `payment` (grava `Boleto`). O Asaas
notifica pagamento via **webhook idempotente** `POST /api/erp/cobrancas/webhook/asaas/` (token
`ASAAS_WEBHOOK_TOKEN`), que aplica a **baixa automática** (`dar_baixa(origem='asaas')` com guarda
`RevisaoBaixa`). Ver [../modulos/funcoescobrancas.md](../modulos/funcoescobrancas.md).

### 4.6 Drone ↔ NodeODM/Potree
O `java-service` orquestra o processamento no NodeODM e a conversão no Potree, compartilhando volumes
de dados (ver [deploy-e-seguranca.md](deploy-e-seguranca.md)).

### 4.7 Autenticação serviço→serviço
Para endpoints expostos a usuários finais, há o middleware `iamAuth`
(`requireIamAuth`/`requireModule`) nos serviços Node, validando o JWT da IAM. Já as chamadas
**Node→Django** ainda usam o token estático legado (`Authorization: Token`), que o backend **não aceita
mais** desde a Fase 6 — o desenho-alvo é **JWT de serviço de vida curta emitido pela IAM**
(Fase 10.8 do [roadmap](../roadmap.md)). Ver [auth-sso.md](auth-sso.md).

## 5. Fluxos de sequência (casos-chave)

### 5.1 Emitir NFS-e a partir de uma conta a receber
```
React ─► /api/erp/contas-a-receber/{id}/emitir-nfse ─► backend
   backend: cria NotaFiscalServico (AGUARDANDO), liga à ContaReceber
   backend ─► funcoesnf POST /api/emitir-nfse {fatura_id, nf_id}   (contrato Node mantém a chave legada)
   funcoesnf ─► NFE.io (emite) ─► callback backend /atualizar-status-nf {status, dados}
   funcoesnf ─► callback backend /registrar-arquivos {url_pdf, url_xml} ─► backend baixa e anexa
```

### 5.2 Cobrança Asaas com baixa automática
```
React ─► /api/erp/contas-a-receber/{id}/gerar-cobranca ─► backend (Celery)
   backend ─► Asaas: upsert customer + create payment ─► grava Boleto EMITIDO
   cliente paga ─► Asaas ─► POST /api/erp/cobrancas/webhook/asaas/ (token; idempotente por evento_id)
   backend: dar_baixa(origem='asaas') → ContaReceber QUITADO · Boleto PAGO · Transacao lançada
```

### 5.3 Criar projeto de drone vinculado à obra
```
React (ficha da obra) ─► iframe /drone/?token=&empreendimento_id=&obra_id=
   Angular: ProjectContextService capta os ids ─► createProject
   ─► /odm-api/projects {..., empreendimentoId, obraId}  (Java valida JWT, exige 'drone', escopa tenant)
   Consulta: GET /odm-api/projects?obraId=  (filtra por obra, dentro do tenant)
   Exclusão de obra no backend ─► DELETE /odm-api/projects/links/obra/{id} (soft-unlink)
```

### 5.4 Login único e acesso a dois produtos
```
React ─► /auth/login (IAM) ─► token  ─► /api/* (backend) e /drone (Angular) com o mesmo token
   backend e drone validam a assinatura (chave pública/JWKS) e aplicam tenant + módulo + papel
```
Detalhe da validação em [auth-sso.md](auth-sso.md).
