# Bot de WhatsApp (`funcoeswhatsapp`, Node)

> Recebe webhooks da API da Meta (WhatsApp), gerencia fluxos de conversa com estado no Redis (ex.:
> diário de obra por chat) e registra dados no ERP; contatos desconhecidos viram `nucleo.PreCadastro`.
> Código: [backend/funcoeswhatsapp/](../../backend/funcoeswhatsapp/).
>
> ⚠️ As chamadas ao ERP usam o token estático legado (pré-Fase 6) — ver
> [../pendencias.md](../pendencias.md). **Destino (Fase 11.3 do [roadmap](../roadmap.md)):** o
> webhook migra para endpoint Django em `modulodiario` + Celery, dentro do novo modelo de diário
> compartilhado ([plano](../arquitetura/diario-ia-reintegracao.md)) — não desenvolver features
> novas aqui.

## Visão Geral

O módulo atua como um servidor dedicado que recebe webhooks da API da Meta (WhatsApp), processa as mensagens recebidas e se comunica de forma segura com o backend principal do Django para acessar e registrar dados. Ele gerencia o fluxo de conversas de múltiplos passos de forma assíncrona e com estado persistente.

## Arquitetura e Features

*   **Plataforma de Fluxos de Conversa:** O serviço é projetado como uma plataforma capaz de gerenciar múltiplos fluxos de conversa independentes. A lógica de cada conversa (ex: "Diário de Obra") é isolada em seu próprio módulo na pasta `/bot/flows`.
*   **Gerenciador de Fluxos e Roteador de Comandos:** O bot possui um gerenciador central (`bot.js`) que roteia as mensagens. Se um usuário já está em uma conversa, a mensagem é enviada para o fluxo ativo. Se não, a mensagem é passada para um roteador de comandos (`commandRouter.js`) que mapeia palavras-chave para iniciar novos fluxos.
*   **Camada de Autorização:** Antes de iniciar qualquer fluxo, o bot verifica a identidade do usuário (Funcionário, Cliente, Fornecedor) através da API do Django. O `commandRouter.js` então valida se aquele tipo de usuário tem permissão para acionar o fluxo solicitado, garantindo que um cliente não possa acessar funcionalidades de um funcionário, por exemplo.
*   **Cache de Identidade (Otimização):** Para minimizar a latência, a identidade de um usuário é mantida em um cache de curta duração (15 segundos) no Redis. Isso garante que, para uma conversa fluida, apenas a primeira mensagem exija uma chamada de API, enquanto as subsequentes têm resposta de identidade instantânea, mantendo a segurança de verificação quase em tempo real.
*   **Gerenciamento de Estado Persistente:** O estado da conversa de cada usuário é armazenado no **Redis** (`services/cacheService.js`), garantindo que as conversas de múltiplos passos sejam persistentes mesmo que o serviço reinicie.
*   **Arquitetura de Serviços de API Escalável:** A comunicação com a API do Django é organizada em uma arquitetura de serviços por domínio. Em vez de um único arquivo, as chamadas de API são divididas em múltiplos arquivos dentro da pasta `services/api/` (ex: `authService.js`, `diarioObraService.js`). Isso torna o código mais modular, escalável e fácil de manter.
*   **Comunicação Segura com a API:** Todas as chamadas para o backend Django são autenticadas usando um token de API estático através de um cliente de API central (`services/apiClient.js`), garantindo que apenas este serviço possa acessar os dados.
*   **Proteção contra DoS (Rate Limiting):** O endpoint de webhook é protegido contra ataques de negação de serviço. O sistema limita o número de requisições por endereço IP, bloqueando tráfego excessivo que poderia sobrecarregar o serviço.
*   **Validação de Configuração e Logging Estruturado:** O serviço valida as variáveis de ambiente na inicialização e utiliza a biblioteca **Winston** para logs robustos em produção e desenvolvimento.

## Fluxo de Execução de Mensagens

1.  **Webhook:** O `whatsappController.js` recebe a mensagem da Meta, valida a assinatura de segurança e passa uma mensagem padronizada para o `bot.js`.
2.  **Identificação (com Cache):** O `bot.js` solicita a identidade do usuário ao `authService.js` (`services/api/authService.js`). Este primeiro tenta buscar os dados de um cache rápido no Redis. Se não encontrar (ou se o cache tiver mais de 15 segundos), ele faz a chamada para a API do Django para identificar o perfil (`funcionário`, `cliente`, `fornecedor` ou `unknown`).
3.  **Gerenciador de Fluxos (`bot.js`):**
    *   Verifica se o usuário possui um estado de conversa ativo no Redis.
    *   **Se sim:** Valida se o perfil do usuário não mudou. Se estiver tudo consistente, carrega o módulo de fluxo correspondente e passa a mensagem para ele processar.
    *   **Se não:** Inicia um novo fluxo.
4.  **Roteamento de Nova Conversa:**
    *   Se o perfil do usuário for `unknown`, o `preCadastroFlow` é iniciado para capturar os dados do novo contato.
    *   Se o perfil for conhecido, a mensagem é enviada ao `commandRouter.js`, que verifica as permissões (utilizando os serviços de API necessários, como o `obraService.js`) e, se autorizado, inicia o fluxo correspondente.

## Configuração (`.env`)

As variáveis de ambiente são gerenciadas em um arquivo `.env` na raiz deste módulo. O serviço não iniciará se alguma das variáveis obrigatórias estiver faltando.

```env
# --- Configurações do Serviço ---
# Porta em que o serviço Node.js irá rodar (opcional, padrão 3001)
WHATSAPP_PORT=3001
# Ambiente de execução ('development' ou 'production')
NODE_ENV=development
# Nível de log a ser exibido (ex: 'info', 'warn', 'error') (opcional)
LOG_LEVEL=info

# --- Credenciais da Meta (Obrigatório) ---
META_ACCESS_TOKEN=SEU_TOKEN_DE_ACESSO_DA_META
META_VERIFY_TOKEN=SEU_TOKEN_DE_VERIFICACAO_DO_WEBHOOK
META_APP_SECRET=SEU_SEGREDO_DO_APP_DA_META
META_PHONE_NUMBER_ID=SEU_ID_DE_TELEFONE_DO_WHATSAPP
META_API_VERSION=v19.0

# --- Conexões com Outros Serviços (Obrigatório) ---
# URL completa para a API do backend Django
DJANGO_API_URL=http://localhost:8000/api
# Token de autenticação para a API do Django
DJANGO_API_TOKEN=SEU_TOKEN_GERADO_NO_DJANGO

# URL de conexão para o servidor Redis
REDIS_URL=redis://localhost:6379
```

### Obtendo o `DJANGO_API_TOKEN`

Este token é crucial para a segurança. Ele é gerado no backend Django através de um comando de gerenciamento. Para criá-lo, execute o seguinte comando na raiz do projeto e siga as instruções:

```bash
./.venv/bin/python backend/manage.py create_service_token --username whatsapp_service --cpf "000.000.000-00" --first_name "Serviço" --last_name "WhatsApp"
```
Para mais detalhes, consulte a documentação no `docs/modulos/nucleo.md`.

## Instalação de Dependências

Para instalar as dependências do Node.js, navegue até o diretório do serviço e execute:

```bash
cd backend/funcoeswhatsapp
npm install
```

## Scripts e Execução

### Execução em Modo de Desenvolvimento

Inicia o serviço com `nodemon`, que reinicia automaticamente após qualquer alteração no código.

```bash
# Dentro de backend/funcoeswhatsapp/
npm run dev
```

### Execução de Testes

Roda todos os testes unitários com Jest.

```bash
# Dentro de backend/funcoeswhatsapp/
npm run test
```

### Execução em Produção

Inicia o serviço usando `node`. Para ambientes de produção, é altamente recomendado usar um gerenciador de processos como o `pm2`.

```bash
# Dentro de backend/funcoeswhatsapp/
npm start
```

## Funcionalidades Futuras (Roadmap)

Esta é uma lista de funcionalidades planejadas para serem implementadas no futuro, visando aumentar a eficiência e segurança das operações.

### Recursos Humanos
- [ ] **Consulta de Holerite:** Permitir que o funcionário solicite seu holerite em PDF.
- [ ] **Ponto Eletrônico Inteligente:** Implementar o registro de ponto de entrada e saída pelo WhatsApp.

### Produtividade e Operações
- [ ] **Requisição de Materiais:** Criar um fluxo para solicitar materiais e ferramentas do canteiro de obras.
- [ ] **Distribuição de Tarefas Diárias:** Permitir que o funcionário consulte suas tarefas do dia.
- [ ] **Apontamento de Horas por Atividade:** Desenvolver um sistema para que o funcionário informe as horas gastas em cada tarefa.

### Segurança, Qualidade e Equipamentos
- [ ] **Reporte Imediato de Incidentes e Riscos:** Criar um fluxo para reportar incidentes, riscos e não conformidades.
- [ ] **Checklist de Ferramentas e EPIs:** Implementar checklists para retirada/devolução de ferramentas e solicitação de EPIs.
- [ ] **Checklists Digitais de Verificação (FVS):** Digitalizar o preenchimento de Fichas de Verificação de Serviço.
- [ ] **DDS Digital e Pílulas de Segurança:** Criar um sistema para envio de conteúdo de segurança (DDS).