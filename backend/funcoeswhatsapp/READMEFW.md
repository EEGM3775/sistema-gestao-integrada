# Módulo `funcoeswhatsapp` - Arquitetura V2 (Microserviço Node.js)

Este documento detalha o funcionamento do módulo de integração com o WhatsApp, implementado como um microserviço independente, robusto e pronto para produção em Node.js.

## Visão Geral

O módulo atua como um servidor dedicado que recebe webhooks da API da Meta (WhatsApp), processa as mensagens recebidas e se comunica de forma segura com o backend principal do Django para acessar e registrar dados. Ele gerencia o fluxo de conversas de múltiplos passos de forma assíncrona e com estado persistente.

## Arquitetura e Features

*   **Validação de Configuração:** Na inicialização, o módulo (`config.js`) valida todas as variáveis de ambiente necessárias. O serviço falhará ao iniciar se alguma variável crítica estiver ausente, evitando erros em tempo de execução.
*   **Comunicação Segura com a API:** Todas as chamadas para o backend Django são autenticadas usando um token de API estático (`apiService.js`), garantindo que apenas serviços autorizados possam acessar os dados.
*   **Logging Estruturado:** Utiliza a biblioteca **Winston** (`logger.js`) para gerar logs. Em ambiente de desenvolvimento, os logs são coloridos e de fácil leitura. Em produção, são emitidos em formato **JSON**, facilitando a integração com sistemas de monitoramento e análise.
*   **Testes Automatizados:** O projeto conta com um conjunto de testes unitários utilizando **Jest**. Isso garante a confiabilidade do código e previne regressões.
*   **Gerenciamento de Estado:** O estado da conversa é armazenado no **Redis** (`services/cacheService.js`), garantindo que as conversas sejam persistentes mesmo que o serviço reinicie.

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
Para mais detalhes, consulte a documentação no `backend/nucleo/README.md`.

## Instalação de Dependências

O comando a seguir instala as dependências de produção e de desenvolvimento (como o Jest):

```bash
npm install --prefix backend --workspace funcoeswhatsapp
```

## Scripts e Execução

Os scripts a seguir podem ser executados a partir da raiz do projeto.

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
