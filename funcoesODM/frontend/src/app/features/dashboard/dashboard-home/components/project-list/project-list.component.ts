import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ProjectUI } from '../../models/dashboard.model';

/**
 * Componente Project List
 * 
 * Exibe os projetos em formato de lista (tabela).
 * Cada linha mostra:
 * - Thumbnail pequeno + Nome e descrição
 * - Status (pill badge)
 * - Progresso (mini barra se em processamento)
 * - Número de imagens
 * - Área
 * - Data de criação
 * - Ações (mapa, download, menu)
 * 
 * Responsabilidades:
 * - Renderizar lista tabular de projetos
 * - Emitir eventos para ações dos botões
 * - Exibir loading placeholder em caso de erro de imagem
 */
@Component({
    selector: 'app-project-list',
    imports: [CommonModule, RouterLink],
    templateUrl: './project-list.component.html',
    styleUrls: ['./project-list.component.scss']
})
export class ProjectListComponent {
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
