# Sistema de Gestão Integrada - Backend

## ⚠️ Aviso de Segurança Crítico - Ação Necessária

**Foi identificada uma vulnerabilidade de segurança crítica em toda a aplicação. A correção é de alta prioridade.**

Atualmente, múltiplos endpoints da API estão configurados de forma insegura, o que pode levar a vazamentos de dados graves e acesso não autorizado. O problema se manifesta de duas formas:

1.  **Endpoints Completamente Abertos:** Vários `ViewSets` (como em `moduloerp` e outros) estão com a autenticação comentada ou ausente (`# permission_classes = [permissions.IsAuthenticated]`). Isso expõe dados sensíveis (financeiros, clientes, etc.) publicamente na API.
2.  **Falta de Validação de Permissão por Objeto:** Nos endpoints que possuem autenticação (`permissions.IsAuthenticated`), a validação atual apenas confirma que o usuário está logado. **Ela não verifica se o usuário tem permissão para acessar o recurso específico solicitado.** Isso significa que um usuário `A` pode visualizar ou modificar dados de um usuário `B` se souber o ID do objeto.

### Ação Requerida

É mandatório revisar **todos os módulos** da aplicação e garantir que:

- **Todos os `ViewSets` e `APIViews` tenham a classe de permissão `IsAuthenticated` (ou mais restritiva) ativa e configurada.**
- **As querysets sejam filtradas para garantir que os usuários só possam acessar dados pertencentes à sua organização ou contexto (ex: filtrar por `empreendimento` ou `usuario`).** Isso deve ser feito, preferencialmente, sobrescrevendo o método `get_queryset` em cada `ViewSet`.

---


Este é o backend do Sistema de Gestão Integrada, uma aplicação web desenvolvida em Django para gerenciar diversos processos de uma empresa.

## Estrutura de Pastas

```
sistema_gestao_integrada/
├── backend/
│   ├── clientes/
│   ├── config/
│   ├── empreendimentos/
│   ├── fornecedores/
│   ├── funcoesia/
│   ├── funcoeswhatsapp/
│   ├── locale/
│   ├── media/
│   ├── moduloaps/
│   ├── modulocrm/
│   ├── modulodiario/
│   ├── modulodms/
│   ├── moduloerp/
│   ├── moduloimpexp/
│   ├── modulomaps/
│   ├── modulopdca/
│   ├── modulorh/
│   ├── moduloscm/
│   ├── modulosil/
│   ├── nfe_xmls/
│   ├── nucleo/
│   ├── obras/
│   ├── rh/
│   ├── templates/
│   ├── .env
│   ├── Dockerfile
│   ├── manage.py
│   ├── Procfile
│   ├── requirements.txt
│   └── runmanage.sh
├── frontend/
│   └── ...
├── ...
└── docker-compose.txt
```

## Módulos

O backend é organizado em módulos, cada um responsável por uma área específica do sistema. **As APIs para os módulos listados abaixo foram implementadas usando Django REST Framework, com Serializers e ViewSets para operações CRUD.**

### Clientes (`clientes`)

Gerencia todas as informações relacionadas aos clientes.

*   **Modelos:**
    *   `Cliente`: Armazena dados cadastrais dos clientes (nome, CPF/CNPJ, contato, etc.).
    *   `ClienteEmpreendimento`: Vincula um cliente a um empreendimento específico, registrando a unidade comprada e detalhes da aquisição.
    *   `ContratoCliente`: Mantém os contratos firmados com os clientes.
    *   `DocumentoCliente`: Armazena documentos diversos dos clientes (RG, CPF, comprovante de residência, etc.).
    *   `DadoBancarioCliente`: Guarda as informações bancárias dos clientes para faturamento.
    *   `PagamentoCliente`: Registra os pagamentos efetuados pelos clientes.

### Empreendimentos (`empreendimentos`)

Gerencia os projetos e empreendimentos da empresa.

*   **Modelos:**
    *   `Empreendimento`: Contém as informações gerais de cada empreendimento (nome, CNPJ, endereço, status, etc.).
    *   `ContaBancariaEmpreendimento`: Armazena os dados bancários de cada empreendimento.
    *   `CustoEmpreendimento`: Registra os custos associados a cada empreendimento.
    *   `NotaFiscal`: Gerencia as notas fiscais recebidas de fornecedores.
*   **Endpoints:**
    *   `/api/empreendimentos/`: Lista todos os empreendimentos (acesso restrito a sócios e gerentes).

### Módulo ERP (`moduloerp`)

Planejamento de Recursos Empresariais (ERP) - **Financeiro e Faturamento**.

Este módulo foi aprimorado para gerenciar faturas, transações, emissão de Notas Fiscais e boletos.

*   **Modelos:**
    *   `Fatura`: Modelo central para contas a pagar e a receber.
    *   `Transacao`: Registra as transações financeiras (entradas e saídas).
    *   `NotaFiscalServico` / `NotaFiscalProduto`: Gerenciam os dados e status de Notas Fiscais de Serviço (NFS-e) e de Produto (NF-e).
    *   `ContaPagar` / `ContaReceber`: Registram as contas da empresa.
    *   `CobrancaCliente`: Registra as cobranças (parcelas) geradas para os clientes.
    *   `Boleto`: Representa um boleto bancário, que pode ser vinculado a uma `ContaPagar` (boletos recebidos) ou a uma `ContaReceber` (boletos emitidos).
*   **Endpoints:**
    *   `/api/erp/dashboard/`: Fornece dados para o dashboard financeiro.
    *   `/api/erp/faturas/`: CRUD para Faturas.
    *   `/api/erp/transacoes/`: CRUD para Transações.
    *   `/api/erp/contas-a-pagar/`: CRUD para Contas a Pagar.
    *   `/api/erp/contas-a-receber/`: CRUD para Contas a Receber.
    *   `/api/erp/boletos/`: CRUD para Boletos.
    *   `/api/erp/faturas/<id>/emitir-nfse/`: Aciona a emissão de uma NFS-e para uma fatura.

### Fornecedores (`fornecedores`)

Gerencia o cadastro de fornecedores e seus produtos/serviços.

*   **Modelos:**
    *   `Fornecedor`: Armazena os dados cadastrais dos fornecedores.
    *   `DadoBancarioFornecedor`: Guarda as informações bancárias dos fornecedores.
    *   `ProdutoServicoFornecedor`: Mantém um catálogo de produtos e serviços oferecidos pelos fornecedores.

### Funções de IA (`funcoesia`)

Módulo para integração com serviços de Inteligência Artificial.

*   **Modelos:**
    *   `AnaliseImagemIA`: Armazena o resultado da análise de imagens por uma IA.

### Funções WhatsApp (`funcoeswhatsapp`) - Node.js

**Nota de Arquitetura:** Conforme o plano de escalar o projeto, este módulo será implementado como um **microserviço em Node.js**, em vez de ser recriado em Django/Celery. Ele será responsável pela comunicação com a API do WhatsApp e pela lógica de conversação do bot.

O objetivo é permitir que funcionários interajam com o sistema através de um bot, começando com a funcionalidade de registrar o Diário de Obra.

*   **Endpoints (Planejados):**
    *   `/webhook`: Endpoint no serviço Node.js para receber mensagens da API da Meta.
*   **Documentação de Referência (v1):** Para uma análise completa do fluxo original (implementado em Django), consulte o arquivo [`funcoeswhatsapp/READMEFW.md`](./backend/funcoeswhatsapp/READMEFW.md).

### Microserviço de Emissão de Notas Fiscais (`funcoesnf`) - Node.js

**Nota de Arquitetura:** Este é um **microserviço em Node.js** dedicado à integração com APIs externas (como NFE.io) para a emissão de Notas Fiscais. Ele é acionado pelo backend Django e opera de forma assíncrona.

*   **Funcionalidade:** O fluxo de emissão funciona da seguinte forma:
    1.  O Django (através da `FaturaViewSet`) cria um registro de `NotaFiscalServico` ou `NotaFiscalProduto` no banco de dados com status `AGUARDANDO`.
    2.  O Django envia uma requisição para o microserviço `funcoesnf`, informando o `fatura_id` e o `nf_id`.
    3.  O microserviço busca os detalhes da fatura no Django, monta o payload para a API externa e **(atualmente em modo de simulação)** a chama.
    4.  Ao receber o resultado (sucesso ou erro), o microserviço faz um *callback* para o Django, que atualiza o status da nota fiscal e armazena os arquivos (PDF/XML) ou registra a falha.
*   **Documentação Detalhada:** Para informações completas sobre configuração, execução e endpoints deste microserviço, consulte o arquivo [`backend/funcoesnf/README.md`](./backend/funcoesnf/README.md).

## Endpoints da API

Os seguintes endpoints da API estão disponíveis no prefixo `/api/`:

*   **Clientes:**
    *   `/api/clientes/`
    *   `/api/clientes-empreendimentos/`
    *   `/api/contratos-clientes/`
    *   `/api/documentos-clientes/`
    *   `/api/dados-bancarios-clientes/`
*   **Empreendimentos:**
    *   `/api/empreendimentos/`
    *   `/api/contas-bancarias-empreendimentos/`
    *   `/api/custos-empreendimentos/`
*   **ERP / Financeiro:**
    *   `/api/erp/faturas/`
    *   `/api/erp/transacoes/`
    *   `/api/erp/notas-fiscais/`
    *   `/api/erp/contas-a-pagar/`
    *   `/api/erp/contas-a-receber/`
    *   `/api/erp/cobrancas-cliente/`
    *   `/api/erp/boletos/`
*   **Fornecedores:**
    *   `/api/fornecedores/`
    *   `/api/dados-bancarios-fornecedores/`
    *   `/api/produtos-servicos-fornecedores/`
*   **Núcleo:**
    *   `/api/usuarios/`
    *   `/api/perfis/`
    *   `/api/permissoes/`
    *   `/api/logs-atividade/`
*   **Obras:**
    *   `/api/obras/`
    *   `/api/etapas-obras/`
    *   `/api/documentos-obras/`
*   **RH:**
    *   `/api/cargos/`
    *   `/api/funcionarios/`
    *   `/api/dados-medicos-funcionarios/`
    *   `/api/documentos-funcionarios/`
    *   `/api/dados-bancarios-funcionarios/`
    *   `/api/pagamentos-funcionarios/`
    *   `/api/folhas-pagamento/`

## Tecnologias Utilizadas

*   **Framework:** Django
*   **API:** Django REST Framework, JWT for authentication
*   **Banco de Dados:** PostgreSQL
*   **Filas e Tarefas Assíncronas:** Celery, Redis
*   **Servidor de Aplicação:** Gunicorn
*   **Outras dependências:**
    *   `python-dotenv` para variáveis de ambiente
    *   `requests` para requisições HTTP
    *   `Pillow` para manipulação de imagens
    *   `pandas` e `openpyxl` para manipulação de planilhas
    *   `weasyprint` para geração de PDFs
*   **Planejado para o futuro:** Funções mais complexas serão implementadas em Node.js, em vez de Django, para microserviços ou tarefas específicas.

## Executando com Docker

1.  **Renomeie o arquivo `docker-compose.txt` para `docker-compose.yml`**

2.  **Configure as variáveis de ambiente:**
    Crie um arquivo `.env` na raiz do projeto (junto ao `docker-compose.yml`) e defina as variáveis necessárias. Consulte o arquivo `.env.example` para um modelo.

3.  **Suba os containers:**
    ```bash
    docker-compose up --build -d
    ```

4.  **Acesse a aplicação:**
    *   Frontend: `http://localhost`
    *   Backend: `http://localhost:8000`

## Configuração do Ambiente (Localmente)

1.  **Clone o repositório:**
    ```bash
    git clone <url-do-repositorio>
    cd sistema_gestao_integrada/backend
    ```

2.  **Crie e ative um ambiente virtual:**
    ```bash
    python -m venv venv
    source venv/bin/activate
    ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure as variáveis de ambiente:**
    Crie um arquivo `.env` na raiz do diretório `backend` (você pode usar o `.env.example` como base) e configure as seguintes variáveis:
    ```
    SECRET_KEY=sua-secret-key
    DEBUG=True
    DATABASE_URL=postgres://user:password@host:port/dbname
    REDIS_URL=redis://localhost:6379/0
    ```

5.  **Execute as migrações do banco de dados:**
    ```bash
    python manage.py migrate
    ```

## Executando a Aplicação (Localmente)

Para iniciar o servidor de desenvolvimento, execute:

```bash
python manage.py runserver
```

O servidor estará disponível em `http://127.0.0.1:8000`.