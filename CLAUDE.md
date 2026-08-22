# CLAUDE.md — Convenções do projeto SGI

Este arquivo é lido automaticamente pelo Claude Code no início de cada conversa.

## Regra de sincronização de documentação

Após implementação significativa (módulo concluído, campo/model alterado, fase do roadmap avançada,
rota nova), atualizar **só os documentos de status**, de forma concisa e no mesmo turno:

- **`docs/roadmap.md`** — status de fases/módulos: 1 linha por mudança, **sem narrativa**.
- **`docs/pendencias.md`** — achados de revisão **em aberto**, e só isso (achado novo = linha nova;
  nunca criar pastas de laudo `revisao-*`).
- **`docs/historico-correcoes.md`** — ao corrigir, o achado **sai** do `pendencias.md` e o relato vem
  inteiro para cá, com `✅ corrigido DD/MM/AAAA`.

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
- Módulos do backend em detalhe: [docs/modulos/](docs/modulos/)
- Frontend (React): [docs/frontend.md](docs/frontend.md) · convenções obrigatórias:
  [docs/frontend-convencoes.md](docs/frontend-convencoes.md)
- Identidade visual (Sistema Malha — marca, cor, tipografia, voz): [docs/identidade-visual.md](docs/identidade-visual.md)
- Acesso e permissões: [docs/acesso-e-permissoes.md](docs/acesso-e-permissoes.md)
- Como rodar: [docs/desenvolvimento.md](docs/desenvolvimento.md)

## Padrões de desenvolvimento

- Rotas simples registradas em `backend/config/urls.py` (sem `urls.py` local — padrão correto).
- Entitlement de módulo via `RequireModule("codigo")` em `backend/nucleo/permissions.py`.
- Todo model de negócio herda `TenantScopedModel` de `nucleo.tenancy`.
- **TODO teto ou limite vive em [`payment/planos.py`](payment/planos.py)** *(decisão do dono,
  08/08/2026)* — tamanho de arquivo, formato aceito, memória, relógio, tamanho de página, corte
  síncrono×job, profundidade de recursão, teto de comando de bancada. Nenhum número desses fica em
  código de engenharia, nem em `config/settings.py`, que é arquivo de deploy. O módulo importa a
  constante e dá a ela o nome local que quiser; o **valor** é do dono. Quem cobra é
  `backend/nucleo/test_tetos_no_payment.py`; a fronteira do que **não** é limite (constante física,
  largura de campo, TTL de cache, janela de protocolo de terceiro) está na §5.6 do `planos.py`.
- **Frontend de módulo segue a régua** (grandioso + expansível): cockpit com fila de decisão,
- loop do domínio ponta a ponta, dados honestos (agregado real ou "em breve", nunca fabricado),
  **integração visível entre módulos** (o que conversa no backend conversa na tela — um *sistema de
  gestão integrada*, não silos) e seams de expansão prontos. Não é CRUD. Régua completa em
  [docs/frontend.md §1.6](docs/frontend.md).
