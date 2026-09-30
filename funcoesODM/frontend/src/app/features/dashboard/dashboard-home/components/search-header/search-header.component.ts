import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ButtonComponent } from '../../../../../shared/components/button/button.component';
import { ViewMode } from '../../models/dashboard.model';

/**
 * Componente Search Header
 * 
 * Cabeçalho do dashboard com:
 * - Título e subtítulo
 * - Caixa de busca
 * - Toggle entre visualização grid/list
 * - Botão de criar novo projeto
 * 
 * Responsabilidades:
 * - Renderizar cabeçalho com controles
 * - Emitir eventos de busca
 * - Emitir eventos de mudança de visualização
 * - Fornecer navegação para criação de projeto
 */
@Component({
  selector: 'app-search-header',
  standalone: true,
  imports: [CommonModule, ButtonComponent],
  templateUrl: './search-header.component.html',
  styleUrls: ['./search-header.component.scss']
})
export class SearchHeaderComponent {
  /**
   * Modo de visualização atual (grid ou list)
   */
  @Input({ required: true }) viewMode!: ViewMode;

  /**
   * Termo de busca atual
   */
  @Input() searchTerm: string = '';

  /**
   * Nome do usuário logado
   */
  @Input() userName: string = '';

  /**
   * Evento emitido quando o usuário digita na busca
   */
  @Output() searchChange = new EventEmitter<Event>();

  /**
   * Evento emitido quando o modo de visualização muda
   */
  @Output() viewModeChange = new EventEmitter<ViewMode>();

  /**
   * Handler para mudança na busca
   */
  onSearch(event: Event): void {
    this.searchChange.emit(event);
  }

  /**
   * Handler para mudança do modo de visualização
   */
  setViewMode(mode: ViewMode): void {
    this.viewModeChange.emit(mode);
  }
}
