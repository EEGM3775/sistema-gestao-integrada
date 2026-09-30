# Domínio: Medições — FuncoesODM

> Cole junto com CONTEXT.md quando a sessão envolver medições, exportação ou queries de elevação DSM.

---

## Componentes (onde cada coisa fica)

```
features/projects/components/measurement-tab/
├── measurement-tab.component.ts    # Orquestrador: signals, fluxo de ferramentas, handlers de evento (~465 linhas)
├── measurement-tab.component.html  # Template: dropdown, viewer, toolbar, sidebar (~120 linhas)
└── measurement-tab.component.scss  # Container, mapa, sidebar, banner (~366 linhas)

features/measurement/
├── models/
│   └── measurement-data.ts         # Interface MeasurementData, tipo ActiveTool
├── services/
│   ├── map-drawing.service.ts       # Desenho Leaflet: line | polygon | twopoint
│   ├── dsm-elevation.service.ts     # Query elevação em GeoTIFF DSM, calculateVolume()
│   ├── measurement.service.ts       # Cálculos: Haversine (distância), Shoelace (área)
│   ├── measurement-api.service.ts   # REST: getMeasurements, saveMeasurement, deleteMeasurement
│   └── measurement-export.service.ts # Facade → delega para export/*
│       └── export/
│           ├── export-base.service.ts       # Tipos, UTM, downloadString/Blob, buildFilename, escapeXml
│           ├── export-tabular.service.ts    # buildCSV(), buildPNEZD(), buildJSON()
│           ├── export-geo-vector.service.ts # buildGeoJSON(), buildKML(), buildGPX(), buildWKT(), buildGML()
│           └── export-cad.service.ts        # buildDXF(), buildSVG(), buildLandXML()
└── components/
    ├── drawing-toolbar/   # MeasDrawingToolbarComponent — presentational puro
    │                      # @Input: activeTool, hasDataSource, hasDSM, isDrawing, isQuerying, drawingPointsCount
    │                      # @Output: toolActivated, undoRequest, completeRequest, cancelRequest, clearAllRequest
    ├── measurement-item/  # MeasItemComponent — item + painel acordeão
    │                      # @Input: measurement, isVisible, isExpanded, isEditing, editingName
    │                      # @Output: toggleVisibilityChange, focusRequested, toggleDetailRequested, startEditRequested, confirmEditRequested, cancelEditRequested, deleteRequested
    ├── measurement-list/  # MeasListComponent — lista com estado de edição
    │                      # @Input: measurements[], visibleIds, projectId
    │                      # @Output: visibilityChange, focusMeasurement, deleteMeasurement, measurementRenamed, openExport
    │                      # Injeta: MeasurementApiService (renomear)
    └── export-modal/      # MeasurementExportModalComponent
                           # @Input: projectId, measurements
                           # signal: coordFormat
```

---

## Modelo de Dados

```typescript
// measurement-data.ts
type ActiveTool = 'distance' | 'area' | 'volume' | 'height' | null;

interface MeasurementData {
  id: string;           // UUID no frontend, Long no backend (conversão em measurement-api)
  type: 'distance' | 'area' | 'volume' | 'height';
  name: string;
  value: number;
  unit: MeasurementUnit;  // 'm', 'm²', 'm³'
  dataSource: 'orthophoto' | 'dsm' | 'dtm';
  coordinates: [number, number][];  // [lat, lng][]
  precision: number;
  createdAt: string;
}
```

```sql
-- tabela measurements
CREATE TABLE measurements (
  id BIGSERIAL PRIMARY KEY,
  project_id BIGINT NOT NULL REFERENCES projects(id),
  chunk_id BIGINT,
  name VARCHAR,
  type VARCHAR NOT NULL,         -- distance|area|volume|height
  value DOUBLE PRECISION,
  unit VARCHAR,
  data_source VARCHAR,
  coordinates_json TEXT,         -- serializado como JSON
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);
-- índices em project_id, chunk_id, created_at
```

---

## Fluxo de Ferramentas

| Ferramenta | DrawMode | Finalização | Requer DSM |
|-----------|----------|------------|------------|
| Distância | `line` | Clique direito | Não |
| Área | `polygon` | Clique direito (3+ pontos) | Não |
| Altura | `twopoint` | Auto após 2 cliques | Sim |
| Volume | `polygon` | Clique direito | Sim |

**MapDrawingService API:**
```typescript
setMap(map: L.Map): void
startDrawing(mode: 'line' | 'polygon' | 'twopoint'): void
stopDrawing(): void
undo(): void
complete(): void   // força finalização manual
onPointsChanged: (points: L.LatLng[]) => void    // callback
onDrawingCompleted: (points: L.LatLng[]) => void // callback
```

---

## Cálculo de Volume

`DsmElevationService.calculateVolume(polygon, dsmUrl)`:
1. Converte vértices do polígono para CRS nativo do raster
2. Itera todos os pixels dentro do polígono por ray casting
3. Encontra elevação mínima → base do cálculo
4. `Volume = Σ (elevação_pixel − base) × área_pixel_m²`
5. Área do pixel: se UTM → `pixelWidth × pixelHeight`; se EPSG:4326 → converte graus→metros pela latitude média

---

## Endpoints REST (medições)

```
GET    /api/v1/projects/{id}/measurements
GET    /api/v1/projects/{id}/chunks/{chunkId}/measurements
POST   /api/v1/projects/{id}/chunks/{chunkId}/measurements
DELETE /api/v1/projects/{id}/measurements/{measurementId}
PATCH  /api/v1/projects/{id}/measurements/{measurementId}/name   body: { "name": "..." }
GET    /api/v1/projects/{id}/measurements/export/gpkg            GeoPackage binário (Java)
```

---

## Exportação (15 formatos)

| Categoria | Formato | Status no modal | Popup multi-fuso? |
|-----------|---------|----------------|-------------------|
| Tabular | CSV | Disponível | Não (lat/lng sempre) |
| Tabular | PNEZD | Disponível | **Sim** (sempre UTM) |
| Tabular | JSON | Disponível | Não |
| Tabular | XLSX | Disponível | Não |
| Geo-vetorial | GeoJSON | Disponível | Não (WGS84 per RFC 7946) |
| Geo-vetorial | KML | Disponível | Não (WGS84 fixo per spec) |
| Geo-vetorial | GPX | Beta | Não (WGS84 fixo per spec) |
| Geo-vetorial | WKT | Disponível | **Sim** (quando UTM selecionado) |
| Geo-vetorial | GML | Disponível | **Sim** (quando UTM selecionado) |
| Geo-vetorial | TopoJSON | Disponível | Não (WGS84 fixo) |
| Geo-vetorial | GeoPackage | Disponível | **Sim** (quando UTM — query param `?epsg=`) |
| Geo-vetorial | Shapefile | Disponível | **Sim** (quando UTM selecionado) |
| CAD | DXF | Disponível | **Sim** (quando UTM selecionado) |
| CAD | SVG | Disponível | Não (sem CRS — projeção visual) |
| CAD | LandXML | Disponível | **Sim** (sempre UTM — fuso detectado automaticamente) |

> **GeoPackage:** gerado pelo servidor Java (`GeoPackageExportService.java`, sqlite-jdbc 3.45.1.0). O serviço Angular faz `GET /api/v1/projects/{id}/measurements/export/gpkg?coordFormat=...&epsg=...` e baixa o binário.

> **TopoJSON:** gerado em TypeScript puro no browser. WGS84 fixo. Nenhuma dependência externa.

Facade `measurement-export.service.ts` → chama o serviço especializado correto → `export-base.downloadString()` ou `downloadBlob()`.

---

## Padrão Obrigatório: Popup de Multi-Fuso UTM

> **REGRA:** Todo formato que exporta coordenadas UTM **deve** verificar multi-fuso e exibir o popup de seleção. Omitir isso gera arquivos com pontos em fusos diferentes misturados — inválidos para CAD/GIS.

### Quando aplicar

Aplicar em qualquer formato cujo `coordFormat` possa ser `'utm'`. Formatos com CRS fixo (KML, GPX, GeoJSON) estão isentos.

### Como implementar (checklist de 4 passos)

**Passo 1 — `pendingExport` signal no modal**

Adicione o novo identificador de formato ao tipo do signal:

```typescript
// measurement-export-modal.component.ts
pendingExport = signal<'wkt' | 'gml' | 'pnezd' | 'dxf' | 'SEU_FORMATO' | null>(null);
```

**Passo 2 — Método `exportXxx()` no modal**

```typescript
exportSeuFormato(): void {
  if (!this.measurements.length) return;
  // Exibe popup APENAS quando UTM está selecionado e há multi-fuso
  if (this.coordFormat() === 'utm' && this.zoneAnalysis()?.isMultiZone) {
    this.pendingExport.set('SEU_FORMATO');
    return;
  }
  this.exportService.exportToSeuFormato(this.measurements, this.coordFormat(), this.projectId, null);
  this.close();
}
```

> Para PNEZD (sempre UTM independente do seletor): verificar apenas `isMultiZone` sem checar `coordFormat()`.

**Passo 3 — Caso no `confirmExport()`**

```typescript
confirmExport(): void {
  const fmt  = this.pendingExport();
  const epsg = this.selectedEpsg();
  if (!fmt) return;
  switch (fmt) {
    // ... casos existentes ...
    case 'SEU_FORMATO': this.exportService.exportToSeuFormato(this.measurements, this.coordFormat(), this.projectId, epsg); break;
  }
  this.pendingExport.set(null);
  this.close();
}
```

**Passo 4 — `buildXxx()` no serviço especializado**

Assinar `UtmZoneAnalyzerService` e usar `projectToZone()` para reprojetar quando há `targetEpsg`:

```typescript
// export-cad.service.ts | export-geo-vector.service.ts | export-tabular.service.ts
private analyzer = inject(UtmZoneAnalyzerService);

buildSeuFormato(
  entries: RawMeasurementEntry[],
  coordFormat: CoordFormat = 'utm',
  targetEpsg: number | null = null   // <— OBRIGATÓRIO
): string {
  const analysis    = coordFormat === 'utm' ? this.analyzer.analyzeEntries(entries) : null;
  const isMultiZone = analysis?.isMultiZone ?? false;

  // Resolve formato efetivo
  let effectiveFmt: CoordFormat;
  if (coordFormat === 'utm' && isMultiZone && targetEpsg !== null) {
    effectiveFmt = 'utm';   // reprojetar todos para o fuso escolhido
  } else if (coordFormat === 'utm' && isMultiZone) {
    effectiveFmt = 'wgs84'; // fallback seguro: graus decimais
  } else {
    effectiveFmt = coordFormat;
  }

  const reprZone    = targetEpsg !== null ? targetEpsg % 100 : undefined;
  const reprIsNorth = targetEpsg !== null ? targetEpsg < 32700 : false;

  // Por ponto:
  const utm = (isMultiZone && reprZone !== undefined)
    ? this.analyzer.projectToZone(lat, lng, reprZone, reprIsNorth)
    : this.base.wgs84ToUtm(lat, lng);
}
```

E na facade, repassar `targetEpsg`:

```typescript
// measurement-export.service.ts
exportToSeuFormato(entries, coordFormat = 'utm', projectId = 0, targetEpsg: number | null = null): void {
  this.base.downloadString(
    this.cad.buildSeuFormato(entries, coordFormat, targetEpsg),
    this.base.buildFilename(projectId, 'ext', 'ext', coordFormat),
    'mime/type;charset=utf-8;'
  );
}
```

### Formatos isentos (não precisam do padrão)

| Formato | Motivo |
|---------|--------|
| GeoJSON | RFC 7946 exige WGS84 — geometria sempre em graus |
| KML | Spec KML 2.2 exige WGS84 |
| GPX | Spec GPX exige WGS84 |
| CSV | Respeita o `coordFormat` do usuário; se UTM escolhido cada ponto vai para seu fuso natural; mistura de fusos é aceitável em CSV pois cada linha tem coluna "fuso" |

---

## Regra: Fonte Única de Conversão UTM

> **NUNCA duplique a implementação WGS84→UTM.** Duplicatas independentes geram divergências entre o que a UI exibe e o que os arquivos exportados contêm.

### Funções centralizadas (usar sempre)

| Necessidade | Função | Arquivo |
|------------|---------|---------|
| String formatada para UI (`333.000,123 E / 7.399.000,456 N  23K`) | `ExportBaseService.wgs84ToUtmStr(lat, lng)` | `export-base.service.ts` |
| Valores numéricos separados para arquivos (DXF, CSV, PNEZD…) | `ExportBaseService.wgs84ToUtm(lat, lng)` | `export-base.service.ts` |
| Reprojetar ponto para fuso específico (multi-fuso) | `UtmZoneAnalyzerService.projectToZone(lat, lng, zone, isNorth)` | `utm-zone-analyzer.service.ts` |

### O que causou o bug (histórico)

`MeasItemComponent` (acordeão de detalhes) tinha 40 linhas de implementação UTM local copiando o mesmo algoritmo do `ExportBaseService`. Qualquer diferença mínima (arredondamento, coeficiente) causava discrepância entre o valor exibido na UI e o valor no DXF exportado.

**Correção (28/02/2026):** `toUtmStr()` no `MeasItemComponent` foi simplificada para:
```typescript
toUtmStr(lat: number, lng: number): string {
  return this.base.wgs84ToUtmStr(lat, lng);
}
```
`ExportBaseService` foi injetado no componente. A UI e todos os formatos de exportação agora compartilham o mesmo code path.

---

## Painel de Detalhes (acordeão)

Ao expandir `MeasItemComponent`, exibe 3 seções:
1. **Coordenadas dos Pontos** — tabela `Pt | Lat (°) | Lng (°) | UTM (WGS84)`
2. **Trechos Parciais** — para distância: `Pt1→Pt2 | dist`; para área: segmentos + perímetro total
3. **Área** (apenas tipo `area`) — m², Hectares, Alqueires paulistas (1 alq = 24.200 m²)
