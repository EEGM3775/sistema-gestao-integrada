import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SelectedInfo } from '../../models/map-viewer.model';

/**
 * Componente Map Info Panel
 * 
 * Painel de informações do mapa:
 * - Detalhes de features clicadas
 * - Informações contextuais
 * - Coordenadas de ponto
 * 
 * Responsabilidades:
 * - Renderizar informações selecionadas
 * - Emitir eventos de fechamento
 * - Formatar dados para exibição
 */
@Component({
  selector: 'app-map-info-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './map-info-panel.component.html',
  styleUrls: ['./map-info-panel.component.scss']
})
export class MapInfoPanelComponent {
  @Input() info: SelectedInfo | null = null;
  @Input() visible: boolean = false;

  @Output() close = new EventEmitter<void>();

  onClose(): void {
    this.close.emit();
  }
}
