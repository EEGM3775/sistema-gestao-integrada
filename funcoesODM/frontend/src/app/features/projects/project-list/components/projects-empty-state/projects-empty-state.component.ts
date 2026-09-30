import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ButtonComponent } from '../../../../../shared/components/button/button.component';

/**
 * Componente Empty State
 * 
 * Exibe mensagem quando nenhum projeto é encontrado.
 * Adapta mensagem baseada em:
 * - Filtros ativos (sugere limpar filtros)
 * - Sem filtros (sugere criar projeto)
 * 
 * Responsabilidades:
 * - Renderizar estado vazio
 * - Fornecer ações contextuais
 * - Emitir evento para limpar filtros
 */
@Component({
  selector: 'app-projects-empty-state',
  standalone: true,
  imports: [CommonModule, RouterLink, ButtonComponent],
  templateUrl: './projects-empty-state.component.html',
  styleUrls: ['./projects-empty-state.component.scss']
})
export class ProjectsEmptyStateComponent {
  @Input() hasActiveFilters: boolean = false;
  @Output() clearFilters = new EventEmitter<void>();

  onClearFilters(): void {
    this.clearFilters.emit();
  }
}
