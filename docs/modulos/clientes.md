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
| `ClienteEmpreendimento` | `cliente` FK, `unidade` FK → `empreendimentos.Unidade`, `empreendimento` FK (denormalizado, mantido a partir da unidade no `save()`), `data_compra`, `condicoes_pagamento` (choices), `observacoes_compra` **+ o plano de pagamento** (abaixo) |
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

#### A venda: da tabela ao carnê

A aquisição deixou de descrever a unidade (isso é cadastro do empreendimento — ver
[empreendimentos.md](empreendimentos.md)) e passou a descrever **a venda**: qual unidade, por quanto
e em que condições. Os campos do plano, todos na aquisição:

| Grupo | Campos |
|---|---|
| Preço | `valor_tabela` (**snapshot** do `valor_base` da unidade no dia da venda), `desconto_percentual`, `desconto_valor`, `valor_compra` (negociado à vista — derivado), `valor_total_plano` (desembolso — derivado) |
| Entrada | `entrada_valor`, `entrada_parcelas`, `entrada_primeiro_vencimento` |
| Saldo | `sistema_amortizacao` (`price`/`sac`), `juros_mensal`, `num_parcelas`, `primeiro_vencimento` |
| Balão | `balao_valor`, `balao_quantidade`, `balao_periodicidade` (`anual`/`semestral`), `balao_primeiro_vencimento` |
| Carnê | `parcelas_geradas_em` (carimbo do botão "Gerar parcelas") |

O cálculo vive em [`clientes/plano_pagamento.py`](../../backend/clientes/plano_pagamento.py), em
funções puras (não tocam banco — é o que permite simular a cada tecla). Três regras que o motor
assume, alinhadas à prática de venda direta de loteadora/incorporadora:

- **A entrada não rende juros** — é sinal, não financiamento. Cobrar juros sobre entrada é o que faz
  a proposta do sistema não bater com a que o corretor fez na mão.
- **O balão abate saldo antes do parcelamento** — senão o comprador pagaria juros sobre o que já se
  comprometeu a quitar à parte.
- **Juros correm a partir da 1ª parcela do saldo**, não da data da venda ("juros inicia na 1ª parcela").

`price()` com taxa zero degenera em saldo ÷ n — a venda "sem juros" não precisa de um terceiro
sistema. A última parcela absorve a sobra de centavos, senão o título fecha com R$ 0,03 em aberto.
**Sem correção monetária** (INCC/IGP-M/IPCA): reajuste anual mexe em parcela já emitida e boleto
vivo — entra depois, com lugar próprio. O que o motor devolve é o plano **na data da assinatura**.

**Gerar parcelas é ato explícito.** Salvar a aquisição grava a proposta; o carnê só vira
`ContaReceber` (uma linha por entrada/parcela/balão, amarrada à unidade) quando o usuário aciona
`POST /api/clientes-empreendimentos/<id>/gerar-parcelas/`, depois de conferir a simulação. **Não
emite boleto** — cobrar é decisão separada, no ERP, unitária ou por lote. Idempotente: a segunda
chamada responde 409 em vez de duplicar o carnê.

### Relações

- `ClienteEmpreendimento` → `empreendimentos.Unidade` (`unique(tenant, unidade)` — **uma unidade, um
  dono**; era o papel do antigo `unique(empreendimento, unidade_comprada)` sobre texto livre, que
  não valia nada porque "Apto 101" e "apto 101" passavam como unidades diferentes)
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
| `GET /clientes-empreendimentos/condicoes/` | O catálogo de formas de pagamento e o que cada uma comporta. A tela **lê** a regra daqui em vez de reescrevê-la. `cadastro.venda.view` |
| `POST /clientes-empreendimentos/simular/` | A proposta sem gravar, recalculada a cada tecla. `cadastro.venda.view` |
| `GET /clientes-empreendimentos/:id/previa-parcelas/` | O carnê que **seria** gerado — quantidade, total, cliente, unidade, faixa de vencimentos. Alimenta a confirmação do botão "Gerar parcelas". `cadastro.venda.view` |
| `POST /clientes-empreendimentos/:id/gerar-parcelas/` | Materializa o carnê como `ContaReceber`. Idempotente (409 na segunda). `cadastro.venda.gerar_carne` |
| `GET\|POST /clientes-empreendimentos/:id/corrigir/` | Correção monetária: `GET` é prévia, `POST` aplica. `cadastro.venda.gerar_carne` |
| `GET/POST /contratos-clientes/` | `?cliente=`, `?empreendimento=`, `?status_contrato=`, `?responsavel=`, `?vendedor=` |
| `GET/PUT/PATCH/DELETE /contratos-clientes/:id/` | — |
| `GET/POST /documentos-clientes/` | `?cliente=`, `?tipo_documento=` · aceita `multipart/form-data` para upload |
| `GET/DELETE /documentos-clientes/:id/` | — |
| `GET/POST /dados-bancarios-clientes/` | `?cliente=` |
| `GET/PUT/PATCH/DELETE /dados-bancarios-clientes/:id/` | — |

### A condição de pagamento rege o plano

O catálogo é [`plano_pagamento.CONDICOES`](../../backend/clientes/plano_pagamento.py) — **um lugar
só**, lido pelo motor de cálculo, pelo serializer e pela tela. Cada condição declara se há entrada,
parcelas e balões (intercaladas/anuais), e se ela **quita por fora**:

| Condição | Entrada | Parcelas | Balões | Quita fora |
|---|:--:|:--:|:--:|:--:|
| `financiamento_direto` | ✔ | ✔ | ✔ | — |
| `a_vista` | — | — | — | — |
| `financiamento_bancario` | ✔ | — | — | ✔ |
| `permuta` | — | — | — | ✔ |
| `cartao` | ✔ | — | — | ✔ |
| `outro` | ✔ | ✔ | ✔ | ✔ |

**`quita_fora` existe porque nem toda venda passa inteira pelo carnê.** Na permuta a construtora não
recebe parcela; no financiamento bancário recebe só o sinal e o banco quita o resto; no cartão o
parcelamento é da operadora. O que sobra do valor negociado depois de entrada e balões vira
`Plano.fora_do_carne` — um número declarado, exibido na proposta, que fecha a conta
(`total + fora_do_carne == valor_negociado`). Não é desconto nem dívida esquecida: é valor liquidado
por outro caminho.

O `financiamento_direto` **não** quita por fora: ali, saldo sem parcela é falta real e vira erro.
Condição desconhecida cai nessa mesma severidade — no permissivo, um plano incompleto viraria um
"pago por fora" silencioso.

`normalizar_por_condicao()` apaga do registro o que a condição não comporta, e roda no serializer
além da tela: a tela não é a única porta (API, importação, admin).

### O vencimento que vai ao boleto

O carnê nasce em **dia útil bancário**. `montar()` recebe o calendário **injetado**
(`ajustar_vencimento`) e continua puro; quem sabe onde fica o imóvel é
[`clientes/vencimento.py`](../../backend/clientes/vencimento.py), e quem sabe o que é dia útil é
[`modulocalendar/dias_uteis.py`](../../backend/modulocalendar/dias_uteis.py).

- **A praça é a do imóvel, não a do comprador.** UF de `Empreendimento.estado`; o código IBGE — sem o
  qual não se afirma feriado municipal — do `Local` do empreendimento no Maps. Sem ele, o ajuste vale
  só para nacional + estadual, e **diz** isso (`calendario.municipio == false`).
- **A parcela guarda as duas datas.** `vencimento` é a pagável; `vencimento_contratual` é a do
  contrato; `ajuste_motivo` diz por que diferem ("domingo", nome do feriado).
- **O ajuste é só da data, nunca do valor.** Juros correm por parcela, não por dia corrido.
- **A base de feriados nasce vazia** (`manage.py sincronizar_feriados`). Sem ela o vencimento desvia
  de fim de semana e não de feriado; as respostas trazem `calendario.feriadosCarregados` para a tela
  não prometer o que não aconteceu.

A descrição do título sai de `descricao_do_titulo()` — `Parcela 32/36 — Residencial Aurora · QD 4 ·
LT 06`. O empreendimento vem antes da unidade porque o boleto chega sem a tela em volta, e a quadra 4
existe em mais de um loteamento. Títulos antigos são reescritos pelo comando
`renomear_titulos_do_carne` (prévia por padrão; grava com `--aplicar`).

### Serializers

Todos os serializers expõem `fields = '__all__'` com `read_only_fields` nos PKs, timestamps e `tenant`.
Campos de exibição adicionados (somente leitura):

| Serializer | Campos extras |
|---|---|
| `ClienteEmpreendimentoSerializer` | `cliente_nome`, `empreendimento_nome`, `rotulo_unidade`, `unidade_valor_base`, `plano` (resumo recalculado). `empreendimento`, `valor_tabela`, `valor_compra` e `valor_total_plano` são **read-only**: derivam da unidade e do motor de cálculo — aceitá-los do cliente da API permitiria gravar um contrato cujo total não bate com o próprio plano |
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
- URLs de mídia (`arquivo` em `DocumentoCliente`): servidas pelo gateway via `location /media/` → backend Django; `Host` header preserva a porta (`$http_host`) para que Django gere URLs corretas (`http://localhost:8090/media/...`)
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
