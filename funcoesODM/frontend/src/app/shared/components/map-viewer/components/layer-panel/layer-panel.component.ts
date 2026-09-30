import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MapLayer } from '../../models/map-viewer.model';

/**
 * Componente Layer Panel
 * 
 * Painel de controle de camadas:
 * - Toggle de visibilidade
 * - Controle de opacidade
 * - Ordem de camadas
 * 
 * Responsabilidades:
 * - Renderizar lista de camadas
 * - Emitir eventos de mudança
 * - Indicar estado de cada layer
 */
@Component({
  selector: 'app-layer-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './layer-panel.component.html',
  styleUrls: ['./layer-panel.component.scss']
})
export class LayerPanelComponent {
  @Input() layers: MapLayer[] = [];
  @Input() visible: boolean = false;

  @Output() layerToggle = new EventEmitter<string>();
  @Output() opacityChange = new EventEmitter<{ layerId: string; opacity: number }>();
  @Output() close = new EventEmitter<void>();

  onToggleLayer(layerId: string): void {
    this.layerToggle.emit(layerId);
  }

  onOpacityChange(layerId: string, event: Event): void {
    const opacity = parseFloat((event.target as HTMLInputElement).value);
    this.opacityChange.emit({ layerId, opacity });
  }

  onClose(): void {
    this.close.emit();
  }
}
