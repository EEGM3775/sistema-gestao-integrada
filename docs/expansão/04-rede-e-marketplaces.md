# Rede e marketplaces — como nasce o efeito de rede

> A camada que transforma um SaaS em plataforma. Base técnica: **Esfera de Rede** (E1, modos
> broadcast, transacional e vitrine/feed) + **eventos** (E3) de
> [02-arquitetura-de-expansao.md](02-arquitetura-de-expansao.md). Dois princípios inegociáveis:
> a rede nasce de **publicação opt-in** de dados que os tenants já produzem — nunca de leitura
> cruzada; e **os dois lados de cada transação são tenants** — cada participante empresarial usa a
> sua própria edição ([09-verticais-por-participante.md](09-verticais-por-participante.md)), e a
> rede é o benefício que conecta as edições, não um clube de convidados.

## 1. O catálogo de marketplaces

| Marketplace | Lado da oferta | Lado da demanda | Dado semente (já existe/planejado) | Monetização ([07](07-monetizacao-da-expansao.md)) |
|---|---|---|---|---|
| **Cotações de materiais** | Lojas/fornecedores respondem RFQ | Construtoras publicam requisições do SCM | `moduloscm` (requisição de compra) | Assinatura da loja + take rate opcional no pedido |
| **Fornecedores & serviços** | Perfil público do fornecedor (catálogo, área, reputação) | Busca por especialidade/região | `fornecedores` (catálogo já existe) | Perfil premium/destaque; lead fee |
| **Profissionais** | Engenheiros, arquitetos, mestres, empreiteiros | Obras precisando de gente/RT | `rh` + medições de empreiteiros | Assinatura do profissional; comissão de contratação |
| **Imóveis (unidades)** | Construtoras publicam espelho de vendas | Imobiliárias/corretores distribuem | espelho de vendas ([03](03-mapa-de-modulos.md) §4) | Comissão de distribuição / assinatura da imobiliária |
| **Terrenos** | Proprietários/loteadoras/corretores | Incorporadoras (banco de terrenos) | banco de terrenos ([03](03-mapa-de-modulos.md) §7) | Success fee / assinatura premium |
| **Empreendimentos (investimento)** | Incorporadoras captando | Investidores qualificados | empreendimentos + viabilidade | Acesso premium do investidor (H3; atenção regulatória CVM) |
| **Equipamentos** | Frota ociosa de um tenant | Obras vizinhas alugando | equipamentos & frota | Take rate da locação |

## 2. Os três casos conectores (detalhe do fluxo)

### 2.1 Falta de material → loja envia orçamento

O caso que inaugura a rede, porque resolve dor diária dos **dois** lados:

```
estoque atinge mínimo (evento E3: scm.estoque_minimo_atingido)
  → automação (E6) cria RequisicaoCompra no tenant
  → comprador publica como RFQ na Esfera de Rede (escopo: lojas da região / parceiras)
  → lojas (tenants da Edição Loja; não-clientes recebem convite → trial) veem a RFQ
    na MESMA fila de orçamentos que já usam no dia a dia → respondem proposta
  → mapa comparativo automático no SCM do construtor → pedido → recebimento com XML NF-e (já lido)
  → preço praticado alimenta o histórico e o benchmark (E4)
```

Sem marketplace, esse fluxo hoje é telefone + WhatsApp + planilha. A plataforma o captura inteiro —
e cada loja não-cliente que responde é um lead da Edição Loja
([09](09-verticais-por-participante.md) §3).

### 2.2 Construtora ↔ imobiliária: vender com status real da obra

O diferencial que nenhum portal de imóveis tem — **a obra é gerida aqui dentro**:

```
construtora publica empreendimento + espelho de vendas (unidades, tabela, comissão)
  → imobiliárias/corretores parceiros veem: unidades disponíveis EM TEMPO REAL
    + evolução física curada (fotos do diário aprovadas p/ marketing, ortofoto do drone, % etapas)
  → corretor reserva unidade com prazo → proposta → contrato entra no CRM/jurídico do construtor
  → comissão calculada e rastreada até o pagamento (moduloerp)
```

Reserva sincronizada mata o overselling entre canais; status real de obra mata o "liga lá e
pergunta como anda". Curadoria é essencial: a construtora escolhe **o que** publicar.

### 2.3 Rede de profissionais e empreiteiros

Empreiteiro bem avaliado em uma obra fica visível (com consentimento) para outros tenants;
histórico de medições vira **reputação portátil** — o profissional tem incentivo a trabalhar via
plataforma, o contratante tem risco menor. A reputação só se constrói com dados transacionais
reais, o que nenhum concorrente-diretório tem.

## 3. O problema do cold start (e a sequência anti-cold-start)

Marketplace vazio afasta os dois lados. Duas defesas estruturais + uma sequência:

**Defesa 1 — a edição vale sozinha.** Cada lado assina a plataforma pelo próprio dia a dia
([01-visao.md](01-visao.md) §3.1): a Edição Loja se paga com orçamentos/estoque/NF-e mesmo sem
nenhuma RFQ da rede. O marketplace não precisa "segurar" ninguém — ele é upside, não a razão da
assinatura. **Defesa 2 — o loop de convite.** Toda transação com uma empresa de fora é um funil de
trial da edição dela ([09](09-verticais-por-participante.md) §3): responder é grátis, operar é
pago; o cliente-âncora traz as contrapartes.

A sequência:

1. **Fase intra-carteira (H2 início):** rede fechada entre os tenants existentes e as
   contrapartes **que eles já têm** — o construtor convida a loja habitual ("responda minha
   cotação aqui"), o empreiteiro recebe o boletim, a imobiliária recebe o espelho. Cada convite
   aceito = trial de edição. Densidade local antes de escala.
2. **Fase regional:** ao ter N construtoras numa cidade, a loja recebe cotações de *várias* — a
   assinatura da edição se paga várias vezes. Idem imobiliárias e empreiteiros.
3. **Fase aberta (H3):** cadastro espontâneo de ofertantes, SEO dos perfis públicos — o
   marketplace vira o canal de aquisição mais barato de todas as edições.

Métricas honestas da fase: **transações cross-tenant/mês** (cotações respondidas, medições
espelhadas, reservas) e **% de contrapartes convertidas em tenant** — não cadastros.

## 4. Confiança, segurança e compliance da esfera pública

| Tema | Regra |
|---|---|
| Verificação | CNPJ (Receita), CREA/CAU p/ profissionais, CRECI p/ corretores/imobiliárias — selo verificado |
| Reputação | Só de transação real concluída na plataforma (não review livre); janela de contestação |
| Moderação | Publicação de empreendimento/imóvel passa por validação do próprio tenant admin; denúncia + takedown na esfera |
| LGPD | Esfera pública não recebe PII de terceiros; dados de contato empresariais somente; benchmark só agregado/anonimizado (E4) |
| Isolamento | Nada na esfera referencia (FK) tabela privada; despublicar = remover a cópia ([02](02-arquitetura-de-expansao.md) §E1) |
| Regulatório | Intermediação de imóveis/investimento tem fronteiras legais (CRECI/CVM) — a plataforma **conecta e informa**, não intermedeia, até parecer jurídico dizer o contrário |

## 5. O que cada marketplace exige antes de existir

| Marketplace | Módulo privado pré-requisito | Quem está do outro lado |
|---|---|---|
| Cotações de materiais | `moduloscm` funcionando + E6 (RFQ automática) | **Edição Loja** ([09](09-verticais-por-participante.md)) |
| Fornecedores/profissionais | `fornecedores` ✅ / medições | Edições Loja / Empreiteiro / Escritório de projeto |
| Imóveis | espelho de vendas + curadoria de mídia do diário/drone | **Edição Imobiliária** |
| Terrenos | banco de terrenos + GIS (`modulomaps`) | Incorporadoras (edição atual) entre si |
| Equipamentos | equipamentos & frota | Construtoras entre si |
| Investimento | viabilidade + prestação de contas + parecer regulatório | Investidor = persona (E2), não tenant |

## 6. A camada de descoberta: a rede social do setor

Marketplace responde "**onde eu transaciono**"; falta o "**quem eu deveria conhecer**". Essa é a
**rede social do setor** ([10-rede-social-do-setor.md](10-rede-social-do-setor.md)): perfis
públicos verificados, páginas de obra, feed de marcos reais, rankings transacionais e o índice de
preços — a vitrine que faz o lojista ver quem está construindo, o cliente ver as novas obras e a
construtora achar os melhores corretores. É o motor de demanda dos marketplaces (toda descoberta
termina numa ação de negócio daqui) e o motor de crescimento da plataforma (o flywheel de
autossustentação, [10](10-rede-social-do-setor.md) §4). A verificação e a reputação deste doc
(§4) são as mesmas peças — construídas uma vez, servem aos dois.
