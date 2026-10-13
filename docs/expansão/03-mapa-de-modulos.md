# Mapa de módulos — catálogo-alvo por camada de domínio (Níveis 2–3)

> O inventário do que **deveria existir** para cobrir o ciclo de vida inteiro do empreendimento
> ([01-visao.md](01-visao.md) §1). Convenções: **✅ existe** (doc em [../modulos/](../modulos/README.md)) ·
> **📦 placeholder** (app vazio, [modulos-planejados.md](../modulos/modulos-planejados.md)) ·
> **🧭 proposto** (este catálogo). Todo módulo novo segue o contrato de módulo
> ([../acesso-e-permissoes.md](../acesso-e-permissoes.md) §7): Django app + `TenantScopedModel` +
> entitlement próprio + permissões no catálogo da IAM. Horizontes (H1/H2/H3) em
> [08-roadmap-estrategico.md](08-roadmap-estrategico.md).

## Mapeamento dos placeholders atuais

| App vazio | Destino neste catálogo |
|---|---|
| `moduloscm` | §3 Suprimentos — SCM (requisições→cotações→pedidos) |
| `modulodms` | §6 Documental — DMS/gestão documental |
| `moduloprancheta` | §2 Engenharia & Obra — **Prancheta**: o visualizador de projeto em campo (era `moduloaps`, lido por engano como "planejamento") |
| `modulopdca` | §2 Engenharia & Obra — planejamento de obra **e** qualidade/melhoria contínua |
| `modulomaps` | §7 Terrenos & Incorporação — GIS/geolocalização |
| `modulosil` | **definido:** §3 Suprimentos — **estoque & logística interna** (almoxarifado central + canteiros, saldo valorado, movimentações, requisição, rastreabilidade, inventário). Planta em [../modulos/modulosil.md](../modulos/modulosil.md) |

> **Catálogo-mestre de plataforma (novo, fundação):** o porte do SIL extrai o `Produto` do SCM para
> um app-fundação **`catalogo`** (sem entitlement) — o **item mestre único** (bem/serviço/equip./
> ativo/composição) compartilhado por SCM, SIL e futuros (comercial, orçamento). Padrão MDM/PIM
> (SAP Material Master / Oracle Item Master). Planta em [../modulos/catalogo.md](../modulos/catalogo.md).

## 1. Núcleo (existente — a fortaleza)

`empreendimentos` · `obras` · `clientes` · `fornecedores` · `modulodiario` · `moduloerp` · `rh` ·
`modulocrm` · `modulocalendar` · `funcoesia` · `funcoescobrancas` · **drone (funcoesODM)** ·
`funcoeswhatsapp` · NF-e/NFS-e (`moduloerp.nfe_client`). Expansão aqui = profundidade
(funcionalidades premium), não módulos novos — DRE por obra, fluxo de caixa projetado, conciliação
bancária (ver §5).

## 2. Engenharia & Obra

| Módulo | Status | O que faz | Depende de | Efeito de rede / IA |
|---|---|---|---|---|
| Planejamento de obra | 📦 `modulopdca` | Cronograma físico (EAP, Gantt, linha de balanço), avanço × previsto | obras, diário, orçamento | IA: previsão de atraso com histórico do diário ([06](06-dados-ia-automacao.md)) |
| Orçamento de obra | ✅ `moduloorcamento` | Planilha orçamentária (EAP × insumos), composições de custo (SINAPI/ORSE/TCPO), BDI/encargos, curva ABC, curva S e **orçado × comprometido × aplicado × realizado**. Planta em [../modulos/moduloorcamento.md](../modulos/moduloorcamento.md) | catálogo, obras, SCM, SIL, moduloerp | Benchmark de custo/m² entre tenants (E4); banco de composições da rede |
| Medições & empreiteiros | ✅ | Contratos de empreitada (custo) e com o contratante (receita), boletins de medição, retenção, reajuste — dentro do PDCA ([modulopdca.md](../modulos/modulopdca.md)) | obras, moduloerp, fornecedores, clientes | Falta o boletim espelhado com a **Edição Empreiteiro** ([09](09-verticais-por-participante.md)) |
| Qualidade / PDCA / ISO | 📦 `modulopdca` *(mesmo app do planejamento)* | Checklists de serviço (FVS), não-conformidades, planos de ação, auditorias ISO 9001/PBQP-H | obras, diário | IA: detectar não-conformidade em foto do diário |
| SST (segurança do trabalho) | 🧭 | NRs, treinamentos, EPIs, inspeções, CAT/acidentes | rh, obras | IA: detecção de EPI em fotos; premium compliance |
| Equipamentos & frota | 🧭 | Ativos de obra, alocação, manutenção preventiva, horímetro/diesel | obras, moduloerp | IoT/telemetria (H3); aluguel ocioso → marketplace |
| **Prancheta** — projeto em campo | 📦 `moduloprancheta` | Visualizador central dos arquivos de projeto: DWG/DXF, RVT, IFC, KMZ/QGIS, nuvem de pontos e PDF, abertos no celular no canteiro. Depois: vínculo modelo↔etapa↔orçamento (4D/5D) e BCF. Planta em [../modulos/moduloprancheta.md](../modulos/moduloprancheta.md) | obras, maps, drone, orçamento | Produto premium por formato (paywall caso a caso); 4D/5D é H3 |

## 3. Suprimentos (SCM)

| Módulo | Status | O que faz | Depende de | Efeito de rede / IA |
|---|---|---|---|---|
| SCM — compras | 📦 `moduloscm` | Requisição → cotação → mapa comparativo → pedido → recebimento (casa com XML NF-e já lido) | fornecedores, moduloerp, obras | **A ponte para o marketplace de cotações** ([04](04-rede-e-marketplaces.md) §2) |
| Estoque / almoxarifado & logística interna | 📦 `modulosil` | Estoque por obra/central, saldo valorado, movimentações, requisição da obra, transferências, devoluções, rastreabilidade (lote/validade), inventário | catálogo, SCM, obras, ERP | Estoque mínimo → RFQ automática (E6); benchmark de giro (E4) |
| Contratos de fornecimento | 🧭 | Acordos de preço, entregas programadas, aditivos | SCM, fornecedores | Preço histórico alimenta benchmark |

## 4. Comercial & Vendas

| Módulo | Status | O que faz | Depende de | Efeito de rede / IA |
|---|---|---|---|---|
| CRM | ✅ | Funil lead→oportunidade | — | IA de scoring ✅ (in-process) |
| Espelho de vendas & tabela de preços | 🧭 | Unidades (disponível/reservado/vendido), tabelas, reserva com prazo, comissões | empreendimentos, clientes, CRM | **Pré-requisito do marketplace de imóveis e do portal do corretor** |
| Contratos & assinatura digital | 🧭 | Minutas, versionamento, assinatura eletrônica (ICP-Brasil/clique) | clientes, DMS | Assinatura por documento = receita medida |
| Simulador de financiamento / repasse | 🧭 | Simulação, dossiê do comprador, esteira de repasse bancário | clientes, moduloerp | Ponte com bancos (H3) |
| Gestão de corretores & comissões | 🧭 | Corretores internos/parceiros, regras de comissão, extrato | espelho de vendas, moduloerp | Espelho distribuído à **Edição Imobiliária** ([09](09-verticais-por-participante.md)) |

## 5. Financeiro avançado (profundidade do `moduloerp`)

Fluxo de caixa projetado · orçamento empresarial · conciliação bancária (OFX/Open Finance) ·
consolidação multiempresa/SPE (comum em incorporação — cada empreendimento é uma SPE; hoje
`Empreendimento` já tem CNPJ próprio, o embrião certo) · antecipação de recebíveis e demais
produtos fintech em [07-monetizacao-da-expansao.md](07-monetizacao-da-expansao.md) §5.

## 6. Documental & Jurídico

| Módulo | Status | O que faz | Depende de |
|---|---|---|---|
| DMS — gestão documental | 📦 `modulodms` | Repositório central, versões, validade/vencimento, GED por obra/empreendimento (absorve `DocumentoObra`/`DocumentoFuncionario` como visões) | todos |
| Licenciamento & alvarás | 🧭 | Protocolos em órgãos, prazos, condicionantes, renovações | DMS, obras |
| Meio ambiente | 🧭 | Licenças ambientais, condicionantes, resíduos (CTR/MTR) | DMS, obras |
| Jurídico & contencioso | 🧭 | Processos, distratos, acordos | clientes, contratos |

DMS é **transversal**: quase todo módulo proposto anexa documento — construí-lo cedo evita 10
mini-GEDs divergentes.

## 7. Terrenos & Incorporação (a ponta inicial do fluxo)

| Módulo | Status | O que faz | Depende de | Efeito de rede |
|---|---|---|---|---|
| Banco de terrenos | 🧭 | Prospecção, dono, m², zoneamento, status de negociação, permutas | GIS | **Marketplace de terrenos** ([04](04-rede-e-marketplaces.md)) |
| Estudo de viabilidade | 🧭 | VGV, custo estimado, TIR/exposição de caixa, cenários | banco de terrenos, orçamento | IA: viabilidade paramétrica por histórico |
| GIS / mapas | 📦 `modulomaps` | Camadas geográficas: terrenos, obras, empreendimentos, ortofotos do **drone** (que já produz GeoTIFF) | drone, terrenos | O acervo de ortofotos é diferencial único |

## 8. Pós-entrega & Operação (a ponta final — hoje deserta)

| Módulo | Status | O que faz | Depende de | Efeito de rede |
|---|---|---|---|---|
| Entrega & vistorias | 🧭 | Agenda de vistoria, checklist por unidade, ressalvas, termo de entrega assinado | espelho de vendas, clientes | Alimenta assistência técnica |
| **Assistência técnica (pós-obra)** | 🧭 | Chamados de garantia por unidade/sistema construtivo, SLA, técnico em campo | entrega, clientes, obras | **Micro-SaaS candidato** ([07](07-monetizacao-da-expansao.md) §4); portal do cliente abre chamado |
| Manual do proprietário | 🧭 | Manual digital por unidade (NBR 14037), garantias por sistema | entrega, DMS | Conteúdo do portal do cliente |
| Facility management | 🧭 | Manutenção predial preventiva/corretiva, ativos, planos | patrimônio | Vende para o condomínio depois da entrega |
| Administração de condomínio | 🧭 | Unidades, moradores, taxas (reusa cobranças Asaas!), reservas, assembleias | funcoescobrancas | Portal síndico/morador; **novo mercado inteiro** (H3) |
| Patrimônio & manutenção | 🧭 | Ativos próprios da empresa, depreciação, manutenção | moduloerp | — |

A assistência técnica é a expansão de maior alavancagem do H1: dor universal (garantia é obrigação
legal), dados já presentes (cliente, unidade, obra) e é a razão natural do comprador entrar no
portal — que depois vira canal de revenda e indicação.

## 9. Pessoas (profundidade do `rh`)

Ponto de obra (app móvel, geofence) · treinamentos/NRs (casa com SST) · gestão de terceiros
(documentação de empreiteiros — integração obrigatória com medições §2).

## 10. Módulos específicos das edições verticais

As edições ([09-verticais-por-participante.md](09-verticais-por-participante.md)) são
majoritariamente **reuso** dos módulos acima; o delta específico é pequeno e deliberadamente
listado aqui para não virar produto paralelo:

| Módulo | Status | Edição que o exige | O que faz |
|---|---|---|---|
| Orçamento & pedido de venda | 🧭 | Loja/distribuidor | Orçamento de balcão, conversão em pedido, fila de RFQs da rede |
| Logística de entrega simples | 🧭 | Loja/distribuidor | Romaneio, agenda de entregas, comprovante |
| Proposta de serviço | 🧭 | Empreiteiro/prestador | Proposta → contrato de serviço → medições a faturar (lado B do boletim) |
| Carteira de imóveis & locação | 🧭 | Imobiliária | Imóveis próprios/parceiros, contratos de aluguel, repasse ao proprietário (reusa Asaas ✅) |
| Projetos & propostas + timesheet | 🧭 | Escritório de projeto | Etapas de projeto, horas, aprovações do cliente, ART/RRT |

## 11. Dados, IA e integrações

Central de IA, BI/warehouse, automações, IoT e integrações externas têm doc próprio:
[06-dados-ia-automacao.md](06-dados-ia-automacao.md). Marketplaces (a camada de rede que consome
tudo acima): [04-rede-e-marketplaces.md](04-rede-e-marketplaces.md); portais de consumidor e apps:
[05-portais-e-apps.md](05-portais-e-apps.md); edições verticais:
[09-verticais-por-participante.md](09-verticais-por-participante.md).

## Dependências estruturantes (o grafo resumido)

```
 DMS ──────────────┐                    espelho de vendas ──► Edição Imobiliária / marketplace imóveis
 eventos (E3) ─────┼──► quase tudo      SCM ───────────────► Edição Loja / marketplace de cotações
 ABAC objeto (E2) ─┘                    entrega/vistoria ──► assistência técnica ──► portal cliente
 PDCA + orçamento ─► Prancheta 4D/5D    cobranças Asaas ───► condomínio (reuso direto)
                                        medições ──────────► Edição Empreiteiro (boletim espelhado)
```

Regra de ouro do sequenciamento: **construir primeiro o módulo privado que gera o dado; o
marketplace/portal correspondente é a publicação dele** ([01-visao.md](01-visao.md) §3.2).
