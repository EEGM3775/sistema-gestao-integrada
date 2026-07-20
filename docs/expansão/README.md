# Expansão — estratégia de produto e ecossistema

> **Natureza deste diretório: 🧭 estratégia.** Terceira natureza da documentação (além de
> 📐 planta e 📊 status — ver [../README.md](../README.md)): descreve **o que a plataforma deve se
> tornar**, não o que ela é nem o que está pronto. Nada aqui é compromisso de implementação;
> quando uma proposta é aprovada, ela **gradua**: vira fase no [roadmap](../roadmap.md) e, se mudar
> o desenho, prancha em [arquitetura/](../arquitetura/README.md). Nenhum documento desta pasta
> contradiz as plantas — ele as **estende**.

## O mandato

O sistema não é um ERP. É a **Plataforma Operacional do Mercado Imobiliário**: o ambiente onde
todos os participantes do setor — construtoras, incorporadoras, loteadoras, imobiliárias,
corretores, arquitetos, engenheiros, empreiteiros, fornecedores, lojas, clientes finais,
investidores, bancos, cartórios, seguradoras, administradoras de condomínio e órgãos públicos —
trabalham no mesmo lugar, do terreno à operação pós-entrega.

A referência de ambição: o que o Salesforce é para CRM e o SAP é para ERP, **especializado em
imobiliário e construção civil**. Cada empresa tem seu ambiente privado (tenant); recursos
compartilhados (marketplaces, portais, centrais) criam o **efeito de rede** que torna a plataforma
mais valiosa a cada participante que entra.

**A regra comercial que organiza tudo:** o foco é **vender o sistema para o máximo de empresas
possível**. Todo participante empresarial entra como **cliente pleno da sua própria edição** — o
sistema tem que resolver o dia a dia dele, e a comunicação com os demais é o benefício
([09-verticais-por-participante.md](09-verticais-por-participante.md)). As únicas exceções: quem
não compra sistema de negócio (comprador, investidor, morador → personas gratuitas de portal) e
quem não pode comprar (cartório/órgão público, banco/seguradora → integrações e parcerias).

**O estágio final é a autossustentação:** a comunicação entre os adquirentes culmina numa **rede
social do setor** ([10-rede-social-do-setor.md](10-rede-social-do-setor.md)) — a atividade real
vira conteúdo visível (obras andando, lançamentos, rankings de corretores, preço de materiais), e
quem está fora vê o mercado acontecendo lá dentro e entra; mais gente dentro, mais atividade
visível, mais gente querendo entrar.

## As seis perguntas de plataforma

Toda análise de funcionalidade ou módulo — nesta pasta e nas conversas de planejamento — responde:

1. Como isso **fortalece o efeito de rede**?
2. Como isso **aumenta o valor do ecossistema**?
3. Como isso **gera novas fontes de receita**?
4. Como isso pode virar um **produto independente** (micro-SaaS, como o drone já é)?
5. Como isso **se conecta** aos demais módulos e participantes do mercado?
6. Como isso aproxima a plataforma de um **sistema operacional do ciclo de vida do
   empreendimento** — da prospecção do terreno à operação pós-entrega?

## Método — planejamento em cinco níveis

| Nível | O quê | Onde vive |
|---|---|---|
| 1 | **Arquitetura** — extensões estruturais que a expansão exige | [02-arquitetura-de-expansao.md](02-arquitetura-de-expansao.md) |
| 2 | **Domínio de negócio** — camadas do ciclo de vida do empreendimento | [01-visao.md](01-visao.md) · [03-mapa-de-modulos.md](03-mapa-de-modulos.md) |
| 3 | **Módulos** — catálogo-alvo, dependências e derivados | [03-mapa-de-modulos.md](03-mapa-de-modulos.md) e seguintes |
| 4 | **Funcionalidades** — detalhadas quando o módulo gradua p/ o roadmap | doc do módulo em [../modulos/](../modulos/README.md) |
| 5 | **Tarefas técnicas** — fatias de implementação | [../roadmap.md](../roadmap.md) |

Checklist sistêmico ao analisar qualquer módulo (existente ou proposto): dependências ·
integrações · dados que produz e quem os consome · dashboards que gera · automações possíveis ·
IAs treináveis · APIs abríveis · apps móveis deriváveis · funcionalidades premium ·
oportunidades de monetização.

## Fronteiras (o que a estratégia respeita)

- **As plantas mandam.** As decisões AD-1…AD-9 de [../arquitetura.md](../arquitetura.md) valem;
  extensões estruturais entram como **novas ADs propostas** (AD-10+), nunca como revogação tácita.
- **Novo módulo de negócio = Django app** (AD-8). Nunca novo microsserviço Node.
- **O tenant é soberano.** Nenhum recurso de rede lê dado privado de tenant; a rede nasce de
  **publicação opt-in** ([02](02-arquitetura-de-expansao.md) §E1).
- **Sem licença de carona.** Empresa não entra como "convidada" de outra: entra como tenant da
  sua edição — o convite gera um trial da edição dela, não um acesso pago pelo parceiro
  ([09](09-verticais-por-participante.md) §3).
- **Sequência.** As Fases 7–11 do [roadmap](../roadmap.md) + a monetização base
  ([../arquitetura/monetizacao.md](../arquitetura/monetizacao.md)) são pré-requisito de tudo aqui
  ([08-roadmap-estrategico.md](08-roadmap-estrategico.md), Gate 0).

## Índice

| Doc | Pergunta que responde |
|---|---|
| [01-visao.md](01-visao.md) | O que estamos construindo e para quem? |
| [02-arquitetura-de-expansao.md](02-arquitetura-de-expansao.md) | O que a fundação atual precisa ganhar (Nível 1)? |
| [03-mapa-de-modulos.md](03-mapa-de-modulos.md) | Quais módulos faltam, por camada de domínio (Níveis 2–3)? |
| [04-rede-e-marketplaces.md](04-rede-e-marketplaces.md) | Como nasce o efeito de rede? |
| [05-portais-e-apps.md](05-portais-e-apps.md) | Qual a interface de cada participante (portais de consumidor + apps)? |
| [06-dados-ia-automacao.md](06-dados-ia-automacao.md) | Como dados, IA e automação multiplicam o valor? |
| [07-monetizacao-da-expansao.md](07-monetizacao-da-expansao.md) | Quais novas fontes de receita a expansão cria? |
| [08-roadmap-estrategico.md](08-roadmap-estrategico.md) | Em que ordem, com quais gates e riscos (5 anos)? |
| [09-verticais-por-participante.md](09-verticais-por-participante.md) | Como cada participante vira **cliente pleno** (edições, loop de convite, exceções)? |
| [10-rede-social-do-setor.md](10-rede-social-do-setor.md) | Como a plataforma passa a **crescer sozinha** (feed de fatos, descoberta, flywheel)? |
| [guia-seguranca-infraestrutura.md](guia-seguranca-infraestrutura.md) | Cobertura do guia de segurança/infraestrutura no projeto (auditoria item a item)? |
