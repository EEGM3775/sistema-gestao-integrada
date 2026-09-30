/**
 * MapDrawingService
 *
 * Responsavel por TODA a interacao de desenho no mapa Leaflet:
 *  - Registrar/remover event handlers (click, dblclick, mousemove)
 *  - Criar/atualizar polylines, markers e labels de segmento
 *  - Gerenciar camadas de medicoes finalizadas
 *  - Undo de pontos
 *
 * Nao conhece Angular signals — recebe callbacks puros para notificar o componente.
 * Pode ser injetado em qualquer componente que tenha um L.Map.
 */

import { Injectable } from '@angular/core';
import * as L from 'leaflet';
import { DEFAULT_MEASUREMENT_STYLE } from '../models/measurement.model';

// ============================================================================
// Tipos publicos
// ============================================================================

/** Modo de desenho: linha (distancia), poligono (area) ou dois pontos (altura) */
export type DrawMode = 'line' | 'polygon' | 'twopoint';

/** Callback emitido a cada mudanca nos pontos de desenho */
export type PointsChangedFn = (points: L.LatLng[]) => void;

/** Callback emitido quando o usuario finaliza (double-click) */
export type DrawingCompletedFn = (points: L.LatLng[]) => void;

export interface DrawingSession {
  /** Pontos coletados ate agora */
  points: L.LatLng[];
}

// ============================================================================
// Service
// ============================================================================

@Injectable()
export class MapDrawingService {

  // ----- Estado interno do desenho -----
  private map: L.Map | null = null;
  private active = false;
  private points: L.LatLng[] = [];

  // Modo de desenho
  private drawMode: DrawMode = 'line';

  // Camadas de desenho (temporarias)
  private polyline: L.Polyline | null = null;
  private polygon: L.Polygon | null = null;
  private markers: L.CircleMarker[] = [];
  private labels: L.Marker[] = [];

  // Camadas finalizadas indexadas por id da medição (sobrevivem ao undo, somem ao trocar mapa)
  private completedLayers: Map<string, L.LayerGroup> = new Map();

  // Handlers de eventos (guardados para poder remover)
  private clickHandler: ((e: L.LeafletMouseEvent) => void) | null = null;
  private contextMenuHandler: ((e: L.LeafletMouseEvent) => void) | null = null;
  private mouseMoveHandler: ((e: L.LeafletMouseEvent) => void) | null = null;

  // Callbacks para o componente
  private onPointsChanged: PointsChangedFn | null = null;
  private onDrawingCompleted: DrawingCompletedFn | null = null;

  // ========================================================================
  // Ciclo de vida
  // ========================================================================

  /** Define (ou troca) a instancia do mapa Leaflet */
  setMap(map: L.Map): void {
    if (this.active) this.cancel();
    // Refs do mapa anterior tornam-se inválidas — limpa sem tentar remover
    this.completedLayers = new Map();
    this.map = map;
  }

  /** Retorna a instancia atual do mapa, ou null */
  getMap(): L.Map | null {
    return this.map;
  }

  isActive(): boolean {
    return this.active;
  }

  getPoints(): L.LatLng[] {
    return [...this.points];
  }

  // ========================================================================
  // Iniciar / Parar sessao de desenho
  // ========================================================================

  /**
   * Inicia uma nova sessao de desenho.
   * @param onPointsChanged  chamado a cada ponto adicionado/removido
   * @param onDrawingCompleted chamado quando o usuario dá double-click
   * @param mode 'line' para polyline (distancia), 'polygon' para area preenchida
   */
  start(
    onPointsChanged: PointsChangedFn,
    onDrawingCompleted: DrawingCompletedFn,
    mode: DrawMode = 'line'
  ): void {
    if (!this.map) {
      console.warn('[MapDrawingService] Mapa nao definido. Chame setMap() primeiro.');
      return;
    }

    // Limpar qualquer sessao anterior
    this.clearDrawingLayers();

    this.active = true;
    this.points = [];
    this.drawMode = mode;
    this.onPointsChanged = onPointsChanged;
    this.onDrawingCompleted = onDrawingCompleted;

    // Cursor crosshair
    this.map.getContainer().style.cursor = 'crosshair';

    // Registrar handlers
    this.clickHandler = (e) => this.handleClick(e);
    this.contextMenuHandler = (e) => this.handleContextMenu(e);
    this.mouseMoveHandler = (e) => this.handleMouseMove(e);

    this.map.on('click', this.clickHandler);
    this.map.on('contextmenu', this.contextMenuHandler);
    this.map.on('mousemove', this.mouseMoveHandler);
  }

  /** Cancela o desenho atual e remove camadas temporarias */
  cancel(): void {
    this.clearDrawingLayers();
    this.detachHandlers();
    this.active = false;
    this.points = [];
  }

  // ========================================================================
  // Undo
  // ========================================================================

  /** Remove o ultimo ponto adicionado */
  undoLastPoint(): void {
    if (!this.map || this.points.length === 0) return;

    this.points.pop();

    // Remover ultimo marker
    const lastMarker = this.markers.pop();
    if (lastMarker) this.map.removeLayer(lastMarker);

    // Remover ultima label de segmento
    if (this.labels.length > 0 && this.points.length >= 1) {
      const lastLabel = this.labels.pop();
      if (lastLabel) this.map.removeLayer(lastLabel);
    }

    // Atualizar polyline
    if (this.polyline) {
      this.polyline.setLatLngs(this.points);
    }

    // Atualizar polygon
    if (this.drawMode === 'polygon') {
      if (this.points.length >= 3 && this.polygon) {
        this.polygon.setLatLngs(this.points);
      } else if (this.points.length < 3 && this.polygon && this.map) {
        this.map.removeLayer(this.polygon);
        this.polygon = null;
      }
    }

    this.notifyPointsChanged();
  }

  // ========================================================================
  // Finalizacao de medicao
  // ========================================================================

  /**
   * Converte as camadas de desenho atuais em um LayerGroup finalizado
   * e associa ao id da medição para controle posterior.
   */
  finalize(totalLabelHtml: string, measurementId: string): L.LayerGroup | null {
    if (!this.map || this.points.length < 2) return null;

    const group = L.layerGroup();

    // Polyline solida (final)
    group.addLayer(L.polyline([...this.points], {
      color: DEFAULT_MEASUREMENT_STYLE.strokeColor,
      weight: DEFAULT_MEASUREMENT_STYLE.strokeWidth,
      opacity: 1
    }));

    // Polygon preenchido (modo area)
    if (this.drawMode === 'polygon' && this.points.length >= 3) {
      group.addLayer(L.polygon([...this.points], {
        color: DEFAULT_MEASUREMENT_STYLE.strokeColor,
        weight: 1,
        opacity: 0.8,
        fillColor: DEFAULT_MEASUREMENT_STYLE.strokeColor,
        fillOpacity: 0.25
      }));
    }

    // Markers nos vertices
    for (const pt of this.points) {
      group.addLayer(L.circleMarker(pt, {
        radius: 4,
        color: DEFAULT_MEASUREMENT_STYLE.strokeColor,
        fillColor: '#ffffff',
        fillOpacity: 1,
        weight: 2
      }));
    }

    // Labels de segmento (transferir da sessao de desenho)
    for (const lbl of this.labels) {
      group.addLayer(lbl);
    }

    // Label de total no ultimo ponto
    const lastPt = this.points[this.points.length - 1];
    group.addLayer(L.marker(lastPt, {
      icon: L.divIcon({
        className: 'measurement-label measurement-label-total',
        html: `<div class="measurement-label-content total">${totalLabelHtml}</div>`,
        iconSize: undefined,
        iconAnchor: undefined
      }),
      interactive: false
    }));

    group.addTo(this.map);
    this.completedLayers.set(measurementId, group);

    // Limpar desenho sem remover labels (ja transferidas)
    this.clearDrawingLayers(false);
    this.detachHandlers();
    this.active = false;
    this.points = [];

    return group;
  }

  // ========================================================================
  // Gerenciamento de camadas finalizadas
  // ========================================================================

  /** Remove uma camada finalizada pelo id da medição */
  removeCompletedLayer(id: string): void {
    const layer = this.completedLayers.get(id);
    if (layer) {
      layer.remove();
      this.completedLayers.delete(id);
    }
  }

  /** Remove todas as camadas finalizadas */
  removeAllCompletedLayers(): void {
    this.completedLayers.forEach(lg => lg.remove());
    this.completedLayers = new Map();
  }

  /** Atualiza o id de uma camada (id temporário → id do backend após save) */
  updateLayerId(oldId: string, newId: string): void {
    const layer = this.completedLayers.get(oldId);
    if (layer) {
      this.completedLayers.delete(oldId);
      this.completedLayers.set(newId, layer);
    }
  }

  /**
   * Desenha uma medição salva no mapa ativo (idempotente).
   * Usado ao clicar num item da lista — a medição retorna ao mapa sem duplicar.
   */
  replayOne(id: string, coords: L.LatLng[], type: string, label: string): void {
    if (!this.map || coords.length < 2) return;
    if (this.completedLayers.has(id)) return; // já visível

    const isPolygon = type === 'area' || type === 'volume';
    const group = L.layerGroup();

    group.addLayer(L.polyline(coords, {
      color: DEFAULT_MEASUREMENT_STYLE.strokeColor,
      weight: DEFAULT_MEASUREMENT_STYLE.strokeWidth,
      opacity: 1
    }));

    if (isPolygon && coords.length >= 3) {
      group.addLayer(L.polygon(coords, {
        color: DEFAULT_MEASUREMENT_STYLE.strokeColor,
        weight: 1,
        opacity: 0.8,
        fillColor: DEFAULT_MEASUREMENT_STYLE.strokeColor,
        fillOpacity: 0.25
      }));
    }

    for (const pt of coords) {
      group.addLayer(L.circleMarker(pt, {
        radius: 4,
        color: DEFAULT_MEASUREMENT_STYLE.strokeColor,
        fillColor: '#ffffff',
        fillOpacity: 1,
        weight: 2
      }));
    }

    const lastPt = coords[coords.length - 1];
    group.addLayer(L.marker(lastPt, {
      icon: L.divIcon({
        className: 'measurement-label measurement-label-total',
        html: `<div class="measurement-label-content total">${label}</div>`,
        iconSize: undefined,
        iconAnchor: undefined
      }),
      interactive: false
    }));

    group.addTo(this.map);
    this.completedLayers.set(id, group);
  }

  /** Quantidade de camadas finalizadas */
  get completedCount(): number {
    return this.completedLayers.size;
  }

  // ========================================================================
  // Limpeza total (chamado no OnDestroy do componente)
  // ========================================================================

  destroy(): void {
    this.cancel();
    this.removeAllCompletedLayers();
    this.map = null;
  }

  // ========================================================================
  // Handlers internos de mapa
  // ========================================================================

  private handleClick(e: L.LeafletMouseEvent): void {
    if (!this.active || !this.map) return;

    const latlng = e.latlng;
    this.points.push(latlng);

    // Marker no ponto
    const marker = L.circleMarker(latlng, {
      radius: 5,
      color: DEFAULT_MEASUREMENT_STYLE.strokeColor,
      fillColor: '#ffffff',
      fillOpacity: 1,
      weight: 2
    }).addTo(this.map);
    this.markers.push(marker);

    // Polyline (sempre atualizada para mostrar segmentos)
    if (this.polyline) {
      this.polyline.setLatLngs(this.points);
    } else {
      this.polyline = L.polyline(this.points, {
        color: DEFAULT_MEASUREMENT_STYLE.strokeColor,
        weight: DEFAULT_MEASUREMENT_STYLE.strokeWidth,
        opacity: DEFAULT_MEASUREMENT_STYLE.strokeOpacity,
        dashArray: '8, 6'
      }).addTo(this.map);
    }

    // Polygon (apenas no modo 'polygon', a partir de 3 pontos)
    if (this.drawMode === 'polygon' && this.points.length >= 3) {
      if (this.polygon) {
        this.polygon.setLatLngs(this.points);
      } else {
        this.polygon = L.polygon(this.points, {
          color: DEFAULT_MEASUREMENT_STYLE.strokeColor,
          weight: 1,
          opacity: 0.6,
          fillColor: DEFAULT_MEASUREMENT_STYLE.strokeColor,
          fillOpacity: 0.2,
          dashArray: ''
        }).addTo(this.map);
      }
    }

    // Label de segmento
    if (this.points.length >= 2) {
      const prev = this.points[this.points.length - 2];
      const curr = this.points[this.points.length - 1];
      const segDist = haversineDistance(prev.lat, prev.lng, curr.lat, curr.lng);
      const midLat = (prev.lat + curr.lat) / 2;
      const midLng = (prev.lng + curr.lng) / 2;

      const label = L.marker([midLat, midLng], {
        icon: L.divIcon({
          className: 'measurement-label',
          html: `<div class="measurement-label-content">${formatDistance(segDist)}</div>`,
          iconSize: [80, 24],
          iconAnchor: [40, 12]
        }),
        interactive: false
      }).addTo(this.map);
      this.labels.push(label);
    }

    this.notifyPointsChanged();

    // Modo twopoint: finaliza automaticamente apos o 2o clique
    if (this.drawMode === 'twopoint' && this.points.length === 2) {
      this.onDrawingCompleted?.([...this.points]);
    }
  }

  private handleContextMenu(e: L.LeafletMouseEvent): void {
    if (!this.active) return;
    // No modo twopoint nao precisa de clique direito para finalizar
    if (this.drawMode === 'twopoint') return;
    L.DomEvent.preventDefault(e.originalEvent);
    this.onDrawingCompleted?.([...this.points]);
  }

  private handleMouseMove(e: L.LeafletMouseEvent): void {
    if (!this.active || this.points.length === 0) return;
    const preview = [...this.points, e.latlng];
    // Preview: polyline ate a posicao do mouse
    if (this.polyline) {
      this.polyline.setLatLngs(preview);
    }
    // Preview: polygon ate a posicao do mouse
    if (this.drawMode === 'polygon' && this.polygon && this.points.length >= 2) {
      this.polygon.setLatLngs(preview);
    }
  }

  // ========================================================================
  // Helpers internos
  // ========================================================================

  private notifyPointsChanged(): void {
    this.onPointsChanged?.([...this.points]);
  }

  private detachHandlers(): void {
    if (!this.map) return;
    if (this.clickHandler) this.map.off('click', this.clickHandler);
    if (this.contextMenuHandler) this.map.off('contextmenu', this.contextMenuHandler);
    if (this.mouseMoveHandler) this.map.off('mousemove', this.mouseMoveHandler);

    this.map.getContainer().style.cursor = '';

    this.clickHandler = null;
    this.contextMenuHandler = null;
    this.mouseMoveHandler = null;
  }

  /**
   * Remove camadas temporarias de desenho.
   * @param removeLabels se false, nao remove labels (usado no finalize, pois
   *        as labels sao transferidas para o grupo finalizado)
   */
  private clearDrawingLayers(removeLabels = true): void {
    if (this.polyline && this.map) {
      this.map.removeLayer(this.polyline);
    }
    this.polyline = null;

    if (this.polygon && this.map) {
      this.map.removeLayer(this.polygon);
    }
    this.polygon = null;

    for (const m of this.markers) {
      if (this.map) this.map.removeLayer(m);
    }
    this.markers = [];

    if (removeLabels) {
      for (const l of this.labels) {
        if (this.map) this.map.removeLayer(l);
      }
    }
    this.labels = [];
  }
}

// ============================================================================
// Funcoes utilitarias puras (exportadas para reuso)
// ============================================================================

/** Distância geodésica Vincenty (WGS84 elipsoide, ~0,06 mm de precisão). */
export function haversineDistance(
  lat1: number, lng1: number,
  lat2: number, lng2: number
): number {
  const a = 6_378_137.0;           // semi-eixo maior WGS84 (m)
  const b = 6_356_752.314_245;     // semi-eixo menor WGS84 (m)
  const f = 1 / 298.257_223_563;

  const φ1 = lat1 * Math.PI / 180;  const φ2 = lat2 * Math.PI / 180;
  const L  = (lng2 - lng1) * Math.PI / 180;

  const tanU1 = (1 - f) * Math.tan(φ1);  const cosU1 = 1 / Math.sqrt(1 + tanU1 * tanU1);  const sinU1 = tanU1 * cosU1;
  const tanU2 = (1 - f) * Math.tan(φ2);  const cosU2 = 1 / Math.sqrt(1 + tanU2 * tanU2);  const sinU2 = tanU2 * cosU2;

  let λ = L;
  let sinλ = 0, cosλ = 0, sinSigma = 0, cosSigma = 0, sigma = 0;
  let sinAlpha = 0, cos2Alpha = 0, cos2SigmaM = 0, C = 0;
  let iter = 0;
  do {
    const λPrev = λ;
    sinλ = Math.sin(λ);  cosλ = Math.cos(λ);
    const t1 = cosU2 * sinλ;  const t2 = cosU1 * sinU2 - sinU1 * cosU2 * cosλ;
    sinSigma = Math.sqrt(t1 * t1 + t2 * t2);
    if (sinSigma === 0) return 0;
    cosSigma   = sinU1 * sinU2 + cosU1 * cosU2 * cosλ;
    sigma      = Math.atan2(sinSigma, cosSigma);
    sinAlpha   = cosU1 * cosU2 * sinλ / sinSigma;
    cos2Alpha  = 1 - sinAlpha * sinAlpha;
    cos2SigmaM = cos2Alpha !== 0 ? cosSigma - 2 * sinU1 * sinU2 / cos2Alpha : 0;
    C = f / 16 * cos2Alpha * (4 + f * (4 - 3 * cos2Alpha));
    λ = L + (1 - C) * f * sinAlpha * (
      sigma + C * sinSigma * (cos2SigmaM + C * cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM))
    );
    if (Math.abs(λ - λPrev) <= 1e-12) break;
  } while (++iter < 100);

  const u2 = cos2Alpha * (a * a - b * b) / (b * b);
  const A  = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)));
  const B  = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)));
  const Δσ = B * sinSigma * (
    cos2SigmaM + B / 4 * (
      cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM) -
      B / 6 * cos2SigmaM * (-3 + 4 * sinSigma * sinSigma) * (-3 + 4 * cos2SigmaM * cos2SigmaM)
    )
  );
  return b * A * (sigma - Δσ);
}

/** Formata metros em string legivel (m ou km) */
export function formatDistance(meters: number): string {
  if (meters >= 1000) return `${(meters / 1000).toFixed(2)} km`;
  return `${meters.toFixed(2)} m`;
}
