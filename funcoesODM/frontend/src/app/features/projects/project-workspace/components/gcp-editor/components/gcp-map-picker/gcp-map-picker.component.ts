/**
 * GcpMapPickerComponent
 *
 * Painel para adicionar GCPs por clique num mapa satellite (Google via Leaflet).
 * Busca altitude via Open-Elevation API (SRTM, precisao +-15m).
 * Emite cada ponto adicionado individualmente; o pai acumula no signal gcpPoints.
 *
 * AVISO: os tiles Google Satellite violam os Termos de Servico do Google fora do
 * Maps JS SDK. Substituir por Esri World Imagery ou Bing Maps antes da producao.
 * Consulte docs/architecture/BEST_PRACTICES.md para alternativas legais.
 */

import {
  Component, Input, Output, EventEmitter, ElementRef, ViewChild,
  signal, computed, OnDestroy, AfterViewInit, ChangeDetectionStrategy
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import * as L from 'leaflet';
import { GcpPoint } from '../../models/gcp-mark.model';

@Component({
  selector: 'app-gcp-map-picker',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="map-picker-panel">

      <div class="map-picker-header">
        <button class="btn-link" (click)="closedRequest.emit()">&#8592; Voltar</button>
        <span class="map-picker-title">Novo GCP via mapa</span>
      </div>

      <p class="map-picker-hint">Clique no satelite para posicionar o ponto.</p>

      <div class="map-picker-map" #mapPickerDiv></div>

      @if (pickerCoords()) {
        <div class="map-picker-coords">
          <span>Lat: {{ pickerCoords()!.lat.toFixed(6) }}</span>
          <span>Lng: {{ pickerCoords()!.lng.toFixed(6) }}</span>
        </div>
        @if (nearbyWarning()) {
          <div class="map-picker-near-warn">
            [AVISO] Proximo a "{{ nearbyWarning() }}" (~&lt;1m) — pontos distintos, apenas verifique.
          </div>
        }
      } @else {
        <div class="map-picker-coords-empty">[Clique no mapa para selecionar]</div>
      }

      <div class="map-picker-form">
        <label class="picker-label">Nome</label>
        <input class="picker-input" [(ngModel)]="labelValue" placeholder="GCP-01" />

        <label class="picker-label">Altitude (m)</label>
        <div class="picker-alt-row">
          <input
            class="picker-input picker-input-alt"
            type="number"
            [(ngModel)]="altValue"
            placeholder="0"
          />
          <button
            class="btn-fetch-alt"
            [disabled]="!pickerCoords() || fetchingElevation()"
            (click)="fetchElevation()"
            title="Buscar altitude via SRTM (precisao +-15m)"
          >{{ fetchingElevation() ? '...' : 'SRTM' }}</button>
        </div>
        <p class="map-picker-warning">[AVISO] Precisao +-1 a 5m. Nao usar para topografia de precisao.</p>
      </div>

      <div class="map-picker-actions">
        <button class="btn-secondary" (click)="closedRequest.emit()">Cancelar</button>
        <button
          class="btn-primary"
          [disabled]="!pickerCoords()"
          (click)="addGcp()"
        >Adicionar GCP</button>
      </div>

    </div>
  `,
  styles: [`
    .map-picker-panel {
      display: flex;
      flex-direction: column;
      gap: 8px;
      height: 100%;
      overflow-y: auto;
    }

    .map-picker-header {
      display: flex;
      align-items: center;
      gap: 8px;
      padding-bottom: 6px;
      border-bottom: 1px solid #21262d;
    }

    .map-picker-title {
      font-size: 12px;
      font-weight: 600;
      color: #e6edf3;
    }

    .map-picker-hint {
      font-size: 11px;
      color: #8b949e;
      margin: 0;
    }

    .map-picker-map {
      width: 100%;
      height: 200px;
      border-radius: 6px;
      border: 1px solid #30363d;
      overflow: hidden;
      background: #010409;
      flex-shrink: 0;
    }

    .map-picker-coords {
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: 6px 8px;
      background: #161b22;
      border: 1px solid #238636;
      border-radius: 6px;
      font-family: monospace;
      font-size: 11px;
      color: #3fb950;
    }

    .map-picker-coords-empty {
      padding: 6px 8px;
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 6px;
      font-family: monospace;
      font-size: 11px;
      color: #6e7681;
    }

    .map-picker-form {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .picker-label {
      font-size: 11px;
      color: #8b949e;
      margin-top: 4px;
    }

    .picker-input {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 6px;
      color: #c9d1d9;
      font-size: 12px;
      padding: 5px 8px;
      width: 100%;
      box-sizing: border-box;
    }

    .picker-input:focus { outline: none; border-color: #58a6ff; }

    .picker-alt-row {
      display: flex;
      gap: 6px;
      align-items: center;
    }

    .picker-input-alt {
      flex: 1;
      width: auto;
    }

    .btn-fetch-alt {
      background: #21262d;
      border: 1px solid #30363d;
      color: #8b949e;
      padding: 5px 8px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 11px;
      white-space: nowrap;
      flex-shrink: 0;
    }

    .btn-fetch-alt:hover:not(:disabled) { border-color: #58a6ff; color: #58a6ff; }
    .btn-fetch-alt:disabled { opacity: 0.4; cursor: default; }

    .map-picker-warning {
      font-size: 10px;
      color: #d29922;
      margin: 4px 0 0;
      font-family: monospace;
      line-height: 1.4;
    }

    .map-picker-near-warn {
      font-size: 10px;
      color: #d29922;
      font-family: monospace;
      line-height: 1.4;
      padding: 4px 8px;
      background: #2a1f00;
      border: 1px solid #7a5900;
      border-radius: 4px;
    }

    .map-picker-actions {
      display: flex;
      gap: 6px;
      margin-top: auto;
      padding-top: 6px;
      border-top: 1px solid #21262d;
    }

    .map-picker-actions .btn-primary,
    .map-picker-actions .btn-secondary { flex: 1; }

    .btn-primary {
      background: #238636;
      border: 1px solid #2ea043;
      color: #fff;
      padding: 6px 16px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
    }

    .btn-primary:hover:not(:disabled) { background: #2ea043; }
    .btn-primary:disabled { opacity: 0.4; cursor: default; }

    .btn-secondary {
      background: transparent;
      border: 1px solid #30363d;
      color: #c9d1d9;
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 12px;
    }

    .btn-secondary:hover { border-color: #58a6ff; color: #58a6ff; }

    .btn-link {
      background: none;
      border: none;
      color: #58a6ff;
      cursor: pointer;
      font-size: 11px;
      padding: 0;
    }
  `]
})
export class GcpMapPickerComponent implements AfterViewInit, OnDestroy {

  /** Pontos ja carregados — usados apenas para dedup/proximidade. */
  @Input({ required: true }) gcpPoints: GcpPoint[] = [];

  /** Emite o novo GcpPoint a ser adicionado pelo pai. */
  @Output() gcpAdded = new EventEmitter<GcpPoint>();

  /** Solicita ao pai que feche este painel. */
  @Output() closedRequest = new EventEmitter<void>();

  @ViewChild('mapPickerDiv') mapPickerDivRef?: ElementRef<HTMLDivElement>;

  private leafletMap?: L.Map;
  private leafletMarker?: L.Marker;

  private readonly PROXIMITY_TOL = 0.00001;

  pickerCoords   = signal<{ lat: number; lng: number } | null>(null);
  fetchingElevation = signal(false);

  labelValue = '';
  altValue: number | null = null;

  nearbyWarning = computed(() => {
    const coords = this.pickerCoords();
    if (!coords) return null;
    const near = this.gcpPoints.find(e =>
      Math.abs(e.lat - coords.lat) < this.PROXIMITY_TOL &&
      Math.abs(e.lng - coords.lng) < this.PROXIMITY_TOL
    );
    return near ? near.label : null;
  });

  ngAfterViewInit(): void {
    // Aguarda o Angular terminar o ciclo de deteccao antes de inicializar o Leaflet
    setTimeout(() => this.initMap(), 50);
  }

  private initMap(): void {
    const el = this.mapPickerDivRef?.nativeElement;
    if (!el || this.leafletMap) return;

    // Inicializa o label com base no numero de pontos ja existentes
    const next = this.gcpPoints.length + 1;
    this.labelValue = `GCP-${String(next).padStart(2, '0')}`;
    this.altValue   = null;
    this.pickerCoords.set(null);

    this.leafletMap = L.map(el, {
      zoomControl: true,
      attributionControl: false,
    }).setView([-15.7801, -47.9292], 4);

    // Google Satellite tiles — substituir por Esri/Bing antes de producao.
    L.tileLayer('https://mt{s}.google.com/vt/lyrs=s&hl=pt&x={x}&y={y}&z={z}', {
      subdomains: ['0', '1', '2', '3'],
      maxZoom: 22,
    }).addTo(this.leafletMap);

    this.leafletMap.on('click', (e: L.LeafletMouseEvent) => {
      const { lat, lng } = e.latlng;
      this.pickerCoords.set({ lat, lng });
      if (this.leafletMarker) {
        this.leafletMarker.setLatLng([lat, lng]);
      } else {
        this.leafletMarker = L.marker([lat, lng], {
          icon: L.divIcon({
            className: '',
            html: '<div style="width:14px;height:14px;background:#ff4444;border:2px solid #fff;border-radius:50%;box-shadow:0 2px 8px rgba(0,0,0,0.7)"></div>',
            iconAnchor: [7, 7],
          }),
        }).addTo(this.leafletMap!);
      }
    });
  }

  async fetchElevation(): Promise<void> {
    const coords = this.pickerCoords();
    if (!coords) return;
    this.fetchingElevation.set(true);
    try {
      const res  = await fetch(
        `https://api.open-elevation.com/api/v1/lookup?locations=${coords.lat},${coords.lng}`
      );
      const data = await res.json();
      const elev = data?.results?.[0]?.elevation;
      if (elev != null) this.altValue = Math.round(elev * 10) / 10;
    } catch {
      // falha silenciosa — usuario preenche manualmente
    } finally {
      this.fetchingElevation.set(false);
    }
  }

  addGcp(): void {
    const coords = this.pickerCoords();
    if (!coords) return;

    const label = (this.labelValue || '').trim()
      || `GCP-${String(this.gcpPoints.length + 1).padStart(2, '0')}`;
    const alt = this.altValue ?? 0;

    const existing = this.gcpPoints;
    const dupCoord = existing.some(e => e.lat === coords.lat && e.lng === coords.lng);
    const dupLabel = existing.some(e => e.label.trim().toLowerCase() === label.toLowerCase());

    if (dupCoord || dupLabel) {
      alert(`[AVISO] Ponto duplicado: ${dupLabel ? 'nome "' + label + '" ja existe' : 'coordenadas identicas a um ponto existente'}.`);
      return;
    }

    const id = `gcp-map-${Date.now()}`;
    this.gcpAdded.emit({ id, label, lat: coords.lat, lng: coords.lng, alt });

    // Prepara proximo ponto sem fechar o painel
    const next = existing.length + 2; // +1 novo que foi adicionado + 1 para o proximo
    this.labelValue = `GCP-${String(next).padStart(2, '0')}`;
    this.altValue   = null;
    this.pickerCoords.set(null);

    if (this.leafletMarker) {
      this.leafletMap?.removeLayer(this.leafletMarker);
      this.leafletMarker = undefined;
    }
  }

  private destroyMap(): void {
    this.leafletMarker = undefined;
    if (this.leafletMap) {
      this.leafletMap.remove();
      this.leafletMap = undefined;
    }
  }

  ngOnDestroy(): void {
    this.destroyMap();
  }
}
