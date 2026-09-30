/**
 * MeasDrawingToolbarComponent
 * 
 * Barra de ferramentas de desenho da aba de medições.
 * Componente puramente apresentacional — sem estado interno, sem serviços.
 *
 * Inputs:
 *   activeTool         — ferramenta ativa ('distance' | 'area' | 'volume' | 'height' | null)
 *   hasDataSource      — existe fonte de dados selecionada?
 *   hasDSM             — existe DSM/DTM disponível?
 *   isDrawing          — desenho em andamento?
 *   isQuerying         — consulta assíncrona ao DSM em andamento?
 *   drawingPointsCount — quantidade de pontos desenhados até o momento
 *
 * Outputs:
 *   toolActivated   — usuário clicou para ativar/desativar uma ferramenta
 *   undoRequest     — usuário quer desfazer último ponto
 *   completeRequest — usuário quer finalizar a medição
 *   cancelRequest   — usuário quer cancelar o desenho
 *   clearAllRequest — usuário quer limpar todas as medições
 */

import {
  Component, Input, Output, EventEmitter,
  ChangeDetectionStrategy
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActiveTool } from '../../models/measurement-data';

@Component({
    selector: 'app-meas-drawing-toolbar',
    imports: [CommonModule],
    templateUrl: './meas-drawing-toolbar.component.html',
    styleUrls: ['./meas-drawing-toolbar.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush
})
export class MeasDrawingToolbarComponent {
  @Input() activeTool: ActiveTool = null;
  @Input() hasDataSource = false;
  @Input() hasDSM = false;
  @Input() isDrawing = false;
  @Input() isQuerying = false;
  @Input() drawingPointsCount = 0;

  @Output() toolActivated  = new EventEmitter<NonNullable<ActiveTool>>();
  @Output() undoRequest    = new EventEmitter<void>();
  @Output() completeRequest = new EventEmitter<void>();
  @Output() cancelRequest  = new EventEmitter<void>();
  @Output() clearAllRequest = new EventEmitter<void>();

  get canComplete(): boolean {
    return this.drawingPointsCount >= 2;
  }
}
