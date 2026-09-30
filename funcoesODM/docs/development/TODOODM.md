# Lista de Tarefas do FuncoesODM

Este documento e o plano ativo de desenvolvimento e o registro dos bugs que ainda bloqueiam o uso.

**Ultima atualizacao:** 24 de maio de 2026 (sessao 21)

---

## Bugs ativos (P0)

Nenhum bug P0 aberto.

| # | Bug | Area | Status |
|---|-----|------|--------|
| B1 | Criar novo projeto nao funciona | Frontend + Backend | Corrigido (sessao 8) |
| B2 | Relatorio de Proximidade GCP nao aparece | Frontend | Corrigido (sessao 9) |
| B3 | Perfil de Elevacao com grafico vazio | Frontend | Corrigido (sessao 10) |
| B4 | Excluir projeto falha com FK violation | Backend | Corrigido (sessao 13) |
| B5 | Aba Vegetacao nao renderizava (canvas 0x0) | Frontend | Corrigido (sessao 13-14) |
| B6 | DataCloneError: ArrayBuffer detached | Frontend | Corrigido (sessao 15) |
| B7 | Lixeira nao aparecia nas anotacoes | Frontend | Corrigido (sessao 20) |
| B8 | Botao delete continuava sumindo — AuthResponse nao retornava user | Backend | Corrigido (sessao 21) |

---

## Fase 3 — Modulos de engenharia

Ver plano completo em [FASE3_PLANO.md](FASE3_PLANO.md).

### M1 — NDVI / VARI (Concluido)

- [x] Aba "Vegetacao" no results-viewer
- [x] Calculo VARI (RGB) e NDVI (multiespectral) no browser via georaster
- [x] Deteccao automatica de banda NIR
- [x] Camada Leaflet com paleta cromatica e controle de opacidade
- [x] Basemap satelite Esri para contexto visual
- [x] Filtro de pixels de fundo (borda preta do bounding box)
- [x] Histograma de distribuicao com Chart.js
- [x] Estatisticas min/max/media na toolbar
- [x] Auto-start ao entrar na aba
- [x] Barra de progresso real (bytes recebidos / total)

### UX — Performance de carregamento (Concluido)

- [x] GeoTiffCacheService: cache singleton de bytes (Uint8Array) e georaster parseado
- [x] Keep-alive: abas Visualizador e Vegetacao usam [hidden] em vez de @if
- [x] Input [visible] em todos os componentes com mapa — chama invalidateSize()
- [x] Progresso real de download em OrthophotoViewer, DsmTab e VegetationTab
- [x] Cache de georaster no servico — parseGeoraster roda uma vez por arquivo por sessao
- [x] invalidateSize() deferred (300ms) no DsmTab e VegetationTab
- [x] Correcao: OrthophotoViewer nao trava mais ao trocar de aba durante download

### M2 — Viewer 3D da Nuvem de Pontos (Concluido e testado)

- [x] Backend: mapeamento `mesh` -> `odm_meshing/odm_mesh.ply` no NodeODMClient
- [x] Backend: endpoint existente `GET /projects/{id}/tasks/{tid}/download/mesh` reutilizado
- [x] Frontend: `three ^0.176` + `@types/three` adicionados ao package.json
- [x] Frontend: Viewer3DService reescrito com WebGLRenderer, PLYLoader, OrbitControls
- [x] Frontend: coloracao por altitude (gradiente azul->verde->vermelho via HSL)
- [x] Frontend: Project3DComponent reescrito com carga real de task via HTTP
- [x] Frontend: PointcloudViewerComponent (measurement-tab) reescrito com Three.js
- [x] Frontend: screenshot via canvas.toDataURL implementado
- [x] Frontend: stats reais (FPS via performance.now, contagem de vertices)
- [x] Frontend: setColorMode / setShowGrid / setShowAxes conectados aos controles
- [x] Bug corrigido: PointcloudViewerComponent usava chunk.id como taskId — corrigido para buscar task real via API
- [x] Potree streaming: container potree-converter, PotreeService/Controller no backend, PotreeLoaderService + @pnext/three-loader no frontend, toggle Mesh/Nuvem
- [x] Testado end-to-end pelo usuario — funcionando corretamente

### M3 — Anotacoes Colaborativas (Concluido — sessoes 18-21)

**Sessao 18 — implementacao inicial (backend + frontend base):**
- [x] Backend: `init-db/02-annotations.sql` — tabela `annotations` com FK cascade e indices
- [x] Backend: `Annotation.java`, `AnnotationDto.java`, `AnnotationCreateRequestDto.java`
- [x] Backend: `AnnotationRepository.java` — JOIN FETCH user, findByIdAndProjectId
- [x] Backend: `AnnotationService.java` — CRUD + validacao de ownership + emissao WebSocket
- [x] Backend: `AnnotationController.java` — `GET/POST/DELETE /api/v1/projects/{id}/annotations`
- [x] Backend: `ProgressMessage.java` — tipos `ANNOTATION_CREATED` e `ANNOTATION_DELETED`
- [x] Backend: `WebSocketService.java` — `sendAnnotationCreated()` e `sendAnnotationDeleted()`
- [x] Frontend: `annotation.model.ts`, `annotation.service.ts`, `AnnotationsPanelComponent`

**Sessao 19 — correcao de arquitetura (anotacoes como sub-ferramenta, nao aba separada):**
- [x] Removido: `MapTabComponent` (era uma aba com mapa duplicado — errado)
- [x] Removido: aba "Anotacoes" do `ResultsViewerComponent`
- [x] `AnnotationService` refatorado: `connectToProject(id)` / `disconnectFromProject()` ref-counted;
  `handleWebSocketMessage` privado; sem mais dependencia de componentes externos para WS
- [x] `AnnotationsPanelComponent` simplificado: sem WS proprio, sem `loadAnnotations()` — so le o signal
- [x] `MeasurementTabComponent`: secao "Anotacoes" na sidebar (visivel em ortofoto/DSM),
  camada Leaflet compartilha o mapa existente, `effect()` reativo, botao Anotar/Cancelar
- [x] `VegetationTabComponent`: botao "+ Anotar" na toolbar, camada Leaflet sobre VARI/NDVI,
  painel abaixo do histograma, `effect()` reativo
- [x] `WebSocketService.ProgressMessage` type: adicionados `ANNOTATION_CREATED | ANNOTATION_DELETED`
- [x] Popup de criacao usa `L.DomUtil` / DOM programatico (sem innerHTML, sem XSS)
- [x] Escaping HTML no popup de visualizacao (`escapeHtml` em ambos os viewers)

**Sessao 20 — correcoes de UX e arquitetura do painel:**
- [x] B7 corrigido: `isOwn()` comparava `author.username` por string (case-sensitive); corrigido para comparar `author.id === currentUser().id`
- [x] Tipo NOTE removido do modelo (`annotation.model.ts`), dos filtros, do `typeLabel()`, do backend e do SQL — apenas MARKER e POLYGON
- [x] Icone do marcador: substituido por `L.divIcon` com SVG inline (fix para PNG do Leaflet nao carregar no webpack/Angular)
- [x] Modo poligono: `startAnnotating(type: 'MARKER' | 'POLYGON')`, signals `annotationType`/`polygonPoints`, feedback visual com `updateTempPolygon()`, `completePolygon()`, popup em centroide
- [x] Sidebar dividida em dois paineis com scroll independente: `.sidebar-pane { flex: 1 1 0; min-height: 0 }` em ambas as abas (MeasurementTab e VegetationTab)
- [x] `AnnotationsPanelComponent`: `@Input() showHeader` para suprimir cabecalho interno; `:host { flex: 1; min-height: 0 }` para participar do layout flex
- [x] Botao de exclusao com icone SVG de lixeira (visivel para autor da anotacao)
- [x] Cursor crosshair ao entrar em modo anotar: `map.getContainer().style.cursor = 'crosshair'`; restaurado ao cancelar/concluir

**Sessao 21 — autenticacao + editar anotacao + visibilidade:**
- [x] B8 corrigido: `AuthResponse` so retornava token; `currentUser()` ficava null; `isOwn()` sempre false
  - Backend: `AuthResponse` agora inclui `user { id, username, email }`; `AuthenticationController.authenticate()` busca usuario no DB
  - Backend: novo endpoint `GET /api/v1/auth/me` para sessoes pre-existentes sem logout
  - Frontend: `AuthService.checkTokenOnInit()` chama `/me` se token existir mas usuario nao estiver em cache
- [x] Editar anotacao: botao lapis visivel para o autor; edicao inline com textarea + Salvar/Cancelar
  - Backend: `AnnotationUpdateRequestDto`, `AnnotationService.update()`, `PATCH /annotations/{id}`, `ANNOTATION_UPDATED` no WebSocket
  - Frontend: `AnnotationService.updateAnnotation()` + handler WS `ANNOTATION_UPDATED`
  - Frontend: `AnnotationsPanelComponent` com signals `editingId`/`editText`/`savingEditId` e metodos `startEdit`/`cancelEdit`/`saveEdit`
- [x] Visibilidade de anotacao no mapa: checkbox com icone olho na lateral esquerda de cada item
  - Frontend: `AnnotationService.hiddenIds` signal, `toggleVisibility()`, `isVisible()`
  - Frontend: `effect()` em `MeasurementTab` e `VegetationTab` rastreia `hiddenIds()` — camada Leaflet omite anotacoes ocultas

### Acabamento (Pendente)

- Responsividade avancada
- Dark/Light mode
- i18n PT-BR + EN
- Testes automatizados
- Biblioteca de icones
- PWA / offline
- Settings / Preferencias

### Producao (Pendente)

- CI/CD
- Testes de carga / performance
- HTTPS, dominio e variaveis de producao
- Swagger / OpenAPI
- Backup automatizado do banco
- Monitoramento e alertas
- Hardening de multi-tenancy
- Plano de licenciamento SaaS

---

## Historico de sessoes resumido

- Sessao 21: B8 corrigido (AuthResponse sem user; /me endpoint; checkTokenOnInit busca user); editar anotacao inline (lapis SVG, textarea, PATCH endpoint, WS ANNOTATION_UPDATED); checkbox de visibilidade com icone olho (hiddenIds signal, effect rastreia visibilidade)
- Sessao 20: M3 acabamento — B7 corrigido (isOwn por ID, nao username); NOTE removido; marcador com divIcon SVG; modo poligono completo; sidebar split com scroll independente; AnnotationsPanelComponent com @Input showHeader; lixeira SVG; cursor crosshair ao anotar
- Sessao 19: M3 corrigido arquiteturalmente — anotacoes movidas para dentro do Visualizador e da Vegetacao (nao mais aba separada); MapTabComponent removido; AnnotationService refatorado com connectToProject/disconnectFromProject ref-counted; effect() reativo nos dois viewers; popup seguro sem XSS
- Sessao 18: M2 testado end-to-end (funcionando); M3 implementado completo — tabela annotations, CRUD REST, WebSocket ANNOTATION_CREATED/DELETED, AnnotationsPanelComponent, modo anotar no MapTab, aba Anotacoes no ResultsViewer
- Sessao 17: M2 Etapa B — Potree streaming: potree-converter container, PotreeService+Controller no backend, PotreeLoaderService+@pnext/three-loader no frontend, toggle Mesh/Nuvem na UI; bug taskId corrigido
- Sessao 16: M2 Etapa A — Viewer3DService com Three.js (WebGL/PLYLoader/OrbitControls); PointcloudViewerComponent reescrito; mapeamento mesh.ply no backend; investigando 404 no download (taskId mismatch)
- Sessao 15: Cache de georaster movido para GeoTiffCacheService; fix duplo "MB" em OrthophotoViewer
- Sessao 14: Fix DataCloneError (ArrayBuffer detached); GeoTiffCacheService usa Uint8Array; fix troca ortofoto<->DSM
- Sessao 13: Keep-alive abas; GeoTiffCacheService criado; barra de progresso; [visible] input; fix FK exclusao projeto
- Sessao 12: M1 implementado (VARI/NDVI frontend-only, vegetation-tab, histograma Chart.js)
- Sessao 11: CONTEXT.md atualizado, plano da Fase 3 criado (FASE3_PLANO.md)
- Sessao 10: B3 corrigido (chart criado apos coordenadas chegarem)
- Sessao 9: B2 corrigido (remocao de OnPush no GCP) e CTA com tipo correto
- Sessao 8: bugs abertos B1-B3 identificados
- Sessao 7: relatorio de proximidade GCP e perfil de elevacao concluidos
- Sessao 6: refatoracao da measurement-tab em subcomponentes
- Sessao 5: refatoracao do modulo de exportacao

---

## Referencias

- [roadmap.md](../roadmap.md) - planejamento de evolucao
- [CONTEXT.md](../CONTEXT.md) - estado atual do projeto
- [FASE3_PLANO.md](FASE3_PLANO.md) - plano detalhado da Fase 3
