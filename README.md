# Sistema de Gestão Integrada - Backend

Este é o backend do Sistema de Gestão Integrada, uma aplicação web desenvolvida em Django para gerenciar diversos processos de uma empresa.

## Estrutura de Pastas

```
sistema_gestao_integrada/
├── backend/
│   ├── clientes/
│   ├── config/
│   ├── empreendimentos/
│   ├── financeiro/
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

### Financeiro (`financeiro`)

Controla as contas a pagar e a receber da empresa.

*   **Modelos:**
    *   `NotaFiscal`: Armazena as informações das notas fiscais recebidas de fornecedores.
    *   `ContaPagar`: Registra as contas a serem pagas a fornecedores.
    *   `ContaReceber`: Registra os valores a serem recebidos de clientes.
    *   `CobrancaCliente`: Registra as cobranças (boletos, parcelas) geradas para os clientes.

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

### Módulo APS (`moduloaps`)

Integração com a plataforma Autodesk Platform Services (APS).

*   **Modelos:**
    *   `APSModel`: Armazena os modelos (plantas/desenhos) do APS associados a uma obra.
*   **Endpoints:**
    *   `/api/aps/token/`: Gera um token de acesso para a API da Autodesk.
    *   `/api/aps/obras/<int:obra_id>/plantas/`: Lista as plantas de uma obra específica.

### Módulo CRM (`modulocrm`)

Gerenciamento de Relacionamento com o Cliente (CRM).

*   **Modelos:**
    *   `Oportunidade`: Representa uma oportunidade de negócio (lead) em um funil de vendas.
    *   `Interacao`: Registra os pontos de contato com o cliente em uma oportunidade.
*   **Endpoints:**
    *   `/api/crm/oportunidades/`: CRUD completo para oportunidades.
    *   `/api/crm/dashboard/`: Fornece dados agregados para o dashboard de CRM.

### Módulo Diário de Obra (`modulodiario`)

Registro diário do andamento das obras.

*   **Modelos:**
    *   `DiarioObra`: Armazena os registros diários da obra, com descrições e tags.
    *   `DocumentoDiario`: Guarda os arquivos de mídia (fotos, vídeos, etc.) associados a um registro do diário.
*   **Endpoints:**
    *   `/api/diario/diarios/`: CRUD para os diários de obra.
    *   `/api/diario/documentos/`: CRUD para os documentos do diário.

### Módulo DMS (`modulodms`)

Sistema de Gerenciamento de Documentos (DMS).

*   **Modelos:**
    *   `Documento`: Representa um documento principal, contendo suas versões.
    *   `VersaoDocumento`: Armazena uma versão específica de um documento.
*   **Endpoints:**
    *   `/api/dms/documentos/`: Lista e cria novos documentos.
    *   `/api/dms/documentos/<int:pk>/`: Detalhes, atualização e exclusão de um documento.

### Módulo ERP (`moduloerp`)

Planejamento de Recursos Empresariais (ERP).

*   **Modelos:**
    *   `Fatura`: Modelo central para contas a pagar e a receber.
    *   `Transacao`: Registra as transações financeiras (entradas e saídas).
    *   `Contrato`: Repositório central para todos os contratos da empresa.
*   **Endpoints:**
    *   `/api/erp/dashboard/`: Fornece dados para o dashboard financeiro (aging report, fluxo de caixa).

### Módulo de Importação/Exportação (`moduloimpexp`)

Funcionalidades para importar e exportar dados do sistema.

*   **Modelos:**
    *   `ExportedFile`: Rastreia os arquivos exportados.
*   **Endpoints:**
    *   `/api/impexp/export/`: Inicia uma tarefa de exportação.
    *   `/api/impexp/import/`: Inicia uma tarefa de importação.
    *   `/api/impexp/task-status/<str:task_id>/`: Verifica o status de uma tarefa.

### Módulo de Mapas (`modulomaps`)

Funcionalidades de mapa interativo.

*   **Modelos:**
    *   `MapObra`: Representa um mapa de uma obra.
    *   `MapFornecedor`, `MapEstoque`, `MapInformativo`: Marcadores no mapa.
*   **Endpoints:**
    *   `/api/maps/obras/<int:obra_id>/details/`: Detalhes do mapa de uma obra.

### Módulo PDCA (`modulopdca`)

Ciclo Plan-Do-Check-Act para gestão de projetos.

*   **Modelos:**
    *   `Tarefa`: Tarefas específicas de uma etapa da obra.
    *   `Marco`: Marcos importantes do projeto.
    *   `Risco`: Riscos do projeto.
*   **Endpoints:**
    *   `/api/pdca/kpis/`: Retorna KPIs (Key Performance Indicators) do projeto.
    *   `/api/pdca/riscos/`: Lista os riscos do projeto.
    *   `/api/pdca/alertas/`: Lista tarefas que precisam de atenção.

### Módulo RH (`modulorh`)

Gerenciamento de Recursos Humanos.

*   **Modelos:**
    *   `FolhaPagamento`: Registra os pagamentos dos funcionários.
    *   `AvaliacaoDesempenho`: Armazena as avaliações de desempenho dos funcionários.
*   **Endpoints:**
    *   `/api/rh/dashboard/`: Dados para o dashboard de RH.

### Módulo SCM (`moduloscm`)

Gerenciamento da Cadeia de Suprimentos (SCM).

*   **Modelos:**
    *   `PedidoCompra`: Pedidos de compra de materiais e serviços.
    *   `ItemPedido`: Itens de um pedido de compra.
    *   `AvaliacaoFornecedor`: Avaliações de desempenho dos fornecedores.
*   **Endpoints:**
    *   `/api/scm/dashboard/`: Dados para o dashboard de SCM.

### Módulo SIL (`modulosil`)

Sistema de Informação Logística (SIL).

*   **Modelos:**
    *   `ItemCatalogo`: Catálogo de todos os itens de estoque.
    *   `Estoque`: Locais de armazenamento de estoque.
    *   `ItemEstoque`: Quantidade de um item em um local de estoque.
    *   `MovimentacaoEstoque`: Histórico de movimentações de estoque.
*   **Endpoints:**
    *   `/api/sil/dashboard/`: Dados para o dashboard de estoque.

### Núcleo (`nucleo`)

Funcionalidades centrais do sistema.

*   **Modelos:**
    *   `Usuario`: Modelo de usuário customizado.
    *   `Perfil`, `Permissao`, `PerfisPermissoes`: Controle de acesso baseado em perfis e permissões.
    *   `LogAtividadeUsuario`: Registra as ações dos usuários no sistema.
*   **Endpoints:**
    *   `/api/nucleo/empreendimentos/`: Lista todos os empreendimentos.
    *   `/api/nucleo/obras/<int:obra_id>/diarios/`: Lista os diários de uma obra.

### Obras (`obras`)

Gerenciamento de obras.

*   **Modelos:**
    *   `Obra`: Informações gerais da obra.
    *   `EtapaObra`: Etapas de uma obra.
    *   `DocumentoObra`: Documentos de uma obra.
*   **Endpoints:**
    *   `/api/obras/diarios-por-empreendimento/<int:empreendimento_id>/`: Diários de um empreendimento.
    *   `/api/obras/obras/`: Lista de obras de um empreendimento.
    *   `/api/obras/obras/<int:pk>/`: Detalhes de uma obra.
    *   `/api/obras/documentos/`: Criação de documentos de uma obra.

### RH (`rh`)

Gerenciamento de Recursos Humanos (dados cadastrais).

*   **Modelos:**
    *   `Cargo`: Cargos da empresa.
    *   `Funcionario`: Dados dos funcionários.
    *   `DadoMedicoFuncionario`: Dados médicos dos funcionários.
    *   `DocumentoFuncionario`: Documentos dos funcionários.
    *   `DadoBancarioFuncionario`: Dados bancários dos funcionários.
    *   `PagamentoFuncionario`: Pagamentos dos funcionários.
    *   `FolhaPagamento`: Folhas de pagamento dos funcionários.

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
*   **Financeiro:**
    *   `/api/notas-fiscais/`
    *   `/api/contas-a-pagar/`
    *   `/api/contas-a-receber/`
    *   `/api/cobrancas-clientes/`
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