import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { Project } from '../../../models/project.model';
import { CardComponent } from '../../../../../shared/components/card/card.component';

/**
 * Componente Project Card Item
 * 
 * Card individual de projeto com:
 * - Nome e status
 * - Descrição
 * - Estatísticas (imagens, tarefas)
 * - Data de criação
 * - Ações (mapa, 3D, deletar)
 * 
 * Responsabilidades:
 * - Renderizar informações do projeto
 * - Emitir eventos de ações
 * - Navegar para detalhes via routerLink
 */
@Component({
  selector: 'app-project-card-item',
  standalone: true,
  imports: [CommonModule, RouterLink, CardComponent],
  templateUrl: './project-card-item.component.html',
  styleUrls: ['./project-card-item.component.scss']
})
export class ProjectCardItemComponent {
  @Input({ required: true }) project!: Project;

  @Output() mapClick = new EventEmitter<number>();
  @Output() view3D = new EventEmitter<number>();
  @Output() deleteClick = new EventEmitter<number>();

  getStatusLabel(status: string): string {
    const labels: Record<string, string> = {
      'PENDING': 'Pendente',
      'PROCESSING': 'Processando',
      'COMPLETED': 'Concluído',
      'ERROR': 'Erro'
    };
    return labels[status] || status;
  }

  onMapClick(event: Event): void {
    event.stopPropagation();
    this.mapClick.emit(this.project.id);
  }

  on3DClick(event: Event): void {
    event.stopPropagation();
    this.view3D.emit(this.project.id);
  }

  onDeleteClick(event: Event): void {
    event.stopPropagation();
    this.deleteClick.emit(this.project.id);
  }
}
