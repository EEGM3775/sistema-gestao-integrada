# Entidades — quem é o dono jurídico de cada coisa

> O tenant é a **conta** (quem assina a plataforma). A **entidade** é o **titular jurídico**: quem
> tem CPF ou CNPJ, emite nota, recebe boleto, paga fornecedor e tem DRE. Um tenant tem uma ou muitas.
> Vale do construtor que trabalha no próprio CPF até o grupo com matriz, filiais e uma SPE por
> loteamento.
> Backend: [backend/entidades/](../../backend/entidades/)

**Por que "entidade" e não "empresa":** no PDP ([acesso-e-permissoes.md §10.7](../acesso-e-permissoes.md))
`empresa` já é o tenant. Reusar a palavra faria "admin da empresa" significar duas coisas.

## 1. Conceitos

| Conceito | O que é |
|---|---|
| `Entidade` | Titular jurídico: `tipo_pessoa` (PF/PJ), `documento` (CPF ou CNPJ, só dígitos, opcional até a emissão), `nome` (razão social ou nome civil), `nome_fantasia`, `papel`, `externa` e, na filial, `matriz` |
| `papel` | `matriz` · `filial` (aponta a matriz) · `spe` (Sociedade de Propósito Específico) · `scp` (Sociedade em Conta de Participação) · `patrimonio_afetacao` (incorporação com RET, CNPJ próprio) · `consorcio` · `pessoa_fisica` · `outra` |
| `externa` | Entidade **fora do grupo**: o dono de um empreendimento em que o tenant só executa (o contratante), ou o sócio externo de uma SPE. Não tem título, caixa nem DRE no tenant e fica fora do consolidado. Pode apontar o `Cliente` que ela é no cadastro |
| `ParticipacaoEmpreendimento` | Quais entidades são donas do empreendimento, com a **cota** (%) e quem é a **administradora** (a líder do consórcio, a ostensiva da SCP). A soma das cotas é 100; há no máximo uma administradora |
| `Empreendimento.entidade_propria` | A entidade com CNPJ do empreendimento: a SPE, a SCP, o consórcio, o patrimônio de afetação — ou, no empreendimento de terceiro, a entidade externa dona dele. Opcional: o pequeno lança o loteamento no próprio CPF |
| `Obra.entidade` | Quem **executa** a obra. Em empreendimento do grupo, herda a dona dele (a `entidade_propria` ou, sem ela, a administradora/maior cota). Em empreendimento de terceiro ou sem empreendimento, é escolhida; o padrão é a matriz |

Toda conta tem **ao menos uma** entidade do grupo: a migração cria a matriz de cada tenant, e não se
exclui a última.

## 2. Quem é dono de cada lançamento

**Todo** título (`ContaPagar`, `ContaReceber`), transação (`Transacao`), centro de custo, nota de
entrada, boleto, carteira de cobrança e integração fiscal pertence a **exatamente uma** entidade do
grupo (nunca a uma externa). A regra, numa função só (`entidades.regras.entidade_do_lancamento`), que
o `save()` do título aplica quando ninguém informou:

1. **Obra** → a entidade da obra (quem executa é quem paga e fatura).
2. **Empreendimento do grupo com `entidade_propria`** → ela.
3. **Empreendimento do grupo sem `entidade_propria`** → a administradora; sem ela, a maior cota. A
   parte das outras participantes sai por **intercompany pela cota** (§3).
4. **Empreendimento de terceiro** (dono externo) sem obra → a matriz.
5. **Sem empreendimento nem obra** (custo de sede, folha da administração) → a matriz.

Quem cria título em outro módulo (SCM, PDCA, carteira de vendas, importação) pode passar a entidade;
se não passar, vale a regra. O **centro de custo** é de uma entidade (pela mesma regra, a partir da
obra ou do empreendimento dele). **Rateio** para centro de custo de outra entidade é permitido e gera
intercompany. A transação herda a entidade do título; o boleto também.

**Centro de custo único.** O centro de custo é um só, o do ERP (`moduloerp.CentroCusto`), com `tipo`
(obra, empreendimento, almoxarifado, filial, administrativo, outro) e `local_estoque_ref`. O
Suprimentos aponta para ele; a rota `scm/centros-custo` serve o mesmo cadastro para quem só tem o SCM.

## 3. Intercompany

Sempre que um título de uma entidade carrega custo ou receita que é de outra, o sistema gera o par
**no mesmo gesto**, sem confirmação — *a receber* na que pagou (ou *a pagar* na que recebeu), e o
espelho na outra —, ligados ao título de origem por `ParIntercompany`. Vale para **qualquer** par de
entidades do grupo, inclusive matriz ↔ filial.

Gatilhos:

- **Rateio** de um título para centro de custo de outra entidade: a fração rateada.
- **Empreendimento do grupo sem `entidade_propria`** com mais de uma participante: o título da dona
  gera, para cada outra, a fração da cota.

O título do par **não tem cliente nem fornecedor**: a contraparte é a entidade (`contraparte`). Não
gera boleto nem nota fiscal. A `natureza` diz o que ele é na DRE:

| Natureza | Na que pagou/recebeu | Na outra |
|---|---|---|
| `repasse_despesa` | *a receber* — **reduz** a despesa dela | *a pagar* — **é** despesa dela |
| `repasse_receita` | *a pagar* — **reduz** a receita dela | *a receber* — **é** receita dela |

Assim a despesa rateada sai da DRE de quem pagou e entra na de quem consumiu, e no consolidado os dois
lados se anulam. A DRE por obra não soma o par: a obra já recebe a fração pelo rateio do título de
origem.

O par acompanha a origem: mudar o valor ou o rateio recalcula o par ainda sem baixa; cancelar a origem
cancela o par sem baixa. Par já baixado não muda — a divergência vira anotação no título.

**Acerto.** Baixa comum, par a par (transferência entre as contas das entidades). E o **encontro de
contas**: entre duas entidades, compensa o que uma deve à outra até o menor dos dois saldos e baixa os
dois lados com o meio `compensação`, numa transação. A escrita cruzada avisa quem pode
([funcoesnotificacoes.md](funcoesnotificacoes.md)).

## 4. Acesso — empreendimento fora do ERP, entidade no ERP

A permissão de **ação** continua do catálogo (`erp.*`, `obra.*`…). Por cima dela, o **escopo de
objeto** (a fatia D do AD-9):

| Concessão | Dá acesso a | Onde vale |
|---|---|---|
| usuário ↔ **entidade** | o ERP **inteiro** da entidade: sede, carteiras, títulos de todos os empreendimentos dela; com `incluir_filiais`, as filiais; e, se ela é a **administradora** de um empreendimento, a `entidade_propria` dele inteira | só o ERP |
| usuário ↔ **empreendimento** | o empreendimento, as obras dele e, no ERP, **o recorte dele** (títulos do empreendimento, de qualquer entidade) | todos os módulos |
| usuário ↔ **obra** | a obra **sem empreendimento** | todos os módulos |

- O **administrador** do tenant vê tudo, sempre.
- Fora do ERP, o usuário é cadastrado **por empreendimento**: quem trabalha no loteamento X não vê o Y,
  mesmo sendo da mesma empresa. Os outros módulos **não ganham lógica de entidade**.
- A sócia que **não** é a administradora vê a SPE pelo **resultado pela cota** (§6), não pelos títulos.
- **Modo simples:** com uma entidade do grupo só, não há recorte. Ao cadastrar a segunda, quem já
  usava o sistema recebe a concessão da primeira — ninguém perde o que via.
- Quem concede: o administrador ou quem tem `cadastro.entidade.conceder`.

## 5. Fiscal e cobrança por entidade

`IntegracaoFiscal` (NFE.io), `IntegracaoAsaas` e `ContaCobrancaBancaria` (CNAB) são **da entidade**.
A NFS-e sai pela integração da entidade dona do título (sem cadastro dela, a do ambiente); a carteira
usada na remessa tem de ser da entidade de cada título. A entidade sem `documento` não emite: a tela
pede o cadastro.

O **boleto pelo Asaas** sai na conta Asaas da entidade dona do título — é ela o beneficiário impresso.
A conta do ambiente (`ASAAS_API_KEY`) é a **da matriz**: vale para ela e para a conta de uma entidade
só. Num grupo, a outra entidade sem conta própria é recusada antes de chegar ao gateway
(`EntidadeSemContaAsaas`), com o caminho na frase: cadastrar a chave em ERP › Configurações, ou emitir
pelo CNAB dela. O boleto guarda em que conta nasceu (`Boleto.conta_asaas`), e cancelar e conferir vão
à mesma; o customer é buscado por CPF/CNPJ na conta da entidade (o `Cliente.id_cliente_gateway` é o da
conta da matriz). O webhook de cada conta usa o mesmo token de autenticação.

## 6. As visões do ERP

`Consolidado` (todas as entidades que a pessoa alcança) → `Entidade` → `Empreendimento` → `Obra`. Toda
lista e relatório do ERP aceita `?entidade=`. A DRE da entidade traz:

- **Própria:** receita e despesa dos títulos dela, com o intercompany pela natureza (§3).
- **Pelas cotas:** o resultado de cada entidade em que ela participa, multiplicado pela cota (a SPE
  60/40 aparece na sócia de 40% como 40% do resultado).

O consolidado soma as entidades alcançadas e **elimina** o intercompany entre elas.

Com **uma** entidade só, o seletor, a coluna de entidade e o intercompany **não aparecem**, e tudo vai
para ela.

## 7. Migração dos dados existentes

- Cada tenant ganha a **matriz** (`<nome do tenant>`, sem documento; a tela pede o CNPJ).
- Empreendimento com CNPJ diferente do da matriz vira **entidade externa** dona dele (o caso da
  empreitada: a construtora executa no empreendimento de outro). Quem for SPE se reclassifica na tela.
  Os próximos nascem certos: o cadastro do empreendimento pede o dono.
- Obras, títulos, transações, centros de custo, notas, boletos, carteiras e a integração fiscal recebem
  a entidade pela regra do §2.
- Os centros de custo do SCM viram centros de custo do ERP (o pedido e a demanda passam a apontar
  para eles).
- Usuários existentes recebem concessão de todas as entidades do grupo e todos os empreendimentos que
  existem. Usuário novo nasce sem concessão.
