# Microserviço `funcoeslead` - Roadmap de Funcionalidades

Este documento descreve o plano de desenvolvimento e a arquitetura para o microserviço de Funções de Lead, construído em Node.js. Este serviço será responsável por orquestrar lógicas de negócio complexas relacionadas ao ciclo de vida de Leads e Oportunidades do módulo CRM.

## Arquitetura Proposta

O microserviço será acionado pelo backend Django através de chamadas de API principalmente em backend/modulocrm seguras ou por um sistema de mensageria (como RabbitMQ ou Redis Pub/Sub) para garantir o desacoplamento e a escalabilidade.

- **Plataforma:** Node.js com Express.js ou Fastify
- **Linguagem:** TypeScript para segurança de tipos
- **Porta:** 3004
- **Comunicação com Django:** API REST segura, com autenticação via token de serviço.
- **Banco de Dados:** Este serviço será, em princípio, *stateless*, orquestrando dados que residem no banco de dados principal do Django.

---

## Roadmap de Funcionalidades

### Fase 1: O Essencial - Automação do Funil de Vendas

#### 1.1. Serviço de Conversão de Leads (Prioridade Máxima)
- **Objetivo:** Automatizar a promoção de um `Lead` qualificado para as próximas etapas do funil de vendas.
- **Gatilho:** Um endpoint `POST /api/leads/convert` que recebe o `lead_id`.
- **Fluxo de Execução:**
    1. O serviço recebe a requisição de conversão do Django.
    2. Valida se o Lead existe e se seu status é "QUALIFICADO".
    3. **Criação de Conta:** Busca na API do Django por uma `Account` com o nome da empresa (`company`) do Lead. Se não existir, cria uma nova.
    4. **Criação de Contato:** Cria um `Contact` no Django, associado à `Account` encontrada ou criada.
    5. **Criação de Oportunidade:** Cria uma `Opportunity` vinculada à nova `Account` e `Contact`, transferindo informações relevantes como valor estimado e responsável.
    6. **Atualização do Lead:** Altera o status do `Lead` original para "CONVERTIDO" e arquiva-o, mantendo o histórico mas removendo-o das listas ativas.
    7. Retorna os IDs dos novos objetos criados (`account_id`, `contact_id`, `opportunity_id`) para o Django.

### Fase 2: Inteligência e Análise de Dados

#### 2.1. Serviço de Dashboard e Analytics
- **Objetivo:** Centralizar o processamento de dados analíticos para o CRM, aliviando a carga do Django.
- **Endpoints:**
    - `GET /api/analytics/sales-funnel`: Retorna a contagem e o valor total de oportunidades em cada estágio (`stage`).
    - `GET /api/analytics/lead-source`: Analisa as oportunidades ganhas e perdidas para determinar a eficácia de cada `source` (origem) de lead.
    - `GET /api/analytics/performance?user_id=<id>`: Calcula métricas de performance para um vendedor específico (taxa de conversão, tempo médio de fechamento, etc.).
    - `GET /api/analytics/forecasting`: Implementa um modelo simples de previsão de vendas com base no valor e na probabilidade das oportunidades em aberto.

### Fase 3: Produtividade e Engajamento

#### 3.1. Serviço de Gestão de Tarefas e Notificações
- **Objetivo:** Prover um sistema ativo de gerenciamento de tarefas e lembretes.
- **Funcionalidades:**
    - **Webhooks para Calendário:** Integração com Google Calendar ou Outlook para sincronizar reuniões agendadas no CRM.
    - **Serviço de Notificação:** Um worker que periodicamente verifica as `Interactions` do tipo "Tarefa" com prazo para vencer e envia notificações (via e-mail) para o responsável (que pode ser um `Usuário`, `Funcionário` ou `Fornecedor`).
    - **API de "Minha Agenda":** Um endpoint auxiliar `GET /api/users/<id>/agenda` que retorna tarefas e interações de um usuário para um determinado período, facilitando a criação de interfaces de produtividade. Esta API é projetada para ser uma fonte de dados para a agenda de leads, mas pode ser estendida para outras finalidades.

#### 3.2. Serviço de Scoring de Leads (Lead Scoring)
- **Objetivo:** Criar um sistema que pontua e prioriza leads automaticamente.
- **Lógica:**
    1. O serviço recebe dados de um novo lead.
    2. Aplica um sistema de pontos com base em critérios pré-definidos (cargo, setor da empresa, origem do lead, interações no site, etc.).
    3. Salva o "score" no registro do `Lead` no Django.
    4. Vendedores podem usar o score para focar nos leads com maior probabilidade de conversão.

### Fase 4: Expansão e Integrações

#### 4.1. Integração com Catálogo de Produtos/Serviços
- **Objetivo:** Permitir que produtos específicos sejam adicionados a uma `Opportunity`.
- **Fluxo:**
    - O microserviço fornecerá um endpoint para buscar produtos do módulo `moduloerp` (ou outro catálogo).
    - Permitirá adicionar "itens de linha" a uma oportunidade, calculando o valor total automaticamente.

#### 4.2. Módulo de Campanhas de Marketing
- **Objetivo:** Medir o ROI de campanhas de marketing.
- **Funcionalidades:**
    - Um endpoint para registrar `Campaigns` (ex: "Campanha de Lançamento XYZ").
    - O serviço irá associar `Leads` a campanhas (possivelmente via parâmetros UTM em um formulário de site).
    - O serviço de Analytics poderá, então, gerar relatórios de "Custo por Lead" e "ROI da Campanha".
