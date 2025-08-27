# App Núcleo - Gestão de Autenticação e Serviços

O app `nucleo` é responsável pelos modelos centrais do sistema, incluindo `Usuario`, `Perfil` e `Permissao`. Além disso, ele contém ferramentas para gerenciar a autenticação de serviços internos e garantir a robustez de tarefas assíncronas.

## Autenticação de Microserviços (Machine-to-Machine)

Para garantir a comunicação segura entre o backend principal do Django e outros serviços (como o microserviço de WhatsApp em Node.js), utilizamos um sistema de autenticação baseado em tokens de API estáticos.

Um usuário de serviço dedicado é criado no Django, e um token de longa duração é gerado e associado a ele. O microserviço, então, utiliza este token para se autenticar em todas as chamadas que faz para a API do Django.

### Gerando um Token de Serviço

Para criar um usuário de serviço (se ele não existir) e gerar seu token, utilize o comando de gerenciamento `create_service_token`. Ele foi projetado para ser uma ferramenta reutilizável para qualquer serviço interno.

**Exemplo de Uso:**

Suponha que você precise criar um token para um novo **"Serviço de Notificações"**.

```bash
./.venv/bin/python backend/manage.py create_service_token \
  --username notificacao_service \
  --cpf "000.000.000-01" \
  --first_name "Serviço" \
  --last_name "Notificações"
```

**Argumentos do Comando:**

*   `--username`: O nome de usuário único para o serviço.
*   `--cpf`: Um CPF placeholder único para o registro do usuário.
*   `--first_name`, `--last_name`: Nomes descritivos para o serviço.

**O que o comando faz:**

1.  Cria um usuário de serviço com os dados fornecidos.
2.  Define uma senha inutilizável para que o login via formulário seja impossível.
3.  Gera um token de API de longa duração para este usuário.
4.  Exibe o token no console.

**Ação Necessária (Passo 1): Configurar o Token**

Após executar o comando, copie o token exibido e adicione-o ao arquivo `.env` do microserviço correspondente.

**Ação Necessária (Passo 2): Configurar Permissões (Crucial!)**

Um token recém-criado não possui permissões específicas. Para seguir o **Princípio do Menor Privilégio**, você deve:

1.  Acessar a **Área Administrativa do Django**.
2.  Criar um novo **Perfil** (ex: "Perfil Serviço de Notificações").
3.  Atribuir a este perfil o **mínimo de permissões** que o serviço precisa para funcionar.
4.  Editar o usuário de serviço recém-criado (ex: `notificacao_service`) e **associá-lo a este novo perfil restrito**.

### Ciclo de Vida e Rotação do Token (Atualização)

O token gerado **não expira automaticamente**. Para rotacionar (invalidar o antigo e gerar um novo) um token, o processo é o mesmo:

1.  **Delete o token antigo** usando o `manage.py shell` (veja o código detalhado na seção anterior, lembrando de alterar o `username`).
2.  **Execute o comando `create_service_token` novamente** com os mesmos argumentos para gerar um novo token para o mesmo usuário.
3.  **Atualize o arquivo `.env`** do microserviço com o novo token.
4.  **Reinicie o microserviço**.

---

## Dead Letter Queue (Fila de Tarefas Falhas)

Para garantir a robustez do sistema e evitar a perda de tarefas assíncronas, o módulo `nucleo` implementa um mecanismo de Dead Letter Queue (DLQ) através do modelo `FailedTask`.

Este modelo armazena informações detalhadas sobre qualquer tarefa Celery que falhe permanentemente (após esgotar todas as suas tentativas de reexecução).

### Funcionamento

1.  **Tarefa Falha:** Uma tarefa crítica em outro módulo (ex: `modulodiario.tasks.disparar_analise_ia`) é configurada com um número máximo de retentativas.
2.  **Captura:** Se a tarefa falhar em todas as tentativas, ela chama automaticamente o handler de falhas `nucleo.tasks.handle_failed_task`.
3.  **Registro:** Este handler popula o modelo `FailedTask` com todos os detalhes da falha: nome da tarefa, argumentos, exceção e traceback completo.

### Benefícios

Isso permite que administradores e desenvolvedores:

*   Diagnostiquem a causa raiz de falhas permanentes através da interface do **Django Admin**, na seção "Tarefas Falhas".
*   Evitem a perda de solicitações assíncronas importantes.
*   Reprocessem tarefas manualmente (se aplicável) após a correção do problema subjacente.

### Considerações de Segurança (Importante)

O mecanismo de DLQ armazena os argumentos (`args` e `kwargs`) da tarefa que falhou. Se uma tarefa for projetada para receber dados sensíveis (tokens de acesso, informações de cartão de crédito, dados pessoais) diretamente em seus argumentos, **esses dados serão salvos em texto plano no banco de dados** em caso de falha permanente.

**Diretriz de Desenvolvimento:**

Para mitigar este risco, todas as tarefas Celery devem seguir o padrão de **passar identificadores, não dados brutos**.

*   **Incorreto:** `processar_pagamento.delay(numero_cartao="...", cvv="...")`
*   **Correto:** `processar_pagamento.delay(pagamento_id=456)`

A tarefa, ao ser executada, deve usar o `pagamento_id` para buscar os dados sensíveis diretamente do banco de dados de forma segura. Isso garante que, se a tarefa falhar, apenas o ID não-sensível será registrado na Dead Letter Queue.

## Log de Atividade Centralizado

O módulo `nucleo` agora oferece um sistema de log de atividades centralizado, permitindo o registro de ações importantes tanto de tarefas assíncronas do Celery quanto de microserviços externos. Todos os logs são armazenados no modelo `LogAtividadeUsuario`.

### 1. Log de Tarefas Celery

As tarefas Celery são automaticamente logadas através de sinais (signals) do Celery.

*   **Início da Tarefa:** Quando uma tarefa Celery começa a ser executada, um registro de "Início da tarefa" é criado no `LogAtividadeUsuario`.
*   **Fim da Tarefa:** Ao finalizar (com sucesso ou falha), o registro inicial é atualizado com o status final da tarefa.

Para associar uma tarefa a um usuário específico, é **altamente recomendado** que o `user_id` seja passado como um argumento `kwargs` ao chamar a tarefa:

```python
from myapp.tasks import my_celery_task

# Exemplo de chamada de tarefa com user_id
my_celery_task.delay(arg1, arg2, user_id=request.user.id)
```

### 2. Log de Microserviços Externos

Microserviços (como o `funcoesnf` em Node.js) podem enviar seus logs de atividade para o backend Django através de um endpoint dedicado.

*   **Endpoint:** `POST /api/log-interno/`
*   **Corpo da Requisição (JSON):**
    ```json
    {
        "acao": "Descrição da ação realizada",
        "entidade_alvo": "Nome do serviço ou componente (ex: 'funcoesnf')",
        "detalhes": {
            "chave1": "valor1",
            "chave2": "valor2"
        },
        "user_id": 123 // Opcional: ID do usuário associado à ação
    }
    ```
*   **Exemplo de Uso (Node.js com `axios`):**
    ```javascript
    const axios = require('axios');

    async function logToDjango(acao, entidade_alvo, detalhes, user_id = null) {
        try {
            await axios.post('http://localhost:8000/api/log-interno/', {
                acao,
                entidade_alvo,
                detalhes,
                user_id,
            });
            console.log('Log enviado com sucesso para o Django.');
        } catch (error) {
            console.error('Falha ao enviar log para o Django:', error.message);
        }
    }

    // Exemplo de chamada
    logToDjango('Emissão de NF-e', 'funcoesnf', { faturaId: 123, nfId: 456 }, 789);
    ```

**Considerações de Segurança:**

O endpoint `/api/log-interno/` atualmente permite requisições de qualquer origem (`AllowAny` na configuração de desenvolvimento). Em um ambiente de produção, é **fundamental** implementar medidas de segurança mais robustas, como:

*   **Autenticação de Serviço:** Utilizar tokens de API ou chaves pré-compartilhadas para autenticar os microserviços que enviam logs.
*   **Restrição de Rede:** Limitar o acesso ao endpoint apenas para IPs ou redes internas confiáveis.
