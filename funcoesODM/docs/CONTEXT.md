# CONTEXT - FuncoesODM

> Resumo curto do estado atual do projeto. Para bugs ativos, use [development/TODOODM.md](development/TODOODM.md). Para planejamento, use [roadmap.md](roadmap.md).

## Stack

| Camada | Tecnologia | Versao |
|--------|-----------|--------|
| Frontend | Angular (Standalone + Signals) | 18.2.21 |
| Frontend | TypeScript | 5.5 |
| Frontend | Leaflet | 1.9.4 |
| Frontend | chart.js | 4.4.7 |
| Frontend | georaster + georaster-layer-for-leaflet | instalados |
| Frontend | three.js | 0.176 |
| Backend | Spring Boot | 3.2.0 |
| Backend | Java | 17 |
| Banco | PostgreSQL | 15 |
| Processamento | NodeODM custom (numpy-fix) | latest base |
| Infra | Docker + Docker Compose + Nginx | - |

## Estrutura em alto nivel

- Frontend: frontend/src/app/
- Backend: backend/java-service/src/main/java/
- Docs: docs/
- Docker: docker-compose.yml, docker/, init-db/

## O que ja esta funcionando

- Login / JWT / guards / interceptors
- CRUD de projetos (incluindo exclusao correta de chunks)
- Upload de imagens
- Processamento NodeODM e progresso via WebSocket
- Ortofoto viewer (GeoTIFF nativo) e DEM/DSM viewer
- Medicoes de distancia, area, altura e volume
- Exportacao de medicoes em multiplos formatos
- Editor visual de GCP com relatorio de proximidade
- Perfil de elevacao com Chart.js
- NodeODM com fix de NumPy
- **Aba Vegetacao: VARI e NDVI calculados no browser (georaster)**
- **Cache de GeoTIFF e georaster entre componentes (GeoTiffCacheService)**
- **Keep-alive das abas Visualizador e Vegetacao (sem recarga ao trocar)**
- **Barra de progresso real no download de arquivos**
- **Viewer3DService com Three.js: WebGLRenderer, PLYLoader, OrbitControls, coloracao por altitude**
- **Project3DComponent reescrito com carga real de task via HTTP**
- **PointcloudViewerComponent (measurement-tab) integrado ao Viewer3DService**
- **Potree streaming: potree-converter container, PotreeService/Controller, PotreeLoaderService, @pnext/three-loader**
- **Toggle Mesh/Nuvem no viewer 3D**
- **Anotacoes colaborativas: CRUD REST, WebSocket em tempo real, camada Leaflet integrada ao Visualizador (ortofoto/DSM) e a Vegetacao (VARI/NDVI), painel lateral em ambos**
- **Anotacoes — modo POLYGON com feedback visual; marcador com divIcon SVG; lixeira visivel; cursor crosshair; sidebar split com scroll independente**
- **Anotacoes — editar texto inline (botao lapis, PATCH endpoint, WS ANNOTATION_UPDATED); checkbox de visibilidade por anotacao (icone olho, signal hiddenIds)**
- **AuthService: login retorna user com id; endpoint /me para sessoes pre-existentes**

## Bloqueadores atuais

Nenhum bloqueador. Fase 3 concluida.

## Fase 3 — Modulos de engenharia

| Modulo | Status |
|--------|--------|
| M1: NDVI / VARI | Concluido |
| M2: Viewer 3D (Three.js + Potree streaming) | Concluido e testado |
| M3: Anotacoes colaborativas | Concluido (sessoes 18-21) |

Ver plano detalhado em [development/FASE3_PLANO.md](development/FASE3_PLANO.md).

## Servicos e padroes chave

### AnnotationService (singleton)
`features/projects/services/annotation.service.ts`

Gerencia o estado das anotacoes e o ciclo de vida da conexao WebSocket. Responsabilidades:
1. Signal `annotations` com lista sincronizada via HTTP e WebSocket
2. `connectToProject(id)` / `disconnectFromProject()` — ref-counted: assina WS e carrega dados
   na primeira chamada; desconecta quando o ultimo componente sai. Suporta Visualizador e
   Vegetacao ativos ao mesmo tempo sem subscricoes duplicadas.
3. `createAnnotation()`, `deleteAnnotation()`, `updateAnnotation()` — atualizam o signal local
4. `handleWebSocketMessage()` privado: processa `ANNOTATION_CREATED`, `ANNOTATION_DELETED`,
   `ANNOTATION_UPDATED`
5. Ownership validado no backend (`UnauthorizedException` se nao for o autor)
6. Signal `hiddenIds: ReadonlySignal<Set<number>>` + `toggleVisibility(id)` + `isVisible(id)` —
   controle de visibilidade de cada anotacao no mapa (client-side only, nao persiste)

**Tipos de anotacao:** apenas `MARKER` e `POLYGON` (NOTE e POLYLINE removidos).

**Integracao nos viewers:**
- `MeasurementTabComponent` — sidebar dividida em dois paineis com scroll independente
  (`.sidebar-pane { flex: 1 1 0; min-height: 0 }`); botoes "+ Marcador" / "+ Poligono";
  modo poligono com feedback visual (`updateTempPolygon()`), cursor crosshair, "Concluir" ao
  atingir 3+ pontos; `effect()` rastreia `annotations()` e `hiddenIds()` — omite camadas ocultas
- `VegetationTabComponent` — botoes "+ Marcador" / "+ Poligono" na toolbar; mesma logica;
  `effect()` tambem rastreia `hiddenIds()`

**AnnotationsPanelComponent:**
- `@Input() showHeader = true` — suprime o cabecalho interno quando o pai ja fornece um
- `:host { flex: 1; min-height: 0 }` — participa do layout flex com scroll interno
- `isOwn()` compara por `author.id === currentUser().id` (nao por username)
- Checkbox com icone olho (esquerda) — controla visibilidade via `annotationService.toggleVisibility()`
- Botao lapis (autor apenas) — ativa edicao inline com textarea + Salvar/Cancelar
- Botao lixeira (autor apenas) — exclui com spinner de feedback

**Marcador Leaflet:** usa `L.divIcon` com SVG inline (pin) — evita 404 nos PNGs do Leaflet
ao fazer bundle com webpack/Angular.

### AuthService
`core/services/auth.service.ts`

- Login retorna `{ token, user: { id, username, email } }` — `currentUserSignal` e localStorage
  sao populados imediatamente apos autenticacao
- `checkTokenOnInit()` chama `GET /api/v1/auth/me` se o token existir mas o usuario nao estiver
  em cache (necessario para sessoes criadas antes da correcao do backend)
- `isOwn()` nas anotacoes depende de `currentUser().id` ser um numero valido — sem o user no
  token/cache o botao de lixeira/lapis nao aparece

### GeoTiffCacheService (singleton)
`core/services/geotiff-cache.service.ts`

Cache de sessao para arquivos GeoTIFF grandes. Resolve dois problemas:
1. Evita re-download do mesmo arquivo por multiplos componentes
2. Armazena bytes como `Uint8Array` (nao transferivel) para que `parseGeoraster`
   possa transferir o `ArrayBuffer` ao Worker sem invalidar o cache
3. Cache do georaster parseado — `parseGeoraster` so roda uma vez por arquivo por sessao

### Keep-alive de abas
Abas Visualizador e Vegetacao usam `[hidden]` em vez de `@if` no results-viewer.
Estado do mapa, georaster e indice calculado sobrevivem a trocas de aba.
Input `[visible]` em cada componente chama `map.invalidateSize()` ao ficar visivel.

## Convencoes criticas

- Nao usar emojis em scripts ou codigo fonte
- Angular com standalone: true
- Estado local com Signals; async com RxJS
- Templates e estilos externos
- Um componente / servico, uma responsabilidade
- GeoTIFFs grandes: sempre usar GeoTiffCacheService, nunca fetch direto

## Referencias

- [README.md](README.md) - indice da documentacao
- [roadmap.md](roadmap.md) - planejamento
- [development/TODOODM.md](development/TODOODM.md) - bugs e historico
- [development/FASE3_PLANO.md](development/FASE3_PLANO.md) - plano da Fase 3

**Ultima atualizacao:** 24 de maio de 2026 (sessao 21)
