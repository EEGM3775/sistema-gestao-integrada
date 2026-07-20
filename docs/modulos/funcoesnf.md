# Microsserviço de Notas Fiscais (`funcoesnf`, Node)

> Comunicação com a API de emissão/consulta de NF (NFE.io hoje; Asaas como destino). Chamado pelo
> backend nas actions `emitir-nfse`/`emitir-nfe` de `ContaReceber`.
> Código: [backend/funcoesnf/](../../backend/funcoesnf/).
>
> ⚠️ O callback de status ao backend usa o token estático legado (pré-Fase 6) — achado **D1**, ver
> [../pendencias.md](../pendencias.md).

> **Provedor: NFE.io → Asaas (sandbox → real).** A emissão de NFS-e migra para o **Asaas** (recurso
> `invoices`), no **mesmo gateway** das cobranças. Por **AD-8** ([arquitetura.md §6](../arquitetura.md#6-estratégia-de-stack-tecnológica)),
> esse código novo é **Python** — reaproveita o `client.py` do [funcoescobrancas](funcoescobrancas.md) e
> entra como parte da **consolidação deste serviço Node em Python** (Fase 11), em vez de novo código Node
> num serviço em descontinuação. A NFE.io permanece neste serviço (Node) como provedor **legado** até a
> migração. Sandbox → real: ver [funcoescobrancas.md](funcoescobrancas.md). Plano de NF em
> [moduloerp.md §7](moduloerp.md#7-notas-fiscais--emitir--cancelar--ver).

## Arquitetura

O fluxo de trabalho é o seguinte:

1.  **Requisição Inicial (Django -> Node):** O backend Django recebe a ordem para emitir ou consultar uma NF. Ele faz uma requisição para este microserviço, enviando os dados necessários (ID da fatura, ID da nota fiscal, etc.).

2.  **Processamento (Node):**
    *   Este serviço recebe a requisição.
    *   Ele busca os dados completos (cliente, serviços/produtos) no Django, se necessário.
    *   Ele monta o payload no formato exigido pela API da NFE.io.
    *   Ele envia a requisição para a NFE.io (emissão ou consulta) e aguarda a resposta.

3.  **Callback (Node -> Django):**
    *   Após receber a resposta da NFE.io, este serviço faz uma requisição de volta (callback) para o Django.
    *   Ele informa o novo status (`EMITIDA`, `ERRO`, `PROCESSANDO`, `CANCELADA`), os dados de retorno da API (como a chave de acesso) e os links para o PDF e XML da nota.

4.  **Finalização (Django):** O Django atualiza o registro da nota fiscal no banco de dados com as informações recebidas.

## Funções

O serviço é dividido nos seguintes arquivos:

-   `index.js`: Ponto de entrada da aplicação. Inicia o servidor Express e define as rotas.
-   `emitirNF.js`: Contém a lógica principal para se comunicar com a API de emissão.
-   `armazenarNF.js`: Responsável por fazer o callback para o Django, atualizando o status e enviando os arquivos.
-   `consultarNF.js`: Contém a lógica para consultar o status de notas fiscais já emitidas na NFE.io.
-   `cancelarNF.js`: (Futuro) Lógica para cancelar notas.
-   `config.js`: Arquivo de configuração (URLs de API, etc.).
-   `logger.js`: Módulo para registro de logs.

## Endpoints da API (Expostos pelo Microserviço)

Este microserviço expõe os seguintes endpoints para comunicação com o backend Django:

-   **`POST /api/emitir-nfse`**: Inicia o processo de emissão de uma Nota Fiscal de Serviço (NFS-e).
    *   **Payload esperado:** `{ "fatura_id": <int>, "nf_id": <int> }`
-   **`POST /api/emitir-nfe`**: Inicia o processo de emissão de uma Nota Fiscal de Produto (NF-e). (Em desenvolvimento)
    *   **Payload esperado:** `{ "fatura_id": <int>, "nf_id": <int> }`
-   **`POST /api/consultar-nf`**: Consulta o status de uma Nota Fiscal de Serviço já emitida na NFE.io.
    *   **Payload esperado:** `{ "nf_id": <int>, "invoice_id": "<string_id_nfeio>" }`

## Variáveis de Ambiente

As credenciais da NFE.io e a URL da API do Django são carregadas de variáveis de ambiente para garantir a segurança e flexibilidade em diferentes ambientes (desenvolvimento, produção).

Crie um arquivo `.env` na raiz da pasta `funcoesnf` (ou defina as variáveis diretamente no seu ambiente de produção) com as seguintes variáveis:

```
DJANGO_API_URL=http://localhost:8000/api/erp
# Provedor NFE.io (legado/alternativo) — específico deste serviço Node
NFE_IO_API_KEY=SUA_CHAVE_DE_API_AQUI
NFE_IO_COMPANY_ID=SEU_ID_DA_EMPRESA_AQUI
```

**Importante:** Substitua `SUA_CHAVE_DE_API_AQUI` e `SEU_ID_DA_EMPRESA_AQUI` pelos valores reais fornecidos pela NFE.io. As credenciais do **Asaas** (`ASAAS_BASE_URL`/`ASAAS_API_KEY`/`ASAAS_WEBHOOK_TOKEN`) **não** ficam aqui — vivem no **Django settings** (lado Python), em [funcoescobrancas](funcoescobrancas.md), já que a emissão via Asaas é Python.

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
