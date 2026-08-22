# Roadmap estratégico — horizontes, gates e riscos (5 anos)

> A ordem em que a expansão acontece — e, tão importante, **o que não fazer ainda**. Horizontes
> são sequência lógica com **gates de saída**, não datas: um horizonte só abre quando o gate do
> anterior fecha. O [roadmap tático](../roadmap.md) (fases 0–11) continua sendo o status de
> implementação; propostas daqui graduam para lá uma a uma.

## Gate 0 — terminar a fundação (em curso, prioridade absoluta)

Nada deste diretório entra em desenvolvimento antes de:

- Fases **7** (migração v01), **10** (observabilidade/operacional) e **11** (consolidação de
  stack) concluídas — ver [roadmap.md](../roadmap.md);
- **Monetização base implementada** (catálogo de planos, quotas, checkout, trial —
  [monetizacao.md §10](../arquitetura/monetizacao.md));
- go-live com **tenants pagantes reais**.

A razão é o maior risco do projeto (R1 abaixo): equipe pequena + superfície grande. A Fase 10/11
existe para *reduzir* superfície; a expansão a *aumenta* — só é sustentável sobre fundação pronta.

## H1 — Profundidade vertical (≈ ano 1 pós-go-live)

**Tese:** aumentar retenção e ARPU dos tenants que já pagam. Critério de admissão de qualquer
item: *um cliente atual pagaria mais por isso amanhã?*

| Entrega | Referência |
|---|---|
| Eventos de domínio (E3) + motor de regras v1 (E6) — o multiplicador de tudo | [02](02-arquitetura-de-expansao.md) |
| SCM (requisição→cotação→pedido) + estoque — destrava o placeholder `moduloscm` | [03](03-mapa-de-modulos.md) §3 |
| DMS — destrava `modulodms`; transversal a tudo | [03](03-mapa-de-modulos.md) §6 |
| Espelho de vendas + contratos & assinatura digital | [03](03-mapa-de-modulos.md) §4 |
| Entrega/vistorias + **assistência técnica** | [03](03-mapa-de-modulos.md) §8 |
| **Portal do cliente** (piloto do E2/ABAC por objeto) | [05](05-portais-e-apps.md) §1 |
| Dashboards nativos (F.1) + IA medida (inadimplência, EPI) | [06](06-dados-ia-automacao.md) |
| Planejamento de obra (cronograma físico) — amplia `modulopdca` | [03](03-mapa-de-modulos.md) §2 |
| **Prancheta** — visualizador de projeto em campo; destrava `moduloprancheta` | [03](03-mapa-de-modulos.md) §2 |

**Gate de saída H1:** retenção líquida > 100% · ≥ 3 módulos ativos por tenant em média · portal
do cliente usado por compradores reais (2ª via self-service medida).

## H2 — Edições verticais + abertura da rede (≈ anos 2–3)

**Tese:** vender o sistema para o máximo de empresas do setor — cada participante empresarial
assina **a própria edição** ([09-verticais-por-participante.md](09-verticais-por-participante.md));
a rede conecta as edições e derruba o CAC pelo loop de convite. Começa **intra-carteira**
(anti-cold-start, [04](04-rede-e-marketplaces.md) §3). Disciplina: **uma edição por vez**, com
gate de tração antes da próxima (ordem recomendada em [09](09-verticais-por-participante.md) §6).

| Entrega | Referência |
|---|---|
| Esfera de Rede (E1: broadcast + transacional) + verificação/reputação + vínculo de parceria | [02](02-arquitetura-de-expansao.md) §E1 |
| Módulos que dão o lado A dos espelhos: medições de empreiteiros, orçamento de obra, qualidade (`modulopdca`), SST | [03](03-mapa-de-modulos.md) §2 |
| **Edição Empreiteiro** (1ª — menor delta; boletim espelhado) | [09](09-verticais-por-participante.md) §2 |
| **Edição Loja** + marketplace de cotações (caso conector nº 1) | [09](09-verticais-por-participante.md) · [04](04-rede-e-marketplaces.md) §2.1 |
| **Edição Imobiliária** + distribuição do espelho de vendas (caso conector nº 2) | [09](09-verticais-por-participante.md) · [04](04-rede-e-marketplaces.md) §2.2 |
| Perfil público verificado + página pública da obra (fundação da rede social; mesmas peças de verificação/curadoria dos marketplaces) | [10](10-rede-social-do-setor.md) §6 |
| API pública + webhooks + SDK (E5) | [02](02-arquitetura-de-expansao.md) §E5 |
| Warehouse + BI premium (E4 estágio 2); workflow/BPM v2 | [06](06-dados-ia-automacao.md) |
| Micro-SaaS piloto (diário standalone ou assistência técnica) | [07](07-monetizacao-da-expansao.md) §4 |

**Gate de saída H2:** ≥ 2 edições com tração própria (empresas ativas pagantes crescendo e churn
saudável **sem depender do convite**) · % de contrapartes convidadas → tenant acima da meta ·
transações cross-tenant recorrentes (cotações respondidas/mês crescendo 3 meses seguidos) ·
primeiras receitas de rede (fontes #4–#6 de [07](07-monetizacao-da-expansao.md)).

## H3 — Dominância de ecossistema (≈ anos 3–5)

**Tese:** cobrir as pontas do ciclo de vida, monetizar o grafo — e ligar o **flywheel de
autossustentação**: a rede social do setor torna a atividade visível para quem está fora, e a
plataforma passa a crescer por atração, não só por venda ([10-rede-social-do-setor.md](10-rede-social-do-setor.md) §4).

| Entrega | Referência |
|---|---|
| Terrenos & incorporação (banco de terrenos, viabilidade, GIS/`modulomaps`) + marketplace de terrenos | [03](03-mapa-de-modulos.md) §7 |
| **Edições Escritório de projeto e Administradora de condomínio** (+ facility, portais síndico/morador) | [09](09-verticais-por-participante.md) · [03](03-mapa-de-modulos.md) §8 |
| BIM (4D/5D) · IoT/telemetria · equipamentos + marketplace de locação | [03](03-mapa-de-modulos.md) §2 · [06](06-dados-ia-automacao.md) §4 |
| Benchmarks/data products (E4 estágio 3) | [06](06-dados-ia-automacao.md) §2 |
| Fintech embutida (antecipação, escrow, seguros — com parceiros licenciados) | [07](07-monetizacao-da-expansao.md) §5 |
| Portal do investidor · white-label/Enterprise · marketplace de integrações | [05](05-portais-e-apps.md) · [07](07-monetizacao-da-expansao.md) |
| **Rede social do setor** (feed de fatos, busca/descoberta, rankings transacionais, índice de preços, growth loops públicos: SEO/widget/selo/contadores) — o capstone | [10](10-rede-social-do-setor.md) |

**Gate de saída H3 (= visão cumprida):** 25–40% da receita não-assinatura · a plataforma presente
em ≥ 3 elos do ciclo de vida de um mesmo empreendimento (ex.: terreno→obra→venda→pós-obra) para
uma fração relevante da base · **flywheel girando**: fração crescente de tenants novos chegando
sem venda ativa (feed, SEO, convite, widget — [10](10-rede-social-do-setor.md) §6).

## Riscos e mitigação

| # | Risco | Impacto | Mitigação |
|---|---|---|---|
| R1 | **Dispersão** — construir rede/módulos/edições antes da fundação e do produto pagante (equipe pequena, superfície já grande) | Fatal | Gate 0 duro; um horizonte por vez; **uma edição por vez** com gate de tração; AD-8 (nada de stack nova); todo item de H1 precisa pagar-se em ARPU/retenção |
| R2 | Cold start dos marketplaces | Rede natimorta | **Cada edição vale sozinha** (valor standalone antes da rede) + loop de convite ([09](09-verticais-por-participante.md) §3); sequência intra-carteira ([04](04-rede-e-marketplaces.md) §3); medir transação e conversão de contraparte, não cadastro |
| R2b | Edição vertical rasa — vender p/ loja/imobiliária um produto que não resolve o dia a dia deles (viraria o "convite pago" que decidimos não fazer) | Churn da vertical | Gate de admissão da edição: resolver as 5 tarefas diárias do segmento antes de lançar ([09](09-verticais-por-participante.md) §2); design partner de cada vertical |
| R3 | COGS de IA/drone corroendo margem | Margem | Regra de ouro: COGS = medido+excedente ([monetizacao.md §4.2](../arquitetura/monetizacao.md)); LLM local (11.3) |
| R4 | LGPD/segurança na esfera pública e personas externas | Legal/reputação | E1 por cópia opt-in (nunca FK); E2 com escopo por objeto; auditoria ✅ (9.E); benchmark só agregado/anonimizado |
| R5 | Concorrentes estabelecidos (ERPs de construção consolidados, CRMs verticais, portais de imóveis) | Mercado | Não competir feature a feature: a combinação diário+IA+drone+financeiro **e a rede** é o diferencial; micro-SaaS como cunha de entrada |
| R6 | Regulatório (CRECI/CVM/BACEN) nos marketplaces de imóveis/investimento e fintech | Legal | Conectar sem intermediar até parecer jurídico; fintech só via parceiro licenciado |
| R7 | Portais/apps multiplicando superfície de suporte | Operacional | PWA sobre o mesmo shell React; serializers allowlist; nada de backend por portal |
| R8 | Módulo novo divergindo do contrato (tenancy/entitlement/permissão) | Segurança | Contrato de módulo obrigatório ([acesso-e-permissoes.md §7](../acesso-e-permissoes.md)); checklist de revisão já praticado nas fases 8–9 |
| R9 | Rede social virando distração (engajamento sem negócio) ou custo de moderação de rede aberta | Foco/operacional | Toda feature social termina em ação de negócio; medir transações originadas no feed, não engajamento; conteúdo gerado de fatos (E3), comentários fechados por padrão ([10](10-rede-social-do-setor.md) §5) |

## Cadência de revisão deste plano

- **Trimestral:** revisitar prioridades do horizonte corrente contra as métricas-norte
  ([01-visao.md](01-visao.md) §5); mover itens entre horizontes é esperado.
- **Ao graduar um item:** criar/atualizar o doc do módulo em [../modulos/](../modulos/README.md),
  registrar fase no [roadmap.md](../roadmap.md) e, se houver mudança estrutural, a AD
  correspondente em [../arquitetura.md](../arquitetura.md).
- **Anual:** reavaliar a tese inteira (participantes, concorrência, regulatório) e atualizar
  esta pasta.
