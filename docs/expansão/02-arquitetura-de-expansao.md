# Arquitetura de expansão — extensões estruturais (Nível 1)

> O que a fundação atual ([../arquitetura.md](../arquitetura.md)) precisa ganhar para sustentar
> ecossistema, rede e portais — **sem revogar nenhuma AD existente**. Cada extensão é uma
> **proposta de nova AD** (AD-10+); ao ser aprovada, gradua para a planta com prancha própria em
> [../arquitetura/](../arquitetura/README.md).

## O que a fundação atual já dá de graça

A arquitetura foi desenhada para um SaaS multi-tenant — e, por sorte de desenho, várias decisões
já são de **plataforma**:

- **IAM separada (AD-5)** → adicionar novas personas/audiences não mexe em nenhum produto.
- **Entitlement por módulo (AD-4)** → todo módulo novo já nasce vendável à la carte — e uma
  **edição vertical** ([09-verticais-por-participante.md](09-verticais-por-participante.md)) é só
  um bundle de módulos no catálogo de planos: zero mudança estrutural para vender a outra
  participante do mercado.
- **Catálogo de permissões em código (AD-9)** → papéis para personas externas são só novas
  permissões no catálogo.
- **Produto destacável com banco próprio (AD-1/AD-7)** → o modelo para micro-SaaS e para a
  esfera de rede já existe (o drone é a prova).
- **Celery + Redis + eventos internos** → base do backbone de automação.
- **Quotas em `AssinaturaTenant.limites`** → medição de consumo pronta para novos recursos.

## E1 — Esfera de Rede (dados cross-tenant por publicação) · *proposta AD-10*

**O problema:** todo o domínio privado é `TenantScopedModel` + RLS **fail-closed** (Fase 8) — e
deve continuar assim. Marketplace, transações entre tenants e benchmark exigem dados que **mais de
um tenant enxerga**. Ler cruzado é proibido; então a rede precisa de outro lugar para viver.

**O desenho:** uma **esfera de rede separada do domínio privado**, com **três modos**:

**Modo broadcast (publicação opt-in)** — para marketplace e descoberta:

```
 tenant A (privado, RLS)          ESFERA DE REDE (pública)          tenant B (privado, RLS)
 ┌────────────────────┐   publica   ┌──────────────────────┐   vê/responde   ┌──────────────┐
 │ RequisicaoCompra   │ ──────────► │ CotacaoPublicada     │ ◄────────────── │ PropostaLoja │
 │ Unidade à venda    │ ──────────► │ OfertaImovel         │                 │ (fornecedor) │
 │ Terreno            │ ──────────► │ OfertaTerreno        │                 └──────────────┘
 └────────────────────┘   (cópia    └──────────────────────┘   resposta volta como registro
                          curada,        sem FK p/ dados         privado no tenant de origem
                          nunca FK)      privados
```

**Modo transacional (par-a-par, o EDI do setor)** — para dois tenants que negociam. Como cada
participante empresarial é **tenant pleno da sua edição**
([09-verticais-por-participante.md](09-verticais-por-participante.md)), o documento da transação
existe **espelhado nos dois tenants** e a esfera sincroniza o estado:

```
 construtora (tenant A)             ESFERA (canal da parceria)        empreiteiro (tenant B)
 BoletimMedicao [aprovado] ──evento──► espelho com estado ──evento──► MedicaoAFaturar [liberada]
        ▲                                                                     │
        └───────────────── aceite/contestação volta pelo mesmo canal ◄───────┘
```

**Modo vitrine/feed (social)** — projeções públicas para a **rede social do setor**
([10-rede-social-do-setor.md](10-rede-social-do-setor.md)): perfil verificado da empresa, página
pública da obra/empreendimento e publicações de marco geradas dos eventos (E3) mediante curadoria.
Mesmo padrão dos outros modos (cópia curada, nunca FK), com uma diferença: a audiência é aberta
(inclusive não-tenants, via SEO) — por isso a curadoria é obrigatória e o conteúdo nunca contém PII.

Regras do padrão (valem para os três modos):

1. **Nunca FK cruzada, sempre cópia com estado.** Publicar/transacionar = projetar um snapshot
   curado; a sincronização é por eventos (E3). Despublicar/encerrar remove a projeção; o dado
   privado nunca esteve exposto.
2. Modelos da esfera **não herdam** `TenantScopedModel`; carregam `tenant_origem` (e, no modo
   transacional, o **vínculo de parceria** entre os dois tenants — criado por convite aceito).
3. **Onde vive:** novo Django app `rede` no backend (mesmo processo, models não-escopados e
   permissões próprias) na fase interna; **serviço próprio com banco próprio** (coerente com AD-7)
   quando a escala/risco justificar. A decisão de quando separar é de escala, não de estética.
4. Moderação, verificação (CNPJ/CREA/CRECI) e reputação são parte do domínio da esfera, não
   acessório ([04-rede-e-marketplaces.md](04-rede-e-marketplaces.md) §4).
5. O catálogo de **objetos espelhados** (RFQ↔proposta, medição, reserva…) está em
   [09-verticais-por-participante.md](09-verticais-por-participante.md) §5.

## E2 — Identidade externa: personas de consumidor · *proposta AD-11*

**Escopo estreito de propósito:** persona externa é **só para quem não compra sistema de negócio**
— comprador, investidor, morador/síndico ([09-verticais-por-participante.md](09-verticais-por-participante.md)
§4). Empresa (loja, empreiteiro, imobiliária, escritório) **não é persona**: é tenant pleno da sua
edição, com identidade normal de tenant. Isso mantém o realm externo pequeno e simples.

**O desenho:** a IAM (única autoridade, AD-5) ganha um **realm de personas de consumidor**:

- `Usuario` externo sem vínculo empregatício, criado por **convite** de um tenant (a construtora
  convida o comprador da unidade 302).
- O JWT de persona carrega `audience`/escopo **restrito ao portal** e um **vínculo por objeto**
  (ex.: `cliente_id` da aquisição), nunca `modules` do tenant — o portal do cliente enxerga *a sua
  unidade*, não o módulo `clientes`.
- Não consome **seat** do plano (seat = funcionário, [monetizacao.md
  §1.1](../arquitetura/monetizacao.md)); é gratuita para a pessoa — quem paga é o tenant
  ([07-monetizacao-da-expansao.md](07-monetizacao-da-expansao.md) §3).
- ABAC por objeto (fatia D do [rbac-abac.md](../arquitetura/rbac-abac.md)) é o mecanismo natural
  de autorização desses vínculos — mais um motivo para essa fatia existir.
- **Vínculo entre tenants** (RT de um escritório acessando o diário da obra do contratante) não é
  persona: é relação de parceria tratada na esfera de rede (E1 transacional), com o usuário
  autenticado no **seu próprio tenant**.

## E3 — Backbone de eventos de domínio · *proposta AD-12*

**O problema:** automação, webhooks de saída, workflow, notificações e integrações precisam todos
da mesma coisa: saber que **algo aconteceu**, com nome e payload estáveis. Hoje isso está implícito
em signals + Celery tasks pontuais (`post_delete` → drone, lembretes, webhook Asaas).

**O desenho:** formalizar **eventos de domínio nomeados** (`obra.etapa_concluida`,
`erp.conta_vencida`, `scm.estoque_minimo_atingido`, `crm.lead_criado`…) publicados via padrão
**outbox** (linha na transação do Postgres → relay Celery), consumidos por: motor de automação
(E6), webhooks de saída da API pública (E5), notificações in-app (já existem, Fatia C do
calendário) e projeções para a esfera de rede (E1) e o warehouse (E4). Sem novo broker: Redis +
Celery que já existem (AD-8); Kafka só se a escala provar necessidade.

**Este é o multiplicador silencioso:** cada módulo novo que emite eventos torna todos os outros
mais valiosos — a materialização técnica do efeito de rede interno.

## E4 — Plataforma de dados (BI → warehouse → benchmarks) · *proposta AD-13*

Três estágios, cada um com produto próprio ([06-dados-ia-automacao.md](06-dados-ia-automacao.md)):

1. **BI embarcado** — dashboards nativos sobre o Postgres transacional (réplica de leitura quando
   doer). Já iniciado (KPIs do hub ERP; dashboard F.1 pendente na Fase 7).
2. **Warehouse** — projeções dos eventos (E3) em esquema analítico por tenant; histórico, séries,
   Power-BI-like interno como funcionalidade premium.
3. **Benchmarks de mercado** — agregados **anonimizados e com k-anonimato** entre tenants que
   **optarem por contribuir** (custo/m² por região, prazo por tipologia, inadimplência média).
   Produto de dados vendável; a LGPD é requisito de projeto, não ajuste posterior.

## E5 — API pública, webhooks e SDK · *proposta AD-14*

- **API keys por tenant** (emitidas pela IAM, escopo = subconjunto das permissões do catálogo)
  com rate limit no gateway Nginx; versionamento `/api/v1/` público e estável.
- **Webhooks de saída** por assinatura de eventos (E3) — o espelho do que já consumimos do Asaas.
- **SDK** (Python/TS) e, por fim, **marketplace de integrações** (contabilidade, bancos, cartórios
  quando houver API, Google/Outlook/Teams) — cada integração é Celery task (AD-8).
- Monetização: chamadas de API são recurso medido no modelo de quotas existente.

## E6 — Motor de automação e workflow · *proposta AD-15*

Sobre os eventos (E3), um motor **declarativo por tenant**, em dois degraus:

1. **Regras** (H1): `quando <evento> e <condição> então <ação>` — ações do catálogo (notificar,
   criar tarefa no calendário, e-mail/WhatsApp, publicar cotação na rede, bloquear etapa).
   Exemplos-alvo: *estoque abaixo do mínimo → RFQ para lojas parceiras*; *parcela vencida há 5
   dias → régua de cobrança*; *etapa concluída → notificar imobiliárias parceiras*.
2. **Workflow/BPM leve** (H2+): processos com estados e aprovações (aprovação de compra em 2
   níveis, liberação de medição de empreiteiro, vistoria de entrega). Motor próprio simples em
   Django — **não** adotar BPMN engine externa antes de 10 casos reais o exigirem.

## Resumo: extensão × pré-requisito × quando

| Ext. | Proposta | Pré-requisito duro | Horizonte ([08](08-roadmap-estrategico.md)) |
|---|---|---|---|
| E1 | Esfera de Rede (broadcast + transacional + vitrine/feed) | Fases 8–9 ✅ · edições verticais ([09](09-verticais-por-participante.md)) p/ o modo transacional | H2 (vitrine) · H3 (feed pleno — [10](10-rede-social-do-setor.md)) |
| E2 | Personas de consumidor | IAM estável ✅ · ABAC por objeto (fatia D do AD-9) | H1 (portal do cliente) |
| E3 | Eventos de domínio | Celery/worker ✅ (10.9) | H1 — **primeira extensão a construir** |
| E4 | Plataforma de dados | E3 · observabilidade (10.1) | BI: H1 · warehouse: H2 · benchmark: H3 |
| E5 | API pública + SDK | E3 · monetização base (quotas) | H2 |
| E6 | Automação/workflow | E3 | regras: H1 · BPM: H2 |
