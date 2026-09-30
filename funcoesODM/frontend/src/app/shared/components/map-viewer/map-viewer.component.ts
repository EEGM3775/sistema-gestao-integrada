import { Component, Input, OnInit, OnDestroy, AfterViewInit, ElementRef, ViewChild, Output, EventEmitter, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import * as L from 'leaflet';

// Sub-components
import { MapControlsComponent } from './components/map-controls/map-controls.component';
import { LayerPanelComponent } from './components/layer-panel/layer-panel.component';
import { MapInfoPanelComponent } from './components/map-info-panel/map-info-panel.component';

// Services
import { LeafletMapService } from './services/leaflet-map.service';

// Models
import {
  MapLayer,
  MapMarker,
  MeasurementResult,
  BasemapType,
  MeasurementMode,
  MapCoordinates,
  SelectedInfo
} from './models/map-viewer.model';

/**
 * Componente Map Viewer (Refatorado)
 * 
 * Visualizador de mapas interativo com Leaflet.
 * 
 * Features:
 * - Múltiplos basemaps (satélite, street, terrain)
 * - Gerenciamento de layers (orthomosaic, DSM, DTM, NDVI)
 * - Ferramentas de medição (distância, área, volume)
 * - Marcadores customizáveis
 * - Info panels e coordenadas
 * 
 * Responsabilidades (Coordenador):
 * - Inicializar mapa via LeafletMapService
 * - Gerenciar estado de layers, basemap, medições
 * - Coordenar comunicação entre sub-componentes
 * - Emitir eventos para componente pai
 * 
 * Arquitetura:
 * - map-controls: Botões de zoom, basemap, medição
 * - layer-panel: Painel de camadas com opacidade
 * - map-info-panel: Informações de features clicadas
 * - leaflet-map.service: Lógica de mapa e cálculos
 */
@Component({
  selector: 'app-map-viewer',
  standalone: true,
  imports: [
    CommonModule,
    MapControlsComponent,
    LayerPanelComponent,
    MapInfoPanelComponent
  ],
  providers: [LeafletMapService],
  templateUrl: './map-viewer.component.html',
  styleUrls: ['./map-viewer.component.scss']
})
export class MapViewerComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('mapElement', { static: true }) mapElement!: ElementRef<HTMLElement>;

  // Inputs
  @Input() center: [number, number] = [-23.5505, -46.6333]; // São Paulo default
  @Input() zoom: number = 13;
  @Input() projectId?: number; // ID do projeto (opcional)
  @Input() layers: MapLayer[] = [];
  @Input() markers: MapMarker[] = [];

  // Outputs
  @Output() mapReady = new EventEmitter<L.Map>();
  @Output() measurementComplete = new EventEmitter<MeasurementResult>();
  @Output() markerClick = new EventEmitter<MapMarker>();
  @Output() mapClick = new EventEmitter<MapCoordinates>();

  // State signals
  currentBasemap = signal<BasemapType>('satellite');
  measurementMode = signal<MeasurementMode>(null);
  showLayerPanel = signal<boolean>(false);
  showInfoPanel = signal<boolean>(false);
  currentCoordinates = signal<MapCoordinates | null>(null);
  currentZoom = signal<number>(13);
  selectedInfo = signal<SelectedInfo | null>(null);
  isLoading = signal<boolean>(true);

  // Layer references
  private layerRefs: Map<string, L.Layer> = new Map();
  private markerRefs: Map<string, L.Marker> = new Map();

  constructor(private mapService: LeafletMapService) {}

  ngOnInit(): void {
    // Initialization logic
  }

  ngAfterViewInit(): void {
    this.initializeMap();
  }

  ngOnDestroy(): void {
    this.mapService.destroy();
  }

  /**
   * Inicializa o mapa Leaflet
   */
  private initializeMap(): void {
    const map = this.mapService.initMap(
      this.mapElement.nativeElement,
      this.center,
      this.zoom
    );

    // Map event listeners
    map.on('zoomend', () => {
      this.currentZoom.set(map.getZoom());
    });

    map.on('mousemove', (e: L.LeafletMouseEvent) => {
      this.currentCoordinates.set({
        lat: e.latlng.lat,
        lng: e.latlng.lng
      });
    });

    map.on('click', (e: L.LeafletMouseEvent) => {
      this.mapClick.emit({
        lat: e.latlng.lat,
        lng: e.latlng.lng
      });
    });

    // Initialize layers
    this.initializeLayers();

    // Initialize markers
    this.initializeMarkers();

    this.isLoading.set(false);
    this.mapReady.emit(map);
  }

  /**
   * Inicializa layers no mapa
   */
  private initializeLayers(): void {
    this.layers.forEach(layer => {
      if (layer.url && layer.bounds && layer.visible) {
        const imageOverlay = this.mapService.addImageLayer(
          layer.url,
          layer.bounds,
          layer.opacity
        );
        this.layerRefs.set(layer.id, imageOverlay);
      }
    });
  }

  /**
   * Inicializa marcadores
   */
  private initializeMarkers(): void {
    this.markers.forEach(marker => {
      const leafletMarker = this.mapService.addMarker(marker.lat, marker.lng, {
        title: marker.label
      });

      leafletMarker.on('click', () => {
        this.markerClick.emit(marker);
      });

      this.markerRefs.set(marker.id, leafletMarker);
    });
  }

  /**
   * Event handlers - Map Controls
   */
  onZoomIn(): void {
    this.mapService.zoomIn();
  }

  onZoomOut(): void {
    this.mapService.zoomOut();
  }

  onFitBounds(): void {
    this.mapService.fitBounds();
  }

  onBasemapChange(basemap: BasemapType): void {
    this.currentBasemap.set(basemap);
    this.mapService.setBasemap(basemap);
  }

  onMeasurementModeChange(mode: MeasurementMode): void {
    this.measurementMode.set(mode);
    
    if (mode === null) {
      this.mapService.clearMeasurement();
    } else if (mode === 'distance' || mode === 'area') {
      this.mapService.startMeasurement(mode);
    }
  }

  onToggleLayers(): void {
    this.showLayerPanel.update(v => !v);
  }

  /**
   * Event handlers - Layer Panel
   */
  onLayerToggle(layerId: string): void {
    const layer = this.layers.find(l => l.id === layerId);
    if (!layer) return;

    layer.visible = !layer.visible;
    const layerRef = this.layerRefs.get(layerId);

    if (layer.visible && layer.url && layer.bounds && !layerRef) {
      const imageOverlay = this.mapService.addImageLayer(
        layer.url,
        layer.bounds,
        layer.opacity
      );
      this.layerRefs.set(layerId, imageOverlay);
    } else if (!layer.visible && layerRef) {
      this.mapService.removeLayer(layerRef);
      this.layerRefs.delete(layerId);
    }
  }

  onOpacityChange(event: { layerId: string; opacity: number }): void {
    const layer = this.layers.find(l => l.id === event.layerId);
    if (!layer) return;

    layer.opacity = event.opacity;
    const layerRef = this.layerRefs.get(event.layerId);
    
    if (layerRef && 'setOpacity' in layerRef) {
      (layerRef as L.ImageOverlay).setOpacity(event.opacity);
    }
  }

  onCloseLayerPanel(): void {
    this.showLayerPanel.set(false);
  }

  /**
   * Event handlers - Info Panel
   */
  onCloseInfoPanel(): void {
    this.showInfoPanel.set(false);
    this.selectedInfo.set(null);
  }

  /**
   * Public API - Para uso externo
   */
  setCenter(lat: number, lng: number, zoom?: number): void {
    const map = this.mapService.getMap();
    if (map) {
      map.setView([lat, lng], zoom || map.getZoom());
    }
  }

  addLayer(layer: MapLayer): void {
    this.layers.push(layer);
    
    if (layer.visible && layer.url && layer.bounds) {
      const imageOverlay = this.mapService.addImageLayer(
        layer.url,
        layer.bounds,
        layer.opacity
      );
      this.layerRefs.set(layer.id, imageOverlay);
    }
  }

  removeLayer(layerId: string): void {
    const layerRef = this.layerRefs.get(layerId);
    if (layerRef) {
      this.mapService.removeLayer(layerRef);
      this.layerRefs.delete(layerId);
    }
    
    const index = this.layers.findIndex(l => l.id === layerId);
    if (index >= 0) {
      this.layers.splice(index, 1);
    }
  }

  addMarker(marker: MapMarker): void {
    this.markers.push(marker);
    
    const leafletMarker = this.mapService.addMarker(marker.lat, marker.lng, {
      title: marker.label
    });

    leafletMarker.on('click', () => {
      this.markerClick.emit(marker);
    });

    this.markerRefs.set(marker.id, leafletMarker);
  }

  showInfo(info: SelectedInfo): void {
    this.selectedInfo.set(info);
    this.showInfoPanel.set(true);
  }
}
