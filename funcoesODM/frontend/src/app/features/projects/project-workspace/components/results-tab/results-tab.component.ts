import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Chunk } from '../../../models/project.model';
import { ResultsViewerComponent } from '../../../components/results-viewer/results-viewer.component';

@Component({
  selector: 'app-results-tab',
  standalone: true,
  imports: [CommonModule, ResultsViewerComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="results-tab">
      @if (chunk.status === 'COMPLETED') {
        <app-results-viewer
          [projectId]="projectId"
          [taskId]="chunk.id"
          [nodeodmTaskId]="chunk.nodeodmTaskId || ''"
          [outputs]="chunkOutputs"
        />
      } @else if (chunk.status === 'RUNNING') {
        <div class="processing-status">
          <div class="spinner-large"></div>
          <h3>Processando...</h3>
          <div class="progress-bar-large">
            <div class="progress-fill" [style.width.%]="chunk.progress"></div>
          </div>
          <span>{{ chunk.progress }}%</span>
        </div>
      } @else if (chunk.status === 'FAILED') {
        <div class="error-status">
          <span class="error-icon">❌</span>
          <h3>Processamento Falhou</h3>
          <p class="error-message">{{ chunk.errorMessage }}</p>
          <button class="btn-retry" (click)="retryProcess.emit()">Tentar Novamente</button>
        </div>
      } @else {
        <div class="no-results">
          <span class="icon">📊</span>
          <h3>Sem resultados ainda</h3>
          <p>Processe este chunk para ver os resultados</p>
          <button class="btn-secondary" (click)="goToProcess.emit()">Ir para Processamento</button>
        </div>
      }
    </div>
  `,
  styles: [`
    .results-tab {
      height: 100%;
    }

    .processing-status, .error-status, .no-results {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100%;
      text-align: center;
      color: #8b949e;
    }

    .spinner-large {
      width: 60px;
      height: 60px;
      border: 4px solid #30363d;
      border-top-color: #58a6ff;
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin-bottom: 16px;
    }

    @keyframes spin { to { transform: rotate(360deg); } }

    .progress-bar-large {
      height: 8px;
      width: 200px;
      background: #30363d;
      border-radius: 2px;
      overflow: hidden;
      margin: 8px 0;
    }

    .progress-fill {
      height: 100%;
      background: #58a6ff;
      transition: width 0.2s;
    }

    .error-icon { font-size: 48px; margin-bottom: 16px; }
    .error-message { color: #f85149; margin: 12px 0; }

    .btn-retry {
      background: #f85149;
      color: white;
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      cursor: pointer;
    }

    .no-results .icon { font-size: 48px; opacity: 0.5; margin-bottom: 16px; }

    .btn-secondary {
      background: #21262d;
      color: #c9d1d9;
      border: 1px solid #30363d;
      padding: 8px 16px;
      border-radius: 6px;
      cursor: pointer;
    }

    .btn-secondary:hover { background: #30363d; }
  `]
})
export class ResultsTabComponent {
  @Input() chunk!: Chunk;
  @Input() projectId!: number;
  @Input() chunkOutputs: any = {};

  @Output() retryProcess = new EventEmitter<void>();
  @Output() goToProcess = new EventEmitter<void>();
}
