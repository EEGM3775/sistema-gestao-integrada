# CLAUDE.md — Convenções do projeto SGI

Este arquivo é lido automaticamente pelo Claude Code no início de cada conversa.

## Regra de sincronização de documentação

Após implementação significativa (módulo concluído, campo/model alterado, fase do roadmap avançada,
rota nova), atualizar **só os documentos de status**, de forma concisa e no mesmo turno:

- **`docs/roadmap.md`** — status de fases/módulos: 1 linha por mudança, **sem narrativa**.
- **`docs/pendencias.md`** — achados de revisão: ao corrigir, status → `✅ corrigido DD/MM/AAAA`
  (achado novo = linha nova; nunca criar pastas de laudo `revisao-*`).

As **plantas** (`arquitetura*`, `dominio`, `modulos/`, `frontend*`) descrevem o sistema **sem status
nem datas** — atualizar só quando o **desenho** muda (nova página/rota/model/padrão/endpoint).

Padrão de status nas tabelas

- `✅ DD/MM/AAAA` — implementado e validado · `🚧 em andamento` · `❌ Fase X.Y` — planejado p/ a fase ·
  `📋 Planejado` — sem fase definida

### Armadilha frequente

`models.py` e migrations podem divergir se uma migration for criada sem atualizar o modelo de volta.
Antes de documentar um campo, verificar se o modelo Python reflete o estado atual do banco
(última migration aplicada). Se divergirem, corrigir o `models.py` primeiro.

## Arquitetura e documentação do projeto

- Planta baixa: [docs/arquitetura.md](docs/arquitetura.md)
- Roadmap (status de fases + plano): [docs/roadmap.md](docs/roadmap.md)
- Pendências (achados de revisão abertos): [docs/pendencias.md](docs/pendencias.md)
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
