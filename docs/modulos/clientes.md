# Clientes

> Os clientes-compradores: cadastro, aquisição de unidades, contratos, documentos e dados bancários.
> Backend: [backend/clientes/](../../backend/clientes/) · Frontend: [frontend/src/modules/clientes/](../../frontend/src/modules/clientes/)

## Acesso

App **base** — sem `required_module`. Isolado por tenant.
**LGPD:** guarda PII (CPF/CNPJ, data de nascimento, endereço, dados bancários, documentos pessoais).
Mascaramento de campos por papel é pendência da Fase 9.

---

## Backend

### Modelos

| Modelo | Campos principais |
|---|---|
| `Cliente` | `nome_completo`, `cpf_cnpj` (único), `email` (único), `telefone`, endereço completo (`endereco`, `numero_endereco`, `complemento_endereco`, `bairro`, `cidade`, `estado`, `cep`, `cidade_ibge`), `data_nascimento`, `estado_civil` (choices), `profissao`, `data_cadastro`, `id_cliente_gateway` |
| `ClienteEmpreendimento` | `cliente` FK, `empreendimento` FK, `unidade_comprada`, `endereco_unidade`, `data_compra`, `valor_compra`, `condicoes_pagamento` (choices), `observacoes_compra` |
| `ContratoCliente` | `cliente` FK, `empreendimento` FK, `cliente_empreendimento` FK (opcional), `numero_contrato` (único), `data_assinatura`, `objeto_contrato`, `arquivo_contrato` (URLField), `status_contrato` (choices), `responsavel` FK `rh.Funcionario`, `vendedor` FK `fornecedores.Fornecedor` |
| `DocumentoCliente` | `cliente` FK, `tipo_documento` (choices), `nome_documento`, `arquivo` (FileField → `media/documentos_clientes/`), `data_upload` |
| `DadoBancarioCliente` | `cliente` FK, `codigo_banco`, `agencia`, `agencia_dv`, `conta`, `conta_dv`, `tipo_conta` (choices), `titular_nome`, `titular_cpf_cnpj`, `chave_pix`, `codigo_cedente`, `carteira`, `observacoes` |

### Choices

| Campo | Opções |
|---|---|
| `estado_civil` | `solteiro`, `casado`, `divorciado`, `viuvo`, `uniao_estavel` |
| `condicoes_pagamento` | `a_vista`, `financiamento_bancario`, `financiamento_direto`, `permuta`, `cartao`, `outro` |
| `status_contrato` | `ativo`, `inativo`, `cancelado`, `concluido` |
| `tipo_documento` | `rg`, `cpf`, `cnh`, `comprovante_residencia`, `certidao_casamento`, `outros` |
| `tipo_conta` | `corrente`, `poupanca`, `investimento`, `salario`, `outros` |

### Relações

- `ClienteEmpreendimento` liga `Cliente` ↔ `empreendimentos.Empreendimento` (`unique(empreendimento, unidade_comprada)`)
- `ContratoCliente` → `Cliente`, `Empreendimento`, aquisição, `rh.Funcionario` (responsável), `fornecedores.Fornecedor` (vendedor)
- Referenciado por: `moduloerp` (`ContaReceber`, `CobrancaCliente`, `NotaFiscalServico`) e `modulocrm` (`Account.cliente_associado`, `Contact.cliente_associado`)

### Endpoints (`/api/`)

| Endpoint | Filtros disponíveis |
|---|---|
| `GET/POST /clientes/` | `?search=` (nome/CPF/email/telefone), `?empreendimento=<id>` (filtra por aquisição), `?estado_civil=`, `?cidade=`, `?estado=` |
| `GET/PUT/PATCH/DELETE /clientes/:id/` | — |
| `GET /clientes/divergencias-asaas/` | Relatório (só leitura) de divergências de identidade banco × Asaas — `sem_documento`/`nome_divergente`/`vinculo_divergente`. Consumido ao abrir "Novo Cliente". Ver [funcoescobrancas.md](funcoescobrancas.md#auditoria-de-divergências-banco--asaas). |
| `GET/POST /clientes-empreendimentos/` | `?cliente=`, `?empreendimento=`, `?condicoes_pagamento=` |
| `GET/PUT/PATCH/DELETE /clientes-empreendimentos/:id/` | — |
| `GET/POST /contratos-clientes/` | `?cliente=`, `?empreendimento=`, `?status_contrato=`, `?responsavel=`, `?vendedor=` |
| `GET/PUT/PATCH/DELETE /contratos-clientes/:id/` | — |
| `GET/POST /documentos-clientes/` | `?cliente=`, `?tipo_documento=` · aceita `multipart/form-data` para upload |
| `GET/DELETE /documentos-clientes/:id/` | — |
| `GET/POST /dados-bancarios-clientes/` | `?cliente=` |
| `GET/PUT/PATCH/DELETE /dados-bancarios-clientes/:id/` | — |

### Serializers

Todos os serializers expõem `fields = '__all__'` com `read_only_fields` nos PKs, timestamps e `tenant`.
Campos de exibição adicionados (somente leitura):

| Serializer | Campos extras |
|---|---|
| `ClienteEmpreendimentoSerializer` | `cliente_nome`, `empreendimento_nome` |
| `ContratoClienteSerializer` | `cliente_nome`, `empreendimento_nome`, `responsavel_nome`, `vendedor_nome` |
| `DocumentoClienteSerializer` | `cliente_nome`, `tipo_documento_display` |
| `DadoBancarioClienteSerializer` | `cliente_nome` |

### Filtros (`filters.py`)

- `ClienteFilter` — busca por nome/CPF/email/cidade; filtro por `empreendimento` via reverse relation (`clienteempreendimento__empreendimento`, com `.distinct()`)
- `ClienteEmpreendimentoFilter`, `ContratoClienteFilter`, `DocumentoClienteFilter` — filtros diretos por FK

---

## Frontend

### Páginas

| Rota | Componente | Funcionalidade |
|---|---|---|
| `/app/clientes` | `ClientesListPage` | Tabela de clientes; busca por texto (server-side); filtro por empreendimento (server-side via `?empreendimento=`); botão "+ Novo Cliente" abre sheet |
| `/app/clientes/:id` | `ClienteDetailPage` | Detalhe com 4 abas: Dados Cadastrais · Aquisições/Contratos · Documentos · Dados Bancários |

### Abas do detalhe

| Aba | Conteúdo | CRUD |
|---|---|---|
| **Dados Cadastrais** | Todos os campos do `Cliente` em grid | Editar via sheet (botão no header) · Excluir com confirmação |
| **Aquisições / Contratos** | Seção Aquisições + seção Contratos | Create + Edit + Delete inline para cada seção |
| **Documentos** | Lista de `DocumentoCliente` com tipo, nome e data | Upload via sheet com seletor de tipo + drop zone · Abrir arquivo · Delete |
| **Dados Bancários** | Cards de `DadoBancarioCliente` com dados bancários | Create + Edit + Delete inline |

### Componentes

| Arquivo | Descrição |
|---|---|
| `ClienteForm.tsx` | Sheet criar/editar `Cliente` — 3 seções (Dados Pessoais, Contato, Endereço); máscaras CPF/CNPJ e CEP; validação de dígito verificador CPF/CNPJ com erro inline; `data_nascimento` com `min=1900-01-01` e `max=hoje` |
| `AquisicaoForm.tsx` | Sheet criar/editar `ClienteEmpreendimento` — select de empreendimento; máscara de moeda; 6 opções de condições de pagamento |
| `ContratoForm.tsx` | Sheet criar/editar `ContratoCliente` — select de empreendimento + aquisição vinculada; URL do arquivo de contrato |
| `DadoBancarioForm.tsx` | Sheet criar/editar `DadoBancarioCliente` — campos bancários completos; validação de dígito verificador CPF/CNPJ do titular |
| `DocumentoUploadForm.tsx` | Sheet upload de `DocumentoCliente` — seletor de tipo, nome, drop zone com feedback visual |

### Hooks

| Arquivo | Responsabilidade |
|---|---|
| `useClientes.ts` | Lista com filtros server-side (`search`, `empreendimento`) |
| `useCliente.ts` | Detalhe: fetch paralelo de cliente + 4 sub-recursos; CRUD completo para todos; upload de documentos via `FormData` |

### Observações técnicas

- Upload de arquivos: `apiClient` detecta `FormData` automaticamente e omite `Content-Type: application/json`, deixando o browser definir `multipart/form-data; boundary=...`
- URLs de mídia (`arquivo` em `DocumentoCliente`): servidas pelo gateway via `location /media/` → ERP Django; `Host` header preserva a porta (`$http_host`) para que Django gere URLs corretas (`http://localhost:8090/media/...`)
- `arquivo_contrato` em `ContratoCliente` é `URLField` — armazena um link para documento externo (Google Drive, S3, etc.), não faz upload direto. Para upload direto, seria necessário migrar para `FileField`
- Datas: campos datetime do Django (ex: `data_cadastro`) são ISO 8601 completos; a função `formatDate` usa `.slice(0, 10)` para extrair apenas a parte de data antes de formatar para `dd/mm/aaaa`

---

## Status (04/06/2026)

| Camada | Status |
|---|---|
| Backend — modelos, views, serializers, filters | ✅ Completo |
| Frontend — lista, detalhe, 4 abas, todos os formulários | ✅ Completo |
| Mascaramento de PII por papel (LGPD) | 📋 Fase 9 |
| `unique` por-tenant em `cpf_cnpj` e `email` (hoje global) | 📋 Fase 8 |
