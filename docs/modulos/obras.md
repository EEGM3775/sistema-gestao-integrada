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
