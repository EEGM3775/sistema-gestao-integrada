# CLAUDE.md — Convenções do projeto SGI

Este arquivo é lido automaticamente pelo Claude Code no início de cada conversa.

## Regra de sincronização de documentação

**Após qualquer implementação significativa, atualizar TODOS os documentos afetados no mesmo turno.**

### O que é "implementação significativa"

- Novo módulo backend concluído (models + views + serializers + rotas)
- Novo módulo frontend concluído (páginas + componentes + hooks)
- Campo de model alterado (adicionado, removido, tornado nullable/not null, unique alterado)
- Migration aplicada que diverge do models.py
- Fase do roadmap concluída ou parcialmente concluída
- Rota nova registrada (mesmo que em `config/urls.py` sem `urls.py` local)

### Cada documento tem UMA natureza — não misturar

- **Planta** (`arquitetura*`, `dominio`, `modulos/`, `frontend.md`, `frontend-convencoes.md`):
  descreve o sistema inteiro, **sem status nem datas**.
- **Status** (`roadmap.md`, `pendencias.md`): o que está pronto/falta/quebrado — tabelas e links,
  **sem narrativa**.
- **Histórico** (`historico.md`): narrativa datada (entregas, bugs corrigidos, validações,
  decisões). **Todo texto com data vai para cá**, nunca para o roadmap.
- **Uma revisão técnica só:** achados (problema → correção → status) e o backlog de ideias vivem
  consolidados em `docs/pendencias.md`. Nunca criar pastas de laudo versionadas (`revisao-*`,
  `*-v02`); revisões novas atualizam o `pendencias.md` (achado novo = linha nova).

### Documentos a atualizar (por escopo da mudança)

| Mudança | Documentos a atualizar |
|---|---|
| Backend: model alterado | `docs/modulos/<modulo>.md` (campos + choices corretos) · `backend/<modulo>/models.py` (sincronizar com migration) |
| Backend: módulo completo | `docs/modulos/<modulo>.md` · `docs/roadmap.md` (tabela backend, 1 linha) · `docs/historico.md` (nota de entrega datada) |
| Frontend: módulo completo | `docs/roadmap.md` (tabela frontend + fluxo testável, 1 linha cada) · `docs/historico.md` (nota de entrega datada) · `docs/frontend.md` **só se** o desenho mudou (nova página/rota/padrão) · `docs/frontend-convencoes.md` se nasceu convenção nova |
| Fase do roadmap concluída | `docs/roadmap.md` (status) · `docs/README.md` (tabela de resumo de fases) · `docs/historico.md` (narrativa da entrega) |
| Rota nova registrada | `docs/modulos/<modulo>.md` (seção de endpoints) |
| Bug relevante corrigido / achado de revisão resolvido | `docs/pendencias.md` (status → `✅ corrigido DD/MM/AAAA`) · `docs/historico.md` (o que era e como foi corrigido) |

### Padrão de status nas tabelas

- `✅ DD/MM/AAAA` — implementado e validado
- `🚧 em andamento` — iniciado mas incompleto
- `❌ Fase X.Y` — planejado para a fase indicada
- `📋 Planejado` — ainda sem fase definida

### Armadilha frequente

`models.py` e migrations podem divergir se uma migration for criada sem atualizar o modelo de volta.
Antes de documentar um campo, verificar se o modelo Python reflete o estado atual do banco
(última migration aplicada). Se divergirem, corrigir o `models.py` primeiro.

## Arquitetura e documentação do projeto

- Planta baixa: [docs/arquitetura.md](docs/arquitetura.md)
- Roadmap (status de fases + plano): [docs/roadmap.md](docs/roadmap.md)
- Pendências (achados de revisão abertos): [docs/pendencias.md](docs/pendencias.md)
- Histórico (diário de obra, entregas datadas): [docs/historico.md](docs/historico.md)
- Módulos do ERP em detalhe: [docs/modulos/](docs/modulos/)
- Frontend (React): [docs/frontend.md](docs/frontend.md) · convenções obrigatórias:
  [docs/frontend-convencoes.md](docs/frontend-convencoes.md)
- Acesso e permissões: [docs/acesso-e-permissoes.md](docs/acesso-e-permissoes.md)
- Como rodar: [docs/desenvolvimento.md](docs/desenvolvimento.md)

## Padrões de desenvolvimento

- Rotas simples registradas em `backend/config/urls.py` (sem `urls.py` local — padrão correto).
- Entitlement de módulo via `RequireModule("codigo")` em `backend/nucleo/permissions.py`.
- Todo model de negócio herda `TenantScopedModel` de `nucleo.tenancy`.
- Novos módulos de negócio → Django app (Python). Nunca novo microsserviço Node.js.
