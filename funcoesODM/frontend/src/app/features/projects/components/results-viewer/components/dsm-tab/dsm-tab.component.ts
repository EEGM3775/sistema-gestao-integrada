/**
 * DsmTabComponent — Visualizador de Modelos de Elevação (DSM/DTM)
 *
 * Renderiza GeoTIFF de DSM/DTM diretamente no Leaflet usando georaster com
 * paleta de cores terrain profissional (azul → verde → amarelo → vermelho).
 * Exibe legenda com valores reais de elevação mínima e máxima.
 */

import {
  Component,
  Input,
  OnInit,
  OnDestroy,
  AfterViewInit,
  ViewChild,
  ElementRef,
  signal,
  computed,
  inject,
  ChangeDetectorRef,
  Output,
  EventEmitter
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AssetInfo, ResultsService } from '../../../../services/results.service';
import { GeoTiffCacheService } from '../../../../../../core/services/geotiff-cache.service';
import * as L from 'leaflet';
import parseGeoraster from 'georaster';
// @ts-ignore
import GeoRasterLayer from 'georaster-layer-for-leaflet';

type ElevationType = 'dsm' | 'dtm';

export interface ElevationRange {
  min: number;
  max: number;
}

// ─── Paleta terrain (azul profundo → ciano → verde → amarelo → laranja → vermelho) ───
const TERRAIN_PALETTE: [number, number, number][] = [
  [2,   62, 138],   // azul profundo (mínimo)
  [0,  116, 217],   // azul
  [41, 182, 246],   // azul claro
  [77, 182, 172],   // teal
  [102,187, 106],   // verde
  [212,225,  87],   // verde-amarelo
  [255,214,   0],   // amarelo
  [255,152,   0],   // laranja
  [229, 57,  53],   // vermelho-laranja
  [183, 28,  28],   // vermelho escuro (máximo)
];

function terrainColor(t: number, opacity = 0.88): string {
  const clamped = Math.max(0, Math.min(1, t));
  const idx = clamped * (TERRAIN_PALETTE.length - 1);
  const lo  = Math.floor(idx);
  const hi  = Math.min(TERRAIN_PALETTE.length - 1, lo + 1);
  const f   = idx - lo;
  const r   = Math.round(TERRAIN_PALETTE[lo][0] + f * (TERRAIN_PALETTE[hi][0] - TERRAIN_PALETTE[lo][0]));
  const g   = Math.round(TERRAIN_PALETTE[lo][1] + f * (TERRAIN_PALETTE[hi][1] - TERRAIN_PALETTE[lo][1]));
  const b   = Math.round(TERRAIN_PALETTE[lo][2] + f * (TERRAIN_PALETTE[hi][2] - TERRAIN_PALETTE[lo][2]));
  return `rgba(${r},${g},${b},${opacity})`;
}

@Component({
    selector: 'app-dsm-tab',
    imports: [CommonModule, FormsModule],
    templateUrl: './dsm-tab.component.html',
    styleUrls: ['./dsm-tab.component.scss']
})
export class DsmTabComponent implements AfterViewInit, OnDestroy {
  @Input() set assets(val: AssetInfo[]) {
    this._assetsSignal.set(val);
    if (this.mapReady_flag) this.loadDefaultLayer();
  }
  get assets(): AssetInfo[] { return this._assetsSignal(); }
  private _assetsSignal = signal<AssetInfo[]>([]);

  @Input() projectId!: number;
  @Input() taskId!: number;

  /** Sinaliza visibilidade — chama invalidateSize quando a aba volta a ficar visivel */
  @Input() set visible(val: boolean) {
    if (val && this.map) {
      setTimeout(() => { try { this.map?.invalidateSize(); } catch {} }, 80);
    }
  }

  @Output() mapReady = new EventEmitter<L.Map>();

  @ViewChild('dsmMapContainer') mapContainerRef!: ElementRef<HTMLDivElement>;

  private resultsService = inject(ResultsService);
  private cdr = inject(ChangeDetectorRef);
  private geoTiffCache = inject(GeoTiffCacheService);

  elevationType = signal<ElevationType>('dsm');
  loading       = signal(false);
  error         = signal<string | null>(null);
  opacityValue  = signal(88);        // 0–100
  elevationRange = signal<ElevationRange | null>(null);

  private map: L.Map | null = null;
  private rasterLayer: any   = null;
  private mapReady_flag = false;

  hasDSM = computed(() => this._assetsSignal().some(a => a.name.toLowerCase().includes('dsm')));
  hasDTM = computed(() => this._assetsSignal().some(a => a.name.toLowerCase().includes('dtm')));

  legendGradient = computed(() => {
    const stops = TERRAIN_PALETTE.map(([r, g, b]) => `rgb(${r},${g},${b})`).join(', ');
    return `linear-gradient(to right, ${stops})`;
  });

  formatElev(v: number | null | undefined): string {
    if (v == null) return '—';
    return `${v.toFixed(1)} m`;
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────────

  ngAfterViewInit(): void {
    this.initMap();
    this.mapReady_flag = true;
    if (this.map) {
      console.log('[DsmTab] Emitindo mapReady, mapa:', this.map);
      this.mapReady.emit(this.map);
    }
    this.loadDefaultLayer();
  }

  ngOnDestroy(): void {
    this.destroyMap();
  }

  // ─── Public actions ────────────────────────────────────────────────────────

  setElevationType(type: ElevationType): void {
    this.elevationType.set(type);
    this.loadElevationLayer(type);
  }

  onOpacityChange(event: Event): void {
    const val = +(event.target as HTMLInputElement).value;
    this.opacityValue.set(val);
    if (this.rasterLayer) {
      this.rasterLayer.setOpacity(val / 100);
    }
  }

  // ─── Map init ──────────────────────────────────────────────────────────────

  private initMap(): void {
    if (!this.mapContainerRef?.nativeElement) return;

    this.map = L.map(this.mapContainerRef.nativeElement, {
      center: [0, 0],
      zoom: 2,
      zoomControl: true,
      attributionControl: false
    });

    // A CARTO passou a exigir chave; a base cinza-escura da Esri não, e tem imagem até o zoom 16.
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 22,
      maxNativeZoom: 16
    }).addTo(this.map);
  }

  private destroyMap(): void {
    if (this.rasterLayer && this.map) {
      this.map.removeLayer(this.rasterLayer);
    }
    if (this.map) {
      this.map.remove();
      this.map = null;
    }
    this.rasterLayer = null;
  }

  private loadDefaultLayer(): void {
    if (this.hasDSM()) {
      this.elevationType.set('dsm');
      this.loadElevationLayer('dsm');
    } else if (this.hasDTM()) {
      this.elevationType.set('dtm');
      this.loadElevationLayer('dtm');
    }
  }

  // ─── Raster loading ────────────────────────────────────────────────────────

  private async loadElevationLayer(type: ElevationType): Promise<void> {
    if (!this.map) return;

    const asset = this._assetsSignal().find(a => a.name.toLowerCase().includes(type));
    if (!asset) {
      this.error.set(`Nenhum arquivo ${type.toUpperCase()} encontrado nos resultados.`);
      this.cdr.detectChanges();
      return;
    }

    // Prefer the pre-built URL from the asset (e.g. /api/v1/chunks/{uuid}/assets/dsm.tif).
    // Fall back to numeric-id URL only when the asset carries no URL.
    const url = asset.downloadUrl || this.resultsService.getChunkAssetDownloadUrl(this.projectId, this.taskId, asset.name);

    this.loading.set(true);
    this.error.set(null);
    this.elevationRange.set(null);
    this.cdr.detectChanges();

    // Remove layer anterior
    if (this.rasterLayer && this.map) {
      this.map.removeLayer(this.rasterLayer);
      this.rasterLayer = null;
    }

    try {
      let georaster = this.geoTiffCache.getGeoRaster(url);

      if (!georaster) {
        const fromCache = this.geoTiffCache.has(url);
        const buffer = await this.geoTiffCache.get(url, (p) => {
          if (!fromCache) {
            const mb    = (p.receivedBytes / 1024 / 1024).toFixed(0);
            const total = p.totalBytes > 0 ? ` / ${(p.totalBytes / 1024 / 1024).toFixed(0)}` : '';
            this.error.set(`Baixando ${type.toUpperCase()}... ${mb}${total} MB`);
            this.cdr.detectChanges();
          }
        });
        this.error.set(null);

        if (!this.map) return;

        georaster = await parseGeoraster(buffer);
        this.geoTiffCache.setGeoRaster(url, georaster);
      } else {
        console.log('[DSM] Georaster do cache — parseGeoraster ignorado:', type.toUpperCase());
      }

      if (!this.map) return;

      const minElev = georaster.mins[0];
      const maxElev = georaster.maxs[0];
      const range   = maxElev - minElev;
      const noData  = georaster.noDataValue;

      this.elevationRange.set({ min: minElev, max: maxElev });

      const opacity = this.opacityValue() / 100;

      this.rasterLayer = new GeoRasterLayer({
        georaster,
        opacity,
        pixelValuesToColorFn: (pixelValues: number[]) => {
          const val = pixelValues[0];
          if (noData !== null && val === noData) return '';
          if (!isFinite(val)) return '';
          const normalized = range > 0 ? (val - minElev) / range : 0;
          return terrainColor(normalized, opacity);
        },
        resolution: 256
      } as any);

      if (!this.map) return;
      this.rasterLayer.addTo(this.map);

      // Adia invalidateSize + fitBounds para apos o layout CSS resolver o tamanho do container
      setTimeout(() => {
        if (!this.map || !this.rasterLayer) return;
        this.map.invalidateSize();
        try {
          const b: L.LatLngBounds = this.rasterLayer.getBounds();
          if (b && b.isValid()) this.map.fitBounds(b, { maxZoom: 19 });
        } catch { /* ignora */ }
      }, 300);

    } catch (err: any) {
      const is404 = String(err?.message ?? err).includes('404');
      if (is404) {
        this._assetsSignal.update(list => list.filter(a => !a.name.toLowerCase().includes(type)));
        this.error.set(`${type.toUpperCase()} não disponível para este projeto.`);
      } else {
        console.error('[DsmTab] Erro ao renderizar raster:', err);
        this.error.set(`Erro ao carregar ${type.toUpperCase()}: ${err.message ?? err}`);
      }
    } finally {
      this.loading.set(false);
      this.cdr.detectChanges();
    }
  }
}
