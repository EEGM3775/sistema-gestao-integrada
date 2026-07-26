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
| `Unidade` | `empreendimento` FK, identificação estruturada (`quadra`, `lote`, `bloco_torre`, `andar`, `apto`), `tipo` (choices), `situacao` (choices), `valor_base` (preço de tabela), `area_privativa`, `area_total`, `endereco`, `observacoes`. Propriedade `rotulo` ("QD 12 · LT 05" / "Torre A · 3º · 302") — **fonte única** do nome da unidade em toda a plataforma |

#### `Unidade` — o que se vende

A unidade é **cadastro do empreendimento, não da venda**. Antes ela nascia junto com a aquisição
(um rótulo livre digitado no formulário do cliente, em paralelo a campos estruturados), o que
permitia dois problemas que nada na tela denunciava: a mesma unidade descrita de dois jeitos e o
mesmo lote vendido duas vezes por caminhos diferentes. Agora a unidade existe **antes** do comprador
e a aquisição apenas aponta para ela.

- **Unicidade:** `UniqueConstraint(tenant, empreendimento, quadra, lote, bloco_torre, andar, apto)` —
  a trava que o texto livre nunca teve ("Apto 101" e "apto 101" passavam como unidades diferentes).
  Ao menos um dos cinco níveis é obrigatório (validação do serializer): unidade sem nível não tem nome.
- **`valor_base` é preço de tabela**, a referência da negociação — não o que o cliente paga. O valor
  final sai do plano de pagamento da aquisição, que é da venda, não do lote.
- **`situacao`** (`disponivel`/`reservada`/`vendida`/`indisponivel`) é mantida pelo servidor: vender
  marca `vendida`, cancelar a aquisição libera. Unidade vendida não é excluível (409).
- **Permissão:** reusa `obra.empreendimento` — quem cadastra o empreendimento cadastra o que ele vende.
- RLS fail-closed própria ([migration 0007](../../backend/empreendimentos/migrations/0007_unidade.py)):
  a política global de `nucleo/0011` só alcançou as tabelas que existiam quando rodou.

### Choices

| Campo | Opções |
|---|---|
| `status_empreendimento` | `planejamento`, `em_execucao`, `concluido`, `cancelado` |
| `Unidade.tipo` | `lote`, `apartamento`, `casa`, `sala`, `outro` |
| `Unidade.situacao` | `disponivel`, `reservada`, `vendida`, `indisponivel` |
| `tipo_conta` | `corrente`, `poupanca`, `investimento` |
| `tipo_custo` | `automovel`, `equipamentos`, `extra`, `fixo`, `funcionarios`, `imovel`, `impostos`, `imprevisto`, `manutencao`, `materiais`, `mobiliario`, `publicidade`, `seguros`, `servicos`, `servicos_terceiros`, `taxas`, `transporte`, `variavel`, `outros` |

### Relações

- `ContaBancariaEmpreendimento.empreendimento`, `CustoEmpreendimento.empreendimento` e
  `Unidade.empreendimento` → `Empreendimento`
- `clientes.ClienteEmpreendimento.unidade` → `Unidade` (a venda aponta para a unidade; uma unidade,
  uma aquisição — `UniqueConstraint(tenant, unidade)`)
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
| `/app/empreendimentos/:id` | `EmpreendimentoDetailPage` | Breadcrumb + header + 4 KPIs + **5 abas** + botões Editar/Excluir |

### Abas do detalhe

| Aba | Conteúdo | CRUD |
|---|---|---|
| **Visão Geral** | **Contagem de unidades** (cadastradas · à venda · vendidas), campos cadastrais, datas reais, descrição | Editar via sheet no header |
| **Obras** | Tabela de `obras.Obra` vinculadas; clique navega para detalhe da obra | Leitura — obras são gerenciadas em `/app/obras` |
| **Contas Bancárias** | Cards de `ContaBancariaEmpreendimento` com flag "Principal" | Criar (botão "Nova Conta") · Editar · Excluir por card |
| **Custos** | Tabela de `CustoEmpreendimento` com total acumulado | Criar (botão "Registrar Custo") · Editar · Excluir por linha |
| **Unidades** | Grade linhas-e-colunas do estoque à venda — colunas ordenáveis **no servidor** (sobre o estoque inteiro, não a página carregada), filtros por situação/quadra, busca e carregamento por página. Ordem padrão é a do endereço (quadra › lote › bloco › andar › apto) e **numérica**: em ordem de texto o lote 10 viria antes do 2 | Criar · Editar · Excluir (vendida é barrada — cancele a aquisição antes) |

### Componentes

| Arquivo | Descrição |
|---|---|
| `EmpreendimentoForm.tsx` | Sheet lateral criar/editar `Empreendimento`; máscaras CNPJ, telefone e moeda em tempo real |
| `EmpreendimentoStatusBadge.tsx` | Badge colorido por status |
| `UnidadesTab.tsx` | A aba Unidades (grade + filtros + paginação) |
| `UnidadeForm.tsx` | Sheet criar/editar `Unidade`: identificação nos cinco níveis, valor de tabela, tipo, situação e áreas. "Vendida" não é escolha — sai da existência de uma aquisição |
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
