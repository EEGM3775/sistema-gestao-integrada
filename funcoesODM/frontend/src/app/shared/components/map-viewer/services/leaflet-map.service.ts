import { Injectable } from '@angular/core';
import * as L from 'leaflet';
import { BasemapType, MeasurementResult } from '../models/map-viewer.model';

/**
 * Service Leaflet Map
 * 
 * Encapsula toda a lógica de interação com Leaflet:
 * - Inicialização do mapa
 * - Gerenciamento de basemaps
 * - Gerenciamento de layers
 * - Ferramentas de medição
 * - Cálculos geométricos
 * 
 * Responsabilidades:
 * - Abstrair API do Leaflet
 * - Fornecer interface simplificada
 * - Gerenciar estado interno do mapa
 */
@Injectable()
export class LeafletMapService {
  private map!: L.Map;
  private baseLayers: Record<BasemapType, L.TileLayer> = {
    satellite: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Tiles © Esri',
      maxZoom: 19
    }),
    street: L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
      maxZoom: 19
    }),
    terrain: L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenTopoMap contributors',
      maxZoom: 17
    })
  };

  private overlayLayers: L.LayerGroup = L.layerGroup();
  private measureLayer: L.LayerGroup = L.layerGroup();
  private measurePoints: L.LatLng[] = [];

  /**
   * Inicializa o mapa Leaflet
   */
  initMap(element: HTMLElement, center: [number, number], zoom: number = 13): L.Map {
    this.map = L.map(element, {
      center,
      zoom,
      zoomControl: false,
      attributionControl: false
    });

    // Add default basemap
    this.baseLayers.satellite.addTo(this.map);
    
    // Add overlay layers
    this.overlayLayers.addTo(this.map);
    this.measureLayer.addTo(this.map);

    // Add scale control
    L.control.scale({ position: 'bottomleft' }).addTo(this.map);

    return this.map;
  }

  /**
   * Retorna a instância do mapa
   */
  getMap(): L.Map {
    return this.map;
  }

  /**
   * Troca o basemap
   */
  setBasemap(type: BasemapType): void {
    Object.values(this.baseLayers).forEach(layer => {
      if (this.map.hasLayer(layer)) {
        this.map.removeLayer(layer);
      }
    });
    this.baseLayers[type].addTo(this.map);
  }

  /**
   * Zoom in
   */
  zoomIn(): void {
    this.map.zoomIn();
  }

  /**
   * Zoom out
   */
  zoomOut(): void {
    this.map.zoomOut();
  }

  /**
   * Ajusta o mapa aos limites
   */
  fitBounds(bounds?: L.LatLngBoundsExpression): void {
    if (bounds) {
      this.map.fitBounds(bounds);
    } else {
      const center = this.map.getCenter();
      const defaultBounds = L.latLngBounds([
        [center.lat - 0.01, center.lng - 0.01],
        [center.lat + 0.01, center.lng + 0.01]
      ]);
      this.map.fitBounds(defaultBounds);
    }
  }

  /**
   * Adiciona uma layer de imagem
   */
  addImageLayer(url: string, bounds: L.LatLngBoundsExpression, opacity: number = 1): L.ImageOverlay {
    const imageOverlay = L.imageOverlay(url, bounds, { opacity });
    this.overlayLayers.addLayer(imageOverlay);
    return imageOverlay;
  }

  /**
   * Remove uma layer
   */
  removeLayer(layer: L.Layer): void {
    this.overlayLayers.removeLayer(layer);
  }

  /**
   * Adiciona um marcador
   */
  addMarker(lat: number, lng: number, options?: L.MarkerOptions): L.Marker {
    const marker = L.marker([lat, lng], options);
    this.overlayLayers.addLayer(marker);
    return marker;
  }

  /**
   * Inicia medição
   */
  startMeasurement(mode: 'distance' | 'area'): void {
    this.clearMeasurement();
    this.measurePoints = [];
    
    const clickHandler = (e: L.LeafletMouseEvent) => {
      this.addMeasurePoint(e.latlng, mode);
    };

    this.map.on('click', clickHandler);
    (this.map as any)._measureClickHandler = clickHandler; // Store reference for cleanup
  }

  /**
   * Para medição
   */
  stopMeasurement(): void {
    const handler = (this.map as any)._measureClickHandler;
    if (handler) {
      this.map.off('click', handler);
      delete (this.map as any)._measureClickHandler;
    }
  }

  /**
   * Limpa medição
   */
  clearMeasurement(): void {
    this.stopMeasurement();
    this.measureLayer.clearLayers();
    this.measurePoints = [];
  }

  /**
   * Adiciona ponto de medição
   */
  private addMeasurePoint(latlng: L.LatLng, mode: 'distance' | 'area'): MeasurementResult | null {
    this.measurePoints.push(latlng);

    // Add point marker
    const pointMarker = L.circleMarker(latlng, {
      radius: 5,
      color: '#3b82f6',
      fillColor: '#3b82f6',
      fillOpacity: 1
    });
    this.measureLayer.addLayer(pointMarker);

    if (mode === 'distance' && this.measurePoints.length >= 2) {
      const polyline = L.polyline(this.measurePoints, {
        color: '#3b82f6',
        weight: 3
      });
      this.measureLayer.addLayer(polyline);

      const distance = this.calculateDistance(this.measurePoints);
      return {
        type: 'distance',
        value: distance,
        unit: distance >= 1000 ? 'km' : 'm',
        coordinates: [...this.measurePoints]
      };
    } else if (mode === 'area' && this.measurePoints.length >= 3) {
      const polygon = L.polygon(this.measurePoints, {
        color: '#3b82f6',
        weight: 2,
        fillColor: '#3b82f6',
        fillOpacity: 0.2
      });
      this.measureLayer.addLayer(polygon);

      const area = this.calculateArea(this.measurePoints);
      return {
        type: 'area',
        value: area,
        unit: area >= 10000 ? 'ha' : 'm²',
        coordinates: [...this.measurePoints]
      };
    }

    return null;
  }

  /**
   * Calcula distância entre pontos
   */
  private calculateDistance(points: L.LatLng[]): number {
    let total = 0;
    for (let i = 1; i < points.length; i++) {
      total += points[i - 1].distanceTo(points[i]);
    }
    return total;
  }

  /**
   * Calcula área do polígono
   */
  private calculateArea(points: L.LatLng[]): number {
    const R = 6371000;
    let area = 0;
    const n = points.length;

    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      const lat1 = points[i].lat * Math.PI / 180;
      const lat2 = points[j].lat * Math.PI / 180;
      const lng1 = points[i].lng * Math.PI / 180;
      const lng2 = points[j].lng * Math.PI / 180;
      
      area += (lng2 - lng1) * (2 + Math.sin(lat1) + Math.sin(lat2));
    }

    return Math.abs(area * R * R / 2);
  }

  /**
   * Destrói o mapa
   */
  destroy(): void {
    if (this.map) {
      this.map.remove();
    }
  }
}
