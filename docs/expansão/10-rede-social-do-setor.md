# Rede social do setor — a camada que faz a plataforma se autossustentar

> O **último estágio da expansão**: sobre as edições verticais
> ([09-verticais-por-participante.md](09-verticais-por-participante.md)) e os marketplaces
> ([04-rede-e-marketplaces.md](04-rede-e-marketplaces.md)), uma camada de **descoberta social** —
> um feed do mercado imobiliário onde a atividade real das empresas vira conteúdo visível.
> Objetivo declarado: **autossustentação** — empresa de fora vê gente entrando e atividade
> acontecendo, entra; com ela dentro, mais atividade fica visível, e mais gente quer entrar.
> Base técnica: modo vitrine/feed da Esfera de Rede
> ([02-arquitetura-de-expansao.md](02-arquitetura-de-expansao.md) §E1).

## 1. O que a torna diferente de uma rede social genérica

**O conteúdo nasce dos dados operacionais, não de posts.** LinkedIn e Instagram mostram o que a
empresa *diz* que faz; aqui o feed mostra o que ela *comprovadamente* faz, porque a operação roda
dentro da plataforma:

| Post típico | De onde nasce (automático, mediante publicação opt-in) |
|---|---|
| "Obra X atingiu 60% — estrutura concluída" | diário de obra ✅ + etapas + ortofoto do drone ✅ |
| "Lançamento: Residencial Y, 48 unidades" | empreendimento + espelho de vendas |
| "Corretor Z: 5 vendas neste trimestre" | reservas/contratos reais (reputação transacional) |
| "Loja W entregou 200 pedidos na região" | pedidos concluídos do marketplace |
| "Empreiteira K concluiu a 12ª obra com nota 4,9" | medições + avaliações de transação |

É um **feed de fatos verificados** — a vitrine mais crível do setor, impossível de copiar por quem
não gere a operação. Cada publicação é **curada pelo tenant** (marketing aprova o que sai), mas o
*fato* por trás é telemetria real (E3).

## 2. O que cada participante vê (a descoberta que interessa a ele)

| Participante | O feed/busca mostra a ele | Ação de negócio a um clique |
|---|---|---|
| **Lojista / fornecedor** | Quem está construindo (e começando a construir) na região dele; volume de RFQs por categoria | Oferecer orçamento, seguir a obra, perfil na frente do comprador |
| **Construtora** | **Pesquisa de preço de material** (índice real das cotações da rede, por região); ranking de corretores/imobiliárias **por vendas reais**; empreiteiros disponíveis por reputação; o que outras construtoras estão lançando | Abrir RFQ, convidar corretor/empreiteiro para parceria |
| **Imobiliária / corretor** | Lançamentos e unidades disponíveis para distribuir; obras evoluindo (argumento de venda) | Pedir credenciamento, reservar |
| **Cliente final** (persona) | Novas obras e lançamentos na cidade; evolução das obras que acompanha; reputação pública das construtoras | Pedir contato / entrar na fila de lançamento (vira lead no CRM ✅ do tenant) |
| **Empreiteiro / escritório** | Obras que vão precisar do serviço dele; concorrências abertas | Apresentar proposta |
| **Todos** | Quem entrou na plataforma; marcos das empresas que segue | Seguir, conectar, transacionar |

Regra de design: **toda feature social termina em ação de negócio** (orçamento, reserva, parceria,
lead). Seguir/notificar existem para alimentar transação — a rede social é o motor de descoberta
dos marketplaces, não um destino em si.

## 3. As peças

- **Perfil público da empresa (vitrine):** página verificada (CNPJ/CREA/CRECI —
  [04](04-rede-e-marketplaces.md) §4) com portfólio *comprovado*: obras entregues geridas na
  plataforma, avaliações transacionais, selos. Indexável (SEO) — cada perfil é uma landing page
  que traz gente de fora.
- **Página pública da obra/empreendimento (opt-in):** evolução curada (fotos do diário aprovadas,
  ortofoto/timelapse do drone, % de etapas), unidades disponíveis. É simultaneamente marketing da
  construtora e conteúdo do feed.
- **Feed:** eventos E3 curados + publicações editoriais do tenant; filtro por região, segmento e
  quem eu sigo. Feed B2B (edições) e feed do consumidor (portais) são **visões distintas** do
  mesmo grafo.
- **Busca/descoberta:** "quem constrói em Goiânia", "preço médio do aço CA-50 este mês na minha
  região", "melhores imobiliárias por VGV vendido", "empreiteiros de alvenaria com nota > 4,5".
- **Grafo de relações:** seguir (unilateral) + parceria (bilateral, a mesma do modo transacional
  E1) — a parceria comercial e a conexão social são o mesmo vínculo.
- **Rankings e selos:** só sobre **dados transacionais** (vendas reais, obras entregues, SLA de
  resposta a RFQ) — nunca autodeclarados; critérios públicos e janela móvel.
- **Interações leves com moderação barata:** reagir e compartilhar sim; comentários **fechados por
  padrão** (o tenant abre se quiser e modera os seus) — evita o custo de moderação de rede aberta.

## 4. O flywheel da autossustentação (explícito)

```
        empresas entram e operam (edições — 09)
                     │
        operação gera fatos publicáveis (E3 → feed)      ◄─────────────┐
                     │                                                 │
        atividade fica VISÍVEL para quem está fora                     │
        (perfis/obras públicas SEO · feed regional ·                   │
         selo "obra gerida no sistema" no site da construtora ·       │
         contador público "N empresas / M obras na plataforma")       │
                     │                                                 │
        quem está fora sente que o mercado está lá dentro             │
        (lojista vê 12 construtoras da cidade · corretor vê            │
         lançamentos que não distribui · construtora vê o             │
         índice de preços que não acessa)                             │
                     │                                                 │
        entra (trial da edição — loop de convite do 09 §3) ────────────┘
```

Táticas de visibilidade que alimentam o loop (todas baratas, todas opt-in):

1. **Convite transacional** — já definido ([09](09-verticais-por-participante.md) §3): cada RFQ,
   boletim ou espelho para empresa de fora é um convite com contexto.
2. **Conteúdo público SEO** — perfis, obras e lançamentos indexáveis: a busca do Google por
   "construtora em [cidade]" ou "[nome do empreendimento]" cai na plataforma.
3. **Selo/widget embutido** — a construtora incorpora no site dela o widget de evolução da obra
   ("acompanhe ao vivo") apontando para a página pública; cada visitante é exposto à plataforma.
4. **FOMO regional honesto** — "N construtoras e M lojas da sua região já estão na rede" nas
   páginas públicas e no onboarding; número real, nunca inflado.
5. **Ranking como ímã** — o corretor quer aparecer no ranking que as construtoras consultam; para
   pontuar, precisa transacionar dentro. O mesmo para lojas (SLA de resposta) e empreiteiras.

## 5. Fronteiras (para a rede social não trair os princípios)

| Princípio | Aplicação aqui |
|---|---|
| Opt-in absoluto (E1) | Nada vai ao feed sem publicação explícita; despublicar remove; obra privada é invisível |
| Sem PII | Feed mostra empresas, obras e agregados; nunca dados de pessoa (comprador, funcionário) — LGPD by design |
| Fato > marketing | Todo número exibido (%, vendas, notas) tem origem transacional auditável (9.E); editorial é permitido, mas rotulado |
| Anti-distração (novo risco R9) | Feature social sem ação de negócio associada não entra; medir **transações originadas no feed**, não engajamento |
| Índice de preços | Agregado k-anônimo por região/categoria (E4 §3) — nunca expõe a cotação de um tenant identificável |
| Concorrência leal | Tenant controla o que os concorrentes veem dele (curadoria); rankings têm critério público e contestável |

## 6. Sequência (por que é o último estágio — e o que antecipar)

A rede social **consome** tudo que vem antes: sem edições não há quem ver; sem marketplaces não há
ação de negócio; sem E3 não há fatos; sem E4 não há índice de preços. Por isso é o capstone (H3).
Mas duas peças **antecipam para H2**, porque os marketplaces já precisam delas:

- **Perfil público verificado** (vitrine) — é a mesma verificação/reputação do
  [04](04-rede-e-marketplaces.md) §4;
- **Página pública da obra/empreendimento** — é a curadoria que a Edição Imobiliária já exige
  ([04](04-rede-e-marketplaces.md) §2.2).

O feed, a busca transversal, os rankings e os growth loops públicos (SEO/widget/contadores)
fecham em H3, quando há densidade para o flywheel girar
([08-roadmap-estrategico.md](08-roadmap-estrategico.md)).

**Métricas do flywheel:** % de tenants novos que chegam **sem venda ativa** (orgânico: SEO, feed,
convite, widget) · transações originadas em descoberta no feed · tempo até a 1ª transação de um
tenant novo · densidade regional (empresas ativas por cidade).
