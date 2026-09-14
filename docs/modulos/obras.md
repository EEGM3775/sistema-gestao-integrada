# Obras

> A execução física de um empreendimento, dividida em etapas e documentada.
> Código: [backend/obras/](../../backend/obras/).

## Acesso
App **base** — sem `required_module`. Isolado por tenant.

## Modelos
| Modelo | Guarda |
|---|---|
| `Obra` | Nome, endereço, status, datas previstas/reais, orçamento previsto; M2M de responsáveis técnicos e equipe |
| `EtapaObra` | Etapas ordenadas com % de conclusão, responsável, datas, orçamento |
| `DocumentoObra` | Documentos da obra (projeto, alvará, licença, …) com versão, status e aprovação |

## Relações
- `Obra.empreendimento` → `empreendimentos.Empreendimento` (**nullable** — pode haver obra avulsa).
- `Obra.responsaveis_tecnicos` e `Obra.equipe` → M2M `rh.Funcionario`.
- `EtapaObra.obra`/`DocumentoObra.obra` → `Obra`; `responsavel` → `rh.Funcionario`;
  `DocumentoObra.aprovador` → `nucleo.Usuario`.
- Referenciada por: `modulodiario.DiarioObra`, `moduloerp.Transacao.obra`, e os projetos de **drone**
  (vínculo `obraId` da Fase 3 — ver [../roadmap.md](../roadmap.md)).

## O nome da obra é único no empreendimento — e a recusa sugere o nome livre

> **Decisão do dono, 13/09/2026:** *"quando a pessoa tenta criar uma obra nova e o nome já existe,
> avisa que o nome já existe e dá um aviso com a nova renomeação. Então a regra ainda continua
> existindo e a pessoa, quando for selecionar a obra em algum módulo, não tem que ficar adivinhando."*

**A regra** (duas `UniqueConstraint`, originais do modelo): com empreendimento, o nome é único em
**(tenant, empreendimento, nome)**; sem empreendimento, em **(tenant, nome)**. Ou seja, o mesmo nome
**pode** existir em dois empreendimentos diferentes — o que se proíbe é repetir dentro do mesmo.
Desde a lixeira ([D116](../arquitetura/lixo.md)) as duas valem só **entre os vivos**: obra sob lápide
não segura o nome.

**A recusa** ([`obras/nomes.py`](../../backend/obras/nomes.py)) devolve **400** com três coisas, e cada
uma responde a uma pergunta de quem cadastra:

| Campo | Responde |
|---|---|
| `nome_obra` | o quê — "já existe uma obra com este nome neste empreendimento" |
| `conflito` | *é a mesma obra que eu já tenho?* — id, datas, status, nº de etapas e de **atividades** |
| `sugestao_nome` | *então como chamo esta?* — um nome livre, pronto para aceitar com um clique |

**O sufixo é o mês de início** (`Torre A — Fundações (05/2026)`), não `(2)`. O nome é como as pessoas
escolhem a obra no seletor do PDCA, na medição e no diário; `(2)` não diz nada e deixa o seletor sendo
adivinhação, só que com um número no fim. O número só entra quando **duas começam no mesmo mês** — o
caso em que a data deixou de distinguir. A base é truncada para o sufixo caber em `max_length=255`;
o sufixo nunca é cortado.

**`atividades` no cartão do conflito** é o número que separa a obra de verdade, com plano rodando, da
casca que alguém cadastrou e abandonou. Sem ele, duas linhas de mesmo nome e mesma data continuariam
indistinguíveis — que é o problema que a regra existe para evitar.

## Endpoints (`/api/`)

| Endpoint | Filtros disponíveis |
|---|---|
| `/obras/` | `?empreendimento_id=`, `?status_obra=`, `?membro_id=` |
| `/etapas-obras/` | `?obra=` (retorna ordenado por `ordem`) |
| `/documentos-obras/` | `?obra=` |

## UI React

Módulo implementado em `frontend/src/modules/obras/` (04/06/2026):

- **ObrasListPage** (`/app/obras`) — tabela com 3 filtros: busca por nome/endereço (client-side), status (client-side) e empreendimento (server-side). Nome do empreendimento resolvido via lookup map.
- **ObraDetailPage** (`/app/obras/:id`) — KPIs (orçamento, progresso geral, datas) + barra de progresso + 3 abas:
  - **Visão Geral** — campos cadastrais
  - **Etapas** — CRUD completo: lista com slider de % e badge de status; form lateral (ObraForm/EtapaForm)
  - **Documentos** — listagem com badge de status e link de download
- Aba **Obras** no `EmpreendimentoDetailPage` exibe obras do empreendimento com navegação direta.

## Status / pendências
Ativo. Constraints de unicidade por empreendimento. Mapa de localização (Leaflet/MapLibre) não implementado na UI — previsto para revisão pós Fase C.3. RBAC de campo e mascaramento de dados sensíveis dependem da Fase 9.
