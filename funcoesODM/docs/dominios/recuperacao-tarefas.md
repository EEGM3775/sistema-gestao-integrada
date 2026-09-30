# Recuperação de Tarefas Interrompidas

## Problema

Quando o Docker ou o computador é desligado durante o processamento de imagens, o thread `CompletableFuture` que executa o polling é destruído junto com a JVM. O banco de dados não é atualizado — o chunk fica congelado no status `RUNNING` com a porcentagem em que estava. O resultado:

- O usuário abre o app e vê o chunk travado (ex.: 39%) para sempre
- Nenhuma mensagem de erro é exibida
- Nenhuma ação é oferecida
- O badge de notificações ficava hardcoded em "3"

---

## Solução Implementada

A correção atua em três camadas:

| Camada | O que faz |
|--------|-----------|
| Backend — `ChunkRecoveryService` | Detecta chunks travados ao subir o servidor e os marca como FAILED com motivo |
| Backend — endpoint `/retry` | Permite reiniciar um chunk com falha usando as mesmas opções salvas |
| Frontend | Exibe o erro no chunk, mostra botão de retry e atualiza o badge dinamicamente |

---

## Backend

### 1. `ChunkRepository` — nova query

**Arquivo:** [ChunkRepository.java](../../backend/java-service/src/main/java/com/funcoesodm/javaservice/repository/ChunkRepository.java)

Adicionada query para buscar chunks em múltiplos status ao mesmo tempo:

```java
@Query("SELECT c FROM Chunk c JOIN FETCH c.project WHERE c.status IN :statuses ORDER BY c.createdAt ASC")
List<Chunk> findByStatusIn(@Param("statuses") List<Chunk.ChunkStatus> statuses);
```

O `JOIN FETCH c.project` garante que o projeto já vem carregado (evita N+1 e `LazyInitializationException` fora de transação).

---

### 2. `ChunkRecoveryService` — detecção no startup

**Arquivo:** [ChunkRecoveryService.java](../../backend/java-service/src/main/java/com/funcoesodm/javaservice/service/ChunkRecoveryService.java)

Roda uma única vez logo após o contexto Spring estar pronto, via `@EventListener(ApplicationReadyEvent.class)`.

**Fluxo de decisão por chunk:**

```
findByStatusIn([RUNNING, QUEUED])
        |
        +-- nodeodmTaskId == null (chunk QUEUED antes de enviar ao ODM)
        |       --> FAILED("Servidor desligado antes do início. Clique em 'Tentar Novamente'.")
        |
        +-- nodeodmTaskId != null (chunk estava RUNNING)
                |
                +-- GET /task/{id}/info no NodeODM
                        |
                        +-- RUNNING / QUEUED  --> resumePolling() (retoma sem reiniciar)
                        +-- COMPLETED         --> finalizeCompletedChunk() (salva assets)
                        +-- FAILED            --> FAILED(mensagem do ODM)
                        +-- Erro / 404        --> FAILED("Servidor reiniciado durante processamento (estava em X%). Clique em 'Tentar Novamente'.")
```

Após marcar como FAILED, o serviço envia um `sendChunkFailed()` via WebSocket para que qualquer frontend conectado atualize a UI em tempo real.

**Código:**

```java
@EventListener(ApplicationReadyEvent.class)
public void recoverInterruptedChunks() {
    List<Chunk> stuck = chunkRepository.findByStatusIn(
        List.of(Chunk.ChunkStatus.RUNNING, Chunk.ChunkStatus.QUEUED)
    );
    for (Chunk chunk : stuck) {
        recoverChunk(chunk);
    }
}
```

---

### 3. `ChunkService` — três métodos novos

**Arquivo:** [ChunkService.java](../../backend/java-service/src/main/java/com/funcoesodm/javaservice/service/ChunkService.java)

#### `retryChunk(projectId, chunkId)`

Reinicia um chunk com falha. Reutiliza as opções de processamento já salvas em `chunk.processingOptions` (JSON), evitando que o usuário precise reconfigurar tudo.

```java
public ChunkDto retryChunk(Long projectId, Long chunkId) {
    // valida: status deve ser FAILED ou CANCELED, imageCount >= 3
    // lê opções salvas de chunk.processingOptions
    // reseta: status=QUEUED, progress=0, errorMessage=null, nodeodmTaskId=null
    // salva e relança startChunkProcessingAsync()
}
```

#### `resumePolling(chunkId, projectId, nodeodmTaskId)`

Chamado pelo `ChunkRecoveryService` quando o NodeODM ainda está processando a tarefa. Relança um `CompletableFuture` conectando ao `nodeodmTaskId` existente — sem reenviar as imagens.

#### `finalizeCompletedChunk(chunkId, projectId, nodeodmTaskId)`

Chamado quando o NodeODM completou o processamento enquanto o servidor Java estava offline. Busca os assets disponíveis e completa o chunk normalmente.

---

### 4. `ChunkController` — endpoint de retry

**Arquivo:** [ChunkController.java](../../backend/java-service/src/main/java/com/funcoesodm/javaservice/controller/ChunkController.java)

```
POST /api/v1/projects/{projectId}/chunks/{chunkId}/retry
```

Retorna o `ChunkDto` com `status: QUEUED` imediatamente. O processamento ocorre em background; atualizações chegam via WebSocket.

Resposta de erro (400) se o chunk não estiver em FAILED/CANCELED ou tiver menos de 3 imagens.

---

## Frontend

### 5. `chunk.service.ts` — signal de contagem e método de retry

**Arquivo:** [chunk.service.ts](../../frontend/src/app/features/projects/services/chunk.service.ts)

**Signal `failedChunksCount`:**

```typescript
private failedCountSignal = signal(0);
failedChunksCount = this.failedCountSignal.asReadonly();
```

Atualizado em dois momentos:
- Em `getChunks()` — ao carregar a lista do servidor
- Em `updateChunkInState()` — quando qualquer chunk muda de status (via WebSocket ou retry)

**Método `retryChunk()`:**

```typescript
retryChunk(projectId: number, chunkId: number): Observable<Chunk> {
  return this.http.post<Chunk>(`${this.apiUrl}/${projectId}/chunks/${chunkId}/retry`, {}).pipe(
    tap(updated => this.updateChunkInState(updated))
  );
}
```

---

### 6. `project-workspace.component.ts` — auto-polling e retry

**Arquivo:** [project-workspace.component.ts](../../frontend/src/app/features/projects/project-workspace/project-workspace.component.ts)

**Auto-polling ao carregar:**

Antes da correção, `pollChunkStatus()` só era chamado quando o usuário clicava em "Processar". Agora, ao carregar o projeto, chunks em `RUNNING` ou `QUEUED` já ativam o polling automaticamente:

```typescript
chunks.filter(c => c.status === 'RUNNING' || c.status === 'QUEUED')
      .forEach(c => this.pollChunkStatus(c.id));
```

Isso garante que se o servidor recuperou o chunk para RUNNING (ODM ainda estava ativo), o frontend começa a mostrar o progresso sem nenhuma ação do usuário.

**Método `retryChunk()` e controle de loading:**

```typescript
retryingChunkIds = new Set<number>();

retryChunk(chunk: Chunk): void {
    // adiciona ID ao Set (desabilita o botão)
    this.chunkService.retryChunk(project.id, chunk.id).subscribe({
        next: (updated) => {
            // atualiza estado local, inicia pollChunkStatus, vai para aba de resultados
        },
        error: () => { /* remove ID do Set */ }
    });
}

isRetrying(chunkId: number): boolean {
    return this.retryingChunkIds.has(chunkId);
}
```

---

### 7. `project-workspace.component.html` — UI de erro no chunk-item

**Arquivo:** [project-workspace.component.html](../../frontend/src/app/features/projects/project-workspace/project-workspace.component.html)

No item do chunk na sidebar esquerda, quando `status === 'FAILED'`:

- A mensagem de erro (`chunk.errorMessage`) aparece em vermelho abaixo do nome
- O botão `↺` vermelho aciona `retryChunk()` sem propagar o clique para `selectChunk()`
- O botão fica desabilitado e mostra `...` enquanto o retry está em andamento

```html
@if (chunk.status === 'FAILED' && chunk.errorMessage) {
  <span class="chunk-error-msg" [title]="chunk.errorMessage">
    {{ chunk.errorMessage }}
  </span>
}

@if (chunk.status === 'FAILED') {
  <button
    class="btn-retry-chunk"
    [disabled]="isRetrying(chunk.id)"
    (click)="$event.stopPropagation(); retryChunk(chunk)"
    title="Tentar novamente"
  >{{ isRetrying(chunk.id) ? '...' : '↺' }}</button>
}
```

**Arquivo de estilos:** [project-workspace.component.scss](../../frontend/src/app/features/projects/project-workspace/project-workspace.component.scss)

- `.chunk-error-msg` — texto vermelho (#f85149), 10px, truncado com reticências se muito longo
- `.btn-retry-chunk` — borda vermelha, fundo transparente com hover sutil, desabilitado quando reprocessando
- `.chunk-item.failed .btn-chunk-menu` — menu de opções sempre visível em chunks com falha

---

### 8. `dashboard-layout.component.ts` — badge dinâmico

**Arquivo:** [dashboard-layout.component.ts](../../frontend/src/app/features/dashboard/dashboard-layout/dashboard-layout.component.ts)

O badge de notificações que estava hardcoded em "3" agora é dinâmico:

```typescript
readonly chunkService = inject(ChunkService);
```

```html
@if (chunkService.failedChunksCount() > 0) {
  <span class="notification-badge">{{ chunkService.failedChunksCount() }}</span>
}
```

O badge some completamente quando não há chunks com falha, e aparece com o número correto quando há.

---

## Fluxo Completo Após a Correção

```
DOCKER REINICIA
      |
      v
ApplicationReadyEvent dispara
      |
      v
ChunkRecoveryService.recoverInterruptedChunks()
      |
      +-- Chunk 2 estava RUNNING (nodeodmTaskId existe)
      |       |
      |       +-- GET /task/{id}/info --> 404 (NodeODM também reiniciou)
      |       |
      |       v
      |   chunk.status = FAILED
      |   chunk.errorMessage = "Servidor reiniciado durante processamento (estava em 39%).
      |                         Clique em 'Tentar Novamente'."
      |       |
      |       v
      |   webSocketService.sendChunkFailed(projectId, chunkId, errorMessage)


USUÁRIO ABRE O PROJETO
      |
      v
GET /api/v1/projects/{id}/chunks
      |
      v
Chunk 2 retorna com status=FAILED, errorMessage="..."
      |
      +-- failedChunksCount signal atualiza para 1
      |   --> Badge do sino mostra "1"
      |
      +-- chunk-item exibe:
          - Icone 🔴
          - Nome "Chunk 2"
          - Mensagem de erro em vermelho (truncada)
          - Botão ↺ vermelho


USUÁRIO CLICA ↺
      |
      v
POST /api/v1/projects/{id}/chunks/{id}/retry
      |
      v
Backend:
  - Le opcoes salvas em chunk.processingOptions
  - Reset: status=QUEUED, progress=0, errorMessage=null, nodeodmTaskId=null
  - Relanca startChunkProcessingAsync()
      |
      v
Frontend recebe ChunkDto com status=QUEUED
  - Botao volta ao normal
  - pollChunkStatus() inicia (HTTP a cada 5s)
  - Aba muda para "Resultados"
      |
      v
WebSocket envia atualizacoes em tempo real (0% -> 39% -> ... -> 100%)
      |
      v
Badge some quando chunk.status = COMPLETED
```

---

## Arquivos Modificados

### Backend

| Arquivo | Tipo | Mudança |
|---------|------|---------|
| [ChunkRepository.java](../../backend/java-service/src/main/java/com/funcoesodm/javaservice/repository/ChunkRepository.java) | Modificado | Query `findByStatusIn` com JOIN FETCH |
| [ChunkRecoveryService.java](../../backend/java-service/src/main/java/com/funcoesodm/javaservice/service/ChunkRecoveryService.java) | **Criado** | Listener de startup para chunks travados |
| [ChunkService.java](../../backend/java-service/src/main/java/com/funcoesodm/javaservice/service/ChunkService.java) | Modificado | `retryChunk()`, `resumePolling()`, `finalizeCompletedChunk()` |
| [ChunkController.java](../../backend/java-service/src/main/java/com/funcoesodm/javaservice/controller/ChunkController.java) | Modificado | Endpoint `POST .../retry` |

### Frontend

| Arquivo | Tipo | Mudança |
|---------|------|---------|
| [chunk.service.ts](../../frontend/src/app/features/projects/services/chunk.service.ts) | Modificado | `retryChunk()`, signal `failedChunksCount` |
| [project-workspace.component.ts](../../frontend/src/app/features/projects/project-workspace/project-workspace.component.ts) | Modificado | Auto-polling ao carregar, `retryChunk()`, `isRetrying()` |
| [project-workspace.component.html](../../frontend/src/app/features/projects/project-workspace/project-workspace.component.html) | Modificado | Mensagem de erro e botão ↺ no chunk-item |
| [project-workspace.component.scss](../../frontend/src/app/features/projects/project-workspace/project-workspace.component.scss) | Modificado | Estilos de `.chunk-error-msg`, `.btn-retry-chunk`, `.chunk-actions` |
| [dashboard-layout.component.ts](../../frontend/src/app/features/dashboard/dashboard-layout/dashboard-layout.component.ts) | Modificado | Badge dinâmico via `failedChunksCount` |

---

## Comportamento por Cenário

| Cenário | O que acontece agora |
|---------|----------------------|
| Docker down completo (Java + NodeODM) | Recovery marca FAILED com "estava em X%" + botão retry |
| Apenas Java reinicia (NodeODM no ar) | Recovery consulta ODM, retoma polling se ainda RUNNING |
| NodeODM completou durante o downtime do Java | Recovery finaliza os assets automaticamente, chunk fica COMPLETED |
| ODM falhou por problema nas imagens | FAILED com mensagem original do ODM + botão retry |
| Usuário abre projeto com chunk RUNNING (polling perdido) | Auto-polling inicia sem nenhuma ação do usuário |
| Usuário clica em "Tentar Novamente" | Reprocessa com as mesmas opções, badge atualiza em tempo real |

---

## Notas Técnicas

**Por que o `CompletableFuture` é perdido?** O polling roda em um thread na memória da JVM. Quando o processo termina (seja por desligamento normal, kill ou crash), todos os threads são encerrados sem persistir estado. Apenas o PostgreSQL (volumes Docker) preserva os dados.

**Por que não há campo `retryable`?** Na implementação final, todo chunk `FAILED` ou `CANCELED` com pelo menos 3 imagens pode ser reprocessado. Não foi necessário adicionar uma coluna extra no banco — o botão de retry simplesmente aparece para esses status.

**O que acontece com as imagens?** As imagens originais estão no volume `uploads_data`, que persiste entre restarts. O retry sempre reenvia as imagens ao NodeODM — não há risco de perda.

**Opções de processamento preservadas.** O campo `chunk.processingOptions` (JSON) guarda as opções usadas no último processamento. O `retryChunk()` as reutiliza, então o usuário não precisa reconfigurar qualidade, saídas, etc.
