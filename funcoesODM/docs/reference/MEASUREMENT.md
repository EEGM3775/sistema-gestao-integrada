# Medições — Referência Completa

**Status:** Distância | Área | Volume (DSM) | Altura (DSM) | Exportação (17 formatos) | Pointcloud pendente  
**Última Atualização:** 6 de maio de 2026

---

## Visão Geral

Módulo de medições integrado na aba **"Medições"** do detalhe de projeto.
Permite visualizar ortofoto georreferenciada (GeoTIFF) e realizar medições topográficas:
distância, área de polígono, volume acima do ponto mais baixo e diferença de altura entre dois pontos.
Volume e Altura requerem DSM processado.

---

## Estrutura de Componentes

\\\
frontend/src/app/
 features/
    projects/components/
       measurement-tab/
           measurement-tab.component.ts
           measurement-tab.component.html
           measurement-tab.component.scss
   
    measurement/
        services/
           map-drawing.service.ts
           dsm-elevation.service.ts
           measurement.service.ts
           measurement-api.service.ts
           measurement-export.service.ts
           export/
               export-base.service.ts
               utm-zone-analyzer.service.ts
               export-tabular.service.ts
               export-geo-vector.service.ts
               export-cad.service.ts
        components/
            export-modal/
                measurement-export-modal.component.ts
                measurement-export-modal.component.html
                measurement-export-modal.component.scss

 shared/viewers/
     orthophoto-viewer/orthophoto-viewer.component.ts
     dem-viewer/dem-viewer.component.ts
     pointcloud-viewer/pointcloud-viewer.component.ts
\\\

---

## Status Rápido

### Ferramentas

| Ferramenta | Status | Precisão |
|---|---|---|
| Distância | Funcional | Vincenty WGS84 (~0.06 mm) |
| Área | Funcional | Trapézio esférico + raio Gauss WGS84 |
| Volume (DSM) | Funcional | Pixel-a-pixel, base = ponto mais baixo |
| Altura (DSM) | Funcional | Requer DSM processado |
| Perfil de Elevação | Funcional | Chart.js |

### Exportação — 17 formatos ativos

| Categoria | Formatos |
|---|---|
| GIS / Web | CSV, GeoJSON, KML, GPX, WKT, GML, TopoJSON, GeoPackage, Shapefile |
| Topografia / CAD | PNEZD, LandXML, GCP (ODM), DXF, SVG |
| Planilha / Relatório | JSON, XLSX, PDF |

### Viewers

| Viewer | Status |
|---|---|
| Orthophoto (GeoTIFF) | Funcional |
| DEM/DSM | Estrutura básica |
| Nuvem de Pontos 3D | Pendente |

---

## Ferramentas Implementadas

### 1. Distância
- Cliques adicionam pontos; polilinha desenhada em tempo real
- Clique direito finaliza
- Cálculo por **fórmula de Vincenty WGS84** (elipsoide real, ~0.06 mm de precisão)
- Label azul sobre o último ponto com valor total; labels menores em cada segmento

### 2. Área
- Mesmo fluxo da distância, polígono preenchido (fill semi-transparente durante o desenho)
- Ao finalizar (clique direito, 3+ pontos), polígono permanente com `fillOpacity: 0.25`
- Cálculo por **fórmula trapezoidal esférica** com **raio de Gauss WGS84** (R = √(M·N) na latitude média)

### 3. Altura (Diferença de Elevação via DSM)
- Disponível apenas com DSM processado (`hasDSM()` = true)
- Modo `twopoint`: clique A → clique B → auto-finaliza
- Exibe: `Pt A: 123.45 m | Pt B: 130.67 m | Δ: +7.22 m`

### 4. Volume (acima do ponto mais baixo)
- Disponível apenas com DSM; mesmo fluxo de polígono
- `DsmElevationService.calculateVolume()`: converte vértices para CRS nativo → itera pixels (ray casting) → base = elevação mínima → `volume = Σ (elev − base) × área_pixel_m²`
- Exibe: `Vol: XX.XXX m³ | Base: YY.YY m | NNN px`

---

## Arquitetura dos Serviços

### `MapDrawingService`

```typescript
type DrawMode = 'line' | 'polygon' | 'twopoint'
```

| Modo | Comportamento | Finalização |
|---|---|---|
| `line` | Polilinha com labels de segmento | Clique direito |
| `polygon` | Polilinha + fill durante desenho | Clique direito (mín. 3 pontos) |
| `twopoint` | Apenas 2 pontos, sem labels | Automática após 2º clique |

**Callbacks:** `onPointsChanged(points)` · `onDrawingCompleted(points)`  
**Labels:** segmento `iconSize: [80, 24]`; total `.total` com `iconSize: undefined` + `transform: translate(-50%, calc(-100% - 10px))`

### `DsmElevationService`

```typescript
getElevationAt(url, lat, lng): Promise<ElevationResult>   // { elevation, valid }
calculateVolume(url, polygon): Promise<VolumeResult>       // { volume, baseElevation, pixelCount, valid }
```

1. Baixa GeoTIFF via `fetch`, parse com `parseGeoraster()`, cache em `Map<url, GeoRaster>`
2. Converte WGS84 → CRS nativo: EPSG:4326 direto · EPSG:326xx UTM Norte · EPSG:327xx UTM Sul
3. `col = floor((x − xmin) / pixelWidth)` · `row = floor((ymax − y) / pixelHeight)`
4. Conversão WGS84→UTM: TypeScript puro, série de 6 termos (**sem** `proj4`)

### `MeasurementService`

```typescript
calculateDistance(points): MeasurementResult   // Vincenty WGS84 elipsoide
calculateArea(points, unit): MeasurementResult  // Trapézio esférico + raio Gauss WGS84
```

---

## Bugs Corrigidos

### 21/02/2026

| Problema | Causa | Solução |
|---|---|---|
| Volume/Altura calculavam distância | `default` no switch caía na distância | Adicionado caso explícito para `volume`/`height` |
| `unit: ''` incompatível | Campo inicializado com string vazia | Alterado para `MeasurementUnit.METERS` |
| Campo `precision` ausente | Interface exige `precision` | Adicionado `precision: 2` |
| `L.DomEvent.preventDefault(e)` tipo errado | `e` era `L.LeafletEvent` | Corrigido para `e.originalEvent.preventDefault()` |

### 20/02/2026

| Problema | Causa | Solução |
|---|---|---|
| HTTP 500 no download | URL incorreta | Corrigido para `ChunkController` |
| HTTP 404 | `processing_tasks` vazia | Usar `chunks.id` na URL |
| OSM retornava 400 | Zoom 22 > max OSM (19) | `maxNativeZoom: 19` |
| Spinner infinito (Zone.js) | Promise fora da Zone | `ChangeDetectorRef.detectChanges()` |
| Spinner infinito (ID conflito) | `id="orthophoto-map"` duplicado | `@ViewChild('mapContainer')` |
| OSM sobrepondo ortofoto | Z-index conflito | Pane `orthophotoPane` z-index 300 |
| Viewer colapsado | `app-measurement-tab` fora do seletor | Adicionado ao seletor |

---

## Decisões Técnicas

### Label do mapa com tamanho automático

O Leaflet `L.divIcon` normalmente requer `iconSize` fixo. Para textos variáveis:

```typescript
icon: L.divIcon({
  className: 'measurement-label measurement-label-total',
  html: `<div class="measurement-label-content total">${label}</div>`,
  iconSize: undefined,
  iconAnchor: undefined
})
```

```scss
.measurement-label-content.total {
  transform: translate(-50%, calc(-100% - 10px));
  white-space: nowrap;
  display: inline-block;
}
```

### `proj4` nos serviços de exportação

- **`ExportBaseService.wgs84ToUtm()`** — `proj4('EPSG:4326', '+proj=utm +zone=N +south +datum=WGS84 ...')`
- **`UtmZoneAnalyzerService._forwardUtmToZone()`** — substituiu série de Helmert (46 linhas) por 3 linhas proj4
- `DsmElevationService` mantém TypeScript puro (adequado para leitura de pixels de raster)

### Finalização por clique direito

Alterado de duplo clique para clique direito para evitar conflitos com zoom do Leaflet.

---

## UX e Persistência

**Persistência:** medições salvas automaticamente no PostgreSQL ao concluir; carregadas ao abrir o projeto.  
`measurement-api.service.ts` — `getMeasurements` · `saveMeasurement` · `deleteMeasurement`

**Sidebar retrátil:** botão `◀` / `▶`; mapa expande a 100% quando colapsado; `transition: width 0.3s`.

**Visibilidade individual:** `WritableSignal<Set<string>>`; desmarcar remove a camada Leaflet sem deletar.

**Edição de nome inline:** duplo-clique ativa `<input>`; Enter/blur confirma; Escape cancela.  
`PATCH /api/v1/projects/{projectId}/measurements/{measurementId}/name`

**Painel de detalhes (acordeão):** Coordenadas (Lat/Lng/UTM) · Trechos Parciais · Área (m²/ha/alqueires) · Informações.

---

## Exportação — Interface do Modal

Botão **Exportar** na linha do título "Medições" (visível quando há ≥ 1 medição).  
Modal com grade de cards por categoria; todos os 16 formatos implementados estão ativos.

### Opções globais

| Opção | Valores | Aplica-se a |
|---|---|---|
| Sistema de coordenadas | `WGS84` · `UTM` | CSV, PNEZD, WKT, DXF, LandXML, JSON |
| Separador | `,` · `;` · espaço | Apenas CSV e PNEZD |

Formatos com CRS fixo (ignoram o seletor): GeoJSON · KML · GPX (WGS84 fixo); SVG (sem CRS).

---

## Exportação — Arquitetura (Facade)

```
measurement/
├── measurement-export.service.ts         ← Facade — sem lógica de formato
└── export/
    ├── export-base.service.ts             ← Tipos, UTM (proj4), download, buildFilename
    ├── export-tabular.service.ts          ← buildCSV(), buildPNEZD(), buildJSON()
    ├── export-geo-vector.service.ts       ← buildGeoJSON(), buildKML(), buildGPX(), buildWKT(), buildGML()
    ├── export-cad.service.ts              ← buildDXF(), buildSVG(), buildLandXML()
    ├── export-shapefile.service.ts        ← binário .shp/.shx/.dbf/.prj + fflate ZIP
    ├── export-xlsx.service.ts             ← ExcelJS, 2 abas
    ├── export-topojson.service.ts         ← TypeScript puro, WGS84 fixo
    ├── export-geopackage.service.ts       ← GET /api/.../export/gpkg → Java (sqlite-jdbc 3.45.1.0)
    └── export-pdf.service.ts              ← jsPDF + jspdf-autotable, browser-side
```

**GeoPackage:** gerado no **servidor Java** (`GeoPackageExportService.java`). Angular envia GET e faz download do binário. Sem WASM no browser.

### Assinatura da Facade

```typescript
exportToCSV(entries, coordFormat, separator): void
exportToGeoJSON(entries, coordFormat): void
exportToKML(entries): void
exportToGPX(entries): void
exportToWKT(entries, coordFormat): void
exportToGML(entries, coordFormat): void
exportToPNEZD(entries, separator): void                   // sempre UTM
exportToLandXML(entries, projectId?, targetEpsg?): void  // sempre UTM
exportToDXF(entries, coordFormat): void
exportToSVG(entries, coordFormat): void
exportToJSON(entries, coordFormat): void
exportToTopoJSON(entries, projectId): void                // WGS84 fixo
exportToGeoPackage(entries, coordFormat, projectId, targetEpsg?): Promise<void>
exportToPDF(entries, coordFormat, projectId): void
exportToGCP(entries, projectId): void
```

### Popup de Multi-Fuso UTM

Dispara quando `UtmZoneAnalyzerService.analyzeEntries()` retorna `isMultiZone = true`.

| Formato | Popup? |
|---|---|
| PNEZD, LandXML | Sim — sempre UTM |
| WKT, GML, DXF, Shapefile, GeoPackage | Sim — quando UTM selecionado |
| GeoJSON, KML, GPX, TopoJSON, SVG, GCP | Não — CRS fixo |
| PDF | Não — fuso por linha |

### Convenção de Nomes de Arquivo

```
medicoes_projeto_{id}_{formato}_{coordFormat}_{YYYYMMDD}.{ext}
```

Exemplos: `medicoes_projeto_5_dxf_utm_20260228.dxf` · `medicoes_projeto_5_kml_20260228.kml`

---

## Exportação — Catálogo Completo

`[OK]` implementado · `[PLAN]` planejado

### GIS / Web

| Formato | Ext. | CRS | Compatibilidade |
|---|---|---|---|
| CSV `[OK]` | `.csv` | WGS84 ou UTM | Excel, QGIS, pandas, Civil 3D |
| GeoJSON `[OK]` | `.geojson` | WGS84 fixo | QGIS, ArcGIS, Mapbox, PostGIS |
| KML `[OK]` | `.kml` | WGS84 fixo | Google Earth, QGIS, ArcGIS |
| GPX `[OK]` | `.gpx` | WGS84 fixo | Garmin, Trimble, QGIS |
| WKT `[OK]` | `.txt` | WGS84 ou UTM | PostGIS, SpatiaLite, SQL Server |
| GML `[OK]` | `.gml` | WGS84 ou UTM | QGIS, GeoServer, IBGE/INDE |
| TopoJSON `[OK]` | `.topojson` | WGS84 fixo | D3.js, Mapshaper |
| GeoPackage `[OK]` | `.gpkg` | WGS84 ou UTM | QGIS, ArcGIS Pro, GDAL |
| Shapefile `[OK]` | `.zip` | WGS84 ou UTM | ArcGIS, QGIS, GDAL |

### Topografia / CAD

| Formato | Ext. | CRS | Compatibilidade |
|---|---|---|---|
| PNEZD `[OK]` | `.txt` | UTM fixo | Carlson, Topcon, Civil 3D, Trimble |
| LandXML `[OK]` | `.xml` | UTM fixo | Civil 3D, Trimble BC, 12d, Bentley |
| GCP (ODM) `[OK]` | `.txt` | WGS84 fixo | ODM, WebODM, OpenDroneMap |
| DXF `[OK]` | `.dxf` | WGS84 ou UTM | AutoCAD, BricsCAD, QGIS, LibreCAD |
| SVG `[OK]` | `.svg` | Sem CRS | Inkscape, Illustrator, Word, PDF |

### Planilha / Relatório

| Formato | Ext. | Compatibilidade |
|---|---|---|
| JSON `[OK]` | `.json` | Qualquer plataforma |
| XLSX `[OK]` | `.xlsx` | Excel, LibreOffice, Google Sheets |
| PDF `[OK]` | `.pdf` | Universal — jsPDF browser-side |

### Fotogrametria (planejados)

| Formato | Detalhes |
|---|---|
| IFC `[PLAN]` | ISO 16739; obrigatório em projetos públicos BR (Decreto 10.306/2021) |
| E57 `[PLAN]` | ASTM E2807; implementar junto ao Pointcloud Viewer |
| RW5 `[PLAN]` | Dados brutos de estação total; nicho — implementar sob demanda |

---

## Precisão Geodésica (Sessão 6 — 28/02/2026)

### Migrações realizadas

| Componente | Antes | Depois | Ganho |
|---|---|---|---|
| `MeasurementService.haversineDistance()` | Haversine esfera R=6 371 000 m | **Vincenty WGS84** elipsoide | ~0.51% em N-S |
| `meas-item — haversine2D()` | Haversine esfera | **Vincenty WGS84** | idem |
| `map-drawing — haversineDistance()` | Haversine esfera | **Vincenty WGS84** | idem |
| `MeasurementService.sphericalPolygonArea()` | Girard R=6 371 000 fixo | **Trapézio esférico + Gauss WGS84** | ~0.46% em áreas |
| `ExportBaseService.wgs84ToUtm()` | Série de Helmert | **proj4** | Coincide com QGIS/AutoCAD |
| `UtmZoneAnalyzerService._forwardUtmToZone()` | Helmert 46 linhas | **proj4** (3 linhas) | Coincide com QGIS/AutoCAD |

### Constantes WGS84

| Símbolo | Valor | Significado |
|---|---|---|
| a | 6 378 137.0 m | Semieixo maior |
| b | 6 356 752.314 245 m | Semieixo menor |
| f | 1 / 298.257 223 563 | Achatamento |
| e² | 0.006 694 379 990 14 | Primeira excentricidade² |
| R_Gauss (lat −13°) | ≈ 6 358 902 m | Raio médio de Gauss √(M·N) |

### Comparação DB vs DXF (dados de teste reais)

| ID | Nome | Tipo | DB | DXF (UTM 24S) | Diferença | Causa |
|---|---|---|---|---|---|---|
| 15 | Distância 1 | distance | 19.301 m | 19.294 m | −0.039% | k₀=0.9996 UTM ✅ |
| 18 | Distância 4 | distance | 30.832 m | 30.820 m | −0.039% | k₀ ✅ |
| 24 | Distância 10 | distance | 25.678 m | 25.668 m | −0.039% | k₀ ✅ |
| 26 | Distância 12 | distance | 3 232 748 m | 3 373 609 m | +4.36% | Fusos distintos (24S↔19S) ✅ |
| 19 | Área 5 | area | 55.416 m² | 55.374 m² | −0.077% | k₀²=0.9992 ✅ |
| 22 | Área 8 | area | 27.771 m² | 27.750 m² | −0.077% | k₀² ✅ |
| 20 | Altura 6 | height | −0.004608 m | −0.004608 m | 0.000% | ΔZ idêntico ✅ |
| 17 | Volume 3 | volume | 239.415 m³ | 301.749 m² (base) | — | m³ não no DXF |

> ~0.039% em distâncias = k₀=0.9996 · ~0.077% em áreas = k₀² · 0.000% em alturas com Z · volumes sem representação no DXF

---

## Roadmap

### Concluídos
- [x] Persistência no backend — Sessão 3
- [x] Sidebar retrátil, visibilidade, edição de nome, painel de detalhes — Sessão 4
- [x] Modal de exportação, facade + 4 serviços especializados — Sessão 5
- [x] 11 formatos ativos na UI — Sessões 5 e 6
- [x] Precisão geodésica: Vincenty WGS84, Gauss √(M·N), proj4 — Sessão 6
- [x] Shapefile (fflate), XLSX (ExcelJS), TopoJSON, GeoPackage (Java sqlite-jdbc), PDF, GCP — 17 formatos ativos

### Pendentes

| Prioridade | Item |
|---|---|
| P3 | Cache ArrayBuffer do orthophoto (evitar re-download) |
| P3 | Otimizar `calculateVolume` para DSMs grandes (Web Worker) |
| P3 | Exportação IFC — Decreto 10.306/2021 |
| P3 | Exportação E57 — junto ao Pointcloud Viewer |

---

## Referências Técnicas

- [georaster-layer-for-leaflet](https://github.com/GeoTIFF/georaster-layer-for-leaflet)
- [georaster](https://github.com/GeoTIFF/georaster)
- [Leaflet Custom Panes](https://leafletjs.com/examples/map-panes/)
- [Leaflet divIcon](https://leafletjs.com/reference.html#divicon)
- [Angular Signals](https://angular.dev/guide/signals)
- [Vincenty Formulae](https://en.wikipedia.org/wiki/Vincenty_formulae)
- [LandXML 1.2 Schema](http://www.landxml.org/schema/LandXML-1.2)
- [proj4js](https://github.com/proj4js/proj4js)

---

**Última atualização:** 1 de março de 2026
