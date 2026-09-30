import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DashboardStats } from '../../models/dashboard.model';

/**
 * Componente Stats Bar
 * 
 * Exibe uma barra com as estatísticas principais do dashboard:
 * - Total de projetos
 * - Projetos em processamento
 * - Projetos concluídos
 * - Total de imagens
 * 
 * Responsabilidades:
 * - Renderizar estatísticas em formato de cards
 * - Fornecer indicadores visuais com ícones SVG
 */
@Component({
    selector: 'app-stats-bar',
    imports: [CommonModule],
    templateUrl: './stats-bar.component.html',
    styleUrls: ['./stats-bar.component.scss']
})
export class StatsBarComponent {
  /**
   * Estatísticas a serem exibidas
   */
  @Input({ required: true }) stats!: DashboardStats;
}
