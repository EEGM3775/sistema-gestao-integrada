# Dados, IA e automação — os multiplicadores

> O que já existe: análise de imagem por IA (`funcoesia` ✅, Celery + LLM local via
> `LLM_VISION_URL`), scoring de leads no CRM ✅, leitura de XML NF-e ✅, notificações in-app ✅,
> volumetria/medições no drone (Potree) ✅. Base técnica das propostas: eventos E3, plataforma de
> dados E4, automação E6 ([02-arquitetura-de-expansao.md](02-arquitetura-de-expansao.md)).
> Regra de custo: toda chamada de IA é recurso **medido** no modelo de quotas
> ([monetizacao.md §4.2](../arquitetura/monetizacao.md)).

## 1. Central de IA — oportunidades por módulo

| Módulo-fonte | IA proposta | Dado de treino/contexto | Valor |
|---|---|---|---|
| Diário de obra ✅ | Análise de foto ✅ → **evoluir p/**: detecção de EPI (SST), detecção de não-conformidade, avanço físico estimado por imagem | Fotos do diário + etiquetas de etapa | Compliance automático; medição sem visita |
| Drone ✅ | Volumetria de aterro/estoque ✅ (Potree) → comparação temporal automática entre voos, avanço vs. cronograma (APS) | Ortofotos/nuvens sequenciais | "A obra andou X% este mês" sem apontamento manual |
| APS + diário | **Previsão de atraso** (o modelo mais vendável do setor) | Histórico cronograma × diário × clima | Alerta antes do estouro |
| Orçamento + SCM | Previsão de estouro de custo; sugestão de preço em cotação | Orçado × realizado × preços da rede | Protege margem do cliente |
| ERP financeiro | Score de **inadimplência** por parcela/cliente; priorização da régua de cobrança | Histórico de pagamento (Asaas ✅) | Menos churn de caixa |
| CRM ✅ | Scoring ✅ → next-best-action; resposta assistida a lead via WhatsApp ✅ (canal pronto) | Interações + conversões | Velocidade de funil |
| Contratos/DMS | Extração de cláusulas, alertas de prazo/reajuste (IGP-M/INCC), resumo de contrato | Documentos do tenant | Jurídico preventivo |
| NF-e ✅ | Classificação automática de item → centro de custo/etapa | XMLs já capturados | Lançamento sem digitação |
| Atendimento | Chatbot RAG sobre os dados do tenant ("qual o saldo da obra X?", "quando vence o alvará?") — respeitando RBAC/RLS do usuário que pergunta | Todos, via API interna | O "fale com seu ERP"; premium claro |

Regras de plataforma: IA **nunca** cruza dados de tenants (modelo global só com dado agregado
anonimizado e opt-in — E4 §3); toda inferência que vira decisão registra trilha no `AuditLog`;
LLM local primeiro (já é o desenho da 11.3) com fallback a API externa medida.

## 2. BI e plataforma de dados (estágios do E4)

| Estágio | Entrega | Produto/monetização |
|---|---|---|
| 1. Dashboards nativos (H1) | KPIs por módulo (hub ERP ✅; dashboard F.1 pendente) + dashboards de obra/comercial/suprimentos | Incluído nos planos; retenção |
| 2. Warehouse + BI interno (H2) | Projeções dos eventos E3 em esquema analítico; construtor de relatórios/dashboards custom, export, agendamento | **Premium** (add-on BI) |
| 3. Benchmarks de mercado (H3) | Custo/m² por região/tipologia, prazo médio, inadimplência média, preço de insumos (alimentado pelas cotações da rede) — agregado, anonimizado, k-anonimato, opt-in | **Produto de dados** vendável até p/ quem não é tenant (bancos, seguradoras) |

O benchmark de preço de insumos é subproduto direto do marketplace de cotações
([04](04-rede-e-marketplaces.md) §2.1) — cada RFQ respondida enriquece o índice: efeito de rede
de dados.

## 3. Automação e workflow (E6) — casos-alvo do motor de regras

| Evento (E3) | Regra exemplo | Ação |
|---|---|---|
| `scm.estoque_minimo_atingido` | sempre | Criar requisição + RFQ p/ lojas parceiras (o caso conector §2.1 de [04](04-rede-e-marketplaces.md)) |
| `erp.parcela_vencida` | há 5 dias e sem acordo | Régua: e-mail → WhatsApp → notificar cobrança → score de inadimplência |
| `obras.etapa_concluida` | etapa é marco contratual | Liberar parcela vinculada; notificar imobiliárias parceiras; agendar vistoria |
| `diario.foto_analisada` | IA detectou ausência de EPI | Abrir não-conformidade (SST) + notificar técnico de segurança |
| `crm.lead_criado` | origem = portal/marketplace | Distribuir p/ corretor por rodízio; SLA de resposta |
| `assistencia.chamado_aberto` | prazo de garantia expirando | Priorizar fila; notificar engenharia |
| `dms.documento_vencendo` | alvará/licença/ART em 30 dias | Tarefa no calendário do responsável ✅ (lembretes já existem) |

## 4. IoT, sensores e telemetria (H3)

Entra **depois** de equipamentos & frota existirem como módulo; sempre via gateway de ingestão
próprio (série temporal), nunca inflando o Postgres transacional.

- Telemetria de frota/equipamento (horímetro, combustível, localização) → manutenção preditiva.
- Sensores de canteiro (concreto/cura, umidade, ruído, poeira) → qualidade e compliance ambiental.
- Câmera timelapse fixa (aliada ao drone) → avanço visual contínuo + material de marketing.
- Telemetria também alimenta o benchmark (custo-hora real de equipamento).

## 5. Integrações externas (consumo e abertura)

| Integração | Status/rota |
|---|---|
| WhatsApp ✅ · Google (OAuth via `moduloapi`) ✅ · Asaas ✅ · NFE.io ✅ | Consolidar como catálogo de conectores |
| Outlook/Teams, Google Calendar sync | H1–H2 (calendário já tem RRULE/feriados) |
| Contabilidade (export SPED/domínio contábil) | H1 — pedido inevitável de todo financeiro |
| Open Finance (conciliação), bancos (repasse/medição) | H2–H3 |
| API pública + webhooks + SDK + marketplace de integrações | E5 — H2; cada conector novo é Celery task (AD-8) |
