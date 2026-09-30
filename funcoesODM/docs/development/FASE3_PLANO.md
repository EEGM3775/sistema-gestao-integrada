# Fase 3 — Modulos de Engenharia: Plano de Implementacao

**Criado:** 16 de maio de 2026
**Atualizado:** 23 de maio de 2026

---

## Visao geral

| Modulo | Dependencia ODM | Status |
|--------|----------------|--------|
| M1: NDVI / VARI | `odm_orthophoto/odm_orthophoto.tif` | Concluido |
| M2: Viewer 3D | `odm_meshing/odm_mesh.ply` (6.6 MB — PLY do mesh) | Em andamento (Etapa A) |
| M3: Anotacoes colaborativas | Nenhuma (dado proprio do sistema) | Pendente |

---

## M1 — Indices de Vegetacao (NDVI / VARI) — CONCLUIDO

### Decisao de arquitetura (como foi implementado)

Calculo **100% no browser** usando `georaster` e `georaster-layer-for-leaflet`,
que ja estavam instalados para o DsmTab. Nenhuma alteracao de backend foi necessaria.

- **VARI** `= (G - R) / (G + R - B)` — disponivel para qualquer ortofoto RGB
- **NDVI** `= (NIR - R) / (NIR + R)` — habilitado automaticamente se `georaster.numberOfRasters >= 4`
- Pixels de fundo (borda preta do bounding box) filtrados com `r < 5 && g < 5 && b < 5`
- Basemap: Esri satellite (melhor contexto visual para analise de vegetacao)

### Componentes criados

| Arquivo | Responsabilidade |
|---------|----------------|
| `vegetation-tab.component.ts/html/scss` | Aba completa: toggle VARI/NDVI, mapa Leaflet, legenda, histograma |

### Integracao

- Adicionado ao `results-viewer.component.html` com `*ngIf="hasOrthophoto()"` e keep-alive `[hidden]`
- Usa `GeoTiffCacheService` para buffer e georaster — sem re-download ao trocar de aba
- Input `[visible]` chama `invalidateSize()` + auto-start ao entrar na aba
- Barra de progresso real via ReadableStream durante o download

### Criterios de conclusao

- [x] VARI funciona com camera RGB comum
- [x] NDVI habilitado automaticamente com camera multiespectral (4 bandas)
- [x] Camada colorida sobre mapa satelite
- [x] Histograma exibe distribuicao dos valores
- [x] Estatisticas min/max/media na toolbar
- [x] Legenda de cores de -1 a +1
- [x] Performance: primeira carga usa cache compartilhado com Visualizador

---

## UX — Performance de carregamento (Concluido junto com M1)

### Problema resolvido

Arquivos GeoTIFF de ortofoto chegam a 230 MB. Sem cache, cada troca de aba
(Visualizador → Vegetacao → Visualizador) redownloadava e reparsava o arquivo inteiro.

### Solucao: GeoTiffCacheService

`core/services/geotiff-cache.service.ts` — singleton Angular (`providedIn: 'root'`)

**Armazena:**
- Bytes brutos como `Uint8Array` — nao e transferivel, nunca fica detached apos postMessage
- Georaster parseado por URL — `parseGeoraster()` so roda uma vez por sessao

**Entrega:**
- `get(url)`: retorna `ArrayBuffer` novo via `bytes.slice().buffer` a cada chamada
  — o chamador pode transferir livremente sem afetar o cache
- `getGeoRaster(url)` / `setGeoRaster(url, georaster)`: cache do objeto parseado

**Beneficio:** ao trocar de aba, a segunda carga e instantanea (sem download, sem parse).

### Keep-alive de abas

`results-viewer.component.html`: abas Visualizador e Vegetacao usam `[hidden]` em vez
de `@if`. O componente permanece no DOM com seu estado completo (mapa Leaflet, layers,
georaster computado). Ao voltar para a aba, o mapa aparece imediatamente.

**Input `[visible]`** em todos os componentes com mapa:
```typescript
@Input() set visible(val: boolean) {
  if (val && this.map) setTimeout(() => this.map?.invalidateSize(), 80);
}
```

---

## M2 — Viewer 3D da Nuvem de Pontos

### Contexto

NodeODM gera varios arquivos PLY. O arquivo utilizado para o viewer e
`odm_meshing/odm_mesh.ply` (6.6 MB — mesh triangulado, ideal para browser).
O `point_cloud.ply` (622 MB) e grande demais para browser — fica para Etapa B com Potree.

### Decisao de arquitetura (como foi implementado)

**Arquivo servido:** `odm_meshing/odm_mesh.ply` via endpoint existente de download.
Alias `mesh` adicionado ao `NodeODMClient.ASSET_FILE_PATHS` e `ASSET_ALIASES`.

**Dois locais de viewer:**
1. Rota `/projects/{id}/3d` — `Project3DComponent` + `Viewer3DService`
2. Aba "Nuvem de Pontos" no measurement-tab — `PointcloudViewerComponent` (shared/viewers)

Ambos reutilizam o mesmo `Viewer3DService` (injetado via `providers: [Viewer3DService]`).

**Viewer3DService** (`project-3d/services/viewer-3d.service.ts`):
- `WebGLRenderer` com antialiasing e pixel ratio adaptativo
- `PLYLoader` do `three/examples/jsm/loaders/PLYLoader.js`
- `OrbitControls` com damping (rotacao, zoom, pan)
- Coloracao por altitude: gradiente HSL azul(frio/baixo)->verde->vermelho(quente/alto)
- FPS counter real via `performance.now()`
- `ResizeObserver` para canvas responsivo
- Screenshot via `renderer.domElement.toDataURL()`
- Metodos `setColorMode`, `setShowGrid`, `setShowAxes`

**Fluxo de carga:**
1. Component chama `GET /api/v1/projects/{id}/tasks` para obter task COMPLETED
2. Chama `GET /api/v1/projects/{id}/tasks/{taskId}/download/mesh` (arraybuffer)
3. `PLYLoader.parse(buffer)` → `BufferGeometry`
4. `computeVertexNormals()` + coloracao por altitude
5. `Mesh` renderizado na cena

### Plano em duas etapas

#### Etapa A (MVP) — Three.js + PLY — Em andamento

**Implementado:**
- [x] Backend: alias `mesh` / `mesh.ply` no NodeODMClient
- [x] Frontend: `three ^0.176` + `@types/three` em package.json
- [x] Frontend: Viewer3DService com WebGL, PLYLoader, OrbitControls
- [x] Frontend: coloracao por altitude (gradiente Z)
- [x] Frontend: Project3DComponent com carga real de task
- [x] Frontend: PointcloudViewerComponent integrado

**Pendente:**
- [ ] Corrigir 404 no download (taskId mismatch — 13 vs 1)
- [ ] Confirmar visualizacao no browser

#### Etapa B (completa) — Potree streaming — Implementado (aguardando teste)

**Arquitetura:**
```
LAZ (84 MB) → funcoesodm-potree → /potree/data/{uuid}/ → nginx /potree-tiles/
                                                                ↓
                                              @pnext/three-loader no browser
```

**Novo container:** `funcoesodm-potree`
- Imagem: Node.js + PotreeConverter 2.1 (binario Linux x64)
- API HTTP interna: `POST /convert` + `GET /status/:uuid`
- Volume compartilhado: `potree_data` (leitura em nginx, escrita no converter)

**Backend:**
- `PotreeService.java` — gerencia ciclo: verificar → disparar → aguardar
- `PotreeController.java` — `GET /api/v1/projects/{id}/tasks/{tid}/potree`
- Inicia conversao automaticamente na primeira consulta de status

**Frontend:**
- `@pnext/three-loader ^3.1.5` — carregador Potree para Three.js
- `PotreeLoaderService` — polling de status (3s) + carregamento de tiles
- `Viewer3DService.loadPointCloudPotree()` — integra Potree ao renderer existente
- Toggle "Mesh / Nuvem" na UI do viewer
- Indicador visual "Convertendo para Potree..." durante processamento

**Fluxo do usuario:**
1. Abre viewer 3D → mesh carrega imediatamente (Etapa A)
2. Clica "Nuvem" → conversao LAZ→Potree inicia automaticamente
3. Progresso indeterminado durante conversao (pode demorar 1-5 min)
4. Quando ready, tiles carregam via streaming com LOD automatico

### Criterios de conclusao (Etapa A)

- [x] Canvas WebGL configurado com Three.js real
- [x] PLYLoader carrega arquivo do backend
- [x] Rotacao, zoom e pan funcionam (OrbitControls)
- [x] Coloracao por altitude com gradiente
- [x] Exibe contagem de vertices nos stats
- [x] Fallback amigavel se arquivo nao existir
- [ ] Viewer funcionando end-to-end no browser

---

## M3 — Anotacoes Colaborativas — CONCLUIDO (sessao 18-19)

### Contexto

Marcacoes textuais geolocalizadas sobre a ortofoto e o indice de vegetacao.
Util para registrar observacoes de campo, defeitos e areas de interesse em equipe.

### Decisao de arquitetura

Anotacoes sao **sub-ferramentas dentro dos viewers existentes**, nao uma aba separada.
Isso mantem o usuario no contexto visual correto ao anotar.

- **Visualizador (MeasurementTabComponent):** secao "Anotacoes" na sidebar retrátil,
  ao lado das medicoes. Visivel quando a camada ativa e ortofoto ou DSM.
- **Vegetacao (VegetationTabComponent):** botao "+ Anotar" na toolbar e painel abaixo
  do histograma. Os marcadores sao exibidos sobre o indice VARI/NDVI.

### Modelo de dados

```sql
CREATE TABLE annotations (
    id               BIGSERIAL PRIMARY KEY,
    project_id       BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id          BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type             VARCHAR(50) NOT NULL DEFAULT 'MARKER',  -- MARKER | POLYGON | POLYLINE | NOTE
    coordinates_json TEXT NOT NULL DEFAULT '[]',             -- [lat,lng] ou [[lat,lng],...]
    text             TEXT,
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### Backend

```
GET    /api/v1/projects/{id}/annotations        — lista do projeto
POST   /api/v1/projects/{id}/annotations        — cria (autor = usuario autenticado)
DELETE /api/v1/projects/{id}/annotations/{aid}  — deleta (so o autor)
```

Classes: `Annotation.java`, `AnnotationDto.java`, `AnnotationCreateRequestDto.java`,
`AnnotationRepository.java`, `AnnotationService.java`, `AnnotationController.java`

WebSocket: `ANNOTATION_CREATED` e `ANNOTATION_DELETED` emitidos via `WebSocketService`
para o topico `/topic/project/{id}/progress`.

### Frontend — componentes

| Arquivo | Responsabilidade |
|---------|----------------|
| `annotation.model.ts` | Interfaces `Annotation` e `CreateAnnotationRequest` |
| `annotation.service.ts` | Signal state + HTTP CRUD + WS ref-counted (connectToProject/disconnectFromProject) |
| `annotations-panel.component.*` | Lista, filtro por tipo, delete com validacao de ownership |
| `MeasurementTabComponent` | Secao de anotacoes na sidebar + camada Leaflet na ortofoto/DSM |
| `VegetationTabComponent` | Botao Anotar na toolbar + camada Leaflet sobre VARI/NDVI |

### Ciclo de vida do WebSocket (Opcao B)

`AnnotationService` e o unico assinante do WS — ref-counted para suportar
multiplos componentes simultaneos sem subscricoes duplicadas:

```typescript
connectToProject(id)    // +1 ref, assina WS e carrega dados se for o primeiro
disconnectFromProject() // -1 ref, desconecta quando o ultimo componente sai
```

### Criterios de conclusao

- [x] Criar e deletar anotacoes no mapa (ortofoto, DSM, VARI/NDVI)
- [x] Painel lateral lista anotacoes com filtro por tipo
- [x] Permissao: so o autor pode excluir a propria anotacao
- [x] Marcador aparece em tempo real para outros usuarios (WebSocket)
- [x] Anotacoes persistem apos reload
- [x] Reatividade: `effect()` re-renderiza marcadores quando o signal muda
- [x] Popup com escaping HTML (sem XSS)
- [x] Popup de criacao usa DOM programatico (sem innerHTML)

---

## Dependencias tecnicas

| Modulo | Pacote | Status |
|--------|--------|--------|
| M1 | georaster, georaster-layer-for-leaflet | Ja instalados |
| M2 (A) | `three ^0.176`, `@types/three ^0.176` | Instalados em package.json |
| M2 (B) | potree-converter | Docker sidecar — a configurar |
| M3 | Nenhum pacote novo | - |

## Arquivos PLY disponiveis no NodeODM (referencia)

| Arquivo | Tamanho | Descricao |
|---------|---------|-----------|
| `odm_meshing/odm_mesh.ply` | 6.6 MB | Mesh triangulado — **usado no Etapa A** |
| `odm_filterpoints/point_cloud.ply` | 622 MB | Nuvem de pontos filtrada — inviavel para browser |
| `odm_georeferencing/odm_georeferenced_model.laz` | 84 MB | Nuvem georreferenciada comprimida — para Etapa B |

---

## Ordem de execucao recomendada

```
M2 Etapa A (Viewer 3D MVP)
  Backend: endpoint PLY URL
  Frontend: Three.js + canvas WebGL + orbit controls

M3 (Anotacoes)
  Backend: migration + CRUD + WebSocket event
  Frontend: mapa layer + painel + formulario + WS sync

M2 Etapa B (Viewer 3D completo) — quando M2A validar o fluxo
```

---

## Referencias

- [CONTEXT.md](../CONTEXT.md)
- [roadmap.md](../roadmap.md)
- [TODOODM.md](TODOODM.md)
