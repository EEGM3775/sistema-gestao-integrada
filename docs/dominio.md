# Domínio de negócio

> Como as entidades do backend se conectam. O negócio é **construção civil / incorporação imobiliária**:
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

- `Unidade` é **o que se vende** — cadastro do empreendimento (quadra/lote/bloco/andar/apto + preço
  de tabela + situação), anterior ao comprador. É a fonte única do rótulo da unidade
- `ClienteEmpreendimento` é **a venda**: aponta para uma `Unidade` (uma unidade, um dono) e carrega o
  plano de pagamento (desconto → entrada → saldo em Price/SAC → balões)
  (`unique(empreendimento, unidade_comprada)`). A unidade é identificada de duas formas: o rótulo
  livre `unidade_comprada` (histórico, e a chave de unicidade) e os campos **estruturados**
  `quadra`/`lote`/`bloco_torre`/`andar`/`unidade` — só estes permitem ordenar, filtrar e agrupar a
  carteira por quadra. A property `rotulo_unidade` monta a exibição ("QD 12 · LT 05",
  "Torre A · 3º · 302") e cai no rótulo livre quando não há campo estruturado.
- `Empreendimento` tem `cidade`/`estado` próprios além do `endereco` em texto livre — é a
  localização do **imóvel** (a de `Cliente` é a do comprador).
- `ContratoCliente` referencia cliente, empreendimento, a aquisição, e ainda um **`responsavel`**
  (`rh.Funcionario`) e um **`vendedor`** (`fornecedores.Fornecedor`).
- No financeiro, `ContaReceber` aponta para o cliente e, opcionalmente, para a **aquisição**
  (`cliente_empreendimento`) e o **contrato** — sem esse vínculo, um cliente com dois lotes no mesmo
  loteamento teria a inadimplência somada num balaio só e a carteira por unidade seria um número
  inventado. Parcelas anteriores ao vínculo ficam com os campos nulos: contam no total do cliente e
  ficam fora do rateio por unidade. `Boleto` pode estar ligado a uma `ContaReceber` (emitido) **ou**
  a uma `ContaPagar` (recebido) — nunca aos dois (CHECK constraint).
- `CobrancaCliente` existe no schema com CRUD exposto, mas **nada no sistema escreve nela** — a
  cadeia viva é `ContaReceber` → `Boleto` (Asaas). Consolidação pendente em
  [pendencias.md, A5](pendencias.md).

## Cadeia de suprimentos (compra)

Registro financeiro do que foi comprado: `Fornecedor` → `ProdutoServicoFornecedor` (catálogo) →
`CustoEmpreendimento` / `ContaPagar` / `NotaFiscal` (recebida).

- `CustoEmpreendimento` liga empreendimento ↔ fornecedor ↔ produto/serviço, com XML da NF-e.
- `ContaPagar` aponta para fornecedor, empreendimento e (opcional) `NotaFiscal`.
- `NotaFiscal` (recebida) liga empreendimento ↔ fornecedor; `db_table = financeiro_notafiscal`.

**Processo de compra (`moduloscm`, módulo `scm`):** o SCM modela o *fluxo* que antecede esse registro
— catálogo próprio (`Produto` + `OfertaFornecedor`) → `Demanda` → `Cotacao`/`Proposta` → `PedidoCompra`
(duas vias: compra direta de uma oferta **ou** adjudicação de cotação) → `Recebimento` → `AvaliacaoFornecedor`.
Custo via `moduloscm.CentroCusto` (próprio, mapeia p/ o rateio do ERP). Multi-vertical e com *seams* de
rede/marketplace — ver [modulos/moduloscm.md](modulos/moduloscm.md) e a visão em
[expansão/modulos/moduloscm.md](expansão/modulos/moduloscm.md).

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

O backend **não** é dono da identidade (ver [acesso-e-permissoes.md](acesso-e-permissoes.md)). Em
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
| SCM (suprimentos): Produto, Oferta, Demanda, Cotação, Pedido, Recebimento | [backend/moduloscm/models.py](../backend/moduloscm/models.py) |
