# Edições verticais — cada participante é cliente pleno

> **O princípio comercial da plataforma:** participante empresarial não entra "de carona" por
> convite da construtora — ele **assina a sua própria edição** do sistema, que resolve a operação
> diária **dele**; a comunicação com os demais participantes é o benefício que nenhum concorrente
> isolado oferece. O foco é **vender o sistema para o máximo de empresas possível** — cada
> vertical multiplica o mercado endereçável. Exceções (quem não vira tenant): §4.

## 1. O modelo: uma plataforma, N edições

**Edição = bundle de módulos + onboarding + linguagem do segmento + tabela de planos própria.**
Não é fork nem produto paralelo: são os **mesmos módulos Django** (AD-8) vendidos em combinações
diferentes — o mecanismo de entitlement por módulo (AD-4) e o catálogo de planos em código
([monetizacao.md §9](../arquitetura/monetizacao.md)) já suportam isso sem mudança estrutural.
O que muda por edição é o empacotamento: hub, terminologia, exemplos do seed, trilha de onboarding.

A consequência arquitetural importante: quando dois tenants negociam (construtora contrata
empreiteiro; loja responde cotação), o documento da transação existe **nos dois tenants,
espelhado e sincronizado** — o modo transacional da Esfera de Rede
([02-arquitetura-de-expansao.md](02-arquitetura-de-expansao.md) §E1). Cada lado trabalha no seu
ambiente privado; a plataforma é o EDI do setor.

## 2. As edições (o dia a dia de cada uma, com o que já existe)

### Edição Construtora / Incorporadora / Loteadora — ✅ o produto atual

O cliente-âncora. Tudo de [03-mapa-de-modulos.md](03-mapa-de-modulos.md) é a profundidade dele.

### Edição Empreiteiro / Prestador de serviços

| Dia a dia dele | Módulo que atende |
|---|---|
| Propostas e contratos de serviço | proposta de serviço 🧭 + contratos & assinatura |
| Diário da frente de obra, fotos, equipe | `modulodiario` ✅ + `rh` ✅ (apontamento) |
| Medições a faturar, retenções | medições & empreiteiros ([03](03-mapa-de-modulos.md) §2) — **o mesmo boletim, visto do outro lado** |
| Receber, emitir NFS-e, boletos | `moduloerp` ✅ + NFE.io ✅ + Asaas ✅ |
| Compras básicas de material | SCM básico + marketplace de cotações |

**Rede:** contratos e boletins de medição espelhados com a construtora-tenant; reputação portátil
([04](04-rede-e-marketplaces.md) §2.3). Menor delta de produto — quase tudo é reuso.

### Edição Loja de materiais / Distribuidor

| Dia a dia dele | Módulo que atende |
|---|---|
| Orçamentos para qualquer cliente (balcão, telefone, WhatsApp ✅) | orçamento de venda 🧭 |
| Catálogo e tabelas de preço | `fornecedores` ✅ (catálogo, invertido p/ visão do dono) |
| Pedidos, entregas | pedido de venda 🧭 + logística simples 🧭 |
| Estoque | estoque/almoxarifado ([03](03-mapa-de-modulos.md) §3) |
| Receber, NF-e, boletos, PIX | `moduloerp` ✅ + NFE.io ✅ + Asaas ✅ |
| Compras dos distribuidores dele | SCM ✅ (o mesmo módulo, agora como comprador) |

**Rede:** as RFQs das construtoras caem **direto na fila de orçamentos** que ele já usa no dia a
dia — responder cotação não é tarefa extra, é o trabalho normal dele.

### Edição Imobiliária (e Corretor autônomo como plano individual)

| Dia a dia dele | Módulo que atende |
|---|---|
| Funil de leads e atendimento | `modulocrm` ✅ + WhatsApp ✅ |
| Carteira de imóveis (próprios + de parceiros) | carteira de imóveis 🧭 (+ espelhos de venda das construtoras via rede) |
| Agenda de visitas | `modulocalendar` ✅ |
| Propostas, contratos, assinatura | contratos & assinatura ([03](03-mapa-de-modulos.md) §4) |
| Comissões (casa e corretores) | gestão de corretores & comissões + `moduloerp` ✅ |
| (opcional) Administração de locação | locação 🧭: contrato de aluguel, repasse ao proprietário — **reusa cobranças Asaas ✅** |

**Rede:** unidades das construtoras parceiras em tempo real, com status real de obra
([04](04-rede-e-marketplaces.md) §2.2); reserva sincronizada mata o overselling.

### Edição Escritório de projeto (Arquiteto / Engenheiro)

| Dia a dia dele | Módulo que atende |
|---|---|
| Propostas e projetos com etapas | projetos & propostas 🧭 |
| Documentos, versões, aprovações do cliente | `modulodms` 📦 |
| Horas trabalhadas / timesheet | timesheet 🧭 + `modulocalendar` ✅ |
| ART/RRT e responsabilidade técnica | registro de RT 🧭 (casa com SST/licenciamento) |
| Faturar, receber | `moduloerp` ✅ + NFS-e ✅ |

**Rede:** entrega projetos para construtoras-tenant via DMS espelhado; como RT de obra de
terceiro, acessa o diário da obra do contratante por **vínculo entre tenants** (não por persona).

### Edição Administradora de condomínio (H3)

O módulo condomínio ([03](03-mapa-de-modulos.md) §8) como produto próprio: taxas (Asaas ✅),
reservas, assembleias, chamados, facility. Síndico e morador são **personas dela** (§4). É a
edição que recebe o comprador→morador na pós-entrega — o ciclo de vida fechando.

## 3. O loop viral de aquisição (convite = lead, não carona)

Cada transação da rede com uma empresa de fora é um **funil de venda da edição dela**:

```
construtora envia RFQ à sua loja habitual (ainda não-cliente)
  → loja recebe por e-mail/WhatsApp com a página da cotação
  → para responder, cria conta TRIAL da Edição Loja (28 dias, padrão do estudo base)
  → responde a cotação (nunca bloquear a resposta — senão a rede morre)
  → o sistema mostra o resto do dia a dia dela já resolvido (orçamentos, estoque, NF, boletos)
  → converte em assinatura própria
```

O mesmo vale para empreiteiro (recebe o contrato/medição), imobiliária (recebe o espelho de
vendas) e escritório de projeto (recebe a solicitação de projeto). **O cliente-âncora traz as
contrapartes; o CAC da vertical despenca.** Regras do loop:

1. **Responder é grátis; operar é pago.** A contraparte nunca paga para atender o parceiro — paga
   quando a edição vira a ferramenta do negócio dela.
2. O trial da contraparte já nasce com o vínculo de parceria ativo (o benefício de rede é visível
   no primeiro login).
3. Métricas do loop: % de contrapartes convidadas que ativam trial · % trial→assinatura ·
   transações espelhadas/mês por parceria.

## 4. Quem NÃO vira tenant (e como participa)

| Participante | Por que não é cliente do sistema | Como participa |
|---|---|---|
| **Cliente final (comprador)** | Não compra sistema de negócio | **Portal do cliente** gratuito ([05](05-portais-e-apps.md)); quem paga é o tenant (valor — menos suporte, mais venda — é dele) |
| **Investidor** | Idem — consome informação, não opera | Portal do investidor (H3), pago pelo tenant que capta |
| **Morador / síndico** | Consumidor | Portais da Edição Administradora |
| **Cartório / órgão público** | Legislação e burocracia inviabilizam a relação comercial | Central de documentos/protocolos do lado do tenant; integração somente quando houver API pública (ONR/e-notariado, prefeituras) — **integração, não licença** |
| **Banco / seguradora** | Restrições institucionais (compliance, homologação, ciclo de venda de anos) | Consomem **dados/APIs** (relatório de medição padronizado, andamento de obra) e entram como **parceiros** da fintech no H3 ([07](07-monetizacao-da-expansao.md) §5) — receita de parceria, não de assinatura |

## 5. Objetos espelhados entre tenants (o vocabulário do EDI)

| Objeto | Lado A (emite) | Lado B (recebe/responde) |
|---|---|---|
| RFQ ↔ Proposta | Construtora (SCM) | Loja (fila de orçamentos) |
| Pedido de compra ↔ Pedido de venda | Construtora | Loja |
| Contrato de empreitada ↔ Contrato de serviço | Construtora | Empreiteiro |
| Boletim de medição ↔ Medição a faturar | Construtora (aprova) | Empreiteiro (fatura) |
| Espelho de vendas ↔ Carteira de parceiro | Construtora | Imobiliária/corretor |
| Reserva de unidade | Imobiliária (pede) | Construtora (confirma) |
| Solicitação de projeto ↔ Projeto entregue | Construtora | Escritório de projeto |

Cada linha é um par de registros privados sincronizados por eventos (E3) através da Esfera de
Rede (E1 transacional) — nunca FK cruzada, sempre cópia com estado.

## 6. Ordem de lançamento recomendada (calibrar com mercado)

| # | Edição | Por quê nessa ordem |
|---|---|---|
| 1 | **Empreiteiro/prestador** | Menor delta (diário+RH+ERP prontos); toda construtora-cliente tem 5–30 deles; o boletim de medição é dor aguda dos dois lados |
| 2 | **Loja/distribuidor** | Destravada pelo SCM (H1); o loop RFQ→orçamento é o caso conector nº 1; NF-e/boletos já prontos |
| 3 | **Imobiliária/corretor** | Destravada pelo espelho de vendas (H1); mercado enorme, mas exige carteira/locação p/ valor standalone |
| 4 | **Escritório de projeto** | Depende do DMS maduro; mercado grande porém ticket menor |
| 5 | **Administradora de condomínio** | Módulo novo inteiro (H3); herda a base de compradores→moradores |

Uma edição por vez, com gate de tração antes da próxima ([08-roadmap-estrategico.md](08-roadmap-estrategico.md)).
