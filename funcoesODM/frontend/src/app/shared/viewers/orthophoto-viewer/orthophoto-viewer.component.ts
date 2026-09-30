/**
 * Orthophoto Viewer - Professional Implementation
 * 
 * Visualizador profissional de ortofoto com suporte completo a:
 * - GeoTIFF rendering nativo (georaster)
 * - Tiles PNG (fallback)
 * - Ferramentas de medição integradas
 * - Controles de camada e opacidade
 * 
 * @engineered-for Engenheiros e profissionais de fotogrametria
 */

import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, AfterViewInit, ViewChild, ElementRef, ChangeDetectorRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Subject, firstValueFrom } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { ResultsService } from '../../../features/projects/services/results.service';
import { GeoTiffCacheService } from '../../../core/services/geotiff-cache.service';
import * as L from 'leaflet';
import parseGeoraster from 'georaster';
// @ts-ignore
import GeoRasterLayer from 'georaster-layer-for-leaflet';

type RenderMode = 'geotiff' | 'tiles' | 'fallback';

@Component({
    selector: 'app-orthophoto-viewer',
    imports: [
        CommonModule
    ],
    template: `
    <div class="orthophoto-viewer">
      <!-- Mapa Leaflet -->
      <div #mapContainer class="map-canvas"></div>

      <!-- Controles de Camada -->
      @if (orthophotoLayer && !isLoading && !errorMessage) {
        <div class="layer-controls">
          <div class="control-group">
            <label>
              <span class="control-icon">🎨</span>
              <span>Opacidade: {{ opacityPercent }}%</span>
            </label>
            <input 
              type="range" 
              min="0" 
              max="100" 
              [value]="opacityPercent"
              (input)="onOpacityChange($event)"
              class="opacity-slider"
            />
          </div>
          <div class="control-group">
            <label>
              <span class="control-icon">🗺️</span>
              <span>Base: {{ activeBasemap }}</span>
            </label>
            <select (change)="onBasemapChange($event)" class="basemap-select">
              <option value="osm">OpenStreetMap</option>
              <option value="satellite">Satélite</option>
              <option value="terrain">Terreno</option>
              <option value="none">Nenhum</option>
            </select>
          </div>
          <div class="info-badge">
            <span class="badge-icon">⚡</span>
            <span>{{ renderMode === 'geotiff' ? 'GeoTIFF' : renderMode === 'tiles' ? 'Tiles' : 'Fallback' }}</span>
          </div>
        </div>
      }

      <!-- Loading Overlay -->
      @if (isLoading) {
        <div class="loading-overlay">
          <div class="spinner"></div>
          <p>{{ loadingMessage }}</p>
          @if (loadingProgress > 0) {
            <div class="progress-bar">
              <div class="progress-fill" [style.width.%]="loadingProgress"></div>
            </div>
          }
        </div>
      }

      <!-- Error Overlay -->
      @if (errorMessage) {
        <div class="error-overlay">
          <div class="error-content">
            <span class="error-icon">⚠️</span>
            <h3>Erro ao Carregar Ortofoto</h3>
            <p>{{ errorMessage }}</p>
            @if (errorDetails) {
              <details class="error-details">
                <summary>Detalhes técnicos</summary>
                <pre>{{ errorDetails }}</pre>
              </details>
            }
          </div>
        </div>
      }
    </div>
  `,
    styles: [`
    .orthophoto-viewer {
      position: relative;
      width: 100%;
      height: 100%;
      background: #0f172a;
    }

    .map-canvas {
      width: 100%;
      height: 100%;
      z-index: 1;
    }

    /* Layer Controls */
    .layer-controls {
      position: absolute;
      top: 10px;
      right: 10px;
      background: rgba(15, 23, 42, 0.95);
      backdrop-filter: blur(10px);
      padding: 1rem;
      border-radius: 8px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
      z-index: 1000;
      min-width: 250px;
      border: 1px solid rgba(59, 130, 246, 0.2);
    }

    .control-group {
      margin-bottom: 0.75rem;
    }

    .control-group:last-child {
      margin-bottom: 0;
    }

    .control-group label {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      color: #e2e8f0;
      font-size: 0.875rem;
      font-weight: 500;
      margin-bottom: 0.5rem;
    }

    .control-icon {
      font-size: 1.2rem;
    }

    .opacity-slider,
    .basemap-select {
      width: 100%;
      padding: 0.5rem;
      background: rgba(30, 41, 59, 0.8);
      border: 1px solid rgba(59, 130, 246, 0.3);
      border-radius: 4px;
      color: #e2e8f0;
      font-size: 0.875rem;
    }

    .opacity-slider {
      cursor: pointer;
    }

    .opacity-slider::-webkit-slider-thumb {
      appearance: none;
      width: 16px;
      height: 16px;
      background: #3b82f6;
      border-radius: 50%;
      cursor: pointer;
    }

    .info-badge {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem;
      background: rgba(59, 130, 246, 0.15);
      border: 1px solid rgba(59, 130, 246, 0.3);
      border-radius: 4px;
      color: #93c5fd;
      font-size: 0.8rem;
      font-weight: 600;
      margin-top: 0.5rem;
    }

    .badge-icon {
      font-size: 1rem;
    }

    /* Loading Overlay */
    .loading-overlay {
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(15, 23, 42, 0.98);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      z-index: 2000;
      gap: 1.5rem;
    }

    .spinner {
      width: 60px;
      height: 60px;
      border: 4px solid rgba(59, 130, 246, 0.2);
      border-top: 4px solid #3b82f6;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    .loading-overlay p {
      color: #94a3b8;
      font-size: 1rem;
      margin: 0;
      font-weight: 500;
    }

    .progress-bar {
      width: 300px;
      height: 4px;
      background: rgba(59, 130, 246, 0.2);
      border-radius: 2px;
      overflow: hidden;
    }

    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, #3b82f6, #60a5fa);
      transition: width 0.3s ease;
    }

    /* Error Overlay */
    .error-overlay {
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(15, 23, 42, 0.98);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 2001;
    }

    .error-content {
      text-align: center;
      color: white;
      padding: 2rem;
      max-width: 600px;
    }

    .error-icon {
      font-size: 4rem;
      display: block;
      margin-bottom: 1rem;
    }

    .error-content h3 {
      color: #ef4444;
      margin: 0 0 1rem 0;
      font-size: 1.5rem;
    }

    .error-content p {
      color: #94a3b8;
      margin: 0 0 1rem 0;
      font-size: 0.95rem;
      line-height: 1.6;
    }

    .error-details {
      margin-top: 1rem;
      text-align: left;
    }

    .error-details summary {
      cursor: pointer;
      color: #60a5fa;
      font-size: 0.875rem;
      margin-bottom: 0.5rem;
    }

    .error-details pre {
      background: rgba(0, 0, 0, 0.3);
      padding: 1rem;
      border-radius: 4px;
      color: #f87171;
      font-size: 0.8rem;
      overflow-x: auto;
      max-height: 200px;
    }

    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
  `]
})
export class OrthophotoViewerComponent implements OnInit, AfterViewInit, OnDestroy {
  @Input() projectId!: number;
  @Input() taskId?: number;
  @Input() nodeodmTaskId?: string;
  @Input() orthophotoUrl?: string;
  @Input() center: [number, number] = [-23.5505, -46.6333];
  @Input() zoom = 18;

  /** Sinaliza visibilidade — chama invalidateSize quando a aba volta a ficar visivel */
  @Input() set visible(val: boolean) {
    if (val && this.map) {
      setTimeout(() => { try { this.map?.invalidateSize(); } catch {} }, 80);
    }
  }

  /** Emite a instancia do mapa Leaflet quando estiver pronto */
  @Output() mapReady = new EventEmitter<L.Map>();

  @ViewChild('mapContainer') private mapContainerRef!: ElementRef<HTMLDivElement>;

  private destroy$ = new Subject<void>();
  private resultsService = inject(ResultsService);
  private http = inject(HttpClient);
  private cdr = inject(ChangeDetectorRef);
  private geoTiffCache = inject(GeoTiffCacheService);
  private map: L.Map | null = null;
  orthophotoLayer: any = null;
  private baseLayer: L.TileLayer | null = null;
  private basemaps: Map<string, L.TileLayer> = new Map();
  
  renderMode: RenderMode = 'geotiff';
  isLoading = true;
  loadingMessage = 'Inicializando visualizador...';
  loadingProgress = 0;
  errorMessage = '';
  errorDetails = '';
  opacityPercent = 80;
  activeBasemap = 'osm';

  ngOnInit(): void {
    console.log('🗺️ OrthophotoViewer initialized:', {
      projectId: this.projectId,
      taskId: this.taskId,
      nodeodmTaskId: this.nodeodmTaskId,
      orthophotoUrl: this.orthophotoUrl
    });
  }

  ngAfterViewInit(): void {
    setTimeout(() => this.initializeMap(), 100);
  }

  ngOnDestroy(): void {
    if (this.map) {
      this.map.remove();
      this.map = null;
    }
    this.destroy$.next();
    this.destroy$.complete();
  }

  /**
   * Inicializa o mapa Leaflet com basemap
   */
  private initializeMap(): void {
    try {
      this.loadingMessage = 'Criando mapa base...';
      
      this.map = L.map(this.mapContainerRef.nativeElement, {
        center: this.center,
        zoom: this.zoom,
        maxZoom: 30,       // zoom 30 ≈ sub-milímetro; tiles do basemap esticam a partir do maxNativeZoom de cada camada
        zoomControl: true,
        attributionControl: true
      });

      // Inicializar basemaps
      this.initializeBasemaps();
      
      // Adicionar basemap padrao
      this.baseLayer = this.basemaps.get('osm')!;
      this.baseLayer.addTo(this.map);

      // Emitir instancia do mapa para componentes pais
      this.mapReady.emit(this.map);

      // Carregar ortofoto se disponivel
      if (this.taskId && this.nodeodmTaskId) {
        this.loadOrthophoto();
      } else {
        this.isLoading = false;
        this.errorMessage = 'TaskId ou NodeODM TaskId não fornecido';
        console.error('❌ Missing required IDs');
      }
    } catch (error) {
      console.error('Erro ao inicializar mapa:', error);
      this.isLoading = false;
      this.errorMessage = 'Erro ao inicializar o visualizador de mapas';
      this.errorDetails = error instanceof Error ? error.message : String(error);
    }
  }

  /**
   * Inicializa os basemaps disponíveis
   */
  private initializeBasemaps(): void {
    this.basemaps.set('osm', L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
      maxZoom: 30,
      maxNativeZoom: 19  // OSM: tiles nativos até zoom 19; estica acima disso
    }));

    // Google Satellite: melhor cobertura nativa para o Brasil (até zoom 21)
    // Substitui ESRI que retornava "Map data not yet available" em zooms altos
    this.basemaps.set('satellite', L.tileLayer('https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', {
      attribution: '© Google',
      subdomains: ['0', '1', '2', '3'],
      maxZoom: 30,
      maxNativeZoom: 21  // Google Satellite: tiles nativos até zoom 21; estica acima disso
    }));

    this.basemaps.set('terrain', L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenTopoMap contributors',
      maxZoom: 30,
      maxNativeZoom: 17  // OpenTopoMap: tiles nativos até zoom 17; estica acima disso
    }));
  }

  /**
   * Carrega ortofoto tentando múltiplas estratégias
   */
  private async loadOrthophoto(): Promise<void> {
    if (!this.projectId || !this.taskId || !this.nodeodmTaskId || !this.map) {
      this.isLoading = false;
      return;
    }

    try {
      // Tentar GeoTIFF primeiro (fonte mais confiável via backend)
      const geotiffSuccess = await this.tryLoadGeoTIFF();
      if (geotiffSuccess) return;

      // Tentar tiles PNG como fallback (NodeODM direto)
      const tilesSuccess = await this.tryLoadTiles();
      if (tilesSuccess) return;

      // Fallback erro
      throw new Error('Nenhum método de renderização disponível');

    } catch (error) {
      console.error('Erro ao carregar ortofoto:', error);
      this.isLoading = false;
      this.errorMessage = 'Não foi possível carregar a ortofoto';
      this.errorDetails = error instanceof Error ? error.message : String(error);
      this.cdr.detectChanges();
    }
  }

  /**
   * Tenta carregar usando tiles PNG
   */
  private async tryLoadTiles(): Promise<boolean> {
    try {
      this.loadingMessage = 'Verificando tiles PNG...';
      this.loadingProgress = 10;

      const tilesUrl = `/nodeodm-api/task/${this.nodeodmTaskId}/tiles/{z}/{x}/{y}.png`;
      
      // Testar se tiles existem
      const testUrl = `/nodeodm-api/task/${this.nodeodmTaskId}/tiles/18/0/0.png`;
      const response = await fetch(testUrl, { method: 'HEAD' });
      
      if (response.ok) {
        this.loadingMessage = 'Carregando tiles PNG...';
        this.loadingProgress = 50;
        
        this.orthophotoLayer = L.tileLayer(tilesUrl, {
          maxZoom: 22,
          tms: false,
          opacity: this.opacityPercent / 100
        });
        
        this.orthophotoLayer.addTo(this.map!);

        // Tentar centralizar o mapa na area da ortofoto via NodeODM task info
        // Se falhar, o mapa permanece no centro/zoom passados via @Input
        try {
          const taskInfo = await firstValueFrom(
            this.http.get<any>(`/nodeodm-api/task/${this.nodeodmTaskId}/info`)
          );
          // NodeODM retorna bounds como array [lng_min, lat_min, lng_max, lat_max]
          const b = taskInfo?.bounds?.value;
          if (Array.isArray(b) && b.length === 4) {
            const layerBounds = L.latLngBounds([b[1], b[0]], [b[3], b[2]]);
            this.map!.fitBounds(layerBounds, { maxZoom: 19 });
          }
        } catch {
          // Task info nao disponivel — mapa permanece no centro padrao
        }

        this.renderMode = 'tiles';
        this.isLoading = false;
        this.loadingProgress = 100;
        this.cdr.detectChanges();
        console.log('[OK] Ortofoto carregada via Tiles PNG');
        return true;
      }
    } catch (error) {
      console.log('⚠️ Tiles PNG não disponíveis, tentando GeoTIFF...');
    }
    
    return false;
  }

  /**
   * Tenta carregar GeoTIFF nativo
   */
  private async tryLoadGeoTIFF(): Promise<boolean> {
    try {
      this.loadingMessage = 'Carregando GeoTIFF...';
      this.loadingProgress = 20;

      // Usar URL do backend se disponível, senão construir a partir de projectId/taskId
      const geotiffUrl = this.orthophotoUrl || 
        (this.projectId && this.taskId 
          ? `/api/v1/projects/${this.projectId}/tasks/${this.taskId}/download/orthophoto.tif`
          : null);

      if (!geotiffUrl) {
        console.warn('❌ Sem URL disponível para o GeoTIFF');
        return false;
      }
      
      const fromCache = this.geoTiffCache.has(geotiffUrl);
      console.log(fromCache ? '⚡ GeoTIFF do cache:' : '📥 Baixando GeoTIFF:', geotiffUrl);

      const response = await this.geoTiffCache.get(geotiffUrl, (p) => {
        this.loadingProgress = 20 + Math.round(p.percent * 0.4); // 20–60%
        const mb    = (p.receivedBytes / 1024 / 1024).toFixed(0);
        const total = p.totalBytes > 0 ? ` / ${(p.totalBytes / 1024 / 1024).toFixed(0)}` : '';
        this.loadingMessage = `Baixando ortofoto... ${mb}${total} MB`;
        this.cdr.detectChanges();
      });

      console.log('✅ GeoTIFF pronto:', (response.byteLength / 1024 / 1024).toFixed(1), 'MB', fromCache ? '(cache)' : '(download)');

      // Validate TIFF magic bytes
      const dataView = new DataView(response);
      const byte1 = dataView.getUint8(0);
      const byte2 = dataView.getUint8(1);
      
      // Debug: print first 16 bytes
      const firstBytes: string[] = [];
      for (let i = 0; i < Math.min(16, response.byteLength); i++) {
        firstBytes.push('0x' + dataView.getUint8(i).toString(16).padStart(2, '0'));
      }
      console.log('📋 Primeiros 16 bytes:', firstBytes.join(' '));
      
      // TIFF magic: II (0x4949) little-endian or MM (0x4D4D) big-endian
      const isValidTIFF = (byte1 === 0x49 && byte2 === 0x49) || (byte1 === 0x4D && byte2 === 0x4D);
      
      if (!isValidTIFF) {
        console.warn('❌ Arquivo não é um TIFF válido. Magic bytes:', 
          '0x' + byte1.toString(16).padStart(2, '0'), 
          '0x' + byte2.toString(16).padStart(2, '0'));
        console.warn('⚠️ Pode ser HTML de erro ou arquivo corrompido');
        return false;
      }

      console.log('✅ TIFF válido detectado. Byte order:', 
        byte1 === 0x49 ? 'Little Endian (II)' : 'Big Endian (MM)');

      this.loadingMessage = 'Processando GeoTIFF...';
      this.loadingProgress = 60;

      let georaster = this.geoTiffCache.getGeoRaster(geotiffUrl);
      if (georaster) {
        console.log('⚡ Georaster do cache — parseGeoraster ignorado');
      } else {
        georaster = await parseGeoraster(response);
        this.geoTiffCache.setGeoRaster(geotiffUrl, georaster);
      }

      if (!this.map) return false;

      console.log('📊 GeoTIFF Info:', {
        width: georaster.width,
        height: georaster.height,
        bands: georaster.numberOfRasters,
        projection: georaster.projection,
        bounds: [georaster.xmin, georaster.ymin, georaster.xmax, georaster.ymax]
      });

      this.loadingMessage = 'Renderizando ortofoto...';
      this.loadingProgress = 80;

      // Criar pane customizado com z-index 300 (acima do tilePane=200, abaixo de overlays=400)
      if (!this.map.getPane('orthophotoPane')) {
        const pane = this.map.createPane('orthophotoPane');
        pane.style.zIndex = '300';
      }

      this.orthophotoLayer = new GeoRasterLayer({
        georaster,
        opacity: this.opacityPercent / 100,
        resolution: 256,
        pane: 'orthophotoPane',
        pixelValuesToColorFn: (values: number[]) => {
          const [r, g, b] = values;
          return `rgb(${r},${g},${b})`;
        }
      } as any);

      if (!this.map) return false;
      this.orthophotoLayer.addTo(this.map);

      // Usar getBounds() do layer — ja reprojetado para WGS84
      const layerBounds = this.orthophotoLayer.getBounds();
      if (this.map) this.map.fitBounds(layerBounds, { maxZoom: 19 });

      this.renderMode = 'geotiff';
      this.isLoading = false;
      this.loadingProgress = 100;
      this.cdr.detectChanges();
      console.log('✅ Ortofoto carregada via GeoTIFF nativo');
      return true;

    } catch (error) {
      console.error('❌ Falha ao carregar GeoTIFF:', error);
      if (error instanceof Error) {
        console.error('Error name:', error.name);
        console.error('Error message:', error.message);
        console.error('Stack trace:', error.stack);
      }
      return false;
    }
  }

  /**
   * Altera opacidade da ortofoto
   */
  onOpacityChange(event: Event): void {
    const value = parseInt((event.target as HTMLInputElement).value);
    this.opacityPercent = value;
    
    if (this.orthophotoLayer) {
      if (this.orthophotoLayer.setOpacity) {
        this.orthophotoLayer.setOpacity(value / 100);
      }
    }
  }

  /**
   * Altera basemap
   */
  onBasemapChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.activeBasemap = value;
    
    if (this.baseLayer && this.map) {
      this.map.removeLayer(this.baseLayer);
    }
    
    if (value !== 'none') {
      this.baseLayer = this.basemaps.get(value)!;
      if (this.baseLayer && this.map) {
        this.baseLayer.addTo(this.map);
      }
    }
  }
}
