import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ProjectUI } from '../../models/dashboard.model';

/**
 * Componente Project Grid
 * 
 * Exibe os projetos em formato de grade (cards).
 * Cada card mostra:
 * - Thumbnail do projeto
 * - Nome e descrição
 * - Status (badge)
 * - Progresso (se em processamento)
 * - Metadados (data, área, nº de imagens)
 * - Ações (mapa, download, menu)
 * 
 * Responsabilidades:
 * - Renderizar grid de projetos
 * - Emitir eventos para ações dos botões
 * - Exibir loading placeholder em caso de erro de imagem
 */
@Component({
  selector: 'app-project-grid',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './project-grid.component.html',
  styleUrls: ['./project-grid.component.scss']
})
export class ProjectGridComponent {
  /**
   * Lista de projetos a serem exibidos
   */
  @Input({ required: true }) projects: ProjectUI[] = [];

  /**
   * Evento emitido quando o botão de mapa é clicado
   */
  @Output() mapClick = new EventEmitter<{ event: Event; project: ProjectUI }>();

  /**
   * Evento emitido quando o botão de download é clicado
   */
  @Output() downloadClick = new EventEmitter<{ event: Event; project: ProjectUI }>();

  /**
   * Evento emitido quando o botão de menu é clicado
   */
  @Output() menuClick = new EventEmitter<{ event: Event; project: ProjectUI }>();

  /**
   * Evento emitido quando ocorre erro ao carregar imagem
   */
  @Output() imageError = new EventEmitter<Event>();

  /**
   * Retorna o label traduzido do status
   */
  getStatusLabel(status: string): string {
    const labels: Record<string, string> = {
      'COMPLETED': 'Concluído',
      'PROCESSING': 'Processando',
      'PENDING': 'Pendente',
      'ERROR': 'Erro'
    };
    return labels[status] || status;
  }

  /**
   * Handler para clique no botão de mapa
   */
  onMapClick(event: Event, project: ProjectUI): void {
    this.mapClick.emit({ event, project });
  }

  /**
   * Handler para clique no botão de download
   */
  onDownloadClick(event: Event, project: ProjectUI): void {
    this.downloadClick.emit({ event, project });
  }

  /**
   * Handler para clique no botão de menu
   */
  onMenuClick(event: Event, project: ProjectUI): void {
    this.menuClick.emit({ event, project });
  }

  /**
   * Handler para erro de carregamento de imagem
   */
  onImageError(event: Event): void {
    this.imageError.emit(event);
  }
}
