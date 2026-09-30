/**
 * ============================================================================
 * MEASUREMENT TAB COMPONENT
 * ============================================================================
 * 
 * Orquestrador fino: conecta toolbar -> mapa -> servico de calculo -> painel.
 *
 * Toda logica pesada esta delegada a:
 *  - MapDrawingService     : desenho interativo no Leaflet
 *  - MeasurementService    : calculos geodesicos
 *  - data-source-detection : deteccao de assets da task
 *
 * @version 4.0.0
 */

import {
  Component, Input, OnInit, OnDestroy, OnChanges, SimpleChanges,
  signal, computed, ChangeDetectorRef, inject, effect, NgZone
} from '@angular/core';
import { AnnotationService } from '../../services/annotation.service';
import { AnnotationsPanelComponent } from '../../components/annotations-panel/annotations-panel.component';
import { Annotation, CreateAnnotationRequest } from '../../models/annotation.model';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ProcessingTask } from '../../services/task.service';

// Visualizadores
import { OrthophotoViewerComponent } from '../../../../shared/viewers/orthophoto-viewer/orthophoto-viewer.component';
import { DemViewerComponent } from '../../../../shared/viewers/dem-viewer/dem-viewer.component';
import { PointcloudViewerComponent } from '../../../../shared/viewers/pointcloud-viewer/pointcloud-viewer.component';

// Medicao
import { MeasurementService } from '../../../measurement/services/measurement.service';
import { MapDrawingService } from '../../../measurement/services/map-drawing.service';
import { DsmElevationService, VolumeResult } from '../../../measurement/services/dsm-elevation.service';
import { MeasurementUnit, MeasurementResult } from '../../../measurement/models/measurement.model';

// Helpers locais
import { DataSourceType, detectAvailableAssets } from './data-source-detection';
import { MeasurementApiService } from '../../../measurement/services/measurement-api.service';
import { MeasurementExportModalComponent } from '../../../measurement/components/export-modal/measurement-export-modal.component';
import { ElevationProfileHoverService } from '../../../measurement/services/elevation-profile-hover.service';

// Sub-componentes do módulo de medições
import { MeasurementData, ActiveTool } from '../../../measurement/models/measurement-data';
import { MeasDrawingToolbarComponent } from '../../../measurement/components/drawing-toolbar/meas-drawing-toolbar.component';
import { MeasListComponent } from '../../../measurement/components/measurement-list/meas-list.component';

import * as L from 'leaflet';
import { AuthService } from '../../../../core/services/auth.service';

// ============================================================================
// Tipos (definidos em measurement-data.ts; re-exportados para retrocompatibilidade)
// ============================================================================
export type { MeasurementData, ActiveTool };

// ============================================================================
// Component
// ============================================================================

@Component({
  selector: 'app-measurement-tab',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    OrthophotoViewerComponent,
    DemViewerComponent,
    PointcloudViewerComponent,
    MeasurementExportModalComponent,
    MeasDrawingToolbarComponent,
    MeasListComponent,
    AnnotationsPanelComponent
  ],
  providers: [MeasurementService, MapDrawingService, DsmElevationService],
  templateUrl: './measurement-tab.component.html',
  styleUrls: ['./measurement-tab.component.scss']
})
export class MeasurementTabComponent implements OnInit, OnChanges, OnDestroy {

  // --- Inputs ---------------------------------------------------------------
  @Input() projectId!: number;
  @Input() task?: ProcessingTask;

  /** Sinaliza visibilidade da aba — usado para invalidateSize() apos [hidden] */
  @Input() set visible(val: boolean) {
    if (val && this._activeMap) {
      setTimeout(() => { try { this._activeMap?.invalidateSize(); } catch {} }, 80);
    }
  }

  get taskId(): number | undefined { return this.task?.id; }
  get nodeodmTaskId(): string | undefined { return this.task?.nodeodmTaskId; }

  // --- Injects --------------------------------------------------------------
  private cdr = inject(ChangeDetectorRef);
  private measurementService = inject(MeasurementService);
  private drawingService = inject(MapDrawingService);
  private dsmElevationService = inject(DsmElevationService);
  private measurementApiService = inject(MeasurementApiService);
  private hoverSvc = inject(ElevationProfileHoverService);
  annotationService = inject(AnnotationService);
  private authService = inject(AuthService);

  /** Referencia ao mapa Leaflet ativo (ortofoto ou DSM) */
  private _activeMap: L.Map | null = null;

  /** Marcador temporario sincronizado com o hover no grafico de perfil */
  private hoverMarker: L.CircleMarker | null = null;

  // --- Anotações -------------------------------------------------------------
  private annotationsLayer: L.LayerGroup | null = null;
  private tempAnnotationMarker: L.Marker | null = null;
  private tempPolyline: L.Polyline | null = null;
  private tempPolygon: L.Polygon | null = null;
  annotateMode = signal(false);
  annotationType = signal<'MARKER' | 'POLYGON'>('MARKER');
  polygonPoints = signal<L.LatLng[]>([]);

  constructor() {
    // Reage ao hover no ElevationProfileChartComponent colocando/removendo
    // um marcador circular no mapa Leaflet.
    effect(() => {
      const state = this.hoverSvc.hoverState();
      const map = this.drawingService.getMap();
      if (this.hoverMarker) {
        try { map?.removeLayer(this.hoverMarker); } catch { /* ignore */ }
        this.hoverMarker = null;
      }
      if (state && map) {
        this.hoverMarker = L.circleMarker([state.lat, state.lng], {
          radius: 7,
          color: '#ffffff',
          fillColor: '#58a6ff',
          fillOpacity: 0.9,
          weight: 2
        }).addTo(map);
      }
    });

    // Re-renderiza marcadores de anotação sempre que anotações mudarem (visible está embutido)
    effect(() => {
      this.annotationService.annotations();
      this.renderAnnotationMarkers();
    });
  }

  // --- Data-source state ----------------------------------------------------
  selectedDataSource = signal<DataSourceType>('');
  isLoading = signal(false);

  orthophotoUrl = signal<string | null>(null);
  dsmUrl = signal<string | null>(null);
  dtmUrl = signal<string | null>(null);
  pointcloudUrl = signal<string | null>(null);

  private _hasOrthophoto = computed(() => !!this.orthophotoUrl());
  private _hasDSM = computed(() => !!(this.dsmUrl() || this.dtmUrl()));
  private _hasPointcloud = computed(() => !!this.pointcloudUrl());

  mapCenter = signal<[number, number]>([-23.5505, -46.6333]);
  mapZoom = signal(18);

  // --- Sidebar collapse state -----------------------------------------------
  sidebarCollapsed = signal(false);

  toggleSidebar(): void { this.sidebarCollapsed.update(v => !v); }

  // (painel de detalhes e edição de nome → MeasListComponent + MeasItemComponent)
  // =========================================================================

  isVisible(id: string): boolean {
    return this.visibleIds().has(id);
  }

  toggleVisibility(m: MeasurementData, show: boolean): void {
    const latLngs = m.coordinates.map(c => L.latLng(c[0], c[1]));
    const label = `${m.name}: ${m.value.toFixed(2)} ${m.unit}`;
    if (show) {
      this.drawingService.replayOne(m.id, latLngs, m.type, label);
      this.visibleIds.update(s => new Set(s).add(m.id));
    } else {
      this.drawingService.removeCompletedLayer(m.id);
      this.visibleIds.update(s => { const n = new Set(s); n.delete(m.id); return n; });
    }
    // Atualização otimista no signal local
    this.measurements.update(list => list.map(item => item.id === m.id ? { ...item, visible: show } : item));
    // Persiste no backend
    this.measurementApiService.updateVisibility(this.projectId, m.id, show).subscribe({
      error: () => {
        // Reverte em caso de erro
        this.measurements.update(list => list.map(item => item.id === m.id ? { ...item, visible: !show } : item));
      }
    });
  }

  // --- Drawing state (expostos ao template) ---------------------------------
  activeTool = signal<ActiveTool>(null);
  drawingPoints = signal<L.LatLng[]>([]);
  liveResult = signal<string>('');
  isDrawing = signal(false);
  isQuerying = signal(false); // consultando DSM (altura)

  // --- Measurement results --------------------------------------------------
  measurements = signal<MeasurementData[]>([]);

  /** IDs das medições atualmente visíveis no mapa */
  visibleIds = signal<Set<string>>(new Set<string>());

  /** Controla visibilidade do popup de exportacao */
  exportPopupOpen = signal(false);

  openExportPopup(): void  { this.exportPopupOpen.set(true); }
  closeExportPopup(): void { this.exportPopupOpen.set(false); }

  // =========================================================================
  // Anotações
  // =========================================================================

  startAnnotating(type: 'MARKER' | 'POLYGON'): void {
    if (this.activeTool()) { this.cancelMeasurement(); }
    this.cancelAnnotation();
    this.annotationType.set(type);
    this.annotateMode.set(true);
    if (this._activeMap) {
      this._activeMap.getContainer().style.cursor = 'crosshair';
    }
  }

  cancelAnnotation(): void {
    if (this._activeMap) {
      this._activeMap.closePopup();
      this._activeMap.getContainer().style.cursor = '';
    }
    if (this.tempAnnotationMarker && this._activeMap) {
      this._activeMap.removeLayer(this.tempAnnotationMarker);
      this.tempAnnotationMarker = null;
    }
    if (this.tempPolyline && this._activeMap) {
      this._activeMap.removeLayer(this.tempPolyline);
      this.tempPolyline = null;
    }
    if (this.tempPolygon && this._activeMap) {
      this._activeMap.removeLayer(this.tempPolygon);
      this.tempPolygon = null;
    }
    this.polygonPoints.set([]);
    this.annotateMode.set(false);
  }

  completePolygon(): void {
    const points = this.polygonPoints();
    if (points.length < 3 || !this._activeMap) return;
    this.annotateMode.set(false);
    this._activeMap.getContainer().style.cursor = '';
    const lat = points.reduce((sum, p) => sum + p.lat, 0) / points.length;
    const lng = points.reduce((sum, p) => sum + p.lng, 0) / points.length;
    const form = this.buildAnnotationFormPolygon(points);
    L.popup({ minWidth: 200 }).setLatLng([lat, lng]).setContent(form).openOn(this._activeMap);
  }

  private onAnnotateMapClick(e: L.LeafletMouseEvent): void {
    if (!this.annotateMode() || !this._activeMap) return;

    if (this.annotationType() === 'MARKER') {
      if (this.tempAnnotationMarker) {
        this._activeMap.removeLayer(this.tempAnnotationMarker);
        this.tempAnnotationMarker = null;
      }
      const { lat, lng } = e.latlng;
      this.tempAnnotationMarker = L.marker([lat, lng], { icon: this.createAnnotationIcon(), opacity: 0.85 }).addTo(this._activeMap);
      const form = this.buildAnnotationForm(lat, lng);
      this.tempAnnotationMarker.bindPopup(L.popup({ minWidth: 200 }).setContent(form)).openPopup();
    } else {
      this.polygonPoints.update(pts => [...pts, e.latlng]);
      this.updateTempPolygon();
    }
  }

  private updateTempPolygon(): void {
    const points = this.polygonPoints();
    if (this.tempPolyline) { this._activeMap?.removeLayer(this.tempPolyline); this.tempPolyline = null; }
    if (this.tempPolygon)  { this._activeMap?.removeLayer(this.tempPolygon);  this.tempPolygon  = null; }
    if (!this._activeMap || points.length < 2) return;
    if (points.length >= 3) {
      this.tempPolygon = L.polygon(points, { color: '#3b5bdb', weight: 2, fillOpacity: 0.2 }).addTo(this._activeMap);
    } else {
      this.tempPolyline = L.polyline(points, { color: '#3b5bdb', weight: 2, dashArray: '6 4' }).addTo(this._activeMap);
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

  // =========================================================================
  // Lifecycle
  // =========================================================================

  ngOnInit(): void {
    this.detectData();
    this.loadMeasurements();
    this.annotationService.connectToProject(this.projectId);
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['task'] && !changes['task'].firstChange) {
      const prev = changes['task'].previousValue as ProcessingTask | undefined;
      const curr = changes['task'].currentValue as ProcessingTask | undefined;
      // Só re-detecta se o ID da task ou status mudou de verdade
      // Evita reset ao receber nova referência do mesmo objeto (change detection)
      if (prev?.id !== curr?.id || prev?.status !== curr?.status) {
        this.detectData();
        this.loadMeasurements();
      }
    }
  }

  ngOnDestroy(): void {
    this.drawingService.destroy();
    this.annotationService.disconnectFromProject();
  }

  // =========================================================================
  // Mapa pronto (evento do OrthophotoViewer)
  // =========================================================================

  onMapReady(map: L.Map): void {
    this.cancelAnnotation();
    this._activeMap = map;
    this.drawingService.setMap(map);
    this.visibleIds.set(new Set());

    this.annotationsLayer = L.layerGroup().addTo(map);
    this.renderAnnotationMarkers();
    map.on('click', (e: L.LeafletMouseEvent) => this.onAnnotateMapClick(e));

    this.replayLoadedMeasurements();
  }

  // =========================================================================
  // Ativacao de ferramentas
  // =========================================================================

  activateDistance(): void { this.toggleTool('distance'); }
  activateArea(): void    { this.toggleTool('area'); }
  activateVolume(): void  { this.toggleTool('volume'); }
  activateHeight(): void  { this.toggleTool('height'); }
  activateElevationProfile(): void { this.toggleTool('elevation_profile'); }

  private toggleTool(tool: ActiveTool): void {
    if (this.activeTool() === tool) {
      this.cancelMeasurement();
      return;
    }

    this.cancelAnnotation();
    this.drawingService.cancel();
    this.resetDrawingState();

    if (!this.drawingService.getMap()) {
      console.warn('[MeasurementTab] Mapa nao disponivel');
      return;
    }

    this.activeTool.set(tool);
    this.isDrawing.set(true);

    if (tool === 'height') {
      this.liveResult.set('Clique no ponto A (inicio)');
      this.drawingService.start(
        (pts) => this.onHeightPointsChanged(pts),
        (pts) => this.onDrawingCompleted(pts),
        'twopoint'
      );
    } else if (tool === 'volume') {
      this.liveResult.set('Desenhe o poligono da area a medir (clique direito para finalizar)');
      this.drawingService.start(
        (pts) => this.onPointsChanged(pts),
        (pts) => this.onDrawingCompleted(pts),
        'polygon'
      );
    } else if (tool === 'elevation_profile') {
      this.liveResult.set('Desenhe o perfil: clique para adicionar pontos, clique direito para finalizar');
      this.drawingService.start(
        (pts) => this.onPointsChanged(pts),
        (pts) => this.onDrawingCompleted(pts),
        'line'
      );
    } else {
      this.liveResult.set('Clique no mapa para iniciar');
      const drawMode = tool === 'area' ? 'polygon' as const : 'line' as const;
      this.drawingService.start(
        (pts) => this.onPointsChanged(pts),
        (pts) => this.onDrawingCompleted(pts),
        drawMode
      );
    }

    this.cdr.detectChanges();
  }

  // =========================================================================
  // Callbacks do MapDrawingService
  // =========================================================================

  private onPointsChanged(points: L.LatLng[]): void {
    this.drawingPoints.set(points);
    this.updateLiveResult(points);
    this.cdr.detectChanges();
  }

  private onHeightPointsChanged(points: L.LatLng[]): void {
    this.drawingPoints.set(points);
    // Feedback progressivo para o modo altura
    if (points.length === 0) this.liveResult.set('Clique no ponto A (inicio)');
    if (points.length === 1) this.liveResult.set('Ponto A marcado. Clique no ponto B (fim)');
    this.cdr.detectChanges();
  }

  private onDrawingCompleted(points: L.LatLng[]): void {
    if (this.activeTool() === 'height') {
      this.completeHeightMeasurement(points);
    } else if (this.activeTool() === 'volume') {
      this.completeVolumeMeasurement(points);
    } else if (this.activeTool() === 'elevation_profile') {
      this.completeElevationProfileMeasurement(points);
    } else {
      this.completeMeasurement();
    }
  }

  // =========================================================================
  // Acoes de medicao
  // =========================================================================

  completeMeasurement(): void {
    const points = this.drawingService.getPoints();
    const tool = this.activeTool();

    if (points.length < 2 || !tool) {
      this.cancelMeasurement();
      return;
    }

    // Volume é assíncrono — despacha para o fluxo específico
    if (tool === 'volume') {
      this.completeVolumeMeasurement(points);
      return;
    }

    const result = this.calculateResult(tool, points);
    const typeLabel = this.getTypeLabel(tool);

    // Criar entrada primeiro para ter o id
    const entry: MeasurementData = {
      id: crypto.randomUUID(),
      name: `${typeLabel} ${this.measurements().length + 1}`,
      type: tool,
      value: result.value,
      unit: result.unit,
      dataSource: this.selectedDataSource(),
      coordinates: points.map(p => [p.lat, p.lng]),
      visible: true,
      createdAt: new Date()
    };

    // Finalizar no mapa associando ao id da entrada
    this.drawingService.finalize(`Total: ${result.displayValue}`, entry.id);
    this.visibleIds.update(s => new Set(s).add(entry.id));

    this.measurements.update(list => [...list, entry]);
    this.saveEntry(entry);
    this.resetDrawingState();
    this.cdr.detectChanges();
  }

  cancelMeasurement(): void {
    this.drawingService.cancel();
    this.resetDrawingState();
    this.cdr.detectChanges();
  }

  // =========================================================================
  // Medicao de Volume (assincrona — consulta DSM pixel a pixel)
  // =========================================================================

  private async completeVolumeMeasurement(points: L.LatLng[]): Promise<void> {
    if (points.length < 3) {
      this.cancelMeasurement();
      return;
    }

    const dsmUrl = this.dsmUrl() || this.dtmUrl();
    if (!dsmUrl) {
      this.cancelMeasurement();
      return;
    }

    this.isQuerying.set(true);
    this.liveResult.set('Calculando volume no DSM...');
    this.cdr.detectChanges();

    try {
      const polygon = points.map(p => ({ lat: p.lat, lng: p.lng }));
      const result: VolumeResult = await this.dsmElevationService.calculateVolume(dsmUrl, polygon);

      if (!result.valid) {
        this.liveResult.set('Poligono fora da area do DSM ou sem dados');
        this.drawingService.cancel();
        this.resetDrawingState();
        this.isQuerying.set(false);
        this.cdr.detectChanges();
        return;
      }

      const volumeM3 = result.volume;
      const displayValue = `${volumeM3.toFixed(3)} m³`;
      const labelHtml =
        `Vol: ${displayValue} | Base: ${result.baseElevation.toFixed(2)} m | ${result.pixelCount} px`;

      const entry: MeasurementData = {
        id: crypto.randomUUID(),
        name: `Volume ${this.measurements().length + 1}`,
        type: 'volume',
        value: volumeM3,
        unit: 'm³',
        dataSource: this.selectedDataSource(),
        coordinates: points.map(p => [p.lat, p.lng]),
        visible: true,
        createdAt: new Date()
      };

      this.drawingService.finalize(labelHtml, entry.id);
      this.visibleIds.update(s => new Set(s).add(entry.id));
      this.measurements.update(list => [...list, entry]);
      this.saveEntry(entry);

    } catch (err) {
      console.error('[MeasurementTab] Erro ao calcular volume:', err);
      this.liveResult.set('Erro ao calcular volume no DSM');
      this.drawingService.cancel();
    }

    this.resetDrawingState();
    this.isQuerying.set(false);
    this.cdr.detectChanges();
  }

  // =========================================================================
  // Medicao de Altura (assincrona — consulta DSM)
  // =========================================================================

  private async completeHeightMeasurement(points: L.LatLng[]): Promise<void> {
    if (points.length < 2) {
      this.cancelMeasurement();
      return;
    }

    const dsmUrl = this.dsmUrl() || this.dtmUrl();
    if (!dsmUrl) {
      this.cancelMeasurement();
      return;
    }

    this.isQuerying.set(true);
    this.liveResult.set('Consultando elevação no DSM...');
    this.cdr.detectChanges();

    try {
      const [ptA, ptB] = points;

      const [elevA, elevB] = await Promise.all([
        this.dsmElevationService.getElevationAt(dsmUrl, ptA.lat, ptA.lng),
        this.dsmElevationService.getElevationAt(dsmUrl, ptB.lat, ptB.lng)
      ]);

      if (!elevA.valid || !elevB.valid) {
        this.liveResult.set('Ponto fora da área do DSM');
        this.drawingService.cancel();
        this.resetDrawingState();
        this.isQuerying.set(false);
        this.cdr.detectChanges();
        return;
      }

      const diff = elevB.elevation - elevA.elevation;
      const absDiff = Math.abs(diff);
      const sign = diff >= 0 ? '+' : '-';
      const displayValue = `${sign}${absDiff.toFixed(3)} m`;

      // Label no mapa com elevacoes e diferenca
      const labelHtml =
        `Pt A: ${elevA.elevation.toFixed(2)} m | ` +
        `Pt B: ${elevB.elevation.toFixed(2)} m | ` +
        `Δ: ${displayValue}`;

      const entry: MeasurementData = {
        id: crypto.randomUUID(),
        name: `Altura ${this.measurements().length + 1}`,
        type: 'height',
        value: diff,
        unit: 'm',
        dataSource: this.selectedDataSource(),
        // Armazena elevacao como 3o elemento [lat, lng, elev] para exportacao
        coordinates: [
          [ptA.lat, ptA.lng, elevA.elevation],
          [ptB.lat, ptB.lng, elevB.elevation]
        ],
        visible: true,
        createdAt: new Date()
      };

      this.drawingService.finalize(labelHtml, entry.id);
      this.visibleIds.update(s => new Set(s).add(entry.id));
      this.measurements.update(list => [...list, entry]);
      this.saveEntry(entry);

    } catch (err) {
      console.error('[MeasurementTab] Erro ao consultar DSM:', err);
      this.liveResult.set('Erro ao consultar elevação no DSM');
      this.drawingService.cancel();
    }

    this.resetDrawingState();
    this.isQuerying.set(false);
    this.cdr.detectChanges();
  }

  // =========================================================================
  // Perfil de Elevacao (assincrono — amostra N pontos ao longo da linha)
  // =========================================================================

  private async completeElevationProfileMeasurement(points: L.LatLng[]): Promise<void> {
    if (points.length < 2) {
      this.cancelMeasurement();
      return;
    }

    const dsmUrl = this.dsmUrl() || this.dtmUrl();
    if (!dsmUrl) {
      this.cancelMeasurement();
      return;
    }

    this.isQuerying.set(true);
    this.liveResult.set('Amostrando perfil de elevacao no DSM...');
    this.cdr.detectChanges();

    try {
      const waypoints = points.map(p => ({ lat: p.lat, lng: p.lng }));
      const samples = await this.dsmElevationService.sampleElevationProfile(dsmUrl, waypoints, 100);

      const validSamples = samples.filter(s => s.valid);
      if (validSamples.length === 0) {
        this.liveResult.set('Linha fora da area do DSM ou sem dados validos');
        this.drawingService.cancel();
        this.resetDrawingState();
        this.isQuerying.set(false);
        this.cdr.detectChanges();
        return;
      }

      const totalDist = samples[samples.length - 1]?.distanceFromStart ?? 0;
      const elevs = validSamples.map(s => s.elevation);
      const minElev = Math.min(...elevs);
      const maxElev = Math.max(...elevs);
      const distLabel = totalDist >= 1000
        ? `${(totalDist / 1000).toFixed(2)} km`
        : `${totalDist.toFixed(1)} m`;

      const labelHtml =
        `Perfil ${distLabel} | Elev: ${minElev.toFixed(1)}\u2013${maxElev.toFixed(1)} m`;

      const entry: MeasurementData = {
        id: crypto.randomUUID(),
        name: `Perfil ${this.measurements().length + 1}`,
        type: 'elevation_profile',
        value: totalDist,
        unit: 'm',
        dataSource: this.selectedDataSource(),
        // Armazena os 100 pontos amostrados como [lat, lng, elev]
        coordinates: samples.map(s => [s.lat, s.lng, s.elevation]),
        visible: true,
        createdAt: new Date()
      };

      this.drawingService.finalize(labelHtml, entry.id);
      this.visibleIds.update(s => new Set(s).add(entry.id));
      this.measurements.update(list => [...list, entry]);
      this.saveEntry(entry);

    } catch (err) {
      console.error('[MeasurementTab] Erro ao amostrar perfil de elevacao:', err);
      this.liveResult.set('Erro ao amostrar perfil de elevacao no DSM');
      this.drawingService.cancel();
    }

    this.resetDrawingState();
    this.isQuerying.set(false);
    this.cdr.detectChanges();
  }

  undoLastPoint(): void {
    this.drawingService.undoLastPoint();
    this.drawingPoints.set(this.drawingService.getPoints());
    this.updateLiveResult(this.drawingService.getPoints());
    this.cdr.detectChanges();
  }

  clearAllMeasurements(): void {
    // Remove todas do backend antes de limpar o estado local
    if (this.projectId && this.task?.id) {
      const projectId = this.projectId;
      this.measurements().forEach(m => {
        this.measurementApiService.deleteMeasurement(projectId, m.id).subscribe({
          error: err => console.error('[MeasurementTab] Erro ao deletar medição:', err)
        });
      });
    }
    this.drawingService.cancel();
    this.drawingService.removeAllCompletedLayers();
    this.measurements.set([]);
    this.visibleIds.set(new Set());
    this.resetDrawingState();
    this.cdr.detectChanges();
  }

  deleteMeasurement(id: string): void {
    // Remove do mapa (se estiver visível) e do backend
    this.drawingService.removeCompletedLayer(id);
    this.visibleIds.update(s => { const n = new Set(s); n.delete(id); return n; });
    if (this.projectId && this.task?.id) {
      this.measurementApiService.deleteMeasurement(this.projectId, id).subscribe({
        error: err => console.error('[MeasurementTab] Erro ao deletar medição:', err)
      });
    }
    this.measurements.update(list => list.filter(m => m.id !== id));
    this.cdr.detectChanges();
  }

  // =========================================================================
  // Calculo (delega ao MeasurementService)
  // =========================================================================

  private calculateResult(tool: ActiveTool, points: L.LatLng[]): MeasurementResult {
    const measPts = points.map((ll, i) => ({
      id: `p${i}`, lat: ll.lat, lng: ll.lng, timestamp: new Date()
    }));

    switch (tool) {
      case 'distance':
        return this.measurementService.calculateDistance(measPts);
      case 'area':
        return this.measurementService.calculateArea(measPts, MeasurementUnit.SQUARE_METERS);
      case 'volume':
      case 'height':
      default:
        return { value: 0, unit: MeasurementUnit.METERS, displayValue: 'Em calculo...', points: measPts, precision: 2 } as MeasurementResult;
    }
  }

  private updateLiveResult(points: L.LatLng[]): void {
    if (points.length < 2) {
      this.liveResult.set(
        points.length === 1
          ? 'Clique para adicionar mais pontos. Clique direito para finalizar.'
          : 'Clique no mapa para iniciar'
      );
      return;
    }

    const result = this.calculateResult(this.activeTool(), points);
    this.liveResult.set(`${result.displayValue}  |  Clique direito para finalizar`);
  }

  // =========================================================================
  // Foco / navegação no mapa
  // =========================================================================

  /**
   * Ao clicar em uma medição salva:
   * 1. Desenha-a no mapa ativo (se ainda não estiver visível)
   * 2. Navega (flyTo/flyToBounds) até ela
   */
  focusMeasurement(m: MeasurementData): void {
    // Só centraliza se a medição estiver visível no mapa
    if (!this.isVisible(m.id)) return;
    const map = this.drawingService.getMap();
    if (!map || m.coordinates.length === 0) return;

    const latLngs = m.coordinates.map(c => L.latLng(c[0], c[1]));

    if (latLngs.length === 1) {
      map.flyTo(latLngs[0], Math.max(map.getZoom(), 17), { duration: 0.6 });
    } else {
      map.flyToBounds(L.latLngBounds(latLngs).pad(0.4), { maxZoom: 20, duration: 0.6 });
    }
  }

  // =========================================================================
  // Persistência de medições (API)
  // =========================================================================

  /**
   * Carrega do backend as medições salvas para o chunk atual.
   */
  private loadMeasurements(): void {
    if (!this.projectId || !this.task?.id) return;
    this.measurementApiService.getMeasurements(this.projectId, this.task.id).subscribe({
      next: data => {
        this.measurements.set(data);
        this.replayLoadedMeasurements();
        this.cdr.detectChanges();
      },
      error: err => console.error('[MeasurementTab] Erro ao carregar medições:', err)
    });
  }

  private replayLoadedMeasurements(): void {
    if (!this._activeMap) return;
    const current = this.visibleIds();
    const toAdd: string[] = [];
    for (const m of this.measurements()) {
      if (current.has(m.id)) continue;
      if (m.visible === false) continue;
      const latLngs = m.coordinates.map(c => L.latLng(c[0], c[1]));
      const label = `${m.name}: ${m.value.toFixed(2)} ${m.unit}`;
      this.drawingService.replayOne(m.id, latLngs, m.type, label);
      toAdd.push(m.id);
    }
    if (toAdd.length > 0) {
      this.visibleIds.update(s => {
        const next = new Set(s);
        toAdd.forEach(id => next.add(id));
        return next;
      });
    }
  }

  /**
   * Salva uma medição no backend e atualiza o id local com o id do servidor.
   */
  private saveEntry(entry: MeasurementData): void {
    if (!this.projectId || !this.task?.id) return;
    const tempId = entry.id;
    this.measurementApiService.saveMeasurement(this.projectId, this.task.id, entry).subscribe({
      next: saved => {
        this.measurements.update(list => list.map(m => m.id === tempId ? saved : m));
        this.drawingService.updateLayerId(tempId, saved.id);
        // Mantém visibilidade: substitui tempId pelo id definitivo do servidor
        this.visibleIds.update(s => {
          if (!s.has(tempId)) return s;
          const next = new Set(s);
          next.delete(tempId);
          next.add(saved.id);
          return next;
        });
      },
      error: err => console.error('[MeasurementTab] Erro ao salvar medição:', err)
    });
  }

  // =========================================================================
  // Deteccao de dados (delegado a helper puro)
  // =========================================================================

  private detectData(): void {
    if (!this.task) return;
    const isCompleted = this.task.status === 'COMPLETED' || this.task.status === 'COMPLETED_WITH_WARNINGS';
    if (!isCompleted) return;

    this.isLoading.set(true);

    const { assets, autoSelected } = detectAvailableAssets(
      this.projectId, this.task.id,
      this.task.outputs, isCompleted
    );

    this.orthophotoUrl.set(assets.orthophotoUrl);
    this.dsmUrl.set(assets.dsmUrl);
    this.dtmUrl.set(assets.dtmUrl);
    this.pointcloudUrl.set(assets.pointcloudUrl);
    this.selectedDataSource.set(autoSelected);

    this.isLoading.set(false);
  }

  // =========================================================================
  // Template helpers
  // =========================================================================

  hasProcessedData(): boolean {
    if (!this.task) return false;
    const ok = this.task.status === 'COMPLETED' || this.task.status === 'COMPLETED_WITH_WARNINGS';
    return ok && (this._hasOrthophoto() || this._hasDSM() || this._hasPointcloud());
  }

  hasOrthophoto(): boolean  { return this._hasOrthophoto(); }
  hasDSM(): boolean         { return this._hasDSM(); }
  hasPointcloud(): boolean  { return this._hasPointcloud(); }

  onDataSourceChange(): void {
    this.cancelMeasurement();
    // Nao zerar o mapa aqui — o novo viewer emitira mapReady ao ser criado
    this.isLoading.set(true);
    setTimeout(() => this.isLoading.set(false), 300);
  }

  // =========================================================================
  // Handlers para eventos dos sub-componentes
  // =========================================================================

  /** Ativação de ferramenta via MeasDrawingToolbarComponent */
  onToolActivated(tool: NonNullable<ActiveTool>): void {
    this.toggleTool(tool);
  }

  /** Visibilidade de medição via MeasListComponent */
  onVisibilityChange(e: { m: MeasurementData; show: boolean }): void {
    this.toggleVisibility(e.m, e.show);
  }

  /** Foco no mapa via MeasListComponent */
  onFocusFromList(m: MeasurementData): void {
    this.focusMeasurement(m);
  }

  /** Deleção via MeasListComponent */
  onDeleteFromList(id: string): void {
    this.deleteMeasurement(id);
  }

  /** Renomeação concluída via MeasListComponent — atualiza signal local */
  onMeasurementRenamed(e: { id: string; name: string }): void {
    this.measurements.update(list =>
      list.map(m => m.id === e.id ? { ...m, name: e.name } : m)
    );
  }

  // =========================================================================
  // Internos
  // =========================================================================

  private resetDrawingState(): void {
    this.activeTool.set(null);
    this.isDrawing.set(false);
    this.drawingPoints.set([]);
    this.liveResult.set('');
  }

  private getTypeLabel(tool: ActiveTool): string {
    return {
      distance: 'Distancia', area: 'Area', volume: 'Volume',
      height: 'Altura', elevation_profile: 'Perfil'
    }[tool!] || 'Medicao';
  }

}
// Exportações de medições foram movidas para MeasurementExportModalComponent