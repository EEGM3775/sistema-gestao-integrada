/**
 * MeasListComponent
 *
 * Painel de resultados: cabeçalho (título + contagem + botão Exportar) +
 * lista de medições.
 *
 * Responsabilidades:
 *  - Renderizar a lista de medições usando MeasItemComponent
 *  - Gerenciar estado de edição de nome (editingId / editingName) localmente
 *  - Chamar MeasurementApiService para renomear e emitir resultado ao tab
 *  - Gerenciar qual item está com o acordeão de detalhes aberto (expandedId)
 *
 * Eventos emitidos ao tab (orquestrador):
 *  - visibilityChange   — usuário marcou/desmarcou visibilidade de uma medição
 *  - focusMeasurement   — usuário clicou para centralizar uma medição no mapa
 *  - deleteMeasurement  — usuário deletou uma medição (tab remove do mapa + do signal)
 *  - measurementRenamed — tab deve atualizar o nome no seu signal de medições
 *  - openExport         — tab deve abrir o modal de exportação
 */

import {
  Component, Input, Output, EventEmitter, signal,
  ChangeDetectionStrategy, ChangeDetectorRef, inject
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MeasurementData } from '../../models/measurement-data';
import { MeasurementApiService } from '../../services/measurement-api.service';
import { MeasItemComponent } from '../measurement-item/meas-item.component';

@Component({
    selector: 'app-meas-list',
    imports: [CommonModule, MeasItemComponent],
    templateUrl: './meas-list.component.html',
    styleUrls: ['./meas-list.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush
})
export class MeasListComponent {
  @Input() measurements: MeasurementData[] = [];
  @Input() visibleIds: Set<string> = new Set<string>();
  @Input() projectId!: number;

  @Output() visibilityChange   = new EventEmitter<{ m: MeasurementData; show: boolean }>();
  @Output() focusMeasurement   = new EventEmitter<MeasurementData>();
  @Output() deleteMeasurement  = new EventEmitter<string>();
  @Output() measurementRenamed = new EventEmitter<{ id: string; name: string }>();
  @Output() openExport         = new EventEmitter<void>();

  // ── Estado interno de edição e acordeão ──────────────────────────────────
  readonly expandedId = signal<string | null>(null);
  readonly editingId  = signal<string | null>(null);
  readonly editingName = signal('');

  private cdr = inject(ChangeDetectorRef);
  private api = inject(MeasurementApiService);

  // =========================================================================
  // Acordeão de detalhes
  // =========================================================================

  onToggleDetail(id: string): void {
    this.expandedId.update(cur => cur === id ? null : id);
  }

  // =========================================================================
  // Edição inline de nome
  // =========================================================================

  onStartEdit(m: MeasurementData): void {
    this.editingId.set(m.id);
    this.editingName.set(m.name ?? '');
  }

  onConfirmEdit(m: MeasurementData, rawName: string): void {
    const newName = rawName.trim();
    if (!newName || newName === m.name) {
      this.onCancelEdit();
      return;
    }
    if (!this.projectId) { this.onCancelEdit(); return; }

    this.api.renameMeasurement(this.projectId, m.id, newName).subscribe({
      next: updated => {
        this.measurementRenamed.emit({ id: m.id, name: updated.name });
        this.editingId.set(null);
        this.cdr.markForCheck();
      },
      error: err => {
        console.error('[MeasList] Erro ao renomear:', err);
        this.onCancelEdit();
      }
    });
  }

  onCancelEdit(): void {
    this.editingId.set(null);
    this.editingName.set('');
  }

  // =========================================================================
  // Delegação de eventos de item
  // =========================================================================

  onToggleVisibility(m: MeasurementData, show: boolean): void {
    this.visibilityChange.emit({ m, show });
  }

  onFocusMeasurement(m: MeasurementData): void {
    this.focusMeasurement.emit(m);
  }

  onDelete(id: string): void {
    this.deleteMeasurement.emit(id);
  }
}
