/**
 * GcpListComponent
 *
 * Lista os pontos GCP carregados, exibindo dot colorido, coordenadas,
 * altitude, contador de marcas e botao de remocao.
 * Responsabilidade unica: renderizacao e interacao com a lista de GCPs.
 */

import {
  Component, Input, Output, EventEmitter, ChangeDetectionStrategy
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { GcpPoint, GcpMark } from '../../models/gcp-mark.model';

@Component({
  selector: 'app-gcp-list',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <!-- Cabecalho da lista -->
    <div class="gcp-list-header">
      <span>{{ gcpPoints.length }} pontos GCP</span>
      <div class="list-header-actions">
        <button class="btn-link" (click)="openMapRequest.emit()">+ Mapa</button>
        <button class="btn-link" (click)="toggleImportRequest.emit()">
          {{ showImportPanel ? 'Ocultar' : '+ Importar texto' }}
        </button>
      </div>
    </div>

    <!-- Lista de GCPs -->
    <div class="gcp-list">
      @for (gcp of gcpPoints; track gcp.id) {
        <div
          class="gcp-item"
          [class.active]="selectedGcpId === gcp.id"
          (click)="gcpSelected.emit(gcp.id)"
        >
          <span class="gcp-dot" [style.background]="colorOf(gcp.id)"></span>
          <div class="gcp-item-info">
            <span class="gcp-label">{{ gcp.label }}</span>
            <span class="gcp-coord">{{ gcp.lat.toFixed(5) }}, {{ gcp.lng.toFixed(5) }}</span>
            <span class="gcp-alt">alt: {{ gcp.alt.toFixed(1) }} m</span>
          </div>
          <span class="gcp-mark-count" [class.ok]="markCount(gcp.id) >= 2">
            {{ markCount(gcp.id) }}
          </span>
          <button
            class="btn-remove-gcp"
            (click)="onRemoveClick(gcp.id, $event)"
            title="Remover GCP"
          >
            <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12">
              <path d="M11 1.5v1h3.5a.5.5 0 0 1 0 1h-.538l-.853 10.66A2 2 0 0 1 11.115 16h-6.23a2 2 0 0 1-1.994-1.84L2.038 3.5H1.5a.5.5 0 0 1 0-1H5v-1A1.5 1.5 0 0 1 6.5 0h3A1.5 1.5 0 0 1 11 1.5m-5 0v1h4v-1a.5.5 0 0 0-.5-.5h-3a.5.5 0 0 0-.5.5M4.5 5.029l.5 8.5a.5.5 0 1 0 .998-.058l-.5-8.5a.5.5 0 1 0-.998.058m6.53-.528a.5.5 0 0 0-.528.47l-.5 8.5a.5.5 0 0 0 .998.058l.5-8.5a.5.5 0 0 0-.47-.528M8 4.5a.5.5 0 0 0-.5.5v8.5a.5.5 0 0 0 1 0V5a.5.5 0 0 0-.5-.5"/>
            </svg>
          </button>
        </div>
      }
    </div>

    <!-- Instrucao para o GCP selecionado -->
    @if (selectedGcpId) {
      <div class="gcp-instruction">
        <span class="dot" [style.background]="colorOf(selectedGcpId)"></span>
        Selecionado: <strong>{{ labelOf(selectedGcpId) }}</strong><br>
        Clique na imagem onde este alvo aparece.
      </div>
    }
  `,
  styles: [`
    .gcp-list-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 12px;
      color: #8b949e;
    }

    .list-header-actions {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .gcp-list {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .gcp-item {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 8px;
      border-radius: 6px;
      cursor: pointer;
      border: 1px solid transparent;
    }

    .gcp-item:hover { background: #161b22; }
    .gcp-item:hover .btn-remove-gcp { opacity: 1; }
    .gcp-item.active {
      background: #161b22;
      border-color: #30363d;
    }

    .gcp-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      flex-shrink: 0;
      margin-top: 3px;
    }

    .gcp-item-info {
      display: flex;
      flex-direction: column;
      gap: 2px;
      flex: 1;
    }

    .gcp-label {
      font-size: 12px;
      font-weight: 600;
      color: #e6edf3;
    }

    .gcp-coord {
      font-size: 10px;
      color: #8b949e;
      font-family: monospace;
    }

    .gcp-alt {
      font-size: 10px;
      color: #8b949e;
    }

    .gcp-mark-count {
      font-size: 11px;
      color: #8b949e;
      background: #21262d;
      border-radius: 10px;
      padding: 1px 6px;
      flex-shrink: 0;
      font-weight: 700;
    }

    .gcp-mark-count.ok {
      color: #3fb950;
      background: #1a3025;
    }

    .btn-remove-gcp {
      background: none;
      border: none;
      color: #f85149;
      cursor: pointer;
      font-size: 10px;
      font-family: monospace;
      padding: 2px 4px;
      flex-shrink: 0;
      opacity: 0;
      transition: opacity 0.15s;
      line-height: 1;
    }

    .btn-remove-gcp:hover { color: #ff6b6b; }

    .gcp-instruction {
      font-size: 11px;
      color: #c9d1d9;
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 6px;
      padding: 8px;
      line-height: 1.5;
    }

    .gcp-instruction .dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      margin-right: 4px;
    }

    .dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .btn-link {
      background: none;
      border: none;
      color: #58a6ff;
      cursor: pointer;
      font-size: 11px;
      padding: 0;
    }
  `]
})
export class GcpListComponent {

  @Input({ required: true }) gcpPoints: GcpPoint[] = [];
  @Input({ required: true }) marks: GcpMark[] = [];
  @Input() selectedGcpId: string | null = null;
  @Input() showImportPanel = false;

  @Output() gcpSelected        = new EventEmitter<string>();
  @Output() gcpRemoved         = new EventEmitter<string>();
  @Output() openMapRequest     = new EventEmitter<void>();
  @Output() toggleImportRequest = new EventEmitter<void>();

  private readonly PALETTE = [
    '#ff4444', '#44aaff', '#44ff88', '#ffaa00',
    '#aa44ff', '#ff44aa', '#00ccff', '#ffff44'
  ];

  colorOf(gcpId: string): string {
    const idx = this.gcpPoints.findIndex(g => g.id === gcpId);
    return this.PALETTE[Math.max(0, idx) % this.PALETTE.length];
  }

  labelOf(gcpId: string): string {
    return this.gcpPoints.find(g => g.id === gcpId)?.label ?? gcpId;
  }

  markCount(gcpId: string): number {
    return this.marks.filter(m => m.gcpId === gcpId).length;
  }

  onRemoveClick(gcpId: string, event: MouseEvent): void {
    event.stopPropagation();
    this.gcpRemoved.emit(gcpId);
  }
}
