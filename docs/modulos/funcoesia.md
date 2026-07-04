# Análise de imagens por IA (`funcoesia`)

> App **híbrido**: a parte Django (models `AnaliseImagemIA`, views, rotas `/api/ia/`) convive no
> mesmo diretório com um **worker Node embutido** (`index.js`, `:3002`) que chama o **Google
> Gemini**. Este documento cobre o worker Node; o contrato de análise e a parte Django estão em
> [funcoesia-analise-ia.md](funcoesia-analise-ia.md).
> Código: [backend/funcoesia/](../../backend/funcoesia/).
>
> ⚠️ **Callback Node→Django provavelmente inoperante:** usa `Authorization: Token` (legado
> pré-Fase 6, mesmo problema do achado L4) — ver [../pendencias.md](../pendencias.md).
> **Destino (Fase 11):** o worker Node migra para task Python (a LLM local do cliente substituirá o
> Gemini — ver [plano de reintegração](../arquitetura/diario-ia-reintegracao.md)); não desenvolver
> features novas na parte Node.

## Visão Geral

O módulo atua como um servidor dedicado que é acionado pelo backend principal (Django) sempre que uma nova imagem é adicionada a um Diário de Obra. Ele é responsável por:

1.  Receber o ID de um documento (imagem).
2.  Comunicar-se de forma segura com a API do Django para obter a URL da imagem e criar um registro de análise.
3.  Baixar a imagem.
4.  Enviá-la para a API do Google Gemini para análise com base em um prompt de engenharia.
5.  Salvar o resultado estruturado (JSON) de volta no banco de dados do Django.

Este processo ocorre de forma totalmente assíncrona, garantindo que a aplicação principal não seja bloqueada por uma tarefa que pode ser demorada.

## Arquitetura e Features

*   **Comunicação Segura:** A comunicação entre serviços é protegida.
    *   **IA -> Django:** As chamadas para o backend Django são autenticadas usando um token de API de serviço (`DJANGO_API_TOKEN`).
    *   **Django -> IA:** As chamadas do Django para este serviço são autenticadas usando um token secreto compartilhado (`IA_SERVICE_SECRET_TOKEN`) no cabeçalho `X-Internal-Service-Token`, garantindo que apenas o backend possa acionar análises.
*   **Processamento 100% Assíncrono:** O gatilho no Django é disparado por uma tarefa **Celery**, tornando a resposta de upload para o usuário instantânea. O microserviço então assume o processamento em background.
*   **Tolerância a Falhas:** A comunicação entre o Django e o serviço de IA é resiliente. Se o microserviço estiver temporariamente indisponível, o Celery tentará reenviar o gatilho automaticamente (até 3 vezes por padrão), garantindo que nenhuma análise seja perdida por falhas transitórias.
*   **Dead Letter Queue:** Se uma tarefa falhar permanentemente (após todas as tentativas), seus detalhes são salvos automaticamente em uma "fila de tarefas falhas". Isso permite que administradores diagnostiquem o problema (bugs, erros de configuração) e reenfileirem a tarefa manualmente, garantindo que nenhuma requisição seja perdida.
*   **Proteção contra DoS (Rate Limiting):** O endpoint de análise é protegido contra picos de tráfego e abusos. O sistema limita o número de requisições por endereço IP, prevenindo que um bug ou ataque no sistema de origem sobrecarregue o serviço de IA ou gere custos excessivos.
*   **Validação de Configuração:** Na inicialização, o módulo (`config.js`) valida todas as variáveis de ambiente necessárias. O serviço não inicia se alguma variável crítica estiver ausente.
*   **Logging Estruturado:** Utiliza a biblioteca **Winston** (`logger.js`) para gerar logs. Em desenvolvimento, os logs são coloridos e de fácil leitura; em produção, são emitidos em formato **JSON** para fácil integração com sistemas de monitoramento.

## Configuração (`.env`)

As variáveis de ambiente são gerenciadas em um arquivo `.env` na raiz deste módulo.

```env
# --- Configurações do Serviço ---
# Porta em que o serviço Node.js irá rodar
IA_PORT=3002
# Ambiente de execução ('development' ou 'production')
NODE_ENV=development
# Nível de log a ser exibido (ex: 'info', 'warn', 'error')
LOG_LEVEL=info

# --- Credenciais (Obrigatório) ---
# Chave da API do Google para o Gemini
GOOGLE_API_KEY=SUA_CHAVE_DE_API_DO_GOOGLE
# Token de autenticação para a API do Django
DJANGO_API_TOKEN=SEU_TOKEN_GERADO_NO_DJANGO

# --- Conexões com Outros Serviços (Obrigatório) ---
# URL completa para a API do backend Django
DJANGO_API_URL=http://localhost:8000/api
```

### Obtendo o `DJANGO_API_TOKEN`

Este token é gerado no backend Django através de um comando de gerenciamento. Para criá-lo, execute o seguinte comando na raiz do projeto:

```bash
./.venv/bin/python backend/manage.py create_service_token --username ia_service --cpf "111.111.111-11" --first_name "Serviço" --last_name "IA"
```

## Fluxo de Execução (Gatilho)

1.  Um usuário faz o upload de um documento em algum lugar do sistema (ex: uma imagem em um Diário de Obra).
2.  A `ViewSet` do Django responsável por aquele upload salva o arquivo e enfileira uma tarefa Celery, passando o `documento_id` e um `tipo_analise` (ex: `'progresso_obra'`). A resposta para o usuário é imediata.
3.  O worker do Celery executa a tarefa, que faz uma requisição `POST` segura para o endpoint `/api/analise` deste microserviço.
4.  O microserviço de IA recebe a requisição, seleciona o prompt correto com base no `tipo_analise` e assume o controle do fluxo de análise.

## Instalação de Dependências

Para instalar as dependências do Node.js, navegue até o diretório do serviço e execute:

```bash
cd backend/funcoesia
npm install
```

## Scripts e Execução

### Execução em Modo de Desenvolvimento

Inicia o serviço com `nodemon`, que reinicia automaticamente após qualquer alteração no código.

```bash
# Dentro de backend/funcoesia/
npm run dev
```

### Execução em Produção

Inicia o serviço usando `node`. Para ambientes de produção, é altamente recomendado usar um gerenciador de processos como o `pm2` para garantir que o serviço reinicie automaticamente em caso de falhas.

```bash
# Dentro de backend/funcoesia/
npm start
```

### Execução de Testes

Roda todos os testes unitários com Jest (testes a serem implementados).

```bash
# Dentro de backend/funcoesia/
npm test
```
