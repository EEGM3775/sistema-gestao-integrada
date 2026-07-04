# Domínio de negócio

> Como as entidades do ERP se conectam. O negócio é **construção civil / incorporação imobiliária**:
> uma incorporadora toca **empreendimentos**, que se desdobram em **obras**, vende unidades a
> **clientes**, compra de **fornecedores**, controla o **financeiro** e gerencia o **RH**. Tudo é
> isolado por **tenant** (ver [arquitetura/dados-e-tenancy.md](arquitetura/dados-e-tenancy.md)). Detalhe campo a campo em cada
> [doc de módulo](modulos/README.md); aqui está o mapa das ligações.

## Entidade central: `Empreendimento`

O **empreendimento** é o eixo. Quase tudo de negócio aponta para ele (direta ou indiretamente):

```
                              ┌───────────────────┐
                              │   Empreendimento  │  (empreendimentos)
                              │  razão social,    │
                              │  CNPJ, orçamento  │
                              └─────────┬─────────┘
        ┌──────────────┬───────────────┼───────────────┬──────────────────┐
        │              │               │               │                  │
   ┌────▼────┐   ┌─────▼──────┐  ┌─────▼──────┐  ┌──────▼───────┐  ┌───────▼────────┐
   │  Obra   │   │ Cliente    │  │  Custo     │  │ Conta        │  │ Contas a pagar/│
   │ (obras) │   │Empreendim. │  │Empreendim. │  │Bancária Emp. │  │recb (moduloerp)│
   └────┬────┘   │(clientes)  │  └─────┬──────┘  └──────────────┘  └────────────────┘
        │        └─────┬──────┘        │
   ┌────▼─────┐        │          ┌────▼─────────────┐
   │EtapaObra │        │          │ Fornecedor       │
   │DiárioObra│        │          │ ProdutoServico   │
   │DocObra   │        │          │ (fornecedores)   │
   └──────────┘        │          └──────────────────┘
                  ┌────▼──────────┐
                  │ContratoCliente│
                  │CobrancaCliente│ → boletos
                  │ContaReceber   │
                  └───────────────┘
```

## Cadeia comercial (venda de unidade)

`Cliente` → `ClienteEmpreendimento` (aquisição de uma unidade) → `ContratoCliente` →
`CobrancaCliente` (parcelas) / `ContaReceber` → `Boleto`.

- `ClienteEmpreendimento` liga **cliente ↔ empreendimento** + unidade comprada, valor e condições
  (`unique(empreendimento, unidade_comprada)`).
- `ContratoCliente` referencia cliente, empreendimento, a aquisição, e ainda um **`responsavel`**
  (`rh.Funcionario`) e um **`vendedor`** (`fornecedores.Fornecedor`).
- No financeiro, `CobrancaCliente` e `ContaReceber` apontam para o cliente (e a cobrança, ao
  `ContratoCliente`); `Boleto` pode estar ligado a uma `ContaReceber` (emitido) **ou** a uma
  `ContaPagar` (recebido) — nunca aos dois (CHECK constraint).

## Cadeia de suprimentos (compra)

`Fornecedor` → `ProdutoServicoFornecedor` (catálogo) → `CustoEmpreendimento` / `ContaPagar` /
`NotaFiscal` (recebida).

- `CustoEmpreendimento` liga empreendimento ↔ fornecedor ↔ produto/serviço, com XML da NF-e.
- `ContaPagar` aponta para fornecedor, empreendimento e (opcional) `NotaFiscal`.
- `NotaFiscal` (recebida) liga empreendimento ↔ fornecedor; `db_table = financeiro_notafiscal`.

## Obra e execução

`Empreendimento` → `Obra` → `EtapaObra` / `DocumentoObra` / `DiarioObra`.

- `Obra.empreendimento` é nullable (pode haver obra avulsa). `Obra` tem M2M com `rh.Funcionario`:
  **`responsaveis_tecnicos`** e **`equipe`**.
- `EtapaObra` e `DocumentoObra` têm `responsavel` (`rh.Funcionario`); `DocumentoObra.aprovador` é
  `nucleo.Usuario`.
- `DiarioObra` (módulo [modulodiario](modulos/modulodiario.md)) registra o dia-a-dia da obra; seus
  `DocumentoDiario` (fotos) disparam **análise de IA** (funcoesia) e se ligam ao mundo do **drone**
  pela Fase 3 (projeto de drone vinculado a `obraId`/`empreendimentoId`).

## RH transversal

`rh.Funcionario` é referenciado por obras (responsáveis/equipe), etapas, documentos e contratos.
- `Funcionario.usuario` é OneToOne com `nucleo.Usuario` (o funcionário pode ser um login do sistema).
- `Funcionario.empreendimento_vinculado` o conecta a um empreendimento.
- Em torno do funcionário: `Cargo`, `DadoMedicoFuncionario` (**PII sensível** — LGPD),
  `DocumentoFuncionario`, `DadoBancarioFuncionario`, `PagamentoFuncionario`, `FolhaPagamento`.

## Financeiro como agregador (`moduloerp`)

`ContaPagar` e `ContaReceber` são o **título único** da empresa (o legado `Fatura` foi consolidado
nelas em 07/06/2026): ligam **empreendimento + fornecedor/cliente**, têm `dar_baixa()` como caminho
único de baixa e rateiam por `CentroCusto`. Uma `ContaReceber` pode originar **NFS-e**
(`NotaFiscalServico`) ou **NF-e** (`NotaFiscalProduto`) via o microsserviço
[funcoesnf](modulos/funcoesnf.md), e **boleto/cobrança Asaas** via
[funcoescobrancas](modulos/funcoescobrancas.md). `Transacao` registra entradas/saídas de uma conta,
podendo apontar para obra e empreendimento. Ver [modulos/moduloerp.md](modulos/moduloerp.md).

## CRM (funil) e sua ligação ao núcleo

`Lead` → `Account` → `Contact` → `Opportunity` → `OpportunityProduct`; `Interaction` (tarefas/
contatos) liga-se a lead/contato/oportunidade.
- `Account.cliente_associado` e `Contact.cliente_associado` (OneToOne com `clientes.Cliente`) **ligam
  o CRM ao cadastro real**; `Opportunity.empreendimento` conecta a negociação a um empreendimento;
  `OpportunityProduct.product` referencia o catálogo de `fornecedores`.
- A conversão de lead, o scoring e as notificações de prazo rodam **in-process** no próprio
  `modulocrm` (Fase 11.2). Ver [modulos/modulocrm.md](modulos/modulocrm.md).

## Identidade (espelho local)

O ERP **não** é dono da identidade (ver [acesso-e-permissoes.md](acesso-e-permissoes.md)). Em
`nucleo` existem espelhos locais provisionados por JIT a partir do JWT da IAM: `Tenant` e `Usuario`
(`Usuario.tenant`). `nucleo.Perfil`/`Permissao` são legado (a fonte de papéis é a IAM, via claims).
Toda entidade acima herda `tenant` do mixin `TenantScopedModel`.

## Onde olhar no código

| Entidade | Arquivo |
|---|---|
| Empreendimento, Conta/Custo | [backend/empreendimentos/models.py](../backend/empreendimentos/models.py) |
| Obra, Etapa, Documento | [backend/obras/models.py](../backend/obras/models.py) |
| Cliente, Aquisição, Contrato | [backend/clientes/models.py](../backend/clientes/models.py) |
| Fornecedor, Produto/Serviço | [backend/fornecedores/models.py](../backend/fornecedores/models.py) |
| ContaPagar/ContaReceber, NF, Boleto, Transacao, CentroCusto | [backend/moduloerp/models.py](../backend/moduloerp/models.py) |
| Funcionário, Folha, etc. | [backend/rh/models.py](../backend/rh/models.py) |
| Diário de obra | [backend/modulodiario/models.py](../backend/modulodiario/models.py) |
| CRM | [backend/modulocrm/models.py](../backend/modulocrm/models.py) |
