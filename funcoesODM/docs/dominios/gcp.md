# GCP — Ground Control Points

> Domínio completo: exportação, upload e editor visual de GCPs para processamento ODM.  
> Cole junto com `CONTEXT.md` em sessões sobre GCP.

**Última atualização:** 1 de março de 2026

---

## O que é GCP

Ground Control Points (Pontos de Controle) são pontos com coordenadas geográficas conhecidas
(medidas em campo com GPS/GNSS ou estação total) e marcados visualmente nas fotos do voo.
O ODM usa esses pontos para corrigir a posição absoluta do ortofoto, eliminando o erro de deriva
do GPS da aeronave (tipicamente 1–5m) e atingindo precisão sub-decimétrica.

**Sem GCP:** ortofoto posicionado apenas pelo GPS da aeronave (±1 m típico).  
**Com GCP:** ortofoto georreferenciado com precisão de 2–5 cm horizontal.

---

## Formato do arquivo GCP (ODM)

```
EPSG:4326
lat lon alt pixel_x pixel_y nome_arquivo.jpg
lat lon alt pixel_x pixel_y nome_arquivo.jpg
```

- **Linha 1:** código EPSG do sistema de coordenadas
- **Linhas seguintes:** uma por marcação (1 GCP pode ter N linhas, 1 por foto)
- `pixel_x / pixel_y`: coordenadas do pixel na resolução **nativa** do arquivo de imagem
- `nome_arquivo.jpg`: nome exato do arquivo conforme enviado ao ODM

### Exemplos por sistema

**GPS (WGS84):**
```
EPSG:4326
-23.5506 -46.6334 760.5 2840 1187 FIML0090.JPG
-23.5512 -46.6341 761.0 1254  889 FIML0091.JPG
```

**UTM SIRGAS 2000 zona 22S (SP, PR, SC, RS, MG-W):**
```
EPSG:31982
316500.123 7394200.456 760.5 2840 1187 FIML0090.JPG
```

**UTM SIRGAS 2000 zona 23S (SP-E, RJ, ES, MG-E):**
```
EPSG:31983
```

**UTM SIRGAS 2000 zona 24S (MA, PI, CE, TO, GO, parte MG-E, ES):**
```
EPSG:31984
```

> Referência completa de EPSGs: https://epsg.io — pesquise por nome do estado + UTM.

### Regras mínimas ODM

- Pelo menos **3 GCPs distintos** com pixel marcado
- Cada GCP deve aparecer em **pelo menos 2 fotos diferentes**
- Quanto mais GCPs e mais distribuídos na área, melhor a precisão

---

## Implementação — visão geral

Foram implementados 3 recursos independentes que trabalham juntos:

```
[Medições do projeto]
        │
        ▼ ExportGcpService
[GCP.txt parcial] ──► [GCP Editor Visual] ──► [gcp_list.txt completo]
                                                        │
                                                        ▼
                                             [Upload no processamento]
                                             (ChunkController multipart)
                                                        │
                                                        ▼
                                              NodeODM recebe como
                                              gcp_list.txt na task
```

---

## 1. Exportação GCP (ExportGcpService)

**Arquivo:** `frontend/src/app/features/measurement/services/export/export-gcp.service.ts`

Gera arquivo GCP parcial a partir das medições do projeto (tipo `distance` e `height`). As
coordenadas lat/lon/alt são preenchidas com os dados das medições; `pixel_x` e `pixel_y`
ficam `0 0` (preenchidos depois no editor visual).

**Categoria no modal de exportação:** Topografia / Geodésia  
**Formato de saída:** texto puro `.txt`, browser-side, sem dependências

```typescript
// Linha gerada por ponto:
`${lat} ${lng} ${alt} 0 0 foto.jpg`
```

---

## 2. Editor Visual de GCP (GcpEditorComponent)

**Arquivo:** `frontend/src/app/features/projects/project-workspace/components/gcp-editor/gcp-editor.component.ts`

Editor inline com dois painéis:

```
┌─────────────────────────────────────────────────────────────────┐
│  [X] Fechar                          Editor de Pontos GCP       │
├──────────────────────┬──────────────────────────────────────────┤
│  LISTA DE GCPs       │  VISUALIZADOR DE IMAGEM                  │
│                      │  ┌──────────────────────────────────┐    │
│  [●] GCP-01 (2 fotos)│  │  < Anterior  FIML0090.JPG  1/45│    │
│  [●] GCP-02 (1 foto) │  │  [−] 100%  [+]                 │    │
│  [○] GCP-03 (0 fotos)│  │                                  │    │
│                      │  │      [imagem com crosshair]      │    │
│  [+ Importar GCPs]   │  │                                  │    │
│                      │  │      📍 pino no clique           │    │
│                      │  │  x 2840  y 1187  (HUD tempo real)│    │
│                      │  └──────────────────────────────────┘    │
├──────────────────────┴──────────────────────────────────────────┤
│  [VALIDACAO]  Marque cada GCP em pelo menos 2 fotos. [Usar]    │
└─────────────────────────────────────────────────────────────────┘
```

### Fluxo de uso

1. Usuário clica **[GCP] Abrir Editor de GCP** na aba Processar
2. Importa o texto do GCP parcial (ou cola coordenadas) — `px py` podem ser `0 0`
3. Seleciona um GCP na lista esquerda (cor ativa)
4. Navega pelas fotos e clica no ponto correspondente → pin aparece na posição exata
5. Repete para cada GCP em cada foto (mínimo 2 fotos por GCP)
6. Clica **Usar** → `File` gerado no frontend, sinal emitido ao workspace

### Sinais e inputs/outputs

```typescript
@Input({ required: true }) projectId: number
@Input() images: ProjectImage[]          // imagens do chunk atual
@Output() gcpFileReady: EventEmitter<File>   // emite o gcp_list.txt pronto
@Output() closeEditor: EventEmitter<void>
```

### Precisão do pixel

```typescript
// pctX/Y: relativo ao image-wrapper (mesma referência dos pins)
const wRect = wrapper.getBoundingClientRect();
const pctX  = (event.clientX - wRect.left) / wRect.width;
const pctY  = (event.clientY - wRect.top)  / wRect.height;

// pixel nativo: relativo ao <img> (resolução original do arquivo)
const iRect  = img.getBoundingClientRect();
const iPctX  = (event.clientX - iRect.left) / iRect.width;
const pixelX = Math.round(iPctX * img.naturalWidth);
```

- `pctX/Y` → posição visual do pin (left/top %) — referência: `image-wrapper`
- `pixelX/Y` → pixel para o arquivo GCP — referência: `<img>` naturalWidth/Height
- As duas referências são calculadas independentemente para evitar desvio

### HUD de pixel em tempo real

```typescript
cursorPixel = signal<{ x: number; y: number } | null>(null);

onImageMouseMove(event: MouseEvent): void { /* atualiza cursorPixel */ }
onImageMouseLeave(): void { this.cursorPixel.set(null); }
```

Exibe `x 2340  y 1187` no canto inferior esquerdo da imagem enquanto o mouse se move.
Atualiza a cada `mousemove`, funciona em qualquer nível de zoom.

### Zoom

```typescript
zoom = signal(1);          // 1 = ajustado, até 4x
zoomIn()    // +0.5
zoomOut()   // -0.5
resetZoom() // volta para 1
```

Ao trocar de foto, o zoom reseta automaticamente para 1.
Com zoom > 1, o container vira `overflow: auto` com scroll.

### Serviços auxiliares

**`GcpEditorService`** (`gcp-editor/services/gcp-editor.service.ts`)

| Método | Descrição |
|--------|-----------|
| `parsePartialGcp(text)` | Lê txt com ou sem pixel coords → `GcpPoint[]` |
| `buildGcpListTxt(points, marks)` | Gera string ODM completa com pixels |
| `toFile(points, marks)` | Cria `File` (`gcp_list.txt`) para upload |
| `isValid(points, marks)` | Valida: ≥3 GCPs, cada um em ≥2 fotos |

**Interfaces** (`gcp-editor/models/gcp-mark.model.ts`)

```typescript
interface GcpPoint { id, label, lat, lng, alt }
interface GcpMark  { gcpId, imageId, imageOriginalFilename,
                     pixelX, pixelY, pctX, pctY }
```

---

## 3. Upload GCP no processamento

### Frontend — ChunkService

`frontend/.../services/chunk.service.ts`

```typescript
processChunk(projectId, chunkId, options, gcpFile?: File)
// Se gcpFile presente: envia FormData (multipart)
// Se ausente:          envia JSON normal
```

### Backend — ChunkController

`backend/.../controller/ChunkController.java`

Dois `@PostMapping("/{chunkId}/process")` com `consumes` diferentes:

```java
// Sem GCP:
@PostMapping(consumes = APPLICATION_JSON_VALUE)
processChunk(@RequestBody Map<String,Object> options)

// Com GCP:
@PostMapping(consumes = MULTIPART_FORM_DATA_VALUE)
processChunkWithGcp(@RequestPart("options") String optionsJson,
                    @RequestPart("gcpFile") MultipartFile gcpFile)
```

### Backend — NodeODMClient

`backend/.../client/NodeODMClient.java`

```java
public JsonNode createTask(
    List<byte[]> imageData,
    List<String> imageNames,
    String name,
    Map<String,Object> options,
    byte[] gcpContent          // null = sem GCP
)
// Quando gcpContent != null:
//   adiciona ao multipart como ByteArrayResource com filename="gcp_list.txt"
```

**Callers:**

| Serviço | gcpContent |
|---------|-----------|
| `ChunkService` | passado pelo controller |
| `TaskService` | `null` (sem GCP) |
| `ProcessingTaskService` | `null` (sem GCP) |

---

## 4. Wiring no workspace

### process-tab.component.ts

```typescript
@Input()  gcpFileFromEditor: File | null  // arquivo do editor visual
@Output() openGcpEditor: EventEmitter<void>

gcpFileFor(optKey): File | null  // prefere upload local, fallback editor
clearGcpFile(optKey): void
```

### project-workspace.component.ts

```typescript
gcpFile = signal<File | null>(null);
showGcpEditor = signal(false);
openGcpEditor(): void { this.showGcpEditor.set(true); }
onGcpEditorReady(file: File): void { this.gcpFile.set(file); this.showGcpEditor.set(false); }
```

### project-workspace.component.html

```html
<app-process-tab
  [gcpFileFromEditor]="gcpFile()"
  (openGcpEditor)="openGcpEditor()"
/>

@if (showGcpEditor()) {
  <app-gcp-editor
    [projectId]="project()!.id"
    [images]="chunkImages()"
    (gcpFileReady)="onGcpEditorReady($event)"
    (closeEditor)="showGcpEditor.set(false)"
  />
}
```

---

## Bugs conhecidos e soluções

| Bug | Causa | Solução aplicada |
|-----|-------|-----------------|
| Pin deslocado verticalmente (proporcional à posição Y) | `object-fit: contain` cria espaço vazio acima/abaixo; `offsetY` conta esse espaço | Removido `object-fit`; `width/height: auto` + `max-*` — elemento tem exatamente o tamanho visível |
| Pin deslocado em zoom | `pctX/Y` calculado via `<img>` mas pin renderiza relativo ao `image-wrapper` | `pctX/Y` agora usa `wrapper.getBoundingClientRect()`; pixel usa `img.getBoundingClientRect()` |
| Ponta do pin 4.5px acima do pixel | `translate(-50%, -100%)` sobe ao topo do box CSS; ponta do losango extrapola o box | `translate(-50%, calc(-100% - 4.56px))` — valor = `11*(√2 - 1) + 11 - 11 = 4.56px` |
| Pixel 30px acima no topo | `getBoundingClientRect()` + `event.clientY` com letterbox | Trocado para `event.offsetX/Y / img.offsetWidth/Height` |

---

## Endpoint de imagem

```
GET /api/v1/projects/{projectId}/images/{imageId}/thumbnail
```

Retorna o arquivo original armazenado em disco (não é thumbnail reduzido).
`img.naturalWidth/Height` = dimensões reais do arquivo = pixelX/Y corretos para ODM.

> **Atenção:** se este endpoint for alterado para retornar um thumbnail reduzido,
> será necessário adicionar `originalWidth` e `originalHeight` ao `ProjectImage`
> e escalar os pixels: `pixelX = pctX * originalWidth`.

---

## Checklist para próxima sessão

- [ ] Confirmar que `pixel_x/y` no gcp_list.txt batem com o relatório de qualidade do ODM
- [ ] Testar com imagens de alta resolução (>20MP) e verificar precisão dos pinos
- [ ] Adicionar `originalWidth/originalHeight` ao `ProjectImage` se o endpoint de thumbnail for otimizado
- [ ] Considerar preview do gcp_list.txt gerado antes de clicar em Usar
- [ ] **Antes de produção:** substituir tiles Google Satellite por Esri World Imagery ou contratar Google Maps Platform API (uso atual viola ToS do Google — ver [BEST_PRACTICES.md](../architecture/BEST_PRACTICES.md#uso-de-tiles-e-apis-de-terceiros))
