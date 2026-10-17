# Fornecedores

> Cadastro de fornecedores, seus dados bancários e o catálogo de produtos/serviços que oferecem.
> Backend: [backend/fornecedores/](../../backend/fornecedores/) ·
> Frontend: [frontend/src/modules/fornecedores/](../../frontend/src/modules/fornecedores/)

## Acesso

App **base** — sem `required_module`. Isolado por tenant.

---

## Backend

### Modelos

| Modelo | Campos principais |
|---|---|
| `Fornecedor` | `razao_social` (único), `cnpj` (único, **nullable** — pessoa física ou estrangeiro sem CNPJ), `contato` (nome da pessoa), `email` (opcional; único quando preenchido), `emails_adicionais` (lista; o conjunto com o principal é único no tenant), `telefone` |
| `DadoBancarioFornecedor` | `fornecedor` FK, `tipo_conta` (choices), `codigo_banco`, `agencia`, `agencia_dv`, `conta`, `conta_dv`, `chave_pix`, `codigo_cedente`, `carteira`, `observacoes` |
| `ProdutoServicoFornecedor` | `fornecedor` FK, `nome_produto_servico`, `tipo_produto_servico` (choices — lista extensa de materiais/serviços de construção), `unidade_medida`, `preco_unitario`, `descricao` |

### Choices

| Campo | Opções |
|---|---|
| `tipo_conta` | `corrente`, `poupanca`, `outro` |
| `tipo_produto_servico` | 59 categorias: `aluguel`, `aluguel_equipamento`, `aluguel_maquinario`, `assinatura`, `comissao`, `consultoria`, `equipamento_obra`, `equipamento_pessoal`, `ferramenta`, `frete`, `hardware`, `imposto`, `licenca`, `maquina`, `manutencao`, `material_acabamento`, `material_construcao`, `material_electrico`, `material_escritorio`, `material_hidraulico`, `material_jardinagem`, `material_limpeza`, `material_manutencao`, `material_pavimentacao`, `obra`, `produto`, `projeto`, `servico`, `servico_administrativo`, `servico_almoxarifado`, `servico_construcao`, `servico_construcao_civil`, `servico_contabil`, `servico_consultoria`, `servico_eletrica`, `servico_engenharia_arquitetura`, `servico_estoque`, `servico_financeiro`, `servico_gerenciamento`, `servico_hidraulica`, `servico_instalacao`, `servico_juridico`, `servico_logistica`, `servico_manutencao`, `servico_marketing`, `servico_pintura`, `servico_reforma`, `servico_tecnico`, `servico_terceirizado`, `servico_terraplenagem`, `servico_transporte`, `servico_vendas`, `software`, `suporte`, `taxa`, `treinamento`, `veiculo`, `outro` |

### Relações

- `DadoBancarioFornecedor.fornecedor` e `ProdutoServicoFornecedor.fornecedor` → `Fornecedor`
- Referenciado por: `empreendimentos.CustoEmpreendimento` (FK para `Fornecedor` e para `ProdutoServicoFornecedor`), `moduloerp` (`ContaPagar`, `NotaFiscal`), `clientes.ContratoCliente.vendedor`, `modulocrm.OpportunityProduct.product`

### Endpoints (`/api/`)

| Endpoint | Operações | Filtros |
|---|---|---|
| `/fornecedores/` | `GET` lista · `POST` cria | `?search=` (razão social/CNPJ/e-mail/contato/telefone) |
| `/fornecedores/:id/` | `GET` · `PUT`/`PATCH` · `DELETE` | — |
| `/dados-bancarios-fornecedores/` | `GET` lista · `POST` cria | `?fornecedor=<id>` |
| `/dados-bancarios-fornecedores/:id/` | `GET` · `PUT`/`PATCH` · `DELETE` | — |
| `/produtos-servicos-fornecedores/` | `GET` lista · `POST` cria | `?fornecedor=<id>`, `?tipo_produto_servico=` |
| `/produtos-servicos-fornecedores/:id/` | `GET` · `PUT`/`PATCH` · `DELETE` | — |

### Serializers

- `FornecedorSerializer` — `fields = '__all__'`; campo `cnpj` declarado explicitamente como
  `CharField(allow_null=True, allow_blank=True, required=False)` para garantir que `null` seja aceito
  mesmo com cache `.pyc` do DRF (migration `0003` tornou o campo nullable).
- `DadoBancarioFornecedorSerializer` e `ProdutoServicoFornecedorSerializer` — `fields = '__all__'`.

---

## Frontend

### Páginas

| Rota | Componente | Funcionalidade |
|---|---|---|
| `/app/fornecedores` | `FornecedoresListPage` | Tabela; busca server-side por razão social/CNPJ/e-mail/contato; botão "+ Novo Fornecedor" |
| `/app/fornecedores/:id` | `FornecedorDetailPage` | Breadcrumb + header + 3 abas: Dados Cadastrais · Produtos/Serviços · Dados Bancários |

### Abas do detalhe

| Aba | Conteúdo | CRUD |
|---|---|---|
| **Dados Cadastrais** | Razão social, CPF/CNPJ (formatado ou "Sem CPF/CNPJ"), e-mail, telefone (formatado), contato, data de cadastro | Editar via sheet no header · Excluir com confirmação |
| **Produtos / Serviços** | Tabela de `ProdutoServicoFornecedor`: nome, tipo (badge), unidade, preço unitário | Criar · Editar · Excluir por linha |
| **Dados Bancários** | Cards de `DadoBancarioFornecedor`: banco, agência+DV, conta+DV, tipo, PIX | Criar · Editar · Excluir por card |

### Componentes

| Arquivo | Descrição |
|---|---|
| `FornecedorForm.tsx` | Sheet lateral criar/editar `Fornecedor`; campo CPF/CNPJ com auto-detecção de tamanho (≤11 dígitos → máscara CPF, 14 dígitos → máscara CNPJ); validação de dígito verificador CPF e CNPJ com erro inline; checkbox "Não informar" desabilita o campo e envia `null`; campo telefone com máscara `(XX) XXXXX-XXXX` / `(XX) XXXX-XXXX`, armazenando apenas dígitos |
| `DadoBancarioFornecedorForm.tsx` | Sheet lateral criar/editar `DadoBancarioFornecedor`; campos bancários completos (banco, agência+DV, conta+DV, tipo, PIX, cedente, carteira, observações) |
| `ProdutoServicoForm.tsx` | Sheet lateral criar/editar `ProdutoServicoFornecedor`; select com +50 tipos do domínio de construção; campos de unidade, preço e descrição |

### Hooks / funções exportadas

| Símbolo | Arquivo | Responsabilidade |
|---|---|---|
| `useFornecedores(filters)` | `useFornecedores.ts` | Lista com `?search=` server-side |
| `useFornecedor(id)` | `useFornecedor.ts` | Detalhe: fetch paralelo de fornecedor + dados bancários + produtos/serviços |
| `createFornecedor(payload)` | `useFornecedor.ts` | `POST /api/fornecedores/`; envia `cnpj: null` quando "Não informar" |
| `updateFornecedor(id, payload)` | `useFornecedor.ts` | `PATCH /api/fornecedores/:id/` |
| `deleteFornecedor(id)` | `useFornecedor.ts` | `DELETE /api/fornecedores/:id/` |
| `createDadoBancario(payload)` | `useFornecedor.ts` | `POST /api/dados-bancarios-fornecedores/` |
| `updateDadoBancario(id, payload)` | `useFornecedor.ts` | `PATCH /api/dados-bancarios-fornecedores/:id/` |
| `deleteDadoBancario(id)` | `useFornecedor.ts` | `DELETE /api/dados-bancarios-fornecedores/:id/` |
| `createProdutoServico(payload)` | `useFornecedor.ts` | `POST /api/produtos-servicos-fornecedores/` |
| `updateProdutoServico(id, payload)` | `useFornecedor.ts` | `PATCH /api/produtos-servicos-fornecedores/:id/` |
| `deleteProdutoServico(id)` | `useFornecedor.ts` | `DELETE /api/produtos-servicos-fornecedores/:id/` |

### Comportamentos notáveis

- **CPF/CNPJ nullable:** o campo aceita CPF (11 dígitos) ou CNPJ (14 dígitos), com validação de dígito verificador no `onBlur` e no submit. Quando "Não informar" está marcado, o campo é desabilitado, limpo visualmente e `null` é enviado à API — refletindo que o fornecedor é pessoa física sem CPF cadastrado ou empresa estrangeira.
- **Formatação na listagem:** `formatCNPJ` aplica máscara `XX.XXX.XXX/XXXX-XX` (ou mostra `—` para `null`); `formatPhone` aplica `(XX) XXXXX-XXXX` ou `(XX) XXXX-XXXX` conforme o número de dígitos.
- **Armazenamento de telefone:** apenas dígitos são armazenados no banco; a máscara é aplicada somente na exibição e durante a digitação.
- **Modal de exclusão:** React próprio com confirmação antes de deletar o fornecedor principal.

---

## Status (05/06/2026)

| Camada | Status |
|---|---|
| Backend — modelos, views, serializers, filtros | ✅ Completo |
| Frontend — lista, detalhe, 3 abas com CRUD total | ✅ Completo |
| Vinculação de fornecedor ao criar custo de empreendimento (select no form) | 📋 Futuro — FK existe no modelo, falta select na UI de custos |
| Soft delete (tabela `Lixo`) | 📋 Fase 8 |
| `unique` por-tenant em `cnpj` e `email` (hoje global) | 📋 Fase 8 |
