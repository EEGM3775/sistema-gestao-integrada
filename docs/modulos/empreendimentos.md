# Empreendimentos

> A entidade **central** do negócio (ver [../dominio.md](../dominio.md)). Cada empreendimento é um
> projeto imobiliário da incorporadora; quase tudo de negócio aponta para ele.
> Backend: [backend/empreendimentos/](../../backend/empreendimentos/) ·
> Frontend: [frontend/src/modules/empreendimentos/](../../frontend/src/modules/empreendimentos/)

## Acesso

App **base** — sem `required_module`; disponível a qualquer usuário autenticado do tenant.
Isolado por tenant (`TenantScopedModel` + `TenantScopedViewSetMixin`).

---

## Backend

### Modelos

| Modelo | Campos principais |
|---|---|
| `Empreendimento` | `empreendimento` (nome), `razao_social` (único), `cnpj` (único), `telefone`, `endereco`, `data_inicio_prevista`, `data_fim_prevista`, `data_inicio_real`, `data_fim_real`, `orcamento_total` (decimal), `status_empreendimento` (choices), `descricao` |
| `ContaBancariaEmpreendimento` | `empreendimento` FK, `codigo_banco`, `agencia`, `agencia_dv`, `conta`, `conta_dv`, `numero_agencia`, `numero_conta`, `tipo_conta` (choices), `codigo_pix`, `codigo_cedente`, `carteira`, `is_principal` (0/1), `observacoes` |
| `CustoEmpreendimento` | `empreendimento` FK, `tipo_custo` (choices — 19 categorias), `fornecedor` FK (nullable), `produto_servico` FK (nullable), `descricao`, `valor`, `quantidade`, `valor_total`, `data_custo`, `nota_fiscal`, `chave_acesso` (nullable — chave NF-e 44 dígitos), `arquivo_xml` (nullable — NF-e XML) |

### Choices

| Campo | Opções |
|---|---|
| `status_empreendimento` | `planejamento`, `em_execucao`, `concluido`, `cancelado` |
| `tipo_conta` | `corrente`, `poupanca`, `investimento` |
| `tipo_custo` | `automovel`, `equipamentos`, `extra`, `fixo`, `funcionarios`, `imovel`, `impostos`, `imprevisto`, `manutencao`, `materiais`, `mobiliario`, `publicidade`, `seguros`, `servicos`, `servicos_terceiros`, `taxas`, `transporte`, `variavel`, `outros` |

### Relações

- `ContaBancariaEmpreendimento.empreendimento` e `CustoEmpreendimento.empreendimento` → `Empreendimento`
- `CustoEmpreendimento.fornecedor` → `fornecedores.Fornecedor` (nullable)
- `CustoEmpreendimento.produto_servico` → `fornecedores.ProdutoServicoFornecedor` (nullable)
- Referenciado por: `obras.Obra`, `clientes.ClienteEmpreendimento`/`ContratoCliente`,
  `moduloerp.*` (ContaPagar/ContaReceber/Transacao/NotaFiscal), `rh.Funcionario.empreendimento_vinculado`,
  `modulocrm.Opportunity`

### Endpoints (`/api/`)

| Endpoint | Operações | Filtros |
|---|---|---|
| `/empreendimentos/` | `GET` lista · `POST` cria | `?search=` (nome/razão social/CNPJ) |
| `/empreendimentos/:id/` | `GET` · `PUT`/`PATCH` · `DELETE` | — |
| `/empreendimentos/por-funcionario/` | `GET` | `?funcionario_id=X` (obras com responsável técnico X) |
| `/contas-bancarias-empreendimentos/` | `GET` lista · `POST` cria | `?empreendimento=<id>` |
| `/contas-bancarias-empreendimentos/:id/` | `GET` · `PUT`/`PATCH` · `DELETE` | — |
| `/custos-empreendimentos/` | `GET` lista · `POST` cria | `?empreendimento=<id>`, `?search=` (descrição/nota fiscal) |
| `/custos-empreendimentos/:id/` | `GET` · `PUT`/`PATCH` · `DELETE` | — |

Rotas registradas no roteador central em [config/urls.py](../../backend/config/urls.py).
O `empreendimentos/urls.py` do app está vazio — não é necessário.

### Serializers

Todos usam `fields = '__all__'`. Nenhum campo extra além dos do modelo.

### Notas do backend

- **`chave_acesso` e `arquivo_xml`** em `CustoEmpreendimento` são **opcionais** (migration `0003`).
  O modelo foi originalmente projetado para importação de NF-e XML; a UI atual faz entrada manual.
  Quando a importação NF-e for implementada, esses campos serão preenchidos automaticamente.
- **`numero_agencia` / `numero_conta`** em `ContaBancariaEmpreendimento` duplicam `agencia`/`conta`;
  o hook frontend os espelha automaticamente no payload de criação/edição.
- O índice parcial `emp_status_execucao_idx` otimiza filtros por `status_empreendimento = 'em_execucao'`.

---

## Frontend

### Páginas

| Rota | Componente | Funcionalidade |
|---|---|---|
| `/app/empreendimentos` | `EmpreendimentosListPage` | Tabela; busca por nome/razão social/CNPJ (client-side); filtro de status; botão "+ Novo" |
| `/app/empreendimentos/:id` | `EmpreendimentoDetailPage` | Breadcrumb + header + 4 KPIs + 4 abas + botões Editar/Excluir |

### Abas do detalhe

| Aba | Conteúdo | CRUD |
|---|---|---|
| **Visão Geral** | Campos cadastrais, datas reais, descrição | Editar via sheet no header |
| **Obras** | Tabela de `obras.Obra` vinculadas; clique navega para detalhe da obra | Leitura — obras são gerenciadas em `/app/obras` |
| **Contas Bancárias** | Cards de `ContaBancariaEmpreendimento` com flag "Principal" | Criar (botão "Nova Conta") · Editar · Excluir por card |
| **Custos** | Tabela de `CustoEmpreendimento` com total acumulado | Criar (botão "Registrar Custo") · Editar · Excluir por linha |

### Componentes

| Arquivo | Descrição |
|---|---|
| `EmpreendimentoForm.tsx` | Sheet lateral criar/editar `Empreendimento`; máscaras CNPJ, telefone e moeda em tempo real |
| `EmpreendimentoStatusBadge.tsx` | Badge colorido por status |
| `ContaBancariaForm.tsx` | Sheet lateral criar/editar `ContaBancariaEmpreendimento`; campos bancários completos (banco, agência+DV, conta+DV, PIX, cedente, carteira, tipo, principal) |
| `CustoEmpreendimentoForm.tsx` | Sheet lateral criar/editar `CustoEmpreendimento`; select de 19 tipos, valor + quantidade com preview do total calculado em tempo real; campo opcional de nota fiscal |

### Hooks / funções exportadas

| Símbolo | Arquivo | Responsabilidade |
|---|---|---|
| `useEmpreendimentos(filters)` | `useEmpreendimentos.ts` | Lista com filtro client-side (busca textual + status) |
| `useEmpreendimento(id)` | `useEmpreendimento.ts` | Detalhe: fetch paralelo de empreendimento + contas + custos |
| `createEmpreendimento(payload)` | `useEmpreendimento.ts` | `POST /api/empreendimentos/` |
| `updateEmpreendimento(id, payload)` | `useEmpreendimento.ts` | `PATCH /api/empreendimentos/:id/` |
| `deleteEmpreendimento(id)` | `useEmpreendimento.ts` | `DELETE /api/empreendimentos/:id/` |
| `createContaBancaria(payload)` | `useEmpreendimento.ts` | `POST /api/contas-bancarias-empreendimentos/`; espelha `numero_agencia`/`numero_conta` automaticamente |
| `updateContaBancaria(id, payload)` | `useEmpreendimento.ts` | `PATCH /api/contas-bancarias-empreendimentos/:id/` |
| `deleteContaBancaria(id)` | `useEmpreendimento.ts` | `DELETE /api/contas-bancarias-empreendimentos/:id/` |
| `createCusto(payload)` | `useEmpreendimento.ts` | `POST /api/custos-empreendimentos/`; calcula `valor_total = valor × quantidade` |
| `updateCusto(id, payload)` | `useEmpreendimento.ts` | `PATCH /api/custos-empreendimentos/:id/`; recalcula `valor_total` se valor ou quantidade mudar |
| `deleteCusto(id)` | `useEmpreendimento.ts` | `DELETE /api/custos-empreendimentos/:id/` |

### Comportamentos notáveis

- **Busca client-side:** filtra nome e razão social por texto; CNPJ só entra no filtro se o termo tiver dígitos (evita false positives em strings vazias).
- **Preview de total:** `CustoEmpreendimentoForm` exibe o total `valor × quantidade` em tempo real antes de salvar.
- **Modal de exclusão:** React próprio (não `window.confirm()`); exclusão atual é hard delete — soft delete virá com a tabela `Lixo` (Fase 8).
- **Máscara de moeda:** formatação BRL em tempo real no `onChange` no `EmpreendimentoForm`.

---

## Status (05/06/2026)

| Camada | Status |
|---|---|
| Backend — modelos, views, serializers, filtros | ✅ Completo |
| Frontend — lista, detalhe, 4 abas com CRUD total | ✅ Completo |
| Importação NF-e XML para custos | 📋 Futuro — campos `chave_acesso`/`arquivo_xml` prontos no modelo |
| Soft delete (tabela `Lixo`) | 📋 Fase 8 |
| Busca server-side na listagem (escala) | 📋 Fase 8 — filtro client-side adequado até ~5 mil registros |
