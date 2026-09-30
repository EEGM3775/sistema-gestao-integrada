/**
 * VegetationTabComponent — Indices de Vegetacao (VARI / NDVI)
 *
 * Calcula VARI (RGB) e NDVI (multiespectral) inteiramente no browser a partir
 * do GeoTIFF da ortofoto, sem processamento backend.
 *
 * VARI = (G - R) / (G + R - B)  — funciona com qualquer ortofoto RGB.
 * NDVI = (NIR - R) / (NIR + R)  — requer banda NIR (camera multiespectral).
 *
 * O GeoTIFF e baixado uma unica vez e mantido em cache durante o ciclo de vida
 * do componente. Alternar entre VARI e NDVI usa o cache sem novo download.
 */

import {
  Component, Input, AfterViewInit, OnDestroy, OnChanges, SimpleChanges,
  ViewChild, ElementRef, signal, computed, inject, effect, ChangeDetectorRef
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AnnotationService } from '../../../../services/annotation.service';
import { AnnotationsPanelComponent } from '../../../../components/annotations-panel/annotations-panel.component';
import { Annotation, CreateAnnotationRequest } from '../../../../models/annotation.model';
import { AuthService } from '../../../../../../core/services/auth.service';
import { AssetInfo, ResultsService } from '../../../../services/results.service';
import { GeoTiffCacheService } from '../../../../../../core/services/geotiff-cache.service';
import * as L from 'leaflet';
import parseGeoraster from 'georaster';
// @ts-ignore
import GeoRasterLayer from 'georaster-layer-for-leaflet';
import {
  Chart, BarController, BarElement, CategoryScale, LinearScale, Tooltip,
  type TooltipItem
} from 'chart.js';

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip);

export type IndexType = 'vari' | 'ndvi';

interface HistogramBucket {
  center: number;
  label: string;
  count: number;
}

export interface IndexStats {
  min: number;
  max: number;
  mean: number;
}

// ─── Paleta de cores: -1 (solo/agua) → 0 (solo exposto) → +1 (vegetacao densa) ───
// Formato: [valor_indice, R, G, B]
const VEG_PALETTE: [number, number, number, number][] = [
  [-1.00, 166,  97,  26],
  [-0.50, 223, 194, 125],
  [ 0.00, 245, 245, 189],
  [ 0.10, 217, 240, 163],
  [ 0.20, 166, 219, 160],
  [ 0.35,  90, 174,  97],
  [ 0.50,  26, 128,  62],
  [ 0.70,   0,  68,  27],
  [ 1.00,   0,  40,   0],
];

function vegetationColor(indexVal: number, opacity: number): string {
  const v = Math.max(-1, Math.min(1, indexVal));
  let lo = VEG_PALETTE.length - 2;
  for (let i = 0; i < VEG_PALETTE.length - 1; i++) {
    if (v <= VEG_PALETTE[i + 1][0]) { lo = i; break; }
  }
  const hi = lo + 1;
  const span = VEG_PALETTE[hi][0] - VEG_PALETTE[lo][0];
  const f = span > 0 ? (v - VEG_PALETTE[lo][0]) / span : 0;
  const r = Math.round(VEG_PALETTE[lo][1] + f * (VEG_PALETTE[hi][1] - VEG_PALETTE[lo][1]));
  const g = Math.round(VEG_PALETTE[lo][2] + f * (VEG_PALETTE[hi][2] - VEG_PALETTE[lo][2]));
  const b = Math.round(VEG_PALETTE[lo][3] + f * (VEG_PALETTE[hi][3] - VEG_PALETTE[lo][3]));
  return `rgba(${r},${g},${b},${opacity})`;
}

const HISTOGRAM_BUCKETS = 30;
const SAMPLE_STRIDE = 50;

@Component({
    selector: 'app-vegetation-tab',
    imports: [CommonModule, FormsModule, AnnotationsPanelComponent],
    templateUrl: './vegetation-tab.component.html',
    styleUrls: ['./vegetation-tab.component.scss']
})
export class VegetationTabComponent implements AfterViewInit, OnDestroy, OnChanges {

  @Input() set assets(val: AssetInfo[]) {
    this._assets = val;
    if (this.mapReady_flag && this.indexReady()) {
      this.resetState();
    }
  }
  get assets(): AssetInfo[] { return this._assets; }
  private _assets: AssetInfo[] = [];

  @Input() projectId!: number;
  @Input() taskId!: number;

  /** Sinaliza visibilidade — re-centraliza mapa e inicia calculo automaticamente */
  @Input() set visible(val: boolean) {
    if (!val) return;
    setTimeout(() => {
      if (this.map) {
        try { this.map.invalidateSize(); } catch {}
        // Re-centra se ja calculado
        if (this.indexReady() && this.rasterLayer) {
          try {
            const b: L.LatLngBounds = this.rasterLayer.getBounds();
            if (b && b.isValid()) this.map.fitBounds(b, { maxZoom: 19 });
          } catch { /* ignora */ }
        }
      }
      // Auto-inicia calculo se nao foi feito ainda
      if (!this.indexReady() && !this.loading() && this.hasOrthophoto()) {
        void this.computeIndex();
      }
    }, 120);
  }

  @ViewChild('vegMapContainer') mapContainerRef!: ElementRef<HTMLDivElement>;
  @ViewChild('histogramCanvas') histogramCanvasRef?: ElementRef<HTMLCanvasElement>;

  private resultsService = inject(ResultsService);
  private geoTiffCache  = inject(GeoTiffCacheService);
  private cdr = inject(ChangeDetectorRef);
  annotationService = inject(AnnotationService);
  private authService = inject(AuthService);

  indexType        = signal<IndexType>('vari');
  loading          = signal(false);
  downloadProgress = signal(0);    // 0–100, usado na barra de progresso
  downloadLabel    = signal('');   // ex: "45 / 230 MB"
  error            = signal<string | null>(null);
  opacityValue     = signal(88);
  stats            = signal<IndexStats | null>(null);
  hasNdvi          = signal(false);
  indexReady       = signal(false);

  private _histogramBuckets = signal<HistogramBucket[]>([]);

  showHistogram = computed(() => this._histogramBuckets().length > 0);

  legendGradient = computed(() => {
    const stops = VEG_PALETTE.map(([, r, g, b]) => `rgb(${r},${g},${b})`).join(', ');
    return `linear-gradient(to right, ${stops})`;
  });

  private map: L.Map | null = null;
  private rasterLayer: any = null;
  private mapReady_flag = false;
  private cachedBuffer: ArrayBuffer | null = null;
  private cachedGeoRaster: any = null;
  private histogramChart: Chart | null = null;

  // --- Anotações -------------------------------------------------------------
  private annotationsLayer: L.LayerGroup | null = null;
  private tempAnnotationMarker: L.Marker | null = null;
  private tempPolyline: L.Polyline | null = null;
  private tempPolygon: L.Polygon | null = null;
  annotateMode = signal(false);
  annotationType = signal<'MARKER' | 'POLYGON'>('MARKER');
  polygonPoints = signal<L.LatLng[]>([]);
  showAnnotationsPanel = signal(false);

  constructor() {
    effect(() => {
      this.annotationService.annotations();
      this.renderAnnotationMarkers();
    });
  }

  hasOrthophoto = computed(() =>
    this._assets.some(a => a.name.toLowerCase().includes('orthophoto'))
  );

  formatIndex(v: number | null | undefined): string {
    if (v == null) return '—';
    return v.toFixed(3);
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────────

  ngAfterViewInit(): void {
    this.initMap();
    this.mapReady_flag = true;
    this.annotationService.connectToProject(this.projectId);
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['assets'] && this.mapReady_flag && this.indexReady()) {
      this.resetState();
    }
  }

  ngOnDestroy(): void {
    this.histogramChart?.destroy();
    this.histogramChart = null;
    this.annotationService.disconnectFromProject();
    this.destroyMap();
  }

  // ─── Public actions ────────────────────────────────────────────────────────

  setIndexType(type: IndexType): void {
    if (this.loading()) return;
    this.indexType.set(type);
    if (this.cachedGeoRaster) {
      void this.renderIndex(this.cachedGeoRaster, type);
    }
  }

  onOpacityChange(event: Event): void {
    const val = +(event.target as HTMLInputElement).value;
    this.opacityValue.set(val);
    if (this.rasterLayer) {
      this.rasterLayer.setOpacity(val / 100);
    }
  }

  async computeIndex(): Promise<void> {
    if (this.loading()) return;

    console.log('[VEG] computeIndex chamado');
    console.log('[VEG] assets disponiveis:', this._assets.map(a => a.name));
    console.log('[VEG] projectId:', this.projectId, 'taskId:', this.taskId);
    console.log('[VEG] mapa inicializado:', !!this.map);

    const asset = this._assets.find(a => a.name.toLowerCase().includes('orthophoto'));
    if (!asset) {
      console.error('[VEG] Ortofoto nao encontrada nos assets:', this._assets);
      this.error.set('Ortofoto nao encontrada nos resultados desta tarefa.');
      this.cdr.detectChanges();
      return;
    }

    const url = this.resultsService.getChunkAssetDownloadUrl(this.projectId, this.taskId, asset.name);
    console.log('[VEG] URL de download:', url);

    this.loading.set(true);
    this.error.set(null);
    this.cdr.detectChanges();

    try {
      // Sempre pede um ArrayBuffer fresco ao cache — cada chamada recebe uma copia
      // independente para que o parseGeoraster possa transferi-la ao Worker sem
      // invalidar o cache ou impedir novas chamadas.
      const fromCache = this.geoTiffCache.has(url);
      console.log(fromCache ? '[VEG] Ortofoto do cache (instantaneo)' : '[VEG] Iniciando download...');
      this.downloadProgress.set(0);
      this.downloadLabel.set('');

      this.cachedBuffer = await this.geoTiffCache.get(url, (p) => {
        this.downloadProgress.set(p.percent);
        const mb    = (p.receivedBytes / 1024 / 1024).toFixed(0);
        const total = p.totalBytes > 0 ? ` / ${(p.totalBytes / 1024 / 1024).toFixed(0)}` : '';
        this.downloadLabel.set(`${mb}${total} MB`);
        this.cdr.detectChanges();
      });
      console.log('[VEG] Buffer pronto:', (this.cachedBuffer.byteLength / 1024 / 1024).toFixed(1), 'MB');

      if (!this.map) { console.warn('[VEG] Mapa destruido apos download'); return; }

      if (!this.cachedGeoRaster) {
        // Tenta do cache do servico (sobrevive a recreacao do componente)
        this.cachedGeoRaster = this.geoTiffCache.getGeoRaster(url);
      }

      if (!this.cachedGeoRaster) {
        console.log('[VEG] Parseando georaster...');
        this.cachedGeoRaster = await parseGeoraster(this.cachedBuffer);
        this.geoTiffCache.setGeoRaster(url, this.cachedGeoRaster);
        console.log('[VEG] Georaster parseado:', {
          width: this.cachedGeoRaster.width,
          height: this.cachedGeoRaster.height,
          bandas: this.cachedGeoRaster.numberOfRasters,
          projecao: this.cachedGeoRaster.projection,
          noDataValue: this.cachedGeoRaster.noDataValue,
          temValues: !!this.cachedGeoRaster.values,
          tamValues0: this.cachedGeoRaster.values?.[0]?.length
        });
      } else {
        console.log('[VEG] Georaster do cache do servico — parseGeoraster ignorado');
      }

      if (!this.map) { console.warn('[VEG] Mapa destruido apos parseGeoraster'); return; }

      const bandCount: number = this.cachedGeoRaster.numberOfRasters ?? 0;
      this.hasNdvi.set(bandCount >= 4);
      console.log('[VEG] Bandas:', bandCount, '| NDVI disponivel:', bandCount >= 4);

      if (this.indexType() === 'ndvi' && !this.hasNdvi()) {
        this.indexType.set('vari');
      }

      console.log('[VEG] Calculando indice:', this.indexType());
      await this.renderIndex(this.cachedGeoRaster, this.indexType());
      this.indexReady.set(true);
      console.log('[VEG] Indice calculado com sucesso');

    } catch (err: any) {
      console.error('[VEG] Erro ao calcular indice:', err);
      this.error.set(`Erro ao calcular indice: ${err.message ?? String(err)}`);
    } finally {
      this.loading.set(false);
      this.cdr.detectChanges();
    }
  }

  // ─── Raster rendering ──────────────────────────────────────────────────────

  private async renderIndex(georaster: any, type: IndexType): Promise<void> {
    if (!this.map) { console.warn('[VEG] renderIndex: mapa e null'); return; }

    console.log('[VEG] renderIndex inicio — tipo:', type);

    if (this.rasterLayer) {
      this.map.removeLayer(this.rasterLayer);
      this.rasterLayer = null;
    }

    this.stats.set(null);
    this._histogramBuckets.set([]);

    const noData: number | null = georaster.noDataValue ?? null;
    const opacity = this.opacityValue() / 100;

    // georaster.values[band] e um array de linhas: values[band][row][col]
    const imgW: number = georaster.width;
    const imgH: number = georaster.height;
    const band0Rows: any = georaster.values?.[0];
    const band1Rows: any = georaster.values?.[1];
    const band2Rows: any = georaster.values?.[2];
    const band3Rows: any = georaster.values?.[3];

    console.log('[VEG] Estrutura values: height=', imgH, 'width=', imgW,
      'tipo values[0]:', typeof band0Rows?.[0],
      'tipo values[0][0]:', typeof band0Rows?.[0]?.[0]);

    // ── Histograma e estatisticas (amostragem 2D) ───────────────────────────
    if (imgH > 0 && imgW > 0 && band0Rows) {
      const bucketSize = 2 / HISTOGRAM_BUCKETS;
      const buckets = new Array<number>(HISTOGRAM_BUCKETS).fill(0);
      let sum = 0, count = 0, minVal = Infinity, maxVal = -Infinity;

      const rowStride = Math.max(1, Math.floor(imgH / 500));   // amostrar ~500 linhas
      const colStride = Math.max(1, Math.floor(imgW / 500));   // amostrar ~500 colunas

      for (let row = 0; row < imgH; row += rowStride) {
        const r0 = band0Rows[row];
        const r1 = band1Rows[row];
        const r2 = band2Rows[row];
        const r3 = band3Rows?.[row];
        if (!r0) continue;

        for (let col = 0; col < imgW; col += colStride) {
          const r = r0[col], g = r1[col], b = r2[col];
          if (noData !== null && (r === noData || g === noData || b === noData)) continue;
          // Filtra pixels do retangulo de fundo (borda preta sem imagem real)
          if (r < 5 && g < 5 && b < 5) continue;

          let idx: number;
          if (type === 'ndvi' && r3) {
            const nir = r3[col];
            if (noData !== null && nir === noData) continue;
            const denom = nir + r;
            idx = denom !== 0 ? (nir - r) / denom : 0;
          } else {
            const denom = g + r - b;
            idx = denom !== 0 ? (g - r) / denom : 0;
          }

          if (!isFinite(idx)) continue;
          const clamped = Math.max(-1, Math.min(1, idx));
          sum += clamped;
          count++;
          if (clamped < minVal) minVal = clamped;
          if (clamped > maxVal) maxVal = clamped;
          const bi = Math.min(HISTOGRAM_BUCKETS - 1, Math.floor((clamped + 1) / bucketSize));
          buckets[bi]++;
        }
      }

      console.log('[VEG] Histograma: pixels amostrados=', count, 'min=', minVal?.toFixed(3), 'max=', maxVal?.toFixed(3));

      if (count > 0) {
        this.stats.set({ min: minVal, max: maxVal, mean: sum / count });
        this._histogramBuckets.set(
          buckets.map((cnt, i) => ({
            center: -1 + (i + 0.5) * bucketSize,
            label: (-1 + (i + 0.5) * bucketSize).toFixed(2),
            count: cnt
          }))
        );
      }
    }

    // ── Camada Leaflet ──────────────────────────────────────────────────────
    this.rasterLayer = new GeoRasterLayer({
      georaster,
      opacity,
      pixelValuesToColorFn: (pixelValues: number[]) => {
        const r = pixelValues[0], g = pixelValues[1], b = pixelValues[2];
        const nir = pixelValues[3];
        if (noData !== null) {
          if (r === noData || g === noData || b === noData) return '';
          if (type === 'ndvi' && nir === noData) return '';
        }
        // Filtra pixels do retangulo de fundo (borda preta sem imagem real)
        if (r < 5 && g < 5 && b < 5) return '';
        let idx: number;
        if (type === 'ndvi' && nir !== undefined) {
          const denom = nir + r;
          idx = denom !== 0 ? (nir - r) / denom : 0;
        } else {
          const denom = g + r - b;
          idx = denom !== 0 ? (g - r) / denom : 0;
        }
        if (!isFinite(idx)) return '';
        return vegetationColor(idx, opacity);
      },
      resolution: 256
    } as any);

    if (!this.map) { console.warn('[VEG] mapa destruido antes de addTo'); return; }

    console.log('[VEG] Adicionando layer ao mapa...');
    this.rasterLayer.addTo(this.map);
    console.log('[VEG] Layer adicionado. Zoom do mapa:', this.map?.getZoom());

    // Adia invalidateSize + fitBounds para apos o layout CSS resolver o tamanho do container.
    // Chamadas sincronas falham quando o container ainda esta em 0px (flex height nao resolvido).
    setTimeout(() => {
      if (!this.map || !this.rasterLayer) return;
      this.map.invalidateSize();
      try {
        const b: L.LatLngBounds = this.rasterLayer.getBounds();
        if (b && b.isValid()) {
          this.map.fitBounds(b, { maxZoom: 19 });
          console.log('[VEG] fitBounds (deferred) zoom:', this.map.getZoom());
        }
      } catch (e) { console.warn('[VEG] fitBounds deferred falhou:', e); }
    }, 300);

    this.cdr.detectChanges();
    setTimeout(() => this.renderHistogramChart(), 400);
  }

  // ─── Histograma ────────────────────────────────────────────────────────────

  private renderHistogramChart(): void {
    const canvas = this.histogramCanvasRef?.nativeElement;
    if (!canvas) return;

    const buckets = this._histogramBuckets();
    if (buckets.length === 0) return;

    this.histogramChart?.destroy();
    this.histogramChart = null;

    this.histogramChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: buckets.map(b => b.label),
        datasets: [{
          data: buckets.map(b => b.count),
          backgroundColor: buckets.map(b => vegetationColor(b.center, 0.85)),
          borderWidth: 0,
          barPercentage: 1.0,
          categoryPercentage: 1.0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items: TooltipItem<'bar'>[]) => `Indice: ${items[0]?.label ?? ''}`,
              label: (item: TooltipItem<'bar'>) => `Pixels (amostra): ${item.raw}`
            }
          }
        },
        scales: {
          x: {
            ticks: { color: '#7c7ca0', font: { size: 9 }, maxRotation: 0, maxTicksLimit: 7 },
            grid: { color: '#2a2a4a' }
          },
          y: {
            ticks: { color: '#7c7ca0', font: { size: 9 } },
            grid: { color: '#2a2a4a' }
          }
        }
      }
    } as any);
  }

  // ─── Map ───────────────────────────────────────────────────────────────────

  // ─── Zoom helpers ──────────────────────────────────────────────────────────

  private zoomToGeoRaster(georaster: any): void {
    if (!this.map) return;

    console.log('[VEG] zoomToGeoRaster — projecao:', georaster.projection,
      'xmin:', georaster.xmin, 'xmax:', georaster.xmax,
      'ymin:', georaster.ymin, 'ymax:', georaster.ymax);

    // Garante que o Leaflet conhece o tamanho real do container antes de calcular zoom
    this.map.invalidateSize();

    // Estrategia 1: bounds do layer (GeoRasterLayer reprojecta internamente)
    if (this.rasterLayer) {
      try {
        const b: L.LatLngBounds = this.rasterLayer.getBounds();
        if (b && b.isValid()) {
          console.log('[VEG] Zoom via getBounds() do layer:', b.toBBoxString());
          this.map.fitBounds(b, { maxZoom: 19 });
          return;
        }
      } catch (e) { console.warn('[VEG] getBounds() falhou:', e); }
    }

    // Estrategia 2: EPSG:4326 — usa coordenadas diretamente como lat/lng
    if (georaster.projection === 4326 || georaster.projection === 'EPSG:4326') {
      try {
        const bounds = L.latLngBounds(
          [georaster.ymin, georaster.xmin],
          [georaster.ymax, georaster.xmax]
        );
        if (bounds.isValid()) {
          console.log('[VEG] Zoom via EPSG:4326 direto');
          this.map.fitBounds(bounds, { maxZoom: 19 });
          return;
        }
      } catch (e) { console.warn('[VEG] EPSG:4326 direto falhou:', e); }
    }

    // Estrategia 3: tenta interpretar como lat/lng independente da projecao
    try {
      const { xmin, xmax, ymin, ymax } = georaster;
      if (xmin >= -180 && xmax <= 180 && ymin >= -90 && ymax <= 90) {
        const bounds = L.latLngBounds([ymin, xmin], [ymax, xmax]);
        if (bounds.isValid()) {
          console.log('[VEG] Zoom via bounds como lat/lng (estrategia 3)');
          this.map.fitBounds(bounds, { maxZoom: 19 });
          return;
        }
      }
    } catch (e) { console.warn('[VEG] Estrategia 3 falhou:', e); }

    console.warn('[VEG] Nenhuma estrategia de zoom funcionou — mapa permanece no zoom atual');
  }

  private initMap(): void {
    if (!this.mapContainerRef?.nativeElement) return;
    this.map = L.map(this.mapContainerRef.nativeElement, {
      center: [0, 0], zoom: 2,
      zoomControl: true, attributionControl: false
    });
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 22, maxNativeZoom: 19,
      attribution: 'Esri, Maxar, Earthstar Geographics'
    }).addTo(this.map);

    this.annotationsLayer = L.layerGroup().addTo(this.map);
    this.map.on('click', (e: L.LeafletMouseEvent) => this.onAnnotateMapClick(e));

    setTimeout(() => this.map?.invalidateSize(), 100);
  }

  private destroyMap(): void {
    if (this.rasterLayer && this.map) this.map.removeLayer(this.rasterLayer);
    if (this.map) { this.map.remove(); this.map = null; }
    this.rasterLayer = null;
    this.annotationsLayer = null;
    this.cachedBuffer = null;
    this.cachedGeoRaster = null;
  }

  // ─── Anotações ─────────────────────────────────────────────────────────────

  startAnnotating(type: 'MARKER' | 'POLYGON'): void {
    this.cancelAnnotation();
    this.annotationType.set(type);
    this.annotateMode.set(true);
    if (this.map) {
      this.map.getContainer().style.cursor = 'crosshair';
    }
  }

  cancelAnnotation(): void {
    if (this.map) {
      this.map.closePopup();
      this.map.getContainer().style.cursor = '';
    }
    if (this.tempAnnotationMarker && this.map) {
      this.map.removeLayer(this.tempAnnotationMarker);
      this.tempAnnotationMarker = null;
    }
    if (this.tempPolyline && this.map) {
      this.map.removeLayer(this.tempPolyline);
      this.tempPolyline = null;
    }
    if (this.tempPolygon && this.map) {
      this.map.removeLayer(this.tempPolygon);
      this.tempPolygon = null;
    }
    this.polygonPoints.set([]);
    this.annotateMode.set(false);
  }

  completePolygon(): void {
    const points = this.polygonPoints();
    if (points.length < 3 || !this.map) return;
    this.annotateMode.set(false);
    this.map.getContainer().style.cursor = '';
    const lat = points.reduce((sum, p) => sum + p.lat, 0) / points.length;
    const lng = points.reduce((sum, p) => sum + p.lng, 0) / points.length;
    const form = this.buildAnnotationFormPolygon(points);
    L.popup({ minWidth: 200 }).setLatLng([lat, lng]).setContent(form).openOn(this.map);
  }

  toggleAnnotationsPanel(): void {
    this.showAnnotationsPanel.update(v => !v);
  }

  private onAnnotateMapClick(e: L.LeafletMouseEvent): void {
    if (!this.annotateMode() || !this.map) return;

    if (this.annotationType() === 'MARKER') {
      if (this.tempAnnotationMarker) {
        this.map.removeLayer(this.tempAnnotationMarker);
        this.tempAnnotationMarker = null;
      }
      const { lat, lng } = e.latlng;
      this.tempAnnotationMarker = L.marker([lat, lng], { icon: this.createAnnotationIcon(), opacity: 0.85 }).addTo(this.map);
      const form = this.buildAnnotationForm(lat, lng);
      this.tempAnnotationMarker.bindPopup(L.popup({ minWidth: 200 }).setContent(form)).openPopup();
    } else {
      this.polygonPoints.update(pts => [...pts, e.latlng]);
      this.updateTempPolygon();
    }
  }

  private updateTempPolygon(): void {
    const points = this.polygonPoints();
    if (this.tempPolyline) { this.map?.removeLayer(this.tempPolyline); this.tempPolyline = null; }
    if (this.tempPolygon)  { this.map?.removeLayer(this.tempPolygon);  this.tempPolygon  = null; }
    if (!this.map || points.length < 2) return;
    if (points.length >= 3) {
      this.tempPolygon = L.polygon(points, { color: '#3b5bdb', weight: 2, fillOpacity: 0.2 }).addTo(this.map);
    } else {
      this.tempPolyline = L.polyline(points, { color: '#3b5bdb', weight: 2, dashArray: '6 4' }).addTo(this.map);
    }
  }

  private createAnnotationIcon(): L.DivIcon {
    return L.divIcon({
      html: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="36" viewBox="0 0 24 36">
        <path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 24 12 24S24 21 24 12C24 5.4 18.6 0 12 0z"
              fill="#3b5bdb" stroke="#fff" stroke-width="1.5"/>
        <circle cx="12" cy="12" r="4" fill="#fff"/>
      </svg>`,
      iconSize: [24, 36],
      iconAnchor: [12, 36],
      popupAnchor: [0, -38],
      className: ''
    });
  }

  private buildAnnotationForm(lat: number, lng: number): HTMLElement {
    const wrap = document.createElement('div');
    const textarea = document.createElement('textarea');
    textarea.placeholder = 'Texto da anotacao (opcional)';
    textarea.rows = 2;
    textarea.style.cssText = 'width:180px;resize:vertical;font-size:12px;padding:4px;';

    const actions = document.createElement('div');
    actions.style.cssText = 'margin-top:6px;display:flex;gap:6px;';

    const btnSave = document.createElement('button');
    btnSave.textContent = 'Salvar';
    btnSave.style.cssText = 'flex:1;background:#3b5bdb;color:#fff;border:none;border-radius:4px;padding:4px 8px;cursor:pointer;font-size:12px;';
    btnSave.addEventListener('click', () => this.saveAnnotation(JSON.stringify([lat, lng]), 'MARKER', textarea.value));

    const btnCancel = document.createElement('button');
    btnCancel.textContent = 'Cancelar';
    btnCancel.style.cssText = 'flex:1;background:#3a3f55;color:#c8ccd8;border:none;border-radius:4px;padding:4px 8px;cursor:pointer;font-size:12px;';
    btnCancel.addEventListener('click', () => this.cancelAnnotation());

    actions.appendChild(btnSave);
    actions.appendChild(btnCancel);
    wrap.appendChild(textarea);
    wrap.appendChild(actions);
    return wrap;
  }

  private buildAnnotationFormPolygon(points: L.LatLng[]): HTMLElement {
    const coords = points.map(p => [p.lat, p.lng]);
    const wrap = document.createElement('div');

    const info = document.createElement('div');
    info.textContent = `Poligono — ${points.length} pontos`;
    info.style.cssText = 'font-size:11px;color:#888;margin-bottom:4px;';

    const textarea = document.createElement('textarea');
    textarea.placeholder = 'Texto da anotacao (opcional)';
    textarea.rows = 2;
    textarea.style.cssText = 'width:180px;resize:vertical;font-size:12px;padding:4px;';

    const actions = document.createElement('div');
    actions.style.cssText = 'margin-top:6px;display:flex;gap:6px;';

    const btnSave = document.createElement('button');
    btnSave.textContent = 'Salvar';
    btnSave.style.cssText = 'flex:1;background:#3b5bdb;color:#fff;border:none;border-radius:4px;padding:4px 8px;cursor:pointer;font-size:12px;';
    btnSave.addEventListener('click', () => this.saveAnnotation(JSON.stringify(coords), 'POLYGON', textarea.value));

    const btnCancel = document.createElement('button');
    btnCancel.textContent = 'Cancelar';
    btnCancel.style.cssText = 'flex:1;background:#3a3f55;color:#c8ccd8;border:none;border-radius:4px;padding:4px 8px;cursor:pointer;font-size:12px;';
    btnCancel.addEventListener('click', () => this.cancelAnnotation());

    actions.appendChild(btnSave);
    actions.appendChild(btnCancel);
    wrap.appendChild(info);
    wrap.appendChild(textarea);
    wrap.appendChild(actions);
    return wrap;
  }

  private saveAnnotation(coordinatesJson: string, type: 'MARKER' | 'POLYGON', text: string): void {
    const request: CreateAnnotationRequest = { type, coordinatesJson, text: text.trim() };
    this.annotationService.createAnnotation(this.projectId, request).subscribe({
      next: () => this.cancelAnnotation(),
      error: () => {}
    });
  }

  private renderAnnotationMarkers(): void {
    if (!this.annotationsLayer) return;
    this.annotationsLayer.clearLayers();
    for (const a of this.annotationService.annotations()) {
      if (this.annotationService.isVisible(a.id)) {
        this.addAnnotationToLayer(a);
      }
    }
  }

  private addAnnotationToLayer(a: Annotation): void {
    if (!this.annotationsLayer) return;
    try {
      const coords = JSON.parse(a.coordinatesJson);
      if (!Array.isArray(coords) || coords.length < 2) return;

      if (a.type === 'POLYGON' && Array.isArray(coords[0])) {
        const latLngs = (coords as [number, number][]).map(c => L.latLng(c[0], c[1]));
        if (latLngs.length < 3) return;
        const poly = L.polygon(latLngs, { color: '#3b5bdb', weight: 2, fillOpacity: 0.15 });
        poly.bindPopup(this.buildAnnotationPopup(a));
        this.annotationsLayer.addLayer(poly);
      } else {
        const [lat, lng] = coords as [number, number];
        const marker = L.marker([lat, lng], { icon: this.createAnnotationIcon() });
        marker.bindPopup(this.buildAnnotationPopup(a));
        this.annotationsLayer.addLayer(marker);
      }
    } catch { /* coordenadas invalidas */ }
  }

  private buildAnnotationPopup(a: Annotation): string {
    const label = ({ MARKER: 'Marcador', POLYGON: 'Poligono' } as Record<string, string>)[a.type] ?? a.type;
    const text = a.text ? `<p style="margin:6px 0 4px;color:#333;">${this.escapeHtml(a.text)}</p>` : '';
    return `<div style="font-size:12px;min-width:140px;">
      <strong style="color:#3b5bdb;">${label}</strong>
      <span style="color:#888;margin-left:6px;">@${this.escapeHtml(a.author.username)}</span>
      ${text}
    </div>`;
  }

  private escapeHtml(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  private resetState(): void {
    this.indexReady.set(false);
    this.stats.set(null);
    this._histogramBuckets.set([]);
    this.cachedBuffer = null;
    this.cachedGeoRaster = null;
    this.histogramChart?.destroy();
    this.histogramChart = null;
    if (this.rasterLayer && this.map) {
      this.map.removeLayer(this.rasterLayer);
      this.rasterLayer = null;
    }
  }
}
