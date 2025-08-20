# Microserviço de Notas Fiscais (`funcoesnf`)

Este microserviço em Node.js é responsável por toda a comunicação com a API de emissão de Notas Fiscais (ex: NFE.io). Ele é projetado para ser chamado pelo backend principal do Django.

## Arquitetura

O fluxo de trabalho é o seguinte:

1.  **Requisição Inicial (Django -> Node):** O backend Django recebe a ordem para emitir uma NF. Ele cria um registro da nota no banco de dados com status `AGUARDANDO` e faz uma requisição para este microserviço, enviando o ID da fatura e o ID da nota fiscal recém-criada.

2.  **Processamento (Node):**
    *   Este serviço recebe a requisição.
    *   (A ser implementado) Ele usa o ID da fatura para buscar os dados completos (cliente, serviços/produtos) no Django.
    *   (A ser implementado) Ele monta o payload no formato exigido pela API da NFE.io.
    *   (A ser implementado) Ele envia a requisição para a NFE.io e aguarda a resposta.

3.  **Callback (Node -> Django):**
    *   Após receber a resposta da NFE.io, este serviço faz uma requisição de volta (callback) para o Django.
    *   Ele informa o novo status (`EMITIDA` ou `ERRO`), os dados de retorno da API (como a chave de acesso) e os links para o PDF e XML da nota.

4.  **Finalização (Django):** O Django atualiza o registro da nota fiscal no banco de dados com as informações recebidas.

## Funções

O serviço é dividido nos seguintes arquivos:

-   `index.js`: Ponto de entrada da aplicação. Inicia o servidor Express e define as rotas.
-   `emitirNF.js`: Contém a lógica principal para se comunicar com a API de emissão.
-   `armazenarNF.js`: Responsável por fazer o callback para o Django, atualizando o status e enviando os arquivos.
-   `consultarNF.js`: (Futuro) Lógica para consultar notas já emitidas.
-   `cancelarNF.js`: (Futuro) Lógica para cancelar notas.
-   `config.js`: Arquivo de configuração (URLs de API, etc.).

## Variáveis de Ambiente

As credenciais da NFE.io e a URL da API do Django são carregadas de variáveis de ambiente para garantir a segurança e flexibilidade em diferentes ambientes (desenvolvimento, produção).

Crie um arquivo `.env` na raiz da pasta `funcoesnf` (ou defina as variáveis diretamente no seu ambiente de produção) com as seguintes variáveis:

```
DJANGO_API_URL=http://localhost:8000/api/erp
NFE_IO_API_KEY=SUA_CHAVE_DE_API_AQUI
NFE_IO_COMPANY_ID=SEU_ID_DA_EMPRESA_AQUI
```

**Importante:** Substitua `SUA_CHAVE_DE_API_AQUI` e `SEU_ID_DA_EMPRESA_AQUI` pelos valores reais fornecidos pela NFE.io.

## Como Executar

1.  **Navegue até a pasta do serviço:**
    ```bash
    cd backend/funcoesnf
    ```

2.  **Instale as dependências:**
    ```bash
    npm install
    ```

3.  **Inicie o serviço em modo de desenvolvimento (com auto-reload):**
    ```bash
    npm run dev
    ```

4.  **Para produção:**
    ```bash
    npm start
    ```

O serviço rodará na porta `3002` por padrão.
