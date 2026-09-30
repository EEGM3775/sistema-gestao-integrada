import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ViewerStats } from '../../models/project-3d.model';

/**
 * Componente Viewer Stats
 * 
 * Painel de estatísticas do visualizador:
 * - Número de pontos
 * - FPS (frames por segundo)
 * - Uso de memória
 * 
 * Responsabilidades:
 * - Exibir métricas em tempo real
 * - Formatar números grandes
 * - Atualizar estatísticas dinamicamente
 */
@Component({
  selector: 'app-viewer-stats',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './viewer-stats.component.html',
  styleUrls: ['./viewer-stats.component.scss']
})
export class ViewerStatsComponent {
  @Input() stats: ViewerStats = {
    points: 0,
    fps: 0,
    memory: 0
  };

  formatNumber(num: number): string {
    if (num >= 1000000) {
      return (num / 1000000).toFixed(2) + 'M';
    } else if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
  }
}
