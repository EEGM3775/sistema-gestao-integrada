import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { BasemapType, MeasurementMode } from '../../models/map-viewer.model';

/**
 * Componente Map Controls
 * 
 * Controles do mapa:
 * - Zoom (in/out/fit)
 * - Basemap (satélite/street/terrain)
 * - Ferramentas de medição (distância/área/volume)
 * - Layers toggle
 * 
 * Responsabilidades:
 * - Renderizar botões de controle
 * - Emitir eventos de ações
 * - Indicar estado ativo
 */
@Component({
  selector: 'app-map-controls',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './map-controls.component.html',
  styleUrls: ['./map-controls.component.scss']
})
export class MapControlsComponent {
  @Input() currentBasemap: BasemapType = 'satellite';
  @Input() measurementMode: MeasurementMode = null;
  @Input() showLayers: boolean = false;

  @Output() zoomIn = new EventEmitter<void>();
  @Output() zoomOut = new EventEmitter<void>();
  @Output() fitBounds = new EventEmitter<void>();
  @Output() basemapChange = new EventEmitter<BasemapType>();
  @Output() measurementModeChange = new EventEmitter<MeasurementMode>();
  @Output() toggleLayers = new EventEmitter<void>();

  onZoomIn(): void {
    this.zoomIn.emit();
  }

  onZoomOut(): void {
    this.zoomOut.emit();
  }

  onFitBounds(): void {
    this.fitBounds.emit();
  }

  setBasemap(type: BasemapType): void {
    this.basemapChange.emit(type);
  }

  setMeasurementMode(mode: MeasurementMode): void {
    this.measurementModeChange.emit(mode);
  }

  onToggleLayers(): void {
    this.toggleLayers.emit();
  }
}
